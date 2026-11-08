"""Read-only stitch selection using the installed Ink/Stitch classifier."""
import copy,io,re,json,tempfile,uuid
import studio_runtime
from pathlib import Path
from lxml import etree as ET
import inkex
from digitizing import geometry,SVG,STITCH
from limits import MAX_LAYERS

TYPES=[('running-stitch','Running / bean stitches','Running'),('ripples','Ripples','Running'),('zigzag','Zigzag stitches','Running'),('manual','Manual needle points','Running'),
       ('satin','Satin columns','Satin'),('e','E stitch','Satin'),('s','S stitch','Satin'),('satin-zigzag','Satin zigzag','Satin'),
       ('tatami-fill','Tatami','Fills'),('circular-fill','Circular','Fills'),('contour-fill','Contour','Fills'),('guided-fill','Guided','Fills'),
       ('linear-gradient-fill','Gradient','Fills'),('meander-fill','Meander / stippling','Fills'),('tartan-fill','Tartan','Fills'),('legacy-fill','Legacy','Fills'),('cross-fill','Cross stitch','Fills'),('clone','Linked copies','Linked copies')]
FILTERS={'runningCondition':['all','autorun-top','autorun-underpath','autosatin-underpath'],'satinUnderlay':['all','no','center','contour','zigzag'],'rungCount':['all','zero','two'],'fillUnderlay':['all','yes','no']}

def layer_id(element,layers):
    for a in element.iterancestors():
        m=re.fullmatch(r'layer-(\d+)',a.get('id',''))
        if m and int(m[1])<len(layers):return layers[int(m[1])]['id']

def query(data,s):
    project=data.get('project');options=data.get('options',{})
    if not isinstance(project,dict) or project.get('version')!=1 or not isinstance(project.get('layers'),list) or len(project['layers'])>MAX_LAYERS:raise ValueError('Choose a valid design.')
    if not isinstance(options,dict) or set(options)-{'types','runningCondition','beanRepeats','satinUnderlay','rungCount','fillUnderlay','scopeIds','includeLocked','exposePaths'}:raise ValueError('Unknown selection option.')
    types=options.get('types',[])
    if not isinstance(types,list) or not types or any(t not in {k for k,_,_ in TYPES} for t in types):raise ValueError('Choose at least one stitch type.')
    for key,values in FILTERS.items():
        if options.get(key,'all') not in values:raise ValueError('Check the selection filters.')
    repeats=options.get('beanRepeats','any')
    if not isinstance(repeats,str) or (repeats!='any' and not re.fullmatch(r'\d{1,3}(?: \d{1,3}){0,19}',repeats)):raise ValueError('Bean repeats must be Any, or whole numbers separated by spaces.')
    for key in ('includeLocked','exposePaths'):
        if key in options and type(options[key]) is not bool:raise ValueError('Invalid selection option.')
    scope=options.get('scopeIds');all_ids={l.get('id') for l in project['layers']}
    if scope is not None and (not isinstance(scope,list) or any(id not in all_ids for id in scope)):raise ValueError('The selection changed. Open the selector again.')
    from linked import resolve
    materialized=resolve(project,s)
    candidates=[l for l in materialized['layers'] if l.get('role','artwork')=='artwork' and l.get('type')!='image' and l.get('visible',True) and (options.get('includeLocked') or not l.get('locked')) and (scope is None or l['id'] in scope)]
    helpers=[h for h in materialized['layers'] if h.get('helperTarget') in {l['id'] for l in candidates}]
    if not candidates:return {'matches':[],'selectedIds':[],'replacements':{},'removeIds':[]}
    source=s.build_svg({**materialized,'layers':candidates+helpers})
    doc=inkex.load_svg(io.BytesIO(source)).getroot()
    for i,e in enumerate(doc.iter()):
        if isinstance(e,inkex.ShapeElement) and not e.get('id'):e.set('id','selection-path-'+str(i))
    source=ET.tostring(doc)
    paths={e.get('id'):layer_id(e,candidates) for e,_,_ in geometry(source,allow_effects=True) if not e.get('{http://www.inkscape.org/namespaces/inkscape}connection-start')}
    for e in doc.xpath('//svg:use'):
        if not str(e.get('href',e.get('{http://www.w3.org/1999/xlink}href',''))).startswith('#inkstitch_'):paths[e.get('id')]=layer_id(e,candidates)
    paths={k:v for k,v in paths.items() if v}
    original_source=source;matched=set()
    if 'cross-fill' in types:
        for e,_,style in geometry(source,allow_effects=True):
            underlay=str(e.get('{'+STITCH+'}fill_underlay','true')).lower() not in ('false','0')
            if options.get('fillUnderlay','all') not in ('all','yes' if underlay else 'no'):continue
            if str(style.get('fill','black'))!='none' and e.get('{'+STITCH+'}fill_method')=='cross_stitch':matched.add(e.get('id'))
    # "Any" adds a useful native convenience without approximating the engine's
    # classification: normalize only this query copy's repeat count to zero.
    for e in doc.iter():
        if repeats=='any' and e.get('id') in paths:e.set('{'+STITCH+'}bean_stitch_repeats','0')
        # Native SVG prefixes imported IDs. Retain the legacy routing meaning
        # for the engine selector without changing saved/exported artwork.
        legacy=re.sub(r'^(?:l\d+-)+','',e.get('id',''))
        if not e.get('{'+STITCH+'}path_type'):
            for prefix,kind in [('autosatinrun','satin-underpath'),('underpath','autorun-underpath'),('autorun','autorun-top'),('redwork','redwork-top')]:
                if legacy.startswith(prefix):e.set('{'+STITCH+'}path_type',kind);break
    engine_types=[t for t in types if t!='cross-fill']
    if engine_types:
        with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='select-stitches-') as tmp:
            root=Path(tmp);p=root/'query.svg';p.write_bytes(ET.tostring(doc))
            # Call the installed classifier itself; capture before its desktop
            # IPC stage. The same worker runs on Windows and Linux.
            args=studio_runtime.worker_command('--native-select')
            args+=['--select-'+t+'=True' for t in engine_types]
            args+=['--running-stitch-condition='+options.get('runningCondition','all'),'--bean-stitch-repeats='+('0' if repeats=='any' else repeats),'--satin-underlay='+options.get('satinUnderlay','all'),'--rung-count='+options.get('rungCount','all'),'--fill-underlay='+options.get('fillUnderlay','all')]
            result=json.loads(s.run(args+[str(p)],headless=True))
            matched.update(result['ids'])
    matching_layers={paths[id] for id in matched if id in paths}
    if 'clone' in types:matching_layers.update(l['id'] for l in candidates if l.get('link'))
    matches=[]
    for layer in candidates:
        if layer['id'] not in matching_layers:continue
        own={id for id,target in paths.items() if target==layer['id']};hits=own&matched
        if 'clone' in types and layer.get('link'):hits=own;matched.update(own)
        matches.append({'id':layer['id'],'name':layer.get('name','Layer'),'matchedPaths':len(hits),'totalPaths':len(own),'locked':bool(layer.get('locked'))})
    result={'matches':matches,'selectedIds':[m['id'] for m in matches],'replacements':{},'removeIds':[]}
    if not options.get('exposePaths') or not matches:return result
    if any(l.get('locked') for l in candidates if l['id'] in matching_layers):raise ValueError('Unlock matching layers before exposing their paths. Selecting whole layers can include locked artwork.')
    if any(h.get('locked') for h in helpers if h.get('helperTarget') in matching_layers):raise ValueError('Unlock attached helpers before exposing the matching artwork.')
    from operations import editable_output
    expose_doc=s.xml(original_source)
    for i,l in enumerate(candidates):
        if l['id'] in matching_layers:continue
        for group in expose_doc.xpath('//*[@id=$id]',id='layer-'+str(i)):group.getparent().remove(group)
    if any(e.get('clip-path') or e.get('mask') or re.search(r'(?:clip-path|mask)\s*:',e.get('style','')) for e in expose_doc.iter()):
        raise ValueError('Apply clipping or masking to path geometry before exposing these paths. Whole-layer selection preserves the original clipping.')
    output=editable_output(ET.tostring(expose_doc),s,'Selected path',candidates,element_ids=True)
    by_source={l['id']:[] for l in candidates}
    for l in output:
        if l.get('_sourceId') in by_source:by_source[l['_sourceId']].append(l)
    selection=[]
    for source_layer in candidates:
        id=source_layer['id']
        if id not in matching_layers:continue
        parts=by_source[id]
        if not parts:raise ValueError('Separate SVG clones before exposing individual stitched paths.')
        # A simple native path is already individually editable.
        if len(parts)==1 and source_layer['type'] not in ('text','import'):
            selection.append(id);continue
        group=source_layer.get('groupId') or uuid.uuid4().hex;part_ids={l['id'] for l in parts}
        attached=[l for l in output if l.get('helperTarget') in part_ids]
        for i,l in enumerate(parts):
            l['name']=source_layer.get('name','Layer')+f' · path {i+1}';l['groupId']=group;l['background']=bool(source_layer.get('background'))
            if l.pop('_elementId',None) in matched:selection.append(l['id'])
            l.pop('_sourceId',None)
        for h in helpers:
            if h.get('helperTarget')!=id or h.get('visible',True):continue
            for l in parts:
                hcopy=copy.deepcopy(h);hcopy.update(id=uuid.uuid4().hex,helperTarget=l['id']);hcopy.pop('linkedHelper',None);attached.append(hcopy)
        result['replacements'][id]=parts+attached
        result['removeIds'] += [h['id'] for h in helpers if h.get('helperTarget')==id]
    result['selectedIds']=selection
    count=len(project['layers'])-len(result['replacements'])-len(result['removeIds'])+sum(map(len,result['replacements'].values()))
    if count>MAX_LAYERS:raise ValueError(f'Exposing these paths exceeds {MAX_LAYERS} layers. Select a smaller part of the design.')
    return result
