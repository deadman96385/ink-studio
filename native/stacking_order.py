"""Read-only path-order labels from the installed desktop extension."""
import copy,hashlib,tempfile,uuid
from pathlib import Path
from lxml import etree as ET

def settings(project,s):
    value=project.get('orderDisplay')
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('Invalid sewing-order display.')
    size=s.number(value.get('size',4),0,100,'Order label size')
    if size!=int(size):raise ValueError('Order label size must be a whole number.')
    if type(value.get('visible',True)) is not bool:raise ValueError('Invalid sewing-order visibility.')
    points=value.get('points',[])
    if not isinstance(points,list) or len(points)>20000:raise ValueError('The order overlay exceeds 20,000 paths.')
    for i,point in enumerate(points):
        if not isinstance(point,list) or len(point)!=3 or point[2]!=i+1:raise ValueError('Invalid sewing-order label.')
        for coordinate in point[:2]:s.number(coordinate,-100000,100000,'Order label position')
    ids=value.get('ids')
    if ids is not None and (not isinstance(ids,list) or any(not isinstance(id,str) for id in ids)):raise ValueError('Invalid sewing-order scope.')
    if not isinstance(value.get('signature',''),str) or len(value.get('signature',''))>100:raise ValueError('Invalid sewing-order snapshot.')
    return value

def generate(data,s,download=False):
    from linked import resolve
    # Resolving linked helpers can remove/reappend helper rows. Match the
    # resulting layer indices used by build_svg, not the incoming list indices.
    project=resolve(data.get('project'),s);source=s.build_svg(project)
    size=s.number(data.get('size',4),0,100,'Order label size')
    if int(size)!=size:raise ValueError('Order label size must be a whole number.')
    ids=data.get('ids');selected=[]
    if ids is not None:
        if not isinstance(ids,list) or not ids or any(not isinstance(id,str) for id in ids) or len(ids)!=len(set(ids)):raise ValueError('Select visible artwork to number.')
        eligible={l['id']:i for i,l in enumerate(project['layers']) if l.get('visible',True) and l.get('role','artwork')=='artwork' and l.get('type')!='image'}
        if any(id not in eligible for id in ids):raise ValueError('Select visible artwork to number.')
        selected=['--id=layer-'+str(eligible[id]) for id in ids]
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-order-') as tmp:
        path=Path(tmp)/'design.svg';path.write_bytes(source)
        raw=s.run([s.ENGINE,'--extension=display_stacking_order','--font_size='+str(int(size)),*selected,str(path)],180,headless=True)
    root=s.xml(raw);group=root.find(".//*[@id='__inkstitch_stacking_order__']")
    if group is None:raise ValueError('Ink/Stitch did not return sewing-order labels.')
    points=[]
    for text in group.iter('{'+s.SVG+'}text'):
        value=''.join(text.itertext()).strip()
        if not value.isdigit():continue
        points.append([float(text.get('x')),float(text.get('y')),int(value)])
        text.set('style',text.get('style','')+';fill:#142d27;stroke:#fffdf5;stroke-width:0.45;stroke-linejoin:round;paint-order:stroke fill;font-family:sans-serif;font-weight:bold')
    if not points:raise ValueError('No visible embroidery paths to number. Check layer visibility and exclusions.')
    result={'points':points,'size':int(size),'ids':ids,'sourceHash':hashlib.sha256(source).hexdigest()}
    settings({'orderDisplay':result},s)
    if download:
        # Reading composed transforms can make Inkex reserialize artwork at
        # reduced precision. Retain the original tree and add only the engine's
        # annotation layer and missing command definitions.
        original=s.xml(source)
        for previous in original.findall(".//*[@id='__inkstitch_stacking_order__']"):previous.getparent().remove(previous)
        existing={e.get('id') for e in original.iter() if e.get('id')}
        definitions=ET.SubElement(original,'{'+s.SVG+'}defs')
        for defs in root.findall('{'+s.SVG+'}defs'):
            for child in defs:
                if child.get('id') and child.get('id') not in existing:
                    definitions.append(copy.deepcopy(child));existing.add(child.get('id'))
        if not len(definitions):original.remove(definitions)
        original.append(copy.deepcopy(group));root=original
        # The desktop extension adds ignore_layer. Hide its command icon while
        # retaining the command itself so these text labels never sew.
        s.command_symbols.hide(root)
        filename='sewing-order-'+uuid.uuid4().hex+'.svg'
        (s.DATA/'exports'/filename).write_bytes(ET.tostring(root,xml_declaration=True,encoding='UTF-8'))
        result['url']='/files/'+filename
    return result
