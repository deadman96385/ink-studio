import {MAX_LAYERS} from './limits.mjs';
import {drawPlan} from './advanced.mjs';

const defaults={height:12,widthScale:100,lineGap:2,letterSpacing:0,align:'center',direction:'auto',spacing:.4,pullCompensation:.1,maxLength:6,underlay:true};
const svgNode=(tag,attrs={})=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);return e;};

export function resizedTTFSettings(layer){
  if(!layer?.ttfLettering)return {...defaults};
  const recipe=structuredClone(layer.ttfLettering),sx=layer.width/recipe.width,sy=layer.height/recipe.blockHeight;
  return {...recipe,height:recipe.height*sy,widthScale:recipe.widthScale*sx/sy};
}

export function applyTTFLettering(project,proposal,targetId=null){
  const index=targetId===null?-1:project.layers.findIndex(l=>l.id===targetId);
  if(targetId!==null&&index<0)throw new Error('The lettering was removed. Reopen this tool.');
  if(index<0&&project.layers.length>=MAX_LAYERS)throw new Error(`This design already contains ${MAX_LAYERS} layers.`);
  const old=index>=0?project.layers[index]:null;
  if(old?.locked||old?.link||old?.linkedHelper)throw new Error('Unlock or detach the lettering before replacing it.');
  const layer=structuredClone(proposal.layer);
  if(old){
    layer.id=old.id;
    for(const key of ['groupId','visible','background','trimAfter','pauseAfter','entry','exit','ignoreObject','ignoreLayer'])if(key in old)layer[key]=structuredClone(old[key]);
    project.layers.splice(index,1,layer);
  }else project.layers.push(layer);
  return layer.id;
}

export function drawTTFArtwork(host,layer,node=svgNode){
  const d=layer.ttfLettering?.artwork;
  if(typeof d==='string')host.append(node('path',{d,fill:layer.color,stroke:'none','fill-rule':'nonzero'}));
}

export function createTTFLettering(ctx){
  const $=id=>document.getElementById(id);let fonts=[],target=null,pid,revision,token=0,result=null,busy=false,resume=null,applied=false;
  document.body.insertAdjacentHTML('beforeend',`<dialog id="ttfDialog" class="ttf-dialog" aria-labelledby="ttfTitle">
    <div class="dialog-heading"><div><span class="eyebrow">YOUR TYPE, IN THREAD</span><h2 id="ttfTitle">TTF / OTF lettering.</h2></div><button id="closeTtf" class="icon-button" aria-label="Close TTF/OTF lettering">×</button></div>
    <p class="caption">Upload a font, enter your words, and preview the satin stitches. Simple, bold fonts give the clearest results.</p>
    <form id="ttfForm"><div class="ttf-workspace"><section class="ttf-stage">
      <div class="button-row"><button id="ttfShowArtwork" type="button" aria-pressed="false" disabled>Artwork</button><button id="ttfShowStitches" type="button" aria-pressed="true" disabled>Stitches</button></div>
      <svg id="ttfArtwork" viewBox="0 0 100 100" aria-label="Converted lettering outlines" hidden></svg><canvas id="ttfCanvas" aria-label="Actual generated satin-lettering stitches"></canvas>
      <p id="ttfStats" role="status" aria-live="polite" class="caption">Preview to see your satin lettering.</p><ul id="ttfWarnings" class="ttf-warnings"></ul>
      <p class="caption">Apply adds an editable lettering block. Change the words later with Edit TTF/OTF lettering, or use Separate paths to edit individual rails and rungs.</p>
    </section><fieldset id="ttfFields"><legend class="sr-only">Font and lettering settings</legend>
      <label>Uploaded font<select id="ttfFont" required><option value="">Import a TTF/OTF font…</option></select></label>
      <button id="ttfImport" type="button" class="wide">Import TTF / OTF font</button><input id="ttfFile" type="file" accept=".ttf,.otf,font/ttf,font/otf" hidden>
      <p id="ttfFontInfo" class="caption"></p><details id="ttfLicense" class="control-section" hidden><summary>Font information</summary><p id="ttfLicenseText" class="caption"></p></details>
      <label>Your text<textarea id="ttfText" rows="3" maxlength="120" required placeholder="Your words here"></textarea></label>
      <div class="field-row"><label>Capital height (mm)<input id="ttfHeight" type="number" min="3" max="50" step="any" value="12" required></label><label>Thread color<input id="ttfColor" type="color" value="#203f38"></label></div>
      <label>Align lines<select id="ttfAlign"><option value="left">Left</option><option value="center" selected>Center</option><option value="right">Right</option></select></label>
      <details class="control-section"><summary>Spacing & width</summary><div class="field-row"><label>Extra line gap (mm)<input id="ttfLineGap" type="number" min="0" max="30" step="any" value="2" required></label><label>Letter spacing (mm)<input id="ttfLetterSpacing" type="number" min="-1" max="10" step="any" value="0" required></label></div><label>Letter width (%)<input id="ttfWidthScale" type="number" min="25" max="400" step="any" value="100" required></label><label>Text direction<select id="ttfDirection"><option value="auto">Automatic</option><option value="ltr">Left to right</option><option value="rtl">Right to left</option></select></label><p class="caption">Font kerning and ligatures are preserved at zero added letter spacing. Each line is shaped in its selected direction.</p></details>
      <details class="control-section"><summary>Satin settings</summary><label>Stitch spacing (mm)<input id="ttfSpacing" type="number" min="0.2" max="1.5" step="any" value="0.4" required></label><label>Pull compensation per side (mm)<input id="ttfCompensation" type="number" min="0" max="1" step="any" value="0.1" required></label><label>Maximum stitch length (mm)<input id="ttfMaxLength" type="number" min="1" max="12" step="any" value="6" required></label><label class="check"><input id="ttfUnderlay" type="checkbox" checked>Center-walk underlay</label></details>
      <p class="caption">Uploaded fonts are reusable here and travel with editable project backups. Existing embroidery fonts remain in the regular picker.</p>
    </fieldset></div><p id="ttfError" class="error" role="alert"></p><div class="dialog-footer"><button id="cancelTtf" type="button">Cancel</button><button id="previewTtf" class="primary">Preview satin stitches</button><button id="applyTtf" type="button" class="primary" disabled>Add lettering</button></div></form>
  </dialog>`);
  const fieldMap={height:'ttfHeight',widthScale:'ttfWidthScale',lineGap:'ttfLineGap',letterSpacing:'ttfLetterSpacing',align:'ttfAlign',direction:'ttfDirection',spacing:'ttfSpacing',pullCompensation:'ttfCompensation',maxLength:'ttfMaxLength',underlay:'ttfUnderlay'};
  const fresh=()=>ctx.getProject().id===pid&&ctx.getRevision()===revision;
  function assertFresh(){if(!fresh())throw new Error('The design changed. Reopen TTF/OTF lettering before applying.');}
  function working(value){
    busy=value;$('ttfFields').disabled=value;$('previewTtf').disabled=value||!$('ttfFont').value;
    $('applyTtf').disabled=value||!result;$('previewTtf').textContent=value?'Preparing…':'Preview satin stitches';
    for(const id of ['ttfShowArtwork','ttfShowStitches'])$(id).disabled=value||!result;
  }
  function view(stitches=true){
    $('ttfArtwork').toggleAttribute('hidden',stitches);$('ttfCanvas').hidden=!stitches;
    $('ttfShowArtwork').setAttribute('aria-pressed',String(!stitches));$('ttfShowStitches').setAttribute('aria-pressed',String(stitches));
    if(stitches&&result){const preview=result.preview;requestAnimationFrame(()=>{if(result?.preview===preview&&!$('ttfCanvas').hidden)drawPlan($('ttfCanvas'),preview);});}
  }
  function invalidate(){
    token++;result=null;$('ttfError').textContent='';$('ttfStats').textContent='Preview to see the current text and satin settings.';$('ttfWarnings').replaceChildren();
    $('ttfCanvas').getContext('2d').clearRect(0,0,$('ttfCanvas').width,$('ttfCanvas').height);$('ttfArtwork').replaceChildren();view();working(false);
  }
  function fontInfo(){
    const f=fonts.find(f=>f.key===$('ttfFont').value);
    $('ttfFontInfo').textContent=f?`${f.name} · ${f.format} · ${f.glyphCount.toLocaleString()} glyphs`:'';
    $('ttfLicense').hidden=!f?.license&&!f?.copyright;$('ttfLicenseText').textContent=[f?.copyright,f?.license].filter(Boolean).join('\n\n');
  }
  function fontOptions(key){
    $('ttfFont').replaceChildren(new Option('Choose an uploaded font…',''),...fonts.map(f=>new Option(f.name,f.key)));
    if(fonts.some(f=>f.key===key))$('ttfFont').value=key;
    fontInfo();working(false);
  }
  function read(){
    const p={font:$('ttfFont').value,text:$('ttfText').value};
    for(const[key,id]of Object.entries(fieldMap)){
      const input=$(id);if(!input.validity.valid||input.type==='number'&&!input.value)throw new Error('Check the lettering settings.');
      p[key]=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;
    }
    return p;
  }
  function artwork(){
    const svg=$('ttfArtwork'),l=result.layer;svg.replaceChildren(svgNode('rect',{width:100,height:100,fill:ctx.getProject().fabric||'#faf7f0'}));
    const g=svgNode('g',{transform:`translate(${l.x} ${l.y}) rotate(${l.rotation||0} ${l.width/2} ${l.height/2}) translate(${l.flipX?l.width:0} ${l.flipY?l.height:0}) scale(${l.flipX?-1:1} ${l.flipY?-1:1})`});drawTTFArtwork(g,l);svg.append(g);
  }
  $('ttfFields').oninput=e=>{invalidate();if(e.target.id==='ttfFont'){fontInfo();try{localStorage.setItem('inkstudio-outline-font',e.target.value);}catch{}}};
  $('ttfImport').onclick=()=>$('ttfFile').click();
  $('ttfFile').onchange=async e=>{
    const file=e.target.files[0];e.target.value='';if(!file)return;invalidate();const run=token;
    try{
      assertFresh();if(!/\.(ttf|otf)$/i.test(file.name)||file.size>8*1024*1024)throw new Error('Choose a TTF/OTF file smaller than 8 MB.');
      working(true);$('ttfFontInfo').textContent='Reading font…';
      const content=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(new Error('The font file could not be read.'));r.readAsDataURL(file);});
      const info=await ctx.api('/api/outline-font-import',{name:file.name,content});
      if(run!==token||!$('ttfDialog').open)return;
      fonts=[...fonts.filter(f=>f.key!==info.key),info].sort((a,b)=>a.name.localeCompare(b.name));fontOptions(info.key);
      try{localStorage.setItem('inkstudio-outline-font',info.key);}catch{}
    }catch(error){if(run===token){$('ttfError').textContent=error.message;fontInfo();}}
    finally{if(run===token)working(false);}
  };
  $('ttfForm').onsubmit=async e=>{
    e.preventDefault();if(busy)return;invalidate();const run=token;
    try{
      assertFresh();const settings=read();working(true);$('ttfStats').textContent='Shaping letters and generating satin stitches…';
      const pose=target?{cx:target.x+target.width/2,cy:target.y+target.height/2,rotation:target.rotation||0,flipX:!!target.flipX,flipY:!!target.flipY}:{};
      const proposed=await ctx.api('/api/outline-lettering',{settings,color:$('ttfColor').value,pose});
      if(run!==token||!$('ttfDialog').open)return;
      assertFresh();result=proposed;artwork();view();
      $('ttfStats').textContent=`${proposed.glyphs} glyphs · ${proposed.columns} satin columns · ${proposed.preview.stitches.toLocaleString()} stitches · ${proposed.preview.trims} cuts · ${proposed.preview.width} × ${proposed.preview.height} mm`;
      $('ttfWarnings').replaceChildren(...proposed.warnings.map(w=>{const li=document.createElement('li');li.textContent=w;return li;}));
    }catch(error){if(run===token){$('ttfError').textContent=error.message;$('ttfStats').textContent='Preview could not be generated. Your design has not changed.';}}
    finally{if(run===token)working(false);}
  };
  $('applyTtf').onclick=()=>{
    try{
      assertFresh();if(!result||busy)throw new Error('Preview the current lettering before applying.');
      const project=structuredClone(ctx.getProject()),id=applyTTFLettering(project,result,target?.id||null);
      ctx.assets.set(result.asset.key,result.asset);ctx.mutate(()=>{Object.assign(ctx.getProject(),project);ctx.select([id]);});
      applied=true;$('ttfDialog').close();ctx.setTab('layer');ctx.toast('Satin lettering added. Edit the text here or separate its paths to adjust individual columns.');
    }catch(error){$('ttfError').textContent=error.message;}
  };
  for(const id of ['closeTtf','cancelTtf'])$(id).onclick=()=>$('ttfDialog').close();
  $('ttfDialog').onclose=()=>{token++;busy=false;const back=resume;resume=null;if(!applied)back?.();};
  $('ttfShowArtwork').onclick=()=>view(false);$('ttfShowStitches').onclick=()=>view();
  new ResizeObserver(()=>{if(result&&!$('ttfCanvas').hidden)drawPlan($('ttfCanvas'),result.preview);}).observe($('ttfCanvas'));
  async function open(layer=null,initial={}){
    if(layer?.locked||layer?.link||layer?.linkedHelper)return ctx.toast('Unlock or detach the lettering before editing.');
    target=layer?structuredClone(layer):null;pid=ctx.getProject().id;revision=ctx.getRevision();applied=false;resume=initial.onCancel||null;
    const p={...defaults,...resizedTTFSettings(layer)};
    for(const[key,id]of Object.entries(fieldMap)){const input=$(id);if(input.type==='checkbox')input.checked=p[key];else input.value=typeof p[key]==='number'?Number(p[key].toFixed(6)):p[key];}
    $('ttfText').value=initial.text??layer?.ttfLettering?.text??'';$('ttfColor').value=initial.color||layer?.color||'#203f38';
    $('ttfTitle').textContent=layer?'Edit TTF / OTF lettering.':'TTF / OTF lettering.';$('applyTtf').textContent=layer?'Update lettering':'Add lettering';
    $('ttfFont').replaceChildren(new Option('Loading uploaded fonts…',''));$('ttfFontInfo').textContent='';$('ttfLicense').hidden=true;invalidate();const run=token;
    $('ttfDialog').showModal();working(true);
    try{
      const list=await ctx.api('/api/outline-fonts');if(run!==token||!$('ttfDialog').open)return;fonts=list;
      let last='';try{last=localStorage.getItem('inkstudio-outline-font')||'';}catch{}
      fontOptions(p.font||last||fonts[0]?.key);
      if(p.font&&!fonts.some(f=>f.key===p.font))$('ttfError').textContent='The original font is missing. Import its TTF/OTF or restore a project backup before re-editing.';
    }catch(e){if(run===token)$('ttfError').textContent=e.message;}
    finally{if(run===token)working(false);}
  }
  function mount(host,layer=null){
    if(layer){
      if(layer.type!=='import'||!layer.ttfLettering)return;
      const button=document.createElement('button');button.id='editTtfLettering';button.className='primary wide';button.textContent='Edit TTF/OTF lettering';button.onclick=()=>open(layer);
      const title=host.querySelector('h2');if(title)title.after(button);else host.prepend(button);
    }else{host.insertAdjacentHTML('beforeend','<button id="openTtfLettering" class="wide">TTF/OTF satin lettering</button>');$('openTtfLettering').onclick=()=>open();}
  }
  return{open,mount};
}
