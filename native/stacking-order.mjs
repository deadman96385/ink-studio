import {signature} from './stitchplan-model.mjs';

export function validateOrderDisplay(value){
  if(value==null)return;
  if(typeof value!=='object'||!Number.isInteger(value.size)||value.size<0||value.size>100||typeof value.visible!=='boolean'||typeof value.signature!=='string'||value.signature.length>100||!Array.isArray(value.points)||value.points.length>20000||value.points.some((p,i)=>!Array.isArray(p)||p.length!==3||p[2]!==i+1||p.slice(0,2).some(v=>!Number.isFinite(v)||Math.abs(v)>100000))||(value.ids!==null&&(!Array.isArray(value.ids)||value.ids.some(id=>typeof id!=='string'))))throw new Error('This project contains an invalid order-number overlay.');
}

export async function restoreOrderDisplay(backup,project,api){
  const display=backup.orderDisplay;
  if(!display||display.signature!==signature(backup))return '';
  // Sanitization can give an imported SVG (or font) a new asset ID. Obtain
  // fresh engine positions instead of trusting the old annotation coordinates.
  try{const result=await api('/api/stacking-order',{project,ids:display.ids,size:display.size});project.orderDisplay={...display,points:result.points,signature:signature(project)};return '';}
  catch(e){project.orderDisplay={...display,signature:''};return 'Order numbers need regeneration: '+e.message;}
}

export function createStackingOrder(ctx){
  const $=id=>document.getElementById(id);let token=0,busy=false;
  document.head.insertAdjacentHTML('beforeend','<link rel="stylesheet" href="/stacking-order.css">');
  document.body.insertAdjacentHTML('beforeend',`<dialog id="orderDisplayDialog" class="order-display-dialog" aria-labelledby="orderDisplayTitle">
    <div class="dialog-heading"><div><span class="eyebrow">FOLLOW THE SEWING SEQUENCE</span><h2 id="orderDisplayTitle">Order numbers on the canvas.</h2></div><button id="closeOrderDisplay" class="icon-button" aria-label="Close order numbers">×</button></div>
    <p>Number individual paths in sewing order, including the pieces inside text and imported SVGs. Guides and excluded artwork are skipped.</p>
    <div class="order-display-columns"><section>
      <div class="field-row"><label>Number these paths<select id="orderDisplayScope"><option value="all">Whole visible design</option><option value="selection">Selected artwork</option></select></label><label>Label size (mm)<input id="orderDisplaySize" type="number" inputmode="numeric" min="0" max="100" step="1" value="4"></label></div>
      <button id="generateOrderDisplay" class="primary wide">Generate order numbers</button>
      <label class="check"><input id="orderDisplayVisible" type="checkbox">Show saved numbers on canvas</label>
      <div class="button-row"><button id="applyOrderDisplay">Apply display</button><button id="removeOrderDisplay">Remove numbers</button></div>
      <button id="downloadOrderDisplay" class="wide">Download numbered SVG</button><a id="orderDisplayDownload" class="button wide" hidden download>Save numbered SVG</a>
      <p id="orderDisplayStatus" role="status"></p><p id="orderDisplayError" class="error" role="alert"></p>
      <p class="caption">Numbers mark each path’s first node, as in the desktop tool; they are not needle entry commands. Selection numbering starts at 1. A single SVG path with fill and stroke receives one number; a separate border path gets its own.</p>
      <p class="caption">The overlay is saved with the project and portable backup. Editing the design hides outdated numbers until you regenerate them. The numbered SVG keeps its labels in a non-sewing layer.</p>
    </section><section><svg id="orderDisplayPreview" viewBox="-5 -5 110 110" aria-label="Preview of path order numbers"></svg><p class="caption">Preview of the saved overlay. Close this panel to inspect it with the normal canvas zoom and pan.</p></section></div>
  </dialog>`);
  const dialog=$('orderDisplayDialog'),row=()=>ctx.getProject().orderDisplay;
  const stale=()=>row()&&row().signature!==signature(ctx.getProject());
  function labels(host,node,display,size=display.size){
    for(const[x,y,n]of display.points||[]){const label=node('text',{x,y,'font-size':size,'text-anchor':'middle','dominant-baseline':'middle',fill:'#142d27',stroke:'#fffdf5','stroke-width':.45,'stroke-linejoin':'round','paint-order':'stroke fill','font-family':'sans-serif','font-weight':'bold'});label.textContent=n;host.append(label);}
  }
  function preview(){
    const svg=$('orderDisplayPreview');svg.replaceChildren();
    const node=(tag,attrs)=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);return e;};
    svg.append(node('rect',{x:0,y:0,width:100,height:100,fill:ctx.getProject().fabric||'#f7f5ee',stroke:'#acb8ab','stroke-width':.3}));
    const art=ctx.artwork().cloneNode(true);art.removeAttribute('id');art.style.opacity='.65';art.style.visibility='visible';
    // Prefix every ID/reference in the clone so imported masks and gradients
    // resolve inside this preview instead of colliding with the main canvas.
    const ids=new Map([...art.querySelectorAll('[id]')].map(e=>[e.id,'order-preview-'+e.id]));
    for(const e of [art,...art.querySelectorAll('*')]){for(const a of [...e.attributes]){let v=a.value;if(a.name==='id')v=ids.get(v)||v;else{v=v.replace(/url\(#([^)]*)\)/g,(all,id)=>ids.has(id)?`url(#${ids.get(id)})`:all);if(['href','xlink:href'].includes(a.name)&&v.startsWith('#')&&ids.has(v.slice(1)))v='#'+ids.get(v.slice(1));}if(v!==a.value)e.setAttribute(a.name,v);}}svg.append(art);
    if(row()&&!stale()&&$('orderDisplayVisible').checked){const g=node('g',{'pointer-events':'none'});labels(g,node,row(),validSize(false)??row().size);svg.append(g);}
  }
  function refresh(){
    const r=row(),old=stale();$('orderDisplayStatus').textContent=!r?'No saved numbers yet.':old?'The design changed. Saved numbers are hidden; generate them again.':`${r.points.length} numbered paths · ${r.ids?'Selected artwork':'Whole visible design'} · ${r.visible?'Shown':'Hidden'} on canvas.`;
    for(const id of ['generateOrderDisplay','downloadOrderDisplay','orderDisplayScope','orderDisplaySize'])$(id).disabled=busy;
    $('generateOrderDisplay').textContent=busy?'Reading path order…':'Generate order numbers';
    for(const id of ['applyOrderDisplay','removeOrderDisplay','orderDisplayVisible'])$(id).disabled=busy||!r;
    preview();
  }
  function open(){token++;busy=false;$('orderDisplayError').textContent='';$('orderDisplayDownload').hidden=true;$('orderDisplaySize').value=row()?.size??4;$('orderDisplayVisible').checked=row()?.visible??true;
    const hasSelection=ctx.chosen().some(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork'));$('orderDisplayScope').querySelector('[value="selection"]').disabled=!hasSelection;$('orderDisplayScope').value=hasSelection?'selection':'all';refresh();dialog.showModal();}
  function validSize(throwError=true){const input=$('orderDisplaySize');if(!input.value||!input.validity.valid){if(throwError)throw new Error('Choose a whole label size from 0 to 100 mm.');return null;}return Number(input.value);}
  async function generate(download=false){
    if(busy)return;const project=structuredClone(ctx.getProject()),revision=ctx.getRevision(),run=++token;
    try{const size=validSize(),ids=$('orderDisplayScope').value==='selection'?ctx.chosen().filter(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork')).map(l=>l.id):null;if(ids&&!ids.length)throw new Error('Select visible artwork to number.');busy=true;$('orderDisplayError').textContent='';$('orderDisplayDownload').hidden=true;refresh();
      const result=await ctx.api(download?'/api/stacking-order-svg':'/api/stacking-order',{project,ids,size});if(run!==token||!dialog.open)return;if(project.id!==ctx.getProject().id||revision!==ctx.getRevision())throw new Error('The design changed. Generate order numbers again.');
      if(download){$('orderDisplayDownload').href=result.url;$('orderDisplayDownload').hidden=false;ctx.toast('Numbered SVG ready. Tap Save numbered SVG.');}
      else{ctx.mutate(()=>ctx.getProject().orderDisplay={points:result.points,size,ids,visible:true,signature:signature(project)});$('orderDisplayVisible').checked=true;ctx.toast('Order numbers added. Close this panel to inspect the canvas.');}
    }catch(e){if(run===token)$('orderDisplayError').textContent=e.message;}finally{if(run===token){busy=false;refresh();}}
  }
  $('generateOrderDisplay').onclick=()=>generate();$('downloadOrderDisplay').onclick=()=>generate(true);
  $('orderDisplaySize').oninput=()=>{$('orderDisplayDownload').hidden=true;preview();};$('orderDisplayScope').onchange=()=>{$('orderDisplayDownload').hidden=true;};$('orderDisplayVisible').onchange=preview;
  $('applyOrderDisplay').onclick=()=>{try{const size=validSize();if(row())ctx.mutate(()=>Object.assign(row(),{size,visible:$('orderDisplayVisible').checked}));refresh();}catch(e){$('orderDisplayError').textContent=e.message;}};
  $('removeOrderDisplay').onclick=()=>{ctx.mutate(()=>delete ctx.getProject().orderDisplay);refresh();ctx.toast('Order numbers removed. Undo restores them.');};
  $('closeOrderDisplay').onclick=()=>dialog.close();dialog.onclose=()=>{token++;busy=false;};
  function draw(canvas,node){let host=$('orderNumbersOverlay');if(!host){host=node('g',{id:'orderNumbersOverlay','pointer-events':'none','aria-label':'Path sewing order'});canvas.append(host);}host.replaceChildren();if(row()?.visible&&!stale())labels(host,node,row());}
  function mount(host){host.insertAdjacentHTML('beforeend','<button id="openOrderDisplay" class="wide">Order numbers on canvas</button>');$('openOrderDisplay').onclick=open;}
  return {open,mount,draw};
}
