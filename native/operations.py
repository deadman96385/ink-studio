"""Touch-facing forms for the installed Ink/Stitch conversion extensions."""
import studio_runtime
from limits import MAX_LAYERS
import copy
import io
import math
import re
from pathlib import Path
import tempfile

import inkex
from lxml import etree as ET
from digitizing import SVG, STITCH, SODIPODI, geometry, from_path
from advanced import layer_mode
from cutwork import prepare_cutwork
from threads import named_pes

INK='http://www.inkscape.org/namespaces/inkscape'
XLINK='http://www.w3.org/1999/xlink'

def num(key,label,default,low,high):
    return dict(key=key,label=label,kind='number',default=default,min=low,max=high)
def flag(key,label,default=False):
    return dict(key=key,label=label,kind='boolean',default=default)
def choice(key,label,default,options):
    return dict(key=key,label=label,kind='select',default=default,options=options)
def tool(key,label,group,help,fields=(),modes=()):
    return dict(key=key,label=label,group=group,help=help,fields=list(fields),modes=list(modes))

TOOLS=[
    tool('transform_elements','Rotate / mirror with stitch directions','Design paths','Rotate and mirror the selection around its shared center. Choose whether fill directions turn with the artwork or stay fixed on the fabric. Attached guides and stitch positions follow the geometry. Results are editable SVG layers; Separate paths exposes their individual settings. Preview first; Undo restores native lettering and shapes.',[
        num('rotate','Rotation (°)',0,-180,180),flag('flip-horizontally','Mirror horizontally'),flag('flip-vertically','Mirror vertically'),
        flag('followAngles','Move fill directions with artwork',True),flag('keepSource','Keep hidden source copies',True)]),
    tool('remove_duplicated_points','Remove repeated needle points','Cleanup','Remove points repeated within a look-back window. Useful for imported manual/bean stitch plans. Curves are flattened by Ink/Stitch; preview before applying. Every subpath is retained as an editable path.',[
        num('num_points','Look back this many points',10,1,5000),num('distance','Distance tolerance (mm)',.01,0,500)],['running','bean','manual','zigzag','original']),
    tool('duplicate_params','Copy stitch settings','Stitch settings','Copy the exact Ink/Stitch parameters from one source path to all other selected paths. Thread colors and geometry stay with each target. Choose a source with one path; separate lettering or SVG first if needed. Results become editable paths; Undo restores native text and shapes.',[
        dict(key='source_id',label='Copy settings from',kind='source',default='')]),
    tool('remove_embroidery_settings','Remove stitch settings or commands','Cleanup','Remove all or one Ink/Stitch parameter, visual command, trim or pause from selected artwork. Results become editable paths, using engine defaults for removed settings. Review the stitches before applying.',[
        choice('del_params','Stitch parameters to remove','none',[['none','Keep parameters'],['all','Remove all parameters']]),
        choice('del_commands','Commands to remove','none',[[k,n] for k,n in [('none','Keep commands'),('all','Remove all commands'),('starting_point','Starting position'),('ending_point','Ending position'),('target_point','Target position'),('autoroute_start','Route start'),('autoroute_end','Route end'),('stop','Pause after sewing'),('trim','Trim after sewing'),('ignore_object','Ignore object'),('satin_cut_point','Satin cut point'),('ignore_layer','Ignore layer')]])]),
    tool('apply_attribute','Set an embroidery parameter','Stitch settings','Apply one Ink/Stitch parameter to every selected path. Values use the engine’s parameter names; normal stitch controls remain available after applying. Results become editable paths. Invalid combinations leave the original design unchanged.',[
        dict(key='key',label='Embroidery parameter',kind='text',default='min_stitch_length_mm',maxLength=80),
        dict(key='value',label='Value',kind='text',default='0.1',maxLength=2000),flag('remove','Remove this parameter instead')]),
    tool('jump_to_trim','Jumps → trim or pause','Commands','Insert trim or pause commands between selected same-color paths, using their actual stitch endpoints. Set a minimum and optional maximum jump distance. Commands become editable native stitch parameters.',[
        choice('command','Command','trim',[['trim','Trim'],['stop','Pause']]),num('minimum-jump-length','Minimum jump length (mm)',3,0,100),num('maximum-jump-length','Maximum jump length (mm; 0 = unlimited)',0,0,10000)]),
    tool('path_offset','Offset / inset paths','Design paths','Grow or shrink outlines by an exact millimeter distance using Inkscape. Positive grows closed shapes; negative insets them. Open paths shift to one side. Stitch settings and editable curves are retained.',[
        num('distance','Offset distance (mm)',1,-20,20),choice('join','Corner join','round',[[k,n] for k,n in [('round','Round'),('bevel','Bevel'),('miter','Miter'),('miter-clip','Miter clip'),('extrp_arc','Extrapolated arc'),('extrp_arc1','Extrapolated arc 1'),('extrp_arc2','Extrapolated arc 2'),('extrp_arc3','Extrapolated arc 3')]]),
        num('miter','Miter limit',4,1,20),flag('forceMiter','Force miter beyond its limit'),flag('keepSource','Keep original hidden')],['fill','running','bean','zigzag','original']),
    tool('stroke_area','Stroke area → filled shape','Design paths','Turn the visible width of an outline into an editable filled region. Choose its physical width, end caps and corners, then preview the generated fill stitches.',[
        num('width','Stroke area width (mm)',3,.2,20),choice('cap','Open end caps','round',[['round','Round'],['butt','Butt'],['square','Square']]),
        choice('join','Stroke corners','round',[['round','Round'],['miter','Miter'],['bevel','Bevel']]),num('miter','Miter limit',4,1,20),flag('keepSource','Keep original hidden')],['running','bean','zigzag','original']),
    tool('applique','Build appliqué steps','Fabric & appliqué','Create editable placement, tack-down and finishing paths from closed filled shapes. Stops follow placement (add fabric) and tack-down (trim excess). Preview the sequence before applying.',[
        choice('sequence','Multiple pieces','piece',[['piece','Complete each piece in order'],['stage','All placements, then tack-downs, then edges']]),
        dict(key='placementColor',label='Placement thread',kind='color',default='#416580'),
        dict(key='tackColor',label='Tack-down thread',kind='color',default='#b96548'),
        dict(key='finishColor',label='Finishing thread',kind='color',default='#203f38'),
        num('stitchLength','Running stitch length (mm)',2.5,.5,6),
        choice('tackStitch','Tack-down stitch','running',[['running','Running stitch'],['bean','Bean stitch'],['zigzag','Zigzag']]),
        num('tackInset','Tack-down inset (mm)',.5,0,3),num('tackWidth','Zigzag tack-down width (mm)',1,.3,3),num('tackSpacing','Zigzag tack-down spacing (mm)',1,.2,2),
        choice('finishStitch','Finishing edge','satin',[['satin','Satin with center underlay'],['zigzag','Zigzag'],['e_stitch','E stitch'],['bean','Bean outline'],['running','Running outline']]),
        num('finishWidth','Satin / zigzag edge width (mm)',3,.6,6),num('finishSpacing','Edge stitch spacing (mm)',.4,.2,2),
        flag('keepSource','Keep the original shape hidden',True)],['fill']),
    tool('stroke_to_satin','Stroke → satin','Satin','Convert the width of a running line into two editable satin rails. Set the source width here before previewing.',[
        num('sourceWidth','Source line width (mm)',3,.6,10)],['running','bean','zigzag']),
    tool('fill_to_satin','Fill → satin','Satin','Convert filled shapes to satin columns. Automatic rungs work well for simple narrow shapes. For complex shapes, draw running guide lines across the fill and include them in the selection.',[
        choice('guide','Stitch direction guides','auto',[['auto','Automatic across the short side'],['horizontal','Horizontal stitches'],['vertical','Vertical stitches'],['selected','Use selected running lines']]),
        flag('skip_end_section','Skip end sections'),num('pull_compensation_mm','Pull compensation (mm)',0,0,2),
        flag('center','Center-walk underlay'),flag('contour','Contour underlay'),flag('zigzag','Zigzag underlay'),
        choice('keep','Keep source shapes','none',[['none','Replace source'],['original_fills','Keep original fills'],['original_fills_and_rungs','Keep fills and guide lines'],['unused_subpaths','Keep unused subpaths']])],['fill','running','bean']),
    tool('satin_to_stroke','Satin → running line','Satin','Extract a running line through satin columns.',[
        flag('keep_satin','Keep the original satin')],['satin']),
    tool('flip','Swap satin rails','Satin','Exchange the first and second rail without changing the outline.',[],['satin']),
    tool('cut_satin','Cut satin at points / lines','Satin','Place a satin cut point in Positions & commands, or select running lines crossing both rails. Each cut produces editable columns; cutting lines are consumed.',[],['satin','running','bean']),
    tool('zigzag_line_to_satin','Zigzag drawing → satin','Satin','Convert an existing square-wave, sawtooth, or zigzag path into rails and rungs.',[
        choice('pattern','Source path pattern','zigzag',[['square','Square wave'],['sawtooth','Sawtooth'],['zigzag','Zigzag']]),
        flag('smoothing','Smooth rails',True),flag('rungs','Create rungs',True),flag('reduce-rungs','Reduce rung count')],['running','bean','zigzag']),
    tool('stroke_to_lpe_satin','Patterned satin','Satin','Repeat a decorative satin pattern along selected running paths. The result becomes editable rails and rungs.',[
        choice('pattern','Pattern','wave',[[x,x.title()] for x in ['normal','pearl','diamond','square','triangle','wave','arch']]),
        num('min-width','Minimum width (mm)',2,.6,10),num('max-width','Maximum width (mm)',5,.6,10),num('length','Pattern length (mm)',15,1,100),
        flag('stretched','Stretch repeats to fit'),flag('rungs','Create rungs',True)],['running','bean','zigzag']),
    tool('fill_to_stroke','Fill → centerline','Running stitches','Find running centerlines through filled shapes.',[
        flag('keep_original','Keep original fill'),num('threshold_mm','Maximum branch distance (mm)',10,.01,100),
        num('line_width_mm','Result stroke width (mm)',.26,.1,10),flag('close_gaps','Close gaps')],['fill']),
    tool('outline','Extract outline','Running stitches','Generate running outlines from selected artwork, with optional inset and smoothing.',[
        flag('keep-original','Keep original artwork'),num('threshold','Small-shape threshold',10,0,100),num('buffer','Merge buffer (mm)',.001,0,10),
        num('smoothness','Smoothness (mm)',.3,0,5),num('inset','Inset (mm)',0,-10,10)]),
    tool('redwork','Redwork routing','Running stitches','Route every line twice. Split by thread color routes each color separately; when off, the first selected stroke color is used for the entire route. Kept originals remain visible and will sew too.',[
        num('merge_distance','Join nearby ends (mm)',.5,0,500),num('minimum_path_length','Minimum path length (mm)',.5,0,500),
        num('redwork_running_stitch_length_mm','Running stitch length (mm)',2.5,0,500),dict(key='redwork_bean_stitch_repeats',label='Bean repeats (numbers separated by spaces)',kind='text',default='0',maxLength=79),
        flag('combine','Combine paths'),flag('redwork_split_colors','Split by thread color'),flag('keep_originals','Keep originals')],['running','bean']),
    tool('knockdown_fill','Knockdown background','Backgrounds','Create an underlay behind the selection to flatten pile fabric. The selected artwork stays above it.',[
        num('stitch-length','Stitch length (mm)',3,.5,10),flag('keep-holes','Keep holes',True),num('offset','Margin around artwork (mm)',1,-5,15),
        choice('join-style','Corner style','1',[['1','Round'],['2','Miter'],['3','Bevel']]),num('mitre-limit','Miter limit',5,.1,20),
        choice('shape','Background shape','',[['','Follow artwork'],['rect','Rectangle'],['circle','Circle']]),flag('simple-shape','Use only the simple shape'),
        num('shape-offset','Shape margin (mm)',1,0,15),choice('shape-join-style','Shape corner style','1',[['1','Round'],['2','Miter'],['3','Bevel']])]),
    tool('gradient_blocks','Gradient → editable color blocks','Color work','Split a color gradient into overlapping solid-color fill paths. Each block keeps its own tapered density and can be edited independently.',[
        num('end-row-spacing','Ending row spacing (mm; 0 = automatic)',0,0,5)],['fill']),
    tool('cutwork_segmentation','Cutwork direction segments','Cutwork','Split running outlines into four directional needle groups. The colors identify cutting directions. Export uses an EXP + INF bundle for compatible cutting-needle machines; it is not a PP1 PES workflow.',[
        *[f for letter,start,end,color in [('a',112,157,'#990000'),('b',158,23,'#e5a50a'),('c',22,68,'#009900'),('d',67,113,'#000099')] for f in
          [num(letter+'_start',letter.upper()+' needle: start angle (°)',start,0,180),num(letter+'_end',letter.upper()+' needle: end angle (°)',end,0,180),dict(key=letter+'_color',label=letter.upper()+' needle: identification color',kind='color',default=color)]],
        flag('sort_by_color','Group by cutting direction',True),flag('keep_original','Keep original running outline')],['running','bean','manual']),
    tool('jump_to_stroke','Jumps → running connections','Running stitches','Replace selected same-color jumps with visible running stitches. The source artwork stays editable. Review the stitch preview to ensure the new connecting stitches belong in your design.',[
        num('minimum-jump-length','Minimum jump length (mm)',3,0,100),num('maximum-jump-length','Maximum jump length (mm; 0 = unlimited)',0,0,100),
        choice('connect','Connect within','all',[['all','All selected objects'],['layer','Each selected layer'],['group','Each SVG group']]),
        flag('exclude-trim','Keep jumps following a trim',True),flag('exclude-stop','Keep jumps following a pause',True),flag('exclude-force-lock-stitch','Keep jumps following forced locks',True),
        flag('merge','Merge connected running paths'),flag('merge_subpaths','Allow connections between subpaths'),num('stitch-length','Connection stitch length (mm)',2.5,.2,10),num('tolerance','Curve tolerance (mm)',.2,.01,2)]),
    tool('break_apart','Repair intersecting fills','Cleanup','Resolve self-intersections and split disconnected regions while retaining holes. Preview any removed small regions before applying.',[
        choice('method','Overlapping regions','1',[['0','Simple separation'],['1','Resolve overlaps']]),num('thresholdMm2','Minimum region area (mm²)',.1,0,30)],['fill']),
    tool('cleanup','Clean small objects','Cleanup','Review removal of tiny fills and short paths. Applying replaces only the selection; Undo restores it.',[
        flag('rm_fill','Remove tiny fills',True),num('fill_threshold','Minimum fill area (mm²)',5,0,100),
        flag('rm_stroke','Remove short running paths',True),num('stroke_threshold','Minimum running length (mm)',1.35,0,20),
        flag('rm_satin','Remove short satin columns',True),num('satin_threshold','Minimum satin length (mm)',1.35,0,20)])
]
CATALOG={t['key']:t for t in TOOLS}
MAINTENANCE={'remove_duplicated_points','duplicate_params','remove_embroidery_settings','apply_attribute','jump_to_trim'}
_remove_inx=studio_runtime.resource('inx','inkstitch_remove_embroidery_settings.inx')
if _remove_inx.exists():
    _options=ET.parse(str(_remove_inx)).xpath('//*[local-name()="param"][@name="del_params"]/*[local-name()="option"]')
    CATALOG['remove_embroidery_settings']['fields'][0]['options']=[[e.get('value'),e.text] for e in _options]
for f in CATALOG['applique']['fields']:
    if f['key'] in ('tackWidth','tackSpacing'):f['when']={'key':'tackStitch','values':['zigzag']}
    if f['key'] in ('finishWidth','finishSpacing'):f['when']={'key':'finishStitch','values':['satin','zigzag','e_stitch']}

def parameters(t,values):
    if not isinstance(values,dict) or set(values)-{f['key'] for f in t['fields']}:raise ValueError('Unknown tool option.')
    result={}
    for f in t['fields']:
        v=values.get(f['key'],f['default'])
        if f['key']=='redwork_bean_stitch_repeats':
            from routing import bean_pattern
            v=bean_pattern(v)
        if f['kind']=='boolean':valid=isinstance(v,bool)
        elif f['kind']=='color':valid=isinstance(v,str) and bool(re.fullmatch(r'#[0-9a-fA-F]{6}',v))
        elif f['kind']=='select':valid=isinstance(v,str) and v in [o[0] for o in f['options']]
        elif f['kind']=='source':valid=isinstance(v,str) and bool(re.fullmatch(r'[\w-]{1,80}',v))
        elif f['kind']=='text':valid=isinstance(v,str) and len(v)<=f.get('maxLength',2000) and '\x00' not in v
        else:valid=type(v) in (int,float) and math.isfinite(v) and f['min']<=v<=f['max']
        if not valid:raise ValueError('Check '+f['label']+'.')
        if (f['key']=='num_points' or re.fullmatch('[abcd]_(start|end)',f['key'])) and v!=int(v):raise ValueError(f['label']+' must be a whole number.')
        result[f['key']]=v
    if 'max-width' in result and result['min-width']>result['max-width']:raise ValueError('Minimum width must not exceed maximum width.')
    return result

def editable_output(raw,s,label,source_layers=None,element_ids=False):
    """Flatten generated geometry, retaining object parameters and commands."""
    doc=inkex.load_svg(io.BytesIO(raw)).getroot();commands={}
    for connector in doc.xpath('//*[@inkscape:connection-start]'):
        refs=[connector.get('{'+INK+'}connection-'+end,'').lstrip('#') for end in ('start','end')]
        a,b=[doc.getElementById(ref) for ref in refs]
        if a is None or b is None:continue
        if b.tag=='{'+SVG+'}use':a,b=b,a
        if a.tag!='{'+SVG+'}use':continue
        name=a.get('{'+XLINK+'}href',a.get('href','')).replace('#inkstitch_','').split('-')[0]
        x,y=a.composed_transform().apply_to_point((float(a.get('x',0)),float(a.get('y',0))))
        commands.setdefault(b.get('id'),{})[name]=(x,y)
    result=[];parent_targets={}
    for e,path,style in geometry(raw):
        if e.get('{'+INK+'}connection-start'):continue
        params={ET.QName(k).localname:v for k,v in e.attrib.items() if k.startswith('{'+STITCH+'}')}
        command=commands.get(e.get('id'),{})
        for name in ('trim','stop'):
            if name in command:params[name+'_after']='True'
        fill=str(style.get('fill','black'));stroke=str(style.get('stroke','none'))
        # Independent fill/outline layers keep their thread colors editable.
        for paint,is_fill in [(fill,True),(stroke,False)]:
            if paint=='none':continue
            try:color='#%02x%02x%02x'%tuple(inkex.Color(paint).to_rgb())
            except (ValueError,TypeError):raise ValueError('Separate gradient or patterned artwork before this conversion.')
            base=dict(name=f'{label} {len(result)+1}',stitch='original',color=color,originalParams=copy.deepcopy(params),originalFill=is_fill,
                      originalStroke=not is_fill,originalFillRule=str(style.get('fill-rule','nonzero')),
                      originalWidth=float(inkex.units.convert_unit(str(style.get('stroke-width',.3)),'px'))*s.stroke_scale(e))
            layer=from_path(path,base,e.get('{'+SODIPODI+'}nodetypes'))
            if element_ids:layer['_elementId']=e.get('id')
            if source_layers:
                for ancestor in e.iterancestors():
                    match=re.fullmatch(r'layer-(\d+)',ancestor.get('id',''))
                    if match and int(match[1])<len(source_layers):layer['_sourceId']=source_layers[int(match[1])]['id'];break
            for key,name in [('entry','starting_point'),('exit','ending_point'),('targetPoint','target_point'),('routeStart','autoroute_start'),('routeEnd','autoroute_end'),('satinCut','satin_cut_point'),('trimCommand','trim'),('stopCommand','stop'),('ignoreObject','ignore_object')]:
                if name in command:
                    x,y=command[name];layer[key]=[(x-layer['x'])/layer['width'],(y-layer['y'])/layer['height']]
            for use in doc.iter('{'+SVG+'}use'):
                href=use.get('{http://www.w3.org/1999/xlink}href','')
                if (href=='#inkstitch_ignore_layer' or href.startswith('#inkstitch_ignore_layer-')) and doc.getroottree().getpath(use.getparent()) in [a.getroottree().getpath(a) for a in e.iterancestors()]:
                    point=use.composed_transform().apply_to_point((float(use.get('x',0)),float(use.get('y',0))))
                    layer['ignoreLayer']=[(point.x-layer['x'])/layer['width'],(point.y-layer['y'])/layer['height']]
            result.append(layer)
            parent_targets.setdefault(e.getroottree().getpath(e.getparent()),[]).append(layer)
    # Marked siblings remain native, non-sewing helper layers when an SVG is
    # separated. A sibling guide can affect several paths, so each output
    # target gets its own editable attachment.
    for helper in doc.iter():
        match=re.search(r'marker-start\s*:\s*url\(#inkstitch-(guide-line|anchor-line|pattern)-marker',helper.get('style',''))
        if not match or not isinstance(helper,inkex.ShapeElement):continue
        targets=parent_targets.get(helper.getroottree().getpath(helper.getparent()),[])
        for target in targets:
            style=helper.specified_style();filled=str(style.get('fill','black'))!='none';satin=str(helper.get('{'+STITCH+'}satin_column','')).lower()=='true'
            role=match[1];base={'name':role.replace('-',' ').title()+' · '+target['name'],'role':role,'helperTarget':target['id'],
                'stitch':'satin' if satin else 'fill' if filled else 'running','color':'#9453b1','helperFilled':filled,
                'patternInterval':helper.get('{'+STITCH+'}pattern_interval','1'),'patternOffset':int(helper.get('{'+STITCH+'}pattern_offset',0))}
            result.append(from_path(helper.path.transform(helper.composed_transform()),base,max_size=10000))
    if len(result)>MAX_LAYERS:raise ValueError(f'The result exceeds {MAX_LAYERS} editable paths. Select a smaller section.')
    return result

def operate(data,s):
    t=CATALOG.get(data.get('tool'));layers=data.get('layers')
    if not t:raise ValueError('Choose an embroidery tool.')
    if not isinstance(layers,list) or not 1<=len(layers)<=30:raise ValueError('Select 1–30 layers.')
    if any(l.get('type')=='image' for l in layers):raise ValueError('Trace reference images before applying embroidery tools.')
    if any(l.get('locked') or l.get('visible',True) is False for l in layers):raise ValueError('Unlock and show the selected layers first.')
    if any(l.get('role','artwork')!='artwork' for l in layers):raise ValueError('Use node editing for helpers, or restore their role to Ordinary stitched artwork before converting them.')
    modes=[layer_mode(l) for l in layers]
    if t['key']!='redwork' and t['modes'] and any(m not in t['modes'] for m in modes):raise ValueError('Choose '+', '.join(t['modes'])+' paths. Separate imported lettering or SVG paths first.')
    key=t['key'];params=parameters(t,data.get('params',{}))
    if key=='redwork':
        from routing import prepare
        return prepare(data,s,redwork=params)
    helpers=[]
    if key in MAINTENANCE or key=='transform_elements':
        from maintenance import validate_helpers
        helpers=validate_helpers(data.get('helpers',[]),layers)
    if key=='transform_elements':
        from transforms import prepare
        return prepare(layers,helpers,params,s,data.get('project'))
    if key=='applique':
        from applique import prepare
        return prepare(layers,params,s)
    if key in ('path_offset','stroke_area'):
        from design_paths import prepare
        return prepare(key,layers,params,s)
    if key=='fill_to_satin' and 'fill' not in modes:raise ValueError('Select at least one filled shape.')
    if key=='cut_satin' and ('satin' not in modes or not any(m in ('running','bean') for m in modes) and not any(l.get('satinCut') for l in layers)):raise ValueError('Select satin columns with a cut point or cutting lines crossing their rails.')
    prepared=copy.deepcopy(layers)
    if key=='stroke_to_satin':
        for l in prepared:
            l['stitch']='original';l['originalFill']=False;l['originalStroke']=True;l['originalWidth']=params['sourceWidth'];l['originalParams']={}
    source=s.build_svg({'version':1,'layers':prepared+helpers})
    doc=s.xml(source)
    if key=='fill_to_satin' and not any(m in ('running','bean') for m in modes):
        if params['guide']=='selected':raise ValueError('Select running guide lines along with the filled shape.')
        for e,path,style in geometry(source):
            if str(style.get('fill','black'))=='none':continue
            box=path.bounding_box();vertical=params['guide']=='vertical' or (params['guide']=='auto' and box.width>=box.height)
            for fraction in (.25,.5,.75):
                if vertical:
                    x=float(box.left+box.width*fraction);d=f'M{x},{float(box.top)-1} L{x},{float(box.bottom)+1}'
                else:
                    y=float(box.top+box.height*fraction);d=f'M{float(box.left)-1},{y} L{float(box.right)+1},{y}'
                ET.SubElement(doc,'{'+SVG+'}path',d=d,style='fill:none;stroke:#203f38;stroke-width:.2')
    for i,e in enumerate(doc.iter()):
        if ET.QName(e).localname in ('path','rect','ellipse','circle','polygon','polyline','line') and not e.get('id'):
            e.set('id','tool-artwork-'+str(i))
    if key=='gradient_blocks' and not doc.xpath('//*[local-name()="linearGradient"]'):raise ValueError('Set a color gradient on a filled shape first.')
    source=ET.tostring(doc)
    maintenance=None
    if key in MAINTENANCE:
        from maintenance import Maintenance
        maintenance=Maintenance(key,params,source,layers,s)
        source=maintenance.source
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='embroidery-tool-') as tmp:
        p=Path(tmp)/'source.svg';p.write_bytes(source)
        # Select actual artwork, because some extensions don't descend groups.
        ids=[e.get('id') for e,_,_ in geometry(source) if e.get('id') and not e.get('{'+INK+'}connection-start')]
        if maintenance:ids=maintenance.ids
        args=[s.ENGINE,'--extension='+key]+['--id='+id for id in ids]
        engine_params=maintenance.params if maintenance else params
        args+=['--'+k+'='+str(int(v) if k in ('num_points','redwork_bean_stitch_repeats') or re.fullmatch('[abcd]_(start|end)',k) else v) for k,v in engine_params.items() if k not in ('sourceWidth','guide','thresholdMm2')]
        if key=='break_apart':args+=['--threshold='+str(params['thresholdMm2']/s.PX_MM**2)]
        if key=='cleanup':args+=['--dry_run=False','--rm_groups=True']
        if key=='stroke_to_lpe_satin':args+=['--path-specific=True']
        raw=s.run(args+[str(p)],headless=True)
        if not raw.strip():raise ValueError('The selected paths are not suitable for '+t['label']+'. Check the tool instructions.')
        if maintenance:raw=maintenance.finish(raw)
        if key=='stroke_to_lpe_satin':
            p.write_bytes(raw);out=Path(tmp)/'expanded.svg'
            s.run(['inkscape',str(p),'--actions=select-all:all;object-to-path;export-filename:'+str(out)+';export-do'])
            raw=out.read_bytes()
        if key=='outline':
            doc=inkex.load_svg(io.BytesIO(raw)).getroot()
            for e in doc.iter():
                if not isinstance(e,inkex.PathElement) or (params['keep-original'] and e.get('id') in ids):continue
                style=e.specified_style();paint=style.get('fill','none')
                if paint=='none':paint=style.get('stroke','#203f38')
                e.style['fill']='none';e.style['stroke']=paint;e.style['stroke-width']='.2'
                e.set('{'+STITCH+'}stroke_method','running_stitch')
            raw=ET.tostring(doc)
        if key=='gradient_blocks':
            doc=s.xml(raw)
            for e in doc.iter():
                if e.get('{'+STITCH+'}fill_method')=='linear_gradient_fill':e.set('{'+STITCH+'}fill_method','tatami_fill')
            raw=ET.tostring(doc)
        result=editable_output(raw,s,t['label'],layers if maintenance else None);placements=None
        if maintenance:
            from maintenance import preserve_identity
            result,placements=preserve_identity(result,layers,helpers)
        if key=='cut_satin' and sum(layer_mode(l)=='satin' for l in result)<=modes.count('satin'):
            raise ValueError('No column was cut. Draw cutting lines that cross both rails, then include them in the selection.')
        if not result and key not in ('cleanup','break_apart'):raise ValueError('This selection produced no paths. The source layers are unchanged.')
        preview=None
        if result:
            machine_svg,cut_threads=prepare_cutwork(s.build_svg({'version':1,'layers':result}),s)
            p.write_bytes(machine_svg)
            x,y,w,h=s.bounds(p)
            if x<-.1 or y<-.1 or x+w>100.1 or y+h>100.1:raise ValueError('The result extends outside the hoop. Move or resize the selection, or reduce the margin.')
            pes=Path(tmp)/'preview.pes';pes.write_bytes(named_pes(s.run([s.ENGINE,'--extension=output','--format=pes','--version=6',str(p)],headless=True),{'threadBook':cut_threads}))
            preview=s.stitch_data(pes)
            if preview['width']>100 or preview['height']>100:raise ValueError('The generated stitches exceed the 100 mm hoop.')
    return {'layers':result,'preview':preview,'tool':key,**({'placements':placements} if placements is not None else {})}
