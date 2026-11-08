"""Canvas snapshots made by the installed Ink/Stitch stitch-plan renderer.

Snapshots live outside sewing layers. Their SVGs are isolated image resources;
editable stitches are a separate, explicit conversion of the saved source.
"""
import copy,hashlib,json,re,tempfile,uuid
from pathlib import Path
from lxml import etree as ET
import svgprep
from cutwork import prepare_cutwork

MODES=('simple','realistic-vector','realistic-300','realistic-600')
MAX_PLANS=6

def folder(s):
    path=s.DATA/'stitchplans';path.mkdir(exist_ok=True);return path

def load(key,s):
    return json.loads((folder(s)/(s.safe_id(key)+'.json')).read_text())

def public(asset):
    return {k:asset[k] for k in ('key','bounds','options')}

def selection(project,ids):
    result=copy.deepcopy(project)
    if ids is None:return result
    if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)):raise ValueError('Select visible artwork for the stitch plan.')
    targets={l['id'] for l in result['layers'] if l['id'] in ids and l.get('visible',True) and l.get('type')!='image' and l.get('role','artwork')=='artwork'}
    if len(targets)!=len(ids):raise ValueError('Select visible artwork for the stitch plan.')
    for layer in result['layers']:
        if layer['id'] not in targets and layer.get('helperTarget') not in targets:layer['visible']=False
    return result

def validate_svg(raw,s):
    # Backup files can come from outside the studio. Allow passive SVG drawing
    # and lighting filters, never scripts, external resources or CSS imports.
    root=s.xml(raw)
    allowed=set('svg defs g path rect circle ellipse polygon polyline line symbol use marker image linearGradient radialGradient stop filter feComposite feDistantLight feGaussianBlur feSpecularLighting feBlend feColorMatrix clipPath mask title desc'.split())
    if root.tag!='{'+s.SVG+'}svg':raise ValueError('Invalid stitch-plan SVG.')
    for e in root.iter():
        if not isinstance(e.tag,str) or ET.QName(e).namespace!=s.SVG or ET.QName(e).localname not in allowed:raise ValueError('Unsupported stitch-plan SVG element.')
        for name,value in e.attrib.items():
            local=ET.QName(name).localname.lower()
            if local.startswith('on') or local in ('base','src') or '@' in value or '\\' in value:raise ValueError('Unsupported stitch-plan SVG attribute.')
            if local=='href' and not (re.fullmatch(r'#[\w.:-]+',value) or (ET.QName(e).localname=='image' and re.fullmatch(r'data:image/png;base64,[A-Za-z0-9+/=\s]+',value))):raise ValueError('Stitch plans must use embedded resources.')
            if re.search(r'url\s*\((?!#[\w.:-]+\))',value,re.I) or re.search(r'expression\s*\(',value,re.I):raise ValueError('Stitch plans cannot load external styles.')
    return root

def generate(data,s):
    project=selection(data.get('project'),data.get('ids'))
    options=data.get('options',{});defaults={'mode':'simple','needlePoints':False,'commands':False,'jumps':True}
    if not isinstance(options,dict) or set(options)-set(defaults):raise ValueError('Unknown stitch-plan option.')
    options={**defaults,**options}
    if options['mode'] not in MODES or any(type(options[k]) is not bool for k in ('needlePoints','commands','jumps')):raise ValueError('Choose valid stitch-plan settings.')
    source=s.build_svg(project,sewing=True)
    rendered_source,_=prepare_cutwork(source,s)
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-stitch-plan-') as tmp:
        path=Path(tmp)/'source.svg';path.write_bytes(rendered_source)
        out=s.run([s.ENGINE,'--extension=stitch_plan_preview','--render-mode='+options['mode'],
                   '--move-to-side=false','--layer-visibility=unchanged','--ignore-layer=false','--insensitive=true',
                   '--needle-points='+str(options['needlePoints']),'--visual-commands='+str(options['commands']),
                   '--render-jumps='+str(options['jumps']),str(path)],240,headless=True)
        if len(out)>s.MAX_BODY:raise ValueError('This vector preview is too large. Choose a 300 dpi preview or a smaller selection.')
        rendered=s.xml(out);plan=rendered.find(".//*[@id='__inkstitch_stitch_plan__']")
        if plan is None:raise ValueError('Ink/Stitch did not create a stitch plan.')
        root=s.svg_root()
        for defs in rendered.findall('{'+s.SVG+'}defs'):root.append(copy.deepcopy(defs))
        root.append(copy.deepcopy(plan));path.write_bytes(ET.tostring(root))
        x,y,w,h=s.bounds(path)
        # Include marker/filter extents and preserve original document placement.
        margin=1;x-=margin;y-=margin;w+=2*margin;h+=2*margin
        root.set('viewBox',f'{x} {y} {w} {h}');root.set('width',f'{w}mm');root.set('height',f'{h}mm')
        svg=ET.tostring(root,encoding='unicode');validate_svg(svg.encode(),s)
    if len(svg.encode())+len(source)>8*1024*1024:raise ValueError('This snapshot exceeds 8 MB. Use a raster preview or a smaller selection.')
    key=hashlib.sha256((svg+source.decode()).encode()).hexdigest()
    asset={'key':key,'svg':svg,'source':source.decode(),'bounds':[x,y,w,h],'options':options}
    s.write_atomic(folder(s)/(key+'.json'),asset)
    return public(asset)

def editable(data,s):
    asset=load(data.get('key'),s)
    raw=svgprep.needle_plan(asset['source'].encode(),s)
    imported=s.import_svg({'svg':raw.decode(),'name':'Editable stitch plan'})
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-plan-edit-') as tmp:
        path=Path(tmp)/'plan.svg';path.write_bytes(raw);x,y,w,h=s.bounds(path)
    if w>100.05 or h>100.05:raise ValueError('The editable stitch plan exceeds the PP1 hoop.')
    layer={'id':uuid.uuid4().hex,'name':'Editable stitch plan','type':'import','asset':imported['key'],
           'x':x,'y':y,'width':imported['width'],'height':imported['height'],'rotation':0,'visible':True,
           'color':'#203f38','stitch':'original','recolor':False}
    return {'asset':imported,'layer':layer}

def plans(project,s):
    rows=project.get('stitchPlans',[])
    if not isinstance(rows,list) or len(rows)>MAX_PLANS:raise ValueError('Keep up to six stitch-plan snapshots in a project.')
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Invalid stitch-plan snapshot.')
        s.safe_id(row.get('id'));s.safe_id(row.get('key'))
        for k in ('x','y'):row[k]=s.number(row.get(k,0),-1000,1000,'Stitch-plan position')
    return rows

def embed(project,s):
    return [load(key,s) for key in {p['key'] for p in plans(project,s)}]

def restore(project,s):
    rows=plans(project,s);embedded=project.pop('embeddedStitchPlans',[])
    if not isinstance(embedded,list) or len(embedded)>MAX_PLANS:raise ValueError('Invalid stitch-plan backup.')
    mapping={}
    for a in embedded:
        if not isinstance(a,dict):raise ValueError('Invalid stitch-plan asset.')
        svg=str(a.get('svg',''));root=validate_svg(svg.encode(),s)
        # Saved engine source uses the same restricted SVG dialect as imports.
        source=str(a.get('source',''));s.sanitize_svg(source.encode(),max_shapes=20000)
        bounds=a.get('bounds',[])
        if not isinstance(bounds,list) or len(bounds)!=4:raise ValueError('Invalid stitch-plan bounds.')
        bounds=[s.number(n,.000001 if i>1 else -10000,10000,'Stitch-plan bounds') for i,n in enumerate(bounds)]
        key=hashlib.sha256((svg+source).encode()).hexdigest();mapping[s.safe_id(a.get('key'))]=key
        s.write_atomic(folder(s)/(key+'.json'),{'key':key,'svg':ET.tostring(root,encoding='unicode'),'source':source,'bounds':bounds,'options':a.get('options',{})})
    for row in rows:
        row['key']=mapping.get(row['key'],row['key'])
        if not (folder(s)/(row['key']+'.json')).exists():raise ValueError('A stitch-plan snapshot is missing from this backup.')
