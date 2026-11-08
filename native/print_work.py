"""Native print workspace: settings, installed-engine artwork and paginated PDFs."""
import studio_runtime
import sys
import base64,copy,hashlib,html,io,json,re,tempfile,uuid
from datetime import date
from pathlib import Path
from lxml import etree as ET,html as LH
from PIL import Image,ImageOps
from cutwork import prepare_cutwork
from element_info import RUNTIME
from threads import palettes,parse_palette

LAYOUTS=['clientOverview','clientDetail','operatorOverview','operatorDetail','pattern','custom']
DEFAULTS={'paper':'letter','layouts':['operatorOverview','operatorDetail'],'thumbnail':15,'patternFooter':False,
    'speed':700,'trimSeconds':10,'colorSeconds':10,'extraSeconds':0,'upperFactor':2,'bobbinFactor':1,
    'showTime':['operatorOverview','operatorDetail'],'title':'','client':'','purchaseOrder':'','date':'',
    'footer':'<p>Created with Ink Studio · Ink/Stitch</p>','custom':'<h2>Custom information sheet</h2>',
    'logo':'','palette':'','threadNames':{},'notes':{},'placements':{},'sampleKeys':True}
DEFAULT_KEYS={'paper','layouts','thumbnail','patternFooter','speed','trimSeconds','colorSeconds','extraSeconds','upperFactor','bobbinFactor','showTime','footer','logo','sampleKeys'}
TAGS={'p','div','span','b','strong','i','em','u','br','a','ul','ol','li','h2','h3','hr','blockquote','table','thead','tbody','tr','td','th'}

def rich(value,limit=30000):
    if not isinstance(value,str) or len(value)>limit:raise ValueError('The formatted print text is too long.')
    root=LH.fragment_fromstring(value or '',create_parent='div')
    for e in list(root.iterdescendants()):
        if not isinstance(e.tag,str):e.drop_tree();continue
        if e.tag in ('script','style','iframe','object','svg','math','img','video','audio','link','input','form'):e.drop_tree();continue
        if e.tag not in TAGS:e.drop_tag();continue
        href=e.get('href','') if e.tag=='a' else ''
        e.attrib.clear()
        if href and re.match(r'^(https?://|mailto:)[^\s<>"\x00-\x1f]+$',href,re.I):e.set('href',href);e.set('rel','noopener');e.set('target','_blank')
    return (html.escape(root.text or '')+''.join(ET.tostring(e,encoding='unicode',method='html') for e in root))

def settings(value,s):
    if not isinstance(value,dict) or set(value)-set(DEFAULTS):raise ValueError('Invalid print settings.')
    o=copy.deepcopy({**DEFAULTS,**value})
    if o['paper'] not in ('letter','a4'):raise ValueError('Choose Letter or A4 paper.')
    for k in ('layouts','showTime'):
        if not isinstance(o[k],list) or any(v not in LAYOUTS for v in o[k]) or len(o[k])!=len(set(o[k])):raise ValueError('Invalid print layouts.')
    for k in ('patternFooter','sampleKeys'):
        if type(o[k]) is not bool:raise ValueError('Invalid print visibility setting.')
    for k,low,high in [('thumbnail',15,110),('speed',0,100000),('trimSeconds',0,86400),('colorSeconds',0,86400),('extraSeconds',0,864000),('upperFactor',1,1000),('bobbinFactor',1,1000)]:
        if isinstance(o[k],bool):raise ValueError('Invalid print number.')
        o[k]=s.number(o[k],low,high,k)
    for k,limit in [('title',120),('client',120),('purchaseOrder',80),('date',30),('palette',64)]:
        if not isinstance(o[k],str) or len(o[k])>limit or any(ord(c)<32 for c in o[k]):raise ValueError('Check the print '+k+'.')
    if o['palette']:s.safe_id(o['palette'])
    o['footer']=rich(o['footer'],4000);o['custom']=rich(o['custom'])
    if len(LH.fromstring('<div>'+o['footer']+'</div>').text_content())>350:raise ValueError('Keep the footer within 350 characters so it fits below the page.')
    logo=o['logo']
    if not isinstance(logo,str) or len(logo)>1400000 or logo and not re.fullmatch(r'data:image/png;base64,[A-Za-z0-9+/=]+',logo):raise ValueError('Upload a valid print logo.')
    if logo:
        try:
            with Image.open(io.BytesIO(base64.b64decode(logo.split(',')[1],validate=True))) as im:
                if im.format!='PNG' or max(im.size)>1200:raise ValueError('Print logos must be PNGs no larger than 1,200 pixels.')
                im.verify()
        except Exception as e:raise ValueError('Upload a valid print logo.') from e
    for k in ('notes','threadNames','placements'):
        if not isinstance(o[k],dict) or len(o[k])>1000:raise ValueError('Invalid print annotations.')
    for k,v in o['notes'].items():
        if not re.fullmatch(r'\d{1,4}',k) or not isinstance(v,str) or len(v)>2000:raise ValueError('Use up to 2,000 characters for each operator note.')
    for k,v in o['threadNames'].items():
        if not re.fullmatch('#[0-9a-f]{6}',k) or not isinstance(v,dict) or set(v)-{'name','brand','number'}:raise ValueError('Invalid printed thread name.')
        for text in v.values():
            if not isinstance(text,str) or len(text)>140 or any(ord(c)<32 for c in text):raise ValueError('Keep printed thread names on one line, within 140 characters.')
    for k,v in o['placements'].items():
        if not re.fullmatch(r'(clientOverview|operatorOverview|pattern|clientDetail-\d{1,4})',k) or not isinstance(v,dict) or set(v)-{'scale','x','y','realistic'}:raise ValueError('Invalid print image placement.')
        if type(v.get('realistic',False)) is not bool:raise ValueError('Invalid print image style.')
        o['placements'][k]={'realistic':v.get('realistic',False)}
        for field,lo,hi,default in [('scale',1,2000,100),('x',-1000,1000,0),('y',-1000,1000,0)]:
            if isinstance(v.get(field),bool):raise ValueError('Invalid print placement number.')
            o['placements'][k][field]=s.number(v.get(field,default),lo,hi,'Print '+field)
    return o

def validate_project(project,s):
    if 'printSettings' in project:project['printSettings']=settings(project['printSettings'],s)

def defaults(s,value=None):
    path=s.DATA/'print-defaults.json'
    if value is not None:
        clean=settings(value,s);s.write_atomic(path,{k:clean[k] for k in DEFAULT_KEYS})
    return settings(json.loads(path.read_text()) if path.exists() else {},s)

def snapshot(id,s):
    from interchange import export_result
    r=export_result(id,s);path=s.DATA/'exports'/Path(r['project']).name
    return r,path,json.loads(path.read_text(encoding='utf-8'))

def context(id,s):
    r,path,p=snapshot(id,s);o=settings({**defaults(s),**p.get('printSettings',{})},s)
    if not o['title']:o['title']=str(p.get('name','Embroidery design'))[:120]
    if not o['date']:o['date']=date.today().isoformat()
    return {'id':r['id'],'projectId':p['id'],'name':p.get('name','Design'),'settings':o,'palettes':[{'key':p['key'],'name':p['name']} for p in palettes(s)],'cutwork':bool(r.get('cutwork'))}

def save(data,s):
    r,path,p=snapshot(data.get('id'),s);o=settings(data.get('settings'),s);p['printSettings']=o;s.write_atomic(path,p)
    return {'settings':o}

def engine_data(id,palette,s,reference=False):
    r,path,p=snapshot(id,s);raw=(s.DATA/'exports'/Path(r['svg']).name).read_bytes();source,cuts=prepare_cutwork(raw,s)
    import svg_structure
    if svg_structure.has_masks(s.xml(source)):raise ValueError('Prepare SVG opacity masks before printing stitches.')
    palette_path=None
    if palette:
        s.safe_id(palette)
        for candidate in [*studio_runtime.resource('palettes').glob('*.gpl'),*(s.DATA/'palettes').glob('*.gpl')]:
            try:
                if parse_palette(candidate.read_text(encoding='utf-8-sig'))['key']==palette:palette_path=candidate;break
            except (ValueError,UnicodeError):continue
        if palette_path is None:raise ValueError('The selected thread palette is no longer installed.')
    key=hashlib.sha256(b'print-v1'+source+json.dumps(p.get('threadBook',{}),sort_keys=True).encode()+palette.encode()).hexdigest()
    folder=s.DATA/'print-assets'/key;info=folder/'report.json'
    with s.ENGINE_LOCK:
        if not info.exists() or reference:
            folder.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='native-print-') as tmp:
                source_path=Path(tmp)/'source.svg';source_path.write_bytes(source)
                config=Path(tmp)/'config.json';config.write_text(json.dumps({'source':str(source_path),'folder':str(folder),'palette':str(palette_path) if palette_path else '',
                    'threadBook':p.get('threadBook',{}),'cutThreads':cuts,'reference':reference}),encoding='utf-8')
                raw=s.run(studio_runtime.worker_command('--native-print',str(config),temporary=tmp),300,headless=True)
                report=json.loads(raw);report.update(key=key);s.write_atomic(info,report)
    report=json.loads(info.read_text());report.update(id=r['id'],machine={k:r['preview'][k] for k in ('stitches','trims','stops','width','height')},cutwork=bool(cuts))
    return report

def asset_path(key,name,s):
    if not re.fullmatch('[0-9a-f]{64}',key) or not re.fullmatch(r'(simple|realistic)-(overview|\d{1,4})\.(svg|png)',name):raise ValueError('Invalid print artwork.')
    return s.DATA/'print-assets'/key/name

def image_data(report,index,realistic,s):
    name=('realistic-' if realistic else 'simple-')+('overview' if index is None else str(index));path=asset_path(report['key'],name+'.svg',s)
    if realistic:
        target=asset_path(report['key'],name+'.png',s)
        if not target.exists():s.run(['inkscape',str(path),'--export-filename='+str(target),'--export-dpi=300','--export-background-opacity=0'],180,headless=True)
        path=target
    mime='image/png' if realistic else 'image/svg+xml'
    return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()

def logo(data,s):
    try:raw=base64.b64decode(data.get('data',''),validate=True)
    except Exception:raise ValueError('Choose a logo image.')
    if not 0<len(raw)<=4*1024*1024:raise ValueError('Choose a logo smaller than 4 MB.')
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='print-logo-') as tmp:
        if str(data.get('name','')).lower().endswith('.svg'):
            root=s.sanitize_svg(raw,for_print=True);path=Path(tmp)/'logo.svg';path.write_bytes(ET.tostring(root));png=Path(tmp)/'logo.png'
            s.run(['inkscape',str(path),'--export-filename='+str(png),'--export-area-drawing','--export-width=1000','--export-background-opacity=0'],180,headless=True);raw=png.read_bytes()
        try:
            with Image.open(io.BytesIO(raw)) as original:
                if original.width*original.height>16000000:raise ValueError('Choose a logo with fewer than 16 million pixels.')
                im=ImageOps.exif_transpose(original).convert('RGBA');im.thumbnail((1000,1000));out=io.BytesIO();im.save(out,format='PNG',optimize=True);raw=out.getvalue()
        except Exception as e:raise ValueError('Choose a valid PNG, JPEG, WebP or SVG logo.') from e
    value='data:image/png;base64,'+base64.b64encode(raw).decode();settings({'logo':value},s);return {'logo':value}

def generate(data,s):
    from print_render import render
    o=settings(data.get('settings',{}),s)
    if not o['layouts']:raise ValueError('Choose at least one print layout.')
    report=engine_data(data.get('id'),o['palette'],s);r,path,p=snapshot(data['id'],s)
    if not o['title']:o['title']=str(p.get('name','Design'))[:120]
    if not o['date']:o['date']=date.today().isoformat()
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-pdf-') as tmp:
        markup=render(report,o,p,lambda i,real:image_data(report,i,real,s))
        source=Path(tmp)/'pages.html';source.write_text(markup,encoding='utf-8');target=Path(tmp)/'pages.pdf'
        raw=s.run([sys.executable,str(Path(__file__).with_name('print_pdf_worker.py')),str(source),str(target)],240,headless=True)
        result=json.loads(raw)
        key=uuid.uuid4().hex;slug=re.sub('[^a-zA-Z0-9_-]+','-',o['title']).strip('-')[:60] or 'design';name=key+'-'+slug+'-print.pdf'
        (s.DATA/'exports'/name).write_bytes(target.read_bytes());s.write_atomic(s.DATA/'exports'/(key+'-print.json'),{'name':name,**result})
    return {'key':key,'url':'/files/'+name,'view':'/print-pdf/'+key,'pages':result['pages'],'settings':o,'report':report}

def pdf_path(key,s):
    key=s.safe_id(key);info=json.loads((s.DATA/'exports'/(key+'-print.json')).read_text());return s.DATA/'exports'/info['name'],info

def page(key,index,s):
    source,info=pdf_path(key,s)
    if type(index)is not int or not 1<=index<=info['pages']:raise ValueError('Choose an available print page.')
    target=s.DATA/'exports'/(key+'-print-page-'+str(index)+'.png')
    with s.ENGINE_LOCK:
        if not target.exists():
            args=([sys.executable,str(Path(__file__).with_name('pdf_preview_worker.py')),str(source),str(index),str(target)]
                  if studio_runtime.current().windows else ['pdftoppm','-f',str(index),'-l',str(index),'-scale-to','1400','-singlefile','-png',str(source),str(target.with_suffix(''))])
            s.run(args,120,headless=True)
    return target

def shell(id,s):
    s.safe_id(id)
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ink Studio · Print workspace</title><link rel="stylesheet" href="/style.css"></head><body data-print-id="'+id+'"><script type="module" src="/print-standalone.mjs"></script></body></html>').encode()
