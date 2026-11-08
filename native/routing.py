"""Installed auto-routing and Redwork with native source order and settings."""
import copy,re,tempfile,uuid
from pathlib import Path
from lxml import etree as ET
from digitizing import geometry,SVG,STITCH
from limits import MAX_LAYERS
import preferences

INK='http://www.inkscape.org/namespaces/inkscape'

def bean_pattern(value):
    if type(value) is int:value=str(value)
    if not isinstance(value,str) or not re.fullmatch(r'\s*\d{1,3}(?:\s+\d{1,3}){0,19}\s*',value):
        raise ValueError('Bean repeats need 1–20 whole numbers from 0 to 999, separated by spaces.')
    return ' '.join(str(int(v)) for v in value.split())

def place(current,source_ids,result):
    """Match the extension's original groups and newly inserted route group."""
    sources=set(source_ids);removed=set(result.get('removeIds',source_ids));outputs={l['id']:l for l in result['layers']}
    placements=result.get('placements',{});grouped=result.get('groupedIds',[]);last=next(l['id'] for l in reversed(current) if l['id'] in sources)
    result_layers=[]
    for layer in current:
        result_layers.extend(copy.deepcopy(outputs[id]) for id in result.get('beforePlacements',{}).get(layer['id'],[]))
        if layer['id'] not in removed:result_layers.append(copy.deepcopy(layer))
        if layer['id'] in sources:
            result_layers.extend(copy.deepcopy(outputs[id]) for id in placements.get(layer['id'],[]))
        if layer['id']==last:result_layers.extend(copy.deepcopy(outputs[id]) for id in grouped)
    return result_layers

def prepare(data,s,redwork=None):
    from linked import resolve
    from maintenance import validate_helpers
    from operations import editable_output
    layers=data.get('layers');kind='redwork' if redwork is not None else data.get('kind')
    if kind not in ('satin','running','redwork'):raise ValueError('Choose satin, running-stitch or Redwork routing.')
    if not isinstance(layers,list) or not 1<=len(layers)<=30 or any(not isinstance(l,dict) for l in layers):raise ValueError('Select 1–30 artwork layers to route.')
    ids=[l.get('id') for l in layers]
    if len(set(ids))!=len(ids):raise ValueError('Select each artwork layer once.')
    project=data.get('project')
    if project is not None:
        project=resolve(project,s);by_id={l['id']:l for l in project['layers']}
        if any(id not in by_id for id in ids):raise ValueError('The routing selection changed. Reopen the tool.')
        # Native stitch order, rather than the sequence of taps, matches SVG order.
        layers=[l for l in project['layers'] if l['id'] in ids];ids=[l['id'] for l in layers]
        helpers=[l for l in project['layers'] if l.get('helperTarget') in ids]
    else:
        helpers=data.get('helpers',[]);project={'version':1,'layers':layers+helpers}
    if any(l.get('locked') or l.get('visible',True) is False or l.get('type')=='image' or l.get('role','artwork')!='artwork' for l in layers):raise ValueError('Select visible, unlocked stitched artwork to route.')
    helpers=validate_helpers(helpers,layers)
    opts={}
    for key,default in [('preserveOrder',True),('trim',False),('breakUp',True),('keepOriginals',False)]:
        value=data.get(key,default)
        if type(value)is not bool:raise ValueError('Choose valid routing switches.')
        opts[key]=value
    keep=redwork['keep_originals'] if redwork is not None else opts['keepOriginals']
    if kind=='running' and keep:raise ValueError('Keep originals is available for satin and Redwork routing.')
    prepared=copy.deepcopy(layers)
    for layer in prepared:layer.pop('link',None)
    source_project={'version':1,'name':'Routing selection','layers':prepared+helpers,
        'embroiderySettings':preferences.effective(project),'threadBook':project.get('threadBook',{})}
    raw=s.build_svg(source_project);items=geometry(raw);root=s.xml(raw)
    satin=any(str(e.get('{'+STITCH+'}satin_column','')).lower()=='true' for e,_,_ in items)
    strokes=any(str(style.get('stroke','none'))!='none' and str(e.get('{'+STITCH+'}satin_column','')).lower()!='true' and not e.get('{'+INK+'}connection-start') for e,_,style in items)
    if (kind=='satin' and not satin) or (kind!='satin' and not strokes):raise ValueError('Select at least one '+('satin column.' if kind=='satin' else 'running outline.'))
    # Give original paths/commands stable probe IDs so Keep originals can retain
    # their native representation while only generated geometry is exposed.
    for i,e in enumerate(root.iter()):
        if not e.get('id'):e.set('id','route-input-'+str(i))
    original_ids={e.get('id') for e in root.iter() if ET.QName(e).localname not in ('svg','g','defs','metadata','title','desc')}
    source=ET.tostring(root);groups=['layer-'+str(i) for i in range(len(layers))]
    args=[s.ENGINE,'--extension='+('auto_satin' if kind=='satin' else 'auto_run' if kind=='running' else 'redwork'),*['--id='+id for id in groups]]
    if redwork is not None:args+=['--'+k+'='+str(v) for k,v in redwork.items()]
    else:
        args+=['--preserve_order='+str(opts['preserveOrder']),'--trim='+str(opts['trim'])]
        args+=['--break_up='+str(opts['breakUp'])] if kind=='running' else ['--keep_originals='+str(keep)]
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-routing-') as tmp:
        path=Path(tmp)/'source.svg';path.write_bytes(source);output=s.run(args+[str(path)],240,headless=True)
        if not output.strip():raise ValueError('These paths could not be routed. Check the source geometry.')
        doc=s.xml(output)
        order={e.get('id'):i for i,e in enumerate(doc.iter()) if e.get('id')}
        source_positions={layers[int(e.get('id')[6:])]['id']:order[e.get('id')] for e in doc.iter() if re.fullmatch(r'layer-\d+',e.get('id','')) and int(e.get('id')[6:])<len(layers)}
        original_positions={id:[] for id in ids}
        for e in doc.iter():
            if e.get('id') not in original_ids:continue
            for parent in e.iterancestors():
                if parent.get('id') in groups:
                    original_positions[layers[int(parent.get('id')[6:])]['id']].append(order[e.get('id')]);break
        if keep:
            for e in list(doc.iter()):
                if e.get('id') in original_ids and e.getparent() is not None:e.getparent().remove(e)
        output=ET.tostring(doc)
        generated=editable_output(output,s,'Routed '+kind,layers,element_ids=True)
        placements={id:[] for id in ids};before={id:[] for id in ids};grouped=[]
        for layer in generated:
            source_id=layer.pop('_sourceId',None);element_id=layer.pop('_elementId',None)
            position=order.get(element_id,-1)
            if source_id:
                originals=original_positions[source_id]
                if keep and originals and position<min(originals):before[source_id].append(layer['id'])
                elif keep and originals and position<max(originals):raise ValueError('Separate imported SVG paths before keeping originals for this route.')
                else:placements[source_id].append(layer['id'])
            else:
                following=next((id for id in ids if source_positions.get(id,-1)>position),None)
                if following:before[following].append(layer['id'])
                else:grouped.append(layer['id'])
        # Helpers follow their new target, including helpers exposed from SVG.
        for helper in generated:
            if not helper.get('helperTarget'):continue
            for target_ids in [*placements.values(),*before.values(),grouped]:
                if helper['helperTarget'] in target_ids:
                    for location in [*placements.values(),*before.values(),grouped]:
                        if helper['id'] in location:location.remove(helper['id'])
                    target_ids.insert(target_ids.index(helper['helperTarget'])+1,helper['id']);break
        if not generated and keep:raise ValueError('Routing produced no new paths. Original artwork is unchanged.')
        # Routing can join/split across objects, so an attachment does not
        # always have one new target. Retain its editable source as a hidden
        # reference rather than silently dropping or guessing that relationship.
        references=[]
        if helpers and not keep:
            for original in layers:
                attached=[h for h in helpers if h['helperTarget']==original['id']]
                if not attached:continue
                reference=copy.deepcopy(original);reference.pop('link',None)
                reference.update(id=uuid.uuid4().hex,name=original.get('name','Artwork')+' · before routing',visible=False,locked=False)
                references.append(reference)
                for helper in attached:
                    copied=copy.deepcopy(helper);copied.pop('linkedHelper',None)
                    copied.update(id=uuid.uuid4().hex,helperTarget=reference['id']);references.append(copied)
            generated.extend(references);grouped.extend(l['id'] for l in references)
        remove_ids=[] if keep else ids+[h['id'] for h in helpers]
        result={'layers':generated,'placements':placements,'beforePlacements':before,'groupedIds':grouped,'removeIds':remove_ids,'keepOriginals':keep,'retainedHelpers':len(helpers) if references else 0,'tool':kind}
        current=[l for l in project['layers'] if l['id'] in set(ids+[h['id'] for h in helpers])]
        preview_layers=place(current,ids,result)
        if len(preview_layers)>MAX_LAYERS:raise ValueError('The route exceeds the editable layer limit. Select fewer paths.')
        if not any(l.get('role','artwork')=='artwork' for l in preview_layers):raise ValueError('The route removed every path. Reduce the minimum path length.')
        result['preview']=preferences.preview({'project':{**source_project,'layers':preview_layers},'settings':source_project['embroiderySettings']},s)['preview']
    return result
