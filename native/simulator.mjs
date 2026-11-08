import {paintStitches} from './thread-render.mjs';
import {PenGate} from './pen.mjs';
import {clamp,indexPlan,nextPosition,advance,fitView,worldPoint,zoomView,viewProjection,inspectStitch} from './simulator-model.mjs';

export function createSimulator(ctx){
  const $=id=>document.getElementById(id),canvas=$('stitchCanvas'),dialog=$('previewDialog'),buffer=document.createElement('canvas');
  let plan=null,model=null,position=0,view=null,cacheView=null,raf=null,lastTime=0,credit=0,cacheKey='',painted=0,gesture=null;
  const pointers=new Map(),gate=new PenGate(),markerColors={jump:'#287ca7',trim:'#b56520',stop:'#c14949',color:'#8754a6'};
  const defaults={style:'thread',speed:500,width:.18,pointSize:.35,crossRadius:10,crossWidth:1.5,crossColor:'#9c422e',adaptive:false,points:false,jumps:true,trims:true,stops:true,colors:true,crosshair:true,hoop:false,pause:false,background:'#faf7f0',customBackground:false,reverse:false};
  let settings={...defaults};try{settings={...settings,...JSON.parse(localStorage.getItem('inkstudio-simulator-v1')||'{}')};}catch{}
  for(const [k,a,b]of [['speed',1,100000],['width',.03,2],['pointSize',.03,3],['crossRadius',1,100],['crossWidth',1,20]])settings[k]=clamp(Number(settings[k])||defaults[k],a,b);
  for(const key of Object.keys(defaults).filter(k=>typeof defaults[k]==='boolean'))settings[key]=settings[key]===true;
  if(!/^#[\da-f]{6}$/i.test(settings.background))settings.background=defaults.background;settings.style=settings.style==='paths'?'paths':'thread';
  if(!/^#[\da-f]{6}$/i.test(settings.crossColor))settings.crossColor=defaults.crossColor;
  const save=()=>{try{localStorage.setItem('inkstudio-simulator-v1',JSON.stringify(settings));}catch{}};
  document.head.insertAdjacentHTML('beforeend','<link rel="stylesheet" href="/simulator.css">');
  $('previewContent').before(Object.assign(document.createElement('div'),{className:'sim-scope',id:'simScope'}));
  $('simScope').innerHTML='<strong id="simScopeLabel">Whole design preview & export</strong><button id="simAll" type="button">Whole design</button><button id="simSelection" type="button">Selected artwork</button>';
  canvas.before(Object.assign(document.createElement('div'),{className:'sim-toolbar',id:'simToolbar'}));
  $('simToolbar').innerHTML='<label>Stitch view<select id="stitchViewStyle"><option value="thread">Thread shading</option><option value="paths">Needle paths</option></select></label><button id="simZoomOut" type="button" aria-label="Zoom simulator out">−</button><button id="simFit" type="button">Fit design</button><button id="simZoomIn" type="button" aria-label="Zoom simulator in">＋</button><button id="simExpand" type="button" aria-pressed="false">Expand</button>';
  canvas.after(Object.assign(document.createElement('div'),{id:'simControls'}));
  document.querySelector('.play-controls').remove();
  $('simControls').innerHTML=`<p class="caption">Drag or pinch to inspect. Tap a stitch with Pencil, or tap without dragging, to go to it.</p>
    <canvas id="simTimeline" aria-label="Command locations on the playback timeline"></canvas>
    <div class="sim-position"><label>Playback position<input id="stitchProgress" type="range" min="0" max="1" step="1" value="0"></label><label>Needle stitch<input id="simStitchNumber" type="number" inputmode="numeric" min="0" step="1" value="0"></label></div>
    <output id="stitchPosition" aria-label="Current simulator position"></output>
    <div class="sim-navigation"><button id="simPreviousStitch" type="button">−1 stitch</button><button id="playBtn" type="button">▶ Play</button><button id="simNextStitch" type="button">+1 stitch</button><button id="simReverse" type="button" aria-pressed="false">Forward →</button></div>
    <div class="sim-navigation"><button id="simRestart" type="button">Start</button><button id="simPreviousCommand" type="button">Previous command</button><button id="simNextCommand" type="button">Next command</button><button id="simEnd" type="button">End</button></div>
    <div class="sim-speed"><label>Jump to<select id="simCommandKind"><option value="all">Any jump, trim, stop or color change</option><option value="jump">Jump</option><option value="trim">Trim</option><option value="stop">Stop</option><option value="color">Color change</option></select></label><label>Playback speed (steps/s)<input id="simSpeed" type="number" inputmode="numeric" min="1" max="100000" step="1"></label><button id="simSlower" type="button" aria-label="Slower playback">½×</button><button id="simFaster" type="button" aria-label="Faster playback">2×</button></div>
    <details class="control-section sim-settings"><summary>Simulator display & playback settings</summary>
    <div class="sim-checks">${[['points','Needle points'],['jumps','Jumps'],['trims','Trim markers'],['stops','Stop markers'],['colors','Color-change markers'],['crosshair','Needle crosshair'],['hoop','100 mm hoop at machine origin'],['pause','Pause at trims, stops & color changes']].map(([key,label])=>`<label class="check"><input id="sim-${key}" type="checkbox">${label}</label>`).join('')}</div>
    <label class="check"><input id="simAdaptive" type="checkbox">Adapt speed to design length (about 5 seconds)</label>
    <div class="field-row"><label>Line width (mm)<input id="simLineWidth" type="number" min="0.03" max="2" step="0.01" inputmode="decimal"></label><label>Needle point size (mm)<input id="simPointSize" type="number" min="0.03" max="3" step="0.01" inputmode="decimal"></label></div>
    <div class="field-row"><label>Crosshair radius (px)<input id="simCrossRadius" type="number" min="1" max="100" step="1" inputmode="numeric"></label><label>Crosshair thickness (px)<input id="simCrossWidth" type="number" min="1" max="20" step="0.5" inputmode="decimal"></label></div><label>Crosshair color<input id="simCrossColor" type="color"></label>
    <label>Preview background<input id="simBackground" type="color"></label><div class="button-row"><button id="simFabric" type="button">Use design fabric color</button><button id="simReset" type="button">Reset simulator settings</button></div>
    <p class="sim-legend">Blue dashed line: jump · Orange ×: trim · Red square: stop · Purple diamond: color change. These are the commands encoded in the PES. Shading illustrates thread lighting. Playback speed does not set machine speed.</p>
    <p class="caption">Keyboard: +/− step a stitch, Page Up/Down jump commands, arrows left/right set direction, arrows up/down change speed, Space or P play/pause, R restart, O toggle needle points.</p></details>`;
  // Keep playback and the canvas together while the settings scroll beside it.
  const area=canvas.parentElement,stage=document.createElement('div');stage.className='sim-stage';area.prepend(stage);
  for(const e of [$('simToolbar'),canvas,$('simControls').querySelector('.caption'),$('simTimeline'),$('simControls').querySelector('.sim-position'),$('stitchPosition'),$('simControls').querySelector('.sim-navigation')])stage.append(e);
  area.after($('simControls'));
  const info=document.createElement('details');info.className='control-section sim-info';info.innerHTML='<summary>Design information & threads</summary>';
  const details=document.querySelector('.preview-details');details.className='sim-info-body';info.append(details);$('simControls').append(info);
  const originNote=$('previewStatus').nextElementSibling;if(originNote?.tagName==='P')info.append(originNote);
  let fabric=settings.background;
  const current=()=>Math.round(position),size=()=>{const r=canvas.getBoundingClientRect();return [r.width,r.height];};
  function transform(c,w,h,dpr){c.setTransform(dpr,0,0,dpr,0,0);c.translate(w/2-view.x*view.scale,h/2-view.y*view.scale);c.scale(view.scale,view.scale);}
  function drawTimeline(){
    if(!model)return;const c=$('simTimeline'),r=c.getBoundingClientRect(),dpr=devicePixelRatio||1;if(!r.width)return;c.width=r.width*dpr;c.height=20*dpr;const g=c.getContext('2d');g.scale(dpr,dpr);
    const sections=[0,...model.events.color,model.length];for(let i=0;i<sections.length-1;i++){g.fillStyle=plan.threads[i]?.color||'#203f38';g.fillRect(sections[i]/model.length*r.width,15,(sections[i+1]-sections[i])/model.length*r.width,5);}
    for(const kind of ['jump','trim','stop','color'])if(settings[{jump:'jumps',trim:'trims',stop:'stops',color:'colors'}[kind]]){g.strokeStyle=markerColors[kind];g.beginPath();for(const p of model.events[kind]){const x=p/model.length*r.width;g.moveTo(x,2);g.lineTo(x,12);}g.stroke();}
  }
  function draw(){
    if(!plan||!dialog.open||$('previewContent').hidden)return;const [w,h]=size(),dpr=devicePixelRatio||1;if(!w||!h)return;
    if(!view)view=fitView(plan.bounds,w,h);const p=current(),count=model.segments[p],key=JSON.stringify([w,h,dpr,view,settings.style,settings.width,settings.background,settings.hoop]);
    if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
    const bg=buffer.getContext('2d');
    const moving=gesture&&cacheView&&cacheKey&&count===painted&&buffer.width===canvas.width&&buffer.height===canvas.height;
    if(!moving&&(cacheKey!==key||count<painted)){buffer.width=canvas.width;buffer.height=canvas.height;bg.fillStyle=settings.background;bg.fillRect(0,0,buffer.width,buffer.height);transform(bg,w,h,dpr);
      if(settings.hoop){bg.fillStyle='#ffffff50';bg.fillRect(-50,-50,100,100);bg.strokeStyle='#829c80';bg.lineWidth=1/view.scale;bg.strokeRect(-50,-50,100,100);bg.fillStyle='#637b61';bg.font=`${11/view.scale}px sans-serif`;bg.fillText('100 × 100 mm · machine origin at center',-49,-51);}
      cacheKey=key;cacheView={...view};painted=0;
    }
    if(!moving){paintStitches(bg,plan,count,settings.style,{start:painted,width:settings.width});painted=count;}
    const g=canvas.getContext('2d');g.setTransform(1,0,0,1,0,0);g.fillStyle=settings.background;g.fillRect(0,0,canvas.width,canvas.height);
    if(moving){const projected=viewProjection(cacheView,view,w,h);g.setTransform(projected.scale,0,0,projected.scale,projected.x*dpr,projected.y*dpr);}
    g.drawImage(buffer,0,0);transform(g,w,h,dpr);g.lineWidth=1.4/view.scale;
    if(settings.points){g.fillStyle='#243e34';g.beginPath();for(let i=1;i<model.needle.length&&model.needle[i]<=p;i++){const e=model.commands[model.needle[i]-1];g.moveTo(e[0]+settings.pointSize/2,e[1]);g.arc(e[0],e[1],settings.pointSize/2,0,Math.PI*2);}g.fill();}
    for(const kind of ['jump','trim','stop','color']){
      if(!settings[{jump:'jumps',trim:'trims',stop:'stops',color:'colors'}[kind]])continue;g.strokeStyle=g.fillStyle=markerColors[kind];const r=4/view.scale;
      for(const index of model.events[kind]){if(index>p)break;const e=model.commands[index-1],[x,y]=e;g.beginPath();
        if(kind==='jump'){const previous=model.commands[index-2]||[0,0];g.setLineDash([4/view.scale,3/view.scale]);g.moveTo(previous[0],previous[1]);g.lineTo(x,y);g.stroke();g.setLineDash([]);g.beginPath();g.arc(x,y,2/view.scale,0,Math.PI*2);g.fill();}
        else if(kind==='trim'){g.moveTo(x-r,y-r);g.lineTo(x+r,y+r);g.moveTo(x-r,y+r);g.lineTo(x+r,y-r);g.stroke();}
        else if(kind==='stop'){g.fillRect(x-r,y-r,r*2,r*2);}
        else{g.moveTo(x,y-r*1.5);g.lineTo(x+r*1.5,y);g.lineTo(x,y+r*1.5);g.lineTo(x-r*1.5,y);g.closePath();g.fill();}
      }
    }
    const event=model.commands[p-1];
    if(event&&settings.crosshair){g.strokeStyle=settings.crossColor;g.lineWidth=settings.crossWidth/view.scale;const r=settings.crossRadius/view.scale;g.beginPath();g.moveTo(event[0]-r,event[1]);g.lineTo(event[0]+r,event[1]);g.moveTo(event[0],event[1]-r);g.lineTo(event[0],event[1]+r);g.stroke();}
    $('stitchProgress').value=p;$('stitchProgress').setAttribute('aria-valuetext',`Stitch ${model.stitches[p]} of ${plan.stitches}, ${event?model.names[event[2]]||'command':'start'}`);
    if(document.activeElement!==$('simStitchNumber'))$('simStitchNumber').value=model.stitches[p];
    const thread=Math.min(model.threads[p],Math.max(0,plan.threads.length-1));
    $('stitchPosition').textContent=`Stitch ${model.stitches[p].toLocaleString()} / ${plan.stitches.toLocaleString()} · ${event?(model.names[event[2]]||'command'):'start'} · Thread ${thread+1}${event?` · X ${event[0]} / Y ${event[1]} mm`:''} · ${Math.round(p/model.length*100)}%`;
    document.querySelectorAll('.sim-thread').forEach((e,i)=>e.setAttribute('aria-current',String(i===thread)));
    $('simPreviousStitch').disabled=p===0;$('simNextStitch').disabled=p===model.length;
  }
  function stop(){if(raf!==null)cancelAnimationFrame(raf);raf=null;credit=0;$('playBtn').textContent='▶ Play';}
  function seek(p){stop();position=clamp(Math.round(p),0,model?.length||0);draw();}
  function play(){if(!model)return;if(raf!==null){stop();return;}const direction=settings.reverse?-1:1;if((direction>0&&position>=model.length)||(direction<0&&position<=0))position=direction>0?0:model.length;
    lastTime=performance.now();credit=0;$('playBtn').textContent='Ⅱ Pause';
    const frame=now=>{credit+=Math.min(.25,(now-lastTime)/1000)*settings.speed;lastTime=now;const amount=Math.floor(credit);credit-=amount;if(amount){const next=advance(model,position,amount,settings.reverse?-1:1,settings.pause);position=next.position;draw();if(next.paused){stop();return;}}raf=requestAnimationFrame(frame);};raf=requestAnimationFrame(frame);
  }
  function fit(hoop=false){if(!plan)return;const [w,h]=size();view=fitView(hoop?[-54,-54,54,54]:plan.bounds,w,h);cacheKey='';draw();}
  function zoom(factor,anchor){if(!view)return;const [w,h]=size();view=zoomView(view,factor,anchor||[w/2,h/2],w,h);draw();}
  function controls(){
    $('stitchViewStyle').value=settings.style;$('simSpeed').value=settings.speed;$('simLineWidth').value=settings.width;$('simPointSize').value=settings.pointSize;$('simBackground').value=settings.background;
    $('simAdaptive').checked=settings.adaptive;$('simCrossRadius').value=settings.crossRadius;$('simCrossWidth').value=settings.crossWidth;$('simCrossColor').value=settings.crossColor;
    for(const key of ['points','jumps','trims','stops','colors','crosshair','hoop','pause'])$('sim-'+key).checked=settings[key];
    $('simReverse').setAttribute('aria-pressed',String(settings.reverse));$('simReverse').textContent=settings.reverse?'← Reverse':'Forward →';
  }
  $('simAll').onclick=()=>ctx.preview('all');$('simSelection').onclick=()=>ctx.preview('selection');
  $('playBtn').onclick=play;$('stitchProgress').oninput=e=>seek(Number(e.target.value));$('simStitchNumber').oninput=e=>{if(e.target.value!==''&&e.target.validity.valid)seek(model.needle[Number(e.target.value)]??model.length);};
  $('simPreviousStitch').onclick=()=>seek(nextPosition(model.needle,current(),-1,model.length));$('simNextStitch').onclick=()=>seek(nextPosition(model.needle,current(),1,model.length));
  for(const [id,direction]of [['simPreviousCommand',-1],['simNextCommand',1]])$(id).onclick=()=>seek(nextPosition(model.events[$('simCommandKind').value],current(),direction,model.length));
  $('simRestart').onclick=()=>seek(0);$('simEnd').onclick=()=>seek(model.length);$('simReverse').onclick=()=>{settings.reverse=!settings.reverse;controls();save();};
  const speed=factor=>{settings.speed=clamp(Math.round(settings.speed*factor),1,100000);settings.adaptive=false;controls();save();};$('simSlower').onclick=()=>speed(.5);$('simFaster').onclick=()=>speed(2);
  for(const [id,key]of [['simSpeed','speed'],['simLineWidth','width'],['simPointSize','pointSize'],['simCrossRadius','crossRadius'],['simCrossWidth','crossWidth']])$(id).oninput=e=>{if(e.target.value!==''&&e.target.validity.valid){settings[key]=Number(e.target.value);if(key==='speed'){settings.adaptive=false;$('simAdaptive').checked=false;}save();draw();}};
  $('simAdaptive').onchange=e=>{settings.adaptive=e.target.checked;if(settings.adaptive&&model)settings.speed=clamp(Math.round(model.length/5),10,100000);controls();save();};$('simCrossColor').oninput=e=>{settings.crossColor=e.target.value;save();draw();};
  $('stitchViewStyle').onchange=e=>{settings.style=e.target.value;save();draw();};
  for(const key of ['points','jumps','trims','stops','colors','crosshair','hoop','pause'])$('sim-'+key).onchange=e=>{settings[key]=e.target.checked;save();if(key==='hoop'&&settings.hoop)fit(true);else draw();drawTimeline();};
  $('simBackground').oninput=e=>{settings.background=e.target.value;settings.customBackground=true;save();draw();};$('simFabric').onclick=()=>{settings.customBackground=false;settings.background=fabric;controls();save();draw();};
  $('simReset').onclick=()=>{stop();settings={...defaults,background:fabric};controls();save();fit();drawTimeline();};
  $('simZoomOut').onclick=()=>zoom(.8);$('simZoomIn').onclick=()=>zoom(1.25);$('simFit').onclick=()=>fit();$('simExpand').onclick=()=>{const expanded=dialog.classList.toggle('sim-expanded');$('simExpand').setAttribute('aria-pressed',String(expanded));$('simExpand').textContent=expanded?'Restore size':'Expand';};
  const point=e=>{const r=canvas.getBoundingClientRect();return[e.clientX-r.left,e.clientY-r.top];};
  function begin(){const points=[...pointers.values()].map(p=>p.point);if(!points.length){gesture=null;return;}gesture={view:{...view},start:points[0],mid:points.length>1?[(points[0][0]+points[1][0])/2,(points[0][1]+points[1][1])/2]:points[0],distance:points.length>1?Math.hypot(points[1][0]-points[0][0],points[1][1]-points[0][1]):0,moved:false,pinch:points.length>1};}
  canvas.onpointerdown=e=>{if(!model||!gate.down(e,performance.now())||e.button>0)return;if(e.pointerType==='pen'){pointers.clear();gesture=null;}stop();e.preventDefault();canvas.setPointerCapture(e.pointerId);pointers.set(e.pointerId,{point:point(e),type:e.pointerType});begin();};
  canvas.onpointermove=e=>{if(!pointers.has(e.pointerId)||!gesture)return;const entry=pointers.get(e.pointerId);entry.point=point(e);const points=[...pointers.values()].map(v=>v.point),[w,h]=size();
    if(points.length>1){const mid=[(points[0][0]+points[1][0])/2,(points[0][1]+points[1][1])/2],distance=Math.hypot(points[1][0]-points[0][0],points[1][1]-points[0][1]);view=zoomView(gesture.view,distance/Math.max(1,gesture.distance),gesture.mid,w,h);view.x-=(mid[0]-gesture.mid[0])/view.scale;view.y-=(mid[1]-gesture.mid[1])/view.scale;gesture.moved=true;}
    else{const dx=entry.point[0]-gesture.start[0],dy=entry.point[1]-gesture.start[1];gesture.moved=gesture.moved||Math.hypot(dx,dy)>7;if(gesture.moved)view={...gesture.view,x:gesture.view.x-dx/view.scale,y:gesture.view.y-dy/view.scale};}draw();};
  function end(e,cancel=false){gate.end(e,performance.now());if(!pointers.has(e.pointerId))return;const was=gesture;pointers.delete(e.pointerId);if(!cancel&&was&&!was.moved&&!was.pinch&&pointers.size===0){const [w,h]=size(),pos=inspectStitch(model,worldPoint(view,point(e),w,h),14/view.scale);if(pos!==null)seek(pos);}begin();if(pointers.size&&gesture)gesture.moved=true;else draw();}
  canvas.onpointerup=e=>end(e);canvas.onpointercancel=e=>end(e,true);canvas.onlostpointercapture=e=>{if(pointers.has(e.pointerId))end(e,true);};canvas.onwheel=e=>{e.preventDefault();zoom(Math.exp(-e.deltaY*.0015),point(e));};
  dialog.addEventListener('keydown',e=>{if(!model||['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)||e.altKey||e.metaKey||e.ctrlKey)return;const key=e.key.toLowerCase();let action={'+':()=> $('simNextStitch').click(),'=':()=> $('simNextStitch').click(),'-':()=> $('simPreviousStitch').click(),pageup:()=> $('simNextCommand').click(),pagedown:()=> $('simPreviousCommand').click(),' ':play,p:play,r:()=>seek(0),o:()=> $('sim-points').click(),arrowup:()=>speed(2),arrowdown:()=>speed(.5),arrowleft:()=>{settings.reverse=true;controls();save();},arrowright:()=>{settings.reverse=false;controls();save();}}[key];if(action){e.preventDefault();action();}});
  dialog.addEventListener('close',()=>{stop();pointers.clear();gate.reset();gesture=null;});document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  new ResizeObserver(()=>{cacheKey='';draw();drawTimeline();}).observe(canvas);controls();
  return{
    stop,
    scope(scope,count,busy=false){$('simScopeLabel').textContent=scope==='selection'?`Selected artwork preview & export · ${count} ${count===1?'layer':'layers'}`:'Whole design preview & export';$('simAll').disabled=busy;$('simSelection').disabled=busy||!count;$('simAll').setAttribute('aria-pressed',String(scope!=='selection'));$('simSelection').setAttribute('aria-pressed',String(scope==='selection'));},
    load(value,color){stop();if(!Array.isArray(value.commands))throw new Error('Refresh the studio to load the machine-command simulator.');plan=value;model=indexPlan(plan);position=model.length;view=null;cacheKey='';fabric=color;if(!settings.customBackground)settings.background=color;if(settings.adaptive)settings.speed=clamp(Math.round(model.length/5),10,100000);controls();$('stitchProgress').max=model.length;$('simStitchNumber').max=plan.stitches;
      $('threadList').replaceChildren(Object.assign(document.createElement('h3'),{textContent:'Thread order · tap to go'}));plan.threads.forEach((thread,i)=>{const b=document.createElement('button');b.type='button';b.className='sim-thread';b.setAttribute('aria-label',`Go to thread ${i+1}: ${thread.name}`);const swatch=document.createElement('span');swatch.className='swatch';swatch.style.background=thread.color;const title=document.createElement('span');title.textContent=`${i+1}. ${thread.name}`;const detail=document.createElement('small');detail.textContent=[thread.brand,thread.number,thread.color].filter(Boolean).join(' · ');title.append(detail);b.append(swatch,title);b.onclick=()=>seek(i===0?0:model.events.color[i-1]??model.length);$('threadList').append(b);});requestAnimationFrame(()=>{draw();drawTimeline();});}
  };
}
