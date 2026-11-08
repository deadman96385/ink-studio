export const COMMAND_NAMES={entry:'starting_point',exit:'ending_point',targetPoint:'target_point',routeStart:'autoroute_start',routeEnd:'autoroute_end',satinCut:'satin_cut_point',trimCommand:'trim',stopCommand:'stop',ignoreObject:'ignore_object',ignoreLayer:'ignore_layer',origin:'origin',frameOut:'stop_position'};
export const displaySettings=p=>({visible:false,size:100,connectors:true,...p.commandDisplay});
export const activeCommand=(l,key)=>Array.isArray(l[key])&&(key!=='trimCommand'||(l.trimAfter??String(l.originalParams?.trim_after).toLowerCase()==='true'))&&(key!=='stopCommand'||(l.stopAfter??String(l.originalParams?.stop_after).toLowerCase()==='true'));
function matrixTo(element,root){let m=new DOMMatrix();for(let e=element;e&&e!==root;e=e.parentElement){const list=e.transform?.baseVal;if(!list)continue;let local=new DOMMatrix();for(let i=0;i<list.numberOfItems;i++)local=local.multiply(list.getItem(i).matrix);m=local.multiply(m);}return m;}
export function importedCommands(art,canvas){
  const result=[],names=Object.values(COMMAND_NAMES),lookup=new Map();
  for(const use of art.querySelectorAll('use')){
    if(use.closest('defs,symbol'))continue;
    const href=(use.getAttribute('href')||use.getAttributeNS('http://www.w3.org/1999/xlink','href')||'').replace(/^#(?:cmd-)+inkstitch_/,'#inkstitch_'),command=names.find(n=>href==='#inkstitch_'+n||href.startsWith('#inkstitch_'+n+'-'));
    if(!command)continue;
    const p=new DOMPoint(Number(use.getAttribute('x')||0),Number(use.getAttribute('y')||0)).matrixTransform(matrixTo(use,canvas));
    let target=null;const layer=use.closest('[data-layer]')||art;
    if(!lookup.has(layer)){const ids=new Map([...layer.querySelectorAll('[id]')].map(e=>[e.id,e])),connections=new Map();for(const path of layer.querySelectorAll('path')){const a=path.getAttributeNS('http://www.inkscape.org/namespaces/inkscape','connection-start')?.slice(1),b=path.getAttributeNS('http://www.inkscape.org/namespaces/inkscape','connection-end')?.slice(1);if(a&&b){connections.set(a,{path,node:ids.get(b)});connections.set(b,{path,node:ids.get(a)});}}lookup.set(layer,connections);}
    const connection=lookup.get(layer).get(use.id);
    if(connection){const {path,node}=connection;
      if(node?.getBBox){try{const b=node.getBBox(),q=new DOMPoint(b.x+b.width/2,b.y+b.height/2).matrixTransform(matrixTo(node,canvas));target=[q.x,q.y];}catch{}}
      path.style.display='none';
    }
    use.style.display='none';result.push({command,p:[p.x,p.y],target});
  }
  return result;
}
export function drawCommandSymbols(canvas,art,project,toWorld,node,id='nativeCommandSymbols'){
  const imported=importedCommands(art,canvas);let overlay=canvas.querySelector('#'+id);if(!overlay){overlay=node('g',{id,'pointer-events':'none'});canvas.append(overlay);}overlay.replaceChildren();
  const settings=displaySettings(project);if(!settings.visible||settings.size<=0)return;
  const rows=imported.filter(r=>!(r.command==='origin'&&'origin' in project)&&!(r.command==='stop_position'&&'frameOut' in project));
  for(const l of project.layers.filter(l=>l.visible!==false&&(!l.role||l.role==='artwork')&&l.type!=='image'))for(const key of Object.keys(COMMAND_NAMES).filter(k=>!['origin','frameOut'].includes(k)))if(activeCommand(l,key))rows.push({command:COMMAND_NAMES[key],p:toWorld(l,l[key]),target:key==='ignoreLayer'?null:toWorld(l,[.5,.5])});
  for(const key of ['origin','frameOut'])if(project[key])rows.push({command:COMMAND_NAMES[key],p:project[key],target:null});
  const size=6*settings.size/100;
  for(const {command,p,target} of rows){if(settings.connectors&&target)overlay.append(node('path',{d:`M${p[0]} ${p[1]} L${target[0]} ${target[1]}`,fill:'none',stroke:'#333','stroke-width':.2,opacity:.5}));const image=node('image',{x:p[0]-size/2,y:p[1]-size/2,width:size,height:size,href:'/command-symbols/'+command+'.svg',opacity:.7});const title=node('title');title.textContent=command.replaceAll('_',' ');image.append(title);overlay.append(image);}
}
