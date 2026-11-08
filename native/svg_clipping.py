"""Resolve SVG clipping in document mm while retaining paints and stitch data."""
import copy,io,re,uuid
from digitizing import inkex
from lxml import etree as ET
from shapely import unary_union,make_valid
from shapely.geometry import Polygon,LineString
from applique import flattened
from components import path_polygon,polygon_path as area_path
from digitizing import path_contours
from svg_structure import SVG,INK,SHAPES,tag,href,properties,visible,features,clone
STITCH='http://inkstitch.org/namespace'

def closed(path):return inkex.Path(' '.join(str(p)+('' if p[-1].letter=='Z' else ' Z') for p in path.break_apart() if p))
def polygon(path,rule):
    if not path:return Polygon()
    return make_valid(path_polygon(closed(path),rule))
def polygon_path(shape):
    # Polygon intersections can also contain touching lines or points.
    if shape.geom_type=='GeometryCollection':return inkex.Path(' '.join(str(polygon_path(g)) for g in shape.geoms))
    return area_path(shape)

def local_path(owner):
    if tag(owner)!='g':return owner.path
    path=inkex.Path()
    for child in owner:
        if properties(child).get('display')=='none':continue
        if tag(child) in SHAPES|{'g','image'}:path.extend(local_path(child).transform(child.transform))
    return path

def freeze_gradients(element,root):
    """Keep object-bounding-box color positions when clipped bounds shrink."""
    style=element.specified_style()
    for paint in ('fill','stroke'):
        match=re.fullmatch(r'url\(#([\w.:-]+)\)',str(style.get(paint,'none')))
        if not match:continue
        gradient=root.getElementById(match[1]);attributes={};stops=None;seen=set()
        while gradient is not None and tag(gradient)=='linearGradient':
            if gradient.get('id') in seen:raise ValueError('The gradient contains a reference loop.')
            seen.add(gradient.get('id'))
            for k,v in gradient.attrib.items():attributes.setdefault(k,v)
            if stops is None and len(gradient):stops=[copy.deepcopy(n) for n in gradient if tag(n)=='stop']
            gradient=root.getElementById(href(gradient).lstrip('#')) if href(gradient) else None
        if attributes.get('gradientUnits','objectBoundingBox')!='objectBoundingBox':continue
        bounds=element.path.bounding_box()
        if bounds is None:continue
        frozen=ET.Element('{'+SVG+'}linearGradient',id='clip-gradient-'+uuid.uuid4().hex,gradientUnits='userSpaceOnUse')
        for key,default in [('x1','0'),('y1','0'),('x2','1'),('y2','0')]:
            value=attributes.get(key,default);frozen.set(key,str(float(value[:-1])/100 if value.endswith('%') else float(value)))
        transform=inkex.Transform(translate=(bounds.left,bounds.top))@inkex.Transform(scale=(bounds.width,bounds.height))@inkex.Transform(attributes.get('gradientTransform',''))
        frozen.set('gradientTransform',str(transform))
        if 'spreadMethod' in attributes:frozen.set('spreadMethod',attributes['spreadMethod'])
        frozen.extend(stops or [])
        root.defs.append(frozen);st=inkex.Style(element.get('style',''));st[paint]='url(#'+frozen.get('id')+')';element.set('style',str(st))

class Clips:
    def __init__(self,root):self.root=root;self.cache={};self.count=0
    def own(self,owner,frame=None,chain=()):
        value=properties(owner).get('clip-path','none')
        ancestor=owner.getparent()
        while value=='inherit' and ancestor is not None:value=properties(ancestor).get('clip-path','none');ancestor=ancestor.getparent()
        if value=='none':return None
        match=re.fullmatch(r'url\(#([\w.:-]+)\)',value)
        if not match:raise ValueError('The SVG has an invalid clipping reference.')
        id=match[1]
        if id in chain or len(chain)>24:raise ValueError('Clipping paths cannot contain circular or deep references.')
        clip=self.root.getElementById(id)
        if clip is None or tag(clip)!='clipPath':raise ValueError('The clipping path is missing.')
        transform=owner.composed_transform() if frame is None else frame
        if clip.get('clipPathUnits','userSpaceOnUse')=='objectBoundingBox':
            bounds=local_path(owner).bounding_box()
            if bounds is None or min(float(bounds.width),float(bounds.height))<=0:return Polygon()
            transform=transform@inkex.Transform(translate=(bounds.left,bounds.top))@inkex.Transform(scale=(bounds.width,bounds.height))
        key=(id,str(transform))
        if key not in self.cache:self.cache[key]=self.children(clip,transform@clip.transform,chain+(id,))
        return self.cache[key]
    def children(self,parent,transform,chain):
        shapes=[]
        for child in parent:
            if properties(child).get('display')=='none' or properties(child).get('visibility')=='hidden':continue
            frame=transform@child.transform
            if clone(child):raise ValueError('Enable recursive clone unlinking before baking clipping paths.')
            if tag(child) in SHAPES:
                self.count+=1
                if self.count>20000:raise ValueError('Too many clipping shapes. Simplify the SVG first.')
                shape=polygon(child.path.transform(frame),str(child.specified_style().get('clip-rule','nonzero')))
            elif tag(child)=='g':shape=self.children(child,frame,chain)
            else:continue
            nested=self.own(child,frame,chain)
            if nested is not None:shape=shape.intersection(nested)
            shapes.append(shape)
        result=make_valid(unary_union(shapes))
        nested=self.own(parent,transform,chain)
        if nested is not None:result=result.intersection(nested)
        return result
    def effective(self,element):
        result=None
        for owner in [element,*element.iterancestors()]:
            if not isinstance(owner,inkex.ShapeElement):continue
            shape=self.own(owner)
            if shape is not None:result=shape if result is None else result.intersection(shape)
        return result

def clear_clip(element):
    element.attrib.pop('clip-path',None);style=inkex.Style(element.get('style',''));style.pop('clip-path',None)
    if style:element.set('style',str(style))
    elif element.get('style') is not None:element.attrib.pop('style')

def clip_lines(path,region):
    output=inkex.Path()
    for piece in clip_needle_path(path,region,.01):output.extend(piece)
    return output

def inkex_point(point):
    from shapely.geometry import Point
    return Point(point)

def clip_needle_path(path,region,tolerance=.001):
    """Clip each sewn segment separately, retaining backtracks and repeated points."""
    chunks=[];current=[]
    def finish():
        nonlocal current
        if len(current)>1:chunks.append(inkex.Path('M'+' L'.join(f'{x:.8f},{y:.8f}' for x,y in current)))
        current=[]
    for contour in path_contours(path):
        finish();points=flattened(contour,tolerance)
        for a,b in zip(points,points[1:]):
            if a==b:
                if region.covers(inkex_point(a)):
                    if not current:current.append(a)
                    current.append(b)
                continue
            line=LineString([a,b]);intersection=line.intersection(region)
            pieces=[intersection] if intersection.geom_type=='LineString' else [v for v in getattr(intersection,'geoms',[]) if v.geom_type=='LineString']
            ordered=[]
            for piece in pieces:
                if piece.is_empty:continue
                coords=list(piece.coords);start=line.project(inkex_point(coords[0]));end=line.project(inkex_point(coords[-1]))
                if start>end:coords.reverse();start=end
                ordered.append((start,coords))
            if not ordered:finish();continue
            for _,coords in sorted(ordered,key=lambda v:v[0]):
                if current and sum((current[-1][i]-coords[0][i])**2 for i in (0,1))>1e-12:finish()
                if not current:current.append(coords[0])
                current.extend(coords[1:])
            if sum((current[-1][i]-b[i])**2 for i in (0,1))>1e-12:finish()
    finish();return chunks

def prepare(raw,mode):
    """Vector bake, canonical engine clips, or release. Definitions stay local."""
    root=inkex.load_svg(io.BytesIO(raw)).getroot();info=features(root)
    if info['masks']:raise ValueError('Opacity masks need mask-to-geometry conversion before this operation.')
    if mode=='release':
        for e in root.iter():
            if visible(e):clear_clip(e)
        return ET.tostring(root),{'clippedPaths':info['clips'],'flattenedCurves':False}
    resolver=Clips(root);items=[]
    for e in list(root.iter()):
        if tag(e) not in SHAPES or not visible(e) or e.get('{'+INK+'}connection-start'):continue
        if 'inkstitch-' in properties(e).get('marker-start',''):continue
        region=resolver.effective(e)
        if region is not None:items.append((e,region))
    # Resolve every inherited clip before removing any ancestor reference.
    for e in root.iter():
        if visible(e):clear_clip(e)
    if mode=='needle':
        defs=root.find('{'+SVG+'}defs')
        if defs is None:defs=ET.SubElement(root,'{'+SVG+'}defs')
        for e,region in items:
            if region.is_empty:e.getparent().remove(e);continue
            id='native-clip-'+uuid.uuid4().hex;clip=ET.SubElement(defs,'{'+SVG+'}clipPath',id=id,clipPathUnits='userSpaceOnUse')
            ET.SubElement(clip,'{'+SVG+'}path',d=str(polygon_path(region).transform(-e.composed_transform())),**{'clip-rule':'evenodd'})
            e.set('clip-path','url(#'+id+')')
    else:
        for e,region in items:
            freeze_gradients(e,root)
            path=e.path.transform(e.composed_transform());style=e.specified_style();fill=str(style.get('fill','black'))!='none';stroke=str(style.get('stroke','none'))!='none';output=[]
            if stroke and (str(e.get('{'+STITCH+'}satin_column','')).lower() in ('true','1') or e.get('{'+STITCH+'}stroke_method') in ('zigzag_stitch','ripple_stitch','manual_stitch')):raise ValueError('Choose Editable needle points for clipped satin, zigzag, ripple or manual stitches. It keeps their generated stitch geometry.')
            if fill:
                result=polygon(path,str(style.get('fill-rule','nonzero'))).intersection(region)
                if not result.is_empty:output.append((polygon_path(result),'fill'))
            if stroke:
                result=clip_lines(path,region)
                if result:output.extend((part,'stroke') for part in result.break_apart())
            parent=e.getparent();index=parent.index(e)
            for i,(result,paint) in enumerate(output):
                node=copy.deepcopy(e);node.tag='{'+SVG+'}path'
                for key in ('x','y','width','height','rx','ry','cx','cy','r','points','{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}nodetypes'):node.attrib.pop(key,None)
                node.set('d',str(result.transform(-e.composed_transform())))
                if i:node.set('id',(e.get('id') or 'clipped')+'-'+uuid.uuid4().hex[:12])
                st=inkex.Style(node.get('style',''));st['stroke' if paint=='fill' else 'fill']='none'
                if paint=='fill':st['fill-rule']='evenodd'
                if paint=='stroke' and i<len(output)-1:
                    node.set('{'+STITCH+'}trim_after','true');node.attrib.pop('{'+STITCH+'}stop_after',None)
                node.set('style',str(st));parent.insert(index+i,node)
            if len(output)>1 and e.get('id'):
                # Exit/trim/stop belong to the final paint when a filled outline splits.
                for connector in root.xpath('//*[@inkscape:connection-start]'):
                    for end,other in [('end','start'),('start','end')]:
                        if connector.get('{'+INK+'}connection-'+end)!='#'+e.get('id'):continue
                        command=root.getElementById(connector.get('{'+INK+'}connection-'+other,'').lstrip('#'))
                        if command is not None:
                            name=command.get('{http://www.w3.org/1999/xlink}href',command.get('href',''))
                            if any(name=='#inkstitch_'+v or name.startswith('#inkstitch_'+v+'-') for v in ('ending_point','autoroute_end','trim','stop')):connector.set('{'+INK+'}connection-'+end,'#'+parent[index+len(output)-1].get('id'))
            parent.remove(e)
    # Remove connectors whose fully clipped artwork no longer exists.
    for connector in list(root.xpath('//*[@inkscape:connection-start]')):
        if any(root.getElementById(connector.get('{'+INK+'}connection-'+end,'').lstrip('#')) is None for end in ('start','end')):
            for end in ('start','end'):
                symbol=root.getElementById(connector.get('{'+INK+'}connection-'+end,'').lstrip('#'))
                if symbol is not None and tag(symbol)=='use':symbol.getparent().remove(symbol)
            connector.getparent().remove(connector)
    return ET.tostring(root),{'clippedPaths':len(items),'flattenedCurves':mode=='vector' and bool(items)}
