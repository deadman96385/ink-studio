"""Color-list readers and installed Ink/Stitch recoloring, without changing source layers."""
import base64
import binascii
from limits import MAX_LAYERS
import copy
import json
import hashlib
from pathlib import Path
import re
import tempfile
import uuid

import pystitch
from lxml import etree as ET
from threads import palettes, thread_entries, named_pes, inf_bytes
from cutwork import prepare_cutwork


def import_threadlist(data,s):
    ext=Path(str(data.get('name',''))).suffix.lower()
    if ext not in ('.txt','.edr','.col','.inf'):raise ValueError('Choose a TXT, EDR, COL or INF thread list.')
    try:raw=base64.b64decode(data.get('data',''),validate=True)
    except (ValueError,TypeError,binascii.Error):raise ValueError('The thread-list file could not be read.')
    if not 0<len(raw)<=500000:raise ValueError('Choose a thread list smaller than 500 KB.')
    rows=[]
    if ext!='.txt':
        if ext=='.edr' and len(raw)%4:raise ValueError('An EDR list needs complete four-byte color records.')
        if ext=='.inf' and (len(raw)<16 or not 1<=int.from_bytes(raw[12:16],'big')<=1000):raise ValueError('An INF list needs 1–1,000 complete color records.')
        try:
            with tempfile.TemporaryDirectory(prefix='threadlist-') as tmp:
                path=Path(tmp)/('colors'+ext);path.write_bytes(raw);pattern=pystitch.read(str(path))
            for t in pattern.threadlist:
                row={'color':t.hex_color(),'name':t.description or '', 'number':t.catalog_number or '', 'brand':t.brand or ''}
                m=re.fullmatch(r'Cut\s*([1-4])',row['name'])
                if m:row['cutworkNeedle']=int(m[1])
                rows.append(row)
            if ext=='.col':
                lines=[x for x in raw.decode('utf-8-sig').splitlines() if x.strip()]
                if int(lines[0])!=len(rows) or len(lines)!=len(rows)+1:raise ValueError()
                for line in lines[1:]:
                    parts=line.split(',')
                    if len(parts)!=4 or any(not 0<=int(v)<=255 for v in parts[1:]):raise ValueError()
            if ext=='.inf' and (len(raw)<16 or int.from_bytes(raw[12:16],'big')!=len(rows)):raise ValueError()
        except Exception as exc:raise ValueError('This color-list file is incomplete or invalid.') from exc
    else:
        try:lines=raw.decode('utf-8-sig').splitlines()
        except UnicodeError:raise ValueError('Save the text list as UTF-8 before importing it.')
        palette=None
        if data.get('method')=='catalog':
            palette=next((p for p in palettes(s) if p['key']==data.get('palette')),None)
            if not palette:raise ValueError('Choose the palette used by the catalog numbers in this list.')
        for line in lines:
            line=line.strip()
            # Only numbered thread rows or bare hexadecimal colors; headers and
            # Ink/Stitch's trailing unordered "Thread Used" section are ignored.
            m=re.match(r'^\d+[.)]?\s+(.+)$',line)
            if not m:
                if re.fullmatch(r'#[0-9a-fA-F]{6}',line):rows.append({'color':line})
                continue
            label=m[1]
            if palette:
                numbers=set(re.findall(r'[\w.-]+',label));matches=[t for t in palette['colors'] if t['number'] and t['number'] in numbers]
                if len(matches)!=1:raise ValueError(f'Row {len(rows)+1} has no unique catalog-number match. Check the list or choose a different palette.')
                rows.append(copy.deepcopy(matches[0]));continue
            color=re.search(r'#[0-9a-fA-F]{6}(?![0-9a-fA-F])',label)
            if not color:raise ValueError(f'Row {len(rows)+1} has no RGB color. Choose catalog-number matching for a numbered thread list.')
            row={'color':color[0]}
            ink=re.fullmatch(r'(.*?)\s+#(.*?)\s+-\s+(.*?)\s+\(#[0-9a-fA-F]{6}\)',label)
            if ink:row.update(name=ink[1],number=ink[2],brand=ink[3])
            else:row['name']=re.sub(r'\(?#[0-9a-fA-F]{6}\)?','',label).strip()[:140]
            rows.append(row)
    return {'name':Path(str(data.get('name','Thread list'))).name[:100],'colors':thread_entries(rows,1000)}


def threadlist_text(threads):
    # Ink/Stitch-compatible numbered rows; Studio's own exports can be reapplied.
    return 'Thread Order\n===========================\n\n'+''.join(f'{i+1} {t["name"]} #{t["number"]} - {t["brand"]} ({t["color"]})\n' for i,t in enumerate(threads))


def preview_svg(raw,project,s,tmp):
    svg,cut_threads=prepare_cutwork(raw,s)
    path=Path(tmp)/'preview.svg';path.write_bytes(svg)
    encoded=s.run([s.ENGINE,'--extension=output','--format=pes','--version=6',str(path)],headless=True)
    encoded=named_pes(encoded,{**project,'threadBook':{**project.get('threadBook',{}),**cut_threads}})
    pes=Path(tmp)/'preview.pes';pes.write_bytes(encoded)
    return s.stitch_data(pes)


def prepare_threadwork(data,s):
    project=copy.deepcopy(data.get('project'))
    if not isinstance(project,dict) or project.get('version')!=1 or not isinstance(project.get('layers'),list) or len(project['layers'])>MAX_LAYERS or any(not isinstance(l,dict) for l in project['layers']):raise ValueError('Open a valid Ink Studio design first.')
    active=[l for l in project.get('layers',[]) if l.get('visible',True) and l.get('type')!='image' and l.get('role','artwork')=='artwork']
    if not active:raise ValueError('Add visible stitched artwork first.')
    if data.get('colors') is not None:
        if any(l.get('locked') for l in active):raise ValueError('Unlock the visible stitched layers before applying colors.')
        if len(project['layers'])>=MAX_LAYERS:raise ValueError('Leave one free layer for the colored SVG copy.')
    # Keep global positions in the native project, outside the embedded SVG.
    source=s.build_svg({k:v for k,v in project.items() if k not in ('origin','frameOut')})
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='threadwork-') as tmp:
        source_path=Path(tmp)/'source.svg';source_path.write_bytes(prepare_cutwork(source,s)[0])
        x,y,w,h=s.bounds(source_path,sewing=True)
        if x<-.1 or y<-.1 or x+w>100.1 or y+h>100.1:raise ValueError('Fit the artwork inside the 100 mm hoop first.')
        # Include native global positions for the actual preview, while the
        # source color-run inventory does not depend on its coordinate origin.
        full=s.xml(source);s.attach_global_commands(full,project)
        before=preview_svg(ET.tostring(full),project,s,tmp)
        for t in before['threads']:
            if t.get('brand')=='Cutwork' and t.get('number') in ('1','2','3','4'):t['cutworkNeedle']=int(t['number'])
        rows=data.get('colors')
        if rows is None:return {'preview':before,'colors':before['threads']}
        rows=thread_entries(rows,1000)
        if len(rows)!=len(before['threads']):raise ValueError(f'The design has {len(before["threads"])} thread steps; the list has {len(rows)}. Match the number of rows before applying.')
        # The desktop extension maps solid element-color runs. A gradient or
        # tartan has several generated colors inside one element: split it first.
        root=s.xml(source)
        if any('url(' in e.get('style','') or e.get('{'+s.STITCH+'}fill_method') in ('linear_gradient_fill','tartan_fill') for e in root.iter()):
            raise ValueError('Separate gradient or tartan color blocks before applying a thread list to this design.')
        # Reuse the installed extension for color-run assignment and INF needle
        # recognition; its native parameters, helpers and command links survive.
        p=pystitch.EmbPattern()
        for row in rows:
            t=pystitch.EmbThread();t.set_hex_color(row['color']);t.description='Cut'+str(row['cutworkNeedle']) if row.get('cutworkNeedle') else row['name'];t.catalog_number=row['number'];t.brand=row['brand'];p.add_thread(t)
        colors=Path(tmp)/'colors.inf';colors.write_bytes(inf_bytes(p))
        changed=s.run([s.ENGINE,'--extension=apply_threadlist','--filepath='+str(colors),'--method=1',str(source_path)],headless=True)
        # Restrict generated output with the same SVG validator used for imports.
        changed_doc=s.sanitize_svg(changed)
        for group in changed_doc.iter():
            recipe=group.get('{'+s.STITCH+'}satin-multicolor')
            if recipe:
                settings=json.loads(recipe);bands=[e for e in group if ET.QName(e).localname=='path']
                if len(settings.get('colors',[]))==len(bands):
                    for entry,band in zip(settings['colors'],bands):
                        style=dict(x.split(':',1) for x in band.get('style','').split(';') if ':' in x)
                        if re.fullmatch(r'#[0-9a-fA-F]{6}',style.get('stroke','')):entry['value']=style['stroke']
                    group.set('{'+s.STITCH+'}satin-multicolor',json.dumps(settings))
        changed=ET.tostring(changed_doc)
    # This is our own millimeter SVG, already validated above. Avoid another
    # Inkscape normalization pass: rounding curves there can change stitch rows.
    group=ET.Element('{'+s.SVG+'}g',nsmap=s.NS,transform=f'translate({-x},{-y})')
    for child in changed_doc:group.append(copy.deepcopy(child))
    svg=ET.tostring(group,encoding='unicode');key=hashlib.sha256(svg.encode()).hexdigest()
    asset={'key':key,'width':w,'height':h,'svg':svg,'name':'Thread-colored design'}
    s.write_atomic(s.DATA/'assets'/(key+'.json'),asset)
    layer={'id':str(uuid.uuid4()),'type':'import','name':'Thread-colored design','asset':asset['key'],'x':x,'y':y,
           'width':asset['width'],'height':asset['height'],'rotation':0,'stitch':'original','recolor':False,'color':rows[0]['color'],'visible':True}
    book={t['color']:{k:t[k] for k in ('name','number','brand')} for t in rows}
    proposed={**project,'layers':[layer],'threadBook':{**project.get('threadBook',{}),**book}}
    raw=s.build_svg(proposed)
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='threadwork-check-') as tmp:
        after=preview_svg(raw,proposed,s,tmp)
    expected=[]
    for t in rows:
        if not expected or expected[-1]!=t['color']:expected.append(t['color'])
    actual=[t['color'].lower() for t in after['threads']]
    # A complex SVG can expose a different element order from its stitch plan.
    # Never silently apply a shifted or partial color list in that case.
    if actual!=expected:raise ValueError('This SVG has a different internal color order. Separate its paths and retry the thread list.')
    if after['width']>100 or after['height']>100:raise ValueError('The generated stitches exceed the 100 mm hoop.')
    note='The colored copy keeps SVG paths, stitch parameters and commands. Original layers stay hidden. Use Separate SVG paths to edit individual paths in the copy.'
    if len(actual)<len(rows):note+=' Adjacent identical colors combine into one thread step; add a pause command if you need a stop between them.'
    return {'asset':asset,'layer':layer,'threadBook':book,'preview':after,'beforeSteps':len(before['threads']),
            'sourceIds':[l['id'] for l in active], 'note':note}
