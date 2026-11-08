export const modes={'simple':'Stitch lines','realistic-vector':'Realistic vector','realistic-300':'Realistic · 300 dpi','realistic-600':'Realistic · 600 dpi'};
const nonSewing=new Set(['id','name','fabric','grid','snap','crossSnap','crossGrids','stitchPlans','stitchPlanView','orderDisplay','densityMap','troubleshootDisplay','commandDisplay','markerDisplay','printSettings','embeddedAssets','embeddedImages','embeddedFonts','embeddedStitchPlans','embeddedFontWorkspace','fontGlyph']);
function ordered(value){return Array.isArray(value)?value.map(ordered):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,ordered(value[k])])):value;}
export function signature(project){
  const source=Object.fromEntries(Object.entries(project).filter(([k])=>!nonSewing.has(k)));
  source.layers=project.layers.map(({name,locked,...l})=>l);
  const text=JSON.stringify(ordered(source));let a=2166136261,b=5381;
  for(let i=0;i<text.length;i++){a=Math.imul(a^text.charCodeAt(i),16777619);b=Math.imul(b,33)^text.charCodeAt(i);}
  return `${text.length}-${a>>>0}-${b>>>0}`;
}
export function display(project){return project.stitchPlans?.some(p=>p.visible!==false)?project.stitchPlanView||'unchanged':'unchanged';}
export function planBounds(plan,asset){const[x,y,w,h]=asset.bounds;return{x:x+(plan.x||0),y:y+(plan.y||0),w,h};}
export function comparisonView(plans,assets){
  let x0=0,y0=0,x1=100,y1=100;for(const p of plans.filter(p=>p.visible!==false)){const a=assets.get(p.key);if(!a)continue;const b=planBounds(p,a);x0=Math.min(x0,b.x);y0=Math.min(y0,b.y);x1=Math.max(x1,b.x+b.w);y1=Math.max(y1,b.y+b.h);}
  const size=Math.max(25,Math.max(x1-x0,y1-y0)+14);return{x:(x0+x1-size)/2,y:(y0+y1-size)/2,w:size,h:size};
}
export function addSnapshot(project,asset,{replace=true,side=true,locked=true,ids=null}={}){
  const rows=project.stitchPlans||[];if(!replace&&rows.length>=6)throw new Error('Keep up to six snapshots. Remove one before adding another.');
  const row={id:crypto.randomUUID(),key:asset.key,name:`${ids?'Selection':'Whole design'} · ${modes[asset.options.mode]}`,options:structuredClone(asset.options),x:side?100:0,y:0,visible:true,locked,signature:signature(project),ids,created:Date.now()};
  project.stitchPlans=replace?[...rows.slice(0,-1),row]:[...rows,row];return row;
}
export function applyEditable(project,row,layer){
  const targets=editableTargets(project,row);
  for(const l of project.layers)if(targets.has(l.id)||targets.has(l.helperTarget))l.visible=false;
  project.layers.push(layer);row.visible=false;
}
export function editableTargets(project,row){return new Set(project.layers.filter(l=>l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork')&&(!row.ids||row.ids.includes(l.id))).map(l=>l.id));}
