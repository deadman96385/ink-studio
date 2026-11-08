const action=(entry,label,value='')=>({entry,label,value});
const number=value=>typeof value==='number'&&Number.isFinite(value)?String(Math.round(value*1000)/1000):'';
const mm=value=>number(value)?number(value)+' mm':'';
const setting=(entry,label,key,value,min,max,unit='mm')=>({...action(entry,label,unit==='%'?number(value)+'%':mm(value)),editor:{key,value,min,max,unit}});

// These are stable shortcut positions for each selection type. The finder owns
// availability and navigation. Settings expose their existing input types, units
// and limits for direct editing; generated lettering still goes through the engine.
export function selectionShelfModel({selection=[],mode='select'}={}){
  if(!selection.length||mode==='draw')return {visible:false,actions:[]};
  const locked=selection.some(l=>l.locked),hidden=selection.some(l=>l.visible===false);
  const l=selection.length===1?selection[0]:null;
  const common=action('tool.arrange','Arrange');
  const thread={...action('layer.color',l?.multicolorSatin?'First thread':'Thread'),editor:{key:'color',type:'color',value:l?.multicolorSatin?.bands?.[0]?.color||l?.color||'#203f38'}};
  let kind,actions;
  if(!l){
    kind='Multiple objects';
    actions=[common,action('tool.threads','Threads'),action('tool.shape-tools','Shapes'),action('tool.stitch-order','Order')];
  }else if(l.link||l.linkedHelper){
    kind=l.linkedHelper?'Linked helper':'Linked copy';
    actions=[action('tool.linked-settings','Link settings'),action('tool.linked-source','Source'),l.linkedHelper?action('tool.linked-owner','Artwork'):common];
  }else if(l.type==='image'){
    kind='Reference image';
    actions=[action('tool.regions','Regions'),action('tool.trace','Trace'),setting('reference.opacity','Opacity','opacity',(l.opacity??.45)*100,5,100,'%'),common];
  }else if(l.ttfLettering){
    kind='Satin lettering';
    actions=[action('tool.ttf','Text & font'),setting('field.ttf.ttfSpacing','Spacing','ttfSpacing',l.ttfLettering.spacing??.4,.2,1.5),thread,common];
  }else if(l.type==='text'){
    kind='Embroidery lettering';
    actions=[action('tool.edit-lettering','Text & font'),setting('field.edit-lettering.letterSpacing','Spacing','letterSpacing',l.lettering?.letterSpacing??0,-2,10),thread,common];
  }else if(l.role&&l.role!=='artwork'){
    kind='Guide / helper';
    actions=[action('tool.nodes','Nodes'),action('tool.helpers','Guides'),action('tool.commands','Commands'),common];
  }else if(l.stitch==='original'||l.type==='import'){
    kind='Imported artwork';
    actions=[action('tool.svg','SVG tools'),action('tool.advanced','Stitches'),action('tool.threads','Threads'),common];
  }else if(l.stitch==='satin'){
    kind='Satin column';
    actions=[action('tool.nodes','Rails & rungs'),setting('layer.spacing','Density','spacing',l.spacing??.4,.2,2),thread,common];
  }else if(l.stitch==='fill'&&['streamline_fill','wave_fill'].includes(l.fillMethod)){
    kind=l.fillMethod==='wave_fill'?'Wave Fill':'Streamlines';
    actions=[action('tool.nodes','Nodes'),action(l.fillMethod==='wave_fill'?'tool.wave':'tool.streamlines','Flow guides',mm(l.streamlines?.separation??1.2)),thread,common];
  }else if(l.stitch==='fill'){
    kind='Filled shape';
    const stitches=['cross_stitch','meander_fill'].includes(l.fillMethod)?action('layer.fillMethod','Pattern'):setting('layer.spacing','Density','spacing',l.spacing??.4,.2,2);
    actions=[action('tool.nodes','Nodes'),stitches,thread,common];
  }else{
    kind=l.stitch==='manual'?'Manual stitches':l.stitch==='ripple'?'Ripple stitches':'Outline stitches';
    const length=['running','bean','ripple'].includes(l.stitch)?setting('layer.stitchLength','Length','stitchLength',l.stitchLength??2.5,.5,6):action('layer.stitchLength','Length',mm(l.stitchLength));
    actions=[action('tool.nodes','Nodes'),l.stitch==='manual'?action('tool.advanced','Stitches'):length,thread,common];
  }
  const size=l&&number(l.width)&&number(l.height)?number(l.width)+' × '+number(l.height)+' mm':'';
  const title=l?l.name||kind:selection.length+' objects selected';
  const dimensions=l&&!l.linkedHelper?['width','height'].map(key=>{
    const entry=l.link?'tool.linked-settings':l.type==='text'?'tool.arrange':(l.type==='image'?'reference.':'layer.')+key;
    const control=setting(entry,key==='width'?'Width':'Height',key,l[key],.2,100);
    control.editor.displayValue=Number.isFinite(l[key])?Math.round(l[key]*1000)/1000:l[key];
    control.editor.reason=l.locked?'Unlock the selected artwork first.':'';
    if(l.type==='text')control.editor.help='Resize through the embroidery font. Font proportions and scale limits are preserved.';
    return control;
  }):[];
  const proportions=dimensions.length?{value:l.type==='text'||l.aspectLock!==false,fixed:l.type==='text',disabled:!!l.locked}:null;
  const positions=l&&!l.linkedHelper?['x','y'].map(key=>{
    const entry=l.link?'tool.linked-settings':(l.type==='image'?'reference.':'layer.')+key;
    const control=setting(entry,key.toUpperCase(),key,l[key],-100,200);
    control.editor.displayValue=Number.isFinite(l[key])?Math.round(l[key]*1000)/1000:l[key];
    control.editor.reason=l.locked?'Unlock the selected artwork first.':'';
    control.editor.help=key.toUpperCase()+' position';
    return control;
  }):[];
  return {visible:true,kind,title,subtitle:[kind,size,hidden?'Hidden':''].filter(Boolean).join(' · '),locked:locked&&!l?.linkedHelper,actions,dimensions,positions,proportions,
    note:l?.linkedHelper?'Position and protection follow the linked artwork.':locked?'Locked artwork · open protection controls to edit.':l?.preserveFontColors?'Font thread colors are preserved. Turn off “Keep font thread colors” to choose a single thread.':''};
}
