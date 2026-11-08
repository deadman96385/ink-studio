"""Native SVG preparation using Ink/Stitch's clone and stitch-plan engines."""
import copy,io,json,re,tempfile,uuid
from pathlib import Path
from lxml import etree as ET
from shapely import unary_union
from shapely.geometry import box
from digitizing import inkex,geometry,path_contours
from svg_structure import features,clone,tag,visible,href,properties,normalize_clone_styles,has_masks,SVG,INK,SHAPES
from svg_clipping import prepare as prepare_clips,Clips,clip_needle_path,clear_clip,polygon,polygon_path
import preferences
import svg_masks

def unlink(raw,s,recursive=True,groups=True):
    root=s.xml(raw);ids=[]
    normalize_clone_styles(root)
    # Ink/Stitch's unlinker copies source paint but drops clip/mask properties
    # on <use>. Keep those effects in the use's coordinate system on a wrapper,
    # so they intersect the source's own effects after the clone is resolved.
    for e in list(root.iter()):
        if not clone(e):continue
        effects={k:v for k,v in properties(e).items() if k in ('clip-path','mask') and v!='none'}
        if not effects:continue
        wrapper=ET.Element('{'+SVG+'}g',**effects)
        if e.get('transform'):wrapper.set('transform',e.attrib.pop('transform'))
        parent=e.getparent();parent.replace(e,wrapper);wrapper.append(e)
        style=inkex.Style(e.get('style',''))
        for key in effects:e.attrib.pop(key,None);style.pop(key,None)
        if style:e.set('style',str(style))
        else:e.attrib.pop('style',None)
    saved_cutwork='{https://inkstudio.local/svg-preparation}cutwork-needle'
    # 3.3.0's cutting-color wrapper can fail while classifying clones. This
    # temporary XML attribute follows the cloned geometry without invoking it.
    for e in root.iter():
        value=e.attrib.pop('{'+s.STITCH+'}cutwork_needle',None)
        if value is not None:e.set(saved_cutwork,value)
    for e in root.iter():
        if clone(e) and (recursive or visible(e)):
            if not e.get('id'):e.set('id','svg-clone-'+uuid.uuid4().hex)
            ids.append(e.get('id'))
    if not ids:return raw,0
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='svg-clones-') as tmp:
        path=Path(tmp)/'clones.svg';path.write_bytes(ET.tostring(root))
        out=s.run([s.ENGINE,'--extension=unlink_clone','--recursive='+str(recursive),'--add-group='+str(groups),*['--id='+id for id in ids],str(path)],headless=True)
    # A definition-only clone can be skipped by Ink/Stitch's embroiderable filter.
    # Resolve those remaining local references using Inkscape's SVG engine.
    remaining=[e.get('id') for e in s.xml(out).iter() if clone(e)]
    if recursive and remaining:
        with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='svg-definitions-') as tmp:
            path=Path(tmp)/'source.svg';path.write_bytes(out);dest=Path(tmp)/'result.svg'
            s.run(['inkscape',str(path),'--actions=select-by-id:'+','.join(remaining)+';clone-unlink-recursively;export-filename:'+str(dest)+';export-do'])
            out=dest.read_bytes()
    root=s.xml(out)
    for e in root.iter():
        value=e.attrib.pop(saved_cutwork,None)
        if value is not None:e.set('{'+s.STITCH+'}cutwork_needle',value)
    ET.cleanup_namespaces(root)
    return ET.tostring(root),len(ids)

def needle_plan(raw,s,ids=()):
    # The desktop SVG renderer drops pauses before a color change and rounds
    # colors/transforms. Read the installed engine's unrounded machine stream
    # instead, at an explicit document origin, before PES integer quantization.
    original=s.xml(raw);source=s.xml(raw)
    for node in list(source.iter()):
        if tag(node)=='use' and any(href(node)=='#inkstitch_'+name or href(node).startswith('#inkstitch_'+name+'-') for name in ('origin','stop_position')):node.getparent().remove(node)
    settings=preferences.imported(source) or preferences.effective();preferences.metadata(source,{**settings,'rotate_on_export':0})
    s.attach_global_commands(source,{'origin':[0,0]})
    from cutwork import prepare_cutwork
    machine,cutting=prepare_cutwork(ET.tostring(source),s)
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='svg-needle-points-') as tmp:
        path=Path(tmp)/'source.svg';path.write_bytes(machine)
        selected=['--id='+id for id in ids]
        data=json.loads(s.run([s.ENGINE,'--extension=output','--format=json','--max_stitch=10000','--max_jump=10000',*selected,str(path)],240,headless=True))
    if len(data['stitches'])>400000:raise ValueError('The stitch plan exceeds 400,000 commands. Prepare a smaller selection.')
    root=s.svg_root()
    for child in original:
        if tag(child) in ('defs','metadata'):root.append(copy.deepcopy(child))
    plan=ET.SubElement(root,'{'+SVG+'}g',id='native-needle-plan-'+uuid.uuid4().hex)
    points=[];thread=0;last=None
    def finish():
        nonlocal points,last
        if not points:return
        if len(points)==1:points.append(points[0])
        last=ET.SubElement(plan,'{'+SVG+'}path',id='needle-'+uuid.uuid4().hex,d='M'+' L'.join(f'{x:.8f},{y:.8f}' for x,y in points),style='fill:none;stroke:'+data['threadlist'][thread]['color']+';stroke-width:0.2')
        for key,value in {'stroke_method':'manual_stitch','min_stitch_length_mm':'0.000001','min_jump_stitch_length_mm':'0.000001'}.items():last.set('{'+s.STITCH+'}'+key,value)
        if data['threadlist'][thread]['color'] in cutting:last.set('{'+s.STITCH+'}cutwork_needle',cutting[data['threadlist'][thread]['color']]['number'])
        points=[]
    for x,y,command in data['stitches']:
        command=command.split()[0]
        if command=='STITCH':points.append((x/10,y/10));continue
        finish()
        if command in ('TRIM','STOP') and last is not None:last.set('{'+s.STITCH+'}'+('trim_after' if command=='TRIM' else 'stop_after'),'true')
        elif command=='COLOR_CHANGE':thread+=1
        elif command not in ('JUMP','END','TRIM','STOP'):raise ValueError('The stitch plan contains an unsupported needle command: '+command)
    finish()
    if last is None:raise ValueError('Ink/Stitch did not return editable stitch paths.')
    return ET.tostring(root)

def clipped_strokes(raw,s):
    """The installed satin/ripple engines do not consistently crop needle paths."""
    root=inkex.load_svg(io.BytesIO(raw)).getroot();resolver=Clips(root);targets=[]
    for e in root.iter():
        if not isinstance(e,inkex.ShapeElement) or tag(e) not in ('path','rect','ellipse','circle','line','polygon','polyline') or not visible(e):continue
        if str(e.specified_style().get('stroke','none'))=='none' or e.get('{'+INK+'}connection-start'):continue
        if 'inkstitch-' in properties(e).get('marker-start',''):continue
        region=resolver.effective(e)
        if region is not None:
            if not e.get('id'):e.set('id','clip-stitches-'+uuid.uuid4().hex)
            targets.append((e,region))
    for e,region in targets:
        # Clip the generated sequence ourselves: the engine's line intersection
        # can merge intentional repeats/backtracks on manual or running paths.
        clear_clip(e)
        plan=inkex.load_svg(io.BytesIO(needle_plan(ET.tostring(root),s,[e.get('id')]))).getroot()
        paths=[n for n in plan.iter('{'+SVG+'}path') if visible(n)]
        parent=e.getparent();group=ET.Element('{'+SVG+'}g',id=e.get('id'),transform=str(-parent.composed_transform()))
        for path in paths:
            pieces=clip_needle_path(path.path.transform(path.composed_transform()),region)
            for index,piece in enumerate(pieces):
                node=copy.deepcopy(path);node.set('id','clipped-needle-'+uuid.uuid4().hex);node.attrib.pop('transform',None);node.set('d',str(piece))
                if index<len(pieces)-1:node.set('{'+s.STITCH+'}trim_after','true');node.attrib.pop('{'+s.STITCH+'}stop_after',None)
                group.append(node)
        for connector in list(root.xpath('//*[@inkscape:connection-start]')):
            if any(connector.get('{'+INK+'}connection-'+end)=='#'+e.get('id') for end in ('start','end')):
                for end in ('start','end'):
                    ref=root.getElementById(connector.get('{'+INK+'}connection-'+end,'').lstrip('#'))
                    if ref is not None and tag(ref)=='use':ref.getparent().remove(ref)
                connector.getparent().remove(connector)
        parent.replace(e,group)
    return ET.tostring(root)

def clipping_shape(project,id,options,s):
    shape=next((l for l in project['layers'] if l['id']==id),None)
    if shape is None or not shape.get('visible',True) or shape.get('role','artwork')!='artwork' or shape.get('type')=='image':raise ValueError('Choose a visible vector shape as the clipping boundary.')
    if shape.get('locked') and options['hideShape']:raise ValueError('Unlock the clipping shape before hiding it, or leave Hide clipping shape off.')
    raw=s.build_svg({**project,'layers':[l if l['id']==id else {**l,'visible':False} for l in project['layers']]});raw,_=unlink(raw,s)
    root=inkex.load_svg(io.BytesIO(raw)).getroot()
    for e in root.iter():
        if tag(e) not in SHAPES or not visible(e):continue
        style=inkex.Style(e.get('style',''));style['fill']='#000000';style['stroke']='none';e.set('style',str(style))
        for key in list(e.attrib):
            if key.startswith('{'+s.STITCH+'}'):e.attrib.pop(key)
    raw=ET.tostring(root)
    if has_masks(root):raw,_=svg_masks.convert(raw,options['maskCutoff']/100,options['maskDetail'],s)
    raw,_=prepare_clips(raw,'vector');parts=[]
    for e,path,style in geometry(raw):
        if e.get('{'+INK+'}connection-start') or 'inkstitch-' in properties(e).get('marker-start',''):continue
        if any(not c['closed'] for c in path_contours(path)):raise ValueError('Close the clipping shape first. Use a filled shape or a closed drawn path.')
        parts.append(polygon(path,str(style.get('fill-rule','nonzero'))))
    result=unary_union(parts)
    if result.is_empty:raise ValueError('The clipping shape has no filled area.')
    # Covers every permitted native artwork position, including rotations and
    # pull compensation, without changing geometry inside the 100 mm hoop.
    return box(-1000,-1000,1000,1000).difference(result) if options['invertClip'] else result

def add_clip(raw,region,s):
    root=s.xml(raw);defs=ET.SubElement(root,'{'+SVG+'}defs');clip=ET.SubElement(defs,'{'+SVG+'}clipPath',id='shape-clip-'+uuid.uuid4().hex,clipPathUnits='userSpaceOnUse')
    ET.SubElement(clip,'{'+SVG+'}path',d=str(polygon_path(region)),**{'clip-rule':'evenodd'})
    for child in list(root):
        if tag(child)=='g' and re.fullmatch(r'layer-\d+',child.get('id','')):
            wrapper=ET.Element('{'+SVG+'}g',**{'clip-path':'url(#'+clip.get('id')+')'});root.replace(child,wrapper);wrapper.append(child)
    return ET.tostring(root)

def prepare(data,s):
    project=data.get('project');ids=data.get('ids');options=data.get('options',{})
    if not isinstance(project,dict) or project.get('version')!=1 or not isinstance(ids,list) or not 1<=len(ids)<=10 or any(not isinstance(id,str) for id in ids) or len(set(ids))!=len(ids):raise ValueError('Select 1–10 artwork layers.')
    defaults={'operation':'bake','output':'vector','unlink':True,'recursive':True,'groupSymbols':True,'keepSource':True,'maskCutoff':50,'maskDetail':.05,'shapeId':None,'invertClip':False,'hideShape':True}
    if not isinstance(options,dict) or set(options)-set(defaults):raise ValueError('Unknown SVG preparation setting.')
    options={**defaults,**options}
    if options['operation'] not in ('bake','release','unlink','clip') or options['output'] not in ('vector','needle'):raise ValueError('Choose an SVG preparation operation and output.')
    if any(type(options[k]) is not bool for k in ('unlink','recursive','groupSymbols','keepSource','invertClip','hideShape')):raise ValueError('Check the SVG preparation choices.')
    options['maskCutoff']=s.number(options['maskCutoff'],1,100,'Mask cutoff')
    if options['maskDetail'] not in (.05,.1,.2):raise ValueError('Choose Fine, Balanced or Fast mask detail.')
    from linked import resolve
    materialized=resolve(project,s);region=None
    if options['operation']=='clip':
        if not isinstance(options['shapeId'],str):raise ValueError('Choose a clipping shape.')
        region=clipping_shape(materialized,options['shapeId'],options,s);ids=[id for id in ids if id!=options['shapeId']]
        if not ids:raise ValueError('Select artwork to crop as well as its clipping shape.')
    chosen=[l for l in materialized['layers'] if l.get('id') in ids]
    if len(chosen)!=len(ids):raise ValueError('The selection changed. Reopen SVG preparation.')
    if any(l.get('locked') or not l.get('visible',True) or l.get('role','artwork')!='artwork' or l.get('type')=='image' for l in chosen):raise ValueError('Select visible, unlocked artwork. Trace reference images first.')
    result=copy.deepcopy(project);assets=[];reports=[];replacements={};before=[]
    for layer in chosen:
        original=copy.deepcopy(layer);layer=copy.deepcopy(layer);layer.pop('link',None)
        needle=options['operation'] in ('bake','clip') and options['output']=='needle'
        helpers=[h for h in materialized['layers'] if h.get('helperTarget')==layer['id']]
        if needle and any(h.get('visible',True) and h.get('locked') for h in helpers):raise ValueError('Unlock attached guides before baking them into needle points.')
        source_layers=[layer if item['id']==layer['id'] else item if needle and item.get('helperTarget')==layer['id'] else {**item,'visible':False} for item in materialized['layers']]
        source=s.build_svg({**materialized,'layers':source_layers});info=features(s.xml(source));raw=source;unlinked=0
        if options['unlink'] or options['operation']=='unlink':raw,unlinked=unlink(raw,s,options['recursive'],options['groupSymbols'])
        if region is not None:raw=add_clip(raw,region,s)
        report={'name':layer.get('name','Artwork'),'clones':unlinked,'clips':info['clips'],'clippedPaths':0,'maskedPaths':0,'releasedMasks':info['masks'] if options['operation']=='release' else 0,'flattenedCurves':False,'guidesBaked':len(helpers) if needle else 0}
        if options['operation']!='unlink':
            if any(clone(e) for e in s.xml(raw).iter()):raise ValueError('Enable recursive clone unlinking before baking or releasing clips.')
            if options['operation']=='release':raw=svg_masks.release(raw)
            elif has_masks(s.xml(raw)):raw,mask_report=svg_masks.convert(raw,options['maskCutoff']/100,options['maskDetail'],s);report.update(mask_report)
            mode='release' if options['operation']=='release' else options['output'];raw,details=prepare_clips(raw,mode);report.update(details)
            if not any(tag(e) in SHAPES and visible(e) for e in s.xml(raw).iter()):raise ValueError('No artwork remains inside the boundary. Lower the mask cutoff, invert the clipping shape, or release the mask.')
            if mode=='needle':raw=needle_plan(clipped_strokes(raw,s),s)
        asset=s.import_svg({'svg':raw.decode(),'name':layer.get('name','Artwork')+' · prepared'})
        # import_svg keeps local geometry; place it at its actual document bounds.
        with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='svg-placement-') as tmp:
            path=Path(tmp)/'source.svg';path.write_bytes(raw);x,y,w,h=s.bounds(path)
        if w>100.05 or h>100.05:raise ValueError('The prepared artwork is larger than the PP1 hoop. Resize the source first.')
        new=dict(id=layer['id'],type='import',name=layer.get('name','Artwork'),asset=asset['key'],x=x,y=y,width=asset['width'],height=asset['height'],rotation=0,flipX=False,flipY=False,visible=True,locked=False,color=layer.get('color','#203f38'),stitch='original',recolor=False)
        for key in ('groupId','background','crossSourceId','traceSourceId'):
            if key in layer:new[key]=copy.deepcopy(layer[key])
        replacements[layer['id']]=new;assets.append(asset);reports.append(report)
        if options['keepSource']:
            original.update(id=uuid.uuid4().hex,groupId=uuid.uuid4().hex,visible=False,locked=False,name=original.get('name','Artwork')+' · source (hidden)');original.pop('link',None);before.append((layer['id'],original))
            for helper in materialized['layers']:
                if helper.get('helperTarget')!=layer['id']:continue
                saved=copy.deepcopy(helper);saved.update(id=uuid.uuid4().hex,helperTarget=original['id'],groupId=original['groupId']);saved.pop('linkedHelper',None);before.append((layer['id'],saved))
    result['layers']=[]
    for l in project['layers']:
        result['layers'].extend(copy.deepcopy(old) for id,old in before if id==l['id'])
        item=replacements.get(l['id'],copy.deepcopy(l))
        if options['operation'] in ('bake','clip') and options['output']=='needle' and item.get('helperTarget') in replacements:item['visible']=False
        if options['operation']=='clip' and options['hideShape'] and item['id']==options['shapeId']:item['visible']=False
        result['layers'].append(item)
    if len(result['layers'])>s.MAX_LAYERS:raise ValueError('Keeping sources would exceed the layer limit. Turn off Keep hidden source copies.')
    # Keep IDs stable so linked copies and external guides retain their target.
    preview_layers=[replacements[l['id']] for l in chosen]+[copy.deepcopy(l) for l in result['layers'] if l.get('helperTarget') in replacements]
    preview=preferences.preview({'project':{**result,'layers':preview_layers},'settings':preferences.effective(project)},s)['preview']
    return {'project':result,'selectedIds':ids,'assets':assets,'reports':reports,'preview':preview,'options':options}

