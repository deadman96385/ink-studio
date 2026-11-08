import {point,packContours,addRung} from './paths.mjs';
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export class PenGate{
  constructor(){this.pen=null;this.lastPen=-Infinity;}
  down(e,now){if(e.pointerType==='pen'){this.pen=e.pointerId;this.lastPen=now;return true;}return e.pointerType!=='touch'||(this.pen===null&&now-this.lastPen>350);}
  end(e,now){if(e.pointerId===this.pen){this.pen=null;this.lastPen=now;}}
  reset(){this.pen=null;this.lastPen=-Infinity;}
}
export function simplifyStroke(points,tolerance,widthRange=0){
  if(points.length<3)return points.slice();const keep=new Set([0,points.length-1]),stack=[[0,points.length-1]];
  while(stack.length){const[a,b]=stack.pop(),p=points[a],q=points[b],dx=q[0]-p[0],dy=q[1]-p[1],length=dx*dx+dy*dy;let far=tolerance,index=-1;
    for(let i=a+1;i<b;i++){const n=points[i],t=length?clamp(((n[0]-p[0])*dx+(n[1]-p[1])*dy)/length,0,1):(i-a)/(b-a),d=Math.max(Math.hypot(n[0]-p[0]-t*dx,n[1]-p[1]-t*dy),Math.abs(n[2]-(p[2]+t*(q[2]-p[2])))*widthRange/2);if(d>far){far=d;index=i;}}
    if(index>=0){keep.add(index);stack.push([a,index],[index,b]);}
  }return [...keep].sort((a,b)=>a-b).map(i=>points[i]);
}
function curve(nodes){for(let i=0;i<nodes.length;i++){const n=nodes[i],a=nodes[Math.max(0,i-1)],b=nodes[Math.min(nodes.length-1,i+1)],dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy)||1,previous=Math.hypot(n.x-a.x,n.y-a.y)/4,next=Math.hypot(n.x-b.x,n.y-b.y)/4;n.in=[n.x-dx/len*previous,n.y-dy/len*previous];n.out=[n.x+dx/len*next,n.y+dy/len*next];}return {closed:false,nodes};}
export function makeStroke(samples,settings,base){
  const clean=[];for(const p of samples)if(p.every(Number.isFinite)&&(!clean.length||Math.hypot(p[0]-clean.at(-1)[0],p[1]-clean.at(-1)[1])>.04))clean.push([p[0],p[1],clamp(p[2],0,1)]);
  if(clean.length<2)return null;
  let points=simplifyStroke(clean,settings.smoothing,settings.brush==='satin'?settings.maxWidth-settings.minWidth:0);
  if(points.length>500){const stride=Math.ceil(points.length/499),last=points.at(-1);points=points.filter((_,i)=>i%stride===0);if(points.at(-1)!==last)points.push(last);}
  let contours;
  if(settings.brush==='satin'){
    const rails=[[],[]];for(let i=0;i<points.length;i++){const p=points[i],a=points[Math.max(0,i-1)],b=points[Math.min(points.length-1,i+1)],dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy)||1,width=settings.minWidth+(settings.maxWidth-settings.minWidth)*p[2];
      for(let side=0;side<2;side++){const d=(side?1:-1)*width/2;rails[side].push(point(p[0]-dy/len*d,p[1]+dx/len*d));}}
    contours=rails.map(curve);for(const t of [.2,.5,.8])addRung(contours,t);
  }else contours=[curve(points.map(p=>point(p[0],p[1])))];
  return packContours(contours,{...base,name:settings.brush==='satin'?'Pencil satin':'Freehand curve',stitch:settings.brush==='satin'?'satin':'running',spacing:.4,satinCenter:true});
}
export function createPenControls(ctx){
  let settings={penOnly:false,brush:'running',minWidth:.8,maxWidth:4,smoothing:.2,keepDrawing:true};
  try{const p=JSON.parse(localStorage.getItem('inkstudio-pen-v1')||'{}');settings={...settings,...p};}catch{}
  settings.brush=settings.brush==='satin'?'satin':'running';for(const k of ['minWidth','maxWidth'])settings[k]=clamp(Number(settings[k])||1,.6,8);settings.maxWidth=Math.max(settings.minWidth,settings.maxWidth);settings.smoothing=clamp(Number(settings.smoothing)||.2,.05,1);
  const $=id=>document.getElementById(id),save=()=>{try{localStorage.setItem('inkstudio-pen-v1',JSON.stringify(settings));}catch{}};
  function render(host){host.innerHTML=`<h2>Draw with touch or Pencil.</h2><p>Make editable curves or pressure-shaped satin columns. Choose Select to edit finished strokes.</p><label class="check"><input id="penOnly" type="checkbox" ${settings.penOnly?'checked':''}>Pencil draws; fingers move the view</label><label>Draw stitch<select id="penBrush"><option value="running" ${settings.brush==='running'?'selected':''}>Running-stitch curve</option><option value="satin" ${settings.brush==='satin'?'selected':''}>Pressure satin brush</option></select></label>${settings.brush==='satin'?`<div class="field-row"><label>Light pressure width (mm)<input id="penMin" type="number" min="0.6" max="8" step="any" value="${settings.minWidth}"></label><label>Firm pressure width (mm)<input id="penMax" type="number" min="0.6" max="8" step="any" value="${settings.maxWidth}"></label></div><p class="caption">Pencil pressure shapes the two satin rails. Finger and mouse use the midpoint width. Tight bends may need rail edits; use Check before sewing.</p>`:''}<label>Smoothing (mm)<input id="penSmooth" type="number" min="0.05" max="1" step="any" value="${settings.smoothing}"></label><label class="check"><input id="keepDrawing" type="checkbox" ${settings.keepDrawing?'checked':''}>Keep drawing after each stroke</label><p class="caption">Palm touches are ignored while a pen is down. Pinch with two fingers to zoom. Pressure is available when the device and browser report it.</p><button id="finishDrawing" class="primary wide">Finish drawing · Select</button>`;
    $('penOnly').onchange=e=>{settings.penOnly=e.target.checked;save();};$('penBrush').onchange=e=>{settings.brush=e.target.value;save();render(host);};$('keepDrawing').onchange=e=>{settings.keepDrawing=e.target.checked;save();};
    for(const[id,key]of [['penMin','minWidth'],['penMax','maxWidth'],['penSmooth','smoothing']])if($(id))$(id).onchange=e=>{if(e.target.value&&e.target.validity.valid){settings[key]=Number(e.target.value);if(settings.maxWidth<settings.minWidth){settings.maxWidth=settings.minWidth;if($('penMax'))$('penMax').value=settings.maxWidth;}save();}};
    $('finishDrawing').onclick=ctx.finish;
  }
  return{render,get:()=>({...settings}),setPenOnly:value=>{settings.penOnly=!!value;save();},canDraw:e=>!settings.penOnly||['pen','mouse'].includes(e.pointerType)};
}
