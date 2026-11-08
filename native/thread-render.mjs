// Lighting follows the real stitch segments; it never invents stitch geometry.
export function tint(hex,amount){
  const value=/^#[0-9a-f]{6}$/i.test(hex)?hex:'#203f38';
  return '#'+[1,3,5].map(i=>{const n=parseInt(value.slice(i,i+2),16);return Math.round(amount<0?n*(1+amount):n+(255-n)*amount).toString(16).padStart(2,'0');}).join('');
}
export function paintStitches(ctx,preview,count=preview.segments.length,style='paths',options={}){
  ctx.lineCap='round';ctx.lineJoin='round';
  const start=options.start||0,widthScale=(options.width??.18)/.18;
  if(style==='thread'){
    const palette=preview.threads.map(t=>({dark:tint(t.color,-.48),mid:t.color,light:tint(t.color,.40)}));
    for(const s of preview.segments.slice(start,count)){
      const color=palette[s[4]]||{dark:'#14251f',mid:'#203f38',light:'#6f8e7f'};
      const dx=s[2]-s[0],dy=s[3]-s[1],length=Math.hypot(dx,dy);if(!length)continue;
      for(const [width,ink,offset]of [[.30,color.dark,0],[.235,color.mid,0],[.065,color.light,-.045]]){
        const x=-dy/length*offset*widthScale,y=dx/length*offset*widthScale;ctx.lineWidth=width*widthScale;ctx.strokeStyle=ink;ctx.beginPath();ctx.moveTo(s[0]+x,s[1]+y);ctx.lineTo(s[2]+x,s[3]+y);ctx.stroke();
      }
    }
  }else{
    ctx.lineWidth=.18*widthScale;let thread=-1;
    for(const s of preview.segments.slice(start,count)){
      if(s[4]!==thread){if(thread>=0)ctx.stroke();thread=s[4];ctx.strokeStyle=preview.threads[thread]?.color||'#203f38';ctx.beginPath();}
      ctx.moveTo(s[0],s[1]);ctx.lineTo(s[2],s[3]);
    }
    if(thread>=0)ctx.stroke();
  }
}
// Standalone, portable proof made from the same PES segments as the canvas.
export function threadSVG(preview,fabric='#ffffff'){
  const [x,y]=preview.bounds,pad=3,fmt=n=>Math.round(n*1000)/1000;
  const palette=preview.threads.map(t=>[tint(t.color,-.48),tint(t.color,0),tint(t.color,.4)]);
  let svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${x-pad} ${y-pad} ${preview.width+2*pad} ${preview.height+2*pad}"><rect x="${x-pad}" y="${y-pad}" width="${preview.width+2*pad}" height="${preview.height+2*pad}" fill="${tint(fabric,0)}"/><g fill="none" stroke-linecap="round">`;
  for(const s of preview.segments){
    const dx=s[2]-s[0],dy=s[3]-s[1],len=Math.hypot(dx,dy);if(!len)continue;
    for(const[i,width,offset]of [[0,.30,0],[1,.235,0],[2,.065,-.045]]){
      const ox=-dy/len*offset,oy=dx/len*offset;
      svg+=`<path d="M${fmt(s[0]+ox)},${fmt(s[1]+oy)} L${fmt(s[2]+ox)},${fmt(s[3]+oy)}" stroke="${palette[s[4]]?.[i]||'#203f38'}" stroke-width="${width}"/>`;
    }
  }
  return svg+'</g></svg>';
}
