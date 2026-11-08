import {PANEL_SETTINGS, SETTING_ALIASES, normalize, searchEntries, entryReason, selectionReason} from './finder-catalog.mjs';
import {fieldMatches} from './advanced.mjs';

const STORAGE='inkstudio-finder-v1';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labelText=label=>{
  const copy=label.cloneNode(true);
  copy.querySelectorAll('input,select,textarea,button,small,.caption,img,svg').forEach(e=>e.remove());
  return copy.textContent.replace(/\s+/g,' ').trim();
};
const visible=element=>!!element?.isConnected&&!element.closest('[hidden]')&&!!element.getClientRects().length;

export function revealControl(target,{focus=true}={}) {
  if(!target)return false;
  for(let parent=target.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
  if(!visible(target))return false;
  document.querySelectorAll('.finder-highlight').forEach(e=>e.classList.remove('finder-highlight'));
  const frame=target.closest('label')||target;
  frame.classList.add('finder-highlight');
  frame.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
  // A navigation result never activates the control or changes its value.
  if(focus&&!target.matches(':disabled')){
    const temporary=!target.matches('input,select,textarea,button,a,summary,[tabindex]');
    if(temporary)target.setAttribute('tabindex','-1');
    target.focus({preventScroll:true});
    if(temporary)target.addEventListener('blur',()=>target.removeAttribute('tabindex'),{once:true});
  }
  setTimeout(()=>frame.classList.remove('finder-highlight'),4500);
  return true;
}

export function createToolFinder(ctx) {
  const routes=new Map(ctx.routes.map(route=>[route.key,route]));
  const entries=new Map();let query='',category='',shown=35,navigating=false,loadError='',loading=true;
  let pins=[],recent=[],returnFocus=null,openStamp='',navigation=0,suppressReturnFocus=false;
  try{const saved=JSON.parse(localStorage.getItem(STORAGE)||'{}');pins=Array.isArray(saved.pins)?saved.pins.filter(x=>typeof x==='string').slice(0,6):[];recent=Array.isArray(saved.recent)?saved.recent.filter(x=>typeof x==='string').slice(0,8):[];}catch{}
  const save=()=>{try{localStorage.setItem(STORAGE,JSON.stringify({pins,recent}));}catch{}};
  const stamp=()=>{const state=ctx.getState();return state.project.id+'|'+state.selection.map(l=>l.id).sort().join(',');};
  document.body.insertAdjacentHTML('beforeend',`<dialog id="toolFinderDialog" class="tool-finder-dialog" aria-labelledby="toolFinderTitle">
    <div class="finder-heading"><div><span class="eyebrow">INK STUDIO</span><h2 id="toolFinderTitle">Tools & settings</h2></div><button id="closeToolFinder" type="button" class="icon-button" aria-label="Close tool finder">×</button></div>
    <label class="finder-search"><span class="sr-only">Find any tool or setting</span><input id="toolFinderSearch" type="search" placeholder="Try density, cut hole, trim, or font…" autocomplete="off" autocapitalize="none" spellcheck="false" enterkeyhint="search" autofocus></label>
    <div id="toolFinderContext" class="finder-context"></div>
    <div id="toolFinderResults" class="finder-results"></div>
    <div class="finder-footer"><span id="toolFinderStatus" role="status" aria-live="polite"></span><button id="retryFinderIndex" type="button" hidden>Retry loading settings</button><span class="finder-key">Ctrl / ⌘ K</span></div>
  </dialog>`);
  const $=id=>document.getElementById(id),dialog=$('toolFinderDialog');
  function add(entry){if(!entry.title||!routes.has(entry.route))return;const route=routes.get(entry.route);entries.set(entry.id,{category:route.category,path:route.path,requires:route.requires,...entry});}
  for(const route of routes.values())if(route.listing!==false)add({id:'tool.'+route.key,title:route.title,aliases:route.aliases,route:route.key,target:route.target,kind:'tool'});
  PANEL_SETTINGS.forEach(entry=>add({...entry,kind:'setting'}));

  function captureFields(route,root=typeof route.root==='string'?document.querySelector(route.root):null,panel=false){
    if(!root||route.fields===false)return;
    const state=ctx.getState(),single=state.selection.length===1?state.selection[0]:null;
    for(const control of root.querySelectorAll('input,select,textarea')){
      if(control.closest('#toolFinderDialog')||control.matches('[type="hidden"],[type="search"],[type="file"],[readonly]'))continue;
      if(panel&&control.closest('dialog'))continue;
      const label=control.labels?.[0]||control.closest('label');
      const title=(label?labelText(label):control.getAttribute('aria-label'))||'';
      if(!title||title.length>110)continue;
      // Repeated editors (glyph lists, color rows, scene recipes) do not have
      // stable identities across selections. Their parent tool remains indexed.
      const attr=['data-prop','data-extra','data-pen','data-reference'].find(k=>control.hasAttribute(k));
      if(!control.id&&!attr)continue;
      const target=control.id?'#'+CSS.escape(control.id):'['+attr+'="'+CSS.escape(control.getAttribute(attr))+'"]';
      if([...entries.values()].some(e=>e.route===route.key&&e.target&&control.matches(e.target)))continue;
      const section=control.closest('details')?.querySelector(':scope > summary')?.textContent.trim();
      const key=control.id||control.getAttribute(attr),id='field.'+route.key+'.'+key;
      const aliases=SETTING_ALIASES[key]||SETTING_ALIASES[key.replaceAll('-','_')]||'';
      const options=control.tagName==='SELECT'?[...control.options].map(o=>o.textContent).join(' '):'';
      const captured=single&&panel?{type:single.type,stitch:single.stitch}:null;
      add({id,title,route:route.key,target,kind:'setting',aliases:aliases+' '+options,
        path:route.path+(section?' › '+section:''),
        requires:panel&&route.key==='layer'?s=>{
          if(key==='groupColor')return selectionReason('artwork',s)||(s.selection.length>1?'':'Select multiple objects to recolor them together.');
          const reason=selectionReason(captured?.type==='image'?'image-edit':'object',s);if(reason)return reason;
          const l=s.selection[0];return captured&&(l.type!==captured.type||l.stitch!==captured.stitch)?'Select the same kind of artwork and stitch method to use this setting.':'';
        }:route.requires});
    }
  }
  for(const route of routes.values())captureFields(route);
  function capturePanel(host,tab){const route=routes.get(tab);if(route)captureFields(route,host,true);}

  function row(entry,state){
    const reason=entryReason(entry,state),pinned=pins.includes(entry.id);
    return `<div class="finder-row"><button type="button" class="finder-result" data-finder-entry="${esc(entry.id)}" ${reason?'aria-describedby="finder-require-'+esc(entry.id)+'"':''}><span class="finder-result-title">${esc(entry.title)}</span><span class="finder-result-path">${esc(entry.path)}</span>${reason?`<span class="finder-requirement" id="finder-require-${esc(entry.id)}">${esc(reason)}</span>`:''}</button><button type="button" class="finder-pin" data-finder-pin="${esc(entry.id)}" aria-label="${pinned?'Unpin':'Pin'} ${esc(entry.title)}" aria-pressed="${pinned}">${pinned?'★':'☆'}</button></div>`;
  }
  function render(){
    if(!dialog.open)return;
    const state=ctx.getState(),selected=state.selection;
    $('toolFinderContext').textContent=selected.length===1?'Selected: '+selected[0].name:selected.length?selected.length+' objects selected':'No artwork selected · selection requirements are shown below';
    const results=searchEntries(entries.values(),query,state,category),home=!query.trim()&&!category;
    let html='';
    if(home){
      for(const [title,ids] of [['Pinned',pins],['Recent',recent.filter(id=>!pins.includes(id))]]){
        const rows=ids.map(id=>entries.get(id)).filter(Boolean);if(rows.length)html+=`<section class="finder-section"><h3>${title}</h3>${rows.slice(0,title==='Pinned'?6:4).map(e=>row(e,state)).join('')}</section>`;
      }
      const categories=[...new Set([...entries.values()].map(e=>e.category))];
      html+=`<section class="finder-section"><h3>Browse</h3><div class="finder-categories">${categories.map(c=>`<button type="button" data-finder-category="${esc(c)}">${esc(c)} <span aria-hidden="true">›</span></button>`).join('')}</div></section>`;
    }else{
      html+=`<div class="finder-result-heading">${category?`<button type="button" id="finderAllTools" class="quiet">‹ All tools</button><h3>${esc(category)}</h3>`:'<h3>Search results</h3>'}<span>${results.length} ${results.length===1?'match':'matches'}</span></div>`;
      html+=results.slice(0,shown).map(entry=>row(entry,state)).join('')||'<p class="caption">No match. Try a task such as “cut hole,” or a setting such as “row spacing.”</p>';
      if(results.length>shown)html+='<button id="finderShowMore" type="button" class="wide">Show more results</button>';
    }
    $('toolFinderResults').innerHTML=html;
    $('toolFinderStatus').textContent=loadError|| (loading?'Loading additional stitch settings…':home?'Search tools, fields, and their common names.':results.length+(results.length===1?' match.':' matches.'));
    $('retryFinderIndex').hidden=!loadError;
    $('toolFinderResults').querySelectorAll('[data-finder-entry]').forEach(b=>b.onclick=()=>navigate(entries.get(b.dataset.finderEntry)));
    $('toolFinderResults').querySelectorAll('[data-finder-pin]').forEach(b=>b.onclick=()=>{
      const id=b.dataset.finderPin;
      if(!pins.includes(id)&&pins.length>=6){$('toolFinderStatus').textContent='Six tools are pinned. Unpin one to make room.';return;}
      pins=pins.includes(id)?pins.filter(x=>x!==id):[...pins,id];save();render();
      $('toolFinderResults').querySelector('[data-finder-pin="'+CSS.escape(id)+'"]')?.focus({preventScroll:true});
    });
    $('toolFinderResults').querySelectorAll('[data-finder-category]').forEach(b=>b.onclick=()=>{category=b.dataset.finderCategory;shown=35;render();$('toolFinderResults').scrollTop=0;});
    if($('finderAllTools'))$('finderAllTools').onclick=()=>{category='';render();};
    if($('finderShowMore'))$('finderShowMore').onclick=()=>{shown+=35;render();};
  }

  function open(initial=null){
    if(navigating)return;
    const other=document.querySelector('dialog[open]:not(#toolFinderDialog)');
    if(other){ctx.toast('Close the current dialog before finding another tool. Its draft settings are kept open.');return;}
    returnFocus=document.activeElement;openStamp=stamp();query=initial??query;if(initial!==null)category='';shown=35;
    $('toolFinderSearch').value=query;
    if(!dialog.open)dialog.showModal();render();$('toolFinderResults').scrollTop=0;
    $('toolFinderSearch').focus({preventScroll:true});
  }
  async function navigate(entry,fromFinder=dialog.open){
    if(!entry||navigating)return false;
    if(document.querySelector('dialog[open]:not(#toolFinderDialog)')){ctx.toast('Close the current dialog before opening another tool.');return false;}
    const reason=entryReason(entry,ctx.getState());
    if(reason){if(fromFinder)$('toolFinderStatus').textContent=reason;else ctx.toast(reason);return false;}
    const destinationStamp=fromFinder?openStamp:stamp();
    if(stamp()!==destinationStamp){$('toolFinderStatus').textContent='The selection changed. Close the finder and choose your artwork again.';return false;}
    const route=routes.get(entry.route),run=++navigation;
    navigating=true;if(dialog.open){suppressReturnFocus=true;dialog.close();}
    try{
      await route.open();
      if(run!==navigation||stamp()!==destinationStamp)throw new Error('The selection changed while opening this tool.');
      captureFields(route);
      const surface=document.querySelector(route.root||route.dialog||'#properties');
      const owner=surface?.closest('dialog');
      if(owner&&!owner.open)throw new Error(route.title+' could not be opened for this selection. Check its artwork requirements.');
      let target=entry.target?surface?.querySelector(entry.target):surface?.querySelector('h2,h3,legend');
      if(!target&&entry.target&&surface?.matches(entry.target))target=surface;
      if(!target&&!entry.target)target=surface;
      if(!target)throw new Error('That setting is not shown for this artwork. Open '+route.title+' and choose the related option first.');
      const revealed=revealControl(target);
      if(!revealed){
        const parent=target.closest('details')||surface;
        if(parent)revealControl(parent,{focus:false});
        ctx.toast('Opened '+route.title+'. '+entry.title+' appears after choosing its related option in this tool.');
      }else if(target.matches(':disabled'))ctx.toast('Opened '+entry.title+'. Its related option must be enabled before editing.');
      recent=[entry.id,...recent.filter(id=>id!==entry.id)].slice(0,8);save();
      return true;
    }catch(error){
      ctx.toast(error.message);
      if(fromFinder&&!document.querySelector('dialog[open]')){dialog.showModal();render();$('toolFinderStatus').textContent=error.message;}
      return false;
    }finally{navigating=false;}
  }

  async function loadSchemas(){
    loading=true;loadError='';render();
    const requests=await Promise.allSettled([ctx.api('/api/stitch-schema'),ctx.api('/api/embroidery-tools')]);
    if(requests[0].status==='fulfilled')for(const field of requests[0].value){
      add({id:'advanced.'+field.key,title:field.label,route:'advanced',kind:'setting',target:'[data-advanced="'+CSS.escape(field.key)+'"]',path:'Selected object › Advanced stitches › '+field.group,aliases:(field.help||'')+' '+field.key.replaceAll('_',' '),requires:state=>selectionReason('object',state)||(fieldMatches(field,state.selection[0])?'':'This setting needs a compatible stitch method ('+field.modes.join(', ')+').')});
    }
    if(requests[1].status==='fulfilled')for(const tool of requests[1].value){
      const key='operation:'+tool.key;
      routes.set(key,{key,title:tool.label,category:'Convert & prepare',path:'Tools › '+tool.group+' › '+tool.label,requires:'artwork',root:'#operationsDialog',fields:false,open:()=>ctx.openOperation(tool.key)});
      add({id:'tool.'+key,title:tool.label,route:key,kind:'tool',aliases:tool.help+' '+tool.key.replaceAll('_',' '),target:'#operationName'});
      for(const field of tool.fields)add({id:key+'.'+field.key,title:field.label,route:key,kind:'setting',target:'[data-option="'+CSS.escape(field.key)+'"]',aliases:tool.label+' '+tool.help+' '+field.key.replaceAll('_',' ')});
    }
    loading=false;
    if(requests.some(r=>r.status==='rejected'))loadError='Some engine settings could not be indexed. Tools and panel settings are still available.';
    render();
  }
  $('toolFinderSearch').oninput=e=>{query=e.target.value;if(query.trim())category='';shown=35;render();$('toolFinderResults').scrollTop=0;};
  $('toolFinderSearch').onkeydown=e=>{if(e.key==='Enter'){const first=searchEntries(entries.values(),query,ctx.getState(),category).find(entry=>!entry.reason);if(first&&query.trim()){e.preventDefault();navigate(first);}}};
  $('closeToolFinder').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{if(suppressReturnFocus){suppressReturnFocus=false;return;}if(!navigating&&!dialog.open&&returnFocus?.isConnected)returnFocus.focus({preventScroll:true});});
  $('retryFinderIndex').onclick=loadSchemas;
  $('finderBtn').onclick=()=>open();
  document.addEventListener('inkstudio:open-finder',()=>open());
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'&&!e.altKey&&!e.isComposing){if(document.querySelector('dialog[open]:not(#toolFinderDialog)'))return;e.preventDefault();if(dialog.open)$('toolFinderSearch').focus();else open();}});
  loadSchemas();
  return {open,capturePanel,
    describe(id){const entry=entries.get(id);return entry?{id:entry.id,title:entry.title,path:entry.path,reason:entryReason(entry,ctx.getState())}:null;},
    navigateTo(id){const entry=entries.get(id);if(!entry){ctx.toast('That shortcut is not available yet. Use Find to choose a tool.');return Promise.resolve(false);}return navigate(entry,false);},
  };
}
