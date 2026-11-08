// Node operations use document millimeters. Curves remain cubic and editable.
import {clone,point,reverseContour,splitSegment,smoothNode,autoSmoothNode,refreshAutoNodes} from './paths.mjs';
import {fitCubicChain} from './curve-fit.mjs';
export const nodeKey=(part,index)=>`${part}:${index}`;
export function selectedNodes(contours,selection){return [...new Set(selection)].map(key=>{const [part,index]=key.split(':').map(Number);return {key,part,index,node:contours[part]?.nodes[index]};}).filter(r=>r.node).sort((a,b)=>a.part-b.part||a.index-b.index);}
export function allNodeKeys(contours,part=null){return contours.flatMap((c,p)=>part===null||part===p?c.nodes.map((_,i)=>nodeKey(p,i)):[]);}
export function nodeBox(contours,selection){const nodes=selectedNodes(contours,selection).map(r=>r.node);if(!nodes.length)return null;const xs=nodes.map(n=>n.x),ys=nodes.map(n=>n.y),x=Math.min(...xs),y=Math.min(...ys),width=Math.max(...xs)-x,height=Math.max(...ys)-y;return{x,y,width,height,cx:x+width/2,cy:y+height/2};}
export function boxNodes(contours,a,b){return allNodeKeys(contours).filter(key=>{const [p,i]=key.split(':').map(Number),n=contours[p].nodes[i];return n.x>=Math.min(a.x,b.x)&&n.x<=Math.max(a.x,b.x)&&n.y>=Math.min(a.y,b.y)&&n.y<=Math.max(a.y,b.y);});}
export function transformNodes(contours,selection,{dx=0,dy=0,rotation=0,sx=1,sy=1}={}){
  if(![dx,dy,rotation,sx,sy].every(Number.isFinite))throw new Error('Enter finite node transform values.');
  const box=nodeBox(contours,selection);if(!box)return;const a=rotation*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
  const transform=([x,y])=>{x=(x-box.cx)*sx;y=(y-box.cy)*sy;return[box.cx+x*c-y*s+dx,box.cy+x*s+y*c+dy];};
  for(const {node:n}of selectedNodes(contours,selection)){[n.x,n.y]=transform([n.x,n.y]);n.in=transform(n.in);n.out=transform(n.out);}
  refreshAutoNodes(contours,selection,true);
}
export function alignNodes(contours,selection,axis,distribute=false){
  const nodes=selectedNodes(contours,selection).map(r=>r.node).sort((a,b)=>a[axis]-b[axis]);if(nodes.length<2)return;
  const low=nodes[0][axis],high=nodes.at(-1)[axis],k=axis==='x'?0:1;
  nodes.forEach((n,i)=>{const target=distribute?low+(high-low)*i/(nodes.length-1):(low+high)/2,delta=target-n[axis];n[axis]=target;n.in[k]+=delta;n.out[k]+=delta;});
  refreshAutoNodes(contours,selection);
}
export function shapeNodes(contours,selection,kind){
  for(const {part,index,node:n}of selectedNodes(contours,selection)){
    if(kind==='corner')n.mode='corner';
    else if(kind==='retract'){n.in=[n.x,n.y];n.out=[n.x,n.y];n.mode='corner';}
    else if(kind==='auto'){n.mode='auto';autoSmoothNode(contours[part],index);}
    else if(kind==='smooth'){
      const before=Math.hypot(n.x-n.in[0],n.y-n.in[1]),after=Math.hypot(n.out[0]-n.x,n.out[1]-n.y),dx=n.out[0]-n.in[0],dy=n.out[1]-n.in[1],length=Math.hypot(dx,dy);
      if(length<1e-10)smoothNode(contours[part],index);
      else{n.in=[n.x-dx/length*before,n.y-dy/length*before];n.out=[n.x+dx/length*after,n.y+dy/length*after];}
      n.mode='smooth';
    }
    else if(kind==='symmetric'){
      let vx=n.out[0]-n.in[0],vy=n.out[1]-n.in[1],length=Math.hypot(vx,vy);
      if(length<1e-9){smoothNode(contours[part],index);vx=n.out[0]-n.in[0];vy=n.out[1]-n.in[1];length=Math.hypot(vx,vy)||1;}
      const size=(Math.hypot(n.in[0]-n.x,n.in[1]-n.y)+Math.hypot(n.out[0]-n.x,n.out[1]-n.y))/2;
      n.in=[n.x-vx/length*size,n.y-vy/length*size];n.out=[n.x+vx/length*size,n.y+vy/length*size];
      n.mode='symmetric';
    }
  }
}
export function selectedSegments(contours,selection){
  const keys=new Set(selection),refs=selectedNodes(contours,selection),segments=[];
  if(refs.length===1){const r=refs[0],c=contours[r.part],i=r.index<c.nodes.length-1||c.closed?r.index:r.index-1;if(i>=0)segments.push([r.part,i]);return segments;}
  for(const r of refs){const c=contours[r.part],next=(r.index+1)%c.nodes.length;if((c.closed||next!==0)&&keys.has(nodeKey(r.part,next)))segments.push([r.part,r.index]);}return segments;
}
export function shapeSegments(contours,selection,kind){
  const segments=selectedSegments(contours,selection);if(!segments.length)throw new Error('Select both ends of a segment, or select one node.');
  for(const [p,i]of segments){const ns=contours[p].nodes,a=ns[i],b=ns[(i+1)%ns.length];
    if(kind==='line'){a.out=[a.x,a.y];b.in=[b.x,b.y];}
    else{a.out=[a.x+(b.x-a.x)/3,a.y+(b.y-a.y)/3];b.in=[b.x-(b.x-a.x)/3,b.y-(b.y-a.y)/3];}
    a.mode=b.mode='corner';
  }
}
export function insertMidpoints(contours,selection){
  const segments=selectedSegments(contours,selection);if(!segments.length)throw new Error('Select a segment’s endpoints or one node.');
  const inserted=new Set();for(const [p,i]of segments.sort((a,b)=>b[0]-a[0]||b[1]-a[1])){splitSegment(contours[p],i);inserted.add(contours[p].nodes[i+1]);}
  return allNodeKeys(contours).filter(key=>{const[p,i]=key.split(':').map(Number);return inserted.has(contours[p].nodes[i]);});
}
export function deleteNodes(contours,selection,mode='handles',report=null){
  if(!['handles','preserve','straight'].includes(mode))throw new Error('Choose a node deletion method.');
  let deviation=0,exact=true,joined=0,trimmed=false,droppedSubpaths=0;const keys=new Set(selection),result=[];
  contours.forEach((source,p)=>{const c=clone(source),ns=c.nodes,keep=ns.map((_,i)=>i).filter(i=>!keys.has(nodeKey(p,i)));
    if(keep.length<2){droppedSubpaths++;return;}if(!c.closed&&(keep[0]!==0||keep.at(-1)!==ns.length-1))trimmed=true;
    for(let j=0;j<keep.length-(c.closed?0:1);j++){
      const start=keep[j],end=keep[(j+1)%keep.length],chain=[ns[start]];let i=(start+1)%ns.length;
      while(i!==end){chain.push(ns[i]);i=(i+1)%ns.length;}chain.push(ns[end]);if(chain.length===2)continue;joined++;if(mode==='handles')continue;
      const a=ns[start],b=ns[end];
      if(mode==='preserve'){const fit=fitCubicChain(chain);a.out=fit.out;b.in=fit.in;deviation=Math.max(deviation,fit.error);exact&&=fit.exact;for(const n of [a,b])if(['auto','symmetric'].includes(n.mode))n.mode='smooth';}
      else{a.out=[a.x,a.y];b.in=[b.x,b.y];a.mode=b.mode='corner';}
    }
    c.nodes=keep.map(i=>ns[i]);result.push(c);
  });
  if(!result.length)throw new Error('Keep at least two nodes in one subpath, or cancel and remove the layer.');if(report)Object.assign(report,{deviation,exact,joined,trimmed,droppedSubpaths,removed:contours.reduce((n,c)=>n+c.nodes.length,0)-result.reduce((n,c)=>n+c.nodes.length,0)});return result;
}
export function breakNodes(contours,selection){
  const keys=new Set(selection);let changed=false;const result=[];
  contours.forEach((contour,p)=>{
    const c=clone(contour),ns=c.nodes,indices=ns.map((_,i)=>i).filter(i=>keys.has(nodeKey(p,i))&&(c.closed||i>0&&i<ns.length-1));
    if(!indices.length){result.push(c);return;}changed=true;
    if(c.closed){for(let j=0;j<indices.length;j++){const start=indices[j],end=indices[(j+1)%indices.length],nodes=[clone(ns[start])];let i=(start+1)%ns.length;while(i!==end){nodes.push(clone(ns[i]));i=(i+1)%ns.length;}nodes.push(clone(ns[end]));result.push({...c,closed:false,nodes});}}
    else{let start=0;for(const end of [...indices,ns.length-1]){result.push({...c,closed:false,nodes:clone(ns.slice(start,end+1))});start=end;}}
  });
  if(!changed)throw new Error('Select an interior node, or a node on a closed subpath.');return result;
}
export function deleteSegments(contours,selection){
  const segments=selectedSegments(contours,selection);if(!segments.length)throw new Error('Select a segment’s endpoints or one node.');
  const remove=new Set(segments.map(([p,i])=>nodeKey(p,i))),result=[];
  contours.forEach((c,p)=>{const ns=c.nodes,cuts=segments.filter(s=>s[0]===p).map(s=>s[1]);if(!cuts.length){result.push(clone(c));return;}
    let chain=[];const start=c.closed?(cuts[0]+1)%ns.length:0,count=ns.length;
    for(let step=0;step<count;step++){const i=(start+step)%ns.length;chain.push(clone(ns[i]));if(remove.has(nodeKey(p,i))||step===count-1){if(chain.length>=2)result.push({...c,closed:false,nodes:chain});chain=[];}}
  });if(!result.length)throw new Error('This would remove every segment. Remove the layer instead.');return result;
}
export function joinEnds(contours,selection,merge=false){
  const refs=selectedNodes(contours,selection);if(refs.length!==2)throw new Error('Select exactly two open endpoints to join.');
  for(const r of refs){const c=contours[r.part];if(c.closed||![0,c.nodes.length-1].includes(r.index))throw new Error('Join needs two endpoints on open subpaths.');}
  const result=clone(contours),[a,b]=refs;
  const mergeNode=(left,right)=>{const x=(left.x+right.x)/2,y=(left.y+right.y)/2;return{x,y,in:[left.in[0]+x-left.x,left.in[1]+y-left.y],out:[right.out[0]+x-right.x,right.out[1]+y-right.y]};};
  if(a.part===b.part){const c=result[a.part],ns=c.nodes;if(merge){if(ns.length<3)throw new Error('Keep at least two nodes after joining.');c.nodes=[mergeNode(ns.at(-1),ns[0]),...ns.slice(1,-1)];}else{ns.at(-1).out=[ns.at(-1).x,ns.at(-1).y];ns[0].in=[ns[0].x,ns[0].y];}c.closed=true;return{contours:result,selection:[nodeKey(a.part,0)]};}
  const left=result[a.part],right=result[b.part];if(a.index===0)reverseContour(left);if(b.index!==0)reverseContour(right);
  const index=left.nodes.length-1;
  if(merge)left.nodes=[...left.nodes.slice(0,-1),mergeNode(left.nodes.at(-1),right.nodes[0]),...right.nodes.slice(1)];
  else{left.nodes.at(-1).out=[left.nodes.at(-1).x,left.nodes.at(-1).y];right.nodes[0].in=[right.nodes[0].x,right.nodes[0].y];left.nodes.push(...right.nodes);}
  result.splice(b.part,1);return{contours:result,selection:[nodeKey(a.part,index),...(!merge?[nodeKey(a.part,index+1)]:[])]};
}
export function firstNode(contours,selection){const refs=selectedNodes(contours,selection);if(refs.length!==1||!contours[refs[0].part].closed)throw new Error('Select one node on a closed subpath.');const {part,index}=refs[0],c=contours[part];c.nodes=[...c.nodes.slice(index),...c.nodes.slice(0,index)];return[nodeKey(part,0)];}
