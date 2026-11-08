import {pathBounds} from './paths.mjs';

export function spotBounds(params,spot){
  const w=params.width,h=params.height;
  const b=pathBounds(spot.contours.map(c=>({...c,nodes:c.nodes.map(n=>({x:n.x*w,y:n.y*h,in:[n.in[0]*w,n.in[1]*h],out:[n.out[0]*w,n.out[1]*h]}))})));
  return {...b,cx:b.x+b.w/2,cy:b.y+b.h/2};
}
export function transformSpot(params,spot,{dx=0,dy=0,sx=1,sy=1,angle=0}={}){
  const b=spotBounds(params,spot),w=params.width,h=params.height,a=angle*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
  const map=q=>{const x=(q[0]*w-b.cx)*sx,y=(q[1]*h-b.cy)*sy;return[(b.cx+dx+x*c-y*s)/w,(b.cy+dy+x*s+y*c)/h];};
  for(const contour of spot.contours)for(const n of contour.nodes){[n.x,n.y]=map([n.x,n.y]);n.in=map(n.in);n.out=map(n.out);}
  spot.rotation=((spot.rotation||0)+angle+540)%360-180;
}
export function mushroomFrame(item,placement){
  const p=item.params,scale=placement.scale??item.scale,w=p.width*scale,h=p.height*scale;
  const root=p.stemRails?[0,1].map(axis=>p.stemRails.reduce((sum,r)=>sum+r[3][axis],0)/2):[.5+(p.bend||0),1];
  const pivot=p.capPivot||[.5,p.dome*.56],tilt=(p.capTilt||0)*Math.PI/180,ct=Math.cos(tilt),st=Math.sin(tilt);
  const a=(placement.rotation??item.angle)*Math.PI/180,c=Math.cos(a),s=Math.sin(a),flip=item.flipX?-1:1,anchor=placement.anchor;
  return {
    toWorld(q){let x=(q[0]-pivot[0])*w,y=(q[1]-pivot[1])*h;[x,y]=[x*ct-y*st+pivot[0]*w,x*st+y*ct+pivot[1]*h];x=(x-root[0]*w)*flip;y-=root[1]*h;return[anchor[0]+x*c-y*s,anchor[1]+x*s+y*c];},
    fromWorld(q){const dx=q[0]-anchor[0],dy=q[1]-anchor[1],x=(dx*c+dy*s)*flip+root[0]*w-pivot[0]*w,y=-dx*s+dy*c+root[1]*h-pivot[1]*h;return[pivot[0]+(x*ct+y*st)/w,pivot[1]+(-x*st+y*ct)/h];}
  };
}
