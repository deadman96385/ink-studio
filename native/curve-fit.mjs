// Join cubic segments while keeping endpoints and endpoint tangent directions.
// Exact subdivisions are recovered algebraically; other chains use a fitted cubic.
import {cubic,clone} from './paths.mjs';
const xy=n=>[n.x,n.y],sub=(a,b)=>[a[0]-b[0],a[1]-b[1]],add=(a,b)=>[a[0]+b[0],a[1]+b[1]],mul=(p,s)=>p.map(v=>v*s),dot=(a,b)=>a[0]*b[0]+a[1]*b[1],len=p=>Math.hypot(...p),dist=(a,b)=>len(sub(a,b));
const unit=v=>len(v)>1e-10?mul(v,1/len(v)):[0,0];
function exactJoin(a,m,b){
  const incoming=sub(xy(m),m.in),outgoing=sub(m.out,xy(m)),total=len(incoming)+len(outgoing);
  if(total<1e-10)return null;
  const t=len(incoming)/total;if(t<1e-7||t>1-1e-7)return null;
  const left={...clone(a),out:add(xy(a),mul(sub(a.out,xy(a)),1/t))},right={...clone(b),in:add(xy(b),mul(sub(b.in,xy(b)),1/(1-t)))};
  const tolerance=1e-8*Math.max(1,dist(xy(a),xy(b)),total);
  for(let i=0;i<=12;i++){const u=i/12;
    if(dist(cubic(a,m,u),cubic(left,right,u*t))>tolerance||dist(cubic(m,b,u),cubic(left,right,t+(1-t)*u))>tolerance)return null;
  }
  return [left,right];
}
function lineDistance(p,a,b){const v=sub(b,a),d=dot(v,v),t=d?Math.max(0,Math.min(1,dot(sub(p,a),v)/d)):0;return dist(p,add(a,mul(v,t)));}
function flatten(a,b,tolerance=.005){
  const output=[xy(a)];
  function split(p0,p1,p2,p3,depth){
    if(depth===10||Math.max(lineDistance(p1,p0,p3),lineDistance(p2,p0,p3))<=tolerance){output.push(p3);return;}
    const mid=(a,b)=>mul(add(a,b),.5),q0=mid(p0,p1),q1=mid(p1,p2),q2=mid(p2,p3),r0=mid(q0,q1),r1=mid(q1,q2),m=mid(r0,r1);
    split(p0,q0,r0,m,depth+1);split(m,r1,q2,p3,depth+1);
  }
  split(xy(a),a.out,b.in,xy(b),0);return output;
}
function resample(points,limit=512){
  const lengths=[0];for(let i=1;i<points.length;i++)lengths.push(lengths.at(-1)+dist(points[i-1],points[i]));
  const total=lengths.at(-1);if(total<1e-10)return{points:[points[0],points.at(-1)],parameters:[0,1],length:0};
  // Uniform arc samples prevent dense, very short source segments dominating the fit.
  const count=Math.min(limit,Math.max(32,points.length)),result=[];let j=1;
  for(let i=0;i<count;i++){const target=total*i/(count-1);while(j<points.length-1&&lengths[j]<target)j++;const t=(target-lengths[j-1])/(lengths[j]-lengths[j-1]||1);result.push(add(points[j-1],mul(sub(points[j],points[j-1]),t)));}
  return{points:result,parameters:result.map((_,i)=>i/(count-1)),length:total};
}
function solve(points,parameters,a,b,t0,t1,total){
  let aa=0,ab=0,bb=0,ra=0,rb=0;
  points.forEach((p,i)=>{const t=parameters[i],u=1-t,b0=u*u*u,b1=3*u*u*t,b2=3*u*t*t,b3=t*t*t,
    v0=mul(t0,b1),v1=mul(t1,b2),rhs=sub(p,add(mul(a,b0+b1),mul(b,b2+b3)));
    aa+=dot(v0,v0);ab+=dot(v0,v1);bb+=dot(v1,v1);ra+=dot(v0,rhs);rb+=dot(v1,rhs);
  });
  const det=aa*bb-ab*ab,candidates=[];
  if(Math.abs(det)>1e-14)candidates.push([(ra*bb-rb*ab)/det,(rb*aa-ra*ab)/det]);
  candidates.push([aa?ra/aa:0,0],[0,bb?rb/bb:0],[0,0]);
  const cost=([x,y])=>aa*x*x+2*ab*x*y+bb*y*y-2*ra*x-2*rb*y;
  const candidatesInRange=candidates.map(v=>v.map(n=>Math.max(0,Math.min(total*2,Number.isFinite(n)?n:0))));
  const [alpha,beta]=candidatesInRange.sort((x,y)=>cost(x)-cost(y))[0];return[add(a,mul(t0,alpha)),add(b,mul(t1,beta))];
}
function project(p,a,b,t){
  const p0=xy(a),p1=a.out,p2=b.in,p3=xy(b);
  for(let i=0;i<5;i++){const u=1-t,q=cubic(a,b,t),d=add(add(mul(sub(p1,p0),3*u*u),mul(sub(p2,p1),6*u*t)),mul(sub(p3,p2),3*t*t)),
    dd=add(mul(add(sub(p2,mul(p1,2)),p0),6*u),mul(add(sub(p3,mul(p2,2)),p1),6*t)),diff=sub(q,p),den=dot(d,d)+dot(diff,dd);
    if(Math.abs(den)<1e-12)break;t=Math.max(0,Math.min(1,t-dot(diff,d)/den));
  }return t;
}
function deviation(source,a,b){
  source=resample(source,2048).points;const fitted=flatten(a,b),points=resample(source,1024).points,reverse=resample(fitted,256).points;
  const directed=(from,to)=>Math.max(...from.map(p=>{let d=Infinity;for(let i=1;i<to.length;i++)d=Math.min(d,lineDistance(p,to[i-1],to[i]));return d;}));
  return Math.max(directed(points,fitted),directed(reverse,source));
}
export function fitCubicChain(nodes){
  if(nodes.length<2)throw new Error('A curve needs two endpoints.');
  let exact=[clone(nodes[0]),clone(nodes[1])];
  for(let i=2;i<nodes.length&&exact;i++)exact=exactJoin(exact[0],exact[1],nodes[i]);
  if(exact)return{out:exact[0].out,in:exact[1].in,error:0,exact:true};
  const source=nodes.slice(1).flatMap((n,i)=>flatten(nodes[i],n).slice(i?1:0)),sample=resample(source),a=clone(nodes[0]),b=clone(nodes.at(-1));
  const start=unit(len(sub(a.out,xy(a)))>1e-10?sub(a.out,xy(a)):sub(source.find(p=>dist(p,xy(a))>1e-8)||xy(b),xy(a))),
    end=unit(len(sub(b.in,xy(b)))>1e-10?sub(b.in,xy(b)):sub([...source].reverse().find(p=>dist(p,xy(b))>1e-8)||xy(a),xy(b)));
  let parameters=sample.parameters,best=null;
  for(let iteration=0;iteration<8;iteration++){
    [a.out,b.in]=solve(sample.points,parameters,xy(a),xy(b),start,end,sample.length);
    const error=sample.points.reduce((sum,p,i)=>sum+dist(p,cubic(a,b,parameters[i]))**2,0);
    if(!best||error<best.error)best={a:clone(a),b:clone(b),error};
    const next=sample.points.map((p,i)=>i===0?0:i===sample.points.length-1?1:project(p,a,b,parameters[i]));
    if(next.some((t,i)=>i&&t<next[i-1]))break;parameters=next;
  }
  return{out:best.a.out,in:best.b.in,error:deviation(source,best.a,best.b),exact:false};
}
