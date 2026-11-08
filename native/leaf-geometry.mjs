// The same normalized branch frame is used by leaf controls and canvas drags.
export function branchFrame(item,placement){
  const p=item.params,scale=placement.scale??item.scale,w=p.width*scale,h=p.height*scale;
  const root=p.stemCurve?.[0]||[.5,1],a=(placement.rotation??item.angle)*Math.PI/180,c=Math.cos(a),s=Math.sin(a),flip=item.flipX?-1:1;
  const anchor=placement.anchor;
  return {
    toWorld(q){const x=(q[0]-root[0])*w*flip,y=(q[1]-root[1])*h;return[anchor[0]+x*c-y*s,anchor[1]+x*s+y*c];},
    fromWorld(q){const x=q[0]-anchor[0],y=q[1]-anchor[1];return[root[0]+(x*c+y*s)*flip/w,root[1]+(-x*s+y*c)/h];}
  };
}
export function bladeCentre(params,leaf){
  const w=params.width,h=params.height,a=[leaf.base[0]*w,leaf.base[1]*h],b=[leaf.tip[0]*w,leaf.tip[1]*h];
  const dx=b[0]-a[0],dy=b[1]-a[1],length=Math.hypot(dx,dy)||1,nx=-dy/length,ny=dx/length,bend=leaf.bend*length;
  return[a,[a[0]+dx*.25+nx*bend*.8,a[1]+dy*.25+ny*bend*.8],[a[0]+dx*.74+nx*bend,a[1]+dy*.74+ny*bend],b].map(([x,y])=>[x/w,y/h]);
}
