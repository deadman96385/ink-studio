// Search and selection rules are independent of the DOM and stitch generation.
export function normalize(value) {
  return String(value ?? '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

export function selectionReason(rule, state) {
  const layers = state.selection || [];
  const one = layers.length === 1 ? layers[0] : null;
  if (typeof rule === 'function') return rule(state) || '';
  if (!rule || rule === 'any') return '';
  if (!layers.length) return rule === 'pair' ? 'Select two shapes.' : 'Select artwork on the canvas or in Stitch order.';
  if (rule === 'image' || rule === 'image-edit') return one?.type !== 'image' ? 'Select a reference image.' : rule === 'image-edit' && one.locked ? 'Unlock the reference image to edit its settings.' : '';
  if (layers.some(l => l.locked)) return 'Unlock the selected artwork first.';
  if (rule === 'selection') return layers.some(l=>l.linkedHelper) ? 'Select the linked artwork to arrange its attached helpers.' : '';
  if (rule === 'artwork') return layers.some(l => l.type === 'image' || (l.role && l.role !== 'artwork')) ? 'Select stitched artwork, rather than a reference or guide.' : '';
  if (rule === 'pair') return layers.length === 2 && layers.every(l => l.type !== 'image' && l.type !== 'text' && !l.linkedHelper) ? '' : 'Select two shapes.';
  if (!one) return 'Select one object.';
  if (rule === 'text') return one.type === 'text' ? '' : 'Select an embroidery lettering object.';
  if (one.link || one.linkedHelper) return 'Edit the linked source, or detach the copy to edit its own settings.';
  if (rule === 'object') return one.type !== 'image' ? '' : 'Select stitched artwork, rather than a reference image.';
  if (one.type === 'text') return 'This embroidery font supplies its stitch construction. Separate its paths to edit individual stitches.';
  if (one.type === 'image') return 'Trace the reference image, or select a stitched shape.';
  if (rule === 'shape') return '';
  if (rule === 'fill') return one.stitch === 'fill' ? '' : 'Select a shape using Fill stitches.';
  if (rule === 'satin') return one.stitch === 'satin' ? '' : 'Select a satin column.';
  return '';
}

export function entryReason(entry, state) {
  return selectionReason(entry.requires, state);
}

export function searchEntries(entries, query, state, category = '') {
  const q = normalize(query), words = q.split(' ').filter(Boolean);
  return [...entries].flatMap((entry, index) => {
    if (category && entry.category !== category) return [];
    const title = normalize(entry.title), aliases = normalize(entry.aliases), path = normalize(entry.path);
    const text = title + ' ' + aliases + ' ' + path + ' ' + normalize(entry.help);
    if (!words.every(word => text.includes(word))) return [];
    const score = !q ? 0 : title === q ? 100 : title.includes(q) ? 70 : aliases.includes(q) ? 55 : words.reduce((n, word) => n + (title.includes(word) ? 8 : aliases.includes(word) ? 4 : 1), 0);
    return [{...entry, reason:entryReason(entry, state), score:score+(q&&entry.kind==='setting'?2:0), index}];
  }).sort((a, b) => b.score - a.score || Number(!!a.reason) - Number(!!b.reason) || a.index - b.index);
}

export const SETTING_ALIASES = {
  spacing:'density less dense more dense lighter fewer stitches coverage distance between rows',
  angle:'direction diagonal slant rows', stitchLength:'longer shorter stitches length',
  rotation:'rotate turn orientation', width:'size resize scale horizontal', height:'size resize scale vertical',
  color:'colour thread recolor recolour', trimAfter:'cut thread cuts trim', stopAfter:'pause stop machine',
  fillMethod:'fill pattern tatami contour circular meander stippling tartan plaid gradient guided streamlines wave flow field',
  pullCompensation:'pull compensation expand edge coverage', underlaySpacing:'underlay density foundation',
  borderEnabled:'outline border edge', borderStitch:'outline running bean zigzag border',
  penOnly:'apple pencil stylus palm finger touch', penSmooth:'smooth smoothing drawing',
  documentPreference_collapse_len_mm:'fewer trims thread cuts join jumps travel',
  documentPreference_min_stitch_len_mm:'tiny short stitches filter',
  preferenceCacheSize:'cache speed storage preview',
};

const field = (key, title, target, requires='shape', section='Layer', aliases='') => ({
  id:'layer.'+key, title, target, route:'layer', requires, category:'Stitches & thread',
  path:'Selected object › '+section, aliases:aliases || SETTING_ALIASES[key] || '',
});
const layer = state => state.selection?.length === 1 ? state.selection[0] : null;
const flowFill = state => layer(state)?.stitch==='fill'&&['streamline_fill','wave_fill'].includes(layer(state)?.fillMethod);
const fillUnderlay = state => selectionReason('fill',state)||(flowFill(state)?'Flow-field fills use running lines without fill underlay.':'');
const spacing = state => {
  const l=layer(state), reason=selectionReason('shape',state); if(reason)return reason;
  if(flowFill(state))return 'Use the flow-field fill editor → Separation to space the lines.';
  return l.stitch==='satin'||l.stitch==='zigzag'||(l.stitch==='fill'&&!['cross_stitch','meander_fill'].includes(l.fillMethod)) ? '' : 'Select a fill, satin column, or zigzag with row spacing controls.';
};

export const PANEL_SETTINGS = [
  field('spacing','Row spacing / density','[data-prop="spacing"], [data-extra="spacing"]',spacing,'Stitches'),
  field('angle','Fill angle','[data-prop="angle"]',state=>selectionReason('fill',state)||( ['tatami_fill','legacy_fill'].includes(layer(state)?.fillMethod||'tatami_fill')?'':'This fill follows its own guide or pattern direction.'),'Stitches'),
  field('stitchLength','Stitch length','[data-prop="stitchLength"]',state=>selectionReason('shape',state)||(['running','bean','ripple'].includes(layer(state)?.stitch)||(layer(state)?.stitch==='fill'&&layer(state)?.fillMethod!=='cross_stitch')?'':'This stitch method supplies its own stitch length.'),'Stitches'),
  field('stitch','Stitch type','[data-prop="stitch"]','shape','Stitches','fill running bean triple run zigzag satin ripple manual'),
  field('fillMethod','Fill pattern','[data-extra="fillMethod"]','fill','Stitches'),
  field('underlay','Fill underlay','#underlayCheck',fillUnderlay,'Stitches','foundation support stabilize stabilise puckering'),
  field('pullCompensation','Pull compensation','[data-extra="pullCompensation"]',state=>selectionReason('shape',state)||(flowFill(state)?'Flow-field fills follow the shape boundary without fill compensation.':['fill','satin'].includes(layer(state)?.stitch)?'':'Select a fill or satin column.'),'Stitches'),
  field('underlaySpacing','Underlay row spacing','[data-extra="underlaySpacing"]',state=>fillUnderlay(state)||(layer(state)?.underlay?'':'Enable Fill underlay to edit its spacing.'),'Fill compensation & underlay'),
  field('underlayInset','Underlay inset','[data-extra="underlayInset"]',state=>fillUnderlay(state)||(layer(state)?.underlay?'':'Enable Fill underlay to edit its inset.'),'Fill compensation & underlay'),
  field('borderEnabled','Outline over fill','[data-extra="borderEnabled"]','fill','Outline over fill'),
  field('trimAfter','Request trim after object','[data-extra="trimAfter"]','object','Trim & pause'),
  field('stopAfter','Pause after object','[data-extra="stopAfter"]','object','Trim & pause'),
  ...['x','y','width','height','rotation'].map(key=>({...field(key,{x:'X position',y:'Y position',width:'Width',height:'Height',rotation:'Rotation'}[key],'[data-prop="'+key+'"]',['width','height'].includes(key)?'shape':'object','Position & size'),category:'Arrange'})),
  field('color','Thread color','[data-prop="color"]',state=>selectionReason('object',state)||(layer(state)?.preserveFontColors?'Turn off “Keep font thread colors” to choose a single thread.':''),'Thread'),
  ...[['width','Reference image width'],['height','Reference image height'],['opacity','Reference image opacity'],['x','Reference image X position'],['y','Reference image Y position']].map(([key,title])=>({id:'reference.'+key,title,route:'layer',requires:'image-edit',target:'[data-reference="'+key+'"]',category:'Draw & edit',path:'Selected image › Reference settings',aliases:key==='opacity'?'transparency fade photo background':'photo picture size scale position '+key})),
  {id:'fabric.color',title:'Fabric preview color',route:'fabric',target:'#fabricColor',category:'Background',path:'Background › Fabric',aliases:'cloth colour canvas background no stitches'},
  {id:'fabric.grid',title:'Show 10 mm grid',route:'fabric',target:'#gridCheck',category:'Background',path:'Background › Grid',aliases:'ruler lines canvas grid'},
  {id:'fabric.snap',title:'Snap movement to 0.5 mm',route:'fabric',target:'#snapCheck',category:'Background',path:'Background › Grid',aliases:'snapping alignment half millimeter precision'},
  {id:'fabric.padding',title:'Stitched background padding',route:'fabric',target:'#backgroundPadding',category:'Background',path:'Background › Stitched background',aliases:'margin border fit background'},
  {id:'arrange.gap',title:'Gap between objects',route:'arrange',target:'#arrangeGap',requires:'selection',category:'Arrange',path:'Arrange › Spacing',aliases:'spacing stack distribute distance'},
  {id:'arrange.reference',title:'Align relative to selection or hoop',route:'arrange',target:'#alignTarget',requires:'selection',category:'Arrange',path:'Arrange › Alignment',aliases:'center centre align bounds'},
  ...[['penOnly','Pencil-only drawing','apple pencil stylus palm finger touch'],['penBrush','Drawing stitch style','brush satin fill running bean'],['penMin','Minimum pressure width','pressure thin satin'],['penMax','Maximum pressure width','pressure thick satin'],['penSmooth','Drawing smoothing','smooth stabilization stabilisation'],['keepDrawing','Keep drawing after a stroke','continuous drawing']].map(([target,title,aliases])=>({id:'draw.'+target,title,aliases,target:'#'+target,route:'draw',category:'Draw & edit',path:'Draw › Pencil & stroke controls'})),
];
