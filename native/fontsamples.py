"""Resumable, hoop-sized font specimens using Ink/Stitch's actual glyph renderer."""
import copy
import preferences
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unicodedata
import uuid
import zipfile
from lxml import etree as ET
import fontlibrary as fl
from limits import MAX_LAYERS

LOCK=threading.RLock()
LIVE=set()
CANCEL=set()


def documents(font,variant,s):
    paths=fl.variants(Path(font['_path']))
    if variant not in paths:raise ValueError('Choose a stitch direction available in this font.')
    result=[]
    for p in paths[variant]:
        raw=fl.unpack_xz(p.read_bytes()) if p.name.endswith('.xz') else p.read_bytes()
        clean,_=fl.clean_svg(raw,s)
        result.append(ET.fromstring(clean,ET.XMLParser(resolve_entities=False,no_network=True,huge_tree=True)))
    return result


def glyphs(docs,s):
    result={}
    for doc in docs:
        for g in doc.iter('{'+s.SVG+'}g'):
            label=g.get('{'+s.INK+'}label','')
            if label.startswith('GlyphLayer-') and any(True for _ in g.iter('{'+s.SVG+'}path')):
                name=unicodedata.normalize('NFC',label[11:])
                result[name]={'name':name,'locked':g.get('{'+fl.SODI+'}insensitive') is not None}
    return list(result.values())


def catalog(key,variant,s):
    font=fl.get_font(key,s)
    if font.get('_internal'):raise ValueError('Choose a font from the library.')
    requested=variant
    variant=variant or fl.metadata(font).get('default_variant','ltr')
    variant=next((k for k,v in fl.VARIANTS.items() if v==variant),variant)
    if variant not in font['variants']:
        if requested:raise ValueError('Choose a stitch direction available in this font.')
        variant=font['variants'][0]
    return {'font':fl.public(font),'variant':variant,'glyphs':glyphs(documents(font,variant,s),s)}


def settings(data,s):
    cat=catalog(data.get('font'),data.get('variant'),s);font=cat['font']
    available={g['name'] for g in cat['glyphs']};chosen=data.get('glyphs')
    if chosen is None:chosen=[g['name'] for g in cat['glyphs'] if not g['locked']]
    if not isinstance(chosen,list) or not chosen or len(chosen)>5000 or any(not isinstance(g,str) or g not in available for g in chosen) or len(set(chosen))!=len(chosen):raise ValueError('Select 1–5,000 distinct glyphs from this stitch direction.')
    order=data.get('order','source')
    if order not in ('source','alphabetical'):raise ValueError('Choose font order or alphabetical order.')
    chosen=sorted(chosen) if order=='alphabetical' else [g['name'] for g in cat['glyphs'] if g['name'] in set(chosen)]
    sort=data.get('colorSort',False)
    if type(sort) is not bool or sort and not font['sortable']:raise ValueError('Color sorting needs a font with indexed thread colors.')
    trim=data.get('trim',True)
    if type(trim) is not bool:raise ValueError('Choose whether to trim between glyphs.')
    return dict(font=font['id'],variant=cat['variant'],glyphs=chosen,order=order,colorSort=sort,trim=trim,
                scale=round(s.number(data.get('scale',100),font['minScale'],font['maxScale'],'Font scale')),
                lineWidth=s.number(data.get('lineWidth',94),5,96,'Maximum row width'),
                gapX=s.number(data.get('gapX',3),.5,30,'Glyph gap'),gapY=s.number(data.get('gapY',4),.5,30,'Row gap'))


def alias_font(font,variant,s):
    docs=documents(font,variant,s);names=[g['name'] for g in glyphs(docs,s)]
    aliases={name:chr(0xE000+i) for i,name in enumerate(names)};files={}
    for i,doc in enumerate(docs):
        for g in doc.iter('{'+s.SVG+'}g'):
            label=g.get('{'+s.INK+'}label','')
            if label.startswith('GlyphLayer-'):
                name=unicodedata.normalize('NFC',label[11:])
                if name in aliases:
                    g.set('{'+s.INK+'}label','GlyphLayer-'+aliases[name]);g.attrib.pop('{'+fl.SODI+'}insensitive',None)
        files[f'{variant}/{i:04d}.svg']=ET.tostring(doc)
    meta=fl.metadata(font)
    meta.update(name='Sampler '+font['id'],letter_case='',text_direction='ltr',default_variant=variant,reversible=False,
                default_glyph=next(iter(aliases.values())),kerning_pairs={},horiz_adv_x={aliases[k]:v for k,v in meta.get('horiz_adv_x',{}).items() if k in aliases})
    installed=fl.install(meta,files,s,verify=False,internal=True)
    return s.FONTS[installed['id']],aliases


def batch(font,texts,scale,trim,sort,s):
    """One engine process per batch, retaining exact glyphs via private aliases."""
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='font-samples-') as tmp:
        p=Path(tmp);source=p/'blank.svg';source.write_bytes(ET.tostring(s.svg_root()));separator=uuid.uuid4().hex
        packed=s.run([s.ENGINE,'--extension=batch_lettering','--font='+font['_engine'],'--text='+separator.join(texts),
                      '--separator='+separator,'--scale='+str(scale),'--trim='+('glyph' if trim else 'off'),
                      '--color-sort='+('all' if sort else 'off'),'--file-formats=svg,pes',str(source)],240)
        try:
            with zipfile.ZipFile(io.BytesIO(packed)) as archive:
                results=[]
                for i in range(len(texts)):
                    raw=archive.read(f'{i:03d}.svg');file=p/'glyph.svg';file.write_bytes(raw)
                    x,y,w,h=s.bounds(file);root=s.xml(raw)
                    group=root.find('.//{'+s.SVG+'}g[@{'+s.STITCH+'}lettering]')
                    if group is None:raise ValueError('The font did not produce editable glyphs.')
                    normalized=ET.Element('{'+s.SVG+'}g',nsmap=s.NS,transform=f'translate({-x},{-y})')
                    for defs in root.findall('{'+s.SVG+'}defs'):normalized.append(copy.deepcopy(defs))
                    normalized.append(copy.deepcopy(group))
                    # The glyph starts at the renderer's y=0 baseline. Preserve
                    # its measured ascent so a row shares a real baseline.
                    normalized.attrib.pop('{'+s.STITCH+'}lettering',None)
                    svg=ET.tostring(normalized,encoding='unicode');key=hashlib.sha256(svg.encode()).hexdigest()
                    pes=p/'glyph.pes';pes.write_bytes(archive.read(f'{i:03d}.pes'));preview=s.stitch_data(pes)
                    asset={'key':key,'svg':svg,'width':max(.2,w),'height':max(.2,h),'name':'Font sample glyph'}
                    s.write_atomic(s.DATA/'assets'/(key+'.json'),asset)
                    results.append({'asset':asset,'top':y,'bottom':y+h,'commands':len(s.pystitch.read(str(pes)).stitches),'stitches':preview['stitches']})
                return results
        except (zipfile.BadZipFile,KeyError):raise ValueError('Ink/Stitch could not render one of these glyphs. Try a smaller selection to locate it.')


def glyph_assets(config,progress,check,s):
    source=fl.get_font(config['font'],s);font,aliases=alias_font(source,config['variant'],s)
    result={};missing=[]
    for name in config['glyphs']:
        key=hashlib.sha256(json.dumps([font['id'],name,config['scale'],config['trim'],'sample-v1']).encode()).hexdigest()
        path=s.DATA/'cache'/('sample-'+key+'.json')
        if path.exists():result[name]=json.loads(path.read_text())
        else:missing.append((name,path))
    for start in range(0,len(missing),12):
        check();chunk=missing[start:start+12];progress(f'Rendering glyphs · {len(result)} / {len(config["glyphs"])}')
        values=batch(font,[aliases[name] for name,path in chunk],config['scale'],config['trim'],False,s)
        for (name,path),value in zip(chunk,values):s.write_atomic(path,value);result[name]=value
    check()
    for name,value in result.items():
        # The portable artwork uses real glyph names. It must not ask desktop
        # Lettering to load a private alias font when the SVG is opened there.
        asset=value['asset'];root=s.xml(asset['svg'].encode())
        for node in root.iter():
            node.attrib.pop('{'+s.STITCH+'}lettering',None)
            label=node.get('{'+s.INK+'}label','')
            if label==aliases[name] or label.startswith('Sampler custom-') or label.startswith('Sampler '+config['font']):node.set('{'+s.INK+'}label',name)
        svg=ET.tostring(root,encoding='unicode');key=hashlib.sha256(svg.encode()).hexdigest()
        value['asset']={**asset,'key':key,'svg':svg,'name':name}
        if not (s.DATA/'assets'/(key+'.json')).exists():s.write_atomic(s.DATA/'assets'/(key+'.json'),value['asset'])
    return [(name,result[name]) for name in config['glyphs']]


def layout(items,config):
    """Baseline-aligned rows. Never shrink artwork to make a sheet fit."""
    rows=[];row=[];width=0
    for name,item in items:
        w=item['asset']['width'];h=item['asset']['height']
        if w>config['lineWidth'] or h>96:raise ValueError(f'Glyph {name!r} is too large for this sheet. Reduce the font scale or increase row width.')
        if row and (width+config['gapX']+w>config['lineWidth'] or sum(v['commands'] for _,v,_ in row)+item['commands']>280000 or len(row)>=MAX_LAYERS):rows.append(row);row=[];width=0
        if item['commands']>280000:raise ValueError(f'Glyph {name!r} exceeds the page stitch limit. Reduce its scale.')
        if row:width+=config['gapX']
        row.append((name,item,width));width+=w
    if row:rows.append(row)
    pages=[];page=[];y=0;count=commands=0
    for row in rows:
        top=min(v['top'] for _,v,_ in row);bottom=max(v['bottom'] for _,v,_ in row);height=max(.2,bottom-top)
        if height>96:raise ValueError('The ascenders and descenders in one row exceed the hoop height. Reduce the font scale.')
        amount=sum(v['commands'] for _,v,_ in row)
        if page and (y+config['gapY']+height>96 or count+len(row)>MAX_LAYERS or commands+amount>280000):pages.append(page);page=[];y=0;count=commands=0
        if page:y+=config['gapY']
        page.append([(name,v,x,y+v['top']-top) for name,v,x in row]);y+=height;count+=len(row);commands+=amount
    if page:pages.append(page)
    return pages


def sorted_page(project,source,s):
    # Reuse Ink/Stitch's indexed color sorter, including the font author's
    # combine_at_sort_indices. RGB grouping alone changes applique sequence.
    root=s.svg_root();root.set('viewBox',f'0 0 {100/s.PX_MM} {100/s.PX_MM}')
    group=ET.SubElement(root,'{'+s.SVG+'}g',attrib={'{'+s.INK+'}label':'GlyphLayer-\ue000','{'+s.INK+'}groupmode':'layer'})
    art=ET.SubElement(group,'{'+s.SVG+'}g',transform=f'scale({1/s.PX_MM})')
    built=s.xml(s.build_svg(project))
    for child in built:
        if child.tag in ('{'+s.SVG+'}g','{'+s.SVG+'}defs'):art.append(copy.deepcopy(child))
    # A sampled glyph is a new font source, not nested live lettering. Old
    # lettering identities would give the sorter the wrong ancestor boundary.
    for node in art.iter():
        for attr in ('lettering','letter-group'):node.attrib.pop('{'+s.STITCH+'}'+attr,None)
        node.attrib.pop('{'+s.INK+'}groupmode',None)
    existing={node.get('id') for node in root.iter() if node.get('id')}
    for i,node in enumerate(root.iter()):
        if not node.get('id'):
            ident=f'specimen-node-{i}'
            while ident in existing:ident+='x'
            node.set('id',ident);existing.add(ident)
    meta={'name':'Sorted font specimen','min_scale':1,'max_scale':1,'auto_satin':False,'reversible':False,'sortable':True,
          'combine_at_sort_indices':fl.metadata(source).get('combine_at_sort_indices',[]),'default_variant':'ltr'}
    installed=fl.install(meta,{'ltr.svg':ET.tostring(root)},s,verify=False,internal=True)
    result=batch(s.FONTS[installed['id']],['\ue000'],100,False,True,s)[0]['asset']
    project['layers']=[layer(result,'Color-sorted glyphs',(100-result['width'])/2,(100-result['height'])/2)]


def layer(asset,name,x,y):
    return dict(id=uuid.uuid4().hex,type='import',name=name,asset=asset['key'],x=x,y=y,width=asset['width'],height=asset['height'],
                color='#305c50',rotation=0,stitch='original',recolor=False,visible=True,locked=False)


def folder(key,s):
    return s.DATA/'font-samples'/s.safe_id(key)


def status(key,s):
    with LOCK:
        path=folder(key,s)/'status.json';value=json.loads(path.read_text())
        if value['state'] in ('queued','working') and key not in LIVE:
            value.update(state='interrupted',message='The service restarted. Generate again to reuse the glyphs already rendered.')
        return value


def start(data,s):
    config=settings(data,s);config['embroiderySettings']=preferences.new_document(s);key=uuid.uuid4().hex;path=folder(key,s)
    with s.JOBS_LOCK:
        if sum(j['state'] in ('queued','working') for j in s.JOBS.values())>=3:raise ValueError('Wait for a current preview or sample job to finish.')
        s.JOBS[key]={'state':'queued','created':time.time()}
    with LOCK:
        path.mkdir(parents=True);LIVE.add(key)
        s.write_atomic(path/'status.json',dict(id=key,state='queued',message='Waiting for Ink/Stitch…',config=config,pages=[]))
    s.POOL.submit(generate,key,config,s)
    return {'id':key}


def cancel(key,s):
    with LOCK:
        value=status(key,s)
        if value['state'] in ('queued','working'):CANCEL.add(key)
    return value


def page(key,index,s):
    value=status(key,s)
    if not str(index).isdigit() or not 0<=int(index)<len(value['pages']):raise ValueError('Choose a completed sample page.')
    return json.loads((folder(key,s)/(str(int(index))+'.json')).read_text())


def save_pages(key,s):
    value=status(key,s)
    if value['state']!='done':raise ValueError('Wait until all sample sheets are ready.')
    ids=[]
    for i in range(len(value['pages'])):
        p=page(key,i,s)['design'];target=s.DATA/'projects'/(p['id']+'.json')
        if not target.exists():s.write_atomic(target,p)
        ids.append(p['id'])
    return {'ids':ids}


class Cancelled(Exception):pass


def generate(key,config,s):
    path=folder(key,s)
    def update(**values):
        with LOCK:
            current=json.loads((path/'status.json').read_text());current.update(values);s.write_atomic(path/'status.json',current)
    def progress(message):update(state='working',message=message)
    def check():
        with LOCK:
            if key in CANCEL:raise Cancelled()
    try:
        with s.JOBS_LOCK:s.JOBS[key]['state']='working'
        check();progress('Reading the font’s glyph layers…');items=glyph_assets(config,progress,check,s);sheets=layout(items,config)
        source=fl.get_font(config['font'],s);summaries=[]
        for i,rows in enumerate(sheets):
            check();progress(f'Generating stitches for sheet {i+1} / {len(sheets)}…')
            entries=[(name,item,x,y,r+1,c+1) for r,row in enumerate(rows) for c,(name,item,x,y) in enumerate(row)]
            width=max(x+item['asset']['width'] for name,item,x,y,r,c in entries);height=max(y+item['asset']['height'] for name,item,x,y,r,c in entries)
            dx=(100-width)/2;dy=(100-height)/2
            design=dict(version=1,id=uuid.uuid4().hex,name=f'{source["name"]} · samples {i+1} of {len(sheets)}',fabric='#f8f5ee',grid=True,snap=True,embroiderySettings=preferences.validate(config.get('embroiderySettings')),
                        layers=[layer(v['asset'],name,x+dx,y+dy) for name,v,x,y,r,c in entries],fontSampleRecipe=config,
                        fontSamplePlan={'fontName':source['name'],'variant':config['variant'],'scale':config['scale'],'page':i+1,'pages':len(sheets),
                                        'glyphs':[{'name':name,'row':r,'column':c} for name,v,x,y,r,c in entries]})
            if config['colorSort']:sorted_page(design,source,s)
            export_id=uuid.uuid4().hex
            with s.JOBS_LOCK:s.JOBS[export_id]={'state':'queued','created':time.time()}
            s.export_job(export_id,design)
            with s.JOBS_LOCK:result=copy.deepcopy(s.JOBS[export_id])
            if result['state']!='done':raise ValueError(result['message'])
            result=result['result'];s.write_atomic(path/(str(i)+'.json'),{'design':design,'export':result})
            # Large fonts may span many pages. The persisted export is enough;
            # don't retain every page's stitch segments in the live queue.
            with s.JOBS_LOCK:s.JOBS.pop(export_id,None)
            summaries.append({'number':i+1,'glyphs':len(entries),'stitches':result['preview']['stitches'],'pes':result['pes'],'print':result['print'],'project':result['project']})
            update(pages=summaries,totalPages=len(sheets));check()
        progress('Packing the sample sheets…')
        archive_path=s.DATA/'exports'/(key+'-font-samples.zip')
        from interchange import print_sheet
        with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
            for i in range(len(sheets)):
                check()
                result=json.loads((path/(str(i)+'.json')).read_text())['export'];prefix=f'sheet-{i+1:03d}'
                for field,ext in [('pes','.pes'),('svg','.svg'),('project','.project.json'),('threadlist','.txt')]:archive.write(s.DATA/'exports'/Path(result[field]).name,prefix+ext)
                archive.writestr(prefix+'-key.html',print_sheet(result['id'],s))
        update(state='done',message=f'{len(sheets)} sample sheets ready',bundle='/files/'+archive_path.name)
    except Cancelled:update(state='cancelled',message='Cancelled. Completed sheets remain available; rendered glyphs are cached.')
    except Exception as exc:update(state='error',message=str(exc))
    finally:
        with LOCK:LIVE.discard(key);CANCEL.discard(key)
        with s.JOBS_LOCK:s.JOBS[key]['state']='done' if status(key,s)['state']=='done' else 'error'
