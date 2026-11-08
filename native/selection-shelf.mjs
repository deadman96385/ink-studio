import {selectionShelfModel} from './selection-shelf-model.mjs';

const STORAGE='inkstudio-selection-shelf-v1';

export function createSelectionShelf({host,getState,finder,edit,toast}){
  let collapsed=false;
  try{collapsed=localStorage.getItem(STORAGE)==='collapsed';}catch{}
  const slotMarkup=i=>`<div class="shelf-slot" data-shelf-slot="${i}"><button type="button"><span class="shelf-action-label"></span><span class="shelf-action-value" hidden></span></button><label class="shelf-editor" hidden><span class="shelf-editor-label"></span><input type="number" inputmode="decimal" step="any" required aria-describedby="selectionShelfStatus"></label></div>`;
  host.innerHTML=`<div class="shelf-heading"><div class="shelf-selection"><h2 id="selectionShelfName"></h2><p id="selectionShelfType"></p></div><button id="shelfProtection" type="button" hidden aria-label="Open protection controls for locked artwork">Locked</button><button id="shelfFind" type="button" aria-haspopup="dialog" aria-controls="toolFinderDialog">All tools</button><button id="shelfToggle" type="button" aria-label="Collapse selection shortcuts" aria-controls="selectionShelfControls selectionShelfNote selectionShelfStatus" aria-expanded="true"><span aria-hidden="true">⌃</span></button></div><div id="selectionShelfControls" class="shelf-controls" role="group" aria-label="Actions for selected artwork">${Array.from({length:4},(_,i)=>slotMarkup(i)).join('')}<div id="shelfPositions" class="shelf-positions" role="group" aria-label="Selection position">${slotMarkup('x')}${slotMarkup('y')}</div><div id="shelfDimensions" class="shelf-dimensions" role="group" aria-label="Selection size">${slotMarkup('width')}<button id="shelfProportions" type="button" aria-label="Keep proportions" aria-pressed="true"><span aria-hidden="true">🔗</span></button>${slotMarkup('height')}</div></div><p id="selectionShelfNote" class="shelf-note" hidden></p><p id="selectionShelfStatus" class="shelf-note" role="status" aria-live="polite" hidden></p>`;
  const $=id=>host.querySelector('#'+id),slots=[...host.querySelectorAll('[data-shelf-slot]')],edits=new Map();
  let currentEditors=[],lastEditor='';
  const selectionStamp=()=>{const state=getState();return JSON.stringify([state.projectId,state.mode,state.selection.map(l=>l.id)]);};
  async function afterEdit(action){
    const stamp=selectionStamp(),pending=currentEditors.map(identity=>edits.get(identity)?.pending).filter(Boolean);
    // A quick next tap should open the updated lettering, without losing that
    // tap or opening a dialog with the recipe from before regeneration.
    if(pending.length)await Promise.allSettled(pending);
    if(stamp===selectionStamp())action();
  }
  function renderStatus(){
    const visible=currentEditors.map(identity=>edits.get(identity)),last=currentEditors.includes(lastEditor)?edits.get(lastEditor):null;
    const editing=visible.find(e=>e?.busy)||(last?.error||last?.notice?last:visible.find(e=>e?.error||e?.notice));
    $('selectionShelfStatus').textContent=editing?.busy?editing.busyMessage:editing?.error||editing?.notice||'';
    $('selectionShelfStatus').classList.toggle('shelf-error',!!editing?.error);
    $('selectionShelfStatus').hidden=collapsed||!$('selectionShelfStatus').textContent;
  }
  function disclosure(model){
    $('selectionShelfControls').hidden=collapsed;
    $('selectionShelfNote').hidden=collapsed||!model.note;
    $('selectionShelfStatus').hidden=collapsed||!$('selectionShelfStatus').textContent;
    $('shelfToggle').setAttribute('aria-expanded',String(!collapsed));
    $('shelfToggle').setAttribute('aria-label',(collapsed?'Expand':'Collapse')+' selection shortcuts');
    $('shelfToggle').querySelector('span').textContent=collapsed?'⌄':'⌃';
    host.classList.toggle('shelf-collapsed',collapsed);
  }
  function render(){
    const state=getState(),model=selectionShelfModel(state);
    currentEditors=[];
    host.hidden=!model.visible;
    if(!model.visible)return;
    // Keep buttons and inputs mounted while values, tabs, or selections change.
    // This preserves focus and does not swallow the next finger/Pencil tap.
    $('selectionShelfName').textContent=model.title;
    $('selectionShelfName').title=model.title;
    $('selectionShelfType').textContent=model.subtitle;
    $('shelfProtection').hidden=!model.locked;
    const protectionReason=finder.describe('tool.protection')?.reason||'';
    $('shelfProtection').setAttribute('aria-disabled',String(!!protectionReason));
    $('shelfProtection').title=protectionReason||'Open protection controls';
    $('selectionShelfNote').textContent=model.locked&&protectionReason?protectionReason:model.note;
    slots.forEach(slot=>{
      const button=slot.querySelector('button'),label=slot.querySelector('label'),input=slot.querySelector('input');
      const key=slot.dataset.shelfSlot;
      const shortcut=/^[0-3]$/.test(key)?model.actions[Number(key)]:[...model.positions,...model.dimensions].find(control=>control.editor.key===key);
      if(!shortcut)slot.editRequest=null;slot.hidden=!shortcut;if(!shortcut)return;
      const editor=shortcut.editor;
      const destination=finder.describe(shortcut.entry)||(editor&&finder.describe({letterSpacing:'tool.edit-lettering',ttfSpacing:'tool.ttf'}[editor.key]));
      const reason=editor?.reason||destination?.reason||(!destination?'Find this setting in All tools.':'');
      button.hidden=!!editor;label.hidden=!editor;
      if(editor){
        const identity=JSON.stringify([state.projectId,state.selection[0].id,editor.key]);
        currentEditors.push(identity);
        const editing=edits.get(identity)||{};
        const type=editor.type||'number';if(input.type!==type)input.type=type;input.inputMode=type==='color'?'':'decimal';input.required=type!=='color';
        // A draft belongs to one project, layer and setting, including when the
        // same shelf position is reused for a different kind of artwork.
        if(input.dataset.shelfIdentity!==identity||document.activeElement!==input)input.value=editing.busy?editing.draft:editor.displayValue??editor.value;
        input.dataset.shelfIdentity=identity;input.dataset.shelfSetting=editor.key;
        slot.editorValue=editor.displayValue??editor.value;
        if(type==='color'){input.removeAttribute('min');input.removeAttribute('max');}else{input.min=editor.min;input.max=editor.max;}
        input.disabled=!!reason||!!editing.busy;
        input.setAttribute('aria-label',type==='color'?(shortcut.label==='First thread'?'First satin thread color':'Thread color'):shortcut.label+' ('+editor.unit+')');
        input.setAttribute('aria-invalid',String(!!editing.error&&!input.validity.valid));
        input.setAttribute('aria-busy',String(!!editing.busy));
        input.title=reason||(type==='color'?'Choose a thread color.':`${editor.help||destination?.title||shortcut.label}. ${editor.min}–${editor.max} ${editor.unit}. Press Enter or tap away to apply.`);
        label.querySelector('span').textContent=shortcut.label+(type==='color'?'':' · '+editor.unit);
        label.title=reason||destination?.title||shortcut.label;
        slot.editRequest={identity,projectId:state.projectId,layerId:state.selection[0].id,key:editor.key,type,unit:editor.unit,unchangedValue:editor.displayValue};
      }else slot.editRequest=null;
      button.dataset.shelfEntry=shortcut.entry;
      button.setAttribute('aria-disabled',String(!!reason));
      button.setAttribute('aria-label',(destination?.title||shortcut.label)+(shortcut.value?' · '+shortcut.value:'')+(reason?'. '+reason:''));
      button.title=reason||destination?.title||shortcut.label;
      button.querySelector('.shelf-action-label').textContent=shortcut.label;
      const value=button.querySelector('.shelf-action-value');value.textContent=shortcut.value;value.hidden=!shortcut.value;
    });
    $('shelfPositions').hidden=!model.positions?.length;
    $('shelfDimensions').hidden=!model.dimensions?.length;
    const proportions=model.proportions;
    $('shelfProportions').disabled=!proportions||proportions.disabled||proportions.fixed;
    $('shelfProportions').setAttribute('aria-pressed',String(!!proportions?.value));
    $('shelfProportions').title=proportions?.fixed?'Embroidery lettering keeps its font proportions.':proportions?.value?'Keep proportions. Tap to resize width and height independently.':'Resize width and height independently. Tap to keep proportions.';
    $('shelfProportions').querySelector('span').textContent=proportions?.value?'🔗':'↔';
    renderStatus();
    disclosure(model);
  }
  slots.forEach(slot=>{
    const button=slot.querySelector('button'),input=slot.querySelector('input');
    button.onclick=()=>{const entry=button.dataset.shelfEntry;return afterEdit(()=>finder.navigateTo(entry));};
    input.oninput=()=>{const request=slot.editRequest;if(request){lastEditor=request.identity;edits.delete(request.identity);input.setAttribute('aria-invalid','false');renderStatus();}};
    const commit=async()=>{
      const request=slot.editRequest;if(!request||input.disabled)return;
      const value=request.type==='color'?input.value:Number(input.value);
      const status={draft:value,busyMessage:request.type==='color'?'Updating thread color…':['x','y'].includes(request.key)?'Moving artwork…':['width','height'].includes(request.key)?'Resizing artwork…':'Updating spacing…'};edits.set(request.identity,status);lastEditor=request.identity;
      try{
        if(!input.value||!input.validity.valid)throw new Error(request.type==='color'?'Choose a valid thread color.':`Choose a value from ${input.min} to ${input.max} ${request.unit}.`);
        // Showing readable millimeters must not resize high-precision artwork
        // merely because an unchanged field was focused and blurred.
        if(request.unchangedValue!==undefined&&value===request.unchangedValue)return;
        // Finish a lettering rebuild before applying a second setting, so a
        // quick color choice cannot invalidate the spacing edit just committed.
        const pending=currentEditors.filter(identity=>identity!==request.identity).map(identity=>edits.get(identity)?.pending).filter(Boolean);
        const apply=()=>edit({...request,value});
        const result=pending.length?Promise.allSettled(pending).then(apply):apply();
        if(result?.then){status.busy=true;status.pending=result;render();const outcome=await result;status.notice=outcome?.notice||'';}
      }catch(error){status.error=error.message;if(!currentEditors.includes(request.identity))toast?.(error.message);}
      finally{status.busy=false;status.pending=null;render();}
    };
    input.onchange=commit;
    input.onblur=()=>{commit();if(!input.validity.valid)render();};
    input.onkeydown=e=>{
      if(e.key==='Enter'){e.preventDefault();e.stopPropagation();commit();input.blur();}
      if(e.key==='Escape'){e.preventDefault();e.stopPropagation();const request=slot.editRequest;if(request)edits.delete(request.identity);input.value=slot.editorValue;input.blur();render();}
    };
  });
  $('shelfProportions').onclick=()=>afterEdit(()=>{
    const state=getState(),model=selectionShelfModel(state);if(!model.proportions)return;
    try{edit({projectId:state.projectId,layerId:state.selection[0].id,key:'aspectLock',value:!model.proportions.value});}catch(error){toast?.(error.message);}
  });
  $('shelfFind').onclick=()=>afterEdit(()=>finder.open(''));
  $('shelfProtection').onclick=()=>afterEdit(()=>finder.navigateTo('tool.protection'));
  $('shelfToggle').onclick=()=>{
    collapsed=!collapsed;
    try{localStorage.setItem(STORAGE,collapsed?'collapsed':'expanded');}catch{}
    disclosure(selectionShelfModel(getState()));
  };
  render();
  return {render};
}
