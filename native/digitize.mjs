import {MAX_LAYERS} from './limits.mjs';
import {clone,point,packContours,addRung} from './paths.mjs';
import {createNodeEditor} from './node-editor.mjs';
export function createDigitizer(ctx){
  const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let editProject=null,editRevision=0;
  const fresh=()=>ctx.getProject().id===editProject&&ctx.getRevision()===editRevision;
  const isSatin=l=>l.stitch==='satin'||String(l.originalParams?.satin_column).toLowerCase()==='true';
  document.body.insertAdjacentHTML('beforeend',`
    <dialog id="curveDialog" class="letter-dialog" aria-labelledby="curveTitle"><div class="dialog-heading"><div><span class="eyebrow">LETTERING ON A PATH</span><h2 id="curveTitle">Follow the curve.</h2></div><button id="closeCurve" class="icon-button" aria-label="Close curved lettering">×</button></div><label>Lettering block<select id="curveTextLayer"></select></label><label>Text<textarea id="curveWords" maxlength="180" rows="3"></textarea></label><label>Extra line gap (mm)<input id="curveLineGap" type="number" min="-10" max="30" step="any" value="0"></label><label>Font scale (%)<input id="curveScale" type="number" min="1" max="500" step="any"></label><label>Guide path<select id="curveGuideLayer"></select></label><div class="field-row"><label>Along path<select id="curveAlign"><option value="left">Start</option><option value="center" selected>Center</option><option value="right">End</option><option value="stretch">Spread letters</option></select></label><label>Vertical position<select id="curveVertical"><option value="baseline">Baseline</option><option value="top">Above path</option><option value="bottom">Below path</option></select></label></div><label class="check"><input id="curveReverse" type="checkbox">Reverse guide direction</label><label class="check"><input id="keepCurveGuide" type="checkbox">Keep the guide visible and stitched</label><p class="caption">The source text and guide remain editable in Stitch order. Each line follows an offset of the guide. Use the extra line gap to space parallel lines. The embroidery font’s scale limits still apply.</p><p id="curveError" class="error" role="alert"></p><div class="dialog-footer"><button id="cancelCurve">Cancel</button><button id="applyCurve" class="primary">Create curved lettering</button></div></dialog>`);
  function replace(ids,layers){
    const p=ctx.getProject();if(p.layers.length-ids.length+layers.length>MAX_LAYERS)throw new Error(`This operation would exceed ${MAX_LAYERS} layers. Use fewer paths.`);
    ctx.mutate(()=>{const start=Math.min(...ids.map(id=>p.layers.findIndex(l=>l.id===id))),remaining=p.layers.filter(l=>!ids.includes(l.id));remaining.splice(start,0,...layers);p.layers=remaining;ctx.select(layers.map(l=>l.id));});
  }
  async function operation(operation){
    if(!ctx.editable())return;const p=ctx.getProject(),pid=p.id,revision=ctx.getRevision(),layers=clone(ctx.chosen());
    try{ctx.toast('Updating editable paths…');const r=await ctx.api('/api/vector',{operation,layers});if(ctx.getProject().id!==pid||ctx.getRevision()!==revision)throw new Error('The design changed. Run the operation again.');replace(layers.map(l=>l.id),r.layers);ctx.toast('Paths updated. Undo restores the source layers.');}catch(e){ctx.toast(e.message);}
  }
  const nodeEditor=createNodeEditor({...ctx,replace}),editNodes=nodeEditor.open;
  function newSatin(){const contours=[{closed:false,nodes:[{...point(20,45),out:[35,30]},{...point(80,45),in:[65,30]}]},{closed:false,nodes:[{...point(20,53),out:[35,38]},{...point(80,53),in:[65,38]}]}];for(const t of [.2,.5,.8])addRung(contours,t);const l=packContours(contours,ctx.newLayer('path',{name:'Satin column',stitch:'satin',color:'#416580',spacing:.4,satinCenter:true}));ctx.addLayer(l);editNodes(l);}
  let curveTarget=null,curveSource=null;
  function openCurve(layer=null){
    if(layer?.locked)return ctx.toast('Unlock this layer first.');
    curveTarget=layer?.curveSource?layer.id:null;curveSource=clone(layer?.curveSource||null);editProject=ctx.getProject().id;editRevision=ctx.getRevision();
    const p=ctx.getProject(),texts=p.layers.filter(l=>l.type==='text'),guides=p.layers.filter(l=>['rectangle','ellipse','path'].includes(l.type)&&!isSatin(l));
    if(curveSource&&!texts.some(l=>l.id===curveSource.textLayer.id))texts.push(curveSource.textLayer);if(curveSource&&!guides.some(l=>l.id===curveSource.guideLayer.id))guides.push(curveSource.guideLayer);
    if(!texts.length||!guides.length)return ctx.toast('Add a lettering block and draw or create a guide path first.');
    $('curveTextLayer').innerHTML=texts.map(l=>`<option value="${l.id}">${esc(l.name)}</option>`).join('');$('curveGuideLayer').innerHTML=guides.map(l=>`<option value="${l.id}">${esc(l.name)}</option>`).join('');
    $('curveTextLayer').value=curveSource?.textLayer.id||ctx.chosen().find(l=>l.type==='text')?.id||texts[0].id;$('curveGuideLayer').value=curveSource?.guideLayer.id||ctx.chosen().find(l=>guides.some(g=>g.id===l.id))?.id||guides[0].id;
    $('curveTextLayer').onchange=()=>{const t=texts.find(l=>l.id===$('curveTextLayer').value);$('curveWords').value=t.lettering.text;$('curveScale').value=t.lettering.scale;$('curveLineGap').value=t.lettering.lineSpacing||0;};$('curveTextLayer').onchange();
    if(curveSource){$('curveWords').value=curveSource.textLayer.lettering.text;$('curveScale').value=curveSource.textLayer.lettering.scale;$('curveLineGap').value=curveSource.textLayer.lettering.lineSpacing||0;}
    $('curveAlign').value=curveSource?.position||'center';$('curveVertical').value=curveSource?.vertical||'baseline';$('curveReverse').checked=curveSource?.reverse||false;$('keepCurveGuide').checked=false;$('curveError').textContent='';$('applyCurve').textContent=curveTarget?'Update curved lettering':'Create curved lettering';$('curveDialog').showModal();
    $('applyCurve').onclick=async()=>{const button=$('applyCurve');button.disabled=true;button.textContent='Generating curved lettering…';try{
      const t=clone(texts.find(l=>l.id===$('curveTextLayer').value)),g=clone(guides.find(l=>l.id===$('curveGuideLayer').value));t.visible=true;g.visible=true;t.lettering.text=$('curveWords').value;t.lettering.scale=Number($('curveScale').value);t.lettering.lineSpacing=Number($('curveLineGap').value);
      const regenerated=await ctx.api('/api/lettering',t.lettering);t.lettering=regenerated.settings;t.width=regenerated.width;t.height=regenerated.height;
      const old=p.layers.find(l=>l.id===curveTarget);
      const r=await ctx.api('/api/curve-lettering',{previousLayer:old,textLayer:t,guideLayer:g,position:$('curveAlign').value,vertical:$('curveVertical').value,reverse:$('curveReverse').checked});
      if(!$('curveDialog').open||!fresh())throw new Error('The design changed. Open curved lettering again.');ctx.assets.set(r.asset.key,r.asset);
      if(old){r.layer={...old,...r.layer,id:old.id,color:old.color,recolor:old.recolor,visible:old.visible,groupId:old.groupId,trimAfter:old.trimAfter,stopAfter:old.stopAfter};}
      if(!old&&p.layers.length>=MAX_LAYERS)throw new Error(`A project can contain up to ${MAX_LAYERS} layers.`);
      ctx.mutate(()=>{if(old)p.layers.splice(p.layers.indexOf(old),1,r.layer);else p.layers.push(r.layer);const source=p.layers.find(l=>l.id===t.id);if(source)source.visible=false;const guide=p.layers.find(l=>l.id===g.id);if(guide)guide.visible=$('keepCurveGuide').checked;ctx.select([r.layer.id]);});$('curveDialog').close();ctx.setTab('digitize');
    }catch(e){$('curveError').textContent=e.message;}finally{button.disabled=false;button.textContent=curveTarget?'Update curved lettering':'Create curved lettering';}};
  }
  for(const id of ['closeCurve','cancelCurve'])$(id).onclick=()=>$('curveDialog').close();
  function render(host){
    const list=ctx.chosen(),l=list.length===1?list[0]:null,locked=list.some(l=>l.locked||l.type==='image'),canNodes=l&&!locked&&l.type!=='text';
    host.innerHTML=`<h2>Digitize with touch.</h2><p>Create and edit paths, cut holes, shape satin rails, or bend lettering.</p><div class="button-row"><button id="newCurvePath">＋ Draw path</button><button id="newSatin">＋ Satin column</button></div><button id="editNodes" class="wide" ${canNodes?'':'disabled'}>Edit nodes, curves & stitch positions</button><p class="caption">${l?.type==='text'?'Separate lettering paths below to edit its stitch geometry.':l?esc(l.name):'Select one shape or path to edit its nodes.'}</p><h3>Shape operations</h3><p class="caption">Select multiple shapes. Cut hole subtracts the later layer from the earlier one. Divide creates filled pieces; Cut outline creates open running paths. Combine and Simplify keep the first layer’s stitch settings. Undo restores the sources.</p><div class="operation-grid">${[['union','Union'],['difference','Cut hole'],['intersection','Intersection'],['exclusion','Exclude overlap'],['combine','Combine paths'],['division','Divide shape'],['cut','Cut outline'],['break-apart','Break apart'],['simplify','Simplify']].map(([op,label])=>`<button data-vector="${op}" ${locked||(['difference','division','cut'].includes(op)?list.length!==2:!['break-apart','simplify'].includes(op)?list.length<2:!l)?'disabled':''}>${label}</button>`).join('')}</div><div class="button-row"><button id="offsetPaths" ${locked||!list.length?'disabled':''}>Offset / inset paths</button><button id="strokeArea" ${locked||!list.length?'disabled':''}>Stroke area → fill</button></div><button id="separatePaths" class="wide" ${l&&!locked?'':'disabled'}>Separate SVG / lettering paths</button><p class="caption">Separate exposes individual paths for colors, stitch settings, node edits, entry/exit, and stitch order.</p><hr class="separator"><h3>Lettering along a path</h3><button id="curveLettering" class="wide">${l?.curveSource?'Edit curved lettering':'Create curved lettering'}</button><p class="caption">Use an editable guide path or shape. The source lettering and guide remain available in Stitch order.</p>`;
    $('offsetPaths').onclick=()=>ctx.openOperation('path_offset');$('strokeArea').onclick=()=>ctx.openOperation('stroke_area');
    $('newCurvePath').onclick=()=>editNodes();$('newSatin').onclick=newSatin;$('editNodes').onclick=()=>editNodes(l);host.querySelectorAll('[data-vector]').forEach(b=>b.onclick=()=>operation(b.dataset.vector));$('separatePaths').onclick=()=>operation('explode');$('curveLettering').onclick=()=>openCurve(l);
    ctx.mountExtras?.(host);
  }
  return{render,editNodes,newSatin};
}
