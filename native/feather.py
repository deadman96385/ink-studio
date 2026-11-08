"""Editable feather recipes applied to the installed engine's tagged top stitches."""
import studio_runtime
import copy,hashlib,json,math,tempfile
from pathlib import Path
from lxml import etree as ET
from shapely.geometry import LineString
from shapely.ops import unary_union
from digitizing import geometry,inkex,path_contours
from applique import flattened

FILL_METHODS=('tatami_fill','legacy_fill','guided_fill','streamline_fill','wave_fill')
KEYS=('type','x','y','width','height','radius','rotation','flipX','flipY','contours','points','closed','color','stitch','fillMethod',
      'spacing','stitchLength','angle','underlay','underlaySpacing','underlayInset','pullCompensation','satinMaxLength',
      'satinCenter','satinContour','satinZigzag','nearestStart','nearestEnd','originalParams','originalFill','originalStroke',
      'borderEnabled','borderColor','borderStitch','borderWidth','borderSpacing','borderLength','advanced','streamlines','feather',
      'entry','exit','routeStart','routeEnd','satinCut','trimAfter','stopAfter','trimCommand','stopCommand','ignoreObject','ignoreLayer','smallFillFallback')

def eligible(layer):
    if layer.get('type') not in ('path','rectangle','ellipse') or layer.get('role','artwork')!='artwork' or layer.get('stitch')=='original' and layer.get('merrow'):return False
    satin=layer.get('stitch')=='satin' or layer.get('stitch')=='original' and str(layer.get('originalParams',{}).get('satin_column','')).lower()=='true'
    if satin and layer.get('multicolorSatin'):return False
    return satin or layer.get('stitch')=='fill' and layer.get('fillMethod','tatami_fill') in FILL_METHODS

def active(layer):return eligible(layer) and isinstance(layer.get('feather'),dict) and layer['feather'].get('enabled',True) and layer['feather'].get('raggedness',.5)>0

def settings(value,s,seed='feather'):
    if not isinstance(value,dict):raise ValueError('Enter feathered-edge settings.')
    for key in ('enabled','includeHoles'):
        if key in value and not isinstance(value[key],bool):raise ValueError('Choose a supported feathered-edge option.')
    out={'enabled':value.get('enabled',True),'raggedness':s.number(value.get('raggedness',.5),0,2,'Feather raggedness'),
         'balance':s.number(value.get('balance',0),-100,100,'Edge balance'),'includeHoles':value.get('includeHoles',False),
         'seed':value.get('seed',seed)}
    if not isinstance(out['seed'],str) or not 1<=len(out['seed'])<=80:raise ValueError('Use a texture seed of 1–80 characters.')
    return out

def key(layer):return {k:layer.get(k) for k in KEYS}

def render(root,group,layer,s):
    if not active(layer) or layer.get('ignoreObject') or layer.get('ignoreLayer'):return
    from components import path_polygon,world_path
    from footprints import envelope,is_satin
    params=settings(layer['feather'],s,layer['id'])
    isolated=s.svg_root()
    for child in root:
        if ET.QName(child).localname in ('defs','metadata'):isolated.append(copy.deepcopy(child))
    isolated.append(copy.deepcopy(group));raw=ET.tostring(isolated)
    items=geometry(raw);satin=is_satin(layer)
    if satin:
        mask=unary_union([envelope({**layer,'feather':None},path,s) for _,path,_ in items])
        contours=path_contours(items[0][1]);rails=[flattened(c,.02) for c in contours[:2]]
    elif layer.get('fillMethod') in ('streamline_fill','wave_fill'):
        mask=path_polygon(world_path({**layer,'feather':None},s));rails=[]
    else:
        mask=unary_union([path_polygon(path) for _,path,style in items if str(style.get('fill','black'))!='none']);rails=[]
    if mask.is_empty:raise ValueError('This shape has no boundary to feather.')
    angle=math.radians(layer.get('angle',45));axis=[math.cos(angle),-math.sin(angle)]
    if layer.get('fillMethod') in ('streamline_fill','wave_fill'):
        guide=layer.get('streamlines',{}).get('guides',[{'points':[[0,0],[1,0]]}])[0]['points']
        a,b=guide[0],guide[-1];rotation=math.radians(layer.get('rotation',0))
        dx=(b[0]-a[0])*layer['width']*(-1 if layer.get('flipX') else 1);dy=(b[1]-a[1])*layer['height']*(-1 if layer.get('flipY') else 1)
        axis=[dx*math.cos(rotation)-dy*math.sin(rotation),dx*math.sin(rotation)+dy*math.cos(rotation)]
    config={'settings':params,'mask':mask.wkt,'rails':rails,'axis':axis,'compensation':layer.get('pullCompensation',0)}
    digest=hashlib.sha256(b'feather-engine-v2'+raw+json.dumps(config,sort_keys=True).encode()).hexdigest()
    cache=s.DATA/'cache'/('feather-'+digest+'.json')
    if cache.exists():data=json.loads(cache.read_text())
    else:
        with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-feather-') as tmp:
            path=Path(tmp)/'source.svg';path.write_bytes(raw);configuration=Path(tmp)/'settings.json'
            configuration.write_text(json.dumps({**config,'source':str(path)}))
            result=s.run(studio_runtime.worker_command('--native-feather',str(configuration)),240,headless=True)
            data=json.loads(result)
        if data.get('error'):raise ValueError('Could not feather this shape: '+data['error'])
        s.write_atomic(cache,data)
    # The engine returned physical world coordinates, including all locks and
    # underlay. Freeze only this layer's needle paths; its project keeps rails,
    # fill boundary, guides and settings for subsequent edits and regeneration.
    for child in list(group):group.remove(child)
    group.attrib.pop('transform',None);group.set('data-feather-edges',str(data['stats']['edges']))
    group.set('data-feather-extension',str(data['stats']['maxExtension']))
    last=None;count=0
    for block in data['blocks']:
        points=[]
        def finish():
            nonlocal points,last,count
            if not points:return
            if len(points)==1:points.append(points[0])
            for i in range(0,len(points)-1,1799):
                node=ET.SubElement(group,'{'+s.SVG+'}path',d='M'+' L'.join(f'{x:.8f},{y:.8f}' for x,y in points[i:i+1800]),style='fill:none;stroke:'+s.color(block['color'])+';stroke-width:.15')
                node.set('id','feather-'+layer['id']+'-'+str(count));count+=1
                for k,v in {'stroke_method':'manual_stitch','ties':'3','min_stitch_length_mm':'.000001','min_jump_stitch_length_mm':'.000001','trim_after':'False','stop_after':'False'}.items():node.set('{'+s.STITCH+'}'+k,v)
                last=node
            points=[]
        for x,y,command in block['points']:
            if command=='STITCH':points.append((x,y));continue
            finish()
            if last is not None and command in ('TRIM','STOP'):last.set('{'+s.STITCH+'}'+('trim_after' if command=='TRIM' else 'stop_after'),'True')
        finish()
    if not count:raise ValueError('This shape produced no feathered stitches.')

def prepare(data,s):
    from stitchplan import selection
    from preferences import preview,effective
    project=data.get('project');target=data.get('id')
    if not isinstance(project,dict):raise ValueError('Choose one shape to feather.')
    source=next((l for l in project.get('layers',[]) if l.get('id')==target),None)
    if not source or not eligible(source):raise ValueError('Choose native satin, Tatami, guided fill, Streamlines or Wave Fill. Separate imported paths first.')
    if source.get('locked') or source.get('visible',True) is False or source.get('link') or source.get('linkedHelper'):raise ValueError('Show, unlock or detach the shape first.')
    layer=copy.deepcopy(source);layer['feather']=settings(data.get('settings',{}),s,source['id']);layer.pop('featherPreview',None)
    proposal=copy.deepcopy(project);proposal['layers']=[layer if l['id']==target else l for l in proposal['layers']]
    chosen=selection(proposal,[target]);raw=s.build_svg(chosen);root=s.xml(raw)
    stats={'edges':sum(int(g.get('data-feather-edges','0')) for g in root.iter()),
        'maxExtension':max((float(g.get('data-feather-extension','0')) for g in root.iter()),default=0)}
    if active(layer):
        w,h=layer['width'],layer['height']
        transform=inkex.Transform(translate=(layer['x'],layer['y']))@inkex.Transform(rotate=(layer.get('rotation',0),w/2,h/2))@inkex.Transform(translate=(w if layer.get('flipX') else 0,h if layer.get('flipY') else 0))@inkex.Transform(scale=(-1 if layer.get('flipX') else 1,-1 if layer.get('flipY') else 1))
        layer['featherPreview']={'key':key(layer),'paths':[{'d':str(path.transform(-transform)),'color':str(style.get('stroke',layer['color']))} for _,path,style in geometry(raw)]}
    result=preview({'project':chosen,'settings':effective(project)},s)['preview']
    return {'layer':layer,'preview':result,'stats':stats}
