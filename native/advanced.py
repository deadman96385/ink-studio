"""Typed Ink/Stitch controls, read-only inspection and engine routing."""
import studio_runtime
import hoops
from limits import MAX_LAYERS
import copy
import io
import json
import math
from pathlib import Path
import tempfile
import uuid
from collections import defaultdict
from lxml import etree as ET
from digitizing import SVG, STITCH, geometry, from_path, inkex

FIELDS=[]
def field(key,label,group,modes,kind='number',low=0,high=20,options=None,help='',methods=None):
    FIELDS.append(dict(key=key,label=label,group=group,modes=modes.split(),kind=kind,min=low,max=high,options=options,help=help,methods=methods))

COMMON='fill satin running bean zigzag original text manual ripple'
field('min_stitch_length_mm','Minimum stitch length (mm)','Locks & filtering',COMMON,low=0,high=1,help='Remove stitches shorter than this value. Zero uses the document preference.')
field('min_jump_stitch_length_mm','Minimum jump for lock stitches (mm)','Locks & filtering',COMMON,low=0,high=10)
field('ties','Lock stitches','Locks & filtering',COMMON,'select',options=[[0,'Before and after'],[1,'Before only'],[2,'After only'],[3,'Neither']])
field('force_lock_stitches','Force lock stitches','Locks & filtering',COMMON,'boolean',help='Add locks even when the connection to the next object is short.')
field('color_sort_index','Font color sort index','Font stitch sequence',COMMON,'integer',high=100,help='Controls indexed color sorting when this path is used in an embroidery font. Enable sorting in the font settings.')
field('expand_mm','Expand shape (mm)','Fill pattern','fill',low=-3,high=3,help='Negative values contract the fill; positive values expand it.')
field('gap_fill_rows','Extra rows at section gaps','Fill pattern','fill','integer',high=5,methods=['tatami_fill'])
field('staggers','Stagger cycle (rows)','Fill pattern','fill',low=1,high=20,methods=['tatami_fill'])
field('end_row_spacing_mm','Final row spacing (mm)','Fill pattern','fill',low=.2,high=3,methods=['tatami_fill','circular_fill'])
field('skip_last','Skip last stitch in each row','Fill pattern','fill','boolean',methods=['tatami_fill'])
field('pull_compensation_percent','Additional pull compensation (%)','Compensation','fill satin',high=30)
field('contour_strategy','Contour strategy','Contour fill','fill','select',options=[[0,'Inner to outer'],[1,'Single spiral'],[2,'Double spiral']],methods=['contour_fill'])
field('join_style','Corner joins','Contour fill','fill','select',options=[[0,'Round'],[1,'Mitered'],[2,'Beveled']],methods=['contour_fill'])
field('clockwise','Clockwise','Contour fill','fill','boolean',methods=['contour_fill'])
field('avoid_self_crossing','Avoid self-crossing','Contour fill','fill','boolean',methods=['contour_fill'])
field('underpath','Travel inside the fill','Travel stitches','fill','boolean',methods=['tatami_fill','circular_fill'])
field('stop_at_ending_point','Finish exactly at the exit command','Travel stitches','fill','boolean',help='Otherwise the exit may only guide the routing direction.',methods=['tatami_fill','circular_fill'])
field('running_stitch_length_mm','Travel stitch length (mm)','Travel stitches','fill satin',low=.5,high=6)
field('running_stitch_tolerance_mm','Path tolerance (mm)','Travel stitches','fill satin running bean',low=.01,high=1,help='Smaller values follow curves more closely.')
field('fill_underlay_angle','Underlay angles (degrees)','Fill underlay','fill','angles',low=-180,high=180,help='Separate angles with spaces for multiple underlay passes. Blank uses the engine default.')
field('fill_underlay_max_stitch_length_mm','Underlay maximum stitch length (mm)','Fill underlay','fill',low=.5,high=6)
field('fill_underlay_skip_last','Skip last underlay stitch per row','Fill underlay','fill','boolean')
field('underlay_underpath','Travel inside the underlay','Fill underlay','fill','boolean')
field('repeats','Path passes','Running & repeated stitches','running bean zigzag fill','integer',low=1,high=8,methods=['contour_fill','circular_fill'])
field('bean_stitch_repeats','Backtracks per stitch','Running & repeated stitches','running bean zigzag fill','integer',high=5,methods=['contour_fill','circular_fill'],help='0 is a normal run; 1 makes a triple-run bean stitch.')
field('zigzag_angle','Zigzag angle (degrees)','Running & repeated stitches','zigzag',low=-80,high=80)
field('stroke_pull_compensation_mm','Zigzag pull compensation (mm)','Compensation','zigzag',high=1)
field('satin_method','Satin method','Satin construction','satin','select',options=[['satin_column','Satin'],['e_stitch','E stitch'],['s_stitch','S stitch'],['zigzag','Zigzag']])
field('split_method','Long-stitch splitting','Satin construction','satin','select',options=[['default','Default'],['simple','Simple'],['staggered','Staggered']])
field('split_staggers','Split stagger cycle','Satin construction','satin',low=1,high=20)
field('random_split_phase','Random split phase','Satin construction','satin','boolean')
field('random_split_jitter_percent','Split jitter (%)','Satin construction','satin',high=100)
field('min_random_split_length_mm','Minimum random split length (mm)','Satin construction','satin',low=.5,high=12)
field('short_stitch_inset','Short stitch inset (%)','Satin construction','satin',high=45)
field('short_stitch_distance_mm','Short stitch spacing threshold (mm)','Satin construction','satin',low=.05,high=1)
field('push_compensation_mm','Shorten satin ends (mm)','Compensation','satin',high=3)
field('reverse_rails','Rail direction','Satin construction','satin','select',options=[['automatic','Detect automatically'],['none','Keep both'],['first','Reverse first'],['second','Reverse second'],['both','Reverse both']])
field('swap_satin_rails','Swap first and second rail','Satin construction','satin','boolean')
field('running_stitch_position','Travel position between rails (%)','Travel stitches','satin',high=100)
for prefix,label in [('center_walk','Center-walk'),('contour','Contour')]:
    field(prefix+'_underlay_stitch_length_mm',label+' stitch length (mm)','Satin underlay','satin',low=.5,high=6)
    field(prefix+'_underlay_stitch_tolerance_mm',label+' tolerance (mm)','Satin underlay','satin',low=.01,high=1)
field('center_walk_underlay_repeats','Center-walk passes','Satin underlay','satin','integer',low=1,high=8)
field('center_walk_underlay_position','Center-walk position between rails (%)','Satin underlay','satin',high=100)
field('contour_underlay_inset_mm','Contour inset (mm)','Satin underlay','satin',high=3)
field('contour_underlay_inset_percent','Additional contour inset (%)','Satin underlay','satin',high=45)
field('zigzag_underlay_spacing_mm','Zigzag underlay spacing (mm)','Satin underlay','satin',low=.3,high=5)
field('zigzag_underlay_inset_mm','Zigzag underlay inset (mm)','Satin underlay','satin',high=3)
field('zigzag_underlay_inset_percent','Additional zigzag inset (%)','Satin underlay','satin',high=45)
field('zigzag_underlay_max_stitch_length_mm','Zigzag underlay maximum length (mm)','Satin underlay','satin',low=.5,high=12)
field('enable_random_stitch_length','Randomize stitch length','Texture','fill running bean','boolean')
field('random_stitch_length_jitter_percent','Stitch length jitter (%)','Texture','fill running bean',high=80)
field('random_width_decrease_percent','Random satin width decrease (%)','Texture','satin',high=45)
field('random_width_increase_percent','Random satin width increase (%)','Texture','satin',high=30)
field('random_zigzag_spacing_percent','Satin spacing jitter (%)','Texture','satin',high=80)
field('random_seed','Random seed','Texture','fill satin running bean','seed',help='Use the same seed to reproduce a texture.')
# Specialty construction settings are regular Ink/Stitch parameters; forms
# stay native and only show parameters relevant to the chosen stitch method.
TILES={}
for p in studio_runtime.resource('tiles').glob('*/tile.json'):
    tile=json.loads(p.read_text());TILES[tile['id']]={**tile,'preview':p.parent/'preview.png'}
field('meander_pattern','Meander pattern','Meander fill','fill','select',options=[[t['id'],t['name']] for t in sorted(TILES.values(),key=lambda t:t['name'])],methods=['meander_fill'])
FIELDS[-1]['preview']='/tile-previews/'
field('meander_angle','Pattern rotation (degrees)','Meander fill','fill',low=-180,high=180,methods=['meander_fill'])
field('meander_scale_percent','Pattern scale: X Y (%)','Meander fill','fill','pair',low=10,high=500,methods=['meander_fill'],help='One percentage for uniform scale, or two separated by a space.')
field('clip','Keep stitches inside the shape','Meander fill','fill','boolean',methods=['meander_fill'])
field('smoothness_mm','Path smoothing (mm)','Meander fill','fill',high=2,methods=['meander_fill','contour_fill'])
field('zigzag_spacing_mm','Meander zigzag spacing (mm)','Meander fill','fill',high=4,methods=['meander_fill'],help='0 keeps a running path; positive spacing adds zigzag stitching.')
field('zigzag_width_mm','Meander zigzag width (mm)','Meander fill','fill',low=.3,high=6,methods=['meander_fill'])
crosses=['simple_cross','half_cross','upright_cross','dense_upright_cross','double_cross','smyrna_cross']
field('cross_stitch_method','Cross pattern','Cross stitch','fill','select',options=[[v,v.replace('_',' ').title()] for c in crosses for v in (c,c+'_flipped')],methods=['cross_stitch'])
field('cross_thread_count','Threads per cross','Cross stitch','fill','integer',low=1,high=16,methods=['cross_stitch'],help='Even values create full crosses; odd values finish with a half cross.')
field('pattern_size_mm','Cross size: X Y (mm)','Cross stitch','fill','pair',low=.5,high=15,methods=['cross_stitch'],help='One size for square crosses, or two sizes separated by a space.')
field('canvas_grid_origin','Align crosses to the hoop grid','Cross stitch','fill','boolean',methods=['cross_stitch'])
field('cross_offset_mm','Grid offset: X Y (mm)','Cross stitch','fill','pair',low=-20,high=20,methods=['cross_stitch'])
field('cross_rotation','Grid rotation (degrees)','Cross stitch','fill',low=-180,high=180,methods=['cross_stitch'])
field('fill_coverage','Minimum cross overlap (%)','Cross stitch','fill','integer',high=100,methods=['cross_stitch'])
field('max_cross_stitch_length_mm','Maximum cross stitch length (mm)','Cross stitch','fill',low=.5,high=15,methods=['cross_stitch'])
field('max_stitch_length_mm','Maximum manual stitch length (mm)','Manual stitches','manual',low=.5,high=12,help='Blank preserves each drawn segment; a value splits longer segments.')
for key,label,kind,low,high in [
    ('line_count','Number of ripple lines','integer',1,100),('min_line_dist_mm','Minimum line spacing (mm)','number',0,10),
    ('skip_start','Skip first lines','integer',0,99),('skip_end','Skip last lines','integer',0,99),
    ('exponent','Density progression','number',.1,5),('grid_size_mm','Cross-grid spacing (mm)','number',0,10),
    ('scale_start','First copy scale (%)','number',0,300),('scale_end','Last copy scale (%)','number',0,300)]:
    field(key,label,'Ripple stitches','ripple',kind,low,high)
for key,label in [('manual_pattern_placement','Preserve pattern stitch points'),('flip_copies','Flip alternate copies'),('flip_exponent','Reverse density progression'),('reverse','Reverse stitch direction'),('grid_first','Sew cross-grid first'),('rotate_ripples','Rotate pattern along guide')]:
    field(key,label,'Ripple stitches','ripple','boolean')
field('scale_axis','Scale pattern axes','Ripple stitches','ripple','select',options=[[0,'Both axes'],[1,'X only'],[2,'Y only'],[3,'Neither']])
field('satin_guide_pattern_position','Satin-guide placement','Ripple stitches','ripple','select',options=[['default','Line count / spacing'],['render_at_rungs','At each rung'],['adaptive','Adaptive with minimum spacing']])
field('ripple_join_style','Ripple joins','Ripple stitches','ripple','select',options=[[0,'Flat'],[1,'Point']]);FIELDS[-1]['parameter']='join_style'
field('ripple_staggers','Ripple stagger cycle','Ripple stitches','ripple',low=0,high=20);FIELDS[-1]['parameter']='staggers'
field('tartan_angle','Stitch angle relative to stripes (degrees)','Tartan fill','fill',low=-180,high=180,methods=['tartan_fill'])
field('rows_per_thread','Consecutive rows per thread','Tartan fill','fill','integer',low=1,high=10,methods=['tartan_fill'])
field('herringbone_width_mm','Herringbone width (mm)','Tartan fill','fill',high=20,methods=['tartan_fill'],help='0 uses regular woven rows.')
field('guided_fill_strategy','Guide following strategy','Guided fill','fill','select',options=[[0,'Copy the guide'],[1,'Parallel offset'],[2,'Buffer']],methods=['guided_fill'])
field('guided_fill_angle','Guide shifting angle (degrees)','Guided fill','fill',low=-180,high=180,methods=['guided_fill'])
field('stitch_position_method','Stitch placement along curves','Guided fill','fill','select',options=[['flexible','Flexible'],['flexible_stagger','Flexible with stagger']],methods=['guided_fill'])
for f in FIELDS:
    if f['key'] in ('repeats','running_stitch_tolerance_mm','enable_random_stitch_length','random_stitch_length_jitter_percent','random_seed','reverse_rails','swap_satin_rails'):f['modes'].append('ripple')
    if f['key']=='bean_stitch_repeats':f['modes']+=['ripple','manual']
    if f['key'] in ('repeats','bean_stitch_repeats'):f['methods'].append('meander_fill')
    if f['key'] in ('staggers','skip_last','stop_at_ending_point'):f['methods']+=['linear_gradient_fill','tartan_fill']
    if f['key'] in ('staggers','skip_last','underpath','smoothness_mm','bean_stitch_repeats'):f['methods'].append('guided_fill')
field('cutwork_needle','Cutting needle','Cutwork','running bean manual','select',options=[[0,'Ordinary sewing'],[1,'Cut 1'],[2,'Cut 2'],[3,'Cut 3'],[4,'Cut 4']],help='Cutwork uses a compatible cutting-needle setup and an EXP + INF export bundle.')
SCHEMA={f['key']:f for f in FIELDS}

def layer_mode(layer):
    if layer.get('type')=='text':return 'text'
    mode=layer.get('stitch','fill')
    if mode=='original' and layer.get('originalParams') is not None:
        if str(layer['originalParams'].get('satin_column','')).lower()=='true':return 'satin'
        return 'fill' if layer.get('originalFill',True) else {'manual_stitch':'manual','ripple_stitch':'ripple','zigzag_stitch':'zigzag'}.get(layer['originalParams'].get('stroke_method'),'running')
    return mode

def matches(field,layer):
    mode=layer_mode(layer)
    if mode=='fill' and layer.get('fillMethod') in ('streamline_fill','wave_fill'):mode='running'
    method=layer.get('fillMethod',layer.get('originalParams',{}).get('fill_method','tatami_fill'))
    return mode in field['modes'] and (mode!='fill' or not field['methods'] or method in field['methods'])

def validate_advanced(values):
    if not isinstance(values,dict) or len(values)>len(FIELDS):raise ValueError('Invalid advanced stitch settings.')
    result={}
    for key,value in values.items():
        f=SCHEMA.get(key)
        if not f:raise ValueError('Unknown advanced stitch setting: '+str(key))
        kind=f['kind'];valid=False
        if kind=='boolean':valid=isinstance(value,bool)
        elif kind=='select':valid=type(value) in (str,int) and value in [v[0] for v in f['options']]
        elif kind=='seed':valid=isinstance(value,str) and len(value)<=80
        elif kind in ('angles','pair'):
            try:
                angles=[float(v) for v in value.split()] if isinstance(value,str) else []
                valid=1<=len(angles)<=(2 if kind=='pair' else 4) and all(math.isfinite(v) and f['min']<=v<=f['max'] for v in angles)
            except ValueError:valid=False
        else:valid=type(value) in (int,float) and math.isfinite(value) and f['min']<=value<=f['max'] and (kind!='integer' or value==int(value))
        if not valid:raise ValueError('Invalid value for '+f['label']+'.')
        result[key]=str(value)
    return result

def apply_advanced(content,layer):
    values=validate_advanced(layer.get('advanced',{}))
    for e in content.iter():
        if ET.QName(e).localname not in ('path','rect','ellipse','circle','polygon','polyline','line'):continue
        if any(ET.QName(a).localname=='defs' for a in e.iterancestors()):continue
        if e.get('{http://www.inkscape.org/namespaces/inkscape}connection-start'):continue
        for key,value in values.items():
            if matches(SCHEMA[key],layer):e.set('{'+STITCH+'}'+SCHEMA[key].get('parameter',key),value)

def flatten_trim_commands(doc):
    """Preserve route trims as parameters so paths and backups stay portable."""
    ink='{http://www.inkscape.org/namespaces/inkscape}'
    for connector in list(doc.xpath('//*[@inkscape:connection-start]',namespaces={'inkscape':ink[1:-1]})):
        refs=[connector.get(ink+'connection-start','')[1:],connector.get(ink+'connection-end','')[1:]]
        nodes=[doc.xpath('//*[@id=$id]',id=ref) for ref in refs]
        if not all(nodes):continue
        a,b=[n[0] for n in nodes]
        if ET.QName(b).localname=='use':a,b=b,a
        href=a.get('{http://www.w3.org/1999/xlink}href','')
        command=href.replace('#inkstitch_','').split('-')[0]
        if command in ('trim','stop'):b.set('{'+STITCH+'}'+command+'_after','True')
        a.getparent().remove(a);connector.getparent().remove(connector)
    # Only routing-generated symbols are left in defs; no artwork depends on them.
    for e in list(doc.xpath('//*[local-name()="defs"]')):e.getparent().remove(e)

def route(data,s):
    from routing import prepare
    return prepare(data,s)

def density_points(segments,radius,yellow,red):
    points=[(s[2],s[3]) for s in segments]
    cells=defaultdict(list)
    for x,y in points:cells[(math.floor(x/radius),math.floor(y/radius))].append((x,y))
    counts=[0,0,0];markers=[];rr=radius*radius
    for x,y in points:
        cx,cy=math.floor(x/radius),math.floor(y/radius);near=0
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for a,b in cells.get((cx+dx,cy+dy),()):
                    if (x-a)**2+(y-b)**2<=rr:near+=1
                    if near>=red:break
                if near>=red:break
            if near>=red:break
        level=2 if near>=red else 1 if near>=yellow else 0
        counts[level]+=1
        if level:markers.append([x,y,level])
    # Keep tablet overlays responsive; counts always include every penetration.
    stride=max(1,math.ceil(len(markers)/15000))
    return {'counts':counts,'markers':markers[::stride],'sampled':stride>1,'radius':radius,'yellow':yellow,'red':red}

def inspect_design(data,s):
    project=data.get('project');source=s.build_svg(project,sewing=True)
    radius=s.number(data.get('radius',.5),.1,2,'Density radius')
    yellow=s.number(data.get('yellow',3),2,30,'Yellow threshold');red=s.number(data.get('red',6),3,60,'Red threshold')
    if int(yellow)!=yellow or int(red)!=red or red<=yellow:raise ValueError('Density thresholds must be whole numbers, with red greater than yellow.')
    findings=[];preview=None;density=None;quality=None
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='check-') as tmp:
        p=Path(tmp)/'design.svg';p.write_bytes(source)
        x,y,w,h=s.bounds(p,sewing=True)
        if not hoops.inside(project,x,y,w,h):findings.append({'severity':'error','message':f"Artwork extends outside the {hoops.hoop(project)['short']} mm hoop. Move or resize it before export."})
        import troubleshoot
        report=troubleshoot.generate({'project':project},s)
        for problem in report['problems']:
            findings.append({'severity':'error' if problem['severity']=='error' else 'warning',
                             'message':problem['name']+' ('+problem['layerName']+')',
                             'description':problem['description'],'layerId':problem['layerId'],'position':problem['position']})
        if not any(f['severity']=='error' for f in findings):
            try:
                from cutwork import prepare_cutwork
                machine,_=prepare_cutwork(source,s);p.write_bytes(machine)
                pes=Path(tmp)/'check.pes';pes.write_bytes(s.run([s.ENGINE,'--extension=output','--format=pes','--version=6',str(p)]))
                preview=s.stitch_data(pes,include_commands=True)
                import sewing_quality
                quality_findings,quality=sewing_quality.analyze(project,preview)
                findings.extend(quality_findings)
                preview.pop('commands',None);preview.pop('commandTypes',None)
                if preview['width']>hoops.size(project)[0] or preview['height']>hoops.size(project)[1]:findings.append({'severity':'error','message':'Generated stitches exceed the hoop, including compensation.'})
                density=density_points(preview['segments'],radius,int(yellow),int(red))
            except ValueError as e:findings.append({'severity':'error','message':str(e)})
    for l in project['layers']:
        if l.get('role','artwork') not in ('artwork','content-area','scene-guide') and not any(t['id']==l.get('helperTarget') for t in project['layers']):findings.append({'severity':'warning','message':l.get('name','Helper')+' has no target layer and is ignored. Reassign it in Guides & patterns.'})
    # Errors first, then sewing-load warnings (most likely to ruin a stitch-out).
    findings.sort(key=lambda f:(f['severity']!='error',{'sewing':0,'small-detail':1}.get(f.get('kind'),2)))
    return {'findings':findings[:100],'findingCount':len(findings),'preview':preview,'density':density,'sewing':quality,'visibleLayers':sum(l.get('visible',True) is not False and l.get('type')!='image' and l.get('role','artwork')=='artwork' for l in project['layers'])}
