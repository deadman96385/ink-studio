"""Embroidery-file interchange and printable plans, using installed engines."""
import studio_runtime
import base64
import binascii
import copy
import html
import json
from pathlib import Path
import re
import tempfile
from lxml import etree as ET
from cutwork import prepare_cutwork,cutwork_pattern
from threads import inf_bytes

INPUTS={p.stem.removeprefix('inkstitch_input_').lower() for p in studio_runtime.resource('inx').glob('inkstitch_input_*.inx')}-{'col','edr','inf','json'}
OUTPUTS={p.stem.removeprefix('inkstitch_output_').lower() for p in studio_runtime.resource('inx').glob('inkstitch_output_*.inx')}
LABELS={'pes':'Brother PES','dst':'Tajima DST','jef':'Janome JEF','vp3':'Husqvarna / Pfaff VP3','exp':'Melco EXP','pec':'Brother PEC',
        'sew':'Janome SEW','xxx':'Singer XXX','u01':'Barudan U01','tbf':'Tajima TBF','edr':'RGB thread list (EDR)',
        'col':'Thread colors (COL)','inf':'Thread information (INF)','txt':'Thread list (TXT)','csv':'Stitch commands (CSV)',
        'json':'Stitch data (JSON)','svg':'Stitch plan SVG','png':'Simple stitch image (PNG)','png-realistic':'Realistic thread image (PNG)','zip':'Design bundle / repeated layout (ZIP)'}

def formats():
    from export_options import ZIP_FORMATS
    return {'inputs':sorted(INPUTS),'outputs':[{'key':k,'label':LABELS.get(k,k.upper())} for k in sorted(OUTPUTS|{'png','png-realistic','zip'})],
            'zipFormats':[{'key':k,'label':{'svg':'Editable SVG','project':'Project backup','threadlist':'Named thread list','png_simple':'Simple PNG','png_realistic':'Realistic PNG'}.get(k,LABELS.get(k,k.upper()))} for k in ZIP_FORMATS]}

def import_embroidery(data,s):
    name=str(data.get('name','design.pes'))[:150];ext=Path(name).suffix.lstrip('.').lower()
    if ext not in INPUTS:raise ValueError('Choose a supported embroidery file, such as PES, DST, JEF, EXP or VP3.')
    try:raw=base64.b64decode(data.get('data',''),validate=True)
    except (ValueError,TypeError,binascii.Error):raise ValueError('The embroidery file could not be read.')
    if not 0<len(raw)<=4*1024*1024:raise ValueError('Import an embroidery file smaller than 4 MB.')
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='embroidery-import-') as tmp:
        p=Path(tmp)/('design.'+ext);p.write_bytes(raw)
        preview=s.stitch_data(p)
        if preview['stitches']>100000:raise ValueError('Import a section with fewer than 100,000 stitches.')
        # Decode machine commands with pystitch, then hand explicit manual
        # paths to Ink/Stitch. Its 3.3.0 input renderer rounds some RGB channels
        # down and loses certain PES pauses; preserve those commands here.
        pattern=s.pystitch.read(str(p));root=s.svg_root();points=[];thread=0;last=None
        def flush():
            nonlocal points,last
            if not points:return
            if len(points)==1:points.append(points[0])
            color=pattern.threadlist[min(thread,len(pattern.threadlist)-1)].hex_color() if pattern.threadlist else '#000000'
            last=ET.SubElement(root,'{'+s.SVG+'}path',d='M'+' L'.join(f'{x/10:g},{y/10:g}' for x,y in points),style=f'fill:none;stroke:{color};stroke-width:.1')
            for key,value in [('stroke_method','manual_stitch'),('ties','3'),('min_stitch_length_mm','0'),('min_jump_stitch_length_mm','0')]:last.set('{'+s.STITCH+'}'+key,value)
            points=[]
        for x,y,command in pattern.stitches:
            command&=255
            if command==s.pystitch.STITCH:points.append((x,y));continue
            flush()
            if command==s.pystitch.COLOR_CHANGE:thread+=1
            elif command in (s.pystitch.TRIM,s.pystitch.STOP) and last is not None:
                last.set('{'+s.STITCH+'}'+('trim_after' if command==s.pystitch.TRIM else 'stop_after'),'True')
        flush();svg=ET.tostring(root)
    # Normalization takes the engine lock itself.
    asset=s.import_svg({'svg':svg.decode('utf-8'),'name':name})
    if len(asset['svg'].encode())>8*1024*1024:raise ValueError('This stitch plan is too large for an editable backup. Import a smaller section.')
    return {'asset':asset,'preview':preview,'note':'Imported as manual stitches. Resizing changes stitch length and density; the original digitizing shapes cannot be recovered from a machine file.'}

def export_result(job_id,s):
    job_id=s.safe_id(job_id)
    with s.JOBS_LOCK:job=copy.deepcopy(s.JOBS.get(job_id))
    if job and job['state']=='done':return job['result']
    # Saved exports outlive the in-memory queue and service restarts.
    projects=list((s.DATA/'exports').glob(job_id+'-*.project.json'))
    if len(projects)!=1:raise ValueError('Generate a preview before opening this export.')
    base=projects[0].name.removesuffix('.project.json');folder=s.DATA/'exports'
    if not (folder/(base+'.pes')).exists() or not (folder/(base+'.svg')).exists():raise ValueError('This export is incomplete. Generate a new preview.')
    cuts=prepare_cutwork((folder/(base+'.svg')).read_bytes(),s)[1]
    return {'cutwork':bool(cuts),'cutworkBundle':'/files/'+base+'-cutwork.zip' if cuts else None,'id':job_id,'preview':s.stitch_data(folder/(base+'.pes')),'pes':'/files/'+base+'.pes','svg':'/files/'+base+'.svg',
            'project':'/files/'+base+'.project.json','threadlist':'/files/'+base+'.txt','print':'/print/'+job_id}

def export_format(data,s):
    fmt=data.get('format')
    if fmt not in OUTPUTS|{'png','png-realistic','zip'}:raise ValueError('Choose a supported export format.')
    result=export_result(data.get('id'),s);svgfile=s.DATA/'exports'/Path(result['svg']).name;base=svgfile.stem
    if fmt in ('png','png-realistic') or fmt=='zip' and 'options' in data:
        from export_options import generate
        return generate(data,result,s)
    cuts=prepare_cutwork(svgfile.read_bytes(),s)[1]
    if cuts and fmt not in ('exp','inf','zip','png','svg','txt'):raise ValueError('Cutwork needs the EXP + INF bundle and a compatible cutting-needle setup. Choose ZIP for both matching files.')
    if cuts and fmt=='zip':return {'url':result['cutworkBundle']}
    filename=base+('-stitch-plan.svg' if fmt=='svg' else '.'+fmt)
    target=s.DATA/'exports'/filename
    if fmt=='pes':return {'url':result['pes']}
    if fmt=='txt':return {'url':result['threadlist']}
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='format-') as tmp:
        if cuts and fmt in ('exp','inf'):
            pattern=cutwork_pattern((s.DATA/'exports'/Path(result['pes']).name).read_bytes(),cuts,s)
            s.pystitch.write(pattern,str(target),{'encode':False})
        elif cuts and fmt=='svg':target.write_bytes(stitch_svg(result['preview'],s))
        elif fmt=='zip':
            import zipfile
            with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
                for suffix in ('.pes','.svg','.project.json','.txt'):
                    f=s.DATA/'exports'/(base+suffix)
                    if f.exists():z.write(f,base[33:]+suffix)
        elif fmt=='png':
            plan=Path(tmp)/'plan.svg';plan.write_bytes(stitch_svg(result['preview'],s))
            s.run(['inkscape',str(plan),'--export-filename='+str(target),'--export-dpi=300','--export-background-opacity=0'])
        elif fmt in ('inf','col','edr'):
            pattern=s.pystitch.read(str(s.DATA/'exports'/Path(result['pes']).name))
            if fmt=='inf':target.write_bytes(inf_bytes(pattern))
            else:s.pystitch.write(pattern,str(target))
        else:
            encoded=s.run([s.ENGINE,'--extension=output','--format='+fmt,str(svgfile)],240,headless=True)
            if not encoded:raise ValueError('The engine produced no file for this format.')
            target.write_bytes(encoded)
    return {'url':'/files/'+filename}

def stitch_svg(preview,s):
    width=max(1,preview['width']);height=max(1,preview['height']);x,y=preview['bounds'][:2]
    root=ET.Element('{'+s.SVG+'}svg',nsmap={None:s.SVG},width=f'{width+2}mm',height=f'{height+2}mm',viewBox=f'{x-1} {y-1} {width+2} {height+2}')
    previous=None;d=[];thread=None
    def flush():
        if d:ET.SubElement(root,'{'+s.SVG+'}path',d=' '.join(d),fill='none',stroke=preview['threads'][thread]['color'],attrib={'stroke-width':'.18','stroke-linecap':'round','stroke-linejoin':'round'})
    for x1,y1,x2,y2,k in preview['segments']:
        if k!=thread:flush();d=[];previous=None;thread=k
        if previous!=(x1,y1):d.append(f'M{x1},{y1}')
        d.append(f'L{x2},{y2}');previous=(x2,y2)
    flush();return ET.tostring(root)

def print_sheet(job_id,s):
    r=export_result(job_id,s);p=r['preview'];project=json.loads((s.DATA/'exports'/Path(r['project']).name).read_text())
    name=html.escape(str(project.get('name','Embroidery design')));rows=[]
    for i,t in enumerate(p['threads']):
        rows.append(f'<tr><td>{i+1}</td><td><i style="background:{t["color"]}"></i></td><td>{html.escape(t["name"])}</td><td>{html.escape(t.get("brand", ""))}</td><td>{html.escape(t.get("number", ""))}</td><td>{t["color"]}</td></tr>')
    svg=stitch_svg(p,s).decode()
    machine_note='Cutwork · use the matching EXP and INF files with compatible cutting needles.' if r.get('cutwork') else 'Brother PP1 · 100 × 100 mm hoop.'
    swatches=swatch_key(project)+font_sample_key(project)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{name} · Stitch sheet</title><style>
    body{{font:15px system-ui,sans-serif;color:#243d35;max-width:850px;margin:24px auto;padding:0 20px}}button{{font:inherit;padding:14px;border:1px solid #bbb;border-radius:10px;background:#214d40;color:white}}h1{{font-size:25px}}.plan{{padding:10px;border:1px solid #ccc;display:inline-block}}.plan svg{{display:block;max-width:none}}table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{padding:9px;text-align:left;border-bottom:1px solid #ddd}}i{{display:block;width:22px;height:22px;border:1px solid #888}}.ruler{{width:50mm;border-top:1px solid;margin-top:18px;font-size:11px}}@page{{size:auto;margin:15mm}}@media print{{body{{margin:0;padding:0}}button,.help{{display:none}}tr,.plan{{break-inside:avoid}}thead{{display:table-header-group}}}} </style></head><body><button onclick="window.print()">Print / Save PDF</button><p class="help">On iPad, use Print or Safari Share → Print, then save the print preview as a PDF. Print at 100% for the actual-size plan; check the 50 mm scale line.</p><h1>{name}</h1><p>{p['width']:g} × {p['height']:g} mm · {p['stitches']:,} stitches · {len(p['threads'])} thread steps · {p['trims']} trims · {p['stops']} extra stops · {p.get('colorChanges',max(0,len(p['threads'])-1))} color changes</p><div class="plan">{svg}</div><div class="ruler">50 mm</div>{swatches}<h2>Thread order</h2><table><thead><tr><th>Step</th><th>Color</th><th>Thread</th><th>Brand / range</th><th>Number</th><th>RGB</th></tr></thead><tbody>{''.join(rows)}</tbody></table><p>{machine_note} Check fabric and stabilizer with a test sew.</p></body></html>'''.encode()


def swatch_key(project):
    plan=project.get('swatchPlan')
    if not isinstance(plan,dict):return ''
    axes=plan.get('axes',[]);samples=plan.get('samples',[])
    if not isinstance(axes,list) or not 1<=len(axes)<=2 or any(not isinstance(a,dict) for a in axes) or not isinstance(samples,list) or len(samples)>36:return ''
    esc=lambda value:html.escape(str(value))
    heads=''.join('<th>'+esc(a.get('label','Parameter'))+'</th>' for a in axes)
    rows=[]
    for sample in samples:
        if not isinstance(sample,dict) or not isinstance(sample.get('values'),dict):continue
        values=''.join('<td>'+esc(sample['values'].get(a.get('key'),''))+'</td>' for a in axes)
        rows.append('<tr><td>'+esc(sample.get('number',''))+'</td><td>'+esc(sample.get('row',''))+' / '+esc(sample.get('column',''))+'</td>'+values+'</tr>')
    return '<h2>Swatch settings</h2><p>Numbers identify samples; row and column positions are counted from the top left. Use the same fabric, stabilizer and thread as your final design.</p><table><thead><tr><th>Sample</th><th>Row / column</th>'+heads+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table>'


def font_sample_key(project):
    plan=project.get('fontSamplePlan')
    if not isinstance(plan,dict) or not isinstance(plan.get('glyphs'),list) or len(plan['glyphs'])>5000:return ''
    esc=lambda v:html.escape(str(v))
    rows=''.join('<tr><td>'+esc(g.get('name',''))+'</td><td>'+esc(g.get('row',''))+' / '+esc(g.get('column',''))+'</td></tr>' for g in plan['glyphs'] if isinstance(g,dict))
    return '<h2>Font sample key</h2><p>'+esc(plan.get('fontName',''))+' · '+esc(plan.get('variant',''))+' · '+esc(plan.get('scale',''))+'% · Sheet '+esc(plan.get('page',''))+' of '+esc(plan.get('pages',''))+'</p><p>Rows and columns count from the top left. Glyph names include alternate forms and ligatures.</p><table><thead><tr><th>Glyph</th><th>Row / column</th></tr></thead><tbody>'+rows+'</tbody></table>'
