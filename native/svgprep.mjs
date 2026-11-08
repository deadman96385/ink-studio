import {drawPlan} from './advanced.mjs';
export function createSvgPreparation(ctx){
  const $=id=>document.getElementById(id);let pid,revision,ids=[],proposal=null,token=0;
  document.head.insertAdjacentHTML('beforeend','<link rel="stylesheet" href="/svgprep.css">');
  document.body.insertAdjacentHTML('beforeend',`
    <dialog id="svgPrepDialog" class="svg-prep-dialog" aria-labelledby="svgPrepTitle">
      <div class="dialog-heading"><div><span class="eyebrow">CLIPS, MASKS & NEEDLE POINTS</span><h2 id="svgPrepTitle">Prepare SVG artwork.</h2></div><button id="closeSvgPrep" class="icon-button" aria-label="Close SVG preparation">×</button></div>
      <p id="svgPrepSelection" class="caption"></p>
      <form id="svgPrepForm"><div class="svg-prep-workspace">
        <section class="svg-prep-stage"><canvas id="svgPrepCanvas" aria-label="Prepared artwork stitch preview"></canvas><p id="svgPrepStatus" role="status">Preview the resulting stitches before applying.</p><ul id="svgPrepReport"></ul></section>
        <fieldset id="svgPrepFields">
          <label>Prepare artwork<select id="svgPrepOperation"><option value="bake">Bake masks & clipping into paths</option><option value="clip">Crop with a shape</option><option value="release">Release masks & clipping</option><option value="unlink">Unlink SVG clones</option></select></label>
          <div id="svgPrepShapeFields" hidden>
            <label>Clipping shape<select id="svgPrepShape"></select></label>
            <label class="check"><input id="svgPrepInvert" type="checkbox">Keep outside the shape</label>
            <label class="check"><input id="svgPrepHideShape" type="checkbox" checked>Hide clipping shape so it does not sew</label>
            <p class="caption">The chosen closed shape crops the other selected artwork. Draw or resize it on the canvas first. Crop creates editable paths; hidden source copies and Undo recover the original.</p>
          </div>
          <label id="svgPrepOutputLabel">Output<select id="svgPrepOutput"><option value="vector">Vector fills & running paths</option><option value="needle">Editable needle points</option></select></label>
          <p id="svgPrepOutputHint" class="caption"></p>
          <details id="svgPrepMaskFields" class="control-section">
            <summary>Opacity mask cutoff & detail</summary>
            <label>Mask cutoff (%)<input id="svgPrepMaskCutoff" type="number" min="1" max="100" step="1" value="50" inputmode="decimal"></label>
            <label>Mask detail<select id="svgPrepMaskDetail"><option value="0.05">Fine · 0.05 mm</option><option value="0.1">Balanced · 0.1 mm</option><option value="0.2">Fast · 0.2 mm</option></select></label>
            <p class="caption">A lower cutoff keeps more of a faded mask; a higher cutoff keeps its more opaque areas. Inkscape renders the combined mask before it becomes a stitch boundary. Preview the result: soft transparency becomes a boundary, not lighter thread.</p>
          </details>
          <label class="check"><input id="svgPrepUnlink" type="checkbox" checked>Unlink SVG clones before preparing</label>
          <details class="control-section"><summary>Clone options</summary><label class="check"><input id="svgPrepRecursive" type="checkbox" checked>Unlink nested clones recursively</label><label class="check"><input id="svgPrepGroups" type="checkbox" checked>Group unlinked symbols</label><p class="caption">Ink/Stitch preserves the clone’s embroidery fill angle. Native linked copies also have independent controls under Layer → Linked copies & offsets.</p></details>
          <label class="check"><input id="svgPrepSource" type="checkbox" checked>Keep hidden source copies</label>
          <p class="caption">Apply keeps sewing order and attached guides. Hidden copies keep the original artwork; Undo restores the entire design. Separate SVG / lettering paths afterward to edit individual shapes or needle points.</p>
        </fieldset>
      </div><p id="svgPrepError" class="error" role="alert"></p><div class="dialog-footer"><button id="previewSvgPrep" class="primary">Preview preparation</button><button id="applySvgPrep" type="button" disabled>Apply to design</button></div></form>
    </dialog>`);
  const fresh=()=>ctx.getProject().id===pid&&ctx.getRevision()===revision;
  function options(){return {
    operation:$('svgPrepOperation').value,output:$('svgPrepOutput').value,unlink:$('svgPrepUnlink').checked,
    recursive:$('svgPrepRecursive').checked,groupSymbols:$('svgPrepGroups').checked,keepSource:$('svgPrepSource').checked,
    maskCutoff:Number($('svgPrepMaskCutoff').value),maskDetail:Number($('svgPrepMaskDetail').value),
    shapeId:$('svgPrepShape').value||null,invertClip:$('svgPrepInvert').checked,hideShape:$('svgPrepHideShape').checked
  };}
  function visibility(){
    const op=$('svgPrepOperation').value,needle=$('svgPrepOutput').value==='needle',bake=op==='bake'||op==='clip';
    $('svgPrepOutputLabel').hidden=!bake;$('svgPrepMaskFields').hidden=!bake;$('svgPrepShapeFields').hidden=op!=='clip';
    $('svgPrepOutputHint').textContent=op==='release'?'Release recovers artwork outside the clip or mask, so check its size and coverage before applying.':
      op==='unlink'?'Copies become independent SVG objects. Other clip paths and stitch settings stay attached. Bake opacity masks first to generate stitches.':
      needle?'Generate the actual stitch plan with Ink/Stitch, then make its needle points editable. Use this for cropped satin, zigzag, ripple or manual stitches. Guides are baked in and kept hidden. Later edits move individual stitches instead of recalculating fills.':
      'Vector output retains fill settings and colors. Clipped curves become editable nodes, within 0.025 mm. Running paths are cut at the boundary without adding an outline.';
    $('svgPrepUnlink').disabled=op==='unlink';
  }
  function invalidate(){token++;proposal=null;$('applySvgPrep').disabled=true;$('svgPrepStatus').textContent='Preview the resulting stitches before applying.';$('svgPrepReport').replaceChildren();$('svgPrepError').textContent='';const c=$('svgPrepCanvas');c.getContext('2d').clearRect(0,0,c.width,c.height);}
  function busy(value){$('svgPrepFields').disabled=$('previewSvgPrep').disabled=value;$('applySvgPrep').disabled=value||!proposal;$('previewSvgPrep').textContent=value?'Preparing stitches…':'Preview preparation';}
  function open(){
    const selected=ctx.chosen();if(!selected.length||selected.length>10)return ctx.toast('Select 1–10 artwork layers to prepare.');
    pid=ctx.getProject().id;revision=ctx.getRevision();ids=selected.map(l=>l.id);
    const candidates=ctx.getProject().layers.filter(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork'));
    $('svgPrepShape').replaceChildren(...candidates.map(l=>{const o=document.createElement('option');o.value=l.id;o.textContent=l.name+(l.locked?' · locked':'');return o;}));
    $('svgPrepShape').value=selected.length>1?selected.at(-1).id:candidates.find(l=>!ids.includes(l.id))?.id||'';
    invalidate();busy(false);visibility();$('svgPrepSelection').textContent=selected.map(l=>l.name).join(' · ');$('svgPrepDialog').showModal();
  }
  $('svgPrepFields').oninput=()=>{visibility();invalidate();};
  $('svgPrepForm').onsubmit=async e=>{
    e.preventDefault();invalidate();const run=token;
    try{
      if(!fresh())throw new Error('The design changed. Reopen SVG preparation.');
      const values=options();busy(true);
      const result=await ctx.api('/api/svg-prepare',{project:structuredClone(ctx.getProject()),ids,options:values});
      if(run!==token||!$('svgPrepDialog').open)return;
      if(!fresh())throw new Error('The design changed. Preview it again.');
      proposal=result;drawPlan($('svgPrepCanvas'),result.preview);
      $('svgPrepStatus').textContent=`${result.preview.stitches.toLocaleString()} stitches · ${result.preview.width} × ${result.preview.height} mm · ${result.preview.threads.length} thread steps`;
      $('svgPrepReport').replaceChildren(...result.reports.map(r=>{
        const li=document.createElement('li'),items=[];
        if(r.clones)items.push(`${r.clones} clones unlinked`);
        if(r.clippedPaths)items.push(`${r.clippedPaths} clipped paths prepared`);
        if(r.maskedPaths)items.push(`${r.maskedPaths} masked paths · ${r.maskCutoff}% cutoff`);
        if(r.releasedMasks)items.push(`${r.releasedMasks} masks released`);
        if(r.guidesBaked)items.push('guides baked in');
        li.textContent=`${r.name}: ${items.join(' · ')||'ready to edit'}`;return li;
      }));
    }catch(e){if(run===token)$('svgPrepError').textContent=e.message;}
    finally{if(run===token)busy(false);}
  };
  $('applySvgPrep').onclick=()=>{try{if(!proposal||!fresh())throw new Error('Preview the current design before applying.');ctx.mutate(()=>{for(const asset of proposal.assets)ctx.assets.set(asset.key,asset);Object.assign(ctx.getProject(),structuredClone(proposal.project));ctx.select(proposal.selectedIds);});$('svgPrepDialog').close();ctx.setTab('digitize');ctx.toast('SVG artwork prepared. Separate its paths to edit individual shapes or stitches.');}catch(e){$('svgPrepError').textContent=e.message;}};
  $('closeSvgPrep').onclick=()=>$('svgPrepDialog').close();$('svgPrepDialog').onclose=()=>{token++;busy(false);};
  new ResizeObserver(()=>{if(proposal&&$('svgPrepDialog').open)drawPlan($('svgPrepCanvas'),proposal.preview);}).observe($('svgPrepCanvas'));
  function mount(host){const list=ctx.chosen(),button=document.createElement('button');button.className='wide';button.textContent='Prepare SVG artwork';button.disabled=!list.length||list.length>10||list.some(l=>l.locked||l.visible===false||l.type==='image'||l.role&&l.role!=='artwork');button.onclick=open;host.append(button);}
  return{mount,open};
}
