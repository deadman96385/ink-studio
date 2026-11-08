import {pathD,worldContours,packContours,pathBounds,point,cubic,splitSegment,smoothNode} from './paths.mjs';
import {componentArtwork} from './components.mjs';
import {referenceArtwork} from './references.mjs';
import {drawPlan} from './advanced.mjs';
import {MAX_LAYERS} from './limits.mjs';
import {PenGate} from './pen.mjs';
import {branchFrame,bladeCentre} from './leaf-geometry.mjs';
import {spotBounds,transformSpot,mushroomFrame} from './mushroom-geometry.mjs';

const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone=v=>structuredClone(v), round=v=>Math.round(v*100)/100;
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));

// Arc-length coordinates are shared by dragging anchors and the guide display.
export function sampleGuide(contours) {
  const ns=contours[0]?.nodes||[], result=[];let length=0,prev=null;
  for(let i=0;i<ns.length-1;i++)for(let j=i?1:0;j<=60;j++){
    const p=cubic(ns[i],ns[i+1],j/60);
    if(prev)length+=Math.hypot(p[0]-prev[0],p[1]-prev[1]);
    result.push({p,length});prev=p;
  }
  return result;
}
export function guidePoint(samples,t,offset=0){
  const distance=(samples.at(-1)?.length||0)*t;
  let i=samples.findIndex(s=>s.length>=distance);i=clamp(i<0?samples.length-1:i,1,samples.length-1);
  if(!samples.length||!samples[i])return [50,50];
  const a=samples[i-1],b=samples[i],f=(distance-a.length)/(b.length-a.length||1),dx=b.p[0]-a.p[0],dy=b.p[1]-a.p[1],len=Math.hypot(dx,dy)||1;
  return[a.p[0]+dx*f-dy/len*offset,a.p[1]+dy*f+dx/len*offset];
}
export function projectToGuide(samples,p){
  let best={distance:Infinity,t:0,offset:0};const total=samples.at(-1)?.length||1;
  for(let i=1;i<samples.length;i++){
    const a=samples[i-1],b=samples[i],dx=b.p[0]-a.p[0],dy=b.p[1]-a.p[1],length=Math.hypot(dx,dy);
    if(!length)continue;
    const f=clamp(((p[0]-a.p[0])*dx+(p[1]-a.p[1])*dy)/(length*length),0,1),q=[a.p[0]+dx*f,a.p[1]+dy*f],d=Math.hypot(p[0]-q[0],p[1]-q[1]);
    if(d<best.distance)best={distance:d,t:(a.length+f*length)/total,offset:((p[0]-q[0])*(-dy)+(p[1]-q[1])*dx)/length};
  }
  return best;
}

// Existing saved paths may contain node/stitch edits that the recipe preview
// intentionally rebuilds. Pin those source paths, not the rebuilt preview.
export function pinSource(project,guideId,itemId,previewLayers){
  const matches=l=>l.sceneBinding?.guideId===guideId&&l.sceneBinding.itemId===itemId;
  if(project.layers.some(matches))return project;
  return {...project,layers:[...project.layers,...clone(previewLayers.filter(matches))]};
}

export function createScenes(ctx){
  const $=id=>document.getElementById(id);
  const penGate=new PenGate();
  let selectedSpot=null;
  let project=null,guide=null,proposal=null,selected=null,nodeIndex=0,mode='motifs',pid=null,revision=0;
  let generation=0,proposedGeneration=-1,timer=null,working=false,again=false,session=0,stitchToken=0,preview=null,previewItem=null;
  let history=[],future=[],view={x:-3,y:-3,w:106,h:106},pointers=new Map(),drag=null,lastArt=null,renderedLayers=null,lastPlacements=[],selectedLeaf=null,focusPending=false;
  const node=(tag,attrs={})=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);return e;};
  document.body.insertAdjacentHTML('beforeend',`<dialog id="sceneDialog" class="scene-dialog" aria-labelledby="sceneTitle">
    <div class="dialog-heading"><div><span class="eyebrow">FLOWING SCENES</span><h2 id="sceneTitle">Arrange along a curve.</h2></div><button id="closeScene" class="icon-button" aria-label="Close scene editor">×</button></div>
    <p class="caption">Drag motif anchors or the guide’s nodes and handles. Preview reflows attached parts inside the selected inner area. Applying rebuilds unpinned parts from their recipes; pin a motif to keep its current path edits. Cancel keeps the project unchanged.</p>
    <div class="scene-workspace"><section class="scene-stage"><div class="scene-toolbar"><button id="sceneMotifMode" aria-pressed="true">Motif anchors</button><button id="sceneGuideMode" aria-pressed="false">Guide nodes</button><button id="sceneLeafMode" aria-pressed="false" disabled>Leaf layout</button><button id="sceneStitchMode" aria-pressed="false" disabled>Actual stitches</button><button id="sceneZoomOut" aria-label="Zoom scene out">−</button><button id="sceneZoomFit">Hoop</button><button id="sceneZoomIn" aria-label="Zoom scene in">＋</button></div>
      <div class="field-row"><label>Reference view<select id="sceneReferenceView"><option value="design">Design</option><option value="overlay">Overlay reference</option><option value="reference">Reference only</option></select></label><label>Stitch view<select id="sceneThreadView"><option value="thread">Thread shading</option><option value="paths">Needle paths</option></select></label></div>
      <svg id="sceneCanvas" viewBox="-3 -3 106 106" aria-label="Scene guide and motif placement canvas" role="img"><rect x="0" y="0" width="100" height="100" fill="#faf7f0" stroke="#bcb9ac" stroke-width=".25"/><g id="sceneArtwork"></g><g id="sceneReferenceArtwork" pointer-events="none"></g><g id="sceneHandles"></g></svg>
      <canvas id="sceneStitchCanvas" aria-label="Actual scene stitches" hidden></canvas>
      <p id="sceneStatus" role="status"></p><div id="sceneFindings"></div>
    </section><aside class="scene-controls"><label>Usable inner area<select id="sceneArea"></select></label><label>Flow preset<select id="scenePresetStyle"><option value="any">Gentle flow · any patch</option></select></label><div class="button-row"><button id="sceneReference">Load flow preset</button><button id="sceneUsePath">Use selected open path</button></div>
      <details class="control-section"><summary>Scene construction</summary><label class="check"><input id="sceneSewVine" type="checkbox">Sew the guide as a continuous vine</label><label class="check"><input id="sceneKnockout" type="checkbox">Remove background beneath filled motifs</label><label>Background underlap (mm)<input id="sceneUnderlap" type="number" min="0.1" max="0.8" step="any"></label><p class="caption">Underlap keeps a small overlap at motif edges. Holes update with each layout.</p></details>
      <div class="button-row"><button id="sceneUndo" aria-label="Undo scene edit">↶ Undo</button><button id="sceneRedo" aria-label="Redo scene edit">↷ Redo</button></div>
      <section id="sceneMotifFields"><label>Attached motif<select id="sceneItem"></select></label><div class="button-row"><button id="sceneAddMushroom">＋ Mushroom</button><button id="sceneAddBranch">＋ Branch</button></div><div class="field-row scene-saved-motif"><label>Saved motif<select id="sceneMotifChoice"></select></label><button id="sceneAddMotif" type="button">＋ Saved motif</button></div><div class="button-row"><button id="sceneDuplicate">Duplicate motif</button><button id="sceneRemove" class="danger">Remove motif</button></div>
        <fieldset id="sceneItemSettings"><label>Motif name<input id="sceneItemName" maxlength="80"></label><div class="field-row"><label>Position along guide (%)<input id="sceneT" type="number" min="0" max="100" step="any"></label><label>Offset from guide (mm)<input id="sceneOffset" type="number" min="-30" max="30" step="any"></label></div>
        <div class="field-row"><label>Scale (%)<input id="sceneScale" type="number" min="20" max="200" step="any"></label><label>Rotation offset (°)<input id="sceneAngle" type="number" min="-180" max="180" step="any"></label></div>
        <label>Follow guide direction (%)<input id="sceneFollow" type="number" min="0" max="100" step="any"></label><div class="field-row"><label><span id="sceneDetailLabel">Cap spots</span><input id="sceneDetail" type="number" min="0" max="12" step="1"></label><label><span id="sceneColorLabel">Cap thread</span><input id="sceneColor" type="color"></label></div>
        <details class="control-section"><summary>Motif shape & stitches</summary><label>Construction<select id="sceneConstruction"><option value="classic">Classic shapes</option><option value="botanical">Botanical · satin stems and leaves</option></select></label><div class="field-row"><label><span id="sceneWidthLabel">Cap width at 100% (mm)</span><input id="sceneShapeWidth" type="number" step="any"></label><label>Height at 100% (mm)<input id="sceneShapeHeight" type="number" min="15" step="any"></label></div><label>Stem bend<input id="sceneBend" type="number" min="-0.25" max="0.25" step="any"></label><div data-mushroom-shape><div class="field-row"><label>Cap depth<input id="sceneDome" type="number" min="0.3" max="0.62" step="any"></label><label>Cap tilt (°)<input id="sceneCapTilt" type="number" min="-25" max="25" step="any"></label></div><label>Stem width / cap width<input id="sceneStemWidth" type="number" min="0.12" max="0.35" step="any"></label><label>Stitch detail<select id="sceneStitchDetail"><option value="1">Single cap fill</option><option value="2">Three cap directions + stem grain</option><option value="3">Extra gill detail</option></select></label><button id="sceneVarySpots">Vary spot pattern</button></div><div data-branch-shape hidden><label>Leaf fullness<input id="sceneLeafWidth" type="number" min="0.2" max="0.6" step="any"></label><label>Leaf side<select id="sceneLeafSide"><option value="both">Both sides</option><option value="left">Left side</option><option value="right">Right side</option></select></label></div></details>
        <label class="check"><input id="sceneFlip" type="checkbox">Mirror motif</label><label class="check"><input id="sceneAutoFit" type="checkbox">Fit inside area: adjust offset and reduce size when needed</label><label class="check"><input id="scenePinned" type="checkbox">Pin current motif geometry</label><p id="scenePlacementNote" class="caption"></p><div class="button-row"><button id="sceneEarlier">Move earlier</button><button id="sceneLater">Move later</button></div></fieldset>
      </section>
      <section id="sceneGuideFields" hidden><label>Guide node<select id="sceneNode"></select></label><div class="field-row"><label>Guide node X (mm)<input id="sceneNodeX" type="number" min="0" max="100" step="any"></label><label>Guide node Y (mm)<input id="sceneNodeY" type="number" min="0" max="100" step="any"></label></div><div class="button-row"><button id="sceneInsertNode">Insert midpoint</button><button id="sceneRemoveNode">Remove node</button><button id="sceneSmoothNode">Smooth node</button></div><p class="caption">Drag the small handle ends to bend the curve. Pinch to zoom; drag empty space to pan. Enable the continuous vine in Scene construction to sew this guide.</p></section>
      <section id="sceneLeafFields" hidden><label>Branch to arrange<select id="sceneLeafBranch"></select></label><p class="caption">Drag a leaf’s green tip or its white base. Purple handles bend the stem. Each blade connects to its stem junction by a petiole. Dimensions below are at 100% motif scale.</p><fieldset id="sceneLeafSettings"><label>Leaf<select id="sceneBlade"></select></label><div class="button-row"><button id="sceneAddLeaf">＋ Leaf</button><button id="sceneDuplicateLeaf">Duplicate leaf</button><button id="sceneRemoveLeaf">Remove leaf</button></div><div class="field-row"><label>Blade base X (mm)<input id="sceneBladeBaseX" type="number" step="any"></label><label>Blade base Y (mm)<input id="sceneBladeBaseY" type="number" step="any"></label><label>Leaf tip X (mm)<input id="sceneBladeTipX" type="number" step="any"></label><label>Leaf tip Y (mm)<input id="sceneBladeTipY" type="number" step="any"></label><label>Blade width (mm)<input id="sceneBladeWidth" type="number" step="any"></label><label>Leaf curve<input id="sceneBladeBend" type="number" min="-0.4" max="0.4" step="any"></label></div><label>Stem junction (%)<input id="sceneBladeJoin" type="number" min="0" max="100" step="any"></label><label class="check"><input id="sceneBladeSplit" type="checkbox">Two-tone satin halves</label><details class="control-section"><summary>Stem curve</summary><label>Stem handle<select id="sceneStemPoint"><option value="1">Control 1</option><option value="2">Control 2</option><option value="3">Stem tip</option></select></label><div class="field-row"><label>Stem handle X (mm)<input id="sceneStemX" type="number" step="any"></label><label>Stem handle Y (mm)<input id="sceneStemY" type="number" step="any"></label></div><p class="caption">The stem base stays attached to the scene guide.</p></details></fieldset></section>
    </aside></div><p id="sceneError" class="error" role="alert"></p><div class="dialog-footer"><button id="cancelScene">Cancel</button><button id="sceneReflow">Reflow preview</button><button id="scenePreviewStitches">Preview stitches</button><button id="applyScene" class="primary" disabled>Apply editable scene</button></div>
  </dialog>`);
  $('sceneLeafSettings').insertAdjacentHTML('afterbegin','<div class="field-row"><label>Leaf shadow thread<input id="sceneBladeDarkColor" type="color"></label><label>Leaf light thread<input id="sceneBladeLightColor" type="color"></label></div>');
  $('sceneLeafBranch').closest('label').insertAdjacentHTML('afterend','<div class="button-row"><button id="sceneLeafFocus">Fit selected branch</button><button id="sceneLeafPreview">Preview branch stitches</button></div>');
  $('sceneLeafMode').insertAdjacentHTML('afterend','<button id="sceneMushroomMode" aria-pressed="false" disabled>Mushroom spots</button>');
  $('sceneUnderlap').closest('details').insertAdjacentHTML('beforeend','<button id="sceneSimplify">Simplify for a small patch</button><p class="caption">Uses one green thread, keeps broad leaves and larger spots, and reduces stitch layers. Routes each sprig through its stem. Undo restores the previous recipes.</p>');
  $('sceneLeafFields').insertAdjacentHTML('afterend',`<section id="sceneSpotFields" hidden><label>Mushroom to arrange<select id="sceneSpotMushroom"></select></label><div class="button-row"><button id="sceneSpotFocus">Fit selected mushroom</button><button id="sceneSpotPreview">Preview mushroom stitches</button></div><p class="caption">Drag a numbered spot to move it. Each spot keeps its own outline and stitches. Overlapping spots must be moved or resized before applying.</p><label>Spot<select id="sceneSpot"></select></label><fieldset id="sceneSpotSettings"><div class="field-row"><label>Spot centre X (mm)<input id="sceneSpotX" type="number" step="any"></label><label>Spot centre Y (mm)<input id="sceneSpotY" type="number" step="any"></label><label>Spot width (mm)<input id="sceneSpotWidth" type="number" min="0.2" step="any"></label><label>Spot height (mm)<input id="sceneSpotHeight" type="number" min="0.2" step="any"></label><label>Spot rotation (°)<input id="sceneSpotRotation" type="number" min="-180" max="180" step="any"></label></div></fieldset><div class="button-row"><button id="sceneSpotAdd">＋ Spot</button><button id="sceneSpotRemove">Remove spot</button></div></section>`);
  $('sceneSpotFields').insertAdjacentHTML('beforeend','<details id="sceneStemFlowFields" class="control-section"><summary>Stem stitch flow</summary><p class="caption">Crosswise rows cover the upper stem. Curved lengthwise fibers spread into the foot. The regions overlap at the transition.</p><label>Transition down stem (%)<input id="sceneStemTransition" type="number" min="20" max="85" step="any"></label><label>Foot fiber spread<input id="sceneStemSpread" type="number" min="0.5" max="2.5" step="any"></label><label>Stem edge repair (mm)<input id="sceneStemRepair" type="number" min="0" max="1" step="any"></label></details>');
  const fresh=()=>ctx.getProject().id===pid&&ctx.getRevision()===revision;
  const current=()=>guide?.scene.items.find(i=>i.id===selected);
  const blade=()=>current()?.params.leafMap?.find(l=>l.id===selectedLeaf);
  const spot=()=>current()?.params.spotDetails?.find(l=>l.id===selectedSpot);
  function layoutStatus(result){return `${result.count} motifs · ${result.partCount} stitched parts · ${result.layerCount}/${MAX_LAYERS} layers · ${result.fits?'all motifs inside the inner area':`${result.findings.length} motifs cross the boundary`}`;}
  function chooseItem(id){
    selected=id;
    if(previewItem&&previewItem!==id){previewItem=null;preview=null;$('sceneStitchMode').disabled=true;if(proposal)$('sceneStatus').textContent=layoutStatus(proposal);if(mode==='stitches')mode='motifs';}
  }
  const snapshot=()=>clone(guide);
  const capture=()=>({guide:snapshot(),project:clone(project)});
  function record(){history.push(capture());if(history.length>35)history.shift();future=[];}
  function stateChanged(schedule=true){generation++;if(proposal)lastArt=proposal.layers;proposal=null;preview=null;$('sceneStitchMode').disabled=true;$('scenePreviewStitches').disabled=true;$('applyScene').disabled=true;$('sceneError').textContent='';$('sceneFindings').replaceChildren();$('sceneStatus').textContent='Layout changed · preparing a fresh fit check…';if(mode==='stitches')mode='motifs';draw();if(schedule)queueLayout();}
  function edit(fn){if(!guide)return;record();fn();stateChanged();fields();}
  function setMode(next){mode=next;draw();fields();}
  function fields(){
    if(mode==='leaves'&&(!current()?.params.leafMap||current()?.params.profile!=='botanical')){mode='motifs';draw();}
    if(mode==='spots'&&(!current()?.params.spotDetails||current()?.params.profile!=='botanical')){mode='motifs';draw();}
    $('sceneUndo').disabled=!history.length;$('sceneRedo').disabled=!future.length;
    $('sceneMotifMode').setAttribute('aria-pressed',String(mode==='motifs'));$('sceneGuideMode').setAttribute('aria-pressed',String(mode==='guide'));$('sceneStitchMode').setAttribute('aria-pressed',String(mode==='stitches'));$('sceneLeafMode').setAttribute('aria-pressed',String(mode==='leaves'));
    $('sceneMotifFields').hidden=['guide','leaves','spots'].includes(mode);$('sceneGuideFields').hidden=mode!=='guide';$('sceneLeafFields').hidden=mode!=='leaves';$('sceneSpotFields').hidden=mode!=='spots';$('sceneMushroomMode').setAttribute('aria-pressed',String(mode==='spots'));
    if(!guide)return;
    $('sceneSewVine').checked=!!guide.scene.sewVine;$('sceneKnockout').checked=!!guide.scene.knockoutBackground;$('sceneUnderlap').value=guide.scene.groundUnderlap??.25;
    const items=guide.scene.items;$('sceneItem').innerHTML=items.map((i,n)=>`<option value="${i.id}">${n+1}. ${esc(i.name)}</option>`).join('');
    if(!items.some(i=>i.id===selected))selected=items[0]?.id;
    $('sceneItem').value=selected||'';const item=current();$('sceneItemSettings').disabled=!item;
    $('sceneLeafMode').disabled=!item||item.kind!=='branch'||!!item.pinned;
    $('sceneMushroomMode').disabled=!item||item.kind!=='mushroom'||!!item.pinned;
    if(item){
      for(const[id,value]of [['sceneItemName',item.name],['sceneT',round(item.t*100)],['sceneOffset',round(item.offset)],['sceneScale',round(item.scale*100)],['sceneAngle',round(item.angle)],['sceneFollow',round(item.follow*100)]])$(id).value=value;
      $('sceneFlip').checked=!!item.flipX;$('sceneAutoFit').checked=item.autoFit!==false;$('scenePinned').checked=!!item.pinned;
      const saved=item.kind==='motif';$('sceneDetail').closest('.field-row').hidden=saved;$('sceneConstruction').closest('details').hidden=saved;const branch=item.kind==='branch';$('sceneDetailLabel').textContent=branch?'Leaf pairs':'Cap spots';$('sceneDetail').min=branch?2:0;$('sceneDetail').max=branch?5:12;$('sceneDetail').value=branch?(item.params.pairs??3):(item.params.spots??5);
      $('sceneConstruction').value=item.params.profile||'classic';$('sceneWidthLabel').textContent=branch?'Spread at 100% (mm)':'Cap width at 100% (mm)';$('sceneShapeWidth').min=branch?8:10;$('sceneShapeWidth').max=branch?40:45;$('sceneShapeHeight').max=branch?60:55;
      for(const[id,key,value]of [['sceneShapeWidth','width',12],['sceneShapeHeight','height',18],['sceneBend','bend',.05],['sceneDome','dome',.45],['sceneCapTilt','capTilt',0],['sceneStemWidth','stemWidth',.2],['sceneStitchDetail','detail',2],['sceneLeafWidth','leafWidth',.36],['sceneLeafSide','leafSide','both']])$(id).value=item.params[key]??value;
      $('sceneDialog').querySelector('[data-mushroom-shape]').hidden=branch;$('sceneDialog').querySelector('[data-branch-shape]').hidden=!branch;
      $('sceneStitchDetail').options[1].textContent=item.params.stemContours?'Three cap fill directions':'Three cap directions + stem grain';
      $('sceneColorLabel').textContent=branch?'Leaf thread':'Cap thread';$('sceneColor').value=branch?(item.params.leafColor||'#64a638'):(item.params.capColor||'#c91830');
      const place=proposal?.placements.find(p=>p.itemId===item.id);
      $('scenePlacementNote').textContent=item.pinned?'Pinned parts retain their current nodes and stitch settings.':place?.adjusted?`Fitted at ${round(place.scale*100)}% scale and ${place.offset} mm offset.`:'The motif’s stem base attaches to the guide. Foliage sews before mushrooms.';
      for(const id of ['sceneT','sceneOffset','sceneScale','sceneAngle','sceneFollow','sceneFlip','sceneAutoFit','sceneDetail','sceneColor','sceneConstruction','sceneShapeWidth','sceneShapeHeight','sceneBend','sceneDome','sceneCapTilt','sceneStemWidth','sceneStitchDetail','sceneLeafWidth','sceneLeafSide','sceneVarySpots'])$(id).disabled=!!item.pinned;
      if(branch&&item.params.profile==='botanical'&&item.params.leafMap){$('sceneDetailLabel').textContent='Leaves · use Leaf layout';$('sceneDetail').max=12;$('sceneDetail').value=item.params.leafMap.length;for(const id of ['sceneDetail','sceneBend','sceneLeafWidth','sceneLeafSide'])$(id).disabled=true;}
      if(item.params.profile!=='botanical')for(const id of branch?['sceneLeafWidth','sceneLeafSide']:['sceneCapTilt','sceneStemWidth','sceneStitchDetail','sceneVarySpots'])$(id).disabled=true;
      if(branch&&item.params.leafMap)leafFields();
      if(!branch&&item.params.profile==='botanical'){
        if(item.params.capContours)for(const id of ['sceneDome','sceneVarySpots'])$(id).disabled=true;
        if(item.params.stemRails)for(const id of ['sceneBend','sceneStemWidth'])$(id).disabled=true;
        if(item.params.spotDetails){$('sceneDetailLabel').textContent='Spots · use Mushroom spots';$('sceneDetail').disabled=true;spotFields();}
      }
      if(item.params.sewingProfile==='simple'){$('scenePlacementNote').textContent+=' Low-trim sewing profile: fewer passes and connected sprigs.';$('sceneStitchDetail').disabled=true;}
    }
    const nodes=worldContours(guide)[0].nodes;nodeIndex=clamp(nodeIndex,0,nodes.length-1);
    $('sceneNode').innerHTML=nodes.map((n,i)=>`<option value="${i}">Node ${i+1}</option>`).join('');$('sceneNode').value=nodeIndex;
    $('sceneNodeX').value=round(nodes[nodeIndex].x);$('sceneNodeY').value=round(nodes[nodeIndex].y);
    $('sceneRemoveNode').disabled=nodes.length<=2;
  }
  function leafFields(){
    const item=current(),p=item.params,leaves=p.leafMap;if(!leaves)return;
    $('sceneLeafBranch').innerHTML=guide.scene.items.filter(i=>i.kind==='branch').map(i=>`<option value="${i.id}">${esc(i.name)}</option>`).join('');$('sceneLeafBranch').value=item.id;
    $('sceneLeafPreview').disabled=!proposal?.fits||proposedGeneration!==generation;
    if(!leaves.some(l=>l.id===selectedLeaf))selectedLeaf=leaves[0].id;
    $('sceneBlade').innerHTML=leaves.map((l,i)=>`<option value="${l.id}">${i+1}. ${esc(l.name)}</option>`).join('');$('sceneBlade').value=selectedLeaf;
    const leaf=blade();$('sceneLeafSettings').disabled=!!item.pinned;
    $('sceneBladeSplit').disabled=p.sewingProfile==='simple';$('sceneBladeLightColor').disabled=p.sewingProfile==='simple';
    $('sceneBladeDarkColor').value=p.leafColor;$('sceneBladeLightColor').value=p.lightColor;
    for(const[id,key,axis]of [['sceneBladeBaseX','base',0],['sceneBladeBaseY','base',1],['sceneBladeTipX','tip',0],['sceneBladeTipY','tip',1]]){const dimension=axis?p.height:p.width;$(id).min=-.5*dimension;$(id).max=1.5*dimension;$(id).value=round(leaf[key][axis]*dimension);}
    $('sceneBladeWidth').min=.015*p.width;$('sceneBladeWidth').max=.8*p.width;$('sceneBladeWidth').value=round(leaf.width*p.width);$('sceneBladeBend').value=leaf.bend;$('sceneBladeJoin').value=round(leaf.join*100);$('sceneBladeSplit').checked=leaf.split;
    $('sceneAddLeaf').disabled=$('sceneDuplicateLeaf').disabled=leaves.length>=12;$('sceneRemoveLeaf').disabled=leaves.length<=1;
    const point=p.stemCurve[Number($('sceneStemPoint').value)||1];for(const[id,axis]of [['sceneStemX',0],['sceneStemY',1]]){const dimension=axis?p.height:p.width;$(id).min=-.5*dimension;$(id).max=1.5*dimension;$(id).value=round(point[axis]*dimension);}
  }
  function curveEdit(fn){edit(()=>{const curves=worldContours(guide);fn(curves[0]);guide=packContours(curves,guide);});}
  function spotFields(){
    const p=current().params,spots=p.spotDetails;
    $('sceneSpotMushroom').innerHTML=guide.scene.items.filter(i=>i.kind==='mushroom').map(i=>`<option value="${i.id}">${esc(i.name)}</option>`).join('');$('sceneSpotMushroom').value=current().id;
    if(!spots.some(s=>s.id===selectedSpot))selectedSpot=spots[0]?.id;
    $('sceneSpot').innerHTML=spots.map((s,i)=>`<option value="${s.id}">${i+1}. ${esc(s.name)}</option>`).join('');$('sceneSpot').value=selectedSpot||'';
    $('sceneSpotSettings').disabled=!spot()||!!current().pinned;
    $('sceneSpotAdd').disabled=spots.length>=12||!!current().pinned;$('sceneSpotRemove').disabled=!spot()||!!current().pinned;
    $('sceneSpotPreview').disabled=!proposal?.fits||proposedGeneration!==generation;
    $('sceneStemFlowFields').hidden=!p.stemContours;
    const flow=p.stemFlow||{};for(const[id,value]of [['sceneStemTransition',(flow.transition??.5)*100],['sceneStemSpread',flow.spread??1.45],['sceneStemRepair',flow.repair??.55]]){$(id).value=round(value);$(id).disabled=!!current().pinned;}
    if(!spot())return;const b=spotBounds(p,spot());
    for(const[id,value]of [['sceneSpotX',b.cx],['sceneSpotY',b.cy],['sceneSpotWidth',b.w],['sceneSpotHeight',b.h],['sceneSpotRotation',spot().rotation||0]])$(id).value=round(value);
  }
  function drawSpots(handles,hit){
    const placement=leafPlacement();if(!placement)return;
    const item=current(),p=item.params,frame=mushroomFrame(item,placement);
    for(const s of [...p.spotDetails.filter(s=>s.id!==selectedSpot),...p.spotDetails.filter(s=>s.id===selectedSpot)]){
      const b=spotBounds(p,s),q=frame.toWorld([b.cx/p.width,b.cy/p.height]),active=s.id===selectedSpot;
      if(active){const contours=s.contours.map(c=>({...c,nodes:c.nodes.map(n=>{const[x,y]=frame.toWorld([n.x,n.y]);return{x,y,in:frame.toWorld(n.in),out:frame.toWorld(n.out)};})}));handles.append(node('path',{d:pathD(contours),fill:'none',stroke:'#3cdbce','stroke-width':.2,'pointer-events':'none'}));}
      handles.append(node('circle',{cx:q[0],cy:q[1],r:hit*.7,fill:'transparent','data-spot-id':s.id,'aria-label':`Move ${s.name}`}));
      const label=node('text',{x:q[0],y:q[1]+.35,'font-size':1.1,'text-anchor':'middle',fill:active?'#00655b':'#584c38','pointer-events':'none'});label.textContent=p.spotDetails.indexOf(s)+1;handles.append(label);
    }
  }
  async function openSpots(){
    const item=current();if(!item||item.kind!=='mushroom'||item.pinned)return;
    if(!item.params.spotDetails||item.params.profile!=='botanical'){
      const active=session,id=item.id,run=generation;
      try{const result=await ctx.api('/api/components',{action:'mushroom-layout',params:item.params});if(active!==session||run!==generation||current()?.id!==id)return;edit(()=>item.params=result.params);}
      catch(e){$('sceneError').textContent=e.message;return;}
    }
    selectedSpot=item.params.spotDetails[0]?.id;setMode('spots');focusMushroom();
  }
  function focusMushroom(){
    const layers=(proposal?.layers||lastArt||[]).filter(l=>l.sceneBinding?.itemId===selected);if(!layers.length){focusPending=true;return;}focusPending=false;
    const b=pathBounds(layers.flatMap(worldContours)),size=clamp(Math.max(b.w,b.h)+4,15,100);view={x:b.x+b.w/2-size/2,y:b.y+b.h/2-size/2,w:size,h:size};draw();
  }
  $('sceneMushroomMode').onclick=openSpots;$('sceneSpotFocus').onclick=focusMushroom;
  $('sceneSpotMushroom').onchange=()=>{chooseItem($('sceneSpotMushroom').value);if(current().pinned)setMode('motifs');else openSpots();};
  $('sceneSpot').onchange=()=>{selectedSpot=$('sceneSpot').value;fields();draw();};
  for(const[id,key]of [['sceneSpotX','cx'],['sceneSpotY','cy'],['sceneSpotWidth','w'],['sceneSpotHeight','h'],['sceneSpotRotation','rotation']])$(id).oninput=()=>{
    if($(id).value===''||!$(id).validity.valid||!spot())return;
    const value=Number($(id).value);edit(()=>{const p=current().params,b=spotBounds(p,spot());transformSpot(p,spot(),key==='cx'?{dx:value-b.cx}:key==='cy'?{dy:value-b.cy}:key==='w'?{sx:value/b.w}:key==='h'?{sy:value/b.h}:{angle:value-(spot().rotation||0)});});
  };
  $('sceneSpotRemove').onclick=()=>{if(spot())edit(()=>{const p=current().params;p.spotDetails=p.spotDetails.filter(s=>s.id!==selectedSpot);p.spots=p.spotDetails.length;});};
  for(const[id,key,factor]of [['sceneStemTransition','transition',.01],['sceneStemSpread','spread',1],['sceneStemRepair','repair',1]])$(id).oninput=()=>{if($(id).value!==''&&$(id).validity.valid)edit(()=>{current().params.stemFlow={...(current().params.stemFlow||{}),[key]:Number($(id).value)*factor};});};
  $('sceneSpotAdd').onclick=()=>edit(()=>{
    const p=current().params;if(p.spotDetails.length>=12)return;
    const b=pathBounds(p.capContours.map(c=>({...c,nodes:c.nodes.map(n=>({x:n.x*p.width,y:n.y*p.height,in:[n.in[0]*p.width,n.in[1]*p.height],out:[n.out[0]*p.width,n.out[1]*p.height]}))}))),cx=(b.x+b.w*.5)/p.width,cy=(b.y+b.h*.3)/p.height,rx=.035,ry=rx*p.width/p.height,k=.55228475;
    const nodes=[{x:cx+rx,y:cy,in:[cx+rx,cy-ry*k],out:[cx+rx,cy+ry*k]},{x:cx,y:cy+ry,in:[cx+rx*k,cy+ry],out:[cx-rx*k,cy+ry]},{x:cx-rx,y:cy,in:[cx-rx,cy+ry*k],out:[cx-rx,cy-ry*k]},{x:cx,y:cy-ry,in:[cx-rx*k,cy-ry],out:[cx+rx*k,cy-ry]}];
    const s={id:crypto.randomUUID().slice(0,8),name:`Spot ${p.spotDetails.length+1}`,rotation:0,contours:[{closed:true,nodes}]};p.spotDetails.push(s);p.spots=p.spotDetails.length;selectedSpot=s.id;
  });
  function draw(){
    $('sceneCanvas').toggleAttribute('hidden',mode==='stitches');$('sceneStitchCanvas').hidden=mode!=='stitches';
    if(mode==='stitches'){if(preview)drawPlan($('sceneStitchCanvas'),preview,null,$('sceneThreadView').value);return;}
    $('sceneCanvas').setAttribute('viewBox',`${view.x} ${view.y} ${view.w} ${view.h}`);
    const layers=proposal?.layers||lastArt||project?.layers||[];
    // Only locally generated SVG is parsed; the outer viewport stays in hoop mm.
    if(layers!==renderedLayers){
      const doc=new DOMParser().parseFromString(componentArtwork(layers.filter(l=>l.visible!==false&&l.type==='path'&&l.role!=='scene-guide')),'image/svg+xml');
      $('sceneArtwork').replaceChildren(...[...doc.documentElement.children].map(e=>document.importNode(e,true)));renderedLayers=layers;
    }
    const referenceMode=$('sceneReferenceView').value;$('sceneArtwork').setAttribute('opacity',referenceMode==='reference'?0:1);$('sceneReferenceArtwork').setAttribute('opacity',referenceMode==='overlay'?.45:referenceMode==='reference'?1:0);
    const handles=$('sceneHandles');handles.replaceChildren();if(!guide||referenceMode==='reference')return;
    const curves=worldContours(guide),ns=curves[0].nodes,samples=sampleGuide(curves);
    handles.append(node('path',{d:pathD(curves),fill:'none',stroke:'#ce923d','stroke-width':.35,'stroke-dasharray':'1.2 .65','pointer-events':'none'}));
    const matrix=$('sceneCanvas').getScreenCTM(),hit=matrix?22/Math.hypot(matrix.a,matrix.b):3;
    if(mode==='leaves'&&current()?.params.leafMap)drawLeaves(handles,hit);
    if(mode==='spots'&&current()?.params.spotDetails)drawSpots(handles,hit);
    if(mode==='guide')for(const[n,i]of ns.map((n,i)=>[n,i])){
      if(i===nodeIndex)for(const key of ['in','out']){
        if(key==='in'&&i===0||key==='out'&&i===ns.length-1)continue;
        handles.append(node('path',{d:`M${n.x} ${n.y}L${n[key][0]} ${n[key][1]}`,stroke:'#997bb4','stroke-width':.22,'pointer-events':'none'}));
        handles.append(node('circle',{cx:n[key][0],cy:n[key][1],r:hit,fill:'transparent','data-guide-handle':key,'data-node-index':i}));
        handles.append(node('circle',{cx:n[key][0],cy:n[key][1],r:.7,fill:'#fff',stroke:'#997bb4','stroke-width':.25,'pointer-events':'none'}));
      }
      handles.append(node('circle',{cx:n.x,cy:n.y,r:hit,fill:'transparent','data-guide-node':i}));
      handles.append(node('circle',{cx:n.x,cy:n.y,r:i===nodeIndex?1.1:.8,fill:i===nodeIndex?'#ce923d':'#fff',stroke:'#9e6d28','stroke-width':.25,'pointer-events':'none'}));
    }
    if(mode==='motifs')for(const[item,i]of guide.scene.items.map((item,i)=>[item,i])){
      const result=proposal?.placements.find(p=>p.itemId===item.id),p=result?.anchor||guidePoint(samples,item.t,item.offset);
      const g=node('g',{'data-scene-item':item.id,role:'button','aria-label':`Select ${item.name}`});
      g.append(node('circle',{cx:p[0],cy:p[1],r:hit,fill:'transparent'}));
      g.append(node('circle',{cx:p[0],cy:p[1],r:item.id===selected?1.5:1.1,fill:item.pinned?'#777':item.kind==='branch'?'#507632':'#ae2433',stroke:'#fff','stroke-width':.22}));
      const text=node('text',{x:p[0],y:p[1]+.5,'font-size':1.5,'text-anchor':'middle',fill:'#fff','pointer-events':'none'});text.textContent=i+1;g.append(text);handles.append(g);
    }
  }
  function leafPlacement(){return (proposal?.placements||lastPlacements).find(p=>p.itemId===selected);}
  function drawLeaves(handles,hit){
    const item=current(),p=item.params,placement=leafPlacement();if(!placement)return;
    const frame=branchFrame(item,placement),stem=p.stemCurve.map(frame.toWorld);
    handles.append(node('path',{d:`M${stem[0]} C${stem.slice(1).join(' ')}`,fill:'none',stroke:'#9b76bc','stroke-width':.25,'stroke-dasharray':'.7 .5','pointer-events':'none'}));
    for(let i=1;i<4;i++){handles.append(node('circle',{cx:stem[i][0],cy:stem[i][1],r:hit*.65,fill:'transparent','data-stem-control':i}));handles.append(node('circle',{cx:stem[i][0],cy:stem[i][1],r:.65,fill:'#9b76bc',stroke:'#fff','stroke-width':.2,'pointer-events':'none'}));}
    const leaves=[...p.leafMap.filter(l=>l.id!==selectedLeaf),...p.leafMap.filter(l=>l.id===selectedLeaf)];
    for(const leaf of leaves){
      const [a,b,c,d]=bladeCentre(p,leaf).map(frame.toWorld),active=leaf.id===selectedLeaf;
      handles.append(node('path',{d:`M${a} C${b} ${c} ${d}`,fill:'none',stroke:active?'#ffffff':'#96c44e','stroke-width':active?.30:.14,'pointer-events':'none'}));
      for(const [key,q]of [['tip',d],...(active?[['base',a]]:[])]){
        handles.append(node('circle',{cx:q[0],cy:q[1],r:hit*.7,fill:'transparent','data-leaf-point':key,'data-leaf-id':leaf.id}));
        handles.append(node('circle',{cx:q[0],cy:q[1],r:active?.85:.6,fill:key==='base'?'#fff':'#74a832',stroke:active?'#123d36':'#fff','stroke-width':.22,'pointer-events':'none'}));
      }
    }
  }
  function queueLayout(){clearTimeout(timer);timer=setTimeout(()=>refresh(),300);}
  async function refresh(){
    if(!guide||!$('sceneDialog').open)return;
    if(working){again=true;return;}working=true;again=false;
    const run=generation,active=session,submitted=clone(guide);
    $('sceneStatus').textContent='Reflowing motifs and checking their full shapes…';$('scenePreviewStitches').disabled=true;
    try{
      const result=await ctx.api('/api/scenes',{project,guide:submitted});
      if(active!==session||run!==generation||!$('sceneDialog').open)return;
      if(!fresh())throw new Error('The project changed outside this editor. Close and reopen the scene.');
      proposal=result;lastPlacements=result.placements;proposedGeneration=run;
      $('sceneStatus').textContent=layoutStatus(result);
      $('sceneFindings').innerHTML=result.findings.map(f=>`<p class="check-finding">${esc(f.name)} · ${f.outsideMm2} mm² outside. Change its position, size or angle.</p>`).join('');
      $('applyScene').disabled=!result.fits;$('scenePreviewStitches').disabled=!result.fits;draw();fields();if(focusPending){if(mode==='leaves')focusBranch();if(mode==='spots')focusMushroom();}
    }catch(e){if(active===session&&run===generation){$('sceneError').textContent=e.message;$('sceneStatus').textContent='';}}
    finally{working=false;if(again||run!==generation&&active===session)queueLayout();}
  }
  async function loadReference(){
    try{const active=session;const style=$('scenePresetStyle').value;const r=await ctx.api('/api/scenes',{action:'preset',project,areaId:$('sceneArea').value,style,...(style==='any'&&$('sceneMotifChoice').value?{motif:$('sceneMotifChoice').value}:{})});if(active!==session)return;if(guide)record();guide=r.guide;selected=guide.scene.items[0].id;nodeIndex=0;stateChanged();fields();}
    catch(e){$('sceneError').textContent=e.message;}
  }
  async function loadMotifs(){try{const list=await ctx.api('/api/motifs',{action:'list'});$('sceneMotifChoice').innerHTML=list.map(m=>`<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');$('sceneMotifChoice').disabled=$('sceneAddMotif').disabled=!list.length;}catch{}}
  async function open(){
    try{
      loadMotifs();
      previewItem=null;
      const live=ctx.getProject(),areas=live.layers.filter(l=>l.role==='content-area'&&l.visible!==false);
      if(!areas.length)throw new Error('Add a crescent patch or build a usable inner area first.');
      project=clone(live);pid=live.id;revision=ctx.getRevision();session++;stitchToken++;history=[];future=[];proposal=null;preview=null;working=false;generation=0;lastArt=null;renderedLayers=null;lastPlacements=[];selectedLeaf=null;
      const chosen=ctx.chosen()[0],binding=chosen?.sceneBinding?.guideId;
      guide=clone(project.layers.find(l=>l.role==='scene-guide'&&(l.id===binding||l.id===chosen?.id))||project.layers.find(l=>l.role==='scene-guide')||null);
      $('sceneArea').innerHTML=areas.map(l=>`<option value="${l.id}">${esc(project.layers.find(b=>b.id===l.areaSource)?.name||'Patch')} · inner area</option>`).join('');
      $('sceneArea').value=guide?.scene.areaId||areas[0].id;view={x:-3,y:-3,w:106,h:106};mode='motifs';nodeIndex=0;pointers.clear();penGate.reset();drag=null;$('sceneError').textContent='';$('sceneFindings').replaceChildren();$('sceneStitchMode').disabled=true;$('applyScene').disabled=true;
      const references=project.layers.filter(l=>l.type==='image'&&l.visible!==false);$('sceneReferenceArtwork').replaceChildren(...references.map(l=>referenceArtwork({...l,opacity:1})));$('sceneReferenceView').value='design';$('sceneReferenceView').disabled=!references.length;
      $('scenePresetStyle').value=guide?.scene.style||project.layers.find(l=>l.id===areas.find(a=>a.id===$('sceneArea').value)?.areaSource)?.component?.params?.profile||'classic';
      $('sceneDialog').showModal();
      if(!guide){
        const area=areas.find(l=>l.id===$('sceneArea').value),body=project.layers.find(l=>l.id===area.areaSource);
        if(body?.component?.kind==='crescent')await loadReference();
        else{
          const source=ctx.chosen().find(l=>l.type==='path'&&l.contours?.length===1&&!l.contours[0].closed),b=pathBounds(worldContours(area));
          const curves=source?worldContours(source):[{closed:false,nodes:[point(b.x+b.w/2,b.y+b.h*.15),point(b.x+b.w/2,b.y+b.h*.85)]}];
          guide=packContours(curves,{id:source?.id||crypto.randomUUID(),type:'path',name:'Scene · flow guide',role:'scene-guide',color:'#ce923d',stitch:'running',visible:true,
            scene:{version:1,areaId:area.id,items:[{id:crypto.randomUUID(),kind:'mushroom',name:'Mushroom 1',t:.7,offset:0,angle:0,follow:.4,scale:1,params:{width:12,height:18},autoFit:true}]}});
          selected=guide.scene.items[0].id;stateChanged();fields();
        }
      }else{selected=guide.scene.items[0]?.id;fields();draw();await refresh();}
    }catch(e){ctx.toast(e.message);}
  }
  $('sceneReference').onclick=loadReference;
  $('sceneSimplify').onclick=async()=>{
    if(!guide)return;const active=session,run=generation;
    try{const result=await ctx.api('/api/scenes',{action:'simplify',guide});if(active!==session||run!==generation)return;edit(()=>guide=result.guide);$('sceneStatus').textContent=`Simplifying to ${result.stats.leaves} broad leaves and ${result.stats.spots} larger spots · routing sprigs…`;}
    catch(e){$('sceneError').textContent=e.message;}
  };
  $('sceneReferenceView').onchange=()=>{if(mode==='stitches')setMode('motifs');else draw();};$('sceneThreadView').onchange=draw;
  for(const[id,key]of [['sceneSewVine','sewVine'],['sceneKnockout','knockoutBackground']])$(id).onchange=()=>edit(()=>guide.scene[key]=$(id).checked);
  $('sceneUnderlap').oninput=()=>{if($('sceneUnderlap').value!==''&&$('sceneUnderlap').validity.valid)edit(()=>guide.scene.groundUnderlap=Number($('sceneUnderlap').value));};
  $('sceneArea').onchange=()=>{if(guide)edit(()=>guide.scene.areaId=$('sceneArea').value);};
  $('sceneUsePath').onclick=()=>{
    try{const source=ctx.chosen().find(l=>l.type==='path'&&l.contours?.length===1&&!l.contours[0].closed);if(!source)throw new Error('Select one open native path before opening the scene editor.');
      const curves=worldContours(source);edit(()=>{guide=packContours(curves,{...guide,id:guide?.id||source.id,name:'Scene · flow guide',role:'scene-guide',scene:guide?.scene||{version:1,areaId:$('sceneArea').value,items:[]}});delete guide.component;delete guide.groupId;if(source.id!==guide.id){const original=project.layers.find(l=>l.id===source.id);if(original)original.visible=false;}});setMode('guide');
    }catch(e){$('sceneError').textContent=e.message;}
  };
  $('sceneItem').onchange=()=>{chooseItem($('sceneItem').value);fields();draw();};
  for(const[id,key,factor]of [['sceneT','t',.01],['sceneOffset','offset',1],['sceneScale','scale',.01],['sceneAngle','angle',1],['sceneFollow','follow',.01]])$(id).oninput=()=>{const input=$(id);if(input.value!==''&&input.validity.valid)edit(()=>current()[key]=Number(input.value)*factor);};
  $('sceneItemName').onchange=()=>edit(()=>current().name=$('sceneItemName').value.trim()||current().kind);
  for(const[id,key]of [['sceneFlip','flipX'],['sceneAutoFit','autoFit']])$(id).onchange=()=>edit(()=>current()[key]=$(id).checked);
  $('scenePinned').onchange=()=>{const on=$('scenePinned').checked;if(on&&proposal)project=pinSource(project,guide.id,selected,proposal.layers);edit(()=>current().pinned=on);};
  $('sceneDetail').oninput=()=>{if($('sceneDetail').value!==''&&$('sceneDetail').validity.valid)edit(()=>{current().params[current().kind==='branch'?'pairs':'spots']=Number($('sceneDetail').value);if(current().kind==='mushroom')delete current().params.spotMap;});};
  $('sceneColor').onchange=()=>edit(()=>current().params[current().kind==='branch'?'leafColor':'capColor']=$('sceneColor').value);
  for(const[id,key]of [['sceneConstruction','profile'],['sceneLeafSide','leafSide'],['sceneStitchDetail','detail']])$(id).onchange=()=>edit(()=>current().params[key]=key==='detail'?Number($(id).value):$(id).value);
  for(const[id,key]of [['sceneShapeWidth','width'],['sceneShapeHeight','height'],['sceneBend','bend'],['sceneDome','dome'],['sceneCapTilt','capTilt'],['sceneStemWidth','stemWidth'],['sceneLeafWidth','leafWidth']])$(id).oninput=()=>{if($(id).value!==''&&$(id).validity.valid)edit(()=>current().params[key]=Number($(id).value));};
  $('sceneVarySpots').onclick=()=>edit(()=>{delete current().params.spotMap;delete current().params.spotDetails;current().params.spotSeed=((current().params.spotSeed||0)+1)%1000;});
  async function openLeaves(){
    const item=current();if(!item||item.kind!=='branch'||item.pinned)return;
    if(!item.params.leafMap||item.params.profile!=='botanical'){
      const active=session,id=item.id,run=generation;
      try{const result=await ctx.api('/api/components',{action:'branch-layout',params:item.params});if(active!==session||run!==generation||current()?.id!==id)return;edit(()=>item.params=result.params);}
      catch(e){$('sceneError').textContent=e.message;return;}
    }
    selectedLeaf=item.params.leafMap[0]?.id;setMode('leaves');focusBranch();
  }
  function focusBranch(){
    const item=current(),placement=leafPlacement();if(!item?.params.leafMap)return;if(!placement){focusPending=true;return;}focusPending=false;
    const p=item.params,frame=branchFrame(item,placement),pts=[...p.stemCurve,...p.leafMap.flatMap(l=>[l.base,l.tip])].map(frame.toWorld);
    const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),x=Math.min(...xs),y=Math.min(...ys),w=Math.max(...xs)-x,h=Math.max(...ys)-y,size=clamp(Math.max(w,h)+6,15,100);
    view={x:x+w/2-size/2,y:y+h/2-size/2,w:size,h:size};draw();
  }
  $('sceneLeafMode').onclick=openLeaves;
  $('sceneLeafFocus').onclick=focusBranch;
  async function previewMotif(button,kind){
    if(!proposal?.fits||proposedGeneration!==generation)return;
    const active=session,gen=generation,run=++stitchToken,item=current();previewItem=item.id;button.disabled=true;
    $('sceneStatus').textContent='Generating actual stitches for '+item.name+'…';
    try{
      const result=await ctx.api('/api/layer-preview',{layers:proposal.layers.filter(l=>l.sceneBinding?.guideId===guide.id&&l.sceneBinding.itemId===selected)});
      if(active!==session||gen!==generation||run!==stitchToken||current()?.id!==item.id||!$('sceneDialog').open)return;
      preview=result.preview;$('sceneStitchMode').disabled=false;
      $('sceneStatus').textContent=`${item.name} · ${preview.stitches.toLocaleString()} actual ${kind} stitches · ${preview.width} × ${preview.height} mm`;setMode('stitches');
    }catch(e){if(active===session)$('sceneError').textContent=e.message;}
    finally{if(active===session)button.disabled=!proposal?.fits||proposedGeneration!==generation;}
  }
  $('sceneLeafPreview').onclick=()=>previewMotif($('sceneLeafPreview'),'branch');
  $('sceneSpotPreview').onclick=()=>previewMotif($('sceneSpotPreview'),'mushroom');
  $('sceneLeafBranch').onchange=()=>{chooseItem($('sceneLeafBranch').value);if(current().pinned)setMode('motifs');else openLeaves();};
  $('sceneBlade').onchange=()=>{selectedLeaf=$('sceneBlade').value;fields();draw();};
  for(const[id,key,axis]of [['sceneBladeBaseX','base',0],['sceneBladeBaseY','base',1],['sceneBladeTipX','tip',0],['sceneBladeTipY','tip',1]])$(id).oninput=()=>{const input=$(id);if(input.value!==''&&input.validity.valid)edit(()=>blade()[key][axis]=Number(input.value)/(axis?current().params.height:current().params.width));};
  for(const[id,key,factor]of [['sceneBladeBend','bend',1],['sceneBladeJoin','join',.01],['sceneBladeWidth','width',null]])$(id).oninput=()=>{const input=$(id);if(input.value!==''&&input.validity.valid)edit(()=>blade()[key]=Number(input.value)*(factor??1/current().params.width));};
  $('sceneBladeSplit').onchange=()=>edit(()=>blade().split=$('sceneBladeSplit').checked);
  for(const[id,key]of [['sceneBladeDarkColor','leafColor'],['sceneBladeLightColor','lightColor']])$(id).onchange=()=>edit(()=>current().params[key]=$(id).value);
  $('sceneStemPoint').onchange=leafFields;
  for(const[id,axis]of [['sceneStemX',0],['sceneStemY',1]])$(id).oninput=()=>{const input=$(id);if(input.value!==''&&input.validity.valid)edit(()=>current().params.stemCurve[Number($('sceneStemPoint').value)][axis]=Number(input.value)/(axis?current().params.height:current().params.width));};
  function addLeaf(duplicate=false){edit(()=>{
    const p=current().params;if(p.leafMap.length>=12)throw new Error('Keep at most 12 leaves per branch.');
    const i=duplicate?clone(blade()):{base:[.5,.5],tip:[.8,.2],width:.14,bend:.04,join:.5,split:true};
    i.id=crypto.randomUUID().slice(0,8);i.name=duplicate?i.name+' copy':`Leaf ${p.leafMap.length+1}`;
    if(duplicate)i.tip[1]=clamp(i.tip[1]-.06,-.5,1.5);
    p.leafMap.push(i);selectedLeaf=i.id;
  });}
  $('sceneAddLeaf').onclick=()=>addLeaf();$('sceneDuplicateLeaf').onclick=()=>addLeaf(true);
  $('sceneRemoveLeaf').onclick=()=>{if(current().params.leafMap.length>1)edit(()=>current().params.leafMap=current().params.leafMap.filter(l=>l.id!==selectedLeaf));};
  function add(kind){if(kind==='motif'&&!$('sceneMotifChoice').value){$('sceneError').textContent='Save a motif first: select shapes, then Layer → Save selection as motif.';return;}edit(()=>{const item={id:crypto.randomUUID(),kind,name:`${kind==='branch'?'Branch':kind==='motif'?$('sceneMotifChoice').selectedOptions[0].textContent:'Mushroom'} ${guide.scene.items.length+1}`,t:.5,offset:0,scale:1,angle:0,follow:.4,params:kind==='motif'?{motif:$('sceneMotifChoice').value,width:16}:{width:12,height:18,profile:guide.scene.style==='any'?'classic':guide.scene.style||'classic',...(kind==='mushroom'?{spots:4}:{})},autoFit:true};guide.scene.items.push(item);selected=item.id;});}
  $('sceneAddMushroom').onclick=()=>add('mushroom');$('sceneAddMotif').onclick=()=>add('motif');$('sceneAddBranch').onclick=()=>add('branch');
  $('sceneDuplicate').onclick=()=>{if(current())edit(()=>{const i=clone(current());i.id=crypto.randomUUID();i.name+=' copy';i.t=clamp(i.t+.05,0,1);i.pinned=false;guide.scene.items.push(i);selected=i.id;});};
  $('sceneRemove').onclick=()=>{if(guide.scene.items.length>1)edit(()=>{guide.scene.items=guide.scene.items.filter(i=>i.id!==selected);selected=guide.scene.items[0].id;});else $('sceneError').textContent='Keep at least one motif in the scene.';};
  for(const[id,delta]of [['sceneEarlier',-1],['sceneLater',1]])$(id).onclick=()=>{const a=guide.scene.items,i=a.findIndex(x=>x.id===selected),j=i+delta;if(j>=0&&j<a.length)edit(()=>[a[i],a[j]]=[a[j],a[i]]);};
  $('sceneMotifMode').onclick=()=>setMode('motifs');$('sceneGuideMode').onclick=()=>setMode('guide');$('sceneStitchMode').onclick=()=>setMode('stitches');
  $('sceneNode').onchange=()=>{nodeIndex=Number($('sceneNode').value);fields();draw();};
  for(const[id,key]of [['sceneNodeX','x'],['sceneNodeY','y']])$(id).oninput=()=>{if($(id).value!==''&&$(id).validity.valid)curveEdit(c=>{const n=c.nodes[nodeIndex],delta=Number($(id).value)-n[key],axis=key==='x'?0:1;n[key]+=delta;n.in[axis]+=delta;n.out[axis]+=delta;});};
  $('sceneInsertNode').onclick=()=>curveEdit(c=>{const i=Math.min(nodeIndex,c.nodes.length-2);splitSegment(c,i);nodeIndex=i+1;});
  $('sceneRemoveNode').onclick=()=>{if(worldContours(guide)[0].nodes.length>2)curveEdit(c=>c.nodes.splice(nodeIndex,1));};
  $('sceneSmoothNode').onclick=()=>curveEdit(c=>smoothNode(c,nodeIndex));
  $('sceneUndo').onclick=()=>{if(history.length){future.push(capture());const state=history.pop();guide=state.guide;project=state.project;stateChanged();fields();}};
  $('sceneRedo').onclick=()=>{if(future.length){history.push(capture());const state=future.pop();guide=state.guide;project=state.project;stateChanged();fields();}};
  $('sceneReflow').onclick=()=>{clearTimeout(timer);refresh();};
  $('scenePreviewStitches').onclick=async()=>{
    if(!proposal?.fits||proposedGeneration!==generation)return;
    previewItem=null;
    const run=++stitchToken,gen=generation,active=session;$('scenePreviewStitches').disabled=true;
    try{
      const job=await ctx.api('/api/export',{project:{...project,layers:proposal.layers}});
      while(run===stitchToken&&gen===generation&&active===session&&$('sceneDialog').open){
        const state=await ctx.api('/api/jobs/'+job.id);$('sceneStatus').textContent=state.message;
        if(state.state==='error')throw new Error(state.message);
        if(state.state==='done'){preview=state.result.preview;$('sceneStitchMode').disabled=false;$('sceneStatus').textContent=`${preview.stitches.toLocaleString()} actual stitches · ${preview.width} × ${preview.height} mm · ${proposal.count} editable motifs`;setMode('stitches');break;}
        await new Promise(r=>setTimeout(r,700));
      }
    }catch(e){if(active===session)$('sceneError').textContent=e.message;}
    finally{if(active===session)$('scenePreviewStitches').disabled=!proposal?.fits||proposedGeneration!==generation;}
  };
  $('applyScene').onclick=()=>{
    try{if(!fresh()||!proposal?.fits||proposedGeneration!==generation)throw new Error('The scene changed. Reflow it again before applying.');
      const result=clone(proposal);ctx.mutate(()=>{ctx.getProject().layers=result.layers;ctx.select([result.guide.id]);});$('sceneDialog').close();ctx.setTab('layer');ctx.toast('Editable scene applied. Select Scene to edit its guide and attachments. Undo restores the previous layout.');
    }catch(e){$('sceneError').textContent=e.message;}
  };
  for(const id of ['closeScene','cancelScene'])$(id).onclick=()=>$('sceneDialog').close();
  $('sceneDialog').addEventListener('close',()=>{session++;stitchToken++;clearTimeout(timer);pointers.clear();drag=null;});
  const svgPoint=e=>{const p=$('sceneCanvas').createSVGPoint();p.x=e.clientX;p.y=e.clientY;const q=p.matrixTransform($('sceneCanvas').getScreenCTM().inverse());return[q.x,q.y];};
  $('sceneCanvas').addEventListener('pointerdown',e=>{
    if(e.button!==0||!penGate.down(e,performance.now()))return;
    if(e.pointerType==='pen'&&pointers.size){if(drag?.before)guide=drag.before;pointers.clear();drag=null;}
    e.preventDefault();$('sceneCanvas').setPointerCapture(e.pointerId);pointers.set(e.pointerId,[e.clientX,e.clientY]);
    if(pointers.size===2){if(drag?.before)guide=drag.before;const[a,b]=[...pointers.values()];drag={kind:'pinch',distance:Math.hypot(a[0]-b[0],a[1]-b[1]),view:{...view},anchor:svgPoint({clientX:(a[0]+b[0])/2,clientY:(a[1]+b[1])/2})};return;}
    if(pointers.size>1||!guide)return;
    if(ctx.penInput&&!ctx.penInput.canDraw(e)){drag={kind:'pan',start:[e.clientX,e.clientY],view:{...view}};return;}
    const n=e.target.closest('[data-guide-node]'),h=e.target.closest('[data-guide-handle]'),item=e.target.closest('[data-scene-item]'),leaf=e.target.closest('[data-leaf-point]'),stem=e.target.closest('[data-stem-control]'),dot=e.target.closest('[data-spot-id]');
    if(mode==='spots'&&dot){
      if(current().pinned||!proposal)return;selectedSpot=dot.dataset.spotId;
      drag={kind:'spot',frame:mushroomFrame(current(),leafPlacement()),start:svgPoint(e),before:snapshot(),changed:false};fields();draw();
    }
    else if(mode==='leaves'&&(leaf||stem)){
      if(current().pinned||!proposal)return;
      if(leaf)selectedLeaf=leaf.dataset.leafId;
      if(stem)$('sceneStemPoint').value=stem.dataset.stemControl;
      drag={kind:leaf?'leaf':'stem',point:leaf?.dataset.leafPoint,index:stem?Number(stem.dataset.stemControl):null,frame:branchFrame(current(),leafPlacement()),before:snapshot(),changed:false};fields();draw();
    }
    else if(mode==='guide'&&(n||h)){nodeIndex=Number(n?n.dataset.guideNode:h.dataset.nodeIndex);drag={kind:'node',handle:h?.dataset.guideHandle,start:svgPoint(e),before:snapshot(),changed:false};fields();draw();}
    else if(item&&mode==='motifs'){chooseItem(item.dataset.sceneItem);const anchor=proposal?.placements.find(p=>p.itemId===selected)?.anchor||guidePoint(sampleGuide(worldContours(guide)),current().t,current().offset);drag=current()?.pinned?null:{kind:'item',before:snapshot(),changed:false,start:svgPoint(e),anchor};fields();draw();}
    else drag={kind:'pan',start:[e.clientX,e.clientY],view:{...view}};
  });
  $('sceneCanvas').addEventListener('pointermove',e=>{
    if(!pointers.has(e.pointerId)||!drag)return;e.preventDefault();pointers.set(e.pointerId,[e.clientX,e.clientY]);
    if(drag.kind==='pinch'&&pointers.size===2){const[a,b]=[...pointers.values()],r=$('sceneCanvas').getBoundingClientRect(),w=clamp(drag.view.w*drag.distance/Math.max(1,Math.hypot(a[0]-b[0],a[1]-b[1])),15,180),scale=Math.min(r.width/w,r.height/w);view={x:drag.anchor[0]-((a[0]+b[0])/2-r.x-(r.width-w*scale)/2)/scale,y:drag.anchor[1]-((a[1]+b[1])/2-r.y-(r.height-w*scale)/2)/scale,w,h:w};draw();return;}
    if(pointers.size>1)return;
    if(drag.kind==='pan'){const r=$('sceneCanvas').getBoundingClientRect(),scale=Math.max(view.w/r.width,view.h/r.height);view.x=drag.view.x-(e.clientX-drag.start[0])*scale;view.y=drag.view.y-(e.clientY-drag.start[1])*scale;draw();return;}
    const p=svgPoint(e);guide=clone(drag.before);
    if(drag.kind==='node'){
      const c=worldContours(guide),n=c[0].nodes[nodeIndex];
      if(drag.handle)n[drag.handle]=[clamp(p[0],-100,200),clamp(p[1],-100,200)];
      else{const dx=clamp(n.x+p[0]-drag.start[0],0,100)-n.x,dy=clamp(n.y+p[1]-drag.start[1],0,100)-n.y;n.x+=dx;n.y+=dy;n.in=n.in.map((v,i)=>v+(i?dy:dx));n.out=n.out.map((v,i)=>v+(i?dy:dx));}
      guide=packContours(c,guide);
    }else if(drag.kind==='spot'){
      const a=drag.frame.fromWorld(drag.start),b=drag.frame.fromWorld(p),params=current().params;
      transformSpot(params,spot(),{dx:(b[0]-a[0])*params.width,dy:(b[1]-a[1])*params.height});
    }else if(drag.kind==='leaf'||drag.kind==='stem'){
      const q=drag.frame.fromWorld(p).map(v=>clamp(v,-.5,1.5));
      if(drag.kind==='leaf')blade()[drag.point]=q;else current().params.stemCurve[drag.index]=q;
    }else{const destination=[drag.anchor[0]+p[0]-drag.start[0],drag.anchor[1]+p[1]-drag.start[1]],projected=projectToGuide(sampleGuide(worldContours(guide)),destination);Object.assign(current(),{t:projected.t,offset:clamp(projected.offset,-30,30)});}
    drag.changed=true;if(proposal)lastArt=proposal.layers;proposal=null;$('applyScene').disabled=true;draw();fields();
  });
  function finish(e,cancel=false){
    penGate.end(e,performance.now());
    pointers.delete(e.pointerId);if(!drag)return;
    if(drag.kind==='pinch'){if(!pointers.size){drag=null;draw();if(!proposal)queueLayout();}return;}
    if(cancel&&drag.before)guide=drag.before;
    else if(drag.changed){history.push({guide:drag.before,project:clone(project)});if(history.length>35)history.shift();future=[];stateChanged();}
    drag=null;fields();draw();
  }
  $('sceneCanvas').addEventListener('pointerup',e=>finish(e));$('sceneCanvas').addEventListener('pointercancel',e=>finish(e,true));
  for(const[id,factor]of [['sceneZoomOut',1.25],['sceneZoomIn',.8]])$(id).onclick=()=>{const w=clamp(view.w*factor,15,180);view={x:view.x+(view.w-w)/2,y:view.y+(view.h-w)/2,w,h:w};draw();};
  $('sceneZoomFit').onclick=()=>{view={x:-3,y:-3,w:106,h:106};draw();};
  new ResizeObserver(()=>{if($('sceneDialog').open)draw();}).observe($('sceneCanvas'));
  function mount(host){host.insertAdjacentHTML('beforeend','<button id="openSceneEditor" class="wide">Scene editor · guide & motifs</button>');$('openSceneEditor').onclick=open;}
  return {open,mount};
}
