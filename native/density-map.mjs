import {signature} from './stitchplan-model.mjs';
const defaults={red:6,radiusRed:.5,yellow:3,radiusYellow:.5,size:.5};
const colors=['green','yellow','red'];
export function validateDensityMap(r){
  if(r==null)return;
  if(typeof r!=='object'||!r.options||Object.keys(r.options).some(k=>!(k in defaults))||Object.keys(defaults).some(k=>!Number.isFinite(r.options[k])||r.options[k]<0||r.options[k]>(['red','yellow'].includes(k)?99:50))||!Number.isInteger(r.options.red)||!Number.isInteger(r.options.yellow)||typeof r.visible!=='boolean'||!['unchanged','hidden','lower_opacity'].includes(r.designView)||typeof r.signature!=='string'||r.signature.length>100||!Array.isArray(r.points)||r.points.length>150000||r.points.some(p=>!Array.isArray(p)||p.length!==3||!Number.isInteger(p[2])||p[2]<0||p[2]>2||p.slice(0,2).some(n=>!Number.isFinite(n)||Math.abs(n)>100000))||(r.ids!==null&&(!Array.isArray(r.ids)||!r.ids.length||r.ids.some(id=>typeof id!=='string'))))throw new Error('This project contains an invalid density map.');
}
export async function restoreDensityMap(backup,p,api){
  const row=backup.densityMap;if(!row||row.signature!==signature(backup))return '';
  try{const r=await api('/api/density-map',{project:p,ids:row.ids,options:row.options});p.densityMap={...row,...r,signature:signature(p)};return '';}
  catch(e){p.densityMap={...row,signature:''};return 'Density map needs regeneration: '+e.message;}
}
export function createDensityMap(ctx){
  const $=id=>document.getElementById(id);let generation=0,busy=false,cacheRow,cacheSize,cacheURL,cacheBounds;
  document.head.insertAdjacentHTML('beforeend','<link rel="stylesheet" href="/density-map.css">');
  document.body.insertAdjacentHTML('beforeend',`<dialog id="densityMapDialog" class="density-map-dialog" aria-labelledby="densityMapTitle">
    <div class="dialog-heading"><div><span class="eyebrow">SEE WHERE STITCHES GATHER</span><h2 id="densityMapTitle">Density map on the canvas.</h2></div><button id="closeDensityMap" class="icon-button" aria-label="Close density map">×</button></div>
    <p>Inspect stitch positions using Ink/Stitch’s desktop density calculations. Choose a separate neighborhood for each warning color.</p>
    <div class="density-map-columns"><section>
      <label>Inspect<select id="densityMapScope"><option value="all">Whole visible design</option><option value="selection">Selected artwork</option></select></label>
      <fieldset><legend>Red markers</legend><div class="field-row"><label>Nearby positions<input id="mapRed" type="number" inputmode="numeric" min="0" max="99" step="1" value="6"></label><label>Within radius (mm)<input id="mapRadiusRed" type="number" inputmode="decimal" min="0" max="50" step="any" value="0.5"></label></div></fieldset>
      <fieldset><legend>Yellow markers</legend><div class="field-row"><label>Nearby positions<input id="mapYellow" type="number" inputmode="numeric" min="0" max="99" step="1" value="3"></label><label>Within radius (mm)<input id="mapRadiusYellow" type="number" inputmode="decimal" min="0" max="50" step="any" value="0.5"></label></div></fieldset>
      <div class="field-row"><label>Indicator size<input id="mapSize" type="number" inputmode="decimal" min="0" max="50" step="any" value="0.5"></label><label>Artwork behind markers<select id="mapDesignView"><option value="unchanged">Unchanged</option><option value="hidden">Hidden</option><option value="lower_opacity">Lower opacity</option></select></label></div>
      <button id="generateDensityMap" class="primary wide">Generate density map</button>
      <label class="check"><input id="densityMapVisible" type="checkbox" checked>Show saved map on canvas</label><div class="button-row"><button id="applyDensityMap">Apply display</button><button id="removeDensityMap">Remove map</button></div>
      <button id="downloadDensityMap" class="wide">Prepare annotated SVG</button><a id="densityMapDownload" class="button wide" hidden download>Save density SVG</a>
      <p id="densityMapStatus" role="status"></p><p id="densityMapError" class="error" role="alert"></p>
    </section><section><svg id="densityMapPreview" viewBox="-5 -5 110 110" aria-label="Preview of density markers"></svg><p id="densityMapStats" class="caption"></p><p class="caption">Close this panel to zoom and pan the map on your canvas. Display controls affect the view; your sewing layers and PES stay unchanged.</p></section></div>
    <details class="control-section"><summary>How to read the density map</summary><p class="caption">Red takes priority over yellow; green is below both thresholds. Counts include the position itself, overlapping thread colors and command positions in Ink/Stitch’s pre-export stitch plan. They can differ from the PES density check.</p><p class="caption">Thresholds are independent. A zero threshold marks every position in that color (red takes priority). A zero radius counts coincident positions. Indicator size uses the desktop tool’s scale; zero makes markers invisible. These are inspection thresholds, not a fabric pass/fail.</p><p class="caption">The map is saved with your project and backup. Editing the design hides an outdated map until you regenerate it. The downloaded SVG preserves artwork and adds a non-sewing density layer; view-only fading/hiding is not applied to that file.</p><a class="button" href="https://inkstitch.org/docs/visualize/#density-map" target="_blank" rel="noopener">Ink/Stitch density map help</a></details>
  </dialog>`);
  const dialog=$('densityMapDialog'),row=()=>ctx.getProject().densityMap,stale=()=>row()&&row().signature!==signature(ctx.getProject());
  const fields={red:'mapRed',radiusRed:'mapRadiusRed',yellow:'mapYellow',radiusYellow:'mapRadiusYellow',size:'mapSize'};
  function readOptions(){const r={};for(const[k,id]of Object.entries(fields)){if(!$(id).value||!$(id).validity.valid)throw new Error('Use whole thresholds from 0–99 and radii/size from 0–50.');r[k]=Number($(id).value);}return r;}
  function image(row,size=row.options.size){
    if(cacheRow!==row||cacheSize!==size){
      if(cacheURL)URL.revokeObjectURL(cacheURL);cacheRow=row;cacheSize=size;
      // Desktop markers have radius = indicator_size * 2 px. Native canvas
      // coordinates are mm; retain every engine position, without sampling.
      const radius=size*2*25.4/96,margin=Math.max(radius,.1);let x0=0,y0=0,x1=100,y1=100;
      for(const[x,y]of row.points){x0=Math.min(x0,x-margin);y0=Math.min(y0,y-margin);x1=Math.max(x1,x+margin);y1=Math.max(y1,y+margin);}cacheBounds=[x0,y0,x1-x0,y1-y0];
      const circles=row.points.map(([x,y,k])=>`<circle cx="${x}" cy="${y}" r="${radius}" fill="${colors[k]}"/>`).join('');
      cacheURL=URL.createObjectURL(new Blob([`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${cacheBounds.join(' ')}"><g stroke="#7e7e7e" stroke-width="0.02">${circles}</g></svg>`],{type:'image/svg+xml'}));
    }
    return{url:cacheURL,bounds:cacheBounds};
  }
  function appendMap(host,node,r,size){const a=image(r,size),[x,y,width,height]=a.bounds;host.append(node('image',{x,y,width,height,href:a.url,'pointer-events':'none'}));}
  function preview(){
    const svg=$('densityMapPreview');svg.replaceChildren();const node=(tag,attrs)=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);return e;};
    svg.append(node('rect',{x:0,y:0,width:100,height:100,fill:ctx.getProject().fabric,stroke:'#acb8ab','stroke-width':.3}));
    const art=ctx.artwork().cloneNode(true),view=$('densityMapVisible').checked&&!stale()?$('mapDesignView').value:'unchanged';art.removeAttribute('id');art.style.opacity=view==='lower_opacity'?'.4':'1';art.style.visibility=view==='hidden'?'hidden':'visible';
    const ids=new Map([...art.querySelectorAll('[id]')].map(e=>[e.id,'density-preview-'+e.id]));
    for(const e of [art,...art.querySelectorAll('*')])for(const a of [...e.attributes]){let v=a.value;if(a.name==='id')v=ids.get(v)||v;else{v=v.replace(/url\(#([^)]*)\)/g,(all,id)=>ids.has(id)?`url(#${ids.get(id)})`:all);if(['href','xlink:href'].includes(a.name)&&v.startsWith('#')&&ids.has(v.slice(1)))v='#'+ids.get(v.slice(1));}if(v!==a.value)e.setAttribute(a.name,v);}svg.append(art);
    if(row()&&!stale()&&$('densityMapVisible').checked){const size=Number($('mapSize').value);appendMap(svg,node,row(),$('mapSize').value&&$('mapSize').validity.valid?size:row().options.size);}
  }
  function refresh(){
    const r=row(),old=stale();$('densityMapStatus').textContent=busy?'Reading stitch positions with Ink/Stitch…':!r?'No saved density map yet.':old?'The design changed. The old map is hidden; generate it again.':`${r.points.length.toLocaleString()} positions · ${r.ids?'Selected artwork':'Whole visible design'} · ${r.visible?'Shown':'Hidden'} on canvas.`;
    const counts=[0,0,0];for(const p of r?.points||[])counts[p[2]]++;$('densityMapStats').textContent=r?`${counts[2].toLocaleString()} red · ${counts[1].toLocaleString()} yellow · ${counts[0].toLocaleString()} green. Saved thresholds: red ${r.options.red} within ${r.options.radiusRed} mm; yellow ${r.options.yellow} within ${r.options.radiusYellow} mm.`:'';
    for(const id of ['generateDensityMap','downloadDensityMap','densityMapScope',...Object.values(fields),'mapDesignView'])$(id).disabled=busy;
    for(const id of ['applyDensityMap','removeDensityMap','densityMapVisible'])$(id).disabled=busy||!r;
    $('generateDensityMap').textContent=busy?'Calculating density…':'Generate density map';preview();
  }
  function open(){generation++;busy=false;$('densityMapError').textContent='';$('densityMapDownload').hidden=true;for(const[k,id]of Object.entries(fields))$(id).value=row()?.options[k]??defaults[k];$('mapDesignView').value=row()?.designView||'unchanged';$('densityMapVisible').checked=row()?.visible??true;const selected=ctx.chosen().some(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork'));$('densityMapScope').querySelector('[value="selection"]').disabled=!selected;$('densityMapScope').value=selected?'selection':'all';refresh();dialog.showModal();dialog.scrollTop=0;}
  async function generate(download=false){
    if(busy)return;const token=++generation,project=structuredClone(ctx.getProject()),revision=ctx.getRevision();
    try{const options=readOptions(),ids=$('densityMapScope').value==='selection'?ctx.chosen().filter(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork')).map(l=>l.id):null;busy=true;$('densityMapError').textContent='';$('densityMapDownload').hidden=true;refresh();const result=await ctx.api(download?'/api/density-map-svg':'/api/density-map',{project,ids,options});if(token!==generation||!dialog.open)return;if(project.id!==ctx.getProject().id||revision!==ctx.getRevision())throw new Error('The design changed. Generate the density map again.');
      if(download){$('densityMapDownload').href=result.url;$('densityMapDownload').hidden=false;ctx.toast('Density SVG ready. Tap Save density SVG.');}
      else{ctx.mutate(()=>ctx.getProject().densityMap={...result,visible:true,designView:$('mapDesignView').value,signature:signature(project)});$('densityMapVisible').checked=true;ctx.toast('Density map added. Close this panel to inspect the canvas.');}
    }catch(e){if(token===generation)$('densityMapError').textContent=e.message;}finally{if(token===generation){busy=false;refresh();}}
  }
  $('generateDensityMap').onclick=()=>generate();$('downloadDensityMap').onclick=()=>generate(true);
  $('applyDensityMap').onclick=()=>{try{const {size}=readOptions();if(row())ctx.mutate(()=>{row().options.size=size;row().visible=$('densityMapVisible').checked;row().designView=$('mapDesignView').value;});refresh();ctx.toast('Map display updated. Changed thresholds take effect when you generate again.');}catch(e){$('densityMapError').textContent=e.message;}};
  $('removeDensityMap').onclick=()=>{ctx.mutate(()=>delete ctx.getProject().densityMap);refresh();ctx.toast('Density map removed. Undo restores it.');};
  for(const id of [...Object.values(fields),'mapDesignView','densityMapVisible','densityMapScope'])$(id).oninput=()=>{$('densityMapDownload').hidden=true;preview();};
  $('closeDensityMap').onclick=()=>dialog.close();dialog.onclose=()=>{generation++;busy=false;};
  function draw(canvas,node){
    let host=$('densityMapOverlay');if(!host){host=node('g',{id:'densityMapOverlay','pointer-events':'none','aria-label':'Stitch density markers'});canvas.append(host);}host.replaceChildren();
    const r=row();if(r?.visible&&!stale()){appendMap(host,node,r);if(r.designView==='hidden'){ctx.artwork().style.visibility='hidden';$('selectionOverlay').style.visibility='hidden';}else if(r.designView==='lower_opacity')ctx.artwork().style.opacity='.4';}
    else if(!r&&cacheURL){URL.revokeObjectURL(cacheURL);cacheURL=null;cacheRow=null;}
  }
  function mount(host){host.insertAdjacentHTML('beforeend','<button id="openDensityMap" class="wide">Density map on canvas</button>');$('openDensityMap').onclick=open;}
  return{open,mount,draw};
}
