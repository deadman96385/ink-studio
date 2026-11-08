import {selectionReason} from './finder-catalog.mjs';

// Only openers and navigation live here. A finder result must never invoke an
// Apply, conversion, delete, reorder, save, or export-generation command.
export function createFinderRoutes(actions) {
  const routes=[];
  function route(key,title,category,path,root,requires='any',aliases='',extra={}) {
    routes.push({key,title,category,path,root,requires,aliases,open:()=>actions[key](),...extra});
  }
  route('layer','Layer settings','Stitches & thread','Selected object › Layer','#properties','object','object stitches density thread settings');
  route('arrange','Arrange selected artwork','Arrange','Arrange','#properties','selection','align center centre distribute stack move mirror rotate');
  route('protection','Lock / unlock selected artwork','Arrange','Arrange › Group, protect & stitch order','#properties',state=>!state.selection.length?'Select artwork first.':state.selection.some(l=>l.linkedHelper)?'Select the linked artwork to change its helpers’ protection.':'','protection locked unlock lock',{target:'#lockSelection, #unlockLinked',fields:false,open:()=>actions.arrange()});
  const linked=state=>state.selection.length===1&&(state.selection[0].link||state.selection[0].linkedHelper)?'':'Select one linked copy or attached helper.';
  route('linked-settings','Linked copy settings','Draw & edit','Selected copy › Linked settings','#properties',linked,'source inherit copy offset',{fields:false,open:()=>actions.layer()});
  route('linked-source','Linked source control','Draw & edit','Selected copy › Linked settings › Source','#properties',state=>linked(state)||(!state.selection[0].linkedHelper&&state.selection[0].locked?'Unlock the selected artwork first.':''),'source original linked copy',{target:'#selectLinkedSource, #editLinkedHelperSource',fields:false,open:()=>actions.layer()});
  route('linked-owner','Linked artwork control','Draw & edit','Selected helper › Linked artwork','#properties',state=>state.selection.length===1&&state.selection[0].linkedHelper?'':'Select a linked helper.','owner parent attached linked helper',{target:'#selectLinkedHelperOwner',fields:false,open:()=>actions.layer()});
  route('shape-tools','Shape operations','Draw & edit','Digitize › Shape operations','#properties','artwork','boolean shape tools',{target:'.operation-grid',fields:false,open:()=>actions.digitize()});
  route('fabric','Background & grid','Background','Background','#properties','any','fabric cloth canvas colour color snap grid padding');
  route('draw','Draw with Pencil','Draw & edit','Draw','#properties','any','pencil pen stylus pressure palm brush smoothing');
  route('digitize','All digitizing tools','Draw & edit','Digitize','#properties','any','shapes paths satin operations');
  route('lettering','Add embroidery lettering','Lettering','Text › Lettering','#letterDialog','any','text font words name multiline',{fields:false});
  route('edit-lettering','Edit text, font & spacing','Lettering','Selected lettering › Text','#letterDialog','text','words line letter gap font height');
  route('ttf','TTF / OTF satin lettering','Lettering','Text › TTF / OTF lettering','#ttfDialog',state=>state.selection.length===1&&state.selection[0].ttfLettering?selectionReason('object',state):'','custom font true type opentype outline font satin automatic');
  route('fonts','Font library & settings','Lettering','Lettering › Font library','#fontLibraryDialog','any','favorite installed fonts import zip kerning glyph license');
  route('font-samples','Generate font sample sheets','Lettering','Lettering › Sample sheets','#fontSamplesDialog','any','glyph sampler alphabet sew samples');
  route('font-workspace','Create & edit embroidery fonts','Lettering','Lettering › Font workspace','#fontWorkspaceDialog','any','glyph authoring baseline advances kerning source');
  route('batches','Batch lettering & export','Lettering','Lettering › Batch lettering','#batchDialog','any','names name list multiple text csv txt');
  route('nodes','Edit nodes, curves & stitch positions','Draw & edit','Selected object › Nodes & curves','#pathDialog','shape','reshape path points handles bezier entry exit satin rails rungs');
  route('new-path','Draw an editable path','Draw & edit','Digitize › Draw path','#pathDialog','any','new vector curve bezier');
  route('new-satin','Create a satin column','Draw & edit','Digitize › Satin column','#pathDialog','any','rails rungs two rail');
  route('curved-text','Lettering along a path','Lettering','Digitize › Lettering along a path','#curveDialog','any','arc curved circle bend text baseline');
  route('trace','Trace a reference image','Draw & edit','Selected image › Trace','#traceDialog','image','photo bitmap silhouette centerline colour color digitize');
  route('regions','Click-to-stitch image regions','Draw & edit','Selected image › Click to stitch','#clickStitchDialog','image','pick regions image automatic guided digitize');
  route('cross','Cross-stitch assistant','Stitches & thread','Digitize › Cross stitch','#crossDialog','any','pixel art raster image cross grid patterns');
  route('svg','Prepare SVG artwork','Draw & edit','Digitize › Prepare SVG','#svgPrepDialog','artwork','clip clipping mask opacity clone crop unlink needle points');
  route('advanced','Advanced stitch settings','Stitches & thread','Selected object › Advanced stitches','#advancedDialog','object','underlay locks ties tolerance random texture satin taper meander ripple',{fields:false});
  route('operations','Embroidery conversions & preparation','Convert & prepare','Digitize › Embroidery tools','#operationsDialog','artwork','satin redwork knockdown cleanup cutwork',{fields:false});
  route('helpers','Guides & patterns','Draw & edit','Digitize › Guides & patterns','#helpersDialog','any','guided fill embossing anchor line pattern guide');
  route('commands','Positions & commands','Stitches & thread','Digitize › Positions & commands','#commandsDialog','any','entry exit start end trim pause target origin frame out');
  route('satin-route','Auto-route satin columns','Stitches & thread','Digitize › Automatic routing','#routeDialog','artwork','optimize optimise travel jumps sewing order');
  route('running-route','Auto-route running stitches','Stitches & thread','Digitize › Automatic routing','#routeDialog','artwork','redwork running connections path order');
  route('optimize-sewing','Optimize sewing','Stitches & thread','Digitize › Stitch tools & routing › Optimize sewing','#sewingOptimizerDialog','any','optimize optimise routing travel trim cuts fewer cuts patch reusable recipe undersew covered details mushroom spots dots islands manual snips floats cleanup Wave');
  route('threads','Thread brands & colors','Stitches & thread','Threads › Brands & colors','#threadsDialog','artwork','palette colour color closest matching');
  route('thread-order','Thread order & color lists','Stitches & thread','Threads › Color lists','#colorworkDialog','any','threadlist txt col edr inf sequence');
  route('palette','Create a thread palette','Stitches & thread','Threads › Custom palette','#colorworkDialog','any','gpl palette import author brands');
  route('swatches','Generate test swatches','Check & inspect','Digitize › Test swatches','#swatchesDialog','any','compare density parameter fabric samples test sewing');
  route('patches','Patches & appliqué','Patches & scenes','Patches › Patch builder','#componentsDialog','any','badge border fabric applique shield circle crescent');
  route('merrow','Faux merrow border','Patches & scenes','Patches › Border style, or selected closed outline','#merrowDialog[open], #componentsDialog[open]','shape','gathered fan binding overlock merrow border edge');
  route('streamlines','Streamlines flow-field fill','Stitches & thread','Selected shape › Streamlines › Flow guides','#streamlinesDialog','shape','flow field curve guide organic fur leaf veins separation density');
  route('wave','Wave Fill','Stitches & thread','Selected shape › Wave Fill › Flow guides','#streamlinesDialog','shape','wave flow field curved bands botanical shared guides separation density');
  route('feather','Feathered edges','Stitches & thread','Selected shape › Feathered edges','#featherDialog','shape','feather ragged soft furry blend stitch effects balance hole edges');
  route('scene','Scene editor & motifs','Patches & scenes','Scene › Guide & motifs','#sceneDialog','any','botanical mushroom leaf foliage arrange curve flow preset');
  route('check','Check design & density','Check & inspect','Check › Design check','#checkDialog','any','problems warnings errors fraying thread breaks cuts tiny detail');
  route('density','Density map on canvas','Check & inspect','Check › Density map','#densityMapDialog','any','crowded stitches hotspot overlapping too dense');
  route('troubleshoot','Troubleshoot objects','Check & inspect','Check › Troubleshoot','#troubleshootDialog','any','errors warnings geometry problems repair');
  route('info','Object stitch information','Check & inspect','Check › Stitch information','#elementInfoDialog','any','counts statistics lengths jumps trims table tsv');
  route('order-numbers','Order numbers on canvas','Check & inspect','Arrange › Order numbers','#orderDisplayDialog','any','stacking sequence labels sewing order');
  route('stitch-plan','Stitch-plan overlays','Check & inspect','Check › Stitch-plan overlays','#stitchPlanDialog','any','compare snapshots actual stitches overlay editable');
  route('select-stitches','Select stitches by type','Arrange','Arrange › Select stitches','#selectStitchesDialog','any','find fill satin running underlay bean classification');
  route('stitch-order','Stitch in selection order','Arrange','Arrange › Sewing order','#stitchOrderDialog','any','reverse restack sequence order');
  route('preferences','This design’s embroidery preferences','Project & preferences','Project › Embroidery preferences › This design','#documentPreferences','any','document jump joining tiny stitch minimum satin rotation',{dialog:'#preferencesDialog'});
  route('defaults','New-design defaults & stitch cache','Project & preferences','Preferences › Defaults & cache','#defaultPreferences','any','new project settings cache memory storage',{dialog:'#preferencesDialog'});
  route('cleanup','Clean document settings','Project & preferences','Project › Clean document settings','#documentCleanupDialog','any','reset metadata origin frame out document preferences');
  route('projects','Projects & backups','Project & preferences','Projects','#projectsDialog','any','open saved projects restore backups copy');
  const needsPreview=state=>state.hasPreview?'':'Use Preview & export to generate the current stitches first.';
  route('preview','Preview, simulator & export settings','Check & inspect','Preview & export','#previewDialog',needsPreview,'playback stitch player png zip dpi repeat machine format');
  route('print','Print / PDF workspace','Check & inspect','Preview & export › Print / PDF','#printWorkspace',needsPreview,'paper page letter a4 actual size operator instructions logo');
  routes.find(r=>r.key==='stitch-order').requires=state=>selectionReason('artwork',state)||(state.selection.length>=2?'':'Select at least two objects in sewing order.');
  route('guide','Guide & help','Project & preferences','Guide','#helpDialog','any','help tutorial touch instructions',{fields:false});
  const shapeOps=[['union','Union shapes','merge combine silhouettes'],['difference','Cut hole','subtract knockout difference negative space remove inside'],['intersection','Intersection','keep overlap common area'],['exclusion','Exclude overlap','xor opposite union'],['combine','Combine paths','compound subpaths'],['division','Divide shape','split pieces cut'],['cut','Cut outline','split open running paths'],['break-apart','Break apart','separate compound paths'],['simplify','Simplify path','reduce nodes smooth path']];
  for(const [key,title,aliases] of shapeOps){
    const one=['break-apart','simplify'].includes(key),exact=['difference','division','cut'].includes(key);
    routes.push({key:'shape:'+key,title,aliases,category:'Draw & edit',path:'Digitize › Shape operations',root:'#properties',fields:false,target:'[data-vector="'+key+'"]',requires:state=>{
      if(one)return selectionReason('shape',state);
      if(exact)return selectionReason('pair',state);
      return selectionReason('artwork',state)||(state.selection.length>=2?'':'Select at least two shapes.');
    },open:()=>actions.digitize()});
  }
  return routes;
}
