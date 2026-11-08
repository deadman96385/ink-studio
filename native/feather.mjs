import {drawPlan} from './advanced.mjs';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const KEYS=['type','x','y','width','height','radius','rotation','flipX','flipY','contours','points','closed','color','stitch','fillMethod','spacing','stitchLength','angle','underlay','underlaySpacing','underlayInset','pullCompensation','satinMaxLength','satinCenter','satinContour','satinZigzag','nearestStart','nearestEnd','originalParams','originalFill','originalStroke','borderEnabled','borderColor','borderStitch','borderWidth','borderSpacing','borderLength','advanced','streamlines','feather','entry','exit','routeStart','routeEnd','satinCut','trimAfter','stopAfter','trimCommand','stopCommand','ignoreObject','ignoreLayer','smallFillFallback'];
export const featherEligible=l=>!!l&&['path','rectangle','ellipse'].includes(l.type)&&(!l.role||l.role==='artwork')&&!(l.stitch==='original'&&l.merrow)&&!(l.multicolorSatin&&(l.stitch==='satin'||l.stitch==='original'))&&(l.stitch==='satin'||l.stitch==='original'&&String(l.originalParams?.satin_column).toLowerCase()==='true'||l.stitch==='fill'&&['tatami_fill','legacy_fill','guided_fill','streamline_fill','wave_fill'].includes(l.fillMethod||'tatami_fill'));
export const featherActive=l=>featherEligible(l)&&!!l.feather&&l.feather.enabled!==false&&l.feather.raggedness>0;
export const featherKey=l=>Object.fromEntries(KEYS.map(k=>[k,l[k]??null]));
export const validFeatherPreview=l=>!!l.featherPreview&&JSON.stringify(l.featherPreview.key)===JSON.stringify(featherKey(l));
export function featherMarkup(l){if(!featherActive(l)||!validFeatherPreview(l))return '';return l.featherPreview.paths.map(p=>`<path d="${esc(p.d)}" fill="none" stroke="${esc(p.color)}" stroke-width=".15" stroke-linecap="round" stroke-linejoin="round"/>`).join('');}
export function featherArtwork(l,node){const markup=featherMarkup(l);if(!markup)return null;const g=node('g');g.innerHTML=markup;return g;}
export function applyFeather(project,id,proposal){const i=project.layers.findIndex(l=>l.id===id),source=project.layers[i];if(!source||source.locked||source.link||source.linkedHelper)throw new Error('The source changed. Unlock or detach it, then reopen feathered edges.');project.layers[i]={...structuredClone(proposal.layer),id};return id;}

export function createFeather(ctx){
  const $=id=>document.getElementById(id);let source,pid,revision,token=0,result=null,busy=false;
  document.body.insertAdjacentHTML('beforeend',`<dialog id="featherDialog" class="feather-dialog" aria-labelledby="featherTitle"><div class="dialog-heading"><div><span class="eyebrow">STITCH EFFECTS</span><h2 id="featherTitle">Feathered edges.</h2></div><button id="closeFeather" class="icon-button" aria-label="Close feathered edges">×</button></div><p id="featherSource" class="caption"></p><form id="featherForm"><div class="feather-workspace"><section><canvas id="featherCanvas" aria-label="Actual feathered-edge stitches"></canvas><p id="featherStats" class="caption" role="status">Preview to see the softened edge.</p><p class="caption">The engine keeps the original underlay and interior stitches. Feathering varies how far selected top stitches reach past the edge. The shape, satin rails and flow guides remain editable.</p></section><fieldset id="featherFields"><legend class="sr-only">Feathered-edge settings</legend>
  <label class="check"><input id="featherEnabled" type="checkbox" checked>Feather the edges</label><div id="featherOptions"><label>Raggedness (mm)<input id="featherRaggedness" type="number" min="0" max="2" step="any" value="0.5" required></label><label for="featherBalance">Edge balance · <output id="featherBalanceValue">Both edges</output></label><input id="featherBalance" type="range" min="-100" max="100" step="5" value="0"><div class="feather-range-labels"><span>Left only</span><span>Both</span><span>Right only</span></div><p class="caption">Left and right follow the fill’s stitch axis; satin uses rails 1 and 2. The center feathers both equally.</p><label class="check"><input id="featherHoles" type="checkbox">Include hole edges</label><p class="caption">Off preserves holes. On softens their edges while keeping a gap to the opposite side.</p><label>Texture seed<input id="featherSeed" type="text" maxlength="80" required></label><button id="featherShuffle" type="button" class="wide">Try another texture</button><p class="caption">The same seed repeats the texture. Raggedness stays in millimeters when the artwork is resized.</p></div></fieldset></div><p id="featherError" class="error" role="alert"></p><div class="dialog-footer"><button id="cancelFeather" type="button">Cancel</button><button id="previewFeather" class="primary">Preview stitches</button><button id="applyFeather" class="primary" type="button" disabled>Apply feathering</button></div></form></dialog>`);
  const fresh=()=>ctx.getProject().id===pid&&ctx.getRevision()===revision;
  function working(on){busy=on;$('featherFields').disabled=on;$('previewFeather').disabled=on;$('applyFeather').disabled=on||!result;$('previewFeather').textContent=on?'Preparing stitches…':'Preview stitches';}
  function labels(){const b=Number($('featherBalance').value);$('featherBalanceValue').textContent=b===0?'Both edges':b===-100?'Left only':b===100?'Right only':b<0?`Left 100% · right ${100+b}%`:`Left ${100-b}% · right 100%`;for(const input of $('featherOptions').querySelectorAll('input,button'))input.disabled=!$('featherEnabled').checked;}
  function clear(){token++;result=null;$('featherError').textContent='';$('featherStats').textContent='Preview to see the current edge settings.';$('applyFeather').disabled=true;$('featherCanvas').getContext('2d').clearRect(0,0,$('featherCanvas').width,$('featherCanvas').height);labels();}
  function open(layer=ctx.chosen()[0]){
    if(!layer||ctx.chosen().length!==1||!featherEligible(layer))return ctx.toast('Select native satin, Tatami, guided fill, Streamlines or Wave Fill.');
    if(layer.locked||layer.visible===false||layer.link||layer.linkedHelper)return ctx.toast('Show, unlock or detach the selected shape first.');
    source=structuredClone(layer);pid=ctx.getProject().id;revision=ctx.getRevision();const p={enabled:true,raggedness:.5,balance:0,includeHoles:false,seed:layer.id,...layer.feather};
    $('featherEnabled').checked=p.enabled;$('featherRaggedness').value=p.raggedness;$('featherBalance').value=p.balance;$('featherHoles').checked=p.includeHoles;$('featherSeed').value=p.seed;
    $('featherSource').textContent=layer.name+' · soften selected top-stitch edges.';working(false);clear();$('featherDialog').showModal();
  }
  $('featherFields').oninput=clear;$('featherShuffle').onclick=()=>{$('featherSeed').value=crypto.randomUUID();clear();};
  $('featherForm').onsubmit=async e=>{
    e.preventDefault();if(busy)return;clear();const run=token;
    try{
      if(!fresh())throw new Error('The design changed. Reopen feathered edges.');
      for(const id of ['featherRaggedness','featherSeed'])if(!$(id).validity.valid||$(id).value==='')throw new Error('Check raggedness and the texture seed.');
      const settings={enabled:$('featherEnabled').checked,raggedness:Number($('featherRaggedness').value),balance:Number($('featherBalance').value),includeHoles:$('featherHoles').checked,seed:$('featherSeed').value};working(true);
      const proposed=await ctx.api('/api/feather',{project:ctx.getProject(),id:source.id,settings});
      if(run!==token||!$('featherDialog').open)return;if(!fresh())throw new Error('The design changed. Reopen feathered edges.');
      result=proposed;drawPlan($('featherCanvas'),proposed.preview);const p=proposed.preview;
      $('featherStats').textContent=`${proposed.stats.edges} feathered edges · ${p.stitches.toLocaleString()} stitches · ${p.trims} cuts · ${p.width} × ${p.height} mm`;
    }catch(error){if(run===token)$('featherError').textContent=error.message;}
    finally{if(run===token)working(false);}
  };
  $('applyFeather').onclick=()=>{try{if(!result||busy||!fresh())throw new Error('Preview the current edge settings before applying.');const draft=structuredClone(ctx.getProject()),id=applyFeather(draft,source.id,result);ctx.mutate(()=>{Object.assign(ctx.getProject(),draft);ctx.select([id]);});$('featherDialog').close();ctx.setTab('layer');ctx.toast(result.layer.feather.enabled?'Feathered edges applied. Undo restores the previous stitches.':'Feathering turned off.');}catch(error){$('featherError').textContent=error.message;}};
  for(const id of ['closeFeather','cancelFeather'])$(id).onclick=()=>$('featherDialog').close();$('featherDialog').onclose=()=>{token++;busy=false;};
  new ResizeObserver(()=>{if(result&&$('featherDialog').open)drawPlan($('featherCanvas'),result.preview);}).observe($('featherCanvas'));
  function mount(host,layer=null){
    if(layer&&!featherEligible(layer))return;const b=document.createElement('button');b.id=layer?'editFeather':'openFeather';b.type='button';b.className='wide'+(featherActive(layer)?' primary':'');b.textContent=featherActive(layer)?'Edit feathered edges':'Feathered edges';b.onclick=()=>open(layer||ctx.chosen()[0]);
    if(!layer){const list=ctx.chosen();b.disabled=list.length!==1||!featherEligible(list[0]);}host.append(b);
    if(featherActive(layer)){const p=document.createElement('p');p.className='caption';p.textContent=validFeatherPreview(layer)?'Feathered top stitches remain editable.':'Feathering regenerates during stitch preview. Re-preview feathered edges to refresh the canvas artwork.';host.append(p);}
  }
  return {open,mount};
}
