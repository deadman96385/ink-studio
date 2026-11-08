import {MAX_LAYERS} from './limits.mjs';
import {modes,signature,display,planBounds,comparisonView,addSnapshot,applyEditable,editableTargets} from './stitchplan-model.mjs';

export function createStitchPlans(ctx){
  const $=id=>document.getElementById(id),assets=new Map(),pending=new Set(),failures=new Set(),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let active=null,busy=false,generation=0;
  document.head.insertAdjacentHTML('beforeend','<link rel="stylesheet" href="/stitchplan.css">');
  document.body.insertAdjacentHTML('beforeend',`<dialog id="stitchPlanDialog" class="stitch-plan-dialog" aria-labelledby="stitchPlanTitle">
    <div class="dialog-heading"><div><span class="eyebrow">CANVAS COMPARISON</span><h2 id="stitchPlanTitle">Stitch-plan overlays.</h2></div><button id="closeStitchPlan" class="icon-button" aria-label="Close stitch-plan overlays">×</button></div>
    <p>Compare Ink/Stitch’s rendered stitches with your artwork in its original position. Snapshots are for viewing; they add no stitches to PES exports.</p>
    <div class="stitch-plan-columns"><section><h3>Create a snapshot</h3>
      <label>Preview scope<select id="planScope"><option value="all">Whole design</option><option value="selection">Selected artwork</option></select></label>
      <label>Rendering<select id="planMode">${Object.entries(modes).map(([v,n])=>`<option value="${v}">${n}</option>`).join('')}</select></label>
      <label class="check"><input id="planNeedles" type="checkbox">Needle points (stitch lines)</label>
      <label class="check"><input id="planCommands" type="checkbox">Show command symbols</label>
      <label class="check"><input id="planJumps" type="checkbox" checked>Show jump stitches</label>
      <label class="check"><input id="planSide" type="checkbox" checked>Place beside the 100 mm hoop</label>
      <label class="check"><input id="planLock" type="checkbox" checked>Lock preview position</label>
      <label class="check"><input id="planReplace" type="checkbox" checked>Replace the most recent snapshot</label>
      <button id="generateStitchPlan" class="primary wide">Generate stitch-plan overlay</button>
      <p class="caption">Realistic modes use Ink/Stitch’s lighting. Needle dots are available in stitch-line mode. The simulator shows the final PES command timeline.</p>
    </section><section><h3>Canvas display</h3>
      <label>Artwork behind previews<select id="planArtwork"><option value="unchanged">Show normally</option><option value="lower_opacity">Dim to 40%</option><option value="hidden">Hide artwork</option></select></label>
      <div class="button-row"><button id="fitStitchPlans">Fit comparison</button><button id="removeStitchPlans">Remove all previews</button></div>
      <p class="caption">These display choices leave sewing visibility unchanged. Removing or hiding every snapshot restores the artwork. Undo restores removed previews.</p>
      <div id="stitchPlanList"></div>
    </section></div><p id="stitchPlanError" class="error" role="status"></p>
  </dialog>`);
  const dialog=$('stitchPlanDialog');
  $('canvasStitchPlans').onclick=open;
  $('closeStitchPlan').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{generation++;busy=false;});
  $('planMode').onchange=()=>{$('planNeedles').disabled=$('planMode').value!=='simple';if($('planNeedles').disabled)$('planNeedles').checked=false;};
  function rows(){return ctx.getProject().stitchPlans||[];}
  function open(){
    failures.clear();const selected=ctx.chosen().filter(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork')),last=rows().at(-1),options=last?.options||assets.get(last?.key)?.options||{};
    $('planScope').querySelector('[value=selection]').disabled=!selected.length;$('planScope').value=selected.length?'selection':'all';
    $('planMode').value=modes[options.mode]?options.mode:'simple';$('planNeedles').checked=!!options.needlePoints;$('planCommands').checked=!!options.commands;$('planJumps').checked=options.jumps!==false;
    $('planSide').checked=last?last.x===100&&last.y===0:true;$('planLock').checked=last?!!last.locked:true;$('planReplace').checked=true;$('planMode').onchange();
    $('stitchPlanError').textContent='';refresh();dialog.showModal();hydrate();
  }
  function mount(host){host.insertAdjacentHTML('beforeend','<hr class="separator"><h3>Stitch-plan comparison</h3><button id="openStitchPlans" class="wide">Stitch-plan overlays</button><p class="caption">Compare stitches on the canvas, keep snapshots, or make an editable stitch copy.</p>');$('openStitchPlans').onclick=open;}
  function refresh(){
    const project=ctx.getProject();$('planArtwork').value=project.stitchPlanView||'unchanged';$('generateStitchPlan').disabled=busy;$('generateStitchPlan').textContent=busy?'Rendering with Ink/Stitch…':'Generate stitch-plan overlay';
    $('removeStitchPlans').disabled=busy||!rows().length;$('fitStitchPlans').disabled=!rows().length;
    $('stitchPlanList').innerHTML=rows().map((p,i)=>{const stale=p.signature!==signature(project),asset=assets.get(p.key);return `<article class="stitch-plan-card" data-plan-card="${esc(p.id)}"><h4>${i+1}. ${esc(p.name)}</h4><p class="caption ${stale?'plan-stale':''}">${stale?'Artwork has changed · regenerate to compare current stitches':'Snapshot of the current artwork'}${asset?'':' · loading…'}</p><div class="button-row"><button data-action="visible" aria-pressed="${p.visible!==false}">${p.visible===false?'Show preview':'Hide preview'}</button><button data-action="locked" aria-pressed="${!!p.locked}">${p.locked?'Unlock position':'Lock position'}</button></div><div class="button-row"><button data-action="original" ${p.locked?'disabled':''}>Original position</button><button data-action="side" ${p.locked?'disabled':''}>Beside hoop</button></div><div class="field-row"><label>Preview X offset (mm)<input data-offset="x" type="number" inputmode="decimal" min="-1000" max="1000" step="any" value="${p.x||0}" ${p.locked?'disabled':''}></label><label>Preview Y offset (mm)<input data-offset="y" type="number" inputmode="decimal" min="-1000" max="1000" step="any" value="${p.y||0}" ${p.locked?'disabled':''}></label></div><div class="button-row"><button data-action="editable" ${busy||stale?'disabled':''}>Make stitches editable</button><button data-action="remove" ${busy?'disabled':''}>Remove preview</button></div><p class="caption">Editable stitches use the original document position and keep hidden source artwork. Preview offsets are only for comparison.</p></article>`;}).join('')||'<p class="caption">No snapshots yet. Generate one to compare the stitch plan.</p>';
    $('stitchPlanList').querySelectorAll('[data-plan-card]').forEach(card=>{const p=rows().find(p=>p.id===card.dataset.planCard);card.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>action(p,b.dataset.action));card.querySelectorAll('[data-offset]').forEach(input=>input.oninput=()=>{const value=Number(input.value);if(input.value===''||!Number.isFinite(value)||Math.abs(value)>1000)return;ctx.mutate(()=>p[input.dataset.offset]=value);});});
  }
  function setView(){ctx.setView(comparisonView(rows(),assets));}
  $('fitStitchPlans').onclick=()=>{setView();dialog.close();};
  $('planArtwork').onchange=e=>ctx.mutate(()=>ctx.getProject().stitchPlanView=e.target.value);
  $('removeStitchPlans').onclick=()=>{ctx.mutate(()=>{ctx.getProject().stitchPlans=[];delete ctx.getProject().stitchPlanView;});active=null;refresh();};
  async function action(p,action){
    if(action==='editable')return edit(p);
    ctx.mutate(()=>{if(action==='visible')p.visible=p.visible===false;else if(action==='locked')p.locked=!p.locked;else if(action==='original'){p.x=0;p.y=0;}else if(action==='side'){p.x=100;p.y=0;}else if(action==='remove'){ctx.getProject().stitchPlans=rows().filter(r=>r.id!==p.id);if(active===p.id)active=null;}});refresh();
  }
  $('generateStitchPlan').onclick=async()=>{
    if(busy)return;const project=structuredClone(ctx.getProject()),revision=ctx.getRevision(),token=++generation;
    const ids=$('planScope').value==='selection'?ctx.chosen().filter(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork')).map(l=>l.id):null;
    const opts={replace:$('planReplace').checked,side:$('planSide').checked,locked:$('planLock').checked,ids};
    if(!opts.replace&&rows().length>=6){$('stitchPlanError').textContent='Remove a snapshot before adding another; a project can keep six.';return;}
    busy=true;refresh();$('stitchPlanError').textContent='';
    try{const asset=await ctx.api('/api/stitch-plan',{project,ids,options:{mode:$('planMode').value,needlePoints:$('planNeedles').checked,commands:$('planCommands').checked,jumps:$('planJumps').checked}});
      if(token!==generation||!dialog.open)return;if(project.id!==ctx.getProject().id||revision!==ctx.getRevision())throw new Error('The design changed. Generate the snapshot again.');
      assets.set(asset.key,asset);ctx.mutate(()=>{active=addSnapshot(ctx.getProject(),asset,opts).id;});setView();ctx.toast('Stitch-plan snapshot added. Close this panel to compare on the canvas.');
    }catch(e){if(token===generation)$('stitchPlanError').textContent=e.message;}finally{if(token===generation){busy=false;refresh();}}
  };
  async function edit(row){
    if(busy)return;const project=ctx.getProject(),revision=ctx.getRevision(),token=++generation;
    if(project.layers.length>=MAX_LAYERS)return ctx.toast('Remove a layer before creating editable stitches.');
    if(row.signature!==signature(project))return ctx.toast('Regenerate this snapshot before making stitches editable.');
    const targets=editableTargets(project,row),affected=project.layers.filter(l=>l.visible!==false&&(targets.has(l.id)||targets.has(l.helperTarget)));
    if(affected.some(l=>l.locked))return ctx.toast('Unlock the source artwork and its guides before making stitches editable.');
    busy=true;refresh();$('stitchPlanError').textContent='Generating editable needle paths…';
    try{const result=await ctx.api('/api/stitch-plan-edit',{key:row.key});if(token!==generation||!dialog.open)return;if(project.id!==ctx.getProject().id||revision!==ctx.getRevision())throw new Error('The design changed. Make the stitch copy again.');ctx.assets.set(result.asset.key,result.asset);ctx.mutate(()=>{applyEditable(project,row,result.layer);ctx.select([result.layer.id]);});ctx.setView({x:-12,y:-12,w:124,h:124});dialog.close();ctx.setTab('digitize');ctx.toast('Editable stitch copy added. Separate its paths to edit individual needle points. Undo restores the source.');}
    catch(e){if(token===generation)$('stitchPlanError').textContent=e.message;}finally{if(token===generation){busy=false;refresh();}}
  }
  async function hydrate(){
    for(const p of rows()){if(assets.has(p.key)||pending.has(p.key)||failures.has(p.key))continue;pending.add(p.key);try{assets.set(p.key,await ctx.api('/api/stitch-plans/'+p.key));ctx.render();if(dialog.open)refresh();}catch(e){failures.add(p.key);ctx.toast('Could not load stitch-plan snapshot: '+e.message);}finally{pending.delete(p.key);}}
  }
  function draw(canvas,node){
    $('canvasStitchPlans').textContent=rows().length?'Stitches · '+rows().length:'Stitches';
    const art=$('artwork'),visibility=rows().some(p=>p.visible!==false&&assets.has(p.key))?display(ctx.getProject()):'unchanged';art.style.opacity=visibility==='lower_opacity'?'.4':'1';art.style.visibility=visibility==='hidden'?'hidden':'visible';
    let host=$('stitchPlanOverlay');if(!host){host=node('g',{id:'stitchPlanOverlay'});art.after(host);}host.replaceChildren();
    for(const p of rows().filter(p=>p.visible!==false)){
      const a=assets.get(p.key);if(!a)continue;const b=planBounds(p,a),g=node('g',{'data-stitch-plan':p.id,'pointer-events':p.locked?'none':'all'});
      g.append(node('image',{x:b.x,y:b.y,width:b.w,height:b.h,href:'/stitch-plans/'+p.key,'pointer-events':'none'}));
      const label=node('text',{x:b.x,y:b.y-2,'font-size':2.5,fill:'#52655d','pointer-events':'none'});label.textContent=`${rows().indexOf(p)+1} · ${modes[a.options.mode]||'Stitch preview'}`;g.append(label);
      if(!p.locked)g.append(node('rect',{x:b.x,y:b.y,width:b.w,height:b.h,fill:'transparent',stroke:active===p.id?'#21766a':'none','stroke-width':.3,'stroke-dasharray':'1 .8'}));host.append(g);
    }
    if(visibility==='hidden')$('selectionOverlay').style.visibility='hidden';else $('selectionOverlay').style.visibility='visible';
    hydrate();
  }
  function hit(id){const row=rows().find(p=>p.id===id);if(row&&!row.locked){active=id;return row;}return null;}
  return {open,mount,draw,hydrate,hit};
}
