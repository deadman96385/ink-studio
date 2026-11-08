// Positions count decoded machine records; stitch numbers count penetrations.
export const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
export function indexPlan(plan){
  const types=plan.commandTypes||{stitch:0,jump:1,trim:2,stop:3,end:4,color:5};
  const commands=plan.commands||[];
  const segments=new Uint32Array(commands.length+1),stitches=new Uint32Array(commands.length+1),threads=new Uint32Array(commands.length+1),needle=[0],events={all:[],jump:[],trim:[],stop:[],color:[]};
  const names=Object.fromEntries(Object.entries(types).map(([k,v])=>[v,k]));
  commands.forEach((c,i)=>{
    const p=i+1,kind=names[c[2]]||'other';
    segments[p]=segments[i]+(kind==='stitch'&&i>0?1:0);stitches[p]=stitches[i]+(kind==='stitch'?1:0);threads[p]=threads[i]+(kind==='color'?1:0);
    if(kind==='stitch')needle.push(p);
    if(events[kind]){events[kind].push(p);events.all.push(p);}
  });
  const pauses=events.all.filter(p=>names[commands[p-1][2]]!=='jump');
  return {commands,types,names,segments,stitches,threads,needle,events,pauses,length:commands.length};
}
export function nextPosition(positions,current,direction,limit){
  let lo=0,hi=positions.length;
  while(lo<hi){const m=(lo+hi)>>>1;if(positions[m]<(direction>0?current+1:current))lo=m+1;else hi=m;}
  return direction>0?(positions[lo]??limit):(positions[lo-1]??0);
}
export function advance(model,position,amount,direction,pauseCommands=false){
  let next=clamp(position+amount*direction,0,model.length),paused=false;
  if(pauseCommands){const edge=nextPosition(model.pauses,Math.round(position),direction,direction>0?Infinity:-Infinity);if(direction>0?edge<=next:edge>=next){next=edge;paused=true;}}
  return {position:next,paused:paused||next===0||next===model.length};
}
export function selectionProject(project,ids){
  const chosen=new Set(ids),art=project.layers.filter(l=>chosen.has(l.id)&&l.visible!==false&&l.type!=='image'&&(!l.role||l.role==='artwork'));
  if(!art.length)throw new Error('Select visible artwork to simulate.');
  const targets=new Set(art.map(l=>l.id)),result=structuredClone(project);result.name=(project.name||'Design')+' · selection';
  for(const layer of result.layers)if(!targets.has(layer.id)&&!targets.has(layer.helperTarget))layer.visible=false;
  return result;
}
export function fitView(bounds,width,height){
  const [x0,y0,x1,y1]=bounds;return{x:(x0+x1)/2,y:(y0+y1)/2,scale:Math.min((width-40)/Math.max(4,x1-x0),(height-40)/Math.max(4,y1-y0))};
}
export function worldPoint(view,point,width,height){return [view.x+(point[0]-width/2)/view.scale,view.y+(point[1]-height/2)/view.scale];}
export function zoomView(view,factor,anchor,width,height){
  const p=worldPoint(view,anchor,width,height),scale=clamp(view.scale*factor,.5,200);
  return{x:p[0]-(anchor[0]-width/2)/scale,y:p[1]-(anchor[1]-height/2)/scale,scale};
}
export function viewProjection(from,to,width,height){
  const scale=to.scale/from.scale;return {scale,x:width/2-to.x*to.scale-scale*(width/2-from.x*from.scale),y:height/2-to.y*to.scale-scale*(height/2-from.y*from.scale)};
}
export function inspectStitch(model,point,radius){
  let best=radius*radius,position=null;
  for(const p of model.needle.slice(1)){const c=model.commands[p-1],d=(c[0]-point[0])**2+(c[1]-point[1])**2;if(d<=best){best=d;position=p;}}
  return position;
}
