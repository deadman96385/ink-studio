// Cubic paths stay editable. All stored coordinates are relative to layer size.
export const clone=v=>structuredClone(v);
export const point=(x,y)=>({x,y,in:[x,y],out:[x,y]});
const lerp=(a,b,t)=>a.map((v,i)=>v+(b[i]-v)*t);
const xy=n=>[n.x,n.y];
export function pathD(contours,w=1,h=1){return contours.map(c=>{
  const ns=c.nodes;if(!ns.length)return '';let d=`M${ns[0].x*w} ${ns[0].y*h}`;
  const pairs=ns.slice(1).map((n,i)=>[ns[i],n]);if(c.closed&&ns.length>1)pairs.push([ns.at(-1),ns[0]]);
  for(const[a,b]of pairs)d+=` C${a.out[0]*w} ${a.out[1]*h} ${b.in[0]*w} ${b.in[1]*h} ${b.x*w} ${b.y*h}`;
  return d+(c.closed?' Z':'');
}).join(' ');}
export function cubic(a,b,t){const p=lerp(xy(a),a.out,t),q=lerp(a.out,b.in,t),r=lerp(b.in,xy(b),t);return lerp(lerp(p,q,t),lerp(q,r,t),t);}
function extrema(p0,p1,p2,p3){
  const a=-p0+3*p1-3*p2+p3,b=2*(p0-2*p1+p2),c=p1-p0;
  if(Math.abs(a)<1e-12)return Math.abs(b)<1e-12?[]:[-c/b].filter(t=>t>0&&t<1);
  const d=b*b-4*a*c;if(d<0)return [];return[(-b+Math.sqrt(d))/(2*a),(-b-Math.sqrt(d))/(2*a)].filter(t=>t>0&&t<1);
}
export function pathBounds(contours){
  const pts=[];
  for(const c of contours){for(const n of c.nodes)pts.push(xy(n));const ns=c.nodes,pairs=ns.slice(1).map((n,i)=>[ns[i],n]);if(c.closed&&ns.length>1)pairs.push([ns.at(-1),ns[0]]);
    for(const[a,b]of pairs)for(let axis=0;axis<2;axis++)for(const t of extrema(xy(a)[axis],a.out[axis],b.in[axis],xy(b)[axis]))pts.push(cubic(a,b,t));
  }
  if(!pts.length)return {x:0,y:0,w:100,h:100};const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),x=Math.min(...xs),y=Math.min(...ys);return{x,y,w:Math.max(.2,Math.max(...xs)-x),h:Math.max(.2,Math.max(...ys)-y)};
}
export function worldContours(layer){
  let contours=layer.contours||[{closed:layer.closed||layer.stitch==='fill',nodes:(layer.points||[]).map(([x,y])=>point(x,y))}];
  const a=(layer.rotation||0)*Math.PI/180,c=Math.cos(a),s=Math.sin(a),w=layer.width,h=layer.height;
  const transform=p=>{const x=(layer.flipX?1-p[0]:p[0])*w-w/2,y=(layer.flipY?1-p[1]:p[1])*h-h/2;return[layer.x+w/2+x*c-y*s,layer.y+h/2+x*s+y*c];};
  return contours.map(p=>({...p,nodes:p.nodes.map(n=>{const [x,y]=transform(xy(n));return{...n,x,y,in:transform(n.in),out:transform(n.out)};})}));
}
export function packContours(contours,base){
  const b=pathBounds(contours),normalize=p=>[(p[0]-b.x)/b.w,(p[1]-b.y)/b.h];
  const result={...base,type:'path',x:b.x,y:b.y,width:b.w,height:b.h,rotation:0,flipX:false,flipY:false,
    contours:contours.map(c=>({...c,nodes:c.nodes.map(n=>{const[x,y]=normalize(xy(n));return{...n,x,y,in:normalize(n.in),out:normalize(n.out)};})}))};
  if(base.streamlines){
    result.streamlines=structuredClone(base.streamlines);
    for(const guide of result.streamlines.guides){const world=worldContours({...base,contours:[{closed:false,nodes:guide.points.map(p=>point(...p))}]})[0];guide.points=world.nodes.map(n=>[(n.x-b.x)/b.w,(n.y-b.y)/b.h]);}
    delete result.streamlinePreview;
  }
  delete result.points;return result;
}
export function splitSegment(contour,index,t=.5){
  const ns=contour.nodes,j=(index+1)%ns.length;if(!contour.closed&&j===0)return false;
  const a=ns[index],b=ns[j],p=lerp(xy(a),a.out,t),q=lerp(a.out,b.in,t),r=lerp(b.in,xy(b),t),u=lerp(p,q,t),v=lerp(q,r,t),m=lerp(u,v,t);
  a.out=p;b.in=r;for(const n of [a,b])if(['auto','symmetric'].includes(n.mode))n.mode='smooth';
  ns.splice(index+1,0,{x:m[0],y:m[1],in:u,out:v,mode:'smooth'});return true;
}
export function reverseContour(c){c.nodes.reverse();for(const n of c.nodes)[n.in,n.out]=[n.out,n.in];}
export function smoothNode(c,index){
  const ns=c.nodes,n=ns[index],prev=ns[index-1]||(c.closed?ns.at(-1):n),next=ns[index+1]||(c.closed?ns[0]:n);
  const dx=next.x-prev.x,dy=next.y-prev.y,d=Math.hypot(dx,dy)||1;
  const before=Math.hypot(n.x-prev.x,n.y-prev.y)/3,after=Math.hypot(next.x-n.x,next.y-n.y)/3;
  n.in=[n.x-dx/d*before,n.y-dy/d*before];n.out=[n.x+dx/d*after,n.y+dy/d*after];
}
export const nodeMode=n=>['corner','smooth','symmetric','auto'].includes(n.mode)?n.mode:'corner';
export function autoSmoothNode(c,index){
  const ns=c.nodes,n=ns[index],prev=ns[index-1]||(c.closed?ns.at(-1):null),next=ns[index+1]||(c.closed?ns[0]:null),
    d0=prev?Math.hypot(n.x-prev.x,n.y-prev.y):0,d1=next?Math.hypot(next.x-n.x,next.y-n.y):0;
  let vx=(d0?(n.x-prev.x)/d0:0)+(d1?(next.x-n.x)/d1:0),vy=(d0?(n.y-prev.y)/d0:0)+(d1?(next.y-n.y)/d1:0),length=Math.hypot(vx,vy);
  if(length<1e-10){n.in=[n.x,n.y];n.out=[n.x,n.y];return;}vx/=length;vy/=length;
  n.in=[n.x-vx*d0/3,n.y-vy*d0/3];n.out=[n.x+vx*d1/3,n.y+vy*d1/3];
}
export function refreshAutoNodes(contours,changed=null,preserveFullySelected=false){
  const keys=changed===null?null:new Set(changed);
  contours.forEach((c,p)=>c.nodes.forEach((n,i)=>{if(nodeMode(n)!=='auto')return;
    const neighbors=[i,...(i>0?[i-1]:c.closed?[c.nodes.length-1]:[]),...(i<c.nodes.length-1?[i+1]:c.closed?[0]:[])].map(j=>`${p}:${j}`);
    if(keys&&(!neighbors.some(k=>keys.has(k))||preserveFullySelected&&neighbors.every(k=>keys.has(k))))return;
    autoSmoothNode(c,i);
  }));
}
export function moveNodeHandle(contours,part,index,handle,position,align=false){
  const n=contours[part].nodes[index],other=handle==='in'?'out':'in',kind=nodeMode(n),oldLength=Math.hypot(n[other][0]-n.x,n[other][1]-n.y);
  n[handle]=[...position];const dx=position[0]-n.x,dy=position[1]-n.y,length=Math.hypot(dx,dy);
  if(kind==='auto')n.mode='smooth';
  if(kind!=='corner'||align){
    if(kind==='corner')n.mode='smooth';
    const size=kind==='symmetric'?length:oldLength;
    if(length>1e-10)n[other]=[n.x-dx/length*size,n.y-dy/length*size];
    else if(kind==='symmetric')n[other]=[n.x,n.y];
  }
}
export function contourSampler(c){
  const samples=[],ns=c.nodes,pairs=ns.slice(1).map((n,i)=>[ns[i],n]);if(c.closed)pairs.push([ns.at(-1),ns[0]]);
  if(!pairs.length)return ()=>ns.length?xy(ns[0]):[0,0];let total=0,prev=xy(ns[0]);
  for(let i=0;i<pairs.length;i++)for(let j=1;j<=40;j++){const p=cubic(...pairs[i],j/40);total+=Math.hypot(p[0]-prev[0],p[1]-prev[1]);samples.push({length:total,i,t:j/40});prev=p;}
  return fraction=>{
    const target=Math.max(0,Math.min(1,fraction))*total;let last=0;
    for(const s of samples){if(s.length>=target){const t=s.t-1/40+(target-last)/(s.length-last||1)/40;return cubic(...pairs[s.i],t);}last=s.length;}
    return xy(ns.at(-1));
  };
}
export function pointAlong(c,fraction){return contourSampler(c)(fraction);}
export function addRung(contours,fraction){
  if(contours.length<2)return;const a=pointAlong(contours[0],fraction),b=pointAlong(contours[1],fraction),dx=b[0]-a[0],dy=b[1]-a[1];
  contours.push({closed:false,nodes:[point(a[0]-.15*dx,a[1]-.15*dy),point(b[0]+.15*dx,b[1]+.15*dy)]});
}
export function satinArea(contours,w=1,h=1){
  if(contours.length<2)return '';const pts=[],left=contourSampler(contours[0]),right=contourSampler(contours[1]);for(let i=0;i<=40;i++)pts.push(left(i/40));for(let i=40;i>=0;i--)pts.push(right(i/40));return pts.map((p,i)=>`${i?'L':'M'}${p[0]*w} ${p[1]*h}`).join(' ')+' Z';
}
