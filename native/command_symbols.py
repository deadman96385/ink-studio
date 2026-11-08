"""Installed command artwork, presentation, and non-sewing command helpers."""
import studio_runtime
import copy,io,math,tempfile
from functools import lru_cache
from pathlib import Path
from lxml import etree as ET
SVG='http://www.w3.org/2000/svg';INK='http://www.inkscape.org/namespaces/inkscape';XLINK='http://www.w3.org/1999/xlink'
NAMES=('starting_point','ending_point','target_point','autoroute_start','autoroute_end','stop','trim','ignore_object','satin_cut_point','ignore_layer','origin','stop_position')
EXTRA={'trimCommand':'trim','stopCommand':'stop','ignoreObject':'ignore_object'}

def name(value):
    value=value.lstrip('#')
    return next((n for n in NAMES if value=='inkstitch_'+n or value.startswith('inkstitch_'+n+'-')),None)

def settings(project):
    raw=project.get('commandDisplay',{})
    if not isinstance(raw,dict) or set(raw)-{'visible','size','connectors'}:raise ValueError('Invalid command symbol display settings.')
    result={'visible':False,'size':100,'connectors':True,**raw}
    if any(type(result[k]) is not bool for k in ('visible','connectors')) or type(result['size']) not in (int,float) or not math.isfinite(result['size']) or not 0<=result['size']<=400:raise ValueError('Command symbol size must be from 0 to 400 percent.')
    return result

def style(e,key,value):
    values={k.strip():v.strip() for item in e.get('style','').split(';') if ':' in item for k,v in [item.split(':',1)]}
    if value is None:values.pop(key,None)
    else:values[key]=value
    e.set('style',';'.join(k+':'+v for k,v in values.items()))

def is_use(e):return e.tag=='{'+SVG+'}use' and name(e.get('{'+XLINK+'}href',e.get('href','')))
def is_connector(e):return e.get('{'+INK+'}connection-start') or e.get('{'+INK+'}connection-end')

def hide(root):
    for e in root.iter():
        if is_use(e) or is_connector(e):style(e,'display','none')

def hide_ignored(root):
    by_id={e.get('id'):e for e in root.iter() if e.get('id')}
    for use in root.iter('{'+SVG+'}use'):
        command=name(use.get('{'+XLINK+'}href',use.get('href','')))
        if command=='ignore_layer':
            # The released engine excludes every containing Inkscape layer.
            for layer in use.iterancestors():
                if layer.get('{'+INK+'}groupmode')=='layer':style(layer,'display','none')
        if command=='ignore_object':
            for connector in root.iter():
                a,b=[connector.get('{'+INK+'}connection-'+side,'') for side in ('start','end')]
                if '#'+str(use.get('id')) not in (a,b):continue
                target=by_id.get((b if a=='#'+str(use.get('id')) else a).lstrip('#'))
                if target is not None:style(target,'display','none')

@lru_cache(maxsize=12)
def symbol(command):
    if command not in NAMES:raise ValueError('Unknown command symbol.')
    root=ET.parse(str(studio_runtime.resource('symbols','inkstitch.svg'))).getroot()
    result=copy.deepcopy(root.find(".//*[@id='inkstitch_"+command+"']"))
    if result is None:raise ValueError('The installed command symbol is missing.')
    # Child IDs are artwork implementation details and may collide between
    # several independently imported copies of the same symbol.
    for child in result.iterdescendants():child.attrib.pop('id',None)
    return ET.tostring(result)

def icon(command):
    root=ET.Element('{'+SVG+'}svg',nsmap={None:SVG},viewBox='-12 -12 24 24')
    group=ET.SubElement(root,'{'+SVG+'}g')
    for child in ET.fromstring(symbol(command)):group.append(copy.deepcopy(child))
    return ET.tostring(root)

def visible_svg(raw,project):
    config=settings(project)
    import marker_symbols
    marker_symbols.settings(project)
    if not config['visible'] and 'markerDisplay' not in project:return raw
    from digitizing import inkex
    # Inkex lazily rewrites parsed transform attributes at six-digit precision.
    # Use it only for calculations; serialize the untouched lxml artwork tree.
    root=ET.fromstring(raw)
    marker_symbols.present(root,project)
    if not config['visible']:return ET.tostring(root,xml_declaration=True,encoding='UTF-8')
    for e in list(root.iter('{'+SVG+'}symbol')):
        command=name(e.get('id',''))
        if not command:continue
        artwork=ET.fromstring(symbol(command))
        for child in list(e):e.remove(child)
        for child in artwork:e.append(copy.deepcopy(child))
        e.set('transform',f'scale({.25*config["size"]/100})');style(e,'opacity','.7')
    for e in list(root.iter()):
        if not is_use(e):continue
        parent=inkex.Transform()
        for ancestor in reversed(list(e.iterancestors())):parent=parent @ inkex.Transform(ancestor.get('transform',''))
        x,y=float(e.get('x',0)),float(e.get('y',0));world=(parent @ inkex.Transform(e.get('transform',''))).apply_to_point((x,y))
        # Keep icons upright at a consistent document size. Their anchor point
        # remains exactly where the engine reads the command position.
        matrix=-parent @ inkex.Transform(f'translate({world.x-x},{world.y-y})')
        # Inkex's default transform string rounds to six significant digits.
        # Command anchors affect stitches, so retain full numeric precision.
        e.set('transform','matrix('+','.join(format(v,'.17g') for v in (matrix.a,matrix.b,matrix.c,matrix.d,matrix.e,matrix.f))+')')
        style(e,'display',None)
        for parent in e.iterancestors():
            if parent.tag!='{'+SVG+'}g':continue
            if parent.get('id','').startswith('command_group') or parent.get('data-native-commands') or all(is_use(c) or is_connector(c) for c in parent):style(parent,'display',None)
    for e in root.iter():
        if is_connector(e):style(e,'display',None if config['connectors'] else 'none')
    return ET.tostring(root,xml_declaration=True,encoding='UTF-8')

def place(data,s):
    from digitizing import POSITION_COMMANDS,inkex
    layers=data.get('layers',[data.get('layer')]);key=data.get('key');corner=data.get('position')
    if not isinstance(layers,list) or not 1<=len(layers)<=s.MAX_LAYERS or any(not isinstance(l,dict) or l.get('locked') or l.get('link') or l.get('type')=='image' or l.get('role','artwork')!='artwork' for l in layers):raise ValueError('Choose unlocked artwork. Edit a linked copy’s source or detach it first.')
    if len({l.get('id') for l in layers})!=len(layers):raise ValueError('Command targets must have unique layer IDs.')
    if key not in {*POSITION_COMMANDS,'ignoreLayer'} or corner not in ('random','top_left','top_right','bottom_left','bottom_right'):raise ValueError('Choose a command and its placement.')
    command=POSITION_COMMANDS.get(key,'ignore_object');sources=copy.deepcopy(layers)
    for source in sources:source.pop('ignoreLayer',None);source.pop('ignoreObject',None);source['visible']=True
    raw=s.build_svg({'version':1,'layers':sources});before=s.xml(raw)
    old={e.get('id') for e in before.iter('{'+SVG+'}use')}
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='command-placement-') as tmp:
        path=Path(tmp)/'source.svg';path.write_bytes(raw)
        result=s.run([s.ENGINE,'--extension=object_commands',*['--id=layer-'+str(i) for i in range(len(layers))],'--'+command+'=True','--command_position='+corner,str(path)],headless=True)
    doc=inkex.load_svg(io.BytesIO(result)).getroot()
    uses=[e for e in doc.iter('{'+SVG+'}use') if e.get('id') not in old and name(e.get('{'+XLINK+'}href',''))==command]
    positions={}
    for i,layer in enumerate(layers):
        matches=[u for u in uses if any(a.get('id')=='layer-'+str(i) for a in u.iterancestors())]
        if not matches:raise ValueError('No eligible path was found in '+str(layer.get('name','a selected layer'))+'. Clear imported ignore commands or separate the artwork first.')
        use=matches[-1] if key in ('exit','routeEnd','trimCommand','stopCommand') else matches[0]
        point=use.composed_transform().apply_to_point((float(use.get('x',0)),float(use.get('y',0))))
        positions[layer['id']]=[float(point.x),float(point.y)]
    return {'positions':positions,**({'position':positions[layers[0]['id']]} if len(layers)==1 else {})}
