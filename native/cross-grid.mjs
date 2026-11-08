export function crossGrids(rows=[]){
  if(!Array.isArray(rows)||rows.length>12)throw new Error('Keep at most 12 cross-stitch grids.');
  return rows.map(g=>{
    if(!g||typeof g.id!=='string'||!/^[\w-]{1,80}$/.test(g.id)||!/^#[\da-f]{6}$/i.test(g.color)||typeof g.visible!=='boolean'||!['width','height','x','y'].every(k=>typeof g[k]==='number'&&Number.isFinite(g[k]))||g.width<.1||g.height<.1||g.width>100||g.height>100||Math.abs(g.x)>100||Math.abs(g.y)>100)throw new Error('Invalid cross-stitch grid.');
    return {...g};
  });
}
export function snappedMove(project,origins,dx,dy){
  const grid=project.crossSnap&&project.crossGrids?.findLast(g=>g.visible);
  if(grid&&origins.length){const x=Math.min(...origins.map(p=>p.x)),y=Math.min(...origins.map(p=>p.y));return [grid.x+Math.round((x+dx-grid.x)/grid.width)*grid.width-x,grid.y+Math.round((y+dy-grid.y)/grid.height)*grid.height-y];}
  return project.snap?[Math.round(dx*2)/2,Math.round(dy*2)/2]:[dx,dy];
}
export function drawGrids(host,rows){
  const signature=JSON.stringify(rows||[]);if(host.dataset.crossGridSignature===signature)return;host.dataset.crossGridSignature=signature;
  host.replaceChildren();
  for(const g of rows||[]){
    if(!g.visible)continue;
    let d='';for(let x=g.x+Math.ceil(-g.x/g.width)*g.width;x<=100.00001;x+=g.width)d+=`M${x},0V100`;
    for(let y=g.y+Math.ceil(-g.y/g.height)*g.height;y<=100.00001;y+=g.height)d+=`M0,${y}H100`;
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');for(const [k,v] of Object.entries({d,fill:'none',stroke:g.color,'stroke-width':.12,opacity:.4,'pointer-events':'none'}))path.setAttribute(k,v);host.append(path);
  }
}
