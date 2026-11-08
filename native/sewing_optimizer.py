"""Reusable, editable sewing optimization; original artwork stays untouched."""
import studio_runtime
import copy,hashlib,json,tempfile
from pathlib import Path
from lxml import etree as ET

def settings(value,s):
    if not isinstance(value,dict) or set(value)-{'version','enabled','reorder','connect','maxBridge','undersewDetails','manualWaveSnips'}:raise ValueError('Choose supported sewing optimization settings.')
    for k in ('enabled','reorder','connect','undersewDetails','manualWaveSnips'):
        if k in value and type(value[k])is not bool:raise ValueError('Choose valid sewing optimization switches.')
    if type(value.get('version',1))is not int or value.get('version',1)!=1:raise ValueError('This sewing optimization version is not supported.')
    out={'version':1,'enabled':value.get('enabled',True),'reorder':value.get('reorder',True),'connect':value.get('connect',True),
        'maxBridge':s.number(value.get('maxBridge',4),.2,8,'Maximum covered connection')}
    if value.get('undersewDetails'):out['undersewDetails']=True
    if value.get('manualWaveSnips'):out['manualWaveSnips']=True
    return out

def configuration(project,root,options,s):
    from components import world_path,path_polygon
    from footprints import envelope,is_satin
    masks=[];fixed=[]
    if any(project.get(k) for k in ('origin','frameOut')):raise ValueError('Remove the design origin or frame-out command before using sewing optimization.')
    if any(e.get('{'+s.STITCH+'}cutwork_needle') not in (None,'0') for e in root.iter()):raise ValueError('Sewing optimization does not support cutwork needle changes.')
    if any(e.get('{http://www.w3.org/1999/xlink}href','') in ('#inkstitch_origin','#inkstitch_stop_position') for e in root.iter()):raise ValueError('Remove the design origin or frame-out command before using sewing optimization.')
    for i,l in enumerate(project['layers']):
        if l.get('visible',True)is False or l.get('role','artwork')!='artwork' or l.get('type')=='image':continue
        if l.get('cutwork') or l.get('cutworkNeedle'):raise ValueError('Sewing optimization does not support cutwork needle changes.')
        special=l.get('locked') or any(l.get(k) for k in ('entry','exit','routeStart','routeEnd','trimCommand','stopCommand','stopAfter')) or any(h.get('helperTarget')==l['id'] for h in project['layers'])
        if special:fixed.append(i)
        if special or l.get('ignoreObject') or l.get('ignoreLayer') or l.get('borderEnabled') or l.get('multicolorSatin'):continue
        advanced=l.get('advanced',{})
        if set(advanced)-{'min_stitch_length_mm','min_jump_stitch_length_mm','ties'} or advanced.get('min_stitch_length_mm',0)>.3:continue
        if any('random' in k or 'pattern' in k for k in l.get('originalParams',{})):continue
        if l.get('stitch')=='fill' and l.get('fillMethod','tatami_fill') not in ('tatami_fill','legacy_fill'):continue
        if l.get('stitch')!='fill' and not is_satin(l):continue
        if float(l.get('originalParams',{}).get('zigzag_spacing_mm',l.get('spacing',.4)))>.5:continue
        # Use the source boundary only as a conservative coverage proof. Contract
        # for texture and pull so a connector cannot protrude through ragged edges.
        try:
            path=world_path(l,s);shape=envelope({**l,'feather':None,'pullCompensation':0},path,s) if is_satin(l) else path_polygon(path)
            if l.get('smallFillFallback') and not is_satin(l):
                from shapely.ops import unary_union
                shape=unary_union([p for p in (shape.geoms if shape.geom_type=='MultiPolygon' else [shape]) if p.area>=1.4 and min(p.bounds[2]-p.bounds[0],p.bounds[3]-p.bounds[1])>=.9])
            feather=l.get('feather') or {};margin=.2+(feather.get('raggedness',.5) if feather.get('enabled',True) and feather else 0)+abs(l.get('pullCompensation',0))
            shape=shape.buffer(-margin)
            # Ground knockouts are not a reliable cover for another motif.
            if any(g.get('scene',{}).get('knockoutBackground') and any(a['id']==g['scene'].get('areaId') and a.get('areaSource')==l['id'] for a in project['layers']) for g in project['layers']):continue
            if not shape.is_empty:masks.append({'source':i,'color':l['color'],'mask':shape.wkt})
        except (ValueError,KeyError):continue
    return {**options,'masks':masks,'fixed':fixed}

def machine_metrics(preview):
    import math
    commands=preview['commands'];jump=preview['commandTypes']['jump']
    travel=sum(math.dist(a[:2],b[:2]) for a,b in zip(commands,commands[1:]) if b[2]==jump)
    return {'cuts':preview['trims'],'stitches':preview['stitches'],'travelMM':round(travel,2),'threadSteps':preview['colorChanges']+1}

def needle_positions(preview):
    thread=0;points=set()
    for x,y,c in preview['commands']:
        if c==preview['commandTypes']['color']:thread+=1
        elif c==preview['commandTypes']['stitch']:points.add((thread,round(x*10),round(y*10)))
    return points

def write_plan(group,blocks,s,prefix):
    counter=0
    for block in blocks:
        points=[];last=None
        def finish():
            nonlocal points,last,counter
            if not points:return
            if len(points)==1:points.append(points[0])
            for i in range(0,len(points)-1,1799):
                node=ET.SubElement(group,'{'+s.SVG+'}path',d='M'+' L'.join(f'{x:.8f},{y:.8f}' for x,y in points[i:i+1800]),style='fill:none;stroke:'+s.color(block['color'])+';stroke-width:.15',id=prefix+'-'+str(counter));counter+=1
                for k,v in {'stroke_method':'manual_stitch','ties':'3','min_stitch_length_mm':'.000001','min_jump_stitch_length_mm':'.000001','trim_after':'False','stop_after':'False'}.items():node.set('{'+s.STITCH+'}'+k,v)
                last=node
            points=[]
        for x,y,command,*_ in block['points']:
            if command=='STITCH':points.append((x,y));continue
            finish()
            if last is not None and command in ('TRIM','STOP'):last.set('{'+s.STITCH+'}'+('trim_after' if command=='TRIM' else 'stop_after'),'True')
        finish()

def compile(root,project,s):
    value=project.get('sewingOptimization')
    if value is None:return
    options=settings(value,s)
    if not options['enabled'] or not (options['connect'] or options['reorder'] or options.get('manualWaveSnips')):return
    config=configuration(project,root,options,s);raw=ET.tostring(root)
    digest=hashlib.sha256(b'sewing-optimizer-v9'+raw+json.dumps(config,sort_keys=True).encode()).hexdigest()
    cache=s.DATA/'cache'/('sewing-optimizer-'+digest+'.json')
    if cache.exists():data=json.loads(cache.read_text())
    else:
        with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-sewing-optimize-') as tmp:
            path=Path(tmp)/'source.svg';path.write_bytes(raw);params=Path(tmp)/'settings.json';params.write_text(json.dumps({**config,'source':str(path)}))
            data=json.loads(s.run(studio_runtime.worker_command('--native-sewing-optimize',str(params)),240,headless=True))
        if data.get('error'):raise ValueError('Could not optimize sewing: '+data['error'])
    original=copy.deepcopy(root)
    if data.get('validated') and not data.get('accepted'):return
    for child in list(root):
        if ET.QName(child).localname not in ('title','desc','metadata','defs'):root.remove(child)
    group=ET.SubElement(root,'{'+s.SVG+'}g',id='optimized-sewing')
    group.set('data-sewing-optimization',json.dumps({k:v for k,v in data['stats'].items() if k!='bridges'}))
    blocks=data['blocks']
    if options.get('manualWaveSnips'):
        from manual_wave_snips import apply as manual_floats
        blocks,manual_report=manual_floats(blocks,project,s)
        root.set('data-manual-wave-snips',json.dumps(manual_report))
    write_plan(group,blocks,s,'optimized')
    if not data.get('validated'):
        with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='sewing-readback-') as tmp:
            previews=[]
            for name,svg in [('before',raw),('after',ET.tostring(root))]:
                path=Path(tmp)/(name+'.svg');path.write_bytes(svg);pes=Path(tmp)/(name+'.pes')
                pes.write_bytes(s.run([s.ENGINE,'--extension=output','--format=pes','--version=6',str(path)],240,headless=True))
                previews.append(s.stitch_data(pes,True))
        before,after=map(machine_metrics,previews)
        same_threads=[t['color'] for t in previews[0]['threads']]==[t['color'] for t in previews[1]['threads']]
        needles=needle_positions(previews[1]);retained=all(any((t,x+dx,y+dy) in needles for dx in (-1,0,1) for dy in (-1,0,1)) for t,x,y in needle_positions(previews[0]))
        improved=after['cuts']<before['cuts'] or after['travelMM']<before['travelMM']-.2
        data.update(validated=True,accepted=improved and retained and before['cuts']>=after['cuts'] and before['travelMM']+.2>=after['travelMM'] and same_threads and previews[0]['stops']==previews[1]['stops'])
        data['stats'].update(before=before,after=after,accepted=data['accepted'],needlePositionsRetained=retained)
        s.write_atomic(cache,data)
    if not data['accepted']:
        for child in list(root):root.remove(child)
        for child in original:root.append(copy.deepcopy(child))
    else:group.set('data-sewing-optimization',json.dumps({k:v for k,v in data['stats'].items() if k!='bridges'}))

def prepare(data,s):
    from preferences import preview,effective
    project=data.get('project')
    if not isinstance(project,dict):raise ValueError('Open a design to optimize.')
    options=settings(data.get('settings',{}),s);proposal=copy.deepcopy(project);proposal['sewingOptimization']=options
    baseline=copy.deepcopy(project);baseline.pop('sewingOptimization',None)
    before=preview({'project':baseline,'settings':effective(project)},s)['preview']
    after=preview({'project':proposal,'settings':effective(project)},s)['preview'] if options['enabled'] else before
    root=s.xml(s.build_svg(proposal,sewing=True));node=root.find('.//*[@data-sewing-optimization]')
    stats=json.loads(node.get('data-sewing-optimization')) if node is not None else None
    covered=json.loads(root.get('data-covered-detail-study','null'))
    manual=json.loads(root.get('data-manual-wave-snips','null'))
    return {'settings':options,'before':before,'preview':after,'stats':stats,'coveredDetails':covered,'manualWaveSnips':manual}
