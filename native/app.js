import {organizeTools} from './tool-groups.mjs';
import {HOOPS,hoopOf} from './hoops.mjs';
import {createToolFinder} from './tool-finder.mjs';
import {createFinderRoutes} from './finder-routes.mjs';
import {createSelectionShelf} from './selection-shelf.mjs';
import {createShelfSettings,setLayerColor,textKey} from './selection-shelf-settings.mjs';
import {installKeywordChips} from './keyword-chips.mjs';
import {createExportOptions} from './export-options.mjs';
import {createPrintWorkspace} from './print-workspace.mjs';
import {createTroubleshoot,validateTroubleshoot,restoreTroubleshoot} from './troubleshoot.mjs';
import {createDensityMap,validateDensityMap,restoreDensityMap} from './density-map.mjs';
import {MAX_LAYERS} from './limits.mjs';
import {createLinked} from './linked-ui.mjs';
import {createSelection} from './selection.mjs';
import {createPreferences,documentSettings,FACTORY} from './preferences.mjs';
import {createCrossStitch} from './crossstitch.mjs';
import {createSvgPreparation} from './svgprep.mjs';
import {createStitchPlans} from './stitchplan.mjs';
import {crossGrids,drawGrids,snappedMove} from './cross-grid.mjs';
import {createSimulator} from './simulator.mjs';
import {selectionProject} from './simulator-model.mjs';
import {objectBounds, groupBounds, units, move, alignLayers, spaceLayers, rotateLayers, mirrorLayers, fitBackground, resizedDimensions} from './geometry.mjs';
import {pathD,satinArea,worldContours,packContours} from './paths.mjs';
import {createDigitizer} from './digitize.mjs';
import {createAdvanced} from './advanced.mjs';
import {createElementInfo} from './element-info.mjs';
import {createStackingOrder,validateOrderDisplay,restoreOrderDisplay} from './stacking-order.mjs';
import {createOperations} from './operations.mjs';
import {createThreads} from './threads.mjs';
import {createSwatches} from './swatches.mjs';
import {createFontLibrary} from './fontlibrary.mjs';
import {createTTFLettering,drawTTFArtwork} from './ttf-lettering.mjs';
import {createFontSamples} from './fontsamples.mjs';
import {createFontWorkspaces} from './fontworkspaces.mjs';
import {createBatches} from './batches.mjs';
import {createCommands} from './commands.mjs';
import {createHelpers} from './helpers.mjs';
import {createSpecialFills,decorateCanvasFill} from './fills.mjs';
import {createMultisatin,satinBands} from './multisatin.mjs';
import {createReferences,imageArtwork} from './references.mjs';
import {createComponents} from './components.mjs';
import {createMerrow,merrowArtwork} from './merrow.mjs';
import {createStreamlines,streamlineArtwork,isFlowFill,flowName} from './streamlines.mjs';
import {createFeather,featherArtwork} from './feather.mjs';
import {createSewingOptimizer} from './sewing-optimizer.mjs';
import {createScenes} from './scenes.mjs';
import {PenGate,makeStroke,createPenControls} from './pen.mjs';
import {createCanvasMotion,prefersReducedMotion} from './motion.mjs';
import {installInterfaceMotion,reveal} from './motion-ui.mjs';
import {createTaskState,createSaveQueue,createProjectTransition} from './workflow-state.mjs';
const $ = (id) => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const copy = (v) => structuredClone(v);
const uid = () => crypto.randomUUID();
const escape = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const round = (v) => Math.round(v * 100) / 100;
const clamp = (v, min, max) => Math.min(max, Math.max(min, v));
const colors = ['#203f38', '#f4eee0', '#272829', '#b96548', '#d4ac59', '#416580', '#83759d'];
const blankProject = (settings=FACTORY) => ({version:1, id:uid(), name:'Untitled design', fabric:'#faf7f0', grid:true, snap:true, layers:[],embroiderySettings:documentSettings(settings)});
let project = blankProject(), selected = new Set(), fonts = [], assets = new Map(), textCache = new Map();
let history = [], future = [], tab = 'layer', multi = false, mode = 'select', editTextId = null, letterGeneration=0;
// Hoop of the open project (hoops.mjs); the canvas, limits and checks follow it.
const hoop=()=>hoopOf(project),hoopMax=()=>Math.max(hoop().w,hoop().h);
const hoopView=()=>{const h=hoop(),pad=Math.max(h.w,h.h)*.12;return {x:-pad,y:-pad,w:h.w+2*pad,h:h.h+2*pad};};
let shownHoop=null;
const canvasMotion=createCanvasMotion({node});let selectionKey='';
function applyHoop(){const h=hoop();if(shownHoop===h.id)return;shownHoop=h.id;for(const id of ['fabricRect','fabricTexture','gridRect','hoopBorder']){$(id).setAttribute('width',h.w);$(id).setAttribute('height',h.h);}$('hoopShadow').setAttribute('width',h.w+4);$('hoopShadow').setAttribute('height',h.h+4);$('hoopMarks').setAttribute('d',`M ${h.w/2} -3 V 0 M ${h.w/2} ${h.h} V ${h.h+3} M -3 ${h.h/2} H 0 M ${h.w} ${h.h/2} H ${h.w+3}`);$('hoopEyebrow').textContent=h.eyebrow;$('hoopSize').textContent=h.short;view=hoopView();}
let view = {x:-12,y:-12,w:124,h:124}, pointers = new Map(), gesture = null, dirty = false;
let lastExport = null, lastExportFabric = '#faf7f0', toastTimer, saveTimer;
let modelRevision = 0, saveRevision = -1;
let toolFinder=null;
let respiraUrl='';
let selectionShelf=null;
const penGate=new PenGate();
const previewTask=createTaskState(state=>{
  $('previewDialog').dataset.state=state.status;
  $('previewDialog').setAttribute('aria-busy',String(state.status==='pending'));
});
const saveQueue=createSaveQueue({write:snapshot=>api('/api/save',{project:snapshot}),onChange:state=>{
  if(project.id!==state.projectId||modelRevision!==state.revision)return;
  $('saveState').dataset.state=state.status;
  if(state.status==='saved'){dirty=false;saveRevision=state.revision;$('saveState').textContent='Saved in Studio';}
  else $('saveState').textContent=state.status==='error'?'Local copy only · tap Save to retry':'Saving in Studio…';
}});
const projectTransitions=createProjectTransition({getProject:()=>project,getRevision:()=>modelRevision,save:()=>saveProject(false,true),onChange:state=>{
  $('projectsDialog').dataset.state=state.status;
  $('projectsDialog').setAttribute('aria-busy',String(state.status==='pending'));
  for(const button of $('projectsDialog').querySelectorAll('.project-card,#newProjectBtn,#saveCopyBtn'))button.disabled=state.status==='pending';
}});

async function api(path, data) {
  const r = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-InkStudio-Preferences':JSON.stringify(documentSettings(project.embroiderySettings))},body:JSON.stringify(data)});
  let value;
  try { value = await r.json(); } catch { throw new Error('The studio service did not respond. Check that Ink Studio is running.'); }
  if (!r.ok) throw new Error(value.error || 'Request failed.');
  return value;
}
function toast(message) { $('toast').textContent=message; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,5500); }
function checkpoint() { history.push(copy(project)); if(history.length>60)history.shift(); future=[]; }
function changed(render=true,refreshLinks=true) {
  if(refreshLinks)linked.changed();
  dirty=true; modelRevision++; lastExport=null;
  if(previewTask.state.status!=='idle'){
    previewTask.cancel();simulator.stop();
    if($('previewDialog').open){$('previewContent').hidden=true;$('previewStatus').hidden=false;$('previewStatus').textContent='The design changed. Preview it again.';simulator.scope('all',chosen().length,false);}
  }
  $('saveState').dataset.state='dirty';
  try { localStorage.setItem('inkstudio-project-v1',JSON.stringify(project)); $('saveState').textContent='Saved in this browser'; }
  catch { $('saveState').textContent='Browser storage full — tap Save'; }
  if(render)renderAll();else selectionShelf?.render();
  $('undoBtn').disabled=!history.length;$('redoBtn').disabled=!future.length;
  clearTimeout(saveTimer); saveTimer=setTimeout(()=>saveProject(false),1800);
}
function mutate(fn) { checkpoint(); fn(); changed(); }
async function saveProject(show=true,required=false) {
  clearTimeout(saveTimer);
  const projectId=project.id,revision=modelRevision;
  try {await saveQueue.save(project,revision);if(show&&project.id===projectId&&revision===modelRevision)toast('Project saved in Studio.');}
  catch(e){if(required)throw e;if(show&&project.id===projectId)toast(e.message);}
}
function chosen() { return project.layers.filter(l=>selected.has(l.id)); }
function single() { return chosen().length===1 ? chosen()[0] : null; }
function newLayer(type, props={}) { return {id:uid(),type,name:type==='ellipse'?'Ellipse':'Shape',x:30,y:35,width:40,height:30,rotation:0,color:'#203f38',stitch:'fill',spacing:.4,angle:45,stitchLength:2.5,underlay:true,radius:3,visible:true,...props}; }
function addLayer(layer,threadBook=null,settings=null,grids=null) { mutate(()=>{if(threadBook)project.threadBook={...project.threadBook,...threadBook};if(!project.layers.length){if(settings)project.embroiderySettings=documentSettings(settings);if(grids?.length){project.crossGrids=crossGrids(grids);project.grid=false;}}project.layers.push(layer);selected=new Set([layer.id]);}); setTab('layer'); }
function node(tag, attrs={}) { const e=document.createElementNS(NS,tag); for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);return e; }

function textPreview(result, color, preserveColors=false) {
  const p=result.preview, sx=result.width/(p.width||1),sy=result.height/(p.height||1);
  const group=node('g',{transform:`scale(${sx},${sy}) translate(${-p.bounds[0]},${-p.bounds[1]})`});
  const blocks=[];let block=null;
  for(const s of p.segments){const paint=preserveColors?(p.threads[s[4]]?.color||color):color;if(block?.color!==paint){block={color:paint,paths:[]};blocks.push(block);}block.paths.push(`M${s[0]} ${s[1]}L${s[2]} ${s[3]}`);}
  for(const b of blocks)group.append(node('path',{d:b.paths.join(''),fill:'none',stroke:b.color,'stroke-width':.23,'stroke-linecap':'round','stroke-linejoin':'round'}));
  return group;
}
function shape(layer) {
  const {width:w,height:h}=layer;
  const softened=featherArtwork(layer,node);if(softened)return softened;
  const merrow=merrowArtwork(layer,node);if(merrow)return merrow;
  const flow=streamlineArtwork(layer,node);if(flow)return flow;
  const bands=satinBands(layer,node);if(bands)return bands;
  let e;
  const satin=layer.stitch==='satin'||String(layer.originalParams?.satin_column).toLowerCase()==='true';
  if(satin&&layer.contours?.length>=2){const g=node('g');g.append(node('path',{d:satinArea(layer.contours,w,h),fill:layer.color,opacity:.7}));g.append(node('path',{d:pathD(layer.contours.slice(0,2),w,h),fill:'none',stroke:layer.color,'stroke-width':.25}));return g;}
  if(layer.type==='ellipse') e=node('ellipse',{cx:w/2,cy:h/2,rx:w/2,ry:h/2});
  else if(layer.type==='path') e=node('path',{d:layer.contours?pathD(layer.contours,w,h):layer.points.map((p,i)=>`${i?'L':'M'}${p[0]*w} ${p[1]*h}`).join(' ')+((layer.closed||layer.stitch==='fill')?' Z':''),'fill-rule':'evenodd'});
  else e=node('rect',{width:w,height:h,rx:Math.min(layer.radius||0,w/2,h/2)});
  const fill=layer.stitch==='fill';
  e.setAttribute('fill',fill?layer.color:'none'); e.setAttribute('stroke',fill?'none':layer.color);
  e.setAttribute('stroke-width',layer.stitch==='zigzag'?(layer.strokeWidth||1.5):.45);
  if(layer.stitch==='running')e.setAttribute('stroke-dasharray','1 .35');
  if(layer.stitch==='original'){e.setAttribute('fill-rule',layer.originalFillRule||'nonzero');e.setAttribute('fill',layer.originalFill===false?'none':layer.color);e.setAttribute('stroke',layer.originalStroke?layer.color:'none');e.setAttribute('stroke-width',layer.originalWidth||.3);}
  return e;
}
const layerTransform=l=>`translate(${l.x} ${l.y}) rotate(${l.rotation||0} ${l.width/2} ${l.height/2}) translate(${l.flipX?l.width:0} ${l.flipY?l.height:0}) scale(${l.flipX?-1:1} ${l.flipY?-1:1})`;
function renderCanvas() {
  applyHoop();
  $('fabricRect').setAttribute('fill',project.fabric);$('gridRect').style.display=project.grid?'':'none';
  let crossGrid=$('crossCanvasGrid');if(!crossGrid){crossGrid=node('g',{id:'crossCanvasGrid','pointer-events':'none'});$('gridRect').after(crossGrid);}drawGrids(crossGrid,project.crossGrids);
  $('canvas').setAttribute('viewBox',`${view.x} ${view.y} ${view.w} ${view.h}`);
  $('canvas').classList.toggle('draw-mode',mode==='draw');
  const art=$('artwork');canvasMotion.before(project,art);art.replaceChildren();
  for(const l of [...project.layers.filter(l=>l.type==='image'),...project.layers.filter(l=>l.type!=='image')]) {
    if(l.visible===false)continue;
    const g=node('g',{'data-layer':l.id,class:'art-layer',transform:layerTransform(l)});
    if(l.locked)g.style.pointerEvents='none';
    if(l.type==='image')g.append(imageArtwork(l));
    else if(l.type==='text'){
      const result=textCache.get(textKey(l.lettering));
      if(result)g.append(textPreview(result,l.color,l.preserveFontColors));
      else { g.append(node('rect',{width:l.width,height:l.height,fill:l.color,opacity:.15,rx:1})); const t=node('text',{x:2,y:l.height/2,'font-size':3,fill:l.color});t.textContent='Loading lettering…';g.append(t); }
    } else if(l.type==='import') {
      const asset=assets.get(l.asset);
      if(asset){
        const inner=node('g',{transform:`scale(${l.width/asset.width} ${l.height/asset.height})`});
        // Ink/Stitch may serialize namespace-prefixed SVG tags. Parsing as XML
        // preserves their SVG namespace; HTML innerHTML makes them invisible.
        if(typeof l.ttfLettering?.artwork==='string'&&l.stitch==='original')drawTTFArtwork(inner,l,node);
        else inner.append(document.importNode(new DOMParser().parseFromString(asset.svg,'image/svg+xml').documentElement,true));g.append(inner);art.append(g);
        for(const p of inner.querySelectorAll('path,rect,ellipse,circle,polygon,polyline,line')){
          if(l.stitch==='original'){
            if(l.recolor){const style=getComputedStyle(p),hasFill=style.fill!=='none',hasStroke=style.stroke!=='none';if(hasFill)p.style.fill=l.color;if(hasStroke)p.style.stroke=l.color;}
          }else{
            const fill=l.stitch==='fill';p.style.fill=fill?l.color:'none';p.style.stroke=fill?'none':l.color;
            if(!fill){const m=$('canvas').getScreenCTM().inverse().multiply(p.getScreenCTM()),scale=(Math.hypot(m.a,m.b)+Math.hypot(m.c,m.d))/2,width=l.stitch==='zigzag'?(l.strokeWidth||1.5):.45;p.style.strokeWidth=String(width/Math.max(.000001,scale));p.style.strokeDasharray=l.stitch==='running'?`${1/scale} ${.35/scale}`:'none';}
          }
        }
      }
    } else {g.append(shape(l));if(l.stitch==='fill'&&l.borderEnabled)g.append(shape({...l,closed:true,stitch:l.borderStitch||'running',color:l.borderColor||'#272829',strokeWidth:l.borderWidth||1.5}));}
    decorateCanvasFill(g,l,node);
    if(l.role==='content-area'||l.role==='scene-guide'){g.classList.add('content-area-art');g.style.pointerEvents='none';for(const p of g.querySelectorAll('path')){p.style.stroke=l.role==='scene-guide'?'#ce923d':'#24b6b0';p.style.strokeWidth='.3';p.style.strokeDasharray='1 .7';p.style.fill=l.role==='scene-guide'?'none':'#24b6b010';}}
    else if(l.role&&l.role!=='artwork'){g.classList.add('helper-art');for(const p of g.querySelectorAll('path,rect,circle,ellipse')){if(p.closest('defs'))continue;p.style.stroke='#9453b1';p.style.strokeWidth='.4';p.style.strokeDasharray='1 .5';p.style.fill=l.role==='pattern'&&l.helperFilled?'#9453b133':'none';}}
    // A generous transparent target makes thin stitches and letter interiors
    // selectable with a finger without requiring a hit on a tiny SVG path.
    g.append(node('rect',{width:l.width,height:l.height,fill:'transparent','pointer-events':l.locked||l.role==='content-area'||l.role==='scene-guide'||l.component?.part==='edge'?'none':'all'}));art.append(canvasMotion.wrap(l.id,g));
  }
  let ghosts=$('artGhosts');if(!ghosts){ghosts=node('g',{id:'artGhosts','pointer-events':'none'});art.after(ghosts);}canvasMotion.after(ghosts);
  fontWorkspaces.drawGuides($('canvas'),node);
  stitchPlans.draw($('canvas'),node);
  commands.draw($('canvas'),node);
  orderNumbers.draw($('canvas'),node);
  densityMaps.draw($('canvas'),node);
  troubleshooting.draw($('canvas'),node);
  renderSelection();
  $('emptyState').hidden=project.layers.some(l=>l.visible!==false);
  const outside=project.layers.filter(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork')&&!l.ignoreLayer).filter(l=>{const b=objectBounds(l);return b.x<-.01||b.y<-.01||b.x+b.w>hoop().w+.01||b.y+b.h>hoop().h+.01;});
  $('canvasHint').textContent=outside.length?`${outside.length} layer(s) outside hoop`:mode==='draw'?'Draw with touch or Pencil · Select to edit':selected.size?`${selected.size} selected · ${chosen().some(l=>l.locked)?'Unlock to edit':single()?.linkedHelper?'Edit the source helper':'Drag to move'}`:'Drag to move · Pinch to zoom';
  $('canvasHint').classList.toggle('error',outside.length>0);
}
function renderSelection() {
  const overlay=$('selectionOverlay');overlay.replaceChildren();const list=chosen().filter(l=>l.visible!==false);
  // Fade the outline in only when the selection itself changes, not on every redraw.
  const key=list.map(l=>l.id).join();if(key!==selectionKey){selectionKey=key;overlay.classList.remove('sel-enter','sel-after-place');if(list.length){void overlay.getBoundingClientRect();overlay.classList.add('sel-enter');overlay.classList.toggle('sel-after-place',list.some(l=>canvasMotion.isEntering(l.id)));}}
  if(!list.length)return;
  for(const l of list){const g=node('g',{transform:`translate(${l.x} ${l.y}) rotate(${l.rotation||0} ${l.width/2} ${l.height/2})`});g.append(node('rect',{x:0,y:0,width:l.width,height:l.height,class:'selection-box'}));overlay.append(g);}
  if(list.length===1){const l=list[0],g=node('g',{transform:`translate(${l.x} ${l.y}) rotate(${l.rotation||0} ${l.width/2} ${l.height/2})`});if(l.type!=='text'&&!l.locked&&!l.linkedHelper){const matrix=$('canvas').getScreenCTM(),hit=Math.max(8,44/Math.hypot(matrix.a,matrix.b));g.append(node('rect',{x:l.width-hit/2,y:l.height-hit/2,width:hit,height:hit,class:'resize-hit','data-resize':l.id}));g.append(node('rect',{x:l.width-1,y:l.height-1,width:2,height:2,rx:.3,class:'resize-dot'}));}const text=node('text',{x:l.width/2,y:-1.6,'text-anchor':'middle',class:'selection-size'});text.textContent=`${round(l.width)} × ${round(l.height)} mm`;g.append(text);overlay.append(g);}
}
const field = (label, key, value, min=-100,max=200,step=.5) => `<label>${label}<input data-prop="${key}" type="number" inputmode="decimal" min="${min}" max="${max}" step="any" value="${['spacing','stitchLength','width','height','x','y'].includes(key)?value:round(value)}"></label>`;
const swatches = () => `<div class="swatches">${colors.map(c=>`<button data-color="${c}" aria-label="Thread ${c}"><span style="background:${c}"></span></button>`).join('')}</div>`;
function baseProperties() {
  const host=$('properties'),list=chosen(),l=single();
  if(tab==='fabric') {
    const bg=project.layers.find(l=>l.background);
    host.innerHTML=`<h2>Hoop</h2><label>Design for<select id="hoopSelect">${Object.values(HOOPS).map(h=>`<option value="${h.id}" ${h.id===hoop().id?'selected':''}>${escape(h.label)}</option>`).join('')}</select></label><p class="caption">Export and the design check use this hoop. The PP1 sews only 100 × 100 mm designs.</p><hr class="separator"><h2>The fabric underneath.</h2><p>Preview your design on a fabric color. This color does not add stitches.</p><label>Fabric preview color<input id="fabricColor" type="color" value="${escape(project.fabric)}"></label><label class="check"><input id="gridCheck" type="checkbox" ${project.grid?'checked':''}>Show 10 mm grid</label><label class="check"><input id="snapCheck" type="checkbox" ${project.snap?'checked':''}>Snap movement to 0.5 mm</label><hr class="separator"><h2>Stitched background</h2><p>Add a filled shape that sews before your lettering.</p><button class="wide" id="backgroundBtn">${bg?'Edit stitched background':'＋ Add stitched background'}</button>`;
    $('fabricColor').onchange=e=>mutate(()=>project.fabric=e.target.value);
    $('hoopSelect').onchange=e=>{const next=HOOPS[e.target.value];const art=project.layers.filter(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork'));const b=art.length?groupBounds(art):null;if(b&&(b.x<-.01||b.y<-.01||b.x+b.w>next.w+.01||b.y+b.h>next.h+.01))toast(`Part of the design is outside the ${next.short} mm hoop. Move or resize it before exporting.`);mutate(()=>{if(next.id==='pp1')delete project.hoop;else project.hoop=next.id;});};
    $('gridCheck').onchange=e=>mutate(()=>project.grid=e.target.checked);
    $('snapCheck').onchange=e=>mutate(()=>project.snap=e.target.checked);
    if(project.crossGrids?.length){host.insertAdjacentHTML('beforeend',`<hr class="separator"><h2>Cross-stitch grid</h2><label class="check"><input id="showCrossGrid" type="checkbox" ${project.crossGrids.some(g=>g.visible)?'checked':''}>Show cross-stitch grids</label><label class="check"><input id="snapCrossGrid" type="checkbox" ${project.crossSnap?'checked':''}>Snap moved objects to the last visible grid</label><button id="editCrossGrid" class="wide">Cross-stitch grid settings</button>`);$('showCrossGrid').onchange=e=>mutate(()=>project.crossGrids.forEach(g=>g.visible=e.target.checked));$('snapCrossGrid').onchange=e=>mutate(()=>project.crossSnap=e.target.checked);$('editCrossGrid').onclick=()=>crossTools.open([]);}
    $('backgroundBtn').onclick=()=>{if(bg){selected=new Set([bg.id]);setTab('layer');}else{const b=project.layers.length?groupBounds(project.layers.filter(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork'))):null;const w=b?Math.min(hoop().w-4,b.w+10):70,h=b?Math.min(hoop().h-4,b.h+10):40;const layer=newLayer('rectangle',{name:'Stitched background',background:true,x:clamp(b?b.x-5:15,0,hoop().w-w),y:clamp(b?b.y-5:30,0,hoop().h-h),width:w,height:h,color:'#d4ac59',radius:3});mutate(()=>{project.layers.unshift(layer);selected=new Set([layer.id]);});setTab('layer');}};
    return;
  }
  if(tab==='arrange')return;
  if(!l) {
    host.innerHTML=list.length?`<h2>${list.length} layers selected</h2><p>Use Arrange to align, center, or stack these objects.</p><button id="arrangeSelected" class="wide">Arrange selected layers</button><label>Thread color<input type="color" id="groupColor" value="${list[0].color}"></label><button id="deleteSelected" class="wide danger">Delete selected layers</button>`:`<span class="eyebrow">YOUR DESIGN</span><h2>Start with an idea.</h2><p>Tap a tool on the left to add lettering or a shape. Select a layer to change its thread and stitches.</p><button id="addTextPrompt" class="wide">＋ Add multiline lettering</button>`;
    if(list.length){$('arrangeSelected').onclick=()=>setTab('arrange');$('groupColor').onchange=e=>mutate(()=>chosen().forEach(l=>setLayerColor(l,e.target.value)));$('deleteSelected').onclick=deleteSelected;}else $('addTextPrompt').onclick=()=>openLettering();
    return;
  }
  const fillMethod=l.fillMethod||'tatami_fill',showSpacing=l.stitch==='zigzag'||(l.stitch==='fill'&&!['cross_stitch','meander_fill','streamline_fill','wave_fill'].includes(fillMethod)),showLength=['running','bean','ripple'].includes(l.stitch)||(l.stitch==='fill'&&fillMethod!=='cross_stitch');
  const typeName=l.type==='text'?'Lettering':l.type==='import'?(l.ttfLettering?'TTF / OTF lettering':'SVG'):isFlowFill(l)?flowName(l)+' fill':l.merrow?'Faux merrow border':l.background?'Background':l.type==='path'?'Drawing':'Shape';
  host.innerHTML=`<div class="selected-title"><h2>${typeName}</h2><span class="tag">${round(l.width)} × ${round(l.height)} mm</span></div>
    ${l.type==='text'?`<p style="white-space:pre-line">${escape(l.lettering.text)}</p><button id="editLetterBtn" class="wide">Edit text, font & line spacing</button>`:`<label>Layer name<input id="layerName" value="${escape(l.name)}" maxlength="100"></label>`}
    <div class="field-row">${field('X (mm)','x',l.x)}${field('Y (mm)','y',l.y)}</div>
    ${l.type==='text'?'':`<div class="field-row">${field('Width (mm)','width',l.width,.2,hoopMax())}${field('Height (mm)','height',l.height,.2,hoopMax())}</div><label class="check"><input id="aspectLock" type="checkbox" ${l.aspectLock!==false?'checked':''}>Keep proportions</label>`}
    ${field('Rotation (°)','rotation',l.rotation||0,-360,360,1)}
    <label>${l.multicolorSatin?'First satin thread':'Thread color'}<input data-prop="color" type="color" value="${escape(l.multicolorSatin?.bands?.[0]?.color||l.color)}" ${l.preserveFontColors?'disabled':''}></label>${swatches()}
    ${l.type==='import'?`<label class="check"><input id="recolorCheck" type="checkbox" ${l.recolor?'checked':''}>Use this color for the whole SVG</label>`:''}
    ${l.type==='text'?'<p class="caption">This embroidery font keeps its own satin/fill construction and underlay settings.</p>':`<hr class="separator"><label>Stitch type<select data-prop="stitch">${[['fill','Fill stitches'],['running','Running stitch'],['bean','Bean stitch (triple run)'],['zigzag','Zigzag border'],['ripple','Ripple stitches'],['manual','Manual stitch points'],...(l.type==='path'&&l.contours?.length>=2?[['satin','Satin column']]:[]),...((l.type==='import'||l.originalParams)?[['original',l.ttfLettering?'Keep satin lettering':l.merrow?'Keep faux merrow border':'Preserve SVG / Ink/Stitch settings']]:[])].map(([v,n])=>`<option value="${v}" ${v===l.stitch?'selected':''}>${n}</option>`).join('')}</select></label>
    ${l.stitch==='original'?(l.ttfLettering?'<p class="caption">Use Edit TTF/OTF lettering to change the words or satin settings. Separate paths to edit individual columns.</p>':l.merrow?'<p class="caption">Edit faux merrow border to change the fans, binding or width. Edit nodes changes its closed outline; stitch preview regenerates the border.</p>':'<p class="caption">The imported SVG’s stitch settings and thread colors are preserved. Choose another stitch type to override them.</p>'):`${showSpacing?field('Row spacing · density (mm)','spacing',l.spacing,.2,2,.05):''}${l.stitch==='fill'&&['tatami_fill','legacy_fill'].includes(fillMethod)?field('Fill angle (°)','angle',l.angle,-180,180,5):''}${showLength?field('Stitch length (mm)','stitchLength',l.stitchLength,.5,6,.25):''}${l.stitch==='zigzag'?field('Zigzag width (mm)','strokeWidth',l.strokeWidth||1.5,.3,6,.25):''}${l.stitch==='fill'&&!['streamline_fill','wave_fill'].includes(fillMethod)?`<label class="check"><input id="underlayCheck" type="checkbox" ${l.underlay?'checked':''}>Fill underlay</label><p class="caption">Smaller row spacing adds more stitches. Underlay supports the top fill.</p>`:''}`}
    ${l.type==='rectangle'?field('Corner radius (mm)','radius',l.radius||0,0,50,.5):''}${l.type==='path'&&!l.contours?`<label class="check"><input id="closedCheck" type="checkbox" ${l.closed?'checked':''}>Close path</label>`:''}`}
    <div class="button-row"><button id="earlierBtn">↑ Sew earlier</button><button id="laterBtn">↓ Sew later</button></div><div class="button-row"><button id="duplicateBtn">Duplicate</button><button id="deleteBtn" class="danger">Delete</button></div>`;
  host.querySelectorAll('[data-prop]').forEach(input=>{
    let editing=false;
    const apply=()=>{
      const key=input.dataset.prop, value=input.type==='number'?Number(input.value):input.value;
      if(input.value===''||input.type==='number'&&(!input.validity.valid||!Number.isFinite(value)))return;
      if(value===l[key])return;
      let size;
      if(key==='width'||key==='height')try{size=resizedDimensions(l,key,value,hoopMax());}catch(error){input.setCustomValidity(error.message);return;}
      if(!editing){checkpoint();editing=true;}
      if(size){Object.assign(l,size);const other=key==='width'?'height':'width';host.querySelector(`[data-prop="${other}"]`).value=l[other];}
      l[key]=value;if(key==='color'){setLayerColor(l,value);if($('recolorCheck'))$('recolorCheck').checked=true;}
      changed(false);renderCanvas();renderLayers();$('undoBtn').disabled=false;$('redoBtn').disabled=true;
      host.querySelector('.tag').textContent=`${round(l.width)} × ${round(l.height)} mm`;
      // Keep focused inputs and the next tapped control mounted. Rebuilding
      // this panel on blur used to swallow the next iPad tap.
      if(key==='stitch')renderProperties();
    };
    input.oninput=()=>{input.setCustomValidity('');apply();};input.onchange=apply;
    input.onblur=()=>{editing=false;};
  });
  host.querySelectorAll('[data-color]').forEach(b=>{b.disabled=!!l.preserveFontColors;b.onclick=()=>mutate(()=>setLayerColor(l,b.dataset.color));});
  if($('editLetterBtn'))$('editLetterBtn').onclick=()=>openLettering(l);
  if($('layerName')){let editingName=false;$('layerName').oninput=e=>{if(!editingName){checkpoint();editingName=true;}l.name=e.target.value;changed(false);renderLayers();};$('layerName').onblur=()=>editingName=false;}
  if($('aspectLock'))$('aspectLock').onchange=e=>mutate(()=>l.aspectLock=e.target.checked);
  if($('underlayCheck'))$('underlayCheck').onchange=e=>mutate(()=>l.underlay=e.target.checked);
  if($('recolorCheck'))$('recolorCheck').onchange=e=>mutate(()=>l.recolor=e.target.checked);
  if($('closedCheck'))$('closedCheck').onchange=e=>mutate(()=>l.closed=e.target.checked);
  $('duplicateBtn').onclick=()=>{const c=copy(l);c.id=uid();c.name+=' copy';c.x+=3;c.y+=3;c.background=false;addLayer(c);};
  $('deleteBtn').onclick=deleteSelected;
  $('earlierBtn').onclick=()=>reorder(l,-1);$('laterBtn').onclick=()=>reorder(l,1);
  $('earlierBtn').disabled=project.layers.indexOf(l)===0;$('laterBtn').disabled=project.layers.indexOf(l)===project.layers.length-1;
}
let arrangeGap=3,nudgeStep=.5,backgroundPadding=5,alignToHoop=false;
const openSections=new Map();
function editable(){if(!chosen().length)return false;if(chosen().some(l=>l.locked)){toast('Unlock the selected layers before editing them.');return false;}return true;}
function editChosen(fn){if(editable())mutate(()=>fn(chosen().filter(l=>!l.linkedHelper)));}
function duplicateSelected(){if(!editable())return;const selectedLayers=chosen().filter(l=>!l.linkedHelper),ids=new Set(selectedLayers.map(l=>l.id)),sources=project.layers.filter(l=>!l.linkedHelper&&(ids.has(l.id)||ids.has(l.helperTarget)));if(project.layers.length+sources.length>MAX_LAYERS)return toast(`A project can contain up to ${MAX_LAYERS} layers.`);const groups=new Map(),mapping=new Map(sources.map(l=>[l.id,uid()])),copies=sources.map(l=>{const c=copy(l);c.id=mapping.get(l.id);c.name+=' copy';c.x+=3;c.y+=3;c.background=false;if(c.link&&mapping.has(c.link.sourceId))c.link.sourceId=mapping.get(c.link.sourceId);if(c.sceneBinding){if(mapping.has(c.sceneBinding.guideId))c.sceneBinding.guideId=mapping.get(c.sceneBinding.guideId);else delete c.sceneBinding;}if(c.scene?.areaId&&mapping.has(c.scene.areaId))c.scene.areaId=mapping.get(c.scene.areaId);if(c.helperTarget&&mapping.has(c.helperTarget))c.helperTarget=mapping.get(c.helperTarget);if(c.areaSource&&mapping.has(c.areaSource))c.areaSource=mapping.get(c.areaSource);if(c.groupId){if(!groups.has(c.groupId))groups.set(c.groupId,uid());c.groupId=groups.get(c.groupId);}return c;});mutate(()=>{project.layers.push(...copies);selected=new Set(copies.map(l=>l.id));});}
async function scaleSelected(factor){
  if(!editable()||!Number.isFinite(factor)||factor<.1||factor>4)return toast('Choose a scale between 10% and 400%.');
  const list=copy(chosen().filter(l=>!l.linkedHelper)),b=groupBounds(list),revision=modelRevision,projectId=project.id;
  if(!list.length)return;
  $('scaleSelection').disabled=true;
  $('scaleSelection').textContent='Resizing selection…';
  try{
    for(const l of list){
      const cx=b.x+b.w/2+(l.x+l.width/2-b.x-b.w/2)*factor,cy=b.y+b.h/2+(l.y+l.height/2-b.y-b.h/2)*factor;
      if(l.type==='text'){
        const s={...l.lettering,scale:l.lettering.scale*factor,lineSpacing:(l.lettering.lineSpacing||0)*factor,letterSpacing:(l.lettering.letterSpacing||0)*factor,wordSpacing:(l.lettering.wordSpacing||0)*factor};
        const r=await api('/api/lettering',s);textCache.set(textKey(r.settings),r);l.lettering=r.settings;l.width=r.width;l.height=r.height;
      }else{l.width*=factor;l.height*=factor;if(l.radius)l.radius=Math.min(50,l.width/2,l.height/2,l.radius*factor);}
      if(l.helperTarget&&l.type==='path'&&(l.width<.2||l.height<.2)){l.x=cx-l.width/2;l.y=cy-l.height/2;Object.assign(l,packContours(worldContours(l),l));continue;}
      const sizeLimit=l.helperTarget?10000:hoopMax();
      if(l.width<.2||l.height<.2||l.width>sizeLimit||l.height>sizeLimit)throw new Error(`A layer would exceed the 0.2–${hoopMax()} mm size limits. Choose a smaller change.`);
      l.x=cx-l.width/2;l.y=cy-l.height/2;
    }
    let resolved=null;
    if(project.layers.some(l=>l.link)){const proposed=copy(project);for(const l of list)Object.assign(proposed.layers.find(p=>p.id===l.id),l);resolved=await api('/api/linked-resolve',{project:proposed,fixedSizeIds:list.map(l=>l.id)});}
    if(project.id!==projectId||modelRevision!==revision)throw new Error('The design changed during resizing. Apply the size again.');
    mutate(()=>{if(resolved)project.layers=resolved.layers;else for(const l of list)Object.assign(project.layers.find(p=>p.id===l.id),l);});
    await hydrateLinkedText();
    toast('Selection resized. Stitch density and outline width stay in millimeters.');
  }catch(e){toast(e.message);}
  finally{if($('scaleSelection')){$('scaleSelection').disabled=chosen().some(l=>l.locked);$('scaleSelection').textContent='Apply selection size';}}
}
function reorderSelection(where){editChosen(list=>{const ids=new Set(list.map(l=>l.id)),other=project.layers.filter(l=>!ids.has(l.id));if(where==='first'||where==='last'){project.layers=where==='first'?[...list,...other]:[...other,...list];return;}const direction=where==='earlier'?-1:1,ordered=direction<0?[...list]:[...list].reverse();for(const l of ordered){const i=project.layers.indexOf(l),j=i+direction;if(j>=0&&j<project.layers.length&&!ids.has(project.layers[j].id)){[project.layers[i],project.layers[j]]=[project.layers[j],project.layers[i]];}}});}
const extraField=(label,key,value,min,max)=>field(label,key,value,min,max).replace('data-prop','data-extra');
const checkExtra=(label,key,value)=>`<label class="check"><input data-extra="${key}" type="checkbox" ${value?'checked':''}>${label}</label>`;
function renderProperties(){
  const panel=$('properties'),selectionKey=tab+'|'+[...selected].sort().join(',');if(panel.dataset.selectionKey!==selectionKey){panel.dataset.selectionKey=selectionKey;panel.scrollTop=0;panel.parentElement.scrollTop=0;}
  if(mode==='draw'&&tab==='layer'){penControls.render($('properties'));return;}
  if((['layer','digitize'].includes(tab)&&chosen().some(l=>l.link||l.linkedHelper))||(single()?.linkedHelper&&tab==='arrange')){linked.panel($('properties'));return;}
  if(tab==='digitize'){digitizer.render($('properties'));components.mount($('properties'));scenes.mount($('properties'));linked.mount($('properties'));return;}
  if(tab==='layer'&&single()?.type==='image'){references.properties($('properties'),single());return;}
  const oldHost=$('properties');
  oldHost.querySelectorAll('details').forEach(d=>openSections.set(`${oldHost.dataset.panel}:${d.querySelector('summary').textContent}`,d.open));
  baseProperties();
  const host=$('properties'),list=chosen(),l=single(),locked=list.some(l=>l.locked);
  host.dataset.panel=tab;
  if(tab==='layer'){components.mount(host);scenes.mount(host);linked.mount(host);}
  if(tab==='fabric'){
    const bg=project.layers.find(l=>l.background);
    host.insertAdjacentHTML('beforeend',`<label>Padding around design (mm)<input id="backgroundPadding" type="number" min="0" max="20" step="any" value="${backgroundPadding}"></label><button id="fitBackground" class="wide">${bg?'Fit background to design':'Add background fitted to design'}</button>${bg?'<button id="removeBackground" class="wide danger">Remove stitched background</button>':''}<p class="caption">Fit uses visible artwork, including rotated layers. Background color and outline are edited in Layer.</p>`);
    $('backgroundPadding').oninput=e=>{if(e.target.value!==''&&e.target.validity.valid)backgroundPadding=Number(e.target.value);};
    $('fitBackground').onclick=()=>{try{if(bg?.locked)throw new Error('Unlock the background before fitting it.');const fit=fitBackground(project.layers,backgroundPadding,hoop());mutate(()=>{if(bg)Object.assign(bg,fit);else project.layers.unshift(newLayer('rectangle',{...fit,name:'Stitched background',background:true,color:'#d4ac59'}));});}catch(e){toast(e.message);}};
    if(bg)$('removeBackground').onclick=()=>{if(bg.locked)return toast('Unlock the background before removing it.');mutate(()=>{project.layers=project.layers.filter(l=>l!==bg);selected.delete(bg.id);});};
    return;
  }
  if(tab==='arrange'){
    const count=units(list).length;
    host.innerHTML=`<h2>Arrange your design.</h2><p>${list.length} layers selected${list.some(l=>l.groupId)?` · ${count} object(s) or groups`:''}.</p><div class="button-row"><button id="selectAll">Select all unlocked</button><button id="clearSelection">Deselect</button></div><fieldset ${!list.length||locked?'disabled':''}><label>Align relative to<select id="alignTarget"><option value="selection" ${!alignToHoop?'selected':''}>Selection bounds</option><option value="hoop" ${alignToHoop?'selected':''}>${hoop().short} mm hoop</option></select></label><div class="button-row">${[['left','Left'],['center','Center'],['right','Right']].map(([v,n])=>`<button data-arrange-align="${v}">${n}</button>`).join('')}</div><div class="button-row">${[['top','Top'],['middle','Middle'],['bottom','Bottom']].map(([v,n])=>`<button data-arrange-align="${v}">${n}</button>`).join('')}</div><button id="centerSelection" class="wide">Center design in hoop</button><p class="caption">Groups move as one object. One object aligns to the hoop.</p><h3>Spacing</h3><label>Gap between objects (mm)<input id="arrangeGap" type="number" min="0" max="30" step="any" value="${arrangeGap}"></label><div class="button-row"><button data-stack-axis="y" ${count<2?'disabled':''}>Stack vertically ↓</button><button data-stack-axis="x" ${count<2?'disabled':''}>Stack horizontally →</button></div><div class="button-row"><button data-space-axis="y" ${count<3?'disabled':''}>Even vertical gaps</button><button data-space-axis="x" ${count<3?'disabled':''}>Even horizontal gaps</button></div></fieldset>`;
    $('selectAll').onclick=()=>{selected=new Set(project.layers.filter(l=>!l.locked&&!l.linkedHelper&&l.visible!==false).map(l=>l.id));renderAll();};$('clearSelection').onclick=()=>{selected.clear();renderAll();};
    $('alignTarget').onchange=e=>alignToHoop=e.target.value==='hoop';
    host.querySelectorAll('[data-arrange-align]').forEach(b=>b.onclick=()=>editChosen(ls=>alignLayers(ls,b.dataset.arrangeAlign,alignToHoop&&hoop(),hoop())));
    $('centerSelection').onclick=()=>editChosen(ls=>{const b=groupBounds(ls);move(ls,hoop().w/2-b.x-b.w/2,hoop().h/2-b.y-b.h/2);});
    $('arrangeGap').oninput=e=>{if(e.target.value!==''&&e.target.validity.valid)arrangeGap=Number(e.target.value);};
    host.querySelectorAll('[data-stack-axis]').forEach(b=>b.onclick=()=>editChosen(ls=>spaceLayers(ls,b.dataset.stackAxis,arrangeGap)));
    host.querySelectorAll('[data-space-axis]').forEach(b=>b.onclick=()=>editChosen(ls=>spaceLayers(ls,b.dataset.spaceAxis)));
    selectionTools.mount(host);
    $('selectionControlSection').open=openSections.get('arrange:Select stitches & set sewing order')??true;
  }
  if(!list.length)return;
  // Keep the core controls compact; advanced stitch options open on demand.
  if(l&&tab==='layer'){
    let extras='';
    if(l.type==='text')extras+=checkExtra('Keep font thread colors','preserveFontColors',l.preserveFontColors)+'<p class="caption">Preserves the built-in placement, tack-down and finishing colors of appliqué fonts. Separate lettering paths to edit individual thread colors.</p>';
    if(l.stitch==='manual')extras+='<p class="caption">Each node becomes a needle point. Use Edit nodes to place stitches; curves use their endpoints. Advanced settings can split long segments.</p>';
    if(l.stitch==='ripple')extras+='<p class="caption">Closed shapes spiral toward their center. Two subpaths interpolate between the paths. Set line count, spacing and taper under Advanced stitch settings.</p>';
    if(l.type!=='text'&&l.stitch==='fill')extras+=`<label>Fill pattern<select data-extra="fillMethod">${[['tatami_fill','Tatami rows'],['contour_fill','Contour fill'],['circular_fill','Circular fill'],['meander_fill','Meander / stippling'],['cross_stitch','Cross stitch'],['legacy_fill','Legacy rows'],['linear_gradient_fill','Color gradient'],['tartan_fill','Tartan / plaid'],['guided_fill','Follow a guide path'],...(['path','rectangle','ellipse'].includes(l.type)?[['streamline_fill','Streamlines · flow field'],['wave_fill','Wave Fill · flow field']]:[])].map(([v,n])=>`<option value="${v}" ${v===(l.fillMethod||'tatami_fill')?'selected':''}>${n}</option>`).join('')}</select></label>`;
    if(l.stitch==='satin')extras+=`<details class="control-section" open><summary>Satin column settings</summary>${extraField('Satin spacing (mm)','spacing',l.spacing??.4,.2,2)}${extraField('Maximum satin length (mm)','satinMaxLength',l.satinMaxLength||6,1,12)}${extraField('Pull compensation per side (mm)','pullCompensation',l.pullCompensation||0,0,1)}${checkExtra('Center-walk underlay','satinCenter',l.satinCenter!==false)}${checkExtra('Contour underlay','satinContour',l.satinContour)}${checkExtra('Zigzag underlay','satinZigzag',l.satinZigzag)}${checkExtra('Start at nearest point','nearestStart',l.nearestStart!==false)}${checkExtra('End at nearest point','nearestEnd',l.nearestEnd!==false)}<button id="editSatin" class="wide">Edit rails & rungs</button></details>`;
    if(l.type!=='text'&&l.stitch==='fill'&&!isFlowFill(l))extras+=`<details class="control-section"><summary>Fill compensation & underlay</summary>${extraField('Pull compensation per side (mm)','pullCompensation',l.pullCompensation||0,0,1)}${l.underlay?extraField('Underlay row spacing (mm)','underlaySpacing',l.underlaySpacing??Math.max(1.2,l.spacing*3),.4,5)+extraField('Underlay inset (mm)','underlayInset',l.underlayInset||0,0,3):''}<p class="caption">Compensation extends stitch rows past the shape edge. Check the generated size before sewing.</p></details>`;
    if(['rectangle','ellipse','path'].includes(l.type)&&l.stitch==='fill')extras+=`<details class="control-section" ${l.borderEnabled?'open':''}><summary>Outline over fill</summary>${checkExtra('Sew an outline after the fill','borderEnabled',l.borderEnabled)}${l.borderEnabled?`<label>Outline thread<input type="color" data-extra="borderColor" value="${escape(l.borderColor||'#272829')}"></label><label>Outline stitch<select data-extra="borderStitch">${[['running','Running stitch'],['bean','Bean stitch'],['zigzag','Zigzag border']].map(([v,n])=>`<option value="${v}" ${v===(l.borderStitch||'running')?'selected':''}>${n}</option>`).join('')}</select></label>${extraField('Outline stitch length (mm)','borderLength',l.borderLength||2.5,.5,6)}${l.borderStitch==='zigzag'?extraField('Outline width (mm)','borderWidth',l.borderWidth||1.5,.3,6)+extraField('Outline spacing (mm)','borderSpacing',l.borderSpacing||.4,.2,2):''}<p class="caption">The outline sews immediately after this fill. Its color is independent.</p>`:''}</details>`;
    extras+=`<details class="control-section"><summary>Trim & pause after layer</summary>${checkExtra('Request trim after this layer','trimAfter',l.trimAfter??(l.originalParams?.trim_after!==undefined?/^(true|1)$/i.test(String(l.originalParams.trim_after)):(l.type!=='text'&&l.stitch!=='original')))}${checkExtra('Pause after this layer','stopAfter',l.stopAfter??/^(true|1)$/i.test(String(l.originalParams?.stop_after)))}<p class="caption">Unchecked allows short connecting stitches; PES jumps may still trim. Internal lettering and SVG commands stay intact. Pauses are encoded in PES; the machine controls execution.</p></details>`;
    host.insertAdjacentHTML('beforeend',extras);
    specialFills.mount(host,l);multisatin.mount(host,l);references.mount(host,l);ttfLettering.mount(host,l);merrowControls.mount(host,l);streamlineControls.mount(host,l);featherControls.mount(host,l);helpers.mount(host,l);commands.mount(host);advanced.mountLayer(host,l);threads.mount(host);
    if($('editSatin'))$('editSatin').onclick=()=>digitizer.editNodes(l);
    host.querySelectorAll('[data-extra]').forEach(input=>{
      let editing=false;
      input.oninput=()=>{if(input.dataset.extra==='fillMethod'&&['streamline_fill','wave_fill'].includes(input.value)&&l.fillMethod!==input.value){const method=input.value;input.value=l.fillMethod||'tatami_fill';streamlineControls.open(l,method);return;}if(input.type==='number'&&(input.value===''||!input.validity.valid))return;if(!editing){checkpoint();editing=true;}l[input.dataset.extra]=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;changed(false);renderCanvas();if(input.type==='checkbox'||input.tagName==='SELECT')renderProperties();};input.onblur=()=>editing=false;
    });
    $('duplicateBtn').onclick=duplicateSelected;
    if(l.groupId){host.insertAdjacentHTML('afterbegin','<button id="selectGroup" class="wide">Select whole group</button>');$('selectGroup').onclick=()=>{selected=new Set(project.layers.filter(p=>p.groupId===l.groupId).map(p=>p.id));setTab('arrange');renderAll();};}
  }
  host.insertAdjacentHTML('beforeend',`<details class="control-section" ${tab==='arrange'?'open':''}><summary>Move, mirror & rotate</summary><fieldset ${locked?'disabled':''}><label>Nudge distance (mm)<input id="nudgeStep" type="number" min="0.1" max="10" step="any" value="${nudgeStep}"></label><div class="nudge-pad"><button data-nudge="up" aria-label="Nudge up">↑</button><button data-nudge="left" aria-label="Nudge left">←</button><button data-nudge="down" aria-label="Nudge down">↓</button><button data-nudge="right" aria-label="Nudge right">→</button></div><div class="button-row"><button data-mirror="x">Mirror ↔</button><button data-mirror="y">Mirror ↕</button></div><div class="button-row"><button data-turn="-90">Rotate −90°</button><button data-turn="90">Rotate +90°</button></div><label>Turn selection (°)<input id="turnDegrees" type="number" min="-360" max="360" step="any" value="15"></label><button id="turnSelection" class="wide">Apply rotation</button><p class="caption">These controls keep fill directions fixed on the fabric. To turn stitches with the shapes, preview a transform that also changes fill directions.</p><button id="transformStitches" class="wide">Rotate / mirror stitch directions</button></fieldset></details><details class="control-section" ${tab==='arrange'?'open':''}><summary>Group, protect & stitch order</summary><fieldset ${locked?'disabled':''}><div class="button-row"><button id="groupSelection" ${list.length<2?'disabled':''}>Group</button><button id="ungroupSelection" ${!list.some(l=>l.groupId)?'disabled':''}>Ungroup</button></div><p class="caption">Tap a group on the canvas to move it together. Tap a layer in Stitch order to edit one member.</p><div class="button-row"><button data-order="first">Sew first</button><button data-order="last">Sew last</button></div>${list.length>1?'<div class="button-row"><button data-order="earlier">↑ Sew earlier</button><button data-order="later">↓ Sew later</button></div><div class="button-row"><button id="duplicateSelection">Duplicate all</button><button id="deleteSelection" class="danger">Delete all</button></div>':''}</fieldset><button id="lockSelection" class="wide">${locked?'Unlock selected layers':'Lock selected layers'}</button></details>`);
  $('nudgeStep').oninput=e=>{if(e.target.value!==''&&e.target.validity.valid)nudgeStep=Number(e.target.value);};
  host.querySelectorAll('[data-nudge]').forEach(b=>b.onclick=()=>{const d={up:[0,-1],down:[0,1],left:[-1,0],right:[1,0]}[b.dataset.nudge];editChosen(ls=>move(ls,d[0]*nudgeStep,d[1]*nudgeStep));});
  host.querySelectorAll('[data-mirror]').forEach(b=>b.onclick=()=>editChosen(ls=>mirrorLayers(ls,b.dataset.mirror)));
  host.querySelectorAll('[data-turn]').forEach(b=>b.onclick=()=>editChosen(ls=>rotateLayers(ls,Number(b.dataset.turn))));
  $('turnSelection').onclick=()=>{const input=$('turnDegrees');if(input.value!==''&&input.validity.valid)editChosen(ls=>rotateLayers(ls,Number(input.value)));};
  $('transformStitches').onclick=()=>operations.open('transform_elements');
  $('groupSelection').onclick=()=>editChosen(ls=>{const id=uid();ls.forEach(l=>l.groupId=id);});
  $('ungroupSelection').onclick=()=>editChosen(ls=>{const ids=new Set(ls.map(l=>l.groupId).filter(Boolean));project.layers.forEach(l=>{if(ids.has(l.groupId))delete l.groupId;});});
  host.querySelectorAll('[data-order]').forEach(b=>b.onclick=()=>reorderSelection(b.dataset.order));
  if($('duplicateSelection'))$('duplicateSelection').onclick=duplicateSelected;
  if($('deleteSelection'))$('deleteSelection').onclick=deleteSelected;
  $('lockSelection').onclick=()=>mutate(()=>list.forEach(l=>l.locked=!locked));
  const bounds=groupBounds(list.filter(l=>!l.linkedHelper))||groupBounds(list);
  host.insertAdjacentHTML('beforeend',`<details class="control-section"><summary>Resize selection together</summary><fieldset ${locked?'disabled':''}><p class="caption">${round(bounds.w)} × ${round(bounds.h)} mm. Keeps proportions and the selection center. Lettering is regenerated within its font’s supported range.</p><label>Selection scale (%)<input id="selectionScale" type="number" min="10" max="400" step="any" value="100"></label><div class="field-row"><label>Selection width (mm)<input id="selectionWidth" type="number" min="0.2" max="${hoopMax()}" step="any" value="${round(bounds.w)}"></label><label>Selection height (mm)<input id="selectionHeight" type="number" min="0.2" max="${hoopMax()}" step="any" value="${round(bounds.h)}"></label></div><button id="scaleSelection" class="wide">Apply selection size</button><p class="caption">Density, stitch length and outline width stay unchanged. Text line and letter spacing scale with the text.</p></fieldset></details>`);
  const scaleInput=$('selectionScale');
  scaleInput.oninput=()=>{if(scaleInput.value!==''&&scaleInput.validity.valid){$('selectionWidth').value=round(bounds.w*Number(scaleInput.value)/100);$('selectionHeight').value=round(bounds.h*Number(scaleInput.value)/100);}};
  for(const [id,size,other,otherSize] of [['selectionWidth','w','selectionHeight','h'],['selectionHeight','h','selectionWidth','w']])$(id).oninput=()=>{const input=$(id);if(input.value!==''&&input.validity.valid){const factor=Number(input.value)/bounds[size];scaleInput.value=round(factor*100);$(other).value=round(bounds[otherSize]*factor);}};
  $('scaleSelection').onclick=()=>{if(scaleInput.value!==''&&scaleInput.validity.valid)scaleSelected(Number(scaleInput.value)/100);};
  if(locked){host.querySelectorAll('input,select,textarea,button').forEach(e=>{if(!['lockSelection','selectGroup','selectAll','clearSelection','arrangeSelected','openStitchSelector','startTapOrder'].includes(e.id))e.disabled=true;});host.insertAdjacentHTML('afterbegin','<p class="lock-note">Locked layers keep their position and settings. Unlock below to edit.</p>');}
  host.querySelectorAll('details').forEach(d=>{const key=`${tab}:${d.querySelector('summary').textContent}`;if(openSections.has(key))d.open=openSections.get(key);});
}
function align(kind) {editChosen(ls=>alignLayers(ls,kind,false,hoop()));}
function deleteSelected() {if(!editable())return;mutate(()=>{project.layers=project.layers.filter(l=>!selected.has(l.id));selected.clear();});}
function reorder(l,delta) {const i=project.layers.indexOf(l),j=i+delta;if(j<0||j>=project.layers.length)return;mutate(()=>{project.layers.splice(i,1);project.layers.splice(j,0,l);});}
function layerDescription(l){return (l.type==='image'?'Reference image':l.ttfLettering?'Satin lettering':isFlowFill(l)?flowName(l)+' fill':l.merrow?'Faux merrow border':l.type==='text'?`${l.lettering.text.split('\n').length} line(s) · ${l.lettering.align}`:l.role&&l.role!=='artwork'?'Helper · '+l.role:l.background?'Stitched background':l.stitch)+` · ${round(l.width)} mm`;}
function renderLayers() {
  queueMicrotask(()=>{const row=$('layers').querySelector('.layer-row.selected');if(row&&!document.querySelector('.layers-section.collapsed'))row.scrollIntoView({block:'nearest'});});
  $('layerCount').textContent=`${project.layers.length} layer${project.layers.length===1?'':'s'}`;
  $('layers').innerHTML=project.layers.map((l,i)=>`<div class="layer-row ${selected.has(l.id)?'selected':''} ${l.visible===false?'hidden-layer':''}"><button class="layer-main" data-layer-id="${l.id}" aria-pressed="${selected.has(l.id)}"><span class="layer-num">${i+1}</span><span class="layer-dot" style="background:${escape(l.color)}"></span><span class="layer-copy"><strong>${l.locked?"🔒 ":""}${l.groupId?"▣ ":""}${escape(l.name)}</strong><small>${escape(layerDescription(l))}</small></span></button><button class="layer-eye" ${l.linkedHelper?'disabled':''} data-visibility="${l.id}" aria-label="${l.visible===false?'Show':'Hide'} ${escape(l.name)}">${l.visible===false?'○':'◉'}</button></div>`).join('')||'<p class="caption">Your layers will appear here.</p>';
  for(const button of $('layers').querySelectorAll('[data-layer-id]')){const layer=project.layers.find(l=>l.id===button.dataset.layerId);if(layer?.ignoreLayer||layer?.ignoreObject){const badge=document.createElement('span');badge.className='selection-pick';badge.textContent=layer.ignoreLayer?'Not sewn':'Primary path not sewn';button.querySelector('.layer-copy').append(badge);}}
  $('layers').querySelectorAll('[data-layer-id]').forEach(b=>b.onclick=()=>selectLayer(b.dataset.layerId));
  layerListToggle();
  if(multi){const ids=[...selected].filter(id=>project.layers.some(l=>l.id===id&&(l.role||'artwork')==='artwork'&&l.type!=='image'));for(const b of $('layers').querySelectorAll('[data-layer-id]')){const index=ids.indexOf(b.dataset.layerId);if(index>=0){const badge=document.createElement('span');badge.className='selection-pick';badge.textContent='Pick '+(index+1);b.querySelector('.layer-copy').append(badge);}}}
  $('layers').querySelectorAll('[data-visibility]').forEach(b=>b.onclick=()=>mutate(()=>{const l=project.layers.find(l=>l.id===b.dataset.visibility);l.visible=l.visible===false;}));
}
function selectLayer(id,toggle=multi) {if(toggle){if(selected.has(id))selected.delete(id);else selected.add(id);}else selected=new Set([id]);renderAll();}
function setTab(next) {tab=next;document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-selected',b.dataset.tab===tab);});renderProperties();}
function renderAll() {renderCanvas();renderProperties();renderLayers();$('undoBtn').disabled=!history.length;$('redoBtn').disabled=!future.length;if(document.activeElement!==$('projectName'))$('projectName').value=project.name;}
function undo() {if(!history.length)return;future.push(copy(project));project=history.pop();selected.clear();canvasMotion.quiet();changed();hydrate();}
function redo() {if(!future.length)return;history.push(copy(project));project=future.pop();selected.clear();canvasMotion.quiet();changed();hydrate();}

function updateFontInfo(reset=false) {
  const f=fonts.find(f=>f.id===$('fontSelect').value);if(!f)return;
  $('fontScale').min=f.minScale;$('fontScale').max=f.maxScale;
  if(reset)$('fontScale').value=clamp(100,f.minScale,f.maxScale);
  $('fontHeight').value=f.size?`${round(f.size*Number($('fontScale').value)/100)} mm`:'Varies by glyph';
  $('fontInfo').textContent=`Supported scale ${f.minScale}–${f.maxScale}%. ${f.case?f.case+'case lettering. ':''}Nominal height is the font size; the finished block size depends on its letters.`;
  $('letterColorSort').disabled=!f.sortable;if(!f.sortable)$('letterColorSort').value='off';
  $('selectedFontName').textContent=f.name;
  $('selectedFontPreview').src=f.preview||`/font-previews/${encodeURIComponent(f.id)}.png`;
  $('selectedFontPreview').alt=`${f.name} embroidery preview`;
  $('fontPickerBtn').setAttribute('aria-label',`Embroidery font: ${f.name}. Change font`);
}
function renderFontPicker(){
  const query=$('fontSearch').value.trim().toLocaleLowerCase();
  const matches=fonts.filter(f=>!f.hidden&&(!$('fontPickerFavorites').checked||f.favorite)&&`${f.name} ${Array.isArray(f.keywords)?f.keywords.join(' '):f.keywords||''}`.toLocaleLowerCase().includes(query));
  const grid=$('fontGrid');grid.replaceChildren();
  $('fontCount').textContent=`${matches.length} ${matches.length===1?'font':'fonts'}`;
  for(const f of matches){
    const button=document.createElement('button');button.type='button';button.className='font-card';
    button.setAttribute('aria-label',`Choose ${f.name}`);button.setAttribute('aria-pressed',String(f.id===$('fontSelect').value));
    const image=document.createElement('img');image.src=f.preview||`/font-previews/${encodeURIComponent(f.id)}.png`;image.alt=`${f.name} embroidery preview`;image.loading='lazy';image.decoding='async';
    const caption=document.createElement('span');caption.className='font-card-caption';
    const name=document.createElement('strong');name.textContent=f.name;
    const detail=document.createElement('span');detail.className='font-card-detail';
    const lo=round(f.size*f.minScale/100),hi=round(f.size*f.maxScale/100);
    detail.textContent=(f.size?(lo===hi?`${lo} mm`:`${lo}–${hi} mm`):`${f.minScale}–${f.maxScale}%`)+(f.id===$('fontSelect').value?' · Selected':'');
    caption.append(name,detail);button.append(image,caption);
    button.onclick=()=>{$('fontSelect').value=f.id;updateFontInfo(true);$('fontDialog').close();};grid.append(button);
  }
  if(!matches.length){const empty=document.createElement('p');empty.className='caption';empty.textContent='No fonts match that search. Try a name or a style such as script, serif, or small.';grid.append(empty);}
}
$('fontPickerBtn').onclick=()=>{if(!fonts.length){toast('The font library is still loading. Try again in a moment.');return;}$('fontSearch').value='';renderFontPicker();$('fontDialog').showModal();};
$('fontSearch').oninput=renderFontPicker;
$('fontPickerFavorites').onchange=renderFontPicker;
$('manageFontsBtn').onclick=()=>fontLibrary.open($('fontSelect').value);
function openLettering(layer=null) {
  letterGeneration++;
  editTextId=layer?.id||null;const s=layer?.lettering;
  $('letterTitle').textContent=layer?'Edit your lettering.':'Make it yours.';
  $('letterText').value=s?.text||'';$('fontSelect').value=s?.font||(fonts.some(f=>f.id==='medium_font')?'medium_font':fonts[0]?.id);
  $('fontScale').value=s?.scale||80;$('textAlign').value=s?.align||'center';$('lineSpacing').value=s?.lineSpacing||0;$('letterSpacing').value=s?.letterSpacing||0;$('letterColor').value=layer?.color||'#203f38';
  $('wordSpacing').value=s?.wordSpacing||0;$('letterTrim').value=s?.trim||'line';$('letterColorSort').value=s?.colorSort||'off';$('letterCommandSymbols').checked=!!s?.commandSymbols;
  $('letterError').textContent='';$('letterSubmit').textContent=layer?'Update lettering':'Create lettering';$('letterSubmit').disabled=false;updateFontInfo();$('letterDialog').showModal();
  $('preserveFontColors').checked=!!layer?.preserveFontColors;$('letterColor').disabled=!!layer?.preserveFontColors;
}
$('preserveFontColors').onchange=e=>$('letterColor').disabled=e.target.checked;
$('letterForm').onsubmit=async e=>{
  e.preventDefault();const button=$('letterSubmit');if(button.disabled)return;
  const settings={text:$('letterText').value,font:$('fontSelect').value,scale:Number($('fontScale').value),align:$('textAlign').value,lineSpacing:Number($('lineSpacing').value),letterSpacing:Number($('letterSpacing').value),wordSpacing:Number($('wordSpacing').value),trim:$('letterTrim').value,colorSort:$('letterColorSort').value,commandSymbols:$('letterCommandSymbols').checked};
  const color=$('letterColor').value, preserveFontColors=$('preserveFontColors').checked, targetId=editTextId, projectId=project.id, generation=letterGeneration;
  button.disabled=true;button.textContent='Stitching lettering…';$('letterError').textContent='';
  try {
    const result=await api('/api/lettering',settings);textCache.set(textKey(result.settings),result);
    if(!$('letterDialog').open||generation!==letterGeneration)return;
    if(project.id!==projectId)throw new Error('The project changed. Add this lettering again.');
    if(result.width>hoop().w||result.height>hoop().h)throw new Error(`This lettering is ${round(result.width)} × ${round(result.height)} mm. Use fewer characters, a smaller font scale, or more lines to fit the ${hoop().short} mm hoop.`);
    mutate(()=>{let l=project.layers.find(l=>l.id===targetId);if(l){const cx=l.x+l.width/2,cy=l.y+l.height/2;Object.assign(l,{width:result.width,height:result.height,x:cx-result.width/2,y:cy-result.height/2,color,preserveFontColors,lettering:result.settings,name:result.settings.text.replace(/\n/g,' / ')});}else{l=newLayer('text',{name:result.settings.text.replace(/\n/g,' / '),lettering:result.settings,color,preserveFontColors,x:(hoop().w-result.width)/2,y:(hoop().h-result.height)/2,width:result.width,height:result.height});project.layers.push(l);}selected=new Set([l.id]);});
    $('letterDialog').close();setMode('select');setTab('layer');
  }catch(err){if(generation===letterGeneration&&$('letterDialog').open)$('letterError').textContent=err.message;}
  finally{if(generation===letterGeneration){button.disabled=false;button.textContent=targetId?'Update lettering':'Create lettering';}}
};
$('letterDialog').addEventListener('close',()=>letterGeneration++);
$('fontScale').oninput=()=>updateFontInfo();

function svgPoint(event) {const p=new DOMPoint(event.clientX,event.clientY);return p.matrixTransform($('canvas').getScreenCTM().inverse());}
function pinchView(original,anchor,rect,center,ratio) {
  const w=clamp(original.w*ratio,25,240),h=original.h*w/original.w;
  const scale=Math.min(rect.width/w,rect.height/h);
  return {w,h,
    x:anchor.x-(center.x-rect.x-(rect.width-w*scale)/2)/scale,
    y:anchor.y-(center.y-rect.y-(rect.height-h*scale)/2)/scale};
}
function setMode(next) {mode=next;$('selectTool').classList.toggle('active',next==='select');$('drawTool').classList.toggle('active',next==='draw');$('selectTool').setAttribute('aria-pressed',next==='select');$('drawTool').setAttribute('aria-pressed',next==='draw');if(next==='draw')tab='layer';renderAll();}
const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
$('canvas').addEventListener('pointerdown',e=>{
  stopViewTween();
  if(!penGate.down(e,performance.now()))return;
  if(e.pointerType==='pen'&&pointers.size){if(gesture?.before)project=gesture.before;gesture=null;pointers.clear();$('drawPreview').setAttribute('d','');renderCanvas();}
  if(e.button!==0)return;e.preventDefault();$('canvas').setPointerCapture(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(pointers.size===2){
    if(gesture?.changed && gesture.before) {project=gesture.before;renderCanvas();}
    const [a,b]=[...pointers.values()],center={x:(a.x+b.x)/2,y:(a.y+b.y)/2};gesture={kind:'pinch',distance:distance(a,b),anchor:svgPoint({clientX:center.x,clientY:center.y}),view:{...view}};return;
  }
  if(pointers.size>1)return;
  const p=svgPoint(e),resize=e.target.closest('[data-resize]'),target=e.target.closest('[data-layer]'),planTarget=e.target.closest('[data-stitch-plan]');
  if(mode==='draw'&&penControls.canDraw(e)){gesture={kind:'draw',pen:e.pointerType==='pen',points:[[p.x,p.y,e.pointerType==='pen'?clamp(e.pressure||.1,0,1):.5]],settings:penControls.get()};return;}
  if(mode==='draw'){gesture={kind:'pan',start:{x:e.clientX,y:e.clientY},view:{...view}};return;}
  if(planTarget){const plan=stitchPlans.hit(planTarget.dataset.stitchPlan);if(plan){gesture={kind:'stitch-plan',id:plan.id,start:p,x:plan.x||0,y:plan.y||0,before:copy(project),changed:false};selected.clear();renderCanvas();return;}}
  if(resize){const l=project.layers.find(l=>l.id===resize.dataset.resize);gesture={kind:'resize',id:l.id,start:p,before:copy(project),original:copy(l),changed:false};return;}
  if(target){const id=target.dataset.layer,l=project.layers.find(l=>l.id===id);if(l.locked)return;if(l.linkedHelper){selected=new Set([l.id]);gesture=null;setTab('layer');renderAll();return;}const members=l.groupId?project.layers.filter(p=>p.groupId===l.groupId):[l];if(multi){const remove=members.every(l=>selected.has(l.id));members.forEach(l=>remove?selected.delete(l.id):selected.add(l.id));renderAll();gesture=null;return;}if(!selected.has(id)){selected=new Set(members.map(l=>l.id));renderAll();}if(!editable()){gesture=null;return;}gesture={kind:'move',start:p,before:copy(project),origins:chosen().filter(l=>!l.linkedHelper).map(l=>({id:l.id,x:l.x,y:l.y})),changed:false};}
  else {if(!multi){selected.clear();renderAll();}gesture={kind:'pan',start:{x:e.clientX,y:e.clientY},view:{...view}};}
});
$('canvas').addEventListener('pointermove',e=>{
  if(!pointers.has(e.pointerId)||!gesture)return;e.preventDefault();pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(gesture.kind==='pinch'&&pointers.size===2){const[a,b]=[...pointers.values()],ratio=clamp(gesture.distance/Math.max(1,distance(a,b)),.2,4);view=pinchView(gesture.view,gesture.anchor,$('canvas').getBoundingClientRect(),{x:(a.x+b.x)/2,y:(a.y+b.y)/2},ratio);$('canvas').setAttribute('viewBox',`${view.x} ${view.y} ${view.w} ${view.h}`);renderSelection();return;}
  if(pointers.size>1)return;
  if(gesture.kind==='pan'){const rect=$('canvas').getBoundingClientRect(),unit=Math.max(view.w/rect.width,view.h/rect.height);view.x=gesture.view.x-(e.clientX-gesture.start.x)*unit;view.y=gesture.view.y-(e.clientY-gesture.start.y)*unit;$('canvas').setAttribute('viewBox',`${view.x} ${view.y} ${view.w} ${view.h}`);return;}
  const p=svgPoint(e);
  if(gesture.kind==='stitch-plan'){const plan=project.stitchPlans?.find(p=>p.id===gesture.id);if(!plan)return;const dx=p.x-gesture.start.x,dy=p.y-gesture.start.y;if(Math.hypot(dx,dy)<.2&&!gesture.changed)return;plan.x=clamp(gesture.x+dx,-1000,1000);plan.y=clamp(gesture.y+dy,-1000,1000);gesture.changed=true;renderCanvas();return;}
  if(gesture.kind==='draw'){const events=e.getCoalescedEvents?.()||[];for(const sample of events.length?events:[e]){const q=svgPoint(sample),last=gesture.points.at(-1);if(Math.hypot(q.x-last[0],q.y-last[1])>.08&&gesture.points.length<4000)gesture.points.push([clamp(q.x,0,hoop().w),clamp(q.y,0,hoop().h),gesture.pen?clamp(sample.pressure||.1,0,1):.5]);}$('drawPreview').setAttribute('d',gesture.points.map((p,i)=>`${i?'L':'M'}${p[0]} ${p[1]}`).join(' '));return;}
  if(gesture.kind==='move'){let dx=p.x-gesture.start.x,dy=p.y-gesture.start.y;if(Math.hypot(dx,dy)<.2&&!gesture.changed)return;gesture.changed=true;[dx,dy]=snappedMove(project,gesture.origins,dx,dy);for(const start of gesture.origins){const l=project.layers.find(l=>l.id===start.id);l.x=start.x+dx;l.y=start.y+dy;}renderCanvas();return;}
  if(gesture.kind==='resize'){const l=project.layers.find(l=>l.id===gesture.id),o=gesture.original;const angle=-(o.rotation||0)*Math.PI/180,dx=p.x-gesture.start.x,dy=p.y-gesture.start.y;const localX=dx*Math.cos(angle)-dy*Math.sin(angle),localY=dx*Math.sin(angle)+dy*Math.cos(angle);const locked=l.aspectLock!==false;const minWidth=locked?Math.max(.2,.2*o.width/o.height):.2,maxWidth=locked?Math.min(hoopMax(),hoopMax()*o.width/o.height):hoopMax();l.width=clamp(round(o.width+localX),minWidth,maxWidth);l.height=locked?round(o.height*l.width/o.width):clamp(round(o.height+localY),.2,hoopMax());const dw=l.width-o.width,dh=l.height-o.height,cos=Math.cos(-angle),sin=Math.sin(-angle);l.x=o.x+(-dw+dw*cos-dh*sin)/2;l.y=o.y+(-dh+dw*sin+dh*cos)/2;gesture.changed=true;renderCanvas();}
});
function endPointer(e,cancel=false){
  penGate.end(e,performance.now());if(!pointers.has(e.pointerId))return;
  pointers.delete(e.pointerId);if(!gesture)return;if(gesture.kind==='pinch'){if(pointers.size===0)gesture=null;return;}
  if(cancel){if(gesture.before)project=gesture.before;$('drawPreview').setAttribute('d','');gesture=null;renderAll();return;}
  if(gesture.kind==='draw'){const {points,settings}=gesture;$('drawPreview').setAttribute('d','');gesture=null;const layer=makeStroke(points,settings,newLayer('path'));if(!layer)return;if(layer.width>hoop().w||layer.height>hoop().h){toast('This stroke exceeds the hoop. Draw a smaller stroke.');return;}canvasMotion.quiet();addLayer(layer);if(!settings.keepDrawing)setMode('select');return;}
  if(gesture.changed){history.push(gesture.before);if(history.length>60)history.shift();future=[];changed();}gesture=null;renderAll();
}
$('canvas').addEventListener('pointerup',e=>endPointer(e));$('canvas').addEventListener('pointercancel',e=>endPointer(e,true));
$('canvas').addEventListener('wheel',e=>{e.preventDefault();stopViewTween();zoom(e.deltaY>0?1.12:.89);},{passive:false});
function zoom(factor,animated=false){const w=clamp(view.w*factor,25,240),next={x:view.x+(view.w-w)/2,y:view.y+(view.h-w)/2,w,h:w};if(animated)animateView(next);else{view=next;renderCanvas();}}
// Zoom/fit buttons glide the view; pinch and wheel stay 1:1. Only the viewBox
// moves during the glide; the full canvas render runs once at the end.
let viewTween=0,shownView=null;
function animateView(target){
  const from=viewTween?shownView:{...view};cancelAnimationFrame(viewTween);view=target;
  if(prefersReducedMotion()){viewTween=0;renderCanvas();return;}
  const t0=performance.now(),ms=260;
  const step=now=>{const k=Math.min(1,(now-t0)/ms),e=1-Math.pow(1-k,4);shownView={x:from.x+(target.x-from.x)*e,y:from.y+(target.y-from.y)*e,w:from.w+(target.w-from.w)*e,h:from.h+(target.h-from.h)*e};$('canvas').setAttribute('viewBox',`${shownView.x} ${shownView.y} ${shownView.w} ${shownView.h}`);if(k<1)viewTween=requestAnimationFrame(step);else{viewTween=0;renderCanvas();}};
  viewTween=requestAnimationFrame(step);
}
function stopViewTween(){if(!viewTween)return;cancelAnimationFrame(viewTween);viewTween=0;view={...shownView};renderCanvas();}

async function hydrate() {
  linked.changed();
  const projectId=project.id;
  const pending=[...project.layers],known=new Set(fonts.map(f=>f.id));let missingFont=false;
  while(pending.length){const l=pending.pop();if(l.type==='text'&&!known.has(l.lettering?.font))missingFont=true;for(const key of ['textLayer','guideLayer'])if(l.curveSource?.[key])pending.push(l.curveSource[key]);}
  if(missingFont)try{fonts=(await api('/api/fonts')).sort((a,b)=>a.name.localeCompare(b.name));}catch(e){toast('Could not refresh the font library: '+e.message);}
  for(const l of project.layers){try{let loaded=false;if(l.type==='text'&&!textCache.has(textKey(l.lettering))){const r=await api('/api/lettering',l.lettering);textCache.set(textKey(r.settings),r);loaded=true;}if(l.type==='import'&&!assets.has(l.asset)){const r=await api('/api/assets/'+l.asset);assets.set(l.asset,r);loaded=true;}if(loaded&&project.id===projectId)renderCanvas();}catch(e){toast(`Could not restore ${l.name}: ${e.message}`);}}
}
async function importFile(file) {
  try {
    if(/\.(png|jpe?g|hei[cf]s?|hif|webp|gif|bmp|tiff?)$/i.test(file.name)){await references.importFile(file);return;}
    if(file.size>12*1024*1024)throw new Error('Import a project smaller than 12 MB, or embroidery file smaller than 4 MB.');
    if(!/\.(svg|json)$/i.test(file.name)){if(file.size>4*1024*1024)throw new Error('Import an embroidery file smaller than 4 MB.');toast('Reading embroidery stitches…');const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));const result=await api('/api/import-embroidery',{name:file.name,data:btoa(binary)}),r=result.asset;assets.set(r.key,r);const scale=Math.min(1,90/r.width,90/r.height),w=r.width*scale,h=r.height*scale;addLayer(newLayer('import',{name:file.name,asset:r.key,x:(hoop().w-w)/2,y:(hoop().h-h)/2,width:w,height:h,stitch:'original',recolor:false}),Object.fromEntries(result.preview.threads.map(t=>[t.color.toLowerCase(),{name:t.name,number:t.number,brand:t.brand}])));toast(result.note);return;}
    const text=await file.text();
    if(file.name.toLowerCase().endsWith('.json')){const backup=JSON.parse(text);let orderWarning='';await switchProject(async()=>{const p=await api('/api/restore',{project:backup});validateProject(p);orderWarning=[await restoreOrderDisplay(backup,p,api),await restoreDensityMap(backup,p,api),await restoreTroubleshoot(backup,p,api)].filter(Boolean).join(' ');return p;});toast(orderWarning||'Project and embedded artwork restored.');}
    else {toast('Reading SVG paths…');const r=await api('/api/import',{name:file.name,svg:text});assets.set(r.key,r);const scale=r.placement?1:Math.min(1,90/r.width,90/r.height),w=r.width*scale,h=r.height*scale;const imported=newLayer('import',{name:file.name.replace(/\.svg$/i,''),asset:r.key,x:r.placement?.x??(hoop().w-w)/2,y:r.placement?.y??(hoop().h-h)/2,width:w,height:h,stitch:'original',recolor:false});addLayer(imported,null,r.embroiderySettings,r.crossGrids);if(r.svgUpdate?.offer)offerLegacyUpdate(file.name,text,imported.id);else if(r.svgUpdate)toast(`Updated stitch settings saved by ${r.svgUpdate.label} to the current Ink/Stitch format.`);}
  }catch(e){toast(e.message);}
}
function validateProject(p){
  if(!p||p.version!==1||!Array.isArray(p.layers)||p.layers.length>MAX_LAYERS||typeof p.id!=='string'||!/^#[\da-f]{6}$/i.test(p.fabric))throw new Error('This is not an Ink Studio project.');
  p.embroiderySettings=documentSettings(p.embroiderySettings);
  validateOrderDisplay(p.orderDisplay);
  validateDensityMap(p.densityMap);
  validateTroubleshoot(p.troubleshootDisplay);
  if(p.crossGrids)p.crossGrids=crossGrids(p.crossGrids);
  for(const l of p.layers){if(!['text','rectangle','ellipse','path','import','image'].includes(l.type)||!/^#[\da-f]{6}$/i.test(l.color)||![l.x,l.y,l.width,l.height].every(Number.isFinite)||typeof l.id!=='string'||!/^[\w-]{1,80}$/.test(l.id))throw new Error('This project contains an invalid layer.');if(l.type==='text'&&(!l.lettering||typeof l.lettering.text!=='string'))throw new Error('This project contains invalid lettering.');}
}

// Unversioned SVGs with Ink/Stitch settings may predate Ink/Stitch 3.0.
// Desktop asks before converting them; so do we. Undo restores the original.
function offerLegacyUpdate(name,svg,layerId){
  let d=$('legacyUpdateDialog');
  if(!d){document.body.insertAdjacentHTML('beforeend',`<dialog id="legacyUpdateDialog" class="legacy-update-dialog" aria-labelledby="legacyUpdateTitle"><div class="dialog-heading"><div><span class="eyebrow">OLDER INK/STITCH FILE?</span><h2 id="legacyUpdateTitle">Update its stitch settings?</h2></div></div><p>This SVG has Ink/Stitch settings but no version number, so it may come from Ink/Stitch 2.x or earlier. Updating converts old settings the same way desktop Ink/Stitch does. Keep it as is if the file came from a current version.</p><div class="dialog-footer"><button id="legacyKeep">Keep as is</button><button id="legacyUpdate" class="primary">Update settings</button></div></dialog>`);d=$('legacyUpdateDialog');}
  $('legacyKeep').onclick=()=>d.close();
  $('legacyUpdate').onclick=async()=>{d.close();try{const r=await api('/api/import',{name,svg,updateFrom:0});assets.set(r.key,r);if(!project.layers.some(l=>l.id===layerId)){toast('The imported layer was removed.');return;}mutate(()=>{project.layers.find(l=>l.id===layerId).asset=r.key;});toast('Updated older Ink/Stitch settings. Undo restores the original.');}catch(e){toast(e.message);}};
  d.showModal();
}

// The stitch-order list is pinned under the settings on wide layouts; its
// header collapses it to give the settings more room (remembered per browser).
function layerListToggle(){
  const section=document.querySelector('.layers-section'),title=section?.querySelector('.section-title');if(!title||title.dataset.toggle)return;
  title.dataset.toggle='1';title.setAttribute('role','button');title.tabIndex=0;
  const apply=c=>{section.classList.toggle('collapsed',c);title.setAttribute('aria-expanded',String(!c));};
  let c=false;try{c=localStorage.getItem('inkstudio-layers-collapsed')==='1';}catch{}apply(c);
  const flip=()=>{c=!section.classList.contains('collapsed');apply(c);if(!c)for(const el of section.querySelectorAll(':scope>.layers,:scope>.caption'))reveal(el);try{localStorage.setItem('inkstudio-layers-collapsed',c?'1':'0');}catch{}};
  title.onclick=flip;title.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();flip();}};
}

async function switchProject(load,{saved=false,resetHistory=false,persist=false,selectAll=false,nextTab=null}={}){
  await projectTransitions.run(async()=>{const next=await load();validateProject(next);return next;},async next=>{
    if(resetHistory){history=[];future=[];}else checkpoint();
    project=next;selected=selectAll?new Set(next.layers.filter(l=>l.visible!==false).map(l=>l.id)):new Set();changed();
    if(saved){clearTimeout(saveTimer);dirty=false;saveRevision=modelRevision;$('saveState').dataset.state='saved';$('saveState').textContent='Saved in Studio';}
    await hydrate();if(persist)await saveProject(false,true);
    $('projectsDialog').close();if(nextTab)setTab(nextTab);
  });
}
let projectListGeneration=0;
async function openProjects(){
  const generation=++projectListGeneration;
  $('projectsDialog').showModal();$('projectList').textContent='Loading projects…';
  try{const list=await api('/api/projects');if(generation!==projectListGeneration||!$('projectsDialog').open)return;$('projectList').replaceChildren();const examples=document.createElement('div');examples.className='project-examples-list';for(const p of list){const b=document.createElement('button');b.className='project-card';const name=document.createElement('span');name.textContent=p.name||'Untitled';const date=document.createElement('small');date.textContent=new Date(p.updated*1000).toLocaleDateString();b.append(name,date);b.onclick=async()=>{try{await switchProject(()=>api('/api/projects/'+p.id),{saved:true,resetHistory:true});}catch(e){toast(e.message);}};(p.example?examples:$('projectList')).append(b);}const own=list.filter(p=>!p.example).length;if(!own){const empty=document.createElement('p');empty.className='caption';empty.textContent='Save your first project to keep it here.';$('projectList').append(empty);}if(examples.children.length){const d=document.createElement('details');d.className='project-examples';const s=document.createElement('summary');s.textContent=`Examples & test designs (${examples.children.length})`;d.append(s,examples);$('projectList').append(d);}}catch(e){if(generation===projectListGeneration&&$('projectsDialog').open)$('projectList').textContent=e.message;}
}
const simulator=createSimulator({preview:scope=>preview(scope)});
async function preview(scope='all'){
  let snapshot=copy(project);const ids=chosen().filter(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork')).map(l=>l.id);
  try{if(scope==='selection'){snapshot=selectionProject(snapshot,ids);snapshot.id=uid();}}catch(e){toast(e.message);return;}
  if(!project.layers.some(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork'))){toast('Add a visible stitched layer first. Reference images and helpers do not sew.');return;}
  simulator.stop();simulator.scope(scope,ids.length,true);if(!$('previewDialog').open)$('previewDialog').showModal();$('previewContent').hidden=true;$('previewStatus').hidden=false;$('previewStatus').textContent='Building editable artwork…';
  const request=previewTask.begin({projectId:project.id,revision:modelRevision,scope});
  try {
    await saveProject(false);if(!request.current())return;const {id}=await api('/api/export',{project:snapshot});
    while(request.current()){const job=await api('/api/jobs/'+id);if(!request.current())return;$('previewStatus').textContent=job.message;if(job.state==='error')throw new Error(job.message);if(job.state==='done'){lastExport=job.result;lastExportFabric=snapshot.fabric;showPreview();request.succeed();break;}if(!['queued','working'].includes(job.state))throw new Error('Preview stopped unexpectedly. Generate the preview again.');await new Promise(r=>setTimeout(r,900));}
  }catch(e){if(request.fail(e)){lastExport=null;$('previewContent').hidden=true;$('previewStatus').hidden=false;$('previewStatus').textContent=e.message;}}
  finally{if(request.current())simulator.scope(scope,ids.length,false);}
}
function showPreview(){
  const p=lastExport.preview;$('previewStatus').hidden=true;$('previewContent').hidden=false;
  $('downloadThreads').href=lastExport.threadlist;$('printSheet').href=lastExport.print;$('formatDownload').hidden=true;
  const cut=!!lastExport.cutwork;$('downloadPes').hidden=cut;$('openRespira').hidden=cut||!respiraUrl;$('downloadCutwork').hidden=!cut;$('downloadCutwork').href=lastExport.cutworkBundle||'';
  $('exportWorkflowNote').textContent=cut?'Cutwork: download and unzip the EXP + INF bundle. Keep both files with the same name. This requires compatible cutting needles and is not a PP1 PES workflow.':respiraUrl?'On the iPad, download the PES, then open Respira in Bluefy and choose that file for the PP1.':'Download the machine file, then transfer it using your embroidery machine’s supported method.';
  {let note=$('manualSnipNote');if(!note){note=document.createElement('p');note.id='manualSnipNote';note.className='cut-warning';note.setAttribute('role','note');$('exportWorkflowNote').before(note);}const m=lastExport.manualSnips;note.hidden=!m?.accepted;note.replaceChildren();if(m?.accepted){const text=document.createElement('strong');text.textContent=`Manual finish required: trim ${m.floatCount} marked cream floats at BOTH ENDS after sewing. `;const a=document.createElement('a');a.id='downloadSnipGuide';a.className='button';a.href=lastExport.manualSnipGuide;a.textContent='Download numbered snip map';a.download='';note.append(text,a);}}
  for(const option of $('exportFormat').options)option.disabled=cut&&!['exp','inf','zip','png','png-realistic','svg','txt'].includes(option.value);if(cut)$('exportFormat').value='zip';
  exportOptions.refresh();
  // Same limits as native/sewing_quality.py (80 cuts or 6 per 1,000 stitches).
  {let w=$('exportCutWarning');if(!w){w=document.createElement('p');w.id='exportCutWarning';w.className='cut-warning';w.setAttribute('role','note');document.querySelector('.download-actions').before(w);}
   const heavy=p.trims>80||p.trims*1000/Math.max(1,p.stitches)>6;w.hidden=!heavy;let sum=$('exportSummary');if(!sum){sum=document.createElement('p');sum.id='exportSummary';sum.className='export-summary';w.before(sum);}sum.textContent=`${round(p.width)} × ${round(p.height)} mm · ${p.stitches.toLocaleString()} stitches · ${new Set(p.threads.map(t=>t.color)).size} colors · ${p.trims} cuts${p.stops?` · ${p.stops} stop${p.stops===1?'':'s'}`:''}`;w.innerHTML=heavy?`<strong>Many thread cuts (${p.trims}).</strong> Frequent cuts can make the PP1 fray the thread. Check → Check design &amp; density lists the small pieces causing them.`:'';}
  $('downloadPes').href=lastExport.pes;$('downloadSvg').href=lastExport.svg;$('downloadProject').href=lastExport.project;
  $('stitchStats').innerHTML=`<div class="stat-row"><span>Finished size</span><strong>${round(p.width)} × ${round(p.height)} mm</strong></div><div class="stat-row"><span>Stitches</span><strong>${p.stitches.toLocaleString()}</strong></div><div class="stat-row"><span>Colors / thread steps</span><strong>${new Set(p.threads.map(t=>t.color)).size} / ${p.threads.length}</strong></div><div class="stat-row"><span>Trims / jumps</span><strong>${p.trims} / ${p.jumps}</strong></div><div class="stat-row"><span>Extra stops / color changes</span><strong>${p.stops||0} / ${p.colorChanges??Math.max(0,p.threads.length-1)}</strong></div>`;
  $('threadList').innerHTML='<h3>Thread order</h3>'+p.threads.map((t,i)=>`<div class="thread-item"><span style="background:${escape(t.color)}"></span><div>${i+1}. ${escape(t.name)}<br><small>${escape([t.brand,t.number,t.color].filter(Boolean).join(' · '))}</small></div></div>`).join('');
  simulator.load(p,lastExportFabric);
  if(!previewTask.pending)previewTask.begin().succeed();
}
$('previewDialog').addEventListener('close',()=>{simulator.stop();previewTask.cancel();});
$('projectsDialog').addEventListener('close',()=>projectListGeneration++);

document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>setTab(b.dataset.tab));
$('selectTool').onclick=()=>setMode('select');$('drawTool').onclick=()=>{setMode(mode==='draw'?'select':'draw');if(mode==='draw')toast('Draw a path on the hoop. Choose fill or an outline in Layer.');};
$('digitizeTool').onclick=()=>{setMode('select');setTab('digitize');};
$('patchTool').onclick=()=>components.open();
$('sceneTool').onclick=()=>scenes.open();
$('textTool').onclick=()=>openLettering();$('emptyTextBtn').onclick=()=>openLettering();
$('rectTool').onclick=()=>{setMode('select');addLayer(newLayer('rectangle'));};$('ellipseTool').onclick=()=>{setMode('select');addLayer(newLayer('ellipse',{name:'Ellipse',width:30,height:30,x:35,y:35}));};
$('undoBtn').onclick=undo;$('redoBtn').onclick=redo;$('saveBtn').onclick=()=>saveProject();$('projectsBtn').onclick=openProjects;$('previewBtn').onclick=()=>preview();$('helpBtn').onclick=()=>$('helpDialog').showModal();
$('importTool').onclick=()=>$('importInput').click();$('importInput').onchange=e=>{if(e.target.files[0])importFile(e.target.files[0]);e.target.value='';};
let editingProjectName=false;
$('projectName').oninput=e=>{if(!editingProjectName){checkpoint();editingProjectName=true;}project.name=e.target.value.trim()||'Untitled design';changed(false);};
$('projectName').onblur=()=>editingProjectName=false;
$('multiBtn').onclick=()=>{multi=!multi;$('multiBtn').setAttribute('aria-pressed',multi);$('multiBtn').textContent=multi?'Done selecting':'Select multiple';if(multi)setTab('arrange');};
$('zoomOut').onclick=()=>zoom(1.2,true);$('zoomIn').onclick=()=>zoom(1/1.2,true);$('fitBtn').onclick=()=>animateView(hoopView());
$('fitDesignBtn').onclick=()=>{const visible=project.layers.filter(l=>l.visible!==false&&(!l.role||l.role==='artwork')),stitched=visible.filter(l=>l.type!=='image');const b=groupBounds(stitched.length?stitched:visible);if(!b)return;const size=clamp(Math.max(b.w,b.h)+12,25,240);animateView({x:b.x+(b.w-size)/2,y:b.y+(b.h-size)/2,w:size,h:size});};
$('saveCopyBtn').onclick=async()=>{try{await switchProject(()=>({...copy(project),id:uid(),name:project.name+' copy'}),{persist:true});toast('A separate copy is saved in Studio.');}catch(e){toast(e.message);}};
$('backupBtn').onclick=async()=>{try{const backup=await api('/api/backup',{project:copy(project)}),url=URL.createObjectURL(new Blob([JSON.stringify(backup,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=(project.name.replace(/[^a-z0-9_-]+/gi,'-')||'design')+'.project.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(e){toast(e.message);}};
$('newProjectBtn').onclick=async()=>{try{await switchProject(async()=>blankProject((await api('/api/preferences')).defaults),{resetHistory:true,nextTab:'layer'});}catch(e){toast(e.message);}};
document.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)||document.querySelector('dialog[open]'))return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.shiftKey?redo():undo();}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();saveProject();}if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();deleteSelected();}if(e.key==='Escape'){selected.clear();setMode('select');renderAll();}});
window.addEventListener('pagehide',()=>{if(dirty){try{localStorage.setItem('inkstudio-project-v1',JSON.stringify(project));}catch{}}});

async function start(){
  try{
    const health=await api('/api/health'),link=$('desktopStudioLink');
    if(link&&health.runtime?.desktopUrl){const url=new URL(health.runtime.desktopUrl);if(['http:','https:'].includes(url.protocol)){link.href=url.href;link.hidden=false;}}
    if(health.runtime?.respiraUrl){const url=new URL(health.runtime.respiraUrl);if(['http:','https:'].includes(url.protocol)){respiraUrl=url.href;$('openRespira').href=respiraUrl;}}
  }catch{}

  let restored=false;
  try{const stored=localStorage.getItem('inkstudio-project-v1');if(stored){const p=JSON.parse(stored);validateProject(p);project=p;restored=true;}}catch{toast('The previous browser draft could not be restored. Saved projects are available under Projects.');}
  if(!restored){const id=project.id,revision=modelRevision;try{const defaults=await api('/api/preferences');if(project.id===id&&modelRevision===revision)project.embroiderySettings=documentSettings(defaults.defaults);}catch(e){toast('Using factory preferences: '+e.message);}}
  renderAll();
  installInterfaceMotion(); // after the first paint, so loading doesn't animate everything
  try{fonts=(await api('/api/fonts')).sort((a,b)=>a.name.localeCompare(b.name));await hydrate();}
  catch(e){toast(e.message);}
}
installKeywordChips();
// Group long tool lists into searchable sections after every panel render.
{const plain=renderProperties;renderProperties=function(){plain();if(!(mode==='draw'&&tab==='layer'))organizeTools($('properties'),tab);toolFinder?.capturePanel($('properties'),mode==='draw'?'draw':tab);selectionShelf?.render();};}
const exportOptions=createExportOptions({api,getExport:()=>lastExport,toast});
const printWorkspace=createPrintWorkspace({api,getProject:()=>project,apply:async(settings,projectId)=>{if(project.id!==projectId)throw new Error('Settings saved with the export. Open its original design to save them there too.');const exported=lastExport;mutate(()=>project.printSettings=settings);lastExport=exported;await saveProject(false,true);}});
$('printSheet').onclick=e=>{e.preventDefault();if(lastExport){simulator.stop();printWorkspace.open(lastExport.id);}};
api('/api/formats').then(f=>{$('exportFormat').innerHTML=f.outputs.map(o=>`<option value="${o.key}">${escape(o.label)}</option>`).join('');$('exportFormat').value='dst';exportOptions.formats(f);$('importInput').accept=['.svg','.json','.png','.jpg','.jpeg','.heic','.heif','.hif','.webp','.gif','.bmp','.tif','.tiff',...f.inputs.map(x=>'.'+x)].join(',');}).catch(e=>toast(e.message));
const penControls=createPenControls({finish:()=>setMode('select')});
const linked=createLinked({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,setTab,deleteSelected,setColor:setLayerColor,checkpoint,changed,render:()=>{renderCanvas();renderLayers();},select:ids=>selected=new Set(ids),resolved:()=>{changed(false,false);renderCanvas();renderLayers();hydrateLinkedText();}});
async function hydrateLinkedText(){for(const l of project.layers.filter(l=>l.link&&l.type==='text'))if(!textCache.has(textKey(l.lettering))){try{const r=await api('/api/lettering',l.lettering);textCache.set(textKey(r.settings),r);renderCanvas();}catch(e){toast(e.message);}}}
const svgPrepTools=createSvgPreparation({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,assets,select:ids=>selected=new Set(ids),setTab});
const stitchPlans=createStitchPlans({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,assets,select:ids=>selected=new Set(ids),setTab,render:renderCanvas,setView:next=>{view=next;renderCanvas();}});
const elementInfo=createElementInfo({getProject:()=>project,getRevision:()=>modelRevision,chosen,api,toast,select:ids=>selected=new Set(ids),setTab,render:renderAll});
const troubleshooting=createTroubleshoot({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,artwork:()=>$('artwork'),select:ids=>selected=new Set(ids),setTab,render:renderAll,setView:next=>{view=next;renderCanvas();}});
const densityMaps=createDensityMap({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,artwork:()=>$('artwork')});
const orderNumbers=createStackingOrder({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,artwork:()=>$('artwork')});
const crossTools=createCrossStitch({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,select:ids=>selected=new Set(ids),setTab});
const references=createReferences({getProject:()=>project,getRevision:()=>modelRevision,mutate,api,toast,checkpoint,changed,renderCanvas,renderLayers,select:ids=>selected=new Set(ids),setTab,cross:layer=>crossTools.open([layer]),draw:()=>setMode('draw'),add:props=>addLayer(newLayer('image',props))});
const components=createComponents({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,select:ids=>selected=new Set(ids),setTab});
const merrowControls=createMerrow({api,toast,getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,select:ids=>selected=new Set(ids),setTab,editComponent:kind=>components.open(kind,true)});
const streamlineControls=createStreamlines({api,toast,getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,select:ids=>selected=new Set(ids),setTab});
const featherControls=createFeather({api,toast,getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,select:ids=>selected=new Set(ids),setTab});
const sewingOptimizer=createSewingOptimizer({api,toast,getProject:()=>project,getRevision:()=>modelRevision,mutate});
const scenes=createScenes({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,select:ids=>selected=new Set(ids),setTab,penInput:penControls});
const commands=createCommands({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,artwork:()=>$('artwork'),render:renderAll,penInput:penControls});
const helpers=createHelpers({openMarkerDisplay:()=>commands.openMarkerDisplay(),getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,toast,select:ids=>selected=new Set(ids)});
const specialFills=createSpecialFills({getProject:()=>project,getRevision:()=>modelRevision,mutate,toast});
const multisatin=createMultisatin({getProject:()=>project,getRevision:()=>modelRevision,mutate,toast,api});
const threads=createThreads({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,editable,assets,select:ids=>selected=new Set(ids),setTab});
const swatchTools=createSwatches({getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,assets,select:ids=>selected=new Set(ids),setTab,createProject:p=>switchProject(()=>p,{persist:true,selectAll:true})});
const batchTools=createBatches({api,toast,getProject:()=>project,openProject:p=>switchProject(()=>p,{persist:true,nextTab:'digitize'})});
const fontSamples=createFontSamples({api,toast,getProject:()=>project,openProject:p=>switchProject(()=>p,{persist:true,nextTab:'digitize'})});
const fontWorkspaces=createFontWorkspaces({api,toast,getProject:()=>project,getRevision:()=>modelRevision,mutate,assets,setTab,refreshFonts:async()=>{fonts=(await api('/api/fonts')).sort((a,b)=>a.name.localeCompare(b.name));},openLibrary:id=>fontLibrary.open(id),openProject:p=>switchProject(()=>p,{persist:true,nextTab:'digitize'})});
const fontLibrary=createFontLibrary({getFonts:()=>fonts,api,toast,sampleFont:id=>fontSamples.open(id),editFont:id=>fontWorkspaces.open(id),refreshFonts:async()=>{fonts=(await api('/api/fonts')).sort((a,b)=>a.name.localeCompare(b.name));if($('fontDialog').open)renderFontPicker();},useFont:id=>{if(!$('letterDialog').open)openLettering();$('fontSelect').value=id;updateFontInfo(true);if($('fontDialog').open)$('fontDialog').close();}});
const ttfLettering=createTTFLettering({api,toast,getProject:()=>project,getRevision:()=>modelRevision,mutate,assets,select:ids=>selected=new Set(ids),setTab});
function useOutlineLettering(){
  const layer=project.layers.find(l=>l.id===editTextId)||null,initial={text:$('letterText').value,color:$('letterColor').value,onCancel:()=>$('letterDialog').showModal()};
  if($('fontDialog').open)$('fontDialog').close();$('letterDialog').close();ttfLettering.open(layer,initial);
}
$('ttfLetteringBtn').onclick=useOutlineLettering;
{const button=document.createElement('button');button.id='ttfFromFontPicker';button.type='button';button.textContent='Use a TTF/OTF font';button.onclick=useOutlineLettering;($('fontDialog').querySelector('.dialog-footer')||$('fontDialog')).append(button);}
const operations=createOperations({assets,getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,select:ids=>selected=new Set(ids),setTab,editable});
const selectionTools=createSelection({openOrderNumbers:()=>orderNumbers.open(),getProject:()=>project,getRevision:()=>modelRevision,selectionIds:()=>[...selected],mutate,api,toast,select:ids=>selected=new Set(ids),setTab,render:renderAll,startSequence:()=>{selected.clear();multi=true;$('multiBtn').setAttribute('aria-pressed','true');$('multiBtn').textContent='Done selecting';setMode('select');setTab('arrange');renderAll();toast('Tap artwork or layer rows in sewing order, then open Stitch in selection order.');}});
const advanced=createAdvanced({openElementInfo:()=>elementInfo.open(),openDensityMap:()=>densityMaps.open(),openTroubleshoot:()=>troubleshooting.open(),getProject:()=>project,getRevision:()=>modelRevision,chosen,mutate,api,toast,select:ids=>selected=new Set(ids),setTab,editable});
const preferenceTools=createPreferences({getProject:()=>project,getRevision:()=>modelRevision,mutate,api,toast,assets});
const digitizer=createDigitizer({openOperation:key=>operations.open(key),getProject:()=>project,getRevision:()=>modelRevision,chosen,single,mutate,api,toast,addLayer,newLayer,select:ids=>selected=new Set(ids),render:renderAll,setTab,assets,editable,mountExtras:host=>{stitchPlans.mount(host);orderNumbers.mount(host);elementInfo.mount(host);densityMaps.mount(host);troubleshooting.mount(host);preferenceTools.mount(host);crossTools.mount(host);svgPrepTools.mount(host);if(single()?.type==='image'){references.mount(host,single());return;}advanced.mountDigitize(host);operations.mount(host);helpers.mount(host);commands.mount(host);threads.mount(host);merrowControls.mount(host);streamlineControls.mount(host);featherControls.mount(host);sewingOptimizer.mount(host);swatchTools.mount(host);fontLibrary.mount(host);ttfLettering.mount(host);fontSamples.mount(host);fontWorkspaces.mount(host);batchTools.mount(host);},penInput:penControls});
$('checkTool').onclick=advanced.openCheck;
const finderPanel=next=>{setMode('select');setTab(next);};
const finderButton=(id,next='digitize')=>{finderPanel(next);const button=$(id);if(!button||button.disabled)throw new Error('Select compatible artwork to use this tool.');return button.onclick?.call(button,new MouseEvent('click',{cancelable:true}));};
toolFinder=createToolFinder({api,toast,getState:()=>({project,selection:chosen(),hasPreview:!!lastExport}),openOperation:key=>operations.open(key),routes:createFinderRoutes({
  layer:()=>finderPanel('layer'),arrange:()=>finderPanel('arrange'),fabric:()=>finderPanel('fabric'),digitize:()=>finderPanel('digitize'),
  draw:()=>setMode('draw'),lettering:()=>openLettering(),'edit-lettering':()=>openLettering(single()),ttf:()=>ttfLettering.open(single()?.ttfLettering?single():null),
  fonts:()=>fontLibrary.open(),'font-samples':()=>fontSamples.open(),'font-workspace':()=>fontWorkspaces.open(),batches:()=>batchTools.open(),
  nodes:()=>digitizer.editNodes(single()),'new-path':()=>digitizer.editNodes(),'new-satin':()=>digitizer.newSatin(),'curved-text':()=>finderButton('curveLettering'),
  trace:()=>references.openTrace(single()),regions:()=>finderButton('clickStitchReference','layer'),cross:()=>crossTools.open(),svg:()=>svgPrepTools.open(),
  advanced:()=>advanced.open(single()),operations:()=>operations.open(),helpers:()=>helpers.open(),commands:()=>commands.open(),
  'satin-route':()=>finderButton('routeSatin'),'running-route':()=>finderButton('routeRunning'),'optimize-sewing':()=>sewingOptimizer.open(),threads:()=>threads.open(),
  'thread-order':()=>finderButton('openThreadOrder'),palette:()=>finderButton('createThreadPalette'),swatches:()=>swatchTools.open(),
  patches:()=>components.open(),merrow:()=>merrowControls.open(),streamlines:()=>streamlineControls.open(),wave:()=>streamlineControls.open(single(),'wave_fill'),feather:()=>featherControls.open(),scene:()=>scenes.open(),check:()=>advanced.openCheck(),density:()=>densityMaps.open(),troubleshoot:()=>troubleshooting.open(),
  info:()=>elementInfo.open(),'order-numbers':()=>orderNumbers.open(),'stitch-plan':()=>stitchPlans.open(),'select-stitches':()=>selectionTools.openFind(),'stitch-order':()=>selectionTools.openOrder(),
  preferences:()=>preferenceTools.open(),defaults:async()=>{await preferenceTools.open();$('defaultPreferencesTab').click();},
  cleanup:()=>finderButton('openDocumentCleanup'),projects:()=>openProjects(),guide:()=>$('helpDialog').showModal(),
  preview:()=>{if(!lastExport)throw new Error('Generate Preview & export first.');$('previewDialog').showModal();showPreview();},
  print:()=>{if(!lastExport)throw new Error('Generate Preview & export first.');return printWorkspace.open(lastExport.id);},
})});
const editShelfSetting=createShelfSettings({getProject:()=>project,getRevision:()=>modelRevision,api,textCache,textKey,assets,hydrateLinkedText,commit:(fn,layer)=>{
  checkpoint();fn();changed(false);layer=project.layers.find(l=>l.id===layer.id)||layer;renderCanvas();
  const currentLayers=new Map(project.layers.map(l=>[l.id,l]));
  for(const button of $('layers').querySelectorAll('.layer-main')){const current=currentLayers.get(button.dataset.layerId);if(current){button.querySelector('.layer-dot').style.backgroundColor=current.color;button.querySelector('small').textContent=layerDescription(current);}}
  // Update mounted inspector fields without rebuilding the next tapped control.
  if(single()?.id===layer.id){
    for(const input of $('properties').querySelectorAll('[data-prop],[data-extra],[data-reference],[data-linked-prop]')){
      const key=input.dataset.prop||input.dataset.extra||input.dataset.reference||input.dataset.linkedProp;
      if(input.type==='color'&&key==='color'){input.value=layer.multicolorSatin?.bands?.[0]?.color||layer.color;continue;}
      if(input.type!=='number'||document.activeElement===input)continue;
      const value=key==='opacity'?(layer.opacity??.45)*100:layer[key];
      if(typeof value==='number')input.value=value;
    }
    const tag=$('properties').querySelector('.tag');if(tag)tag.textContent=`${round(layer.width)} × ${round(layer.height)} mm`;
    if($('recolorCheck'))$('recolorCheck').checked=!!layer.recolor;
    for(const id of ['aspectLock','referenceAspect'])if($(id))$(id).checked=layer.aspectLock!==false;
  }
}});
selectionShelf=createSelectionShelf({host:$('selectionShelf'),getState:()=>({selection:chosen(),mode,projectId:project.id}),finder:toolFinder,edit:editShelfSetting,toast});
start();
