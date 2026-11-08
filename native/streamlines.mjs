import {pathD} from './paths.mjs';
import {drawPlan} from './advanced.mjs';

const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SHAPE_KEYS=['type','width','height','radius','contours','points','closed'];
export const isStreamlines=l=>l?.stitch==='fill'&&l.fillMethod==='streamline_fill';
export const isFlowFill=l=>l?.stitch==='fill'&&['streamline_fill','wave_fill'].includes(l.fillMethod);
export const flowName=l=>l?.fillMethod==='wave_fill'?'Wave Fill':'Streamlines';
export const defaultFlow=()=>({separation:1.2,guides:[{id:'flow-1',points:[[.12,.65],[.5,.35],[.88,.5]]}]});
const shapeKey=l=>Object.fromEntries(SHAPE_KEYS.map(k=>[k,l[k]??null]));
export function validStreamlinePreview(l){const c=l.streamlinePreview;return !!c&&(c.method||'streamline_fill')===l.fillMethod&&JSON.stringify(c.shape)===JSON.stringify(shapeKey(l))&&JSON.stringify(c.settings)===JSON.stringify(l.streamlines);}
export function outlineD(l){
  const w=l.width,h=l.height;
  if(l.contours)return pathD(l.contours,w,h);
  if(l.type==='ellipse')return `M0 ${h/2} A${w/2} ${h/2} 0 1 0 ${w} ${h/2} A${w/2} ${h/2} 0 1 0 0 ${h/2} Z`;
  if(l.type==='path')return l.points.map((p,i)=>`${i?'L':'M'}${p[0]*w} ${p[1]*h}`).join(' ')+' Z';
  const r=Math.min(l.radius||0,w/2,h/2);return `M${r} 0 H${w-r} Q${w} 0 ${w} ${r} V${h-r} Q${w} ${h} ${w-r} ${h} H${r} Q0 ${h} 0 ${h-r} V${r} Q0 0 ${r} 0 Z`;
}
export function flowContour(guide,w,h){return {closed:false,nodes:guide.points.map((p,i,all)=>{const a=all[Math.max(0,i-1)],b=all[Math.min(all.length-1,i+1)],x=p[0]*w,y=p[1]*h,dx=(b[0]-a[0])*w/6,dy=(b[1]-a[1])*h/6;return {x,y,in:[x-dx,y-dy],out:[x+dx,y+dy]};})};}
export function streamlineMarkup(l){
  if(!isFlowFill(l))return '';
  return `<path d="${esc(outlineD(l))}" fill="${esc(l.color)}" fill-opacity=".06" fill-rule="evenodd" stroke="${esc(l.color)}" stroke-opacity=".35" stroke-width=".12"/>`+(validStreamlinePreview(l)?`<path d="${esc(l.streamlinePreview.d)}" fill="none" stroke="${esc(l.color)}" stroke-width=".16" stroke-linecap="round"/>`:'');
}
export function streamlineArtwork(l,node){if(!isFlowFill(l))return null;const g=node('g');g.innerHTML=streamlineMarkup(l);return g;}
export function applyStreamlines(project,id,proposal){
  const index=project.layers.findIndex(l=>l.id===id),source=project.layers[index];
  if(!source)throw new Error('The source shape was removed. Reopen the flow-field fill.');
  if(source.locked||source.link||source.linkedHelper)throw new Error('Unlock or detach the source shape first.');
  project.layers[index]={...structuredClone(proposal.layer),id};return id;
}

export function createStreamlines(ctx){
  const $=id=>document.getElementById(id);let source,params,method='streamline_fill',selected=0,point=0,pid,revision,result=null,token=0,busy=false,pending=null,undo=[],redo=[],view,drag=null,pinch=null;
  const pointers=new Map();
  document.body.insertAdjacentHTML('beforeend',`<dialog id="streamlinesDialog" class="streamlines-dialog" aria-labelledby="streamlinesTitle"><div class="dialog-heading"><div><span class="eyebrow">FLOW-FIELD FILLS</span><h2 id="streamlinesTitle">Streamlines.</h2></div><button id="closeStreamlines" class="icon-button" aria-label="Close flow-field fill">×</button></div>
  <p id="flowSource" class="caption"></p><form id="streamlinesForm"><div class="flow-workspace"><section class="flow-stage"><div class="button-row"><button id="flowGuidesTab" type="button" aria-pressed="true">Flow guides</button><button id="flowStitchesTab" type="button" aria-pressed="false" disabled>Actual stitches</button></div>
  <div id="flowEditor"><svg id="flowSvg" role="img" aria-label="Flow guides: drag points, tap to draw a guide, pinch to zoom"></svg><div class="button-row flow-zoom"><button id="flowZoomOut" type="button" aria-label="Zoom out flow guides">−</button><button id="flowFit" type="button">Fit shape</button><button id="flowZoomIn" type="button" aria-label="Zoom in flow guides">＋</button></div></div><canvas id="flowCanvas" aria-label="Actual Streamlines stitches" hidden></canvas><p id="flowInstruction" class="caption">Drag the teal points to bend a guide. Add more guides to steer nearby stitches. Drag empty space to pan; pinch to zoom.</p><p id="flowStats" class="caption" role="status">Preview to generate stitches.</p></section>
  <fieldset id="flowFields"><legend class="sr-only">Flow-field fill settings</legend><label>Fill style<select id="flowMethod"><option value="streamline_fill">Streamlines</option><option value="wave_fill">Wave Fill</option></select></label><p id="flowMethodHelp" class="caption"></p><div class="field-row"><label>Separation (mm)<input id="flowSeparation" type="number" min="0.4" max="8" step="any" required></label><label>Stitch length (mm)<input id="flowLength" type="number" min="0.5" max="6" step="any" required></label></div><label>Thread color<input id="flowColor" type="color"></label><p class="caption">Smaller separation packs lines closer together. Guides do not sew themselves. Paths stop at the boundary and avoid holes.</p>
  <label>Selected guide<select id="flowGuide"></select></label><div class="button-row"><button id="flowAddGuide" type="button">＋ Draw guide</button><button id="flowRemoveGuide" type="button">Remove guide</button></div><div id="flowDrawing" hidden><p class="caption">Tap at least two points, then finish. The curve passes smoothly through your points.</p><div class="button-row"><button id="flowFinishGuide" type="button">Finish guide</button><button id="flowCancelGuide" type="button">Cancel guide</button></div></div>
  <label>Selected point<select id="flowPoint"></select></label><div class="field-row"><label>Point X (%)<input id="flowX" type="number" min="-50" max="150" step="any"></label><label>Point Y (%)<input id="flowY" type="number" min="-50" max="150" step="any"></label></div><div class="button-row"><button id="flowInsertPoint" type="button">Insert point</button><button id="flowRemovePoint" type="button">Remove point</button></div><div class="button-row"><button id="flowUndo" type="button">Undo guide edit</button><button id="flowRedo" type="button">Redo guide edit</button></div></fieldset></div>
  <p id="flowError" class="error" role="alert"></p><div class="dialog-footer"><button id="cancelStreamlines" type="button">Cancel</button><button id="previewStreamlines" class="primary">Preview stitches</button><button id="applyStreamlines" class="primary" type="button" disabled>Apply Streamlines</button></div></form></dialog>`);
  const fresh=()=>ctx.getProject().id===pid&&ctx.getRevision()===revision;
  function tab(stitches){$('flowEditor').hidden=stitches;$('flowCanvas').hidden=!stitches;$('flowGuidesTab').setAttribute('aria-pressed',String(!stitches));$('flowStitchesTab').setAttribute('aria-pressed',String(stitches));if(stitches&&result)drawPlan($('flowCanvas'),result.preview);}
  function invalidate(){token++;result=null;$('flowError').textContent='';$('flowStats').textContent='Preview to generate the current flow.';$('flowStitchesTab').disabled=true;$('applyStreamlines').disabled=true;tab(false);}
  function working(on){busy=on;$('flowFields').disabled=on;$('previewStreamlines').disabled=on;$('applyStreamlines').disabled=on||!result;$('previewStreamlines').textContent=on?'Preparing stitches…':'Preview stitches';}
  function methodControls(){const name=flowName({fillMethod:method});$('streamlinesTitle').textContent=name+'.';$('flowCanvas').setAttribute('aria-label',`Actual ${name} stitches`);$('applyStreamlines').textContent='Apply '+name;$('flowMethod').value=method;$('flowMethodHelp').textContent=method==='wave_fill'?'Coordinated bands bend through the field. Guide changes spread smoothly across neighboring waves.':'Individual paths trace the field. Add curves to steer nearby stitch directions.';}
  const snapshot=()=>JSON.stringify(params.guides);
  function record(before){if(before===snapshot())return;undo.push(before);if(undo.length>60)undo.shift();redo=[];invalidate();}
  function action(fn){const before=snapshot();fn();record(before);controls();draw();}
  function controls(){
    selected=Math.max(0,Math.min(selected,params.guides.length-1));const guide=params.guides[selected];point=Math.max(0,Math.min(point,guide.points.length-1));
    $('flowGuide').innerHTML=params.guides.map((g,i)=>`<option value="${i}">Guide ${i+1} · ${g.points.length} points</option>`).join('');$('flowGuide').value=selected;
    $('flowPoint').innerHTML=guide.points.map((p,i)=>`<option value="${i}">Point ${i+1}</option>`).join('');$('flowPoint').value=point;
    $('flowX').value=Number((guide.points[point][0]*100).toFixed(2));$('flowY').value=Number((guide.points[point][1]*100).toFixed(2));
    $('flowRemoveGuide').disabled=params.guides.length<=1||pending!==null;$('flowAddGuide').disabled=params.guides.length>=12||pending!==null;
    $('flowRemovePoint').disabled=guide.points.length<=2||pending!==null;$('flowInsertPoint').disabled=guide.points.length>=32||pending!==null;
    for(const id of ['flowGuide','flowPoint','flowX','flowY'])$(id).disabled=pending!==null;
    $('flowDrawing').hidden=pending===null;$('flowFinishGuide').disabled=!pending||pending.length<2;
    $('flowUndo').disabled=!undo.length||pending!==null;$('flowRedo').disabled=!redo.length||pending!==null;
    $('flowInstruction').textContent=pending===null?'Drag the teal points to bend a guide. Drag empty space to pan; pinch to zoom.':`Tap points for the new guide (${pending.length}/32). Finish guide when its curve is ready.`;
  }
  function draw(){
    const svg=$('flowSvg');svg.setAttribute('viewBox',`${view.x} ${view.y} ${view.w} ${view.h}`);
    const scale=svg.getScreenCTM()?.a||5,r=22/scale,ns=source.width,nh=source.height;
    const guidePaths=params.guides.map((g,i)=>`<path d="${esc(pathD([flowContour(g,ns,nh)]))}" fill="none" stroke="${i===selected?'#008b91':'#6b92a0'}" stroke-width="${2.5/scale}"/>`+g.points.map((p,j)=>`<circle data-guide="${i}" data-point="${j}" cx="${p[0]*ns}" cy="${p[1]*nh}" r="${r}" fill="transparent"/><circle cx="${p[0]*ns}" cy="${p[1]*nh}" r="${(i===selected&&j===point?6:4.5)/scale}" fill="${i===selected&&j===point?'#ee9f35':'#fff'}" stroke="#00777e" stroke-width="${2/scale}" pointer-events="none"/>`).join('')).join('');
    const draft=pending?.length?`<path d="${esc(pathD([flowContour({points:pending},ns,nh)]))}" fill="none" stroke="#d38624" stroke-width="${2.5/scale}"/>`+pending.map(p=>`<circle cx="${p[0]*ns}" cy="${p[1]*nh}" r="${5/scale}" fill="#d38624"/>`).join(''):'';
    svg.innerHTML=`<defs><clipPath id="flowClip"><path d="${esc(outlineD(source))}" fill-rule="evenodd" clip-rule="evenodd"/></clipPath></defs><path d="${esc(outlineD(source))}" fill="#f3efe2" fill-rule="evenodd" stroke="#9baba5" stroke-width="${1/scale}"/>${result?`<path d="${esc(result.layer.streamlinePreview.d)}" fill="none" stroke="${esc($('flowColor').value)}" stroke-width=".14" clip-path="url(#flowClip)"/>`:''}${guidePaths}${draft}`;
  }
  function fit(){const pad=Math.max(source.width,source.height)*.09;view={x:-pad,y:-pad,w:source.width+pad*2,h:source.height+pad*2};draw();}
  function zoom(factor,center=null){const c=center||[view.x+view.w/2,view.y+view.h/2],nw=Math.max(source.width/8,Math.min(source.width*3,view.w*factor)),ratio=nw/view.w;view={x:c[0]+(view.x-c[0])*ratio,y:c[1]+(view.y-c[1])*ratio,w:nw,h:view.h*ratio};draw();}
  function coord(e){const p=new DOMPoint(e.clientX,e.clientY).matrixTransform($('flowSvg').getScreenCTM().inverse());return [p.x,p.y];}
  function open(layer=ctx.chosen()[0],requestedMethod=null){
    if(!layer||ctx.chosen().length!==1||!['path','rectangle','ellipse'].includes(layer.type))return ctx.toast('Select one closed native shape for a flow-field fill.');
    if(layer.locked||layer.visible===false||layer.link||layer.linkedHelper||layer.role&&layer.role!=='artwork')return ctx.toast('Show, unlock or detach the selected shape first.');
    if(layer.type==='path'&&(layer.contours?.some(c=>!c.closed)||!layer.contours&&!layer.closed&&layer.stitch!=='fill'))return ctx.toast('Close the outline before adding a flow-field fill.');
    source=structuredClone(layer);method=requestedMethod||(isFlowFill(layer)?layer.fillMethod:'streamline_fill');params=structuredClone(layer.streamlines||defaultFlow());selected=0;point=0;pending=null;undo=[];redo=[];pointers.clear();drag=null;pinch=null;
    pid=ctx.getProject().id;revision=ctx.getRevision();$('flowSource').textContent=`${layer.name} · Draw guides through the shape to steer its fill.`;
    $('flowSeparation').value=params.separation;$('flowLength').value=layer.stitchLength||2.5;$('flowColor').value=layer.color;methodControls();working(false);invalidate();controls();$('streamlinesDialog').showModal();fit();
  }
  $('flowMethod').onchange=()=>{method=$('flowMethod').value;methodControls();invalidate();draw();};
  $('flowGuidesTab').onclick=()=>{tab(false);draw();};$('flowStitchesTab').onclick=()=>{if(result)tab(true);};
  $('flowGuide').onchange=()=>{selected=Number($('flowGuide').value);point=0;controls();draw();};$('flowPoint').onchange=()=>{point=Number($('flowPoint').value);controls();draw();};
  for(const [id,axis]of [['flowX',0],['flowY',1]])$(id).onchange=()=>{const input=$(id);if(input.value===''||!input.validity.valid)return;action(()=>params.guides[selected].points[point][axis]=Number(input.value)/100);};
  $('flowAddGuide').onclick=()=>{pending=[];invalidate();controls();draw();};$('flowCancelGuide').onclick=()=>{pending=null;controls();draw();};
  $('flowFinishGuide').onclick=()=>{if(pending?.length>=2)action(()=>{params.guides.push({id:crypto.randomUUID(),points:pending});selected=params.guides.length-1;point=0;pending=null;});};
  $('flowRemoveGuide').onclick=()=>action(()=>{if(params.guides.length>1)params.guides.splice(selected,1);point=0;});
  $('flowInsertPoint').onclick=()=>action(()=>{const pts=params.guides[selected].points,j=Math.min(point,pts.length-2);pts.splice(j+1,0,[(pts[j][0]+pts[j+1][0])/2,(pts[j][1]+pts[j+1][1])/2]);point=j+1;});
  $('flowRemovePoint').onclick=()=>action(()=>{const pts=params.guides[selected].points;if(pts.length>2)pts.splice(point,1);});
  function history(back){const from=back?undo:redo,to=back?redo:undo;if(!from.length)return;to.push(snapshot());params.guides=JSON.parse(from.pop());invalidate();controls();draw();}
  $('flowUndo').onclick=()=>history(true);$('flowRedo').onclick=()=>history(false);
  for(const id of ['flowSeparation','flowLength','flowColor'])$(id).oninput=()=>{invalidate();draw();};
  $('flowFit').onclick=fit;$('flowZoomIn').onclick=()=>zoom(.8);$('flowZoomOut').onclick=()=>zoom(1.25);
  const svg=$('flowSvg');
  svg.onpointerdown=e=>{
    if(busy||e.button>0)return;e.preventDefault();svg.setPointerCapture(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
    if(pointers.size===2){if(drag?.before){params.guides=JSON.parse(drag.before);controls();draw();}drag=null;const[a,b]=[...pointers.values()];pinch={distance:Math.hypot(a.x-b.x,a.y-b.y),view:{...view},center:coord({clientX:(a.x+b.x)/2,clientY:(a.y+b.y)/2})};return;}
    if(pointers.size>1)return;
    const p=coord(e),target=e.target.closest('[data-guide]');
    if(pending===null&&target){selected=Number(target.dataset.guide);point=Number(target.dataset.point);drag={kind:'point',before:snapshot(),start:p};controls();draw();}
    else drag={kind:pending!==null?'add':'pan',start:p,client:[e.clientX,e.clientY],view:{...view},moved:false};
  };
  svg.onpointermove=e=>{
    if(!pointers.has(e.pointerId))return;e.preventDefault();pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
    if(pointers.size>=2&&pinch){const[a,b]=[...pointers.values()],ratio=pinch.distance/(Math.hypot(a.x-b.x,a.y-b.y)||1);view={...pinch.view};zoom(ratio,pinch.center);return;}
    if(!drag||pinch)return;const p=coord(e);
    if(drag.kind==='point'){params.guides[selected].points[point]=[Math.max(-.5,Math.min(1.5,p[0]/source.width)),Math.max(-.5,Math.min(1.5,p[1]/source.height))];invalidate();controls();draw();}
    else{drag.moved ||= Math.hypot(e.clientX-drag.client[0],e.clientY-drag.client[1])>7;if(drag.kind==='pan'){const scale=svg.getScreenCTM().a;view={...drag.view,x:drag.view.x-(e.clientX-drag.client[0])/scale,y:drag.view.y-(e.clientY-drag.client[1])/scale};draw();}}
  };
  function release(e,cancel=false){
    if(!pointers.has(e.pointerId))return;pointers.delete(e.pointerId);
    if(pinch){if(!pointers.size)pinch=null;drag=null;return;}
    if(drag?.kind==='point'){if(cancel)params.guides=JSON.parse(drag.before);else record(drag.before);}
    else if(!cancel&&drag?.kind==='add'&&!drag.moved&&pending!==null&&pending.length<32){const p=coord(e);pending.push([Math.max(0,Math.min(1,p[0]/source.width)),Math.max(0,Math.min(1,p[1]/source.height))]);}
    drag=null;controls();draw();
  }
  svg.onpointerup=e=>release(e);svg.onpointercancel=e=>release(e,true);
  svg.onwheel=e=>{e.preventDefault();zoom(e.deltaY>0?1.1:.9,coord(e));};
  $('streamlinesForm').onsubmit=async e=>{
    e.preventDefault();if(busy)return;invalidate();const run=token;
    try{
      if(!fresh())throw new Error('The design changed. Reopen the flow-field fill.');if(pending!==null)throw new Error('Finish or cancel the new guide before previewing.');
      for(const id of ['flowSeparation','flowLength'])if(!$(id).validity.valid||$(id).value==='')throw new Error('Check separation and stitch length.');
      params.separation=Number($('flowSeparation').value);working(true);
      const proposal=await ctx.api('/api/flow-fill',{layer:source,method,settings:params,stitchLength:Number($('flowLength').value),color:$('flowColor').value});
      if(run!==token||!$('streamlinesDialog').open)return;if(!fresh())throw new Error('The design changed. Reopen the flow-field fill.');
      result=proposal;const p=proposal.preview;$('flowStats').textContent=`${proposal.stats.lines} ${method==='wave_fill'?'wave lines':'streamlines'} · ${p.stitches.toLocaleString()} stitches · ${p.trims} cuts · ${p.width} × ${p.height} mm`;
      $('flowStitchesTab').disabled=false;draw();tab(true);
    }catch(error){if(run===token)$('flowError').textContent=error.message;}
    finally{if(run===token)working(false);}
  };
  $('applyStreamlines').onclick=()=>{
    try{if(!result||busy||!fresh())throw new Error('Preview the current flow before applying.');const draft=structuredClone(ctx.getProject()),id=applyStreamlines(draft,source.id,result);ctx.mutate(()=>{Object.assign(ctx.getProject(),draft);ctx.select([id]);});$('streamlinesDialog').close();ctx.setTab('layer');ctx.toast(flowName(result.layer)+' applied. Edit flow guides here to change the fill.');}
    catch(error){$('flowError').textContent=error.message;}
  };
  for(const id of ['closeStreamlines','cancelStreamlines'])$(id).onclick=()=>$('streamlinesDialog').close();$('streamlinesDialog').onclose=()=>{token++;busy=false;pointers.clear();drag=null;pinch=null;};
  new ResizeObserver(()=>{if($('streamlinesDialog').open){draw();if(result&&!$('flowCanvas').hidden)drawPlan($('flowCanvas'),result.preview);}}).observe(svg);
  function mount(host,layer=null){
    if(layer&&(!['path','rectangle','ellipse'].includes(layer.type)||layer.role&&layer.role!=='artwork'))return;
    const button=document.createElement('button');button.id=layer?'editStreamlines':'openStreamlines';button.type='button';button.className='wide'+(isFlowFill(layer)?' primary':'');button.textContent=isFlowFill(layer)?`Edit ${flowName(layer)} flow guides`:'Streamlines & Wave Fill';button.onclick=()=>open(layer||ctx.chosen()[0]);
    if(!layer){const list=ctx.chosen();button.disabled=list.length!==1||!['path','rectangle','ellipse'].includes(list[0].type);host.append(button);}
    else if(isFlowFill(layer)){const title=host.querySelector('h2');if(title)title.after(button);else host.prepend(button);}else host.append(button);
  }
  return {open,mount};
}
