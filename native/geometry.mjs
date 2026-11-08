// Geometry shared by the touch controls and the invariant tests. Units are mm.
export function resizedDimensions(layer,key,value,max=100){
  if(!['width','height'].includes(key)||!Number.isFinite(value)||value<.2||value>max)throw new Error(`Both dimensions must be between 0.2 and ${max} mm.`);
  const other=key==='width'?'height':'width',result={[key]:value,[other]:layer[other]};
  if(layer.type==='text'||layer.aspectLock!==false){
    if(!Number.isFinite(layer[key])||layer[key]<=0)throw new Error('The artwork has an invalid size.');
    result[other]=layer[other]*value/layer[key];
    if(!Number.isFinite(result[other])||result[other]<.2-1e-9||result[other]>max+1e-9)throw new Error(`Both dimensions must be between 0.2 and ${max} mm.`);
    result[other]=Math.max(.2,Math.min(max,result[other]));
  }
  return result;
}

export function objectBounds(l) {
  const a=(l.rotation||0)*Math.PI/180,c=Math.abs(Math.cos(a)),s=Math.abs(Math.sin(a));
  const w=l.width*c+l.height*s,h=l.width*s+l.height*c;
  return {x:l.x+l.width/2-w/2,y:l.y+l.height/2-h/2,w,h};
}
export function groupBounds(list) {
  if(!list.length)return null;
  const bs=list.map(objectBounds),x=Math.min(...bs.map(b=>b.x)),y=Math.min(...bs.map(b=>b.y));
  return {x,y,w:Math.max(...bs.map(b=>b.x+b.w))-x,h:Math.max(...bs.map(b=>b.y+b.h))-y};
}
export function units(list) {
  const map=new Map();
  for(const l of list){const key=l.groupId||l.id;if(!map.has(key))map.set(key,[]);map.get(key).push(l);}
  return [...map.values()];
}
export function move(list,dx,dy){for(const l of list){l.x+=dx;l.y+=dy;}}
// hoop: false (align to the selection), true (the 100 mm hoop) or a {w,h} hoop size.
export function alignLayers(list,kind,hoop=false,hoopSize={w:100,h:100}) {
  const area=typeof hoop==="object"&&hoop?hoop:hoopSize;
  const sets=units(list),b=hoop||sets.length===1?{x:0,y:0,w:area.w,h:area.h}:groupBounds(list);
  const horizontal=['left','center','right'].includes(kind),axis=horizontal?'x':'y',size=horizontal?'w':'h';
  const factor={left:0,center:.5,right:1,top:0,middle:.5,bottom:1}[kind];
  for(const set of sets){const box=groupBounds(set),delta=b[axis]+(b[size]-box[size])*factor-box[axis];move(set,horizontal?delta:0,horizontal?0:delta);}
}
export function spaceLayers(list,axis,gap=null) {
  const size=axis==='x'?'w':'h',sets=units(list).sort((a,b)=>groupBounds(a)[axis]-groupBounds(b)[axis]);
  if(sets.length<2)return;
  const first=groupBounds(sets[0]),last=groupBounds(sets.at(-1));
  if(gap===null)gap=(last[axis]+last[size]-first[axis]-sets.reduce((v,s)=>v+groupBounds(s)[size],0))/(sets.length-1);
  let at=first[axis];
  for(const set of sets){const b=groupBounds(set),delta=at-b[axis];move(set,axis==='x'?delta:0,axis==='y'?delta:0);at+=b[size]+gap;}
}
export function rotateLayers(list,degrees) {
  const b=groupBounds(list),cx=b.x+b.w/2,cy=b.y+b.h/2,a=degrees*Math.PI/180;
  for(const l of list){const dx=l.x+l.width/2-cx,dy=l.y+l.height/2-cy;l.x=cx+dx*Math.cos(a)-dy*Math.sin(a)-l.width/2;l.y=cy+dx*Math.sin(a)+dy*Math.cos(a)-l.height/2;l.rotation=(((l.rotation||0)+degrees+180)%360+360)%360-180;}
}
export function mirrorLayers(list,axis) {
  const b=groupBounds(list);
  for(const l of list){if(axis==='x'){l.x=2*b.x+b.w-l.x-l.width;l.flipX=!l.flipX;}else{l.y=2*b.y+b.h-l.y-l.height;l.flipY=!l.flipY;}l.rotation=-(l.rotation||0);}
}
export function fitBackground(list,padding,hoop={w:100,h:100}) {
  const artwork=list.filter(l=>!l.background&&l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork')).map(l=>{
    if(!['rectangle','ellipse','path'].includes(l.type))return l;
    const baseStroke=l.merrow&&l.stitch==='original'?l.merrow.width:l.stitch==='fill'?(l.borderEnabled?(l.borderStitch==='zigzag'?(l.borderWidth||1.5):.3):0):l.stitch==='zigzag'?(l.strokeWidth||1.5):.3;
    const stroke=Math.max(baseStroke,l.feather&&l.feather.enabled!==false&&['fill','satin','original'].includes(l.stitch)?2*(l.feather.raggedness||0):0);
    return {...l,x:l.x-stroke/2,y:l.y-stroke/2,width:l.width+stroke,height:l.height+stroke};
  });
  const b=groupBounds(artwork);
  if(!b)throw new Error('Add a visible design layer before fitting a background.');
  const result={x:b.x-padding,y:b.y-padding,width:b.w+2*padding,height:b.h+2*padding,rotation:0};
  if(result.x<0||result.y<0||result.x+result.width>hoop.w||result.y+result.height>hoop.h)throw new Error('That padding extends beyond the hoop. Reduce padding or center/resize the design.');
  return result;
}
