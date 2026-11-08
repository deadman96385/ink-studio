// Groups the long Digitize/Layer tool lists into collapsible sections with a
// shared-finder entry. Runs after a panel renders; it moves (not rebuilds) existing
// controls, so their handlers keep working.
const KEY='inkstudio-tool-groups-v1';
const DIGITIZE=[
  {id:'draw',title:'Draw & edit shapes',open:true,match:['Draw path','#editNodes','.operation-grid','Offset / inset','#separatePaths','#curveLettering']},
  {id:'stitch',title:'Stitch tools & routing',match:['#openEmbroideryTools','#openHelpers','#openCommands','#openStreamlines','#openFeather','#openSewingOptimizer','#routeSatin','#routeRunning','#pickSourceRegions','Cross-stitch assistant','Prepare SVG artwork']},
  {id:'check',title:'Check & inspect',match:['#digitizeCheck','#openStitchPlans','#openOrderDisplay','#openElementInfo','#openDensityMap','#openTroubleshoot']},
  {id:'thread',title:'Threads & colors',match:['#openThreadLibrary','#openThreadOrder','#createThreadPalette','#openSwatches']},
  {id:'fonts',title:'Lettering, fonts & batches',match:['#openFontLibrary','#openTtfLettering','#editTtfLettering','#openFontSamples','#openFontWorkspace','#openBatches']},
  {id:'patch',title:'Patches, scenes & linked copies',match:['.component-controls','#openMerrow','#editMerrow','#openSceneEditor','Linked copies']},
  {id:'doc',title:'Document & preferences',match:['Document & new-design']},
];
// On the Layer tab only secondary tools are grouped, below the layer's own settings.
const LAYER=[
  {id:'layer-thread',title:'Thread palettes & color lists',match:['#openThreadLibrary','#openThreadOrder','#createThreadPalette']},
  {id:'layer-patch',title:'Patches, scenes & linked copies',match:['.component-controls','#openSceneEditor','Linked copies']},
];

let state={};try{state=JSON.parse(localStorage.getItem(KEY)||'{}');}catch{}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(state));}catch{}};
const ownText=e=>(e.matches('details')?e.querySelector('summary')?.textContent:e.textContent||'').trim();

function classify(el,groups){
  for(const g of groups)for(const m of g.match){
    if(/^[#.]/.test(m)){if(el.matches(m)||el.querySelector(m))return g;}
    else if(ownText(el).includes(m)||[...el.querySelectorAll("button,summary")].some(b=>b.textContent.includes(m)))return g;
  }
  return null;
}

function group(g,els,tools){
  const d=document.createElement('details');d.className='tool-group';d.dataset.group=g.id;
  d.open=state[g.id]??!!g.open;
  const s=document.createElement('summary');s.innerHTML=`<span>${g.title}</span><small>${tools} tool${tools===1?'':'s'}</small>`;
  d.append(s,...els);d.addEventListener('toggle',()=>{if(!d.closest('.tool-searching')){state[g.id]=d.open;save();}});
  return d;
}

function blocks(host,groups,keepIntro){
  // A block = optional heading/captions + one control + trailing captions.
  const out=[];let cur=null,head=[];
  for(const child of [...host.children]){
    if(child.matches('.tool-search-open,.tool-group'))continue;
    if(keepIntro&&!out.length&&!head.length&&(child.tagName==='H2'||(child.tagName==='P'&&!child.matches('.caption'))))continue;
    if(child.matches('hr.separator')){if(cur||head.length)child.remove();continue;}
    if(child.tagName==='H3'){head.push(child);continue;}
    if(child.matches('p.caption')){if(head.length)head.push(child);else if(cur)cur.els.push(child);continue;}
    const g=classify(child,groups);
    if(g){cur={g,els:[...head,child]};out.push(cur);}
    else if(cur&&keepIntro)cur.els.push(...head,child);
    else cur=null;
    head=[];
  }
  if(head.length&&cur)cur.els.push(...head);
  return out;
}

function search(){
  const button=document.createElement('button');button.type='button';button.className='tool-search-open wide';
  button.textContent='⌕ Find any tool or setting…';button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-controls','toolFinderDialog');
  button.onclick=()=>document.dispatchEvent(new CustomEvent('inkstudio:open-finder'));
  return button;
}

export function organizeTools(host,tab){
  if(!host||!['digitize','layer'].includes(tab))return;
  const groups=tab==='digitize'?DIGITIZE:LAYER;
  const found=blocks(host,groups,tab==='digitize');if(!found.length)return;
  const by=new Map();let n=0;
  for(const b of found){for(const e of b.els)e.dataset.block=String(n);n++;if(!by.has(b.g))by.set(b.g,[]);by.get(b.g).push(b);}
  const made=[];
  for(const g of groups){
    const list=by.get(g);if(!list)continue;
    const els=list.flatMap(b=>b.els),tools=els.reduce((t,e)=>t+(e.matches('button,details')?1:e.querySelectorAll('button').length),0);
    const d=group(g,els,tools);d.dataset.defaultOpen=String(!!g.open);made.push(d);
  }
  if(tab==='digitize'){
    const anchor=[...host.children].find(e=>e.tagName==='P'&&!e.matches('.caption'))||host.querySelector('h2');
    const box=search();
    if(anchor)anchor.after(box,...made);else host.prepend(box,...made);
  }else host.append(...made);
}
