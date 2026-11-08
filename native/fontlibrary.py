"""Versioned custom embroidery fonts backed by the installed Ink/Stitch engine."""
import studio_runtime
import base64
import copy
import hashlib
import io
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import threading
import unicodedata
import zipfile
from lxml import etree as ET

LOCK=threading.RLock()
VARIANTS={'ltr':'→','rtl':'←','ttb':'↓','btt':'↑'}
MAX_EXPANDED=24*1024*1024
SODI='http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd'

def unpack_xz(raw):
    try:
        decoder=lzma.LZMADecompressor(memlimit=128*1024*1024);out=decoder.decompress(raw,max_length=MAX_EXPANDED+1)
        if not decoder.eof or len(out)>MAX_EXPANDED:raise ValueError('A compressed font file is too large.')
        return out
    except lzma.LZMAError:raise ValueError('The font contains an invalid XZ file.')

def read_meta(path):
    p=path/'font.json'
    raw=p.read_bytes() if p.exists() else unpack_xz((path/'font.json.xz').read_bytes())
    return json.loads(raw.decode('utf-8-sig'))

def variants(path):
    result={}
    for kind,legacy in VARIANTS.items():
        found=[]
        for name in (kind,legacy):
            for ext in ('.svg','.svg.xz'):
                p=path/(name+ext)
                if p.is_file():found.append(p)
            if (path/name).is_dir():found.extend(sorted(p for p in (path/name).iterdir() if p.is_file() and p.name.endswith(('.svg','.svg.xz'))))
        if found:result[kind]=found
    return result

def library_state(s):
    path=s.DATA/'font-library.json'
    return json.loads(path.read_text()) if path.exists() else {'hidden':[],'favorites':[]}

def load_fonts(s,configure=False):
    custom=s.DATA/'fonts';custom.mkdir(exist_ok=True)
    if configure:
        with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='font-directory-') as tmp:
            p=Path(tmp)/'blank.svg';p.write_bytes(ET.tostring(s.svg_root()))
            s.run([s.ENGINE,'--extension=lettering_custom_font_dir','--path='+str(custom),str(p)])
    state=library_state(s);result={}
    for path in sorted(studio_runtime.resource('fonts','src').iterdir())+sorted(custom.glob('custom-*')):
        if not path.is_dir() or not ((path/'font.json').exists() or (path/'font.json.xz').exists()):continue
        meta=read_meta(path)
        if not meta.get('name'):continue
        own=path.parent==custom;key=path.name;choices=list(variants(path))
        result[key]={'id':key,'name':meta.get('_studio_name',meta['name']),'size':meta.get('size',0),
            'minScale':round(meta.get('min_scale',1)*100),'maxScale':round(meta.get('max_scale',1)*100),
            'leading':meta.get('leading',100)*s.PX_MM,'description':meta.get('description',''),
            'case':meta.get('letter_case',''),'glyphs':meta.get('glyphs',[]),'license':meta.get('font_license',''),
            'keywords':meta.get('keywords',[]),'preview':'/font-previews/'+key+'.png','custom':own,
            'hidden':key in state['hidden'],'favorite':key in state['favorites'],'variants':choices,
            'sortable':bool(meta.get('sortable',False)),
            '_path':str(path),'_engine':meta['name'],'_internal':bool(meta.get('_studio_internal',False))}
    return result

def public(font):return {k:v for k,v in font.items() if not k.startswith('_')}

def refresh(s):s.FONTS=load_fonts(s)

def get_font(key,s):
    font=s.FONTS.get(s.safe_id(key))
    if not font:raise ValueError('Choose an installed embroidery font.')
    return font

def metadata(font):
    meta=read_meta(Path(font['_path']));meta['name']=font['name']
    return {k:v for k,v in meta.items() if not k.startswith('_studio')}

def detail(key,s):
    font=get_font(key,s);path=Path(font['_path']);license_text=''
    for p in path.iterdir():
        if p.is_file() and p.name.lower().startswith(('license','licence','ofl','copyright')):
            license_text+=p.read_text(errors='replace')[:100000]+'\n'
    return {'font':public(font),'metadata':metadata(font),'licenseText':license_text[:200000]}

def validate_metadata(meta,s):
    if not isinstance(meta,dict) or len(json.dumps(meta))>8*1024*1024:raise ValueError('The font metadata is invalid or too large.')
    meta=copy.deepcopy(meta)
    for key,limit,default in [('name',120,''),('description',4000,''),('font_license',500,''),('original_font',300,''),('original_font_url',2000,''),('default_glyph',32,'�')]:
        value=meta.get(key,default)
        if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 and c not in '\n\t' for c in value):raise ValueError('Invalid font '+key+'.')
        meta[key]=value.strip()
    if not meta['name']:raise ValueError('Give the font a name.')
    if '\n' in meta['name'] or '\t' in meta['name']:raise ValueError('The font name must be one line.')
    for key,lo,hi,default in [('size',0,200,0),('leading',.1,2000,100),('horiz_adv_x_space',0,2000,20),('min_scale',.05,10,1),('max_scale',.05,10,1)]:meta[key]=s.number(meta.get(key,default),lo,hi,key)
    if meta['max_scale']<meta['min_scale']:raise ValueError('Maximum font scale must be at least the minimum.')
    if meta.get('horiz_adv_x_default') is not None:meta['horiz_adv_x_default']=s.number(meta['horiz_adv_x_default'],0,2000,'Default advance')
    for key,default in [('auto_satin',True),('reversible',True),('sortable',False),('scale_cross_stitch_pattern',False)]:
        if type(meta.get(key,default)) is not bool:raise ValueError('Invalid '+key+' option.')
        meta[key]=meta.get(key,default)
    for key,allowed,default in [('letter_case',('','upper','lower'),''),('text_direction',('ltr','rtl'),'ltr'),('default_variant',tuple(VARIANTS),'ltr')]:
        value=meta.get(key,default)
        if key=='default_variant':value=next((k for k,v in VARIANTS.items() if value==v),value)
        if value not in allowed:raise ValueError('Choose a valid '+key+'.')
        meta[key]=value
    words=meta.get('keywords',[])
    if isinstance(words,str):words=[w.strip() for w in words.split(',') if w.strip()]
    if not isinstance(words,list) or len(words)>40 or any(not isinstance(w,str) or len(w)>80 for w in words):raise ValueError('Use at most 40 short font keywords.')
    meta['keywords']=words
    for key in ('horiz_adv_x','kerning_pairs'):
        values=meta.get(key,{})
        if not isinstance(values,dict) or len(values)>250000:raise ValueError('Invalid font spacing table.')
        meta[key]={}
        for name,value in values.items():
            if name=='' and key=='horiz_adv_x':continue  # Legacy, unused empty-glyph entry.
            if not isinstance(name,str) or not 1<=len(name)<=129:raise ValueError('Invalid glyph or pair in the spacing table.')
            meta[key][name]=s.number(value,-2000 if key=='kerning_pairs' else 0,2000,'Glyph spacing')
    indices=meta.get('combine_at_sort_indices',[])
    if not isinstance(indices,list) or len(indices)>100 or any(type(i) is not int or not 0<=i<=1000 for i in indices):raise ValueError('Color-sort combine indices must be integers from 0 to 1000.')
    return {k:v for k,v in meta.items() if not k.startswith('_studio')}

def clean_svg(raw,s,allow_outline=False):
    if len(raw)>MAX_EXPANDED or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('The font SVG is too large or contains document declarations.')
    # Some installed fonts have multi-megabyte path attributes. Use bounded
    # incremental parsing, retaining the no-entity/no-network guarantees.
    parser=ET.XMLPullParser(events=('start','end'),resolve_entities=False,no_network=True,remove_comments=True,remove_pis=True,huge_tree=True)
    depth=count=0
    try:
        for offset in range(0,len(raw),65536):
            parser.feed(raw[offset:offset+65536])
            for event,e in parser.read_events():
                if event=='start':depth+=1;count+=1
                else:depth-=1
                if depth>128 or count>150000:raise ValueError('The font SVG is too deeply nested or contains too many objects.')
        root=parser.close()
    except ET.XMLSyntaxError:raise ValueError('The font SVG is not a valid XML document.')
    if root.tag!='{'+s.SVG+'}svg':raise ValueError('A font variant must be an SVG document.')
    allowed={'svg','g','path','rect','ellipse','circle','polygon','polyline','line','defs','symbol','use','linearGradient','radialGradient','stop','clipPath','marker','metadata','title','desc',
             'font','font-face','font-face-src','font-face-name','glyph','missing-glyph','hkern','vkern','pattern','filter','feGaussianBlur','feBlend','feComposite','feColorMatrix','feOffset','feFlood','feMerge','feMergeNode','feComponentTransfer','feFuncR','feFuncG','feFuncB','feFuncA','feMorphology','feTurbulence','feDisplacementMap','feConvolveMatrix','feDiffuseLighting','feSpecularLighting','feDistantLight','fePointLight','feSpotLight'}
    refs=[];paths=0
    for e in list(root.iter()):
        name=ET.QName(e);local=name.localname
        if name.namespace==s.SVG and local in ('image','text','tspan','textPath'):
            # Reference pictures are not embroidery glyphs and are not needed
            # by the font renderer. Do not carry embedded/external photos into
            # generated lettering or the installed font copy.
            if e.getparent() is not None:e.getparent().remove(e)
            continue
        if name.namespace==s.SVG and local=='a':
            e.tag='{'+s.SVG+'}g';local='g'
            e.attrib.pop('href',None);e.attrib.pop('{http://www.w3.org/1999/xlink}href',None)
        if name.namespace==s.SVG and local not in allowed:raise ValueError('Font variants must contain embroidery paths, without '+local+' elements.')
        if name.namespace not in (s.SVG,s.STITCH,SODI,s.INK):
            if e.getparent() is not None:e.getparent().remove(e)
            continue
        if name.namespace==SODI and local not in ('namedview','guide'):
            if e.getparent() is not None:e.getparent().remove(e)
            continue
        paths+=local=='path'
        for key,value in list(e.attrib.items()):
            attr=ET.QName(key).localname.lower()
            if re.fullmatch(r'on[a-z]+',attr) or attr=='src' or re.search(r'@import|javascript:',value,re.I):raise ValueError('Font SVGs cannot include scripts or external resources.')
            if attr=='href':
                if not re.fullmatch(r'#[\w.:-]{1,200}',value):raise ValueError('Font SVG links must remain inside the document.')
                refs.append(value[1:])
            if attr in ('style','fill','stroke','clip-path','filter','mask','marker-start','marker-end','marker-mid'):
                if '\\' in value:raise ValueError('Font SVG styles must use plain local values.')
                for match in re.finditer(r'url\s*\(([^)]*)\)',value,re.I):
                    target=match[1].strip().strip('\'"')
                    if not re.fullmatch(r'#[\w.:-]{1,200}',target):raise ValueError('Font SVG resources must be local.')
                    refs.append(target[1:])
    ids=[e.get('id') for e in root.iter() if e.get('id')]
    idset=set(ids)
    if len(ids)!=len(idset) or any(r not in idset for r in refs):raise ValueError('Font SVG references must use existing, unique object IDs.')
    by_id={e.get('id'):e for e in root.iter() if e.get('id')};checked=set()
    def check_references(key,chain):
        if key in chain or len(chain)>32:raise ValueError('Font SVG references cannot contain loops or deep chains.')
        if key in checked:return
        for e in by_id[key].iter():
            href=e.get('{http://www.w3.org/1999/xlink}href',e.get('href',''))
            if href.startswith('#'):check_references(href[1:],chain|{key})
        checked.add(key)
    for ref in set(refs):check_references(ref,set())
    outlines=sum(bool(g.get('d')) for g in root.iter('{'+s.SVG+'}glyph')) if allow_outline else 0
    if paths>20000 or (not paths and not 1<=outlines<=6000):raise ValueError('A font file must contain 1–20,000 embroidery paths or a valid outline font.')
    glyphs=[]
    for g in root.iter('{'+s.SVG+'}g'):
        label=g.get('{'+s.INK+'}label','')
        if label.startswith('GlyphLayer-') and any(True for _ in g.iter('{'+s.SVG+'}path')):
            glyph=unicodedata.normalize('NFC',label[11:])
            if not 1<=len(glyph)<=32:raise ValueError('Font glyph names must be 1–32 characters.')
            g.set('{'+s.INK+'}groupmode','layer');glyphs.append(glyph)
    if not glyphs and not (allow_outline and outlines):raise ValueError('The SVG has no Ink/Stitch GlyphLayer- layers. Convert or digitize it as an embroidery font first.')
    return ET.tostring(root),glyphs

def files_for(font,s):
    path=Path(font['_path']);files={}
    for kind,paths in variants(path).items():
        for i,p in enumerate(paths):
            name=kind+'.svg' if len(paths)==1 else kind+'/'+str(i)+'.svg'
            files[name]=unpack_xz(p.read_bytes()) if p.name.endswith('.xz') else p.read_bytes()
    for p in path.iterdir():
        if p.is_file() and p.name.lower().startswith(('license','licence','ofl','copyright')):files[p.name]=p.read_bytes()
    return files

def decode_package(data,s):
    try:raw=base64.b64decode(data.get('content',''),validate=True)
    except (ValueError,TypeError):raise ValueError('Choose an Ink/Stitch font ZIP file.')
    if not 0<len(raw)<=8*1024*1024:raise ValueError('Font ZIP files must be smaller than 8 MB.')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos=[i for i in archive.infolist() if not i.is_dir() and not i.filename.startswith('__MACOSX/')]
            if len(infos)>6000 or sum(i.file_size for i in infos)>MAX_EXPANDED:raise ValueError('The font package is too large.')
            names=[i.filename for i in infos]
            if len(set(names))!=len(names):raise ValueError('The font ZIP contains duplicate filenames.')
            for info in infos:
                path=PurePosixPath(info.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in info.filename or ':' in info.filename or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('The font ZIP contains an unsafe path.')
            candidates=[n for n in names if PurePosixPath(n).name in ('font.json','font.json.xz')]
            folders={str(PurePosixPath(n).parent) for n in candidates}
            if len(folders)!=1:raise ValueError('Import one font per ZIP, with font.json and its SVG variants.')
            folder=next(iter(folders));prefix='' if folder=='.' else folder+'/'
            meta_name=prefix+'font.json' if prefix+'font.json' in names else prefix+'font.json.xz'
            meta_raw=archive.read(meta_name);meta_raw=unpack_xz(meta_raw) if meta_name.endswith('.xz') else meta_raw
            meta=json.loads(meta_raw.decode('utf-8-sig'));files={};total=len(meta_raw)
            for name in names:
                if not name.startswith(prefix):continue
                relative=name[len(prefix):];p=PurePosixPath(relative)
                if relative in ('font.json','font.json.xz') or p.name.startswith('.'):continue
                stem=relative.removesuffix('.xz').removesuffix('.svg');kind=stem.split('/')[0]
                kind=next((k for k,v in VARIANTS.items() if kind==v),kind)
                is_svg=name.endswith(('.svg','.svg.xz')) and kind in VARIANTS
                is_license=len(p.parts)==1 and p.name.lower().startswith(('license','licence','ofl','copyright'))
                if not is_svg and not is_license:continue
                content=archive.read(name)
                if is_svg and name.endswith('.xz'):content=unpack_xz(content)
                total+=len(content)
                if total>MAX_EXPANDED:raise ValueError('The expanded font is too large.')
                target=kind+'.svg' if is_svg and len(p.parts)==1 else kind+'/'+p.name.removesuffix('.xz') if is_svg else p.name
                if target in files:raise ValueError('The font has duplicate variants. Keep only one compressed or uncompressed copy.')
                files[target]=content
            return meta,files
    except (zipfile.BadZipFile,KeyError,UnicodeError,json.JSONDecodeError):raise ValueError('This is not a readable Ink/Stitch font package.')

def probe_text(font):
    glyphs=font['glyphs'];text=''.join(c for c in 'Abc123' if c in glyphs)
    if not text:text=next((g for g in glyphs if len(g)==1 and not g.isspace()),glyphs[0])
    return text

def install(meta,files,s,verify=True,internal=False):
    meta=validate_metadata(meta,s);clean={};glyphs=[];choices=[]
    for name,raw in files.items():
        if name.endswith('.svg'):
            raw,found=clean_svg(raw,s);glyphs.extend(found);kind=name.split('/')[0].removesuffix('.svg')
            if kind not in choices:choices.append(kind)
        clean[name]=raw
    if not choices:raise ValueError('The font needs at least one ltr, rtl, ttb or btt SVG variant.')
    meta['glyphs']=sorted(set(glyphs))
    if len(meta['glyphs'])>5000:raise ValueError('Use a font with at most 5,000 glyphs.')
    if meta['default_variant'] not in choices:meta['default_variant']=choices[0]
    fingerprint=hashlib.sha256(json.dumps(meta,ensure_ascii=False,sort_keys=True).encode())
    if internal:fingerprint.update(b'ink-studio-internal-font-v1')
    for name,raw in sorted(clean.items()):fingerprint.update(name.encode()+b'\0'+raw)
    key='custom-'+fingerprint.hexdigest()[:24];target=s.DATA/'fonts'/key
    with LOCK:
        created=not target.exists()
        if created:
            with tempfile.TemporaryDirectory(prefix='.font-',dir=target.parent) as tmp:
                stage=Path(tmp)/'font';stage.mkdir()
                for name,raw in clean.items():
                    p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
                stored={**meta,'_studio_name':meta['name'],'_studio_key':key,'_studio_internal':internal,'name':meta['name']+' [Ink Studio '+key[-10:]+']'}
                (stage/'font.json').write_text(json.dumps(stored,ensure_ascii=False,indent=2),encoding='utf-8');stage.rename(target)
        refresh(s)
        try:
            font=get_font(key,s)
            if verify:s.lettering({'font':key,'text':probe_text(font),'scale':max(font['minScale'],min(100,font['maxScale']))})
        except Exception:
            if created:shutil.rmtree(target)
            refresh(s);raise
    return public(get_font(key,s))

def import_font(data,s):
    meta,files=decode_package(data,s)
    font=install(meta,files,s)
    return set_state({'font':font['id'],'hidden':False},s)

def save_metadata(data,s):
    font=get_font(data.get('font'),s);meta=metadata(font);changes=data.get('metadata')
    if not isinstance(changes,dict):raise ValueError('Enter the font settings.')
    allowed={'name','description','font_license','original_font','original_font_url','keywords','size','leading','horiz_adv_x_space','horiz_adv_x_default','min_scale','max_scale','auto_satin','reversible','sortable','scale_cross_stitch_pattern','letter_case','text_direction','default_variant','default_glyph','horiz_adv_x','kerning_pairs','combine_at_sort_indices'}
    if any(k not in allowed for k in changes):raise ValueError('Unknown font setting.')
    meta.update(changes);new=install(meta,files_for(font,s),s)
    if font['custom'] and new['id']!=font['id']:set_state({'font':font['id'],'hidden':True},s)
    new=set_state({'font':new['id'],'hidden':False,'favorite':font['favorite']},s)['font']
    return {'font':new,'previous':font['id']}

def set_state(data,s):
    font=get_font(data.get('font'),s)
    with LOCK:
        state=library_state(s)
        for prop,name in [('hidden','hidden'),('favorite','favorites')]:
            if prop not in data:continue
            if type(data[prop]) is not bool:raise ValueError('Choose an on/off font option.')
            values=set(state[name]);values.add(font['id']) if data[prop] else values.discard(font['id']);state[name]=sorted(values)
        s.write_atomic(s.DATA/'font-library.json',state);refresh(s)
    return {'font':public(get_font(font['id'],s))}

def package(key,s):
    font=get_font(key,s);files=files_for(font,s);files['font.json']=json.dumps(metadata(font),ensure_ascii=False,indent=2).encode();out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in files.items():archive.writestr(name,raw)
    return out.getvalue()

def preview_path(key,s):
    font=get_font(key,s);p=Path(font['_path'])/'preview.png'
    if p.exists():return p
    p=s.DATA/'cache'/('font-preview-'+key+'.png')
    if p.exists():return p
    result=s.lettering({'font':key,'text':probe_text(font),'scale':max(font['minScale'],min(100,font['maxScale']))})
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='font-preview-') as tmp:
        root=s.svg_root();root.set('viewBox',f'0 0 {result["width"]+2} {result["height"]+2}');root.set('width',str(result['width']+2)+'mm');root.set('height',str(result['height']+2)+'mm')
        g=ET.SubElement(root,'{'+s.SVG+'}g',transform='translate(1,1)');g.append(s.xml(result['svg'].encode()))
        source=Path(tmp)/'preview.svg';source.write_bytes(ET.tostring(root));out=Path(tmp)/'preview.png'
        width=min(600,max(100,600*(result['width']+2)/(result['height']+2)))
        s.run(['inkscape',str(source),'--export-width='+str(round(width)),'--export-filename='+str(out)])
        with tempfile.NamedTemporaryFile(dir=p.parent,suffix='.png',delete=False) as image:
            image.write(out.read_bytes());stage=Path(image.name)
        stage.replace(p)
    return p

def embed_fonts(project,s):
    ids={l.get('lettering',{}).get('font') for l in s.asset_layers(project) if l.get('type')=='text'}
    if isinstance(project.get('fontSampleRecipe'),dict):ids.add(project['fontSampleRecipe'].get('font'))
    return [{'id':key,'content':base64.b64encode(package(key,s)).decode()} for key in sorted(k for k in ids if k and get_font(k,s)['custom'])]

def restore_fonts(project,s):
    fonts=project.pop('embeddedFonts',[])
    if not isinstance(fonts,list) or len(fonts)>120:raise ValueError('Invalid embedded font list.')
    mapping={}
    for item in fonts:
        if not isinstance(item,dict):raise ValueError('Invalid embedded font package.')
        key=s.safe_id(item.get('id'));meta,files=decode_package(item,s);mapping[key]=install(meta,files,s)['id']
    for layer in s.asset_layers(project):
        if layer.get('type')=='text':
            settings=layer.get('lettering',{});settings['font']=mapping.get(settings.get('font'),settings.get('font'))
    if isinstance(project.get('fontSampleRecipe'),dict):
        recipe=project['fontSampleRecipe'];recipe['font']=mapping.get(recipe.get('font'),recipe.get('font'))
