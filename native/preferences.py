"""Document embroidery metadata, frozen new-design defaults and engine cache."""
import hoops
import hashlib,json,math,os,tempfile,threading
from contextvars import ContextVar
from pathlib import Path
from lxml import etree as ET
import diskcache
import studio_runtime

SVG='http://www.w3.org/2000/svg';STITCH='http://inkstitch.org/namespace'
FACTORY={'collapse_len_mm':3,'min_stitch_len_mm':.1,'min_satin_stroke_width_mm':1,'rotate_on_export':0}
LENGTH_KEYS=tuple(k for k in FACTORY if k!='rotate_on_export')
CURRENT=ContextVar('inkstudio_document_preferences',default=None)
LOCK=threading.RLock()

def validate(value,defaults_only=False):
    allowed=LENGTH_KEYS if defaults_only else tuple(FACTORY)
    if value is None:value={}
    if not isinstance(value,dict) or set(value)-set(allowed):raise ValueError('Unknown embroidery preference.')
    result={k:FACTORY[k] for k in allowed}
    for key,v in value.items():
        if type(v) not in (int,float) or not math.isfinite(v):raise ValueError('Embroidery preferences must be finite numbers.')
        if key=='rotate_on_export':
            if v not in (-90,0,90):raise ValueError('Choose no export rotation, 90° left or 90° right.')
        elif not 0<=v<=100:raise ValueError('Embroidery length preferences must be between 0 and 100 mm.')
        result[key]=v
    return result

def effective(project=None):
    if isinstance(project,dict) and 'embroiderySettings' in project:return validate(project['embroiderySettings'])
    return validate(CURRENT.get())

def freeze(project):
    # A complete saved document never borrows settings from a different open
    # document's request context. That context is only for layer-only tools.
    return {**project,'embroiderySettings':validate(project.get('embroiderySettings'))}

def metadata(root,values):
    values=validate(values);meta=root.find('{'+SVG+'}metadata')
    if meta is None:meta=ET.SubElement(root,'{'+SVG+'}metadata')
    for key,value in values.items():
        for old in meta.findall('{'+STITCH+'}'+key):meta.remove(old)
        ET.SubElement(meta,'{'+STITCH+'}'+key).text=json.dumps(value)

def imported(root):
    meta=root.find('{'+SVG+'}metadata');values={}
    if meta is None:return None
    for key in FACTORY:
        entry=meta.find('{'+STITCH+'}'+key)
        if entry is not None:
            try:values[key]=json.loads(entry.text)
            except (ValueError,TypeError):raise ValueError('The SVG contains an invalid embroidery preference.')
    return validate(values) if values else None

def config_dir():return studio_runtime.current().engine_config
def cache_dir():return config_dir()/'cache'/'stitch_plan'

def stored(s):
    path=s.DATA/'preferences.json'
    if path.exists():
        value=json.loads(path.read_text(encoding='utf-8'))
        return {'defaults':validate(value.get('defaults'),True),'cacheSizeMB':cache_limit(value.get('cacheSizeMB',100))}
    return {'defaults':validate(None,True),'cacheSizeMB':100}

def revision(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def cache_limit(value):
    if type(value) is not int or not 0<=value<=4096:raise ValueError('Cache size must be a whole number from 0 to 4096 MB.')
    return value

def cache_status():
    with diskcache.Cache(str(cache_dir())) as cache:return {'plans':len(cache),'usedMB':round(cache.volume()/1024/1024,2)}

def state(s):
    with LOCK:value=stored(s)
    return {**value,'revision':revision(value),'factory':FACTORY,'cache':cache_status()}

def new_document(s):
    with LOCK:return {**stored(s)['defaults'],'rotate_on_export':0}

def configure_engine(limit,s):
    path=config_dir()/'settings.json';path.parent.mkdir(parents=True,exist_ok=True)
    existing=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    # New-document defaults belong to the native project snapshot. Do not make
    # a later defaults change alter older files or immutable lettering caches.
    existing['cache_size']=limit;s.write_atomic(path,existing)
    with diskcache.Cache(str(cache_dir()),size_limit=limit*1024*1024) as cache:
        cache.cull(retry=True)
        if limit==0:cache.clear(retry=True)

def initialize(s):
    with s.ENGINE_LOCK,LOCK:configure_engine(stored(s)['cacheSizeMB'],s)

def save(data,s):
    values={'defaults':validate(data.get('defaults'),True),'cacheSizeMB':cache_limit(data.get('cacheSizeMB',100))}
    with s.ENGINE_LOCK,LOCK:
        if data.get('revision')!=revision(stored(s)):raise ValueError('New-design defaults changed elsewhere. Reopen preferences before saving them.')
        configure_engine(values['cacheSizeMB'],s);s.write_atomic(s.DATA/'preferences.json',values)
    return state(s)

def clear_cache(s):
    with s.ENGINE_LOCK,LOCK:
        with diskcache.Cache(str(cache_dir())) as cache:removed=cache.clear(retry=True)
    return {'removed':removed,'cache':cache_status()}

def preview(data,s):
    project=data.get('project')
    if not isinstance(project,dict):raise ValueError('Choose a design to preview.')
    project={**project,'embroiderySettings':validate(data.get('settings'))}
    from linked import resolve
    from helpers import require_guides
    from cutwork import prepare_cutwork
    from threads import named_pes
    project=resolve(project,s);require_guides(project)
    svg=s.build_svg(project,sewing=True)
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='preferences-preview-') as tmp:
        machine,threads=prepare_cutwork(svg,s);path=Path(tmp)/'preview.svg';path.write_bytes(machine)
        x,y,w,h=s.bounds(path,sewing=True)
        if not hoops.inside(project,x,y,w,h):raise ValueError(f"Move or resize the design to fit the {hoops.hoop(project)['short']} mm hoop before previewing.")
        pes=Path(tmp)/'preview.pes';pes.write_bytes(named_pes(s.run([s.ENGINE,'--extension=output','--format=pes','--version=6',str(path)],240,headless=True),{**project,'threadBook':{**project.get('threadBook',{}),**threads}}))
        result=s.stitch_data(pes)
        if result['width']>hoops.size(project)[0] or result['height']>hoops.size(project)[1]:raise ValueError('Generated stitches exceed the hoop.')
    return {'preview':result,'settings':project['embroiderySettings']}
