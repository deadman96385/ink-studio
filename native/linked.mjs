// Materialized linked artwork keeps the ordinary layer/export representation.
// Placement belongs to the copy; geometry and stitch settings belong to its source.
export const LOCAL_KEYS=['id','name','x','y','width','height','rotation','flipX','flipY','visible','locked','groupId','background','aspectLock','link'];
export const OMIT_KEYS=['link','scene','sceneBinding','areaSource','component','curveSource','fontGlyph'];
const clone=v=>structuredClone(v);
export function applyLinked(source,target){
  const local=Object.fromEntries(LOCAL_KEYS.filter(k=>k in target).map(k=>[k,clone(target[k])])),link=local.link;
  const w=source.width*(target.width/(link.resolvedWidth||target.width)),h=source.height*(target.height/(link.resolvedHeight||target.height));
  const result=clone(source);for(const k of [...LOCAL_KEYS,...OMIT_KEYS])delete result[k];
  if(link.inheritColor===false)for(const k of ['color','recolor','preserveFontColors']){if(k in target)result[k]=target[k];else delete result[k];}
  if(link.inheritColor===false&&result.multicolorSatin?.bands?.length)result.multicolorSatin.bands[0].color=target.color;
  Object.assign(result,local,{width:w,height:h,x:target.x+(target.width-w)/2,y:target.y+(target.height-h)/2});
  result.link={...link,resolvedWidth:source.width,resolvedHeight:source.height};
  for(const k of Object.keys(target))delete target[k];Object.assign(target,result);return target;
}
export function resolveCopies(project,{detachMissing=false}={}){
  const byId=new Map(project.layers.map(l=>[l.id,l])),done=new Set(),visiting=new Set();let detached=0;
  const visit=(l,depth=0)=>{
    if(done.has(l.id))return;if(depth>32||visiting.has(l.id))throw new Error('Linked artwork contains a circular source reference.');
    const link=l.link;if(link){
      if(!['copy','offset'].includes(link.kind))throw new Error('Unknown linked artwork type.');
      const source=byId.get(link.sourceId);
      if(!source){if(!detachMissing)throw new Error('A linked artwork source is missing.');delete l.link;detached++;}
      else{visiting.add(l.id);visit(source,depth+1);if(link.kind==='copy'&&!(source.type==='text'&&link.textScale&&link.textScale!==1))applyLinked(source,l);visiting.delete(l.id);}
    }done.add(l.id);
  };
  project.layers.forEach(l=>visit(l));
  project.layers=project.layers.filter(l=>{if(!l.linkedHelper)return true;const owner=byId.get(l.linkedHelper.ownerId);if(!owner)return false;if(!owner.link)delete l.linkedHelper;return true;});return detached;
}
export function newLinked(source,id,kind='copy',params={}){
  const l=clone(source);for(const k of OMIT_KEYS)delete l[k];delete l.groupId;
  Object.assign(l,{id,name:source.name+(kind==='offset'?' · linked offset':' · linked copy'),x:source.x+(kind==='copy'?4:0),y:source.y+(kind==='copy'?4:0),visible:true,locked:false,background:false,
    link:{kind,sourceId:source.id,inheritColor:true,resolvedWidth:source.width,resolvedHeight:source.height,...(kind==='offset'?{params}: {})}});return l;
}
