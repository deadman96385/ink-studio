import {MAX_LAYERS} from './limits.mjs';
import {pathD} from './paths.mjs';
import {toLocal,toWorld} from './commands.mjs';
import {PenGate} from './pen.mjs';
import {drawPlan} from './advanced.mjs';

const svgNode=(tag,attrs={})=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);return e;};
const LABELS={fill:'Fill',running:'Running outline',bean:'Bean outline'};
export const MAX_REGIONS=12;

export function pickedLayers(regions){return regions.flatMap(r=>r.layers);}

export function applyPickedRegions(project,sourceId,regions,hideReference){
  const ref=project.layers.find(l=>l.id===sourceId&&l.type==='image');
  if(!ref)throw new Error('The source image is missing. Reopen click-to-stitch.');
  if(!regions.length||regions.length>MAX_REGIONS)throw new Error('Pick 1–12 regions first.');
  const layers=structuredClone(pickedLayers(regions));
  if(!layers.length||layers.length>30)throw new Error('Pick fewer regions before applying.');
  if(project.layers.length+layers.length>MAX_LAYERS)throw new Error(`This would exceed ${MAX_LAYERS} layers. Remove unused layers first.`);
  if(hideReference)ref.visible=false;
  ref.clickStitchSettings=structuredClone(regions.at(-1).params);
  project.layers.splice(project.layers.indexOf(ref)+1,0,...layers);
  return layers.map(l=>l.id);
}

export function createClickStitch(ctx){
  const $=id=>document.getElementById(id),gate=new PenGate(),pointers=new Map();
  let source,pid,revision,regions=[],preview=null,busy=false,token=0,view,fit,gesture=null;
  document.body.insertAdjacentHTML('beforeend',`<dialog id="clickStitchDialog" class="click-stitch-dialog" aria-labelledby="clickStitchTitle">
    <div class="dialog-heading"><div><span class="eyebrow">GUIDED DIGITIZING</span><h2 id="clickStitchTitle">Click to stitch.</h2></div><button id="closeClickStitch" class="icon-button" aria-label="Close click-to-stitch">×</button></div>
    <p id="clickStitchSource" class="caption"></p>
    <div class="click-stitch-workspace">
      <section class="click-stitch-stage" aria-label="Region selection and preview">
        <div class="button-row"><button id="clickStitchArtwork" aria-pressed="true">Pick regions</button><button id="clickStitchView" aria-pressed="false" disabled>Stitches</button><button id="clickStitchFit">Fit image</button><button id="clickStitchZoomIn" aria-label="Zoom into image">＋</button><button id="clickStitchZoomOut" aria-label="Zoom out of image">−</button></div>
        <svg id="clickStitchCanvas" role="img" aria-label="Tap a visible color region to digitize it"></svg>
        <canvas id="clickStitchPreview" aria-label="Actual generated region stitches" hidden></canvas>
        <p class="caption">Tap inside a color region with a finger, Pencil or mouse. Drag to pan; pinch or use + / − to zoom. Flat-color artwork works best.</p>
        <p id="clickStitchStats" class="caption" role="status" aria-live="polite"></p>
      </section>
      <section class="click-stitch-controls">
        <fieldset id="clickStitchFields"><legend>For the next region</legend>
          <label>Stitch as<select id="clickStitchType"><option value="fill">Filled region</option><option value="running">Running outline</option><option value="bean">Bean outline</option></select></label>
          <label>Color tolerance (%)<input id="clickStitchTolerance" type="number" min="0" max="100" step="1" value="12" required></label>
          <p class="caption">Higher tolerance includes more neighboring colors. Disconnected areas stay separate. Settings here affect new picks.</p>
          <label class="check"><input id="clickStitchSourceColor" type="checkbox" checked>Use the picked image color</label>
          <label id="clickStitchColorLabel" hidden>Thread color<input id="clickStitchColor" type="color" value="#203f38"></label>
          <div id="clickStitchFillFields"><div class="field-row"><label>Row spacing (mm)<input id="clickStitchSpacing" type="number" min="0.2" max="3" step="any" value="0.4" required></label><label>Fill angle (°)<input id="clickStitchAngle" type="number" min="-360" max="360" step="any" value="45" required></label></div><label class="check"><input id="clickStitchUnderlay" type="checkbox" checked>Fill underlay</label></div>
          <label>Stitch length (mm)<input id="clickStitchLength" type="number" min="0.5" max="6" step="any" value="2.5" required></label>
          <p id="clickStitchOutlineHint" class="caption" hidden>Outlines follow the outside and any holes. To make a line through the middle, use Trace image → Running centerlines.</p>
        </fieldset>
        <div class="section-title"><h3>Picked regions <span id="clickStitchCount">0 / 12</span></h3><button id="clearClickStitch" class="quiet" disabled>Clear</button></div>
        <ol id="clickStitchRegions" class="click-stitch-regions" aria-label="Picked regions in sewing order"></ol>
        <p id="clickStitchEmpty" class="caption">Choose settings, then tap a region. Pick several to digitize them together; add a fill and an outline to the same region if needed.</p>
      </section>
    </div>
    <label class="check"><input id="clickStitchHide" type="checkbox">Hide the reference after applying</label>
    <p id="clickStitchError" class="error" role="alert"></p>
    <div class="dialog-footer"><button id="cancelClickStitch">Cancel</button><button id="previewClickStitch" class="primary" disabled>Preview stitches</button><button id="applyClickStitch" class="primary" disabled>Apply regions</button></div>
  </dialog>`);

  const fresh=()=>ctx.getProject().id===pid&&ctx.getRevision()===revision;
  function assertFresh(){if(!fresh())throw new Error('The design changed. Reopen click-to-stitch before continuing.');}
  function stats(message){$('clickStitchStats').textContent=message;}
  function controls(){
    $('clickStitchFields').disabled=busy;
    $('previewClickStitch').disabled=busy||!regions.length;
    $('applyClickStitch').disabled=busy||!preview;
    $('clickStitchView').disabled=busy||!preview;
    $('clearClickStitch').disabled=busy||!regions.length;
    $('previewClickStitch').textContent=busy?'Preparing…':'Preview stitches';
    for(const b of $('clickStitchRegions').querySelectorAll('button'))b.disabled=busy;
    $('clickStitchCanvas').setAttribute('aria-busy',String(busy));
  }
  function visibility(){
    const fill=$('clickStitchType').value==='fill';
    $('clickStitchFillFields').hidden=!fill;$('clickStitchOutlineHint').hidden=fill;
    $('clickStitchColorLabel').hidden=$('clickStitchSourceColor').checked;
  }
  function read(){
    for(const input of $('clickStitchFields').querySelectorAll('input[type=number]'))if(!input.value||!input.validity.valid)throw new Error('Check the region stitch settings.');
    return {stitch:$('clickStitchType').value,tolerance:Number($('clickStitchTolerance').value),
      spacing:Number($('clickStitchSpacing').value),angle:Number($('clickStitchAngle').value),
      stitchLength:Number($('clickStitchLength').value),underlay:$('clickStitchUnderlay').checked,
      useSourceColor:$('clickStitchSourceColor').checked,color:$('clickStitchColor').value};
  }
  function showArtwork(){
    $('clickStitchCanvas').removeAttribute('hidden');$('clickStitchPreview').hidden=true;
    $('clickStitchArtwork').setAttribute('aria-pressed','true');$('clickStitchView').setAttribute('aria-pressed','false');draw();
  }
  function invalidate(){
    preview=null;$('clickStitchError').textContent='';controls();showArtwork();
    stats(regions.length?`${regions.length} regions selected. Preview stitches before applying.`:'Tap a region to begin.');
  }
  function draw(){
    if(!source||!view)return;
    const svg=$('clickStitchCanvas');svg.setAttribute('viewBox',`${view.x} ${view.y} ${view.w} ${view.h}`);
    svg.replaceChildren(ctx.referenceArtwork({...source,opacity:1}));
    for(const[rIndex,r]of regions.entries()){
      for(const l of r.layers){
        const fill=l.stitch==='fill';
        svg.append(svgNode('path',{d:pathD(l.contours,l.width,l.height),transform:`translate(${l.x} ${l.y})`,fill:fill?'#e8a847':'none',
          'fill-opacity':.45,stroke:fill?'#214e42':l.color,'stroke-width':fill?1.5:2.5,'vector-effect':'non-scaling-stroke','fill-rule':'evenodd','pointer-events':'none'}));
      }
      const [x,y]=toWorld(source,r.seed),g=svgNode('g',{'pointer-events':'none'}),size=view.w/55;
      g.append(svgNode('circle',{cx:x,cy:y,r:size,fill:'#173f38',stroke:'#fff','stroke-width':1.5,'vector-effect':'non-scaling-stroke'}));
      const label=svgNode('text',{x,y:y+size*.35,'text-anchor':'middle',fill:'#fff','font-size':size*1.2,'font-weight':700});label.textContent=String(rIndex+1);g.append(label);svg.append(g);
    }
  }
  function list(){
    $('clickStitchCount').textContent=`${regions.length} / ${MAX_REGIONS}`;$('clickStitchEmpty').hidden=!!regions.length;
    $('clickStitchRegions').replaceChildren(...regions.map((r,i)=>{
      const li=document.createElement('li'),swatch=document.createElement('span'),text=document.createElement('span'),remove=document.createElement('button');
      swatch.className='click-stitch-swatch';swatch.style.backgroundColor=r.layers[0].color;
      text.textContent=`${i+1}. ${LABELS[r.params.stitch]} · ${r.layers.length} path${r.layers.length===1?'':'s'}`;
      remove.type='button';remove.textContent='×';remove.setAttribute('aria-label',`Remove region ${i+1}`);
      remove.onclick=()=>{regions.splice(i,1);list();invalidate();};li.append(swatch,text,remove);return li;
    }));controls();
  }
  async function pick(world){
    if(busy)return;
    const seed=toLocal(source,world);
    if(seed.some(n=>n<0||n>1))return;
    const run=++token;
    try{
      assertFresh();if(regions.length>=MAX_REGIONS)throw new Error('Apply these regions, then reopen click-to-stitch to add more.');
      const params=read();busy=true;controls();$('clickStitchError').textContent='';stats('Selecting the connected region…');
      const result=await ctx.api('/api/click-stitch',{layer:source,seed,params});
      if(run!==token||!$('clickStitchDialog').open)return;
      assertFresh();
      if(regions.some(r=>r.regionKey===result.regionKey&&r.params.stitch===result.params.stitch))throw new Error('That region already has this stitch type. Remove its pick to change the settings.');
      if(pickedLayers([...regions,result]).length>30)throw new Error('Pick fewer regions for this preview. Apply the current picks first.');
      if(ctx.getProject().layers.length+pickedLayers([...regions,result]).length>MAX_LAYERS)throw new Error(`This would exceed ${MAX_LAYERS} project layers. Apply fewer regions.`);
      const groupId=crypto.randomUUID();result.layers=result.layers.map(l=>({...l,groupId,name:`Region ${regions.length+1} · ${LABELS[params.stitch]}`}));
      regions.push(result);list();invalidate();
    }catch(e){if(run===token){$('clickStitchError').textContent=e.message;stats(`${regions.length} regions selected.`);}}
    finally{if(run===token){busy=false;controls();}}
  }
  $('previewClickStitch').onclick=async()=>{
    const run=++token;
    try{
      assertFresh();busy=true;preview=null;controls();$('clickStitchError').textContent='';stats('Generating the actual stitches…');
      const result=await ctx.api('/api/layer-preview',{layers:pickedLayers(regions)});
      if(run!==token||!$('clickStitchDialog').open)return;
      assertFresh();if(!result.preview.stitches)throw new Error('These regions generated no stitches. Pick a larger region or change the stitch settings.');
      preview=result.preview;stats(`${regions.length} regions · ${preview.stitches.toLocaleString()} stitches · ${preview.width} × ${preview.height} mm`);
      $('clickStitchCanvas').setAttribute('hidden','');$('clickStitchPreview').hidden=false;
      $('clickStitchArtwork').setAttribute('aria-pressed','false');$('clickStitchView').setAttribute('aria-pressed','true');
      requestAnimationFrame(()=>drawPlan($('clickStitchPreview'),preview));
    }catch(e){if(run===token){$('clickStitchError').textContent=e.message;stats('Preview could not be generated. Your design has not changed.');}}
    finally{if(run===token){busy=false;controls();}}
  };
  $('applyClickStitch').onclick=()=>{
    try{
      assertFresh();if(busy||!preview)throw new Error('Preview the current regions before applying.');
      // Validate on a copy first so a failed apply never creates an undo entry.
      const draft=structuredClone(ctx.getProject()),ids=applyPickedRegions(draft,source.id,regions,$('clickStitchHide').checked);
      ctx.mutate(()=>{Object.assign(ctx.getProject(),draft);ctx.select(ids);});
      $('clickStitchDialog').close();ctx.setTab('layer');ctx.toast('Editable regions added. Undo restores the previous design.');
    }catch(e){$('clickStitchError').textContent=e.message;}
  };
  $('clickStitchFields').oninput=visibility;
  $('clickStitchArtwork').onclick=showArtwork;
  $('clickStitchView').onclick=()=>{if(preview){$('clickStitchCanvas').setAttribute('hidden','');$('clickStitchPreview').hidden=false;$('clickStitchArtwork').setAttribute('aria-pressed','false');$('clickStitchView').setAttribute('aria-pressed','true');requestAnimationFrame(()=>drawPlan($('clickStitchPreview'),preview));}};
  $('clearClickStitch').onclick=()=>{regions=[];list();invalidate();};
  $('clickStitchFit').onclick=()=>{view={...fit};showArtwork();};
  function zoom(factor){const w=Math.max(fit.w/25,Math.min(fit.w*4,view.w*factor)),ratio=w/view.w;view={x:view.x+(view.w-w)/2,y:view.y+view.h*(1-ratio)/2,w,h:view.h*ratio};showArtwork();}
  $('clickStitchZoomIn').onclick=()=>zoom(.7);$('clickStitchZoomOut').onclick=()=>zoom(1/.7);
  const canvas=$('clickStitchCanvas'),point=(p,matrix=canvas.getScreenCTM().inverse())=>{const v=new DOMPoint(p.x,p.y).matrixTransform(matrix);return[v.x,v.y];};
  function startGesture(){
    const ps=[...pointers.values()];if(!ps.length){gesture=null;return;}
    gesture={view:{...view},matrix:canvas.getScreenCTM().inverse(),start:ps.map(p=>({...p})),pinch:ps.length>1};
  }
  canvas.onpointerdown=e=>{
    if(e.button!==0||!gate.down(e,performance.now()))return;
    e.preventDefault();if(e.pointerType==='pen')pointers.clear();
    pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY,moved:false});canvas.setPointerCapture(e.pointerId);
    if(pointers.size>1)for(const p of pointers.values())p.moved=true;startGesture();
  };
  canvas.onpointermove=e=>{
    const p=pointers.get(e.pointerId);if(!p||!gesture)return;e.preventDefault();p.x=e.clientX;p.y=e.clientY;
    p.moved||=Math.hypot(p.x-p.startX,p.y-p.startY)>8;
    const current=[...pointers.values()],base=gesture.start;
    if(current.length>1&&base.length>1){
      const dist=ps=>Math.hypot(ps[0].x-ps[1].x,ps[0].y-ps[1].y),mid=ps=>({x:(ps[0].x+ps[1].x)/2,y:(ps[0].y+ps[1].y)/2});
      const ratio=Math.max(fit.w/25/gesture.view.w,Math.min(fit.w*4/gesture.view.w,dist(base)/Math.max(1,dist(current))));
      const a=point(mid(base),gesture.matrix),b=point(mid(current),gesture.matrix),v=gesture.view;
      view={x:a[0]-(b[0]-v.x)*ratio,y:a[1]-(b[1]-v.y)*ratio,w:v.w*ratio,h:v.h*ratio};draw();
    }else if(p.moved){const a=point(base[0],gesture.matrix),b=point(p,gesture.matrix);view={...gesture.view,x:gesture.view.x+a[0]-b[0],y:gesture.view.y+a[1]-b[1]};draw();}
  };
  function endPointer(e,cancel=false){
    const p=pointers.get(e.pointerId);gate.end(e,performance.now());pointers.delete(e.pointerId);
    if(!p)return;
    const tapped=!p.moved&&!cancel&&!pointers.size,world=tapped?point({x:e.clientX,y:e.clientY}):null;
    startGesture();if(tapped)pick(world);
  }
  canvas.onpointerup=e=>endPointer(e);canvas.onpointercancel=e=>endPointer(e,true);
  canvas.onlostpointercapture=e=>endPointer(e,true);
  canvas.onwheel=e=>{e.preventDefault();zoom(e.deltaY>0?1.15:1/1.15);};
  for(const id of ['closeClickStitch','cancelClickStitch'])$(id).onclick=()=>$('clickStitchDialog').close();
  $('clickStitchDialog').onclose=()=>{token++;busy=false;pointers.clear();gesture=null;gate.reset();};
  new ResizeObserver(()=>{if(preview&&!$('clickStitchPreview').hidden)drawPlan($('clickStitchPreview'),preview);}).observe($('clickStitchPreview'));
  function open(layer){
    source=structuredClone(layer);pid=ctx.getProject().id;revision=ctx.getRevision();regions=[];preview=null;busy=false;token++;pointers.clear();gesture=null;gate.reset();
    const p={tolerance:12,stitch:'fill',spacing:.4,angle:45,stitchLength:2.5,underlay:true,useSourceColor:true,color:'#203f38',...layer.clickStitchSettings};
    for(const[id,key]of [['clickStitchType','stitch'],['clickStitchTolerance','tolerance'],['clickStitchSpacing','spacing'],['clickStitchAngle','angle'],['clickStitchLength','stitchLength'],['clickStitchColor','color']])$(id).value=p[key];
    for(const[id,key]of [['clickStitchUnderlay','underlay'],['clickStitchSourceColor','useSourceColor']])$(id).checked=p[key];
    $('clickStitchHide').checked=false;$('clickStitchSource').textContent=layer.name+' · choose only the areas you want to sew';
    const corners=[[0,0],[0,1],[1,0],[1,1]].map(p=>toWorld(source,p)),xs=corners.map(p=>p[0]),ys=corners.map(p=>p[1]),pad=Math.max(layer.width,layer.height)*.04;
    fit={x:Math.min(...xs)-pad,y:Math.min(...ys)-pad,w:Math.max(...xs)-Math.min(...xs)+2*pad,h:Math.max(...ys)-Math.min(...ys)+2*pad};view={...fit};
    visibility();list();invalidate();$('clickStitchDialog').showModal();
  }
  return{open};
}
