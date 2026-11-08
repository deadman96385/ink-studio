"""Native path editing and Inkscape-powered vector operations (millimeters)."""
import copy
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import uuid

import studio_runtime
studio_runtime.configure_imports()
import inkex
from lxml import etree as ET

SVG='http://www.w3.org/2000/svg'
STITCH='http://inkstitch.org/namespace'
SODIPODI='http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd'
NODE_TYPES={'corner':'c','smooth':'s','symmetric':'z','auto':'a'}


def contour_node_types(contours):
    return ''.join(''.join(NODE_TYPES.get(n.get('mode'),'c') for n in c['nodes'])+(NODE_TYPES.get(c['nodes'][0].get('mode'),'c') if c.get('closed') else '') for c in contours)

def finite(v,low=-5,high=6):
    if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or not low<=v<=high:
        raise ValueError('Path coordinates are outside the editable range.')
    return v

def contour_d(contours,w,h):
    if not isinstance(contours,list) or not 1<=len(contours)<=100:
        raise ValueError('A path needs 1–100 subpaths.')
    result=[];count=0
    for c in contours:
        nodes=c.get('nodes',[]);count+=len(nodes)
        if not 2<=len(nodes)<=2500 or count>2500:raise ValueError('A path needs 2–2,500 nodes.')
        for n in nodes:
            finite(n['x']);finite(n['y'])
            if 'mode' in n and n['mode'] not in NODE_TYPES:raise ValueError('Choose Corner, Smooth, Symmetric or Auto-smooth for the node.')
            for k in ('in','out'):
                if len(n[k])!=2:raise ValueError('Invalid curve handle.')
                [finite(v) for v in n[k]]
        first=nodes[0];result.append(f'M {first["x"]*w},{first["y"]*h}')
        pairs=list(zip(nodes,nodes[1:]))
        if c.get('closed'):pairs.append((nodes[-1],first))
        for a,b in pairs:
            result.append(f'C {a["out"][0]*w},{a["out"][1]*h} {b["in"][0]*w},{b["in"][1]*h} {b["x"]*w},{b["y"]*h}')
        if c.get('closed'):result.append('Z')
    return ' '.join(result)

def path_contours(path,node_types=None):
    flags=[];current=False
    for cmd in path.to_absolute():
        if cmd.letter=='M':
            if len(flags):flags[-1]=current
            flags.append(False);current=False
        elif cmd.letter=='Z':current=True
    if flags:flags[-1]=current
    output=[]
    for i,sub in enumerate(path.to_superpath()):
        closed=flags[i] if i<len(flags) else False
        # An explicit closing cubic followed by Z can produce two copies of
        # the start point. Drop only empty closing segments, retaining loops.
        while closed and len(sub)>2 and math.dist(sub[-1][1],sub[0][1])<1e-7 and math.dist(sub[-2][1],sub[-1][1])<1e-7 and math.dist(sub[-2][2],sub[-2][1])<1e-7 and math.dist(sub[-1][0],sub[-1][1])<1e-7:
            sub=sub[:-1]
        if closed and len(sub)>1 and math.dist(sub[0][1],sub[-1][1])<1e-7:
            sub[0][0]=sub[-1][0];sub=sub[:-1]
        if len(sub)<2:continue
        output.append({'closed':closed,'nodes':[{'x':n[1][0],'y':n[1][1],'in':list(n[0]),'out':list(n[2])} for n in sub]})
    if node_types:
        # Inkscape repeats the first node's type at the end of closed subpaths.
        # Do not misassign metadata when an arc conversion added extra nodes.
        count=sum(len(c['nodes']) for c in output);repeated=sum(bool(c['closed']) for c in output)
        if len(node_types) in (count,count+repeated):
            mapping={v:k for k,v in NODE_TYPES.items()};offset=0;duplicate=len(node_types)==count+repeated
            for c in output:
                for n in c['nodes']:
                    if node_types[offset] in mapping:n['mode']=mapping[node_types[offset]]
                    offset+=1
                if c['closed'] and duplicate:offset+=1
    return output

def from_path(path,base=None,node_types=None,max_size=100):
    box=path.bounding_box()
    if box is None:raise ValueError('This operation produced no path.')
    x,y,w,h=float(box.left),float(box.top),max(.2,float(box.width)),max(.2,float(box.height))
    if w>max_size+.05 or h>max_size+.05:raise ValueError(f'The result is larger than the {max_size:g} mm hoop. Resize the source first.' if max_size<=300 else 'The helper exceeds the supported area. Resize the source first.')
    contours=path_contours(path,node_types)
    for c in contours:
        for n in c['nodes']:
            n['x']=(n['x']-x)/w;n['y']=(n['y']-y)/h
            for k in ('in','out'):n[k]=[(n[k][0]-x)/w,(n[k][1]-y)/h]
    result={**(base or {}),'id':uuid.uuid4().hex,'type':'path','name':(base or {}).get('name','Editable path'),
            'x':x,'y':y,'width':w,'height':h,'rotation':0,'flipX':False,'flipY':False,
            'contours':contours,'visible':True,'background':False,'locked':False}
    for k in ('asset','lettering','points','groupId'):result.pop(k,None)
    if base and all(k in base for k in ('width','height','x','y')):
        for key in ('entry','exit','targetPoint','routeStart','routeEnd','satinCut','trimCommand','stopCommand','ignoreObject','ignoreLayer'):
            if base.get(key) is None:continue
            px,py=base[key];a=math.radians(base.get('rotation',0));c,s=math.cos(a),math.sin(a)
            px=((1-px) if base.get('flipX') else px)*base['width']-base['width']/2
            py=((1-py) if base.get('flipY') else py)*base['height']-base['height']/2
            wx=base['x']+base['width']/2+px*c-py*s;wy=base['y']+base['height']/2+px*s+py*c
            result[key]=[(wx-x)/w,(wy-y)/h]
    result.setdefault('color','#203f38');result.setdefault('stitch','fill')
    if base and base.get('streamlines') and all(k in base for k in ('width','height','x','y')):
        result['streamlines']=copy.deepcopy(base['streamlines']);a=math.radians(base.get('rotation',0));c,sn=math.cos(a),math.sin(a)
        for guide in result['streamlines']['guides']:
            for p in guide['points']:
                px=((1-p[0]) if base.get('flipX') else p[0])*base['width']-base['width']/2
                py=((1-p[1]) if base.get('flipY') else p[1])*base['height']-base['height']/2
                p[:]=[(base['x']+base['width']/2+px*c-py*sn-x)/w,(base['y']+base['height']/2+px*sn+py*c-y)/h]
        result.pop('streamlinePreview',None)
    return result

def geometry(svg,allow_effects=False):
    root=inkex.load_svg(io.BytesIO(svg)).getroot()
    if not allow_effects:
        from svg_structure import require_geometry
        require_geometry(root)
    result=[]
    for e in root.iter():
        if not isinstance(e,inkex.ShapeElement) or e.tag.rsplit('}',1)[-1] not in ('path','rect','ellipse','circle','polygon','polyline','line'):continue
        if any(a.tag.rsplit('}',1)[-1]=='defs' or a.specified_style().get('display')=='none' for a in e.iterancestors()):continue
        style=e.specified_style()
        if style.get('display')=='none' or style.get('visibility')=='hidden':continue
        result.append((e,e.path.transform(e.composed_transform()),style))
    return result

def vector_operation(data,s):
    op=data.get('operation');layers=data.get('layers')
    if op not in ('nodes','explode','union','difference','intersection','exclusion','combine','break-apart','simplify','division','cut'):
        raise ValueError('Unknown vector operation.')
    if not isinstance(layers,list) or not 1<=len(layers)<=30:raise ValueError('Select 1–30 layers.')
    if any(l.get('locked') for l in layers):raise ValueError('Unlock the layers first.')
    if any(l.get('type')=='image' for l in layers):raise ValueError('Trace the reference image to create editable paths first.')
    if op!='explode' and any(l.get('type')=='text' for l in layers):
        raise ValueError('Use Separate SVG / lettering paths first to preserve the embroidery font’s stitch geometry.')
    if op not in ('nodes','explode') and any(l.get('stitch')=='satin' or str(l.get('originalParams',{}).get('satin_column','')).lower()=='true' for l in layers):
        raise ValueError('Use Edit nodes to change satin rails and rungs. Shape operations require filled shapes.')
    if op in ('nodes','explode','break-apart','simplify') and len(layers)!=1:raise ValueError('Select one layer for this operation.')
    if op in ('difference','division','cut') and len(layers)!=2:raise ValueError('Select two layers. The later layer cuts the earlier layer.')
    helper_mode=op=='nodes' and all(l.get('role') in ('guide-line','anchor-line','pattern') for l in layers)
    source=s.build_svg({'version':1,'layers':[{**l,'visible':True,'borderEnabled':False,'role':'artwork','helperTarget':None,
        **({'multicolorSatin':None,'merrow':None,'feather':None,**({'fillMethod':'tatami_fill','smallFillFallback':False} if l.get('fillMethod') in ('streamline_fill','wave_fill') else {})} if op=='nodes' else {})} for l in layers]},helper_mode=helper_mode)
    items=geometry(source)
    if not items:raise ValueError('There are no editable paths in this selection.')
    base=copy.deepcopy(layers[0])
    if op not in ('nodes','explode') and base.get('stitch')=='original':
        # A native path cannot depend on an SVG asset for its inherited paint or
        # Ink/Stitch attributes after the geometry operation removes that asset.
        base=vector_operation({'operation':'nodes','layers':[layers[0]]},s)['layers'][0]
    if op=='explode':
        from operations import editable_output
        return {'layers':editable_output(source,s,base.get('name','SVG')+' · path')}
    if op=='nodes':
        # Preserve compound holes and explicitly preserve original stitch params.
        combined=inkex.Path()
        for _,path,_ in items:combined.extend(path)
        if len(items)>1 and base.get('stitch')=='original':
            raise ValueError('Use Separate SVG paths first to preserve each path’s color and stitch settings.')
        if base.get('stitch')=='original':
            e,_,style=items[0];base['originalParams']={ET.QName(k).localname:v for k,v in e.attrib.items() if k.startswith('{'+STITCH+'}')}
            base['originalFill']=str(style.get('fill','black'))!='none';base['originalStroke']=str(style.get('stroke','none'))!='none'
            if base['originalFill'] and base['originalStroke']:raise ValueError('Use Separate SVG paths to keep the fill and outline independently editable.')
            base['originalFillRule']=str(style.get('fill-rule','nonzero'))
            base['originalWidth']=float(inkex.units.convert_unit(str(style.get('stroke-width',.3)),'px'))*s.stroke_scale(e)
            paint=style.get('fill','black') if base['originalFill'] else style.get('stroke')
            base['color']='#%02x%02x%02x'%tuple(inkex.Color(paint).to_rgb())
        if base.get('type')=='text':base['stitch']='fill'
        return {'layers':[from_path(combined,base,items[0][0].get('{'+SODIPODI+'}nodetypes') if len(items)==1 else None,max_size=10000 if helper_mode else 100)]}
    if op=='break-apart':
        result=[]
        for _,path,_ in items:
            for contour in path_contours(path):
                # Construct directly in document units; contour_d validates normalized values.
                nodes=contour['nodes'];d=f'M {nodes[0]["x"]},{nodes[0]["y"]}'
                for a,b in list(zip(nodes,nodes[1:]))+([(nodes[-1],nodes[0])] if contour['closed'] else []):d+=f' C {a["out"][0]},{a["out"][1]} {b["in"][0]},{b["in"][1]} {b["x"]},{b["y"]}'
                if contour['closed']:d+=' Z'
                result.append(from_path(inkex.Path(d),base))
        return {'layers':result}
    root=s.svg_root()
    if op in ('division','cut') and len(items)!=2:raise ValueError('Select two individual paths. Separate imported SVG paths first.')
    for i,(_,path,style) in enumerate(items):ET.SubElement(root,f'{{{SVG}}}path',id=f'operand-{i}',d=str(path),style='fill:#203f38;stroke:none;fill-rule:'+str(style.get('fill-rule','nonzero')))
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='vector-') as tmp:
        src=Path(tmp)/'input.svg';out=Path(tmp)/'result.svg';src.write_bytes(ET.tostring(root))
        s.run(['inkscape',str(src),'--actions=select-by-element:path;path-'+op+';export-filename:'+str(out)+';export-do'])
        paths=geometry(out.read_bytes())
    if op in ('division','cut'):
        result=[]
        for _,path,_ in paths:
            parts=[]
            if op=='cut':
                parts=[inkex.Path(str(inkex.CubicSuperPath([sub]).to_path())) for sub in path.to_superpath()]
            else:parts=[path]
            for piece in parts:result.append(from_path(piece,{**base,'name':'Cut outline' if op=='cut' else 'Divided shape','stitch':'running' if op=='cut' else 'fill','originalParams':{}}))
        if not result:raise ValueError('The cutter leaves no paths. Your original layers are unchanged.')
        return {'layers':result}
    combined=inkex.Path()
    for _,path,_ in paths:combined.extend(path)
    if not combined:raise ValueError('The shapes do not leave a visible result. Your original layers are unchanged.')
    settings=base if op in ('combine','simplify') else {**base,'stitch':'fill','originalParams':{}}
    return {'layers':[from_path(combined,{**settings,'name':op.replace('-',' ').title()})]}

def curve_frame(old,reference,new):
    """Carry the template's later moves/scales/flips around its original guide."""
    sx=old['width']/reference['width'];sy=old['height']/reference['height'];angle=math.radians(old.get('rotation',0))
    dx=(new['x']+new['width']/2-reference['x']-reference['width']/2)*sx*(-1 if old.get('flipX') else 1)
    dy=(new['y']+new['height']/2-reference['y']-reference['height']/2)*sy*(-1 if old.get('flipY') else 1)
    w=new['width']*sx;h=new['height']*sy
    return dict(x=old['x']+old['width']/2+math.cos(angle)*dx-math.sin(angle)*dy-w/2,y=old['y']+old['height']/2+math.sin(angle)*dx+math.cos(angle)*dy-h/2,width=w,height=h,rotation=old.get('rotation',0),flipX=old.get('flipX',False),flipY=old.get('flipY',False))


def curved_lettering(data,s):
    text=data.get('textLayer');guide=data.get('guideLayer');position=data.get('position','center');vertical=data.get('vertical','baseline')
    if not isinstance(text,dict) or text.get('type')!='text' or not isinstance(guide,dict):raise ValueError('Choose a lettering block and one path.')
    if position not in ('left','center','right','stretch') or vertical not in ('top','baseline','bottom'):raise ValueError('Choose a valid lettering alignment.')
    if text.get('locked') or guide.get('locked'):raise ValueError('Unlock the text and guide first.')
    guide_artwork={**guide,'role':'artwork','helperTarget':None}
    source=s.build_svg({'version':1,'layers':[text,guide_artwork]});root=s.xml(source)
    lettering=root.find(f'.//{{{SVG}}}g[@{{{STITCH}}}lettering]')
    if lettering is None:raise ValueError('This layer has no editable lettering.')
    if position=='stretch':
        lines=lettering.findall(f'.//{{{SVG}}}g[@{{{STITCH}}}letter-group="line"]')
        if any(len(line.findall(f'.//{{{SVG}}}g[@{{{STITCH}}}letter-group="glyph"]'))<2 for line in lines):raise ValueError('Spread letters needs at least two glyphs on each line. Use Start, Center or End for a single glyph.')
    # 3.3.0's path tool does not reverse alternate lines when consuming the
    # batch extension's back-and-forth layout. Keep each line in reading order.
    settings=json.loads(lettering.get(f'{{{STITCH}}}lettering'))
    settings['back_and_forth']=False
    lettering.set(f'{{{STITCH}}}lettering',json.dumps(settings))
    lettering.set('id','curve-text')
    paths=geometry(s.build_svg({'version':1,'layers':[guide_artwork]}))
    if len(paths)!=1 or len(path_contours(paths[0][1]))!=1:raise ValueError('Use a single continuous path as the lettering guide.')
    path=paths[0][1]
    if data.get('reverse'):path=path.reverse()
    guide_group=root[-1];root.remove(guide_group)
    ET.SubElement(root,f'{{{SVG}}}path',id='curve-guide',d=str(path),style='fill:none;stroke:#203f38;stroke-width:.2')
    cache_key=s.hashlib.sha256(b'curve-reading-order-v1'+ET.tostring(root)+position.encode()+b'|'+vertical.encode()).hexdigest()
    cache=s.DATA/'cache'/('curve-'+cache_key+'.json')
    cached=json.loads(cache.read_text()) if cache.exists() else None
    if cached:
        asset=cached['asset'];x,y,w,h=cached['frame'];key=asset['key']
        if not (s.DATA/'assets'/(key+'.json')).exists():s.write_atomic(s.DATA/'assets'/(key+'.json'),asset)
    else:
        with s.ENGINE_LOCK:
            if cache.exists():
                cached=json.loads(cache.read_text());asset=cached['asset'];x,y,w,h=cached['frame'];key=asset['key']
            else:
                with tempfile.TemporaryDirectory(prefix='curve-text-') as tmp:
                    p=Path(tmp)/'source.svg';p.write_bytes(ET.tostring(root))
                    output=s.run([s.ENGINE,'--extension=lettering_along_path','--id=curve-text','--id=curve-guide','--text-position='+position,'--vertical-alignment='+vertical,str(p)])
                    doc=s.xml(output)
                    for e in doc.xpath('//*[@id="curve-guide"]'):e.getparent().remove(e)
                    # The extension regenerates glyphs from its font; restore the chosen
                    # thread color after that regeneration.
                    if not text.get('preserveFontColors'):s.paint(doc,s.color(text['color']))
                    p.write_bytes(ET.tostring(doc));x,y,w,h=s.bounds(p)
                    if w>100 or h>100:raise ValueError('The curved lettering exceeds the hoop. Use a smaller font or a flatter guide.')
                    g=ET.Element(f'{{{SVG}}}g',nsmap=s.NS,transform=f'translate({-x},{-y})')
                    for e in doc:
                        if ET.QName(e).localname not in ('title','metadata','namedview'):g.append(copy.deepcopy(e))
                    raw=ET.tostring(g,encoding='unicode');key=s.hashlib.sha256(raw.encode()).hexdigest()
                    asset={'key':key,'width':w,'height':h,'svg':raw,'name':'Curved '+text.get('lettering',{}).get('text','lettering')[:60]}
                    s.write_atomic(s.DATA/'assets'/(key+'.json'),asset)
                s.write_atomic(cache,{'asset':asset,'frame':[x,y,w,h]})
    layer={**text,'id':uuid.uuid4().hex,'type':'import','name':asset['name'],'asset':key,'stitch':'original','recolor':False,
           'x':x,'y':y,'width':w,'height':h,'rotation':0,'flipX':False,'flipY':False,
           'curveSource':{'textLayer':text,'guideLayer':guide,'position':position,'vertical':vertical,'reverse':bool(data.get('reverse')),'frame':{'x':x,'y':y,'width':w,'height':h}}}
    layer.pop('lettering',None);layer.pop('groupId',None)
    previous=data.get('previousLayer')
    if previous is not None:
        if not isinstance(previous,dict) or not isinstance(previous.get('curveSource'),dict):raise ValueError('Choose an editable curved-lettering layer.')
        if previous.get('locked'):raise ValueError('Unlock the curved-lettering layer first.')
        # Recreate the original guide frame before applying any later layer pose.
        # Re-centering by the new bounds would cancel Start/End and line offsets.
        original=copy.deepcopy(previous['curveSource'])
        original={k:original[k] for k in ('textLayer','guideLayer','position','vertical','reverse') if k in original}
        for key in ('textLayer','guideLayer'):
            if not isinstance(original.get(key),dict):raise ValueError('The curved-lettering source is incomplete.')
            original[key].update(locked=False,visible=True)
        for key in ('x','y'):s.number(previous.get(key),-10000,10000,'Curve position')
        for key in ('width','height'):s.number(previous.get(key),.000001,10000,'Curve size')
        s.number(previous.get('rotation',0),-36000,36000,'Curve rotation')
        reference=previous['curveSource'].get('frame')
        if not isinstance(reference,dict):reference=curved_lettering(original,s)['layer']
        for key in ('x','y'):s.number(reference.get(key),-10000,10000,'Source curve position')
        for key in ('width','height'):s.number(reference.get(key),.000001,10000,'Source curve size')
        layer.update(curve_frame(previous,reference,layer))
    return {'layer':layer,'asset':asset}

POSITION_COMMANDS={'entry':'starting_point','exit':'ending_point','targetPoint':'target_point',
                   'routeStart':'autoroute_start','routeEnd':'autoroute_end','satinCut':'satin_cut_point',
                   'trimCommand':'trim','stopCommand':'stop','ignoreObject':'ignore_object'}

def command_symbol(root,command):
    defs=root.find(f'{{{SVG}}}defs')
    if defs is None:defs=ET.SubElement(root,f'{{{SVG}}}defs')
    symbol_id='inkstitch_'+command
    if not root.xpath('//*[@id=$id]',id=symbol_id):ET.SubElement(defs,f'{{{SVG}}}symbol',id=symbol_id)
    return '#'+symbol_id

def attach_position_commands(root,group,target,layer,end_target=None):
    """Connected commands follow the layer's rotation, mirrors and resizing."""
    mode=layer.get('stitch','fill')
    for key,command in POSITION_COMMANDS.items():
        pos=layer.get(key)
        if pos is None:continue
        if key=='trimCommand' and not layer.get('trimAfter',str(layer.get('originalParams',{}).get('trim_after','')).lower()=='true'):continue
        if key=='stopCommand' and not layer.get('stopAfter',str(layer.get('originalParams',{}).get('stop_after','')).lower()=='true'):continue
        if key in ('entry','exit') and mode not in ('fill','satin','original'):continue
        if not isinstance(pos,list) or len(pos)!=2:raise ValueError('Invalid stitch position.')
        x=finite(pos[0],-500,500)*layer['width'];y=finite(pos[1],-500,500)*layer['height']
        href=command_symbol(root,command)
        dest=end_target if key in ('exit','routeEnd','trimCommand','stopCommand') and end_target is not None else target
        token=layer['id']+'-'+key;target_id=dest.get('id') or 'target-'+token;dest.set('id',target_id)
        commands=ET.SubElement(group,f'{{{SVG}}}g',id='command_group-'+token,style='display:none')
        use=ET.SubElement(commands,f'{{{SVG}}}use',id='position-'+token,x=str(x),y=str(y))
        use.set('{http://www.w3.org/1999/xlink}href',href)
        connector=ET.SubElement(commands,f'{{{SVG}}}path',d=f'M{x},{y} L{layer["width"]/2},{layer["height"]/2}',style='fill:none;stroke:#333;stroke-width:.2;stroke-opacity:.5')
        connector.set('{http://www.inkscape.org/namespaces/inkscape}connection-start','#position-'+token)
        connector.set('{http://www.inkscape.org/namespaces/inkscape}connection-end','#'+target_id)
    pos=layer.get('ignoreLayer')
    if pos is not None:
        if not isinstance(pos,list) or len(pos)!=2:raise ValueError('Invalid ignore-layer position.')
        x=finite(pos[0],-500,500)*layer['width'];y=finite(pos[1],-500,500)*layer['height']
        use=ET.SubElement(group,f'{{{SVG}}}use',id='ignore-layer-'+layer['id'],x=str(x),y=str(y),style='display:none')
        use.set('{http://www.w3.org/1999/xlink}href',command_symbol(root,'ignore_layer'))

def attach_global_commands(root,project):
    for key,command in [('origin','origin'),('frameOut','stop_position')]:
        pos=project.get(key)
        if pos is None:continue
        if not isinstance(pos,list) or len(pos)!=2:raise ValueError('Invalid export position.')
        x,y=[finite(v,0,100) for v in pos]
        href=command_symbol(root,command)
        group=ET.SubElement(root,f'{{{SVG}}}g',style='display:none',attrib={'data-native-commands':'true'})
        use=ET.SubElement(group,f'{{{SVG}}}use',id='global-'+command,x=str(x),y=str(y))
        use.set('{http://www.w3.org/1999/xlink}href',href)
