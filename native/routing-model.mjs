export function placeRouting(current,sourceIds,result){
  const sources=new Set(sourceIds),removed=new Set(result.removeIds||sourceIds),outputs=new Map(result.layers.map(l=>[l.id,l])),used=new Set();
  const last=[...current].reverse().find(l=>sources.has(l.id))?.id;if(!last)throw new Error('The routing selection changed. Preview again.');
  const take=ids=>(ids||[]).map(id=>{const l=outputs.get(id);if(!l||used.has(id))throw new Error('The route has invalid path placement. Preview again.');used.add(id);return l;});
  const next=current.flatMap(l=>[...take(result.beforePlacements?.[l.id]),...(removed.has(l.id)?[]:[l]),...(sources.has(l.id)?take(result.placements?.[l.id]):[]),...(l.id===last?take(result.groupedIds):[])]);
  if(used.size!==outputs.size)throw new Error('Some routed paths are missing. Preview again.');return next;
}
