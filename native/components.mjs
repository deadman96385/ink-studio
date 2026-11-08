import {MAX_LAYERS} from './limits.mjs';
import {pathD,satinArea} from './paths.mjs';
import {groupBounds} from './geometry.mjs';
import {drawPlan} from './advanced.mjs';
import {merrowMarkup} from './merrow.mjs';
import {streamlineMarkup} from './streamlines.mjs';
import {featherMarkup} from './feather.mjs';

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const round = v => Math.round(v*100)/100;
export const componentGroup = (project, layer) => layer?.component && layer.groupId
  ? project.layers.filter(l => l.groupId === layer.groupId && l.component?.kind === layer.component.kind) : [];

// Replace parts at their existing stitch positions. Other motifs can be between
// the patch ground and its finishing edge, and must retain that ordering.
export function replaceComponentParts(layers, targets, replacements) {
  const ids = new Set(targets.map(l => l.id));
  const byId = new Map(replacements.map(l => [l.id, l]));
  const extras = replacements.filter(l => !ids.has(l.id));
  const last = layers.findLastIndex(l => ids.has(l.id));
  return layers.flatMap((l, i) => [...(ids.has(l.id) ? (byId.has(l.id) ? [byId.get(l.id)] : []) : [l]), ...(i === last ? extras : [])]);
}

export function effectiveParams(layers) {
  const anchor = layers.find(l => l.component?.localBox);
  if (!anchor) throw new Error('The original component parts are missing. Add a new component.');
  const p = structuredClone(anchor.component.params), b = anchor.component.localBox;
  p.width = round(p.width*anchor.width/b[2]);
  p.height = round(p.height*anchor.height/b[3]);
  if (['crescent','patch'].includes(anchor.component.kind)) {
    const body=layers.find(l=>l.component?.part==='body'), edge=layers.find(l=>l.component?.part==='edge');
    const area=layers.find(l=>l.role==='content-area');
    if(body?.color){if(p.construction==='applique')p.placementColor=body.color;else p.bodyColor=body.color;}
    if(p.construction!=='applique'&&Number.isFinite(body?.spacing))p.spacing=body.spacing;
    if(edge?.color)p.edgeColor=edge.color;
    if(Number.isFinite(edge?.strokeWidth))p.borderWidth=edge.strokeWidth;
    if(edge?.merrow&&edge.stitch==='original'){
      const m=edge.merrow;Object.assign(p,{borderStyle:'merrow',borderWidth:m.width,merrowSpacing:m.spacing,merrowFanLength:m.fanLength,
        merrowSpread:m.spread*100,merrowBinding:m.bindingDepth,merrowSide:m.side,merrowUnderlay:m.underlay});
    }
    if(area?.areaSettings)p.clearance=area.areaSettings.clearance;
  }
  return p;
}

const transform = l => `translate(${l.x} ${l.y}) rotate(${l.rotation||0} ${l.width/2} ${l.height/2}) translate(${l.flipX?l.width:0} ${l.flipY?l.height:0}) scale(${l.flipX?-1:1} ${l.flipY?-1:1})`;
// Saved motifs may include native ellipses/rectangles, which have no contours.
function shapeD(l,satin){
  if(l.contours)return satin?satinArea(l.contours,l.width,l.height):pathD(l.contours,l.width,l.height);
  const w=l.width,h=l.height;
  if(l.type==='ellipse')return `M0,${h/2} A${w/2},${h/2} 0 1 0 ${w},${h/2} A${w/2},${h/2} 0 1 0 0,${h/2} Z`;
  const r=Math.max(0,Math.min(l.radius||0,w/2,h/2));
  return r?`M${r},0 H${w-r} A${r},${r} 0 0 1 ${w},${r} V${h-r} A${r},${r} 0 0 1 ${w-r},${h} H${r} A${r},${r} 0 0 1 0,${h-r} V${r} A${r},${r} 0 0 1 ${r},0 Z`:`M0,0 H${w} V${h} H0 Z`;
}
export function componentArtwork(layers) {
  const b = groupBounds(layers), pad = 3;
  if (!b) return '';
  const paths = layers.map(l => {
    const feather=featherMarkup(l);if(feather)return `<g data-component-layer="${esc(l.id)}" transform="${esc(transform(l))}">${feather}</g>`;
    const merrow=merrowMarkup(l);if(merrow)return `<g data-component-layer="${esc(l.id)}" transform="${esc(transform(l))}">${merrow}</g>`;
    const flow=streamlineMarkup(l);if(flow)return `<g data-component-layer="${esc(l.id)}" transform="${esc(transform(l))}">${flow}</g>`;
    const area = l.role === 'content-area', satin=l.stitch==='satin', fill = l.stitch === 'fill'||satin;
    return `<g data-component-layer="${esc(l.id)}" ${l.sceneBinding?`data-scene-item="${esc(l.sceneBinding.itemId)}"`:''} transform="${esc(transform(l))}"><path d="${esc(shapeD(l,satin))}" fill="${area?'#24b6b018':fill?esc(l.color):'none'}" fill-rule="evenodd" stroke="${area?'#24b6b0':fill?'none':esc(l.color)}" stroke-width="${esc(area ? .3 : l.stitch==='zigzag'?l.strokeWidth:l.stitch==='bean'?.26:.18)}" ${area?'stroke-dasharray="1 .7"':''}/></g>`;
  }).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${b.x-pad} ${b.y-pad} ${b.w+pad*2} ${b.h+pad*2}" role="img" aria-label="Editable component artwork and usable inner area">${paths}</svg>`;
}

export function createComponents(ctx) {
  const $ = id => document.getElementById(id);
  let customOutline = null;
  let catalog = [], targets = [], proposal = null, revision = 0, pid = null, token = 0;
  let areaSource = null, oldArea = null, areaProposal = null, areaRevision = 0, areaPid = null, areaToken = 0;
  document.body.insertAdjacentHTML('beforeend', `
    <dialog id="componentsDialog" class="components-dialog" aria-labelledby="componentsTitle">
      <div class="dialog-heading"><div><span class="eyebrow">PATCHES & MOTIFS</span><h2 id="componentsTitle">Build a reusable design.</h2></div><button id="closeComponents" class="icon-button" aria-label="Close patches and motifs">×</button></div>
      <p id="componentHelp" class="caption"></p>
      <form id="componentForm"><div class="components-workspace"><section class="component-stage">
        <div class="button-row"><button type="button" id="componentArtworkTab" aria-pressed="true">Artwork + inner area</button><button type="button" id="componentStitchTab" aria-pressed="false" disabled>Actual stitches</button></div>
        <div id="componentArtwork" class="component-artwork"><p>Choose settings, then preview your component.</p></div>
        <canvas id="componentStitches" aria-label="Actual Ink/Stitch component preview" hidden></canvas>
        <p id="componentStats" role="status"></p><p id="componentWarnings" class="caption"></p>
      </section><fieldset id="componentFields"><label>Component<select id="componentKind"><option value="patch">Patch · any shape, embroidered or appliqué</option><option value="starter">Crescent starter · patch + mushroom + branch</option><option value="crescent">Crescent patch</option><option value="mushroom">Mushroom</option><option value="branch">Leafy branch</option><option value="motif">Saved motif</option></select></label><div id="componentOptions"></div>
        <div id="componentPose"><div class="field-row"><label>Center X (mm)<input id="componentX" type="number" min="0" max="100" step="any" value="50"></label><label>Center Y (mm)<input id="componentY" type="number" min="0" max="100" step="any" value="50"></label></div><label>Rotation (°)<input id="componentRotation" type="number" min="-360" max="360" step="any" value="0"></label></div>
      </fieldset></div><p id="componentError" class="error" role="alert"></p>
      <div class="dialog-footer"><button id="cancelComponents" type="button">Cancel</button><button id="previewComponent" class="primary" type="submit">Preview stitches</button><button id="applyComponent" class="primary" type="button" hidden>Add editable parts</button></div></form>
    </dialog>
    <dialog id="contentAreaDialog" class="content-area-dialog" aria-labelledby="contentAreaTitle">
      <div class="dialog-heading"><div><span class="eyebrow">USABLE INNER AREA</span><h2 id="contentAreaTitle">Leave room for the edge.</h2></div><button id="closeContentArea" class="icon-button" aria-label="Close inner area">×</button></div>
      <p class="caption">Inset the current outline by half the cover-edge width, plus the gap and compensation allowance. This editable guide never sews. Refresh after resizing or changing the patch outline or edge. These settings change the guide.</p>
      <form id="contentAreaForm"><div class="field-row"><label>Cover edge width (mm)<input id="areaBorder" type="number" min="0.6" max="6" step="any" required></label><label>Gap beyond edge (mm)<input id="areaGap" type="number" min="0" max="5" step="any" required></label><label>Compensation allowance (mm)<input id="areaCompensation" type="number" min="0" max="1" step="any" required></label></div>
      <div id="areaArtwork" class="component-artwork" hidden></div><p id="areaStats" role="status"></p><p id="areaError" class="error" role="alert"></p>
      <div class="dialog-footer"><button id="cancelContentArea" type="button">Cancel</button><button id="previewContentArea" type="submit">Preview inner area</button><button id="applyContentArea" class="primary" type="button" hidden>Apply inner area</button></div></form>
    </dialog>
    <dialog id="componentFitDialog" class="content-area-dialog" aria-labelledby="componentFitTitle">
      <div class="dialog-heading"><h2 id="componentFitTitle">Check the content boundary.</h2><button id="closeComponentFit" class="icon-button" aria-label="Close content fit check">×</button></div>
      <p class="caption">Checks the full visible motif geometry, including line width and fill compensation, against the current guide. Refresh the guide first if the patch outline or edge changed. Intentional motif overlaps are allowed.</p>
      <label>Usable inner area<select id="fitArea"></select></label><button id="runComponentFit" class="primary wide">Check scene motifs</button><p id="componentFitStatus" role="status"></p><div id="componentFitFindings"></div>
    </dialog>`);

  const fresh = () => ctx.getProject().id === pid && ctx.getRevision() === revision;
  const areaFresh = () => ctx.getProject().id === areaPid && ctx.getRevision() === areaRevision;
  function clear() {
    proposal = null; token++;
    $('applyComponent').hidden = true; $('componentStitchTab').disabled = true;
    $('componentStats').textContent = ''; $('componentWarnings').textContent = ''; $('componentError').textContent = '';
    $('componentArtwork').innerHTML = '<p>Preview again to see your changes.</p>';
    showStitches(false);
  }
  function showStitches(on) {
    $('componentArtwork').hidden = on; $('componentStitches').hidden = !on;
    $('componentArtworkTab').setAttribute('aria-pressed', String(!on));
    $('componentStitchTab').setAttribute('aria-pressed', String(on));
    if (on && proposal?.preview) drawPlan($('componentStitches'), proposal.preview);
  }
  function options(params=null) {
    clear();
    const kind = $('componentKind').value, spec = catalog.find(c => c.key === (kind==='starter'?'crescent':kind));
    const fields = spec.fields.map(f=>({...f,min:kind==='starter'&&f.key==='width'?55:kind==='starter'&&f.key==='height'?65:f.min}));
    $('componentOptions').innerHTML = fields.map(f => f.kind==='select'?`<label>${esc(f.label)}<select data-component-option="${f.key}">${f.options.map(([value,label])=>`<option value="${esc(value)}" ${value===(params?.[f.key]??f.default)?'selected':''}>${esc(label)}</option>`).join('')}</select></label>`:`<label>${esc(f.label)}<input data-component-option="${f.key}" type="${f.kind==='color'?'color':'number'}" ${f.kind==='color'?'':`min="${f.min}" max="${f.max}" step="${f.kind==='integer'?1:'any'}" inputmode="decimal"`} value="${esc(params?.[f.key]??f.default)}" required></label>`).join('');
    $('componentPose').hidden = !!targets.length || kind === 'starter';
    customOutline = kind === 'patch' && params?.shape === 'custom' ? params.outline : null;
    // "Selected shape" is only offered when rebuilding a patch made from one.
    const shapeSelect = $('componentOptions').querySelector('[data-component-option="shape"]');
    if (shapeSelect && !customOutline) shapeSelect.querySelector('option[value="custom"]')?.remove();
    relevance();
  }
  function relevance() {
    const kind=$('componentKind').value;
    if(!['patch','crescent','starter'].includes(kind))return;
    const get = k => $('componentOptions').querySelector(`[data-component-option="${k}"]`)?.value;
    const shape = get('shape'), applique = get('construction') === 'applique';
    const show = kind==='patch'?{cornerRadius: shape === 'rounded', height: shape !== 'circle', tackInset: applique, placementColor: applique,
                  bodyColor: !applique, spacing: !applique}:{};
    for(const key of ['merrowSpacing','merrowFanLength','merrowSpread','merrowBinding','merrowSide','merrowUnderlay'])show[key]=get('borderStyle')==='merrow';
    const border=$('componentOptions').querySelector('[data-component-option="borderWidth"]');if(border)border.min=get('borderStyle')==='merrow'?'0.8':kind==='patch'?'0.8':'0.6';
    for (const [k, on] of Object.entries(show)) {
      const label = $('componentOptions').querySelector(`[data-component-option="${k}"]`)?.closest('label');
      if (label) label.hidden = !on;
    }
  }
  async function open(kind='patch', edit=false) {
    try {
      const p = ctx.getProject(); pid=p.id; revision=ctx.getRevision(); targets=[];
      if (edit) {
        targets = structuredClone(componentGroup(p,ctx.chosen()[0]));
        if (!targets.length || targets.some(l=>l.locked)) throw new Error('Select one unlocked component group.');
        kind = targets[0].component.kind;
      }
      catalog = await ctx.api('/api/component-catalog');
      if (kind === 'motif' && !catalog.find(c => c.key === 'motif')?.fields[0].options.length) throw new Error('No saved motifs yet. Select shapes, then choose Save selection as motif.');
      if (!fresh()) throw new Error('The design changed. Open patches again.');
      $('componentKind').value=kind; $('componentKind').disabled=!!targets.length;
      $('componentHelp').textContent = targets.length
        ? 'Rebuild this group from its saved recipe. This replaces its node and stitch edits; position, rotation and mirroring are retained. Undo restores the previous parts.'
        : 'Create editable paths with a saved recipe. A patch gets a sewing border and a dashed inner-area guide (it never sews) to design inside; motifs are placed under the border. Move groups together; select individual parts in Stitch order to edit nodes.';
      $('componentFields').disabled=false; $('previewComponent').disabled=false;
      $('componentX').value=50; $('componentY').value=50; $('componentRotation').value=0;
      options(targets.length?effectiveParams(targets):null);
      if(targets.length){
        $('componentArtwork').innerHTML=componentArtwork(targets);
        $('componentStats').textContent=`${targets.length} saved editable parts · preview stitches to rebuild from this recipe.`;
      }
      $('applyComponent').textContent=targets.length?'Rebuild editable parts':'Add editable parts';
      $('componentsDialog').showModal();
    } catch(e) { ctx.toast(e.message); }
  }
  $('componentOptions').addEventListener('change',e=>{if(e.target.matches('[data-component-option="shape"],[data-component-option="construction"],[data-component-option="borderStyle"]'))relevance();});
  $('componentKind').onchange=()=>options();
  $('componentFields').addEventListener('input', e=>{if(e.target.id!=='componentKind')clear();});
  $('componentArtworkTab').onclick=()=>showStitches(false);
  $('componentStitchTab').onclick=()=>showStitches(true);
  $('componentForm').onsubmit=async e=>{
    e.preventDefault(); clear(); const run=token; $('componentFields').disabled=true; $('previewComponent').disabled=true;
    $('componentStats').textContent='Generating actual Ink/Stitch stitches…';
    try {
      const kind=$('componentKind').value, params={};
      const spec=catalog.find(c=>c.key===(kind==='starter'?'crescent':kind)),fieldKind=k=>spec?.fields.find(f=>f.key===k)?.kind;
      // Use the recipe's declared kind: browsers without a color picker report color inputs as text.
      for(const input of $('componentOptions').querySelectorAll('input,select'))params[input.dataset.componentOption]=['color','select'].includes(fieldKind(input.dataset.componentOption))?input.value:Number(input.value);
      if(customOutline)params.outline=customOutline;
      const result=await ctx.api('/api/components',{action:kind==='starter'?'starter':'generate',kind,params,targets,
        pose:{cx:Number($('componentX').value),cy:Number($('componentY').value),rotation:Number($('componentRotation').value)}});
      const stitched=await ctx.api('/api/layer-preview',{layers:result.layers});
      if(run!==token||!$('componentsDialog').open)return;
      if(!fresh())throw new Error('The design changed. Open patches again.');
      if(ctx.getProject().layers.length-targets.length+result.layers.length>MAX_LAYERS)throw new Error(`The result exceeds ${MAX_LAYERS} layers. Remove unused parts first.`);
      proposal={...result,preview:stitched.preview};
      $('componentArtwork').innerHTML=componentArtwork(result.layers);
      const p=proposal.preview;
      $('componentStats').textContent=`${result.layers.length} editable parts · ${p.stitches.toLocaleString()} stitches · ${p.width} × ${p.height} mm`;
      $('componentWarnings').textContent=[...(result.warnings||[]),...(result.fit&&!result.fit.fits?['Some starter parts cross the content guide at this size. Adjust them and check scene fit.']:[])].join(' ');
      $('componentStitchTab').disabled=false; $('applyComponent').hidden=false; showStitches(false);
    } catch(e) { if(run===token){$('componentError').textContent=e.message;$('componentStats').textContent='';} }
    finally {if(run===token){$('componentFields').disabled=false;$('previewComponent').disabled=false;$('componentKind').disabled=!!targets.length;}}
  };
  $('applyComponent').onclick=()=>{
    try {
      if(!proposal||!fresh())throw new Error('The design changed. Preview again.');
      const p=ctx.getProject(), parts=proposal.layers;
      ctx.mutate(()=>{
        if(targets.length)p.layers=replaceComponentParts(p.layers,targets,parts);
        else {
          const edge=p.layers.findIndex(l=>['crescent','patch'].includes(l.component?.kind)&&['edge','edge-shadow'].includes(l.component.part));
          const index=['mushroom','branch','motif'].includes($('componentKind').value)?edge:-1;
          p.layers.splice(index<0?p.layers.length:index,0,...parts);
        }
        ctx.select(parts.map(l=>l.id));
      });
      $('componentsDialog').close(); ctx.setTab('arrange');ctx.toast('Editable parts added. The inner-area guide does not sew.');
    }catch(e){$('componentError').textContent=e.message;}
  };
  for(const id of ['closeComponents','cancelComponents'])$(id).onclick=()=>$('componentsDialog').close();
  $('componentsDialog').addEventListener('close',()=>token++);
  new ResizeObserver(()=>{if($('componentsDialog').open&&!$('componentStitches').hidden&&proposal?.preview)drawPlan($('componentStitches'),proposal.preview);}).observe($('componentStitches'));

  function clearArea(){areaProposal=null;areaToken++;$('applyContentArea').hidden=true;$('areaArtwork').hidden=true;$('areaStats').textContent='';$('areaError').textContent='';$('previewContentArea').disabled=false;}
  function openArea(source=null) {
    try {
      const p=ctx.getProject(), selected=source||ctx.chosen()[0];
      areaSource=selected?.role==='content-area'?p.layers.find(l=>l.id===selected.areaSource):selected;
      if(areaSource?.component?.kind==='crescent')areaSource=componentGroup(p,areaSource).find(l=>l.component.part==='body');
      if(!areaSource||!['path','rectangle','ellipse'].includes(areaSource.type)||areaSource.locked)throw new Error('Select an unlocked, closed patch shape.');
      oldArea=p.layers.find(l=>l.role==='content-area'&&l.areaSource===areaSource.id);
      if(oldArea?.locked)throw new Error('Unlock the inner-area guide before refreshing it.');
      const edge=componentGroup(p,areaSource).find(l=>l.component.part==='edge');
      areaSource=structuredClone(areaSource); oldArea=oldArea?structuredClone(oldArea):null;
      areaPid=p.id;areaRevision=ctx.getRevision();clearArea();
      $('areaBorder').value=edge?.merrow?.width??edge?.strokeWidth??oldArea?.areaSettings?.borderWidth??2;
      $('areaGap').value=oldArea?.areaSettings?.clearance??.8;
      $('areaCompensation').value=Math.max(areaSource.pullCompensation||0,oldArea?.areaSettings?.compensation||0);
      $('previewContentArea').disabled=false;$('contentAreaDialog').showModal();
    }catch(e){ctx.toast(e.message);}
  }
  for(const id of ['areaBorder','areaGap','areaCompensation'])$(id).oninput=clearArea;
  $('contentAreaForm').onsubmit=async e=>{
    e.preventDefault();clearArea();const run=areaToken;$('previewContentArea').disabled=true;
    try{
      const r=await ctx.api('/api/components',{action:'refresh-area',source:areaSource,borderWidth:Number($('areaBorder').value),clearance:Number($('areaGap').value),compensation:Number($('areaCompensation').value)});
      if(run!==areaToken||!$('contentAreaDialog').open)return;
      if(!areaFresh())throw new Error('The design changed. Open inner area again.');
      areaProposal=r.layers[0];
      if(oldArea)Object.assign(areaProposal,{id:oldArea.id,component:oldArea.component});
      $('areaArtwork').innerHTML=componentArtwork([areaSource,areaProposal]);$('areaArtwork').hidden=false;
      $('areaStats').textContent=`${r.areaMm2} mm² usable · ${round(areaProposal.areaInset)} mm inset. ${(r.warnings||[]).join(' ')}`;
      $('applyContentArea').hidden=false;
    }catch(e){if(run===areaToken)$('areaError').textContent=e.message;}
    finally{if(run===areaToken)$('previewContentArea').disabled=false;}
  };
  $('applyContentArea').onclick=()=>{
    try{
      if(!areaProposal||!areaFresh())throw new Error('The design changed. Preview again.');
      const p=ctx.getProject();if(!oldArea&&p.layers.length>=MAX_LAYERS)throw new Error(`A project can contain up to ${MAX_LAYERS} layers.`);
      ctx.mutate(()=>{
        if(oldArea)p.layers=replaceComponentParts(p.layers,[oldArea],[areaProposal]);
        else p.layers.splice(p.layers.findIndex(l=>l.id===areaSource.id)+1,0,areaProposal);
        ctx.select([areaProposal.id]);
      });$('contentAreaDialog').close();ctx.toast('Inner-area guide updated from the current outline.');
    }catch(e){$('areaError').textContent=e.message;}
  };
  for(const id of ['closeContentArea','cancelContentArea'])$(id).onclick=()=>$('contentAreaDialog').close();
  $('contentAreaDialog').addEventListener('close',()=>areaToken++);
  function openFit(){
    const areas=ctx.getProject().layers.filter(l=>l.role==='content-area'&&l.visible!==false);
    if(!areas.length)return ctx.toast('Build a usable inner area first.');
    $('fitArea').innerHTML=areas.map(l=>`<option value="${l.id}">${esc(l.name)}</option>`).join('');
    $('componentFitStatus').textContent='';$('componentFitFindings').replaceChildren();$('componentFitDialog').showModal();
  }
  $('runComponentFit').onclick=async()=>{
    const p=ctx.getProject(), rev=ctx.getRevision(), button=$('runComponentFit');
    const area=p.layers.find(l=>l.id===$('fitArea').value);
    const motifs=p.layers.filter(l=>l.component&&l.component.kind!=='crescent'&&l.visible!==false);
    const layers=motifs.length?motifs:ctx.chosen().filter(l=>l.id!==area?.areaSource&&l.role!=='content-area');
    button.disabled=true;$('componentFitStatus').textContent='Checking full motif footprints…';$('componentFitFindings').replaceChildren();
    try{
      if(!layers.length)throw new Error('Add a motif or select artwork to check.');
      const findings=[];let checked=0;
      for(let i=0;i<layers.length;i+=30){const r=await ctx.api('/api/components',{action:'check-fit',area,layers:layers.slice(i,i+30)});findings.push(...r.findings);checked+=r.checked;}
      if(p.id!==ctx.getProject().id||rev!==ctx.getRevision())throw new Error('The design changed. Check again.');
      $('componentFitStatus').textContent=findings.length?`${findings.length} of ${checked} parts cross the current inner-area guide.`:`All ${checked} motif parts fit inside the current inner area.`;
      $('componentFitFindings').innerHTML=findings.map(f=>`<p class="check-finding">${esc(f.name)} · ${f.outsideMm2} mm² outside</p>`).join('');
    }catch(e){$('componentFitStatus').textContent=e.message;}finally{button.disabled=false;}
  };
  $('closeComponentFit').onclick=()=>$('componentFitDialog').close();
  function mount(host) {
    const list=ctx.chosen(), group=componentGroup(ctx.getProject(),list[0]);
    const same=group.length&&list.every(l=>group.some(g=>g.id===l.id))&&!list[0]?.sceneBinding;
    const source=list.length===1&&['path','rectangle','ellipse'].includes(list[0].type)?list[0]:null;
    const shapes=list.filter(l=>['path','rectangle','ellipse'].includes(l.type)&&(l.role||'artwork')==='artwork'&&l.visible!==false);
    host.insertAdjacentHTML('beforeend',`<div class="component-controls"><h3>Patches & motifs</h3><button id="addComponent" class="wide">Add patch or reusable motif</button>${same?'<button id="editComponent" class="wide">Edit component recipe</button>':''}${source&&!source.component&&source.role!=='content-area'?'<button id="shapeToPatch" class="wide">Make selected shape a patch</button>':''}${source?'<button id="editContentArea" class="wide">Build / refresh inner area</button>':''}<button id="checkComponentFit" class="wide">Check scene fit in inner area</button>${shapes.length?`<button id="saveMotif" class="wide">Save selection as motif${shapes.length>1?` (${shapes.length} shapes)`:''}</button>`:''}${source?.role==='content-area'?'<p class="caption">This editable guide does not sew. Select Digitize → Edit nodes to customize it. Refresh rebuilds it from the source patch.</p>':''}</div>`);
    $('addComponent').onclick=()=>open();if(same)$('editComponent').onclick=()=>open(list[0].component.kind,true);
    if(source)$('editContentArea').onclick=()=>openArea(source);
    if($('shapeToPatch'))$('shapeToPatch').onclick=()=>shapeToPatch(source);
    if($('saveMotif'))$('saveMotif').onclick=()=>openMotifs(shapes);$('checkComponentFit').onclick=openFit;
  }
  async function shapeToPatch(source){
    try{
      const p=ctx.getProject(),id=p.id,rev=ctx.getRevision();
      const result=await ctx.api('/api/components',{action:'patch-from-shape',source,params:{}});
      if(ctx.getProject().id!==id||ctx.getRevision()!==rev)throw new Error('The design changed. Try again.');
      if(p.layers.length+result.layers.length>MAX_LAYERS)throw new Error(`The patch would exceed ${MAX_LAYERS} layers.`);
      ctx.mutate(()=>{
        const i=p.layers.findIndex(l=>l.id===source.id),original=p.layers[i];
        // Keep the source shape as a hidden reference; the patch takes its place in sewing order.
        original.visible=false;original.name=(original.name||'Shape')+' · patch source (hidden)';
        p.layers.splice(i+1,0,...result.layers);ctx.select([result.layers[0].id]);
      });
      ctx.toast('Patch created from the shape. Edit component recipe to change appliqué, border or colors; Undo restores the shape.');
    }catch(e){ctx.toast(e.message);}
  }
  async function openMotifs(shapes){
    let d=$('motifDialog');
    if(!d){document.body.insertAdjacentHTML('beforeend',`<dialog id="motifDialog" class="motif-dialog" aria-labelledby="motifTitle"><div class="dialog-heading"><div><span class="eyebrow">MOTIF LIBRARY</span><h2 id="motifTitle">Save as a reusable motif.</h2></div><button id="closeMotif" class="icon-button" aria-label="Close motif library">×</button></div>
      <p class="caption">Saved motifs keep their shapes, threads and stitch settings. Add them from Patches → Saved motif, or along a scene guide with ＋ Saved motif.</p>
      <label>Motif name<input id="motifName" maxlength="80" placeholder="e.g. Star and dot" autocomplete="off"></label><p id="motifError" class="error" role="alert"></p>
      <div class="dialog-footer"><button id="cancelMotif" type="button">Cancel</button><button id="saveMotifNow" class="primary" type="button">Save motif</button></div>
      <h3>Saved motifs</h3><div id="motifList" class="motif-list"></div></dialog>`);d=$('motifDialog');
      for(const id of ['closeMotif','cancelMotif'])$(id).onclick=()=>d.close();}
    const list=async()=>{try{const items=await ctx.api('/api/motifs',{action:'list'});$('motifList').innerHTML=items.length?items.map(m=>`<div class="motif-row"><span>${esc(m.name)}<small>${m.parts} part${m.parts===1?'':'s'} · ${Math.round(m.width)} × ${Math.round(m.height)} mm</small></span><button data-delete-motif="${esc(m.id)}" class="danger" aria-label="Delete ${esc(m.name)}">Delete</button></div>`).join(''):'<p class="caption">None yet.</p>';
      for(const b of $('motifList').querySelectorAll('[data-delete-motif]'))b.onclick=async()=>{await ctx.api('/api/motifs',{action:'delete',id:b.dataset.deleteMotif});list();};}catch(e){$('motifError').textContent=e.message;}};
    $('motifError').textContent='';$('motifName').value='';$('saveMotifNow').disabled=!shapes.length;
    $('saveMotifNow').onclick=async()=>{try{const name=$('motifName').value.trim();if(!name)throw new Error('Name the motif.');const m=await ctx.api('/api/motifs',{action:'save',name,layers:structuredClone(shapes)});ctx.toast(`Saved “${m.name}” (${Math.round(m.width)} × ${Math.round(m.height)} mm).`);$('motifName').value='';list();}catch(e){$('motifError').textContent=e.message;}};
    d.showModal();list();
  }
  return {open,mount,openArea,openFit};
}
