"""Native controls for the installed image/ZIP exporters and PP1 validation."""
import studio_runtime
import io,json,re,struct,tempfile,uuid,zipfile
from pathlib import Path
from lxml import etree as ET
from cutwork import prepare_cutwork,cutwork_pattern
from element_info import RUNTIME
from threads import named_pes,inf_bytes

ZIP_FORMATS=['pec','pes','exp','dst','jef','vp3','xxx','sew','u01','tbf','pmv','gcode','plt','qcc','edr','col','inf','threadlist','svg','png_realistic','png_simple','project']
DEFAULTS={'dpi':300,'lineWidth':.3,'background':'transparent','color':'#ffffff','filename':'',
    'formats':['pes','svg','project','threadlist'],'xRepeats':1,'yRepeats':1,'xSpacing':100,'ySpacing':100,
    'simpleDpi':300,'realisticDpi':300,'destination':'pp1'}

def options(value,s):
    if not isinstance(value,dict) or set(value)-set(DEFAULTS):raise ValueError('Invalid image or ZIP options.')
    o={**DEFAULTS,**value}
    for k,low,high in [('dpi',100,2000),('simpleDpi',100,2000),('realisticDpi',100,2000),('xRepeats',1,20),('yRepeats',1,20),('xSpacing',-1000,1000),('ySpacing',-1000,1000),('lineWidth',.01,5)]:
        if isinstance(o[k],bool):raise ValueError('Invalid '+k+'.')
        o[k]=s.number(o[k],low,high,k)
        if k in ('dpi','simpleDpi','realisticDpi','xRepeats','yRepeats'):
            if int(o[k])!=o[k]:raise ValueError(k+' must be a whole number.')
            o[k]=int(o[k])
    if o['background'] not in ('transparent','fabric','custom') or not isinstance(o['color'],str) or not re.fullmatch('#[0-9a-fA-F]{6}',o['color']):raise ValueError('Choose a background and a valid color.')
    if o['destination'] not in ('pp1','other'):raise ValueError('Choose PP1 or another machine.')
    if not isinstance(o['filename'],str) or len(o['filename'])>80 or re.search(r'[/\\\x00-\x1f\x7f:<>"|?*]',o['filename']) or o['filename'].strip(' .') in ('.','..'):raise ValueError('Use a filename up to 80 characters, without slashes or reserved punctuation.')
    o['filename']=o['filename'].strip(' .')
    if not isinstance(o['formats'],list) or not o['formats'] or any(not isinstance(k,str) or k not in ZIP_FORMATS for k in o['formats']):raise ValueError('Select one or more ZIP file types.')
    o['formats']=list(dict.fromkeys(o['formats']))
    return o

def generate(data,result,s):
    mode=data['format'];o=options(data.get('options',{}),s);folder=s.DATA/'exports'
    original=(folder/Path(result['svg']).name).read_bytes()
    project=json.loads((folder/Path(result['project']).name).read_text(encoding='utf-8'))
    source,cuts=prepare_cutwork(original,s)
    if cuts and mode=='zip':
        if set(o['formats'])-{'exp','inf','svg','threadlist','png_simple','png_realistic','project'}:raise ValueError('Cutwork bundles support EXP, INF, SVG, thread lists, images and project backup.')
        if ('exp' in o['formats'])!=('inf' in o['formats']):raise ValueError('Include both EXP and INF for matching cutwork files.')
        o['destination']='other'
    import svg_structure
    root=s.xml(source)
    if svg_structure.has_masks(root):raise ValueError('Use Digitize → Prepare SVG artwork to convert opacity masks before exporting stitches.')
    view=root.find('{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}namedview')
    if view is None:view=ET.SubElement(root,'{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}namedview')
    color=project.get('fabric','#ffffff') if o['background']=='fabric' else o['color']
    if not isinstance(color,str) or not re.fullmatch('#[0-9a-fA-F]{6}',color):color='#ffffff'
    view.set('pagecolor',color)
    stem=o['filename'] or re.sub(r'[^a-zA-Z0-9_-]+','-',str(project.get('name','design'))).strip('-')[:60] or 'design'
    # URLs stay ASCII; the ZIP entries retain the chosen Unicode filename.
    slug=re.sub(r'[^a-zA-Z0-9_-]+','-',stem).strip('-')[:60] or 'design'
    filename=uuid.uuid4().hex+'-'+slug+('-realistic.png' if mode=='png-realistic' else '.png' if mode=='png' else '.zip')
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-export-') as tmp:
        path=Path(tmp)/'source.svg';path.write_bytes(ET.tostring(root))
        config=Path(tmp)/'options.json';config.write_text(json.dumps({'source':str(path),'mode':mode,'options':o}),encoding='utf-8')
        raw=s.run(studio_runtime.worker_command('--native-export',str(config),temporary=tmp),300,headless=True)
        if mode!='zip':
            if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Ink/Stitch did not produce an image.')
            width,height=struct.unpack('>II',raw[16:24]);(folder/filename).write_bytes(raw)
            return {'url':'/files/'+filename,'pixels':[width,height],'options':o,'files':[filename[33:]]}
        with zipfile.ZipFile(io.BytesIO(raw)) as z:files={n:z.read(n) for n in z.namelist()}
        pes=named_pes(files['design.pes'],{'threadBook':{**project.get('threadBook',{}),**cuts}})
        p=Path(tmp)/'design.pes';p.write_bytes(pes);preview=s.stitch_data(p)
        if o['destination']=='pp1' and max(preview['width'],preview['height'])>100:raise ValueError('The finished repeated stitches exceed the PP1 100 × 100 mm hoop. Reduce spacing or repeats.')
        files['design.pes']=pes
        pattern=cutwork_pattern(pes,cuts,s) if cuts else s.pystitch.read(str(p))
        # Use the named v6 thread table for color files without re-encoding PES.
        for ext in ('inf','col','edr'):
            if ext not in o['formats']:continue
            target=Path(tmp)/('design.'+ext)
            if ext=='inf':files['design.inf']=inf_bytes(pattern)
            else:s.pystitch.write(pattern,str(target),{'encode':False});files['design.'+ext]=target.read_bytes()
        if cuts and 'exp' in o['formats']:
            target=Path(tmp)/'design.exp';s.pystitch.write(pattern,str(target),{'encode':False});files['design.exp']=target.read_bytes()
        if 'pes' not in o['formats']:files.pop('design.pes',None)
        if 'svg' in o['formats']:files['design.svg']=original
        if 'project' in o['formats']:files['design.project.json']=json.dumps(project,ensure_ascii=False,indent=2).encode()
        if 'threadlist' in o['formats']:
            used=list(dict.fromkeys(f'{t["name"]} #{t["number"]} - {t["brand"]} ({t["color"]})' for t in preview['threads']))
            files['design_threadlist.txt']=(f'Design Details\n==============================\n\nTitle: {stem}\nSize (mm): {preview["width"]:g} x {preview["height"]:g}\nStitches: {preview["stitches"]}\nColors: {len(set(t["color"] for t in preview["threads"]))}\nRepeats: {o["xRepeats"]} x {o["yRepeats"]}; spacing {o["xSpacing"]:g} x {o["ySpacing"]:g} mm\n\n'+s.threadlist_text(preview['threads'])+'\nThread Used\n===========================\n\n'+'\n'.join(used)+'\n').encode()
        renamed={stem+n[len('design'):]:raw for n,raw in files.items()}
        with zipfile.ZipFile(folder/filename,'w',zipfile.ZIP_DEFLATED) as z:
            for name,contents in renamed.items():z.writestr(name,contents)
    return {'url':'/files/'+filename,'options':o,'files':list(renamed),'preview':preview,
        'note':'Machine files and images contain the repeated layout, sewn one color across all copies. Editable SVG and project backup retain the single original design. Images use the artwork orientation; machine files use the document export rotation.'}
