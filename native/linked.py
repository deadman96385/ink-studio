"""Resolve native linked artwork before SVG/PES generation, never trusting a stale canvas."""
import copy,hashlib,json,threading,math
from collections import OrderedDict

LOCAL=('id','name','x','y','width','height','rotation','flipX','flipY','visible','locked','groupId','background','aspectLock','link')
OMIT=('link','scene','sceneBinding','areaSource','component','curveSource','fontGlyph')
CACHE=OrderedDict()
CACHE_LOCK=threading.Lock()

def apply(source,target,s,fixed=False):
    local={k:copy.deepcopy(target[k]) for k in LOCAL if k in target};link=local['link']
    w=source['width']*(target['width']/s.number(link.get('resolvedWidth',target['width']),.000001,1000,'Linked source width'))
    h=source['height']*(target['height']/s.number(link.get('resolvedHeight',target['height']),.000001,1000,'Linked source height'))
    if fixed:w,h=target['width'],target['height']
    if source['type']=='text':w,h=source['width'],source['height']
    s.number(w,.2,100,'Linked width');s.number(h,.2,100,'Linked height')
    result=copy.deepcopy(source)
    for k in (*LOCAL,*OMIT):result.pop(k,None)
    if link.get('inheritColor') is False:
        for k in ('color','recolor','preserveFontColors'):
            if k in target:result[k]=target[k]
            else:result.pop(k,None)
        if result.get('multicolorSatin',{}).get('bands'):result['multicolorSatin']['bands'][0]['color']=target['color']
    result.update(local);result.update(width=w,height=h,x=target['x']+(target['width']-w)/2,y=target['y']+(target['height']-h)/2)
    result['link'].update(resolvedWidth=source['width'],resolvedHeight=source['height'])
    return result

def offset(source,params,s):
    from operations import CATALOG,parameters,layer_mode
    from design_paths import prepare
    if layer_mode(source) not in CATALOG['path_offset']['modes']:raise ValueError('Linked offsets require a fill or outline. Use a linked copy for satin columns.')
    params=parameters(CATALOG['path_offset'],{**params,'keepSource':False})
    base=copy.deepcopy(source)
    for k in (*OMIT,'groupId'):base.pop(k,None)
    base.update(id='linked-source',name='Linked source',x=0,y=0,rotation=0,flipX=False,flipY=False,visible=True,locked=False)
    key=hashlib.sha256(json.dumps([base,params],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    with CACHE_LOCK:
        if key in CACHE:
            CACHE.move_to_end(key);return copy.deepcopy(CACHE[key])
    result=prepare('path_offset',[base],params,s,preview=False)['layers'][0]
    with CACHE_LOCK:
        CACHE[key]=copy.deepcopy(result)
        while len(CACHE)>128:CACHE.popitem(last=False)
    return result

def helper_paths(source,target,helpers,s):
    """Map source-world helpers through the source frame into the copy frame."""
    from digitizing import geometry,from_path,inkex
    def frame(l):
        w,h=l['width'],l['height'];r=math.radians(l.get('rotation',0));c,sn=math.cos(r),math.sin(r)
        fx=-1 if l.get('flipX') else 1;fy=-1 if l.get('flipY') else 1
        a,b,c0,d=c*w*fx,sn*w*fx,-sn*h*fy,c*h*fy
        return inkex.Transform((a,b,c0,d,l['x']+w/2-(a+c0)/2,l['y']+h/2-(b+d)/2))
    mapped=copy.deepcopy(target)
    if target['link']['kind']=='offset':
        sx=target['width']/target['link']['resolvedWidth'];sy=target['height']/target['link']['resolvedHeight']
        dx,dy=target['link'].get('offsetCenter',[0,0]);dx*=sx*(-1 if target.get('flipX') else 1);dy*=sy*(-1 if target.get('flipY') else 1)
        r=math.radians(target.get('rotation',0));w=source['width']*sx;h=source['height']*sy
        mapped.update(x=target['x']+target['width']/2-dx*math.cos(r)+dy*math.sin(r)-w/2,
                      y=target['y']+target['height']/2-dx*math.sin(r)-dy*math.cos(r)-h/2,width=w,height=h)
    transform=frame(mapped) @ -frame(source);result=[]
    for helper in helpers:
        base=copy.deepcopy(helper)
        for k in ('link','linkedHelper','groupId','entry','exit','targetPoint','routeStart','routeEnd','satinCut'):base.pop(k,None)
        base.update(visible=True,role='artwork',borderEnabled=False,fillMethod='tatami_fill',advanced={})
        items=geometry(s.build_svg({'version':1,'layers':[base]},helper_mode=True))
        combined=inkex.Path()
        for _,path,_ in items:combined.extend(path.transform(transform))
        layer=from_path(combined,helper,max_size=10000)
        inherited_visible=helper.get('linkedHelper',{}).get('sourceVisible',helper.get('visible',True))
        layer.update(id='lh-'+hashlib.sha256((target['id']+'\0'+helper['id']).encode()).hexdigest()[:32],
                     name=helper.get('name','Helper')+' · '+target.get('name','copy'),helperTarget=target['id'],
                     visible=inherited_visible and target.get('visible',True),locked=False,
                     linkedHelper={'ownerId':target['id'],'sourceId':helper['id'],'sourceVisible':inherited_visible})
        layer.pop('link',None);result.append(layer)
    return result

def resolve(project,s,fixed_size_ids=()):
    if not isinstance(project,dict) or not isinstance(project.get('layers'),list):raise ValueError('Invalid linked project.')
    if not any(isinstance(l,dict) and (l.get('link') or l.get('linkedHelper')) for l in project['layers']):return project
    if len(project['layers'])>s.MAX_LAYERS:raise ValueError(f'A project can contain up to {s.MAX_LAYERS} layers.')
    result=copy.deepcopy(project);by_id={l['id']:l for l in result['layers']};done={};visiting=set();mapped_helpers={}
    if len(by_id)!=len(result['layers']):raise ValueError('Linked layers must have unique IDs.')
    if not isinstance(fixed_size_ids,(list,tuple)) or len(fixed_size_ids)>s.MAX_LAYERS or any(not isinstance(k,str) or k not in by_id for k in fixed_size_ids):raise ValueError('Invalid linked resize selection.')
    fixed_size_ids=set(fixed_size_ids)
    # Detached owners keep the last resolved helpers; deleted owners remove them.
    retained=[]
    for l in result['layers']:
        marker=l.get('linkedHelper')
        if marker:
            owner=by_id.get(marker.get('ownerId'))
            if not owner or owner.get('link'):continue
            l.pop('linkedHelper',None)
        retained.append(l)
    result['layers']=retained;by_id={l['id']:l for l in retained}
    def visit(l,depth=0):
        key=l['id']
        if key in done:return done[key]
        if depth>32 or key in visiting:raise ValueError('Linked artwork contains a circular source reference.')
        link=l.get('link')
        if link:
            if not isinstance(link,dict) or link.get('kind') not in ('copy','offset'):raise ValueError('Unknown linked artwork type.')
            if link.get('sourceId') not in by_id:raise ValueError('A linked artwork source is missing. Restore it or detach the copy.')
            visiting.add(key);source=visit(by_id[link['sourceId']],depth+1)
            if source.get('type') not in ('rectangle','ellipse','path','text','import') or source.get('role','artwork')!='artwork':raise ValueError('Link ordinary stitched artwork, not reference images or guides.')
            original=source
            if link['kind']=='offset':source=offset(source,link.get('params',{}),s)
            if source['type']=='text':
                ratio=(l.get('lettering',{}).get('scale',100)/source['lettering']['scale']) if key in fixed_size_ids else s.number(link.get('textScale',1),.01,100,'Linked font scale')
                if abs(ratio-1)>1e-12:
                    settings=copy.deepcopy(source['lettering']);settings['scale']*=ratio
                    for field in ('lineSpacing','letterSpacing','wordSpacing'):settings[field]=settings.get(field,0)*ratio
                    text=s.lettering(settings);source={**source,'width':text['width'],'height':text['height'],'lettering':text['settings']}
                l['link']['textScale']=ratio
            old=l;l=apply(source,l,s,key in fixed_size_ids)
            if link['kind']=='offset':
                center=[source['x']+source['width']/2-original['width']/2,source['y']+source['height']/2-original['height']/2]
                previous=link.get('offsetCenter',[0,0])
                if not isinstance(previous,list) or len(previous)!=2:raise ValueError('Invalid linked offset position.')
                dx=(center[0]-s.number(previous[0],-200,200,'Offset X'))*old['width']/link.get('resolvedWidth',old['width'])*(-1 if old.get('flipX') else 1)
                dy=(center[1]-s.number(previous[1],-200,200,'Offset Y'))*old['height']/link.get('resolvedHeight',old['height'])*(-1 if old.get('flipY') else 1)
                a=math.radians(s.number(old.get('rotation',0),-360,360,'Rotation'))
                if key not in fixed_size_ids:l['x']+=dx*math.cos(a)-dy*math.sin(a);l['y']+=dx*math.sin(a)+dy*math.cos(a)
                l['link']['offsetCenter']=center
            mapped_helpers[key]=helper_paths(original,l,mapped_helpers[original['id']],s)
            visiting.remove(key)
        else:mapped_helpers[key]=[]
        mapped_helpers[key].extend(h for h in retained if h.get('helperTarget')==key and h.get('role') in ('guide-line','anchor-line','pattern'))
        done[key]=l;return l
    result['layers']=[visit(l) for l in result['layers']]
    result['layers'].extend(h for l in list(result['layers']) if l.get('link') for h in mapped_helpers[l['id']] if h.get('linkedHelper'))
    if len(result['layers'])>s.MAX_LAYERS:raise ValueError(f'Linked guides would exceed {s.MAX_LAYERS} layers. Remove a copy or helper first.')
    return result
