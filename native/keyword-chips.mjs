// Tap-to-toggle chips for Ink/Stitch font categories (desktop "Generate JSON"
// checkboxes) under the comma-separated keyword fields. The text field stays
// the source of truth; chips just add/remove the category ids in it.
export const FONT_CATEGORIES=[['applique','Appliqué'],['crossstitch','Cross stitch'],['display','Display'],['handwriting','Handwriting'],['italic','Italic'],['monogram','Monogram'],['multicolor','Multicolor'],['ripple','Ripple stitch'],['running_stitch','Running stitch'],['sans_serif','Sans serif'],['satin','Satin'],['serif','Serif'],['tartan','Tartan'],['tiny','Tiny'],['arabic','Script: Arabic'],['cyrillic','Script: Cyrillic'],['greek','Script: Greek'],['hebrew','Script: Hebrew'],['japanese','Script: Japanese'],['latin','Script: Latin']];
const FIELDS=['fmKeywords','fsKeywords'];
const native=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');
const words=input=>native.get.call(input).split(',').map(w=>w.trim()).filter(Boolean);

function sync(input){
  const set=new Set(words(input));
  for(const b of input._chips?.querySelectorAll('button')||[])b.setAttribute('aria-pressed',String(set.has(b.dataset.fontCategory)));
}

function attach(input){
  if(input._chips)return;
  const box=document.createElement('div');box.className='keyword-chips';box.setAttribute('role','group');box.setAttribute('aria-label','Font categories');
  box.innerHTML=FONT_CATEGORIES.map(([id,label])=>`<button type="button" data-font-category="${id}" aria-pressed="false">${label}</button>`).join('');
  (input.closest('label')||input).after(box);input._chips=box;
  // Keep chips in sync when code assigns .value, not only when typing.
  Object.defineProperty(input,'value',{configurable:true,get(){return native.get.call(this);},set(v){native.set.call(this,v);sync(this);}});
  input.addEventListener('input',()=>sync(input));
  box.addEventListener('click',e=>{
    const b=e.target.closest('[data-font-category]');if(!b||input.disabled)return;
    const id=b.dataset.fontCategory,list=words(input),next=list.includes(id)?list.filter(w=>w!==id):[...list,id];
    input.value=next.join(', ');input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
  });
  sync(input);
}

export function installKeywordChips(){
  const scan=()=>{for(const id of FIELDS){const el=document.getElementById(id);if(el&&!el._chips)attach(el);}};
  new MutationObserver(scan).observe(document.body,{childList:true,subtree:true});scan();
}
