"""Installed embroidery transforms with native guides and command positions."""
import copy,io,json,math,tempfile,uuid,re
from pathlib import Path
from lxml import etree as ET
from digitizing import inkex,geometry,SVG,STITCH
from preferences import preview,effective

INK='http://www.inkscape.org/namespaces/inkscape'
XLINK='http://www.w3.org/1999/xlink'
ANGLES=('angle','fill_underlay_angle','meander_angle','tartan')

def prepare_gradients(doc,ids):
    from svg_clipping import freeze_gradients
    result=[]
    for id in ids:
        node=doc.getElementById(id);freeze_gradients(node,doc)
        for paint in ('fill','stroke'):
            match=re.fullmatch(r'url\(#([\w.:-]+)\)',str(node.specified_style().get(paint,'none')))
            if not match:continue
            gradient=doc.find(".//*[@id='"+match[1]+"']")
            if gradient is None or gradient.tag!='{'+SVG+'}linearGradient':raise ValueError('Convert unsupported gradient paints before transforming this artwork.')
            saved=copy.deepcopy(gradient);saved.set('id','transform-gradient-'+uuid.uuid4().hex);doc.defs.append(saved)
            result.append((id,paint,saved.get('id'),node.composed_transform(),inkex.Transform(saved.get('gradientTransform',''))))
            # The installed transform's fill query crashes on URL paints. A
            # temporary solid fill lets it transform geometry and stitch angles.
            node.style[paint]='#000000'
    return result

def finish_gradients(doc,gradients,matrix):
    for id,paint,gradient_id,old_frame,old_gradient in gradients:
        node=doc.getElementById(id);gradient=doc.getElementById(gradient_id)
        gradient.set('gradientTransform',str(-node.composed_transform() @ matrix @ old_frame @ old_gradient))
        node.style[paint]='url(#'+gradient_id+')'

def turn(value,p,tartan=False):
    angle=float(value)+(p['rotate'] if tartan else -p['rotate'])
    if p['flip-horizontally']:angle=-angle
    if p['flip-vertically']:angle=-angle
    return angle

def follow_angles(before,after,p):
    """Keep the installed algorithm, correcting its scalar-only underlay parser."""
    for id,source in before.items():
        target=after.getElementById(id)
        if target is None:raise ValueError('The transform did not retain every source path.')
        if not p['followAngles']:
            for key in ANGLES:
                attr='{'+STITCH+'}'+key;value=source.get(attr)
                if value is None:target.attrib.pop(attr,None)
                else:target.set(attr,value)
            continue
        if str(source.specified_style().get('fill','black'))=='none':continue
        value=source.get('{'+STITCH+'}fill_underlay_angle')
        if value is not None:
            try:angles=[float(v) for v in value.replace(',',' ').split()]
            except ValueError:continue
            if angles:target.set('{'+STITCH+'}fill_underlay_angle',' '.join(f'{turn(v,p):.12g}' for v in angles))

def transform_helper(helper,matrix,p):
    result=copy.deepcopy(helper);w,h=result['width'],result['height']
    cx,cy=matrix.apply_to_point((result['x']+w/2,result['y']+h/2))
    result['x']=float(cx)-w/2;result['y']=float(cy)-h/2
    angle=result.get('rotation',0)+p['rotate']
    for field,flip in [('flip-horizontally','flipX'),('flip-vertically','flipY')]:
        if p[field]:angle=-angle;result[flip]=not result.get(flip,False)
    result['rotation']=(angle+180)%360-180;result.pop('linkedHelper',None)
    return result

def prepare(layers,helpers,p,s,project=None):
    if not p['rotate'] and not p['flip-horizontally'] and not p['flip-vertically']:raise ValueError('Choose a rotation or mirror direction.')
    if project is not None:
        from linked import resolve
        from maintenance import validate_helpers
        resolved=resolve(project,s);selected={l['id'] for l in layers};by_id={l['id']:l for l in resolved['layers']}
        if not selected<=by_id.keys():raise ValueError('The transform selection changed. Open the tool again.')
        layers=[by_id[l['id']] for l in layers]
        if any(l.get('locked') or not l.get('visible',True) or l.get('role','artwork')!='artwork' or l.get('type')=='image' for l in layers):raise ValueError('Select visible, unlocked embroidery artwork.')
        helpers=validate_helpers([h for h in resolved['layers'] if h.get('helperTarget') in selected and h.get('role') in ('guide-line','anchor-line','pattern')],layers)
    prepared=copy.deepcopy(layers)
    for layer in prepared:layer.pop('link',None)
    source=s.build_svg({'version':1,'layers':prepared})
    # Explicit geometry validation gives the existing preparation workflow for
    # live masks/clones/clips, rather than losing those effects during conversion.
    geometry(source)
    doc=inkex.load_svg(io.BytesIO(source)).getroot()
    ids=[e.get('id') for e,_,_ in geometry(source) if e.get('id') and not e.get('{'+INK+'}connection-start')]
    if not ids:raise ValueError('Select visible stitched artwork to transform.')
    # Selecting child paths makes Ink/Stitch 3.3.0 measure their local bounds
    # without parent translations. Top-level native groups provide world bounds.
    group_ids=['layer-'+str(i) for i in range(len(layers))]
    doc.selection.set(*group_ids);center=doc.selection.bounding_box().center
    matrix=inkex.Transform(f'rotate({p["rotate"]},{center.x},{center.y})')
    for enabled,scale in [(p['flip-horizontally'],'-1,1'),(p['flip-vertically'],'1,-1')]:
        if enabled:matrix=inkex.Transform(f'translate({center.x},{center.y}) scale({scale}) translate({-center.x},{-center.y})') @ matrix
    original={id:copy.deepcopy(doc.getElementById(id)) for id in ids}
    # deepcopy loses ancestry needed for inherited paint. Freeze it first.
    for id in ids:original[id].set('style',str(doc.getElementById(id).specified_style()))
    gradients=prepare_gradients(doc,ids)
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-transform-') as tmp:
        file=Path(tmp)/'source.svg';file.write_bytes(ET.tostring(doc))
        args=[s.ENGINE,'--extension=transform_elements',*['--id='+id for id in group_ids],*['--'+k+'='+str(p[k]) for k in ('rotate','flip-horizontally','flip-vertically')],str(file)]
        transformed=inkex.load_svg(io.BytesIO(s.run(args,headless=True))).getroot()
        follow_angles(original,transformed,p)
        finish_gradients(transformed,gradients,matrix)
        # Desktop transformations skip visual commands and marked helpers.
        # Their locations are world-space data, so apply the same matrix.
        for e in transformed.iter():
            if not isinstance(e,inkex.ShapeElement) or e.get('id') in ids:continue
            href=e.get('{'+XLINK+'}href',e.get('href',''))
            command=e.get('{'+INK+'}connection-start') or (e.tag=='{'+SVG+'}use' and href.startswith('#inkstitch_'))
            helper='inkstitch-' in str(e.specified_style().get('marker-start',''))
            if not (command or helper) or any(a.tag in ('{'+SVG+'}defs','{'+SVG+'}symbol') for a in e.iterancestors()):continue
            parent=e.getparent().composed_transform();e.transform=-parent @ matrix @ e.composed_transform()
        result=[];assets=[];placements={}
        for i,layer in enumerate(layers):
            group=transformed.getElementById('layer-'+str(i))
            if group is None:raise ValueError('The transform did not retain its source layer.')
            root=s.svg_root()
            for e in transformed:
                if e.tag in ('{'+SVG+'}defs','{'+SVG+'}metadata'):root.append(copy.deepcopy(e))
            root.append(copy.deepcopy(group));raw=ET.tostring(root);file.write_bytes(raw)
            x,y,w,h=s.bounds(file)
            if x<-.1 or y<-.1 or x+w>100.1 or y+h>100.1:raise ValueError('The transformed selection extends outside the hoop. Move it inward or use a smaller rotation.')
            asset=s.import_svg({'svg':raw.decode(),'name':layer.get('name','Transformed artwork')})
            new={'id':layer['id'],'type':'import','name':layer.get('name','Transformed artwork'),'asset':asset['key'],'x':x,'y':y,'width':asset['width'],'height':asset['height'],
                 'rotation':0,'flipX':False,'flipY':False,'visible':True,'locked':False,'color':layer.get('color','#203f38'),'stitch':'original','recolor':False}
            for key in ('groupId','background','aspectLock'):
                if key in layer:new[key]=layer[key]
            result.append(new);assets.append(asset);placements[layer['id']]=[layer['id']]
        result.extend(transform_helper(h,matrix,p) for h in helpers)
        if p.get('keepSource'):
            for layer in layers:
                saved=copy.deepcopy(layer);saved.update(id=uuid.uuid4().hex,groupId=uuid.uuid4().hex,visible=False,locked=False,name=layer.get('name','Artwork')+' · source (hidden)');saved.pop('link',None)
                result.append(saved);placements[layer['id']].insert(0,saved['id'])
                for helper in helpers:
                    if helper.get('helperTarget')!=layer['id']:continue
                    h=copy.deepcopy(helper);h.update(id=uuid.uuid4().hex,helperTarget=saved['id'],groupId=saved['groupId'],visible=False,locked=False);h.pop('linkedHelper',None);result.append(h)
        if len(result)>s.MAX_LAYERS:raise ValueError('Keeping sources would exceed the layer limit. Transform a smaller selection.')
        report=preview({'project':{'version':1,'layers':result},'settings':effective()},s)['preview']
    return {'layers':result,'assets':assets,'placements':placements,'preview':report,'tool':'transform_elements','center':[float(center.x),float(center.y)]}
