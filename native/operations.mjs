import {placeRouting} from './routing-model.mjs';
import {MAX_LAYERS} from './limits.mjs';
import {drawPlan,stitchMode} from './advanced.mjs';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function placeMaintenance(current,sourceIds,helperIds,result){
  const outputs=new Map(result.layers.map(l=>[l.id,l])),used=new Set(),sources=new Set(sourceIds),oldHelpers=new Set(helperIds);
  const replaced=current.flatMap(l=>{
    if(!sources.has(l.id))return oldHelpers.has(l.id)?[]:[l];
    const ids=result.placements?.[l.id];if(!Array.isArray(ids))throw new Error('The result is missing its source order. Preview again.');
    return ids.flatMap(id=>{const art=outputs.get(id);if(!art||used.has(id))throw new Error('The result contains an invalid source path.');used.add(id);
      const attached=result.layers.filter(h=>h.helperTarget===id);attached.forEach(h=>used.add(h.id));return [art,...attached];});
  });
  if(used.size!==outputs.size)throw new Error('The result contains unattached paths. Preview again.');
  return replaced;
}
export function createOperations(ctx){
  document.head.insertAdjacentHTML('beforeend','<link rel="stylesheet" href="/transforms.css">');
  const $=id=>document.getElementById(id);let catalog=[],tool=null,layers=[],helpers=[],proposal=null,revision=0,pid=null,token=0;
  const maintenance=new Set(['transform_elements','remove_duplicated_points','duplicate_params','remove_embroidery_settings','apply_attribute','jump_to_trim']);
  const consumed=()=>[...layers,...(maintenance.has(tool?.key)?helpers:[])];
  document.body.insertAdjacentHTML('beforeend',`<dialog id="operationsDialog" class="operations-dialog" aria-labelledby="operationsTitle"><div class="dialog-heading"><div><span class="eyebrow">EMBROIDERY TOOLS</span><h2 id="operationsTitle">Convert & prepare.</h2></div><button id="closeOperations" class="icon-button" aria-label="Close embroidery tools">×</button></div><p id="operationsSelection"></p><button id="operationsBrowse" type="button" class="quiet" hidden>Choose another tool</button><label>Find a tool<input id="operationsSearch" type="search" placeholder="Satin, background, cleanup…"></label><div class="operations-workspace"><nav id="operationsList" aria-label="Embroidery tools"></nav><section><h3 id="operationName"></h3><p id="operationHelp" class="caption"></p><form id="operationForm"><fieldset id="operationFields"></fieldset><p id="operationError" class="error" role="alert"></p><div id="operationPreview" hidden><canvas id="operationCanvas" aria-label="Proposed embroidery stitches"></canvas><p id="operationStats" role="status"></p></div><div class="dialog-footer"><button id="cancelOperation" type="button">Cancel</button><button id="previewOperation" class="primary">Preview result</button><button id="applyOperation" type="button" class="primary" hidden>Apply result</button></div></form></section></div></dialog>`);
  const fresh=()=>ctx.getProject().id===pid&&ctx.getRevision()===revision;
  function clear(){proposal=null;token++;$('operationPreview').hidden=true;$('applyOperation').hidden=true;$('operationError').textContent='';}
  function select(key){clear();tool=catalog.find(t=>t.key===key);$('operationName').textContent=tool.label;$('operationHelp').textContent=tool.help;
    const focus=key==='transform_elements';$('operationsDialog').classList.toggle('transform-tool',focus);$('operationsTitle').textContent=focus?'Transform embroidery.':'Convert & prepare.';$('operationsBrowse').hidden=!focus;
    $('operationFields').innerHTML=tool.fields.map(f=>{
      const k=esc(f.key),label=esc(f.label);
      if(f.kind==='boolean')return `<label class="check"><input data-option="${k}" type="checkbox" ${f.default?'checked':''}>${label}</label>`;
      if(f.kind==='color')return `<label>${label}<input data-option="${k}" type="color" value="${f.default}"></label>`;
      if(f.kind==='source')return `<label>${label}<select data-option="${k}">${layers.map(l=>`<option value="${esc(l.id)}">${esc(l.name||'Path')}</option>`).join('')}</select></label>`;
      if(f.kind==='text')return `<label>${label}<input data-option="${k}" type="text" maxlength="${f.maxLength||2000}" value="${esc(f.default)}" autocapitalize="none" autocorrect="off" spellcheck="false" ${f.key==='key'?'required':''}></label>`;
      if(f.kind==='select')return `<label>${label}<select data-option="${k}">${f.options.map(([v,n])=>`<option value="${esc(v)}" ${v===f.default?'selected':''}>${esc(n)}</option>`).join('')}</select></label>`;
      return `<label>${label}<input data-option="${k}" type="number" min="${f.min}" max="${f.max}" step="${['num_points','redwork_bean_stitch_repeats'].includes(f.key)?1:'any'}" inputmode="decimal" value="${f.default}" required></label>`;
    }).join('');const visibility=()=>{for(const f of tool.fields.filter(f=>f.when)){const input=$('operationFields').querySelector(`[data-option="${f.key}"]`),other=$('operationFields').querySelector(`[data-option="${f.when.key}"]`);input.closest('label').hidden=!f.when.values.includes(other.value);input.disabled=input.closest('label').hidden;}};visibility();$('operationFields').oninput=()=>{clear();visibility();};for(const b of $('operationsList').querySelectorAll('button'))b.setAttribute('aria-pressed',b.dataset.tool===key);}
  function list(){const q=$('operationsSearch').value.trim().toLowerCase(),shown=catalog.filter(t=>(t.label+' '+t.group+' '+t.help).toLowerCase().includes(q));
    $('operationsList').innerHTML=[...new Set(shown.map(t=>t.group))].map(g=>`<h4>${esc(g)}</h4>${shown.filter(t=>t.group===g).map(t=>`<button type="button" data-tool="${t.key}" aria-pressed="${tool?.key===t.key}">${esc(t.label)}</button>`).join('')}`).join('')||'<p class="caption">No matching tools.</p>';
    for(const b of $('operationsList').querySelectorAll('button'))b.onclick=()=>select(b.dataset.tool);
  }
  async function open(preferred=null){if(!ctx.chosen().length||!ctx.editable())return;pid=ctx.getProject().id;revision=ctx.getRevision();layers=structuredClone(ctx.chosen().filter(l=>(l.role||'artwork')==='artwork'));helpers=structuredClone(ctx.getProject().layers.filter(l=>['guide-line','anchor-line','pattern'].includes(l.role)&&layers.some(a=>a.id===l.helperTarget)));
    if(!layers.length){ctx.toast('Select stitched artwork to use embroidery tools.');return;}
    try{if(!catalog.length)catalog=await ctx.api('/api/embroidery-tools');if(!fresh())throw new Error('The design changed. Open tools again.');clear();$('operationsSelection').textContent=`${layers.length} selected layer(s). Applying converts text, shapes and linked copies to editable paths. Preview first; Undo restores the source layers.`;$('operationsSearch').value='';list();
      const mode=stitchMode(layers[0]);select(typeof preferred==='string'&&catalog.some(t=>t.key===preferred)?preferred:mode==='satin'?'satin_to_stroke':mode==='fill'?'fill_to_satin':'stroke_to_satin');busy(false);$('operationsDialog').showModal();
    }catch(e){ctx.toast(e.message);}}
  function busy(on){$('operationFields').disabled=on;$('previewOperation').disabled=on;$('previewOperation').textContent=on?'Generating stitches…':'Preview result';$('operationsSearch').disabled=on;for(const b of $('operationsList').querySelectorAll('button'))b.disabled=on;}
  $('operationsSearch').oninput=list;
  $('operationsBrowse').onclick=()=>{$('operationsDialog').classList.remove('transform-tool');$('operationsBrowse').hidden=true;$('operationsTitle').textContent='Convert & prepare.';};
  $('operationForm').onsubmit=async e=>{e.preventDefault();clear();const run=token;busy(true);try{
    const params={};for(const f of tool.fields){const input=$('operationFields').querySelector(`[data-option="${f.key}"]`);if(!input.validity.valid)throw new Error('Check '+f.label+'.');if(input.disabled){params[f.key]=f.default;continue;}params[f.key]=f.kind==='boolean'?input.checked:f.kind==='number'?Number(input.value):input.value;}
    const result=await ctx.api('/api/operate',{tool:tool.key,params,layers,...(maintenance.has(tool.key)?{helpers}:{}),...(['transform_elements','redwork'].includes(tool.key)?{project:structuredClone(ctx.getProject())}:{})});if(run!==token||!$('operationsDialog').open)return;if(!fresh())throw new Error('The design changed. Open tools again.');
    if(ctx.getProject().layers.length-(tool.key==='redwork'?result.removeIds.length:consumed().length)+result.layers.length>MAX_LAYERS)throw new Error(`The result exceeds ${MAX_LAYERS} layers. Select fewer paths.`);proposal=result;
    $('operationPreview').hidden=false;$('operationCanvas').hidden=!result.preview;$('applyOperation').hidden=false;$('applyOperation').textContent=result.layers.length?'Apply result':'Remove selected objects';
    $('operationStats').textContent=result.preview?`${result.layers.length} editable layers · ${result.preview.stitches.toLocaleString()} stitches · ${result.preview.width} × ${result.preview.height} mm`:'No objects remain under these cleanup settings. Applying removes the selected objects.';if(result.preview)drawPlan($('operationCanvas'),result.preview);
  }catch(e){if(run===token)$('operationError').textContent=e.message;}finally{if(run===token)busy(false);}};
  $('applyOperation').onclick=()=>{try{if(!proposal||!fresh())throw new Error('The design changed. Preview again.');const p=ctx.getProject(),ids=consumed().map(l=>l.id);for(const asset of proposal.assets||[])ctx.assets.set(asset.key,asset);if(p.layers.some(l=>ids.includes(l.id)&&l.locked))throw new Error('Unlock the selected layers and attached helpers first.');let next;if(tool.key==='redwork')next=placeRouting(p.layers,layers.map(l=>l.id),proposal);else if(maintenance.has(tool.key))next=placeMaintenance(p.layers,layers.map(l=>l.id),helpers.map(l=>l.id),proposal);else{const first=Math.min(...ids.map(id=>p.layers.findIndex(l=>l.id===id)));next=p.layers.filter(l=>!ids.includes(l.id));next.splice(first,0,...proposal.layers);}ctx.mutate(()=>{p.layers=next;ctx.select(proposal.layers.filter(l=>(l.role||'artwork')==='artwork'&&(tool.key!=='transform_elements'||l.visible!==false)).map(l=>l.id));});$('operationsDialog').close();ctx.setTab('digitize');ctx.toast('Applied. Undo restores the source layers.');}catch(e){$('operationError').textContent=e.message;}};
  for(const id of ['closeOperations','cancelOperation'])$(id).onclick=()=>$('operationsDialog').close();$('operationsDialog').addEventListener('close',()=>token++);
  new ResizeObserver(()=>{if($('operationsDialog').open&&proposal?.preview)drawPlan($('operationCanvas'),proposal.preview);}).observe($('operationCanvas'));
  function mount(host){host.insertAdjacentHTML('beforeend','<hr class="separator"><h3>Convert & prepare</h3><button id="openEmbroideryTools" class="wide">Embroidery tools</button><p class="caption">Appliqué steps, satin conversion, cut points, gradients, cutwork, running connections, redwork, backgrounds and cleanup.</p>');$('openEmbroideryTools').disabled=!ctx.chosen().length;$('openEmbroideryTools').onclick=open;}
  return {open,mount};
}
