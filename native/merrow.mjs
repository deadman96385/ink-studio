import {MAX_LAYERS} from './limits.mjs';
import {drawPlan} from './advanced.mjs';
import {pathD} from './paths.mjs';

const DEFAULTS={width:3,spacing:.4,fanLength:2.4,spread:.3,bindingDepth:.45,side:'inside',underlay:'center'};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const isMerrow=l=>!!l?.merrow&&l.stitch==='original';
export function validMerrowPreview(l){
  const c=l.merrowPreview;
  return !!c&&l.width===c.width&&l.height===c.height&&JSON.stringify(l.contours)===JSON.stringify(c.contours)&&JSON.stringify(l.merrow)===JSON.stringify(c.settings);
}
export function merrowMarkup(l){
  if(!isMerrow(l))return '';
  if(validMerrowPreview(l))return `<path d="${esc(l.merrowPreview.d)}" fill="none" stroke="${esc(l.color)}" stroke-width=".14" stroke-linecap="round" stroke-linejoin="round"/>`;
  return `<path d="${esc(pathD(l.contours,l.width,l.height))}" fill="none" stroke="${esc(l.color)}" stroke-width="${esc(l.merrow.width)}" opacity=".65"/>`;
}
export function merrowArtwork(l,node){
  if(!isMerrow(l))return null;
  const g=node('g');
  g.append(node('path',{d:validMerrowPreview(l)?l.merrowPreview.d:pathD(l.contours,l.width,l.height),fill:'none',stroke:l.color,
    'stroke-width':validMerrowPreview(l)?.14:l.merrow.width,'stroke-linecap':'round','stroke-linejoin':'round'}));
  return g;
}
export function applyMerrow(project,sourceId,proposal){
  const index=project.layers.findIndex(l=>l.id===sourceId);
  if(index<0)throw new Error('The source outline was removed. Reopen faux merrow.');
  const source=project.layers[index];if(source.locked||source.link||source.linkedHelper)throw new Error('Unlock or detach the source before applying.');
  const layer=structuredClone(proposal.layer);
  if(source.merrow){layer.id=source.id;project.layers.splice(index,1,layer);}
  else{
    if(project.layers.length>=MAX_LAYERS)throw new Error(`This design already contains ${MAX_LAYERS} layers.`);
    project.layers.splice(index+1,0,layer);
  }
  return layer.id;
}

export function createMerrow(ctx){
  const $=id=>document.getElementById(id);let source,pid,revision,token=0,result=null,busy=false;
  document.body.insertAdjacentHTML('beforeend',`<dialog id="merrowDialog" class="merrow-dialog" aria-labelledby="merrowTitle"><div class="dialog-heading"><div><span class="eyebrow">PATCH EDGES & BORDERS</span><h2 id="merrowTitle">Faux merrow border.</h2></div><button id="closeMerrow" class="icon-button" aria-label="Close faux merrow border">×</button></div>
  <p id="merrowSource" class="caption"></p><form id="merrowForm"><div class="merrow-workspace"><section><canvas id="merrowCanvas" aria-label="Actual faux merrow border stitches"></canvas><p id="merrowStats" role="status" class="caption">Preview to see the fan and binding stitches.</p><p class="caption">The outline and border settings stay editable. Re-preview after changing the width, fans or outline. Undo restores your previous design.</p></section><fieldset id="merrowFields"><legend class="sr-only">Faux merrow settings</legend>
  <label>Border width (mm)<input id="merrowWidth" type="number" min="0.8" max="6" step="any" value="3" required></label><label>Thread color<input id="merrowColor" type="color" value="#203f38"></label>
  <div class="field-row"><label>Fan stitch spacing (mm)<input id="merrowSpacing" type="number" min="0.2" max="1.2" step="any" value="0.4" required></label><label>Fan length (mm)<input id="merrowFanLength" type="number" min="1" max="8" step="any" value="2.4" required></label></div>
  <label>Gathered fan spread (%)<input id="merrowSpread" type="number" min="10" max="80" step="any" value="30" required></label><label>Binding depth (mm)<input id="merrowBinding" type="number" min="0.1" max="2" step="any" value="0.45" required></label>
  <label>Gather on<select id="merrowSide"><option value="inside">Inside edge</option><option value="outside">Outside edge</option></select></label><label>Underlay<select id="merrowUnderlay"><option value="none">None</option><option value="center" selected>Center run</option><option value="center-contour">Center + contour runs</option><option value="full">Center, contour + zigzag</option></select></label>
  <p class="caption">Smaller stitch spacing adds more stitches. Fan length sets the repeat; spread controls how tightly the roots gather. Binding depth sets the short stitch into each fan.</p></fieldset></div><p id="merrowError" class="error" role="alert"></p><div class="dialog-footer"><button id="cancelMerrow" type="button">Cancel</button><button id="previewMerrow" class="primary">Preview border</button><button id="applyMerrow" class="primary" type="button" disabled>Add border</button></div></form></dialog>`);
  const fields={width:'merrowWidth',spacing:'merrowSpacing',fanLength:'merrowFanLength',spread:'merrowSpread',bindingDepth:'merrowBinding',side:'merrowSide',underlay:'merrowUnderlay'};
  const fresh=()=>ctx.getProject().id===pid&&ctx.getRevision()===revision;
  function working(on){busy=on;$('merrowFields').disabled=on;$('previewMerrow').disabled=on;$('applyMerrow').disabled=on||!result;$('previewMerrow').textContent=on?'Preparing stitches…':'Preview border';}
  function clear(){token++;result=null;$('merrowError').textContent='';$('merrowStats').textContent='Preview to see the current border settings.';$('merrowCanvas').getContext('2d').clearRect(0,0,$('merrowCanvas').width,$('merrowCanvas').height);working(false);}
  function read(){const out={};for(const[key,id]of Object.entries(fields)){const e=$(id);if(!e.validity.valid||e.value==='')throw new Error('Check the border settings.');out[key]=e.type==='number'?Number(e.value)/(key==='spread'?100:1):e.value;}return out;}
  function open(layer=ctx.chosen()[0]){
    if(!layer||ctx.chosen().length!==1||!['path','rectangle','ellipse'].includes(layer.type))return ctx.toast('Select one closed shape or border.');
    if(layer.locked||layer.link||layer.linkedHelper)return ctx.toast('Unlock or detach the source outline first.');
    if(['patch','crescent'].includes(layer.component?.kind))return ctx.editComponent(layer.component.kind);
    source=structuredClone(layer);pid=ctx.getProject().id;revision=ctx.getRevision();const p={...DEFAULTS,...layer.merrow};
    for(const[key,id]of Object.entries(fields))$(id).value=key==='spread'?p[key]*100:p[key];$('merrowColor').value=layer.color;
    $('merrowSource').textContent=layer.merrow?`Edit ${layer.name}.`:`Add a border following ${layer.name}. The source shape is retained.`;
    $('applyMerrow').textContent=layer.merrow?'Update border':'Add border';clear();$('merrowDialog').showModal();
  }
  $('merrowFields').oninput=clear;
  $('merrowForm').onsubmit=async e=>{
    e.preventDefault();if(busy)return;clear();const run=token;
    try{
      if(!fresh())throw new Error('The design changed. Reopen faux merrow.');const settings=read();working(true);
      const proposed=await ctx.api('/api/merrow',{layer:source,settings,color:$('merrowColor').value});
      if(run!==token||!$('merrowDialog').open)return;if(!fresh())throw new Error('The design changed. Reopen faux merrow.');
      result=proposed;drawPlan($('merrowCanvas'),result.preview);const p=result.preview;
      $('merrowStats').textContent=`${proposed.stats.fans} fans · ${p.stitches.toLocaleString()} stitches · ${p.trims} cuts · ${p.width} × ${p.height} mm`;
    }catch(error){if(run===token)$('merrowError').textContent=error.message;}
    finally{if(run===token)working(false);}
  };
  $('applyMerrow').onclick=()=>{
    try{
      if(!result||busy||!fresh())throw new Error('Preview the current border before applying.');
      const draft=structuredClone(ctx.getProject()),id=applyMerrow(draft,source.id,result);
      ctx.mutate(()=>{Object.assign(ctx.getProject(),draft);ctx.select([id]);});$('merrowDialog').close();ctx.setTab('layer');ctx.toast('Faux merrow border applied. Undo restores the previous design.');
    }catch(error){$('merrowError').textContent=error.message;}
  };
  for(const id of ['closeMerrow','cancelMerrow'])$(id).onclick=()=>$('merrowDialog').close();$('merrowDialog').onclose=()=>{token++;busy=false;};
  new ResizeObserver(()=>{if(result&&$('merrowDialog').open)drawPlan($('merrowCanvas'),result.preview);}).observe($('merrowCanvas'));
  function mount(host,layer=null){
    if(layer&&(!['path','rectangle','ellipse'].includes(layer.type)||layer.role&&layer.role!=='artwork'))return;
    const button=document.createElement('button');button.type='button';button.id=layer?'editMerrow':'openMerrow';button.className='wide'+(layer?.merrow?' primary':'');
    button.textContent=layer?.merrow?'Edit faux merrow border':'Faux merrow border';button.onclick=()=>open(layer||ctx.chosen()[0]);
    if(!layer){const selected=ctx.chosen();button.disabled=selected.length!==1||!['path','rectangle','ellipse'].includes(selected[0].type);host.append(button);}
    else if(layer.merrow){const title=host.querySelector('h2');if(title)title.after(button);else host.prepend(button);}else host.append(button);
  }
  return{open,mount};
}
