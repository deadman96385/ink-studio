export function stitchOrder(layers,ids){
  const map=new Map(layers.map(l=>[l.id,l]));
  const order=ids.map(id=>map.get(id)).filter(l=>l&&(l.role||'artwork')==='artwork'&&l.type!=='image');
  if(new Set(order.map(l=>l.id)).size!==order.length)throw new Error('Choose each layer only once.');
  if(order.length<2)throw new Error('Choose at least two stitched layers.');
  if(order.some(l=>l.locked))throw new Error('Unlock the chosen layers before changing their stitch order.');
  const moved=new Set(order.slice(1).map(l=>l.id)),rest=layers.filter(l=>!moved.has(l.id));
  const index=rest.indexOf(order[0]);rest.splice(index+1,0,...order.slice(1));
  return rest;
}
export function applySelectionPaths(layers,result){
  const remove=new Set(result.removeIds),sources=new Set(Object.keys(result.replacements));
  if(layers.some(l=>(sources.has(l.id)||remove.has(l.id))&&l.locked))throw new Error('Unlock artwork and attached helpers before exposing paths.');
  if([...sources].some(id=>!layers.some(l=>l.id===id)))throw new Error('The source layers changed. Find matches again.');
  return layers.flatMap(l=>result.replacements[l.id]||(remove.has(l.id)?[]:[l]));
}
export function mergeSelection(existing,matches,action){
  const hit=new Set(matches);
  if(action==='remove')return existing.filter(id=>!hit.has(id));
  if(action==='add')return [...new Set([...existing,...matches])];
  return [...existing.filter(id=>hit.has(id)),...matches.filter(id=>!existing.includes(id))];
}
