"""Editable faux-merrow border recipes, encoded by Ink/Stitch as manual paths."""
import copy
import math
import uuid
from lxml import etree as ET
from shapely.geometry import LineString,LinearRing,Point
from digitizing import inkex,path_contours,from_path,contour_d
from applique import flattened

DEFAULTS={'width':3,'spacing':.4,'fanLength':2.4,'spread':.3,'bindingDepth':.45,'side':'inside','underlay':'center'}
MAX_POINTS=40000


def settings(value,s):
    if not isinstance(value,dict):raise ValueError('Enter faux merrow border settings.')
    out={}
    for key,low,high,label in [('width',.8,6,'Border width'),('spacing',.2,1.2,'Fan stitch spacing'),
        ('fanLength',1,8,'Fan length'),('spread',.1,.8,'Fan spread'),('bindingDepth',.1,2,'Binding depth')]:
        out[key]=s.number(value.get(key,DEFAULTS[key]),low,high,label)
    for key,choices in [('side',('inside','outside')),('underlay',('none','center','center-contour','full'))]:
        out[key]=value.get(key,DEFAULTS[key])
        if out[key] not in choices:raise ValueError('Choose a supported faux merrow '+key+'.')
    if out['bindingDepth']>out['width']*.8:raise ValueError('Binding depth must be at most 80% of the border width.')
    return out


def active(layer):return isinstance(layer.get('merrow'),dict) and layer.get('stitch')=='original'


def d_path(points,closed=False):return 'M'+' L'.join(f'{x:.6f},{y:.6f}' for x,y in points)+(' Z' if closed else '')


def pattern(path,params):
    """Build fan and binding geometry in local, physical millimeter coordinates.

    A fan opens along one rail while its roots occupy a shorter span on the
    opposite rail. A short in-and-out binding stitch finishes each fan.
    Offset distance is bounded at half the width, including sharp corners.
    """
    from components import path_polygon
    contours=path_contours(path)
    if not contours or any(not c['closed'] for c in contours):raise ValueError('Faux merrow borders need closed outlines. Close the path first.')
    shape=path_polygon(path)
    if shape.is_empty:raise ValueError('The outline has no enclosed area.')
    stages=[];total=0;fans=0
    for contour in contours:
        points=flattened(contour,.015);line=LineString(points);length=line.length
        if not line.is_simple:raise ValueError('The border outline crosses itself. Simplify or repair it before adding faux merrow.')
        if length<params['width']*4:raise ValueError('A border or hole is too small for this width. Enlarge it, remove the small hole or reduce border width.')
        epsilon=min(.1,length/400)
        def frame(distance):
            distance%=length
            p=line.interpolate(distance);a=line.interpolate((distance-epsilon)%length);b=line.interpolate((distance+epsilon)%length)
            dx,dy=b.x-a.x,b.y-a.y;n=math.hypot(dx,dy)
            if n<1e-8:raise ValueError('The outline doubles back on itself. Smooth that corner before adding faux merrow.')
            return (p.x,p.y),(-dy/n,dx/n)
        probe,normal=frame(length*.371)
        material=1 if LinearRing(points).is_ccw else -1
        for offset in (.05,.02,.1,.005):
            left=shape.covers(Point(probe[0]+normal[0]*offset,probe[1]+normal[1]*offset))
            right=shape.covers(Point(probe[0]-normal[0]*offset,probe[1]-normal[1]*offset))
            if left!=right:
                material=1 if left else -1;break
        gathered=material*(1 if params['side']=='inside' else -1)
        def at(distance,side):
            p,n=frame(distance);return (p[0]+n[0]*side*params['width']/2,p[1]+n[1]*side*params['width']/2)
        repeats=max(3,int(math.floor(length/params['fanLength']+.5)));fan_length=length/repeats
        teeth=max(3,int(math.ceil(fan_length/params['spacing'])))
        if repeats*(2*teeth+6)+total>MAX_POINTS:raise ValueError('This border needs too many stitches. Increase fan stitch spacing or simplify the outline.')
        fan=[]
        for index in range(repeats):
            start=index*fan_length;center=start+fan_length/2
            for tooth in range(teeth+1):
                t=tooth/teeth
                fan.append(at(center+(t-.5)*fan_length*params['spread'],gathered))
                fan.append(at(start+t*fan_length,-gathered))
            root_distance=center+fan_length*params['spread']/2;root=at(root_distance,gathered)
            p,n=frame(root_distance)
            binding=(root[0]-n[0]*gathered*params['bindingDepth'],root[1]-n[1]*gathered*params['bindingDepth'])
            fan.extend([root,binding,root])
            gap=fan_length*(1-params['spread']);walk=max(1,math.ceil(gap/2.5))
            fan.extend(at(root_distance+gap*i/walk,gathered) for i in range(1,walk+1))
        fan.append(fan[0]);fans+=repeats
        if params['underlay']!='none':stages.append({'kind':'run','points':points,'name':'Center underlay'})
        if params['underlay'] in ('center-contour','full'):
            count=max(12,math.ceil(length/.7))
            for side in (-.65,.65):
                rail=[at(length*i/count,side) for i in range(count)];rail.append(rail[0]);stages.append({'kind':'run','points':rail,'name':'Contour underlay'})
        if params['underlay']=='full':
            count=max(12,math.ceil(length/1.4));zig=[]
            for i in range(count):zig.extend([at(length*i/count,-.65),at(length*(i+.5)/count,.65)])
            zig.append(zig[0]);stages.append({'kind':'manual','points':zig,'name':'Zigzag underlay'})
        stages.append({'kind':'manual','points':fan,'name':'Faux merrow fans'})
        total+=len(fan)
    count=sum(len(row['points']) for row in stages)
    if count>MAX_POINTS:raise ValueError('This border needs too many stitches. Increase fan stitch spacing or simplify the outline.')
    return stages,{'fans':fans,'needlePoints':count,'outlines':len(contours)}


def configure(layer,params):
    layer.update(stitch='original',originalFill=False,originalStroke=True,originalWidth=params['width'],
        originalFillRule='evenodd',originalParams={'stroke_method':'manual_stitch','min_stitch_length_mm':'0.05','max_stitch_length_mm':'12'},merrow=copy.deepcopy(params))
    return layer


def cache_artwork(layer,s):
    params=settings(layer['merrow'],s);path=inkex.Path(contour_d(layer['contours'],layer['width'],layer['height']))
    stages,stats=pattern(path,params)
    layer['merrowPreview']={'contours':copy.deepcopy(layer['contours']),'width':layer['width'],'height':layer['height'],
        'settings':copy.deepcopy(layer['merrow']),'d':' '.join(d_path(stage['points']) for stage in stages if stage['kind']=='manual')}
    return stats


def decorate(content,layer,s):
    if not active(layer):return content
    if layer.get('type') not in ('path','ellipse','rectangle'):raise ValueError('Use a native closed outline for faux merrow.')
    params=settings(layer['merrow'],s);stages,_=pattern(inkex.Path(content.get('d','')),params)
    group=ET.Element('{'+s.SVG+'}g')
    # Parameters apply to every generated path; layer-level commands remain at
    # the outside of this group, as for other multi-path native objects.
    output=[]
    for stage in stages:
        points=stage['points'];chunks=[points] if stage['kind']=='run' else [points[i:i+1800] for i in range(0,len(points),1799) if len(points[i:i+1800])>1]
        for chunk in chunks:
            node=ET.SubElement(group,'{'+s.SVG+'}path',d=d_path(chunk),style=f'fill:none;stroke:{s.color(layer["color"])};stroke-width:.03')
            node.set('{'+s.INK+'}label',stage['name'])
            values={'stroke_method':'manual_stitch' if stage['kind']=='manual' else 'running_stitch',
                'running_stitch_length_mm':'2.5','running_stitch_tolerance_mm':'.05','min_stitch_length_mm':'.05',
                'max_stitch_length_mm':'12','ties':'3','trim_after':'False','random_seed':'faux-merrow'}
            for key,value in values.items():node.set('{'+s.STITCH+'}'+key,value)
            output.append(node)
    output[0].set('{'+s.STITCH+'}ties','1' if len(output)>1 else '0')
    if len(output)>1:output[-1].set('{'+s.STITCH+'}ties','2')
    return group


def from_outline(path,params,color,name='Faux merrow border'):
    return configure(from_path(path,{'name':name,'color':color,'trimAfter':True,'underlay':False}),params)


def prepare(data,s):
    from components import world_path
    from multisatin import layer_preview
    source=data.get('layer')
    if not isinstance(source,dict) or source.get('type') not in ('path','ellipse','rectangle'):raise ValueError('Select one closed shape or border.')
    if source.get('locked') or source.get('visible',True) is False or source.get('role','artwork')!='artwork':raise ValueError('Show and unlock the selected outline first.')
    if source.get('link') or source.get('linkedHelper'):raise ValueError('Detach the linked outline before adding faux merrow.')
    if source.get('type')=='path' and (source.get('contours') and any(not c.get('closed') for c in source['contours']) or not source.get('contours') and not source.get('closed') and source.get('stitch')!='fill'):
        raise ValueError('Faux merrow borders need closed outlines. Close the path first.')
    params=settings(data.get('settings',{}),s);color=s.color(data.get('color',source.get('color','#203f38')))
    if isinstance(source.get('merrow'),dict):
        layer=configure(copy.deepcopy(source),params);layer['color']=color
    else:
        layer=from_outline(world_path(source,s),params,color,(source.get('name','Shape')+' · faux merrow')[:120]);layer['merrowSourceId']=source['id']
    stats=cache_artwork(layer,s);preview=layer_preview({'layers':[layer]},s)['preview']
    return {'layer':layer,'preview':preview,'stats':stats}
