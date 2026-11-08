"""Crosswise stem body and curved, longitudinal fibers in the flared foot."""
import math
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union
from botanical import cubic


def outer_only(shape):
    pieces=[shape] if shape.geom_type=='Polygon' else list(getattr(shape,'geoms',[]))
    return unary_union([Polygon(p.exterior) for p in pieces if p.geom_type=='Polygon' and p.area>.00001])


def regions(shape,left,right,flow):
    axis=[tuple((a+b)/2 for a,b in zip(l,r)) for l,r in zip(left,right)]
    transition=flow.get('transition',.5);spread=flow.get('spread',1.45)
    p=cubic(axis,transition);a=cubic(axis,transition-.001);b=cubic(axis,transition+.001)
    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);dx/=length;dy/=length;nx,ny=-dy,dx
    reach=max(shape.bounds[2]-shape.bounds[0],shape.bounds[3]-shape.bounds[1])*4+10
    A=(p[0]-nx*reach,p[1]-ny*reach);B=(p[0]+nx*reach,p[1]+ny*reach)
    lower=Polygon([A,B,(B[0]+dx*reach,B[1]+dy*reach),(A[0]+dx*reach,A[1]+dy*reach)])
    source=outer_only(shape)
    foot=outer_only(source.intersection(lower));body=outer_only(source.difference(lower))
    if body.is_empty or foot.is_empty:raise ValueError('Move the stem transition into the stem body.')
    repair=flow.get('repair',.55)
    if repair:
        repaired=body.buffer(repair).buffer(-repair)
        if transition>.6:
            rp=cubic(axis,.6);ra=cubic(axis,.599);rb=cubic(axis,.601)
            tx,ty=rb[0]-ra[0],rb[1]-ra[1];mag=math.hypot(tx,ty);tx/=mag;ty/=mag
            a=(rp[0]+ty*reach,rp[1]-tx*reach);b=(rp[0]-ty*reach,rp[1]+tx*reach)
            repaired=repaired.difference(Polygon([a,b,(b[0]+tx*reach,b[1]+ty*reach),(a[0]+tx*reach,a[1]+ty*reach)]))
        body=outer_only(body.union(repaired))
    # A small overlap covers the shared seam. Closing applies only to the body;
    # the intentional cleft between the foot's toes remains untouched.
    body=outer_only(body.buffer(.08,join_style=1))
    cut=source.intersection(LineString([A,B]));segments=[cut] if cut.geom_type=='LineString' else list(getattr(cut,'geoms',[]))
    cut=max((s for s in segments if s.geom_type=='LineString'),key=lambda s:s.length)
    start=cut.interpolate(.5,normalized=True);shift=(start.x-p[0],start.y-p[1]);width=cut.length
    count=max(7,min(36,math.ceil(width/.20)))
    paths=[];fiber_lines=[]
    for i in range(count):
        q=cut.interpolate((i+.5)/count,normalized=True)
        offset=(q.x-start.x)*nx+(q.y-start.y)*ny;points=[]
        for j in range(15):
            v=j/14;t=transition+(1-transition)*v
            center=cubic(axis,t);before=cubic(axis,max(0,t-.001));after=cubic(axis,min(1,t+.001))
            tx,ty=after[0]-before[0],after[1]-before[1];mag=math.hypot(tx,ty) or 1
            side=offset*(1+(spread-1)*v)
            points.append((center[0]+shift[0]*(1-v)-ty/mag*side,center[1]+shift[1]*(1-v)+tx/mag*side))
        tx,ty=axis[3][0]-axis[2][0],axis[3][1]-axis[2][1];mag=math.hypot(tx,ty) or 1
        points.append((points[-1][0]+tx/mag*reach,points[-1][1]+ty/mag*reach))
        line=foot.buffer(.015).intersection(LineString(points))
        pieces=[line] if line.geom_type=='LineString' else list(getattr(line,'geoms',[]))
        connected=[piece for piece in pieces if piece.geom_type=='LineString' and piece.distance(Point(q))<.03]
        if not connected:continue
        line=min(connected,key=lambda piece:piece.distance(Point(q)))
        coords=list(line.coords)
        if math.dist(coords[-1],q.coords[0])<math.dist(coords[0],q.coords[0]):coords.reverse()
        if len(coords)<2 or line.length<.08:continue
        fiber_lines.append(LineString(coords))
        paths.append(('M' if not paths else 'L')+f'{coords[0][0]},{coords[0][1]}')
        paths.extend(f'L{x},{y}' for x,y in coords[1:])
        paths.extend(f'L{x},{y}' for x,y in reversed(coords[:-1]))
    if not paths:raise ValueError('The foot needs more room for its fiber flow. Move the stem transition upward.')
    combined=outer_only(body.union(foot))
    if source.difference(combined.buffer(.001)).area>=.0001:raise ValueError('The stem stitch regions left a gap. Adjust the transition.')
    if any(len(p.interiors) for p in ([combined] if combined.geom_type=='Polygon' else combined.geoms)):raise ValueError('An unintended hole formed in the stem. Adjust its outline or transition.')
    body_tangent=(axis[1][0]-axis[0][0],axis[1][1]-axis[0][1])
    foot_tangent=(axis[3][0]-p[0],axis[3][1]-p[1])
    return dict(body=body,foot=foot,fibers=' '.join(paths),fiberLines=fiber_lines,source=source,combined=combined,
        bodyAngle=90-math.degrees(math.atan2(body_tangent[1],body_tangent[0])),
        footAngle=-math.degrees(math.atan2(foot_tangent[1],foot_tangent[0])))


def layers(shape,left,right,params):
    from components import part,polygon_path
    result=regions(shape,left,right,params.get('stemFlow',{}));cream=params['creamColor']
    if params.get('sewingProfile')=='simple':
        if params['width']*params.get('sewingScale',1)<8:
            body=part(str(polygon_path(result['combined'])),'Mushroom · simple solid stem',cream)
            body.update(spacing=.4,angle=result['bodyAngle'],stitchLength=3,underlay=False,paintStage=3,
                smallFillFallback=True,isolateFillIslands=False,trimAfter=True,advanced={'min_stitch_length_mm':.3})
            return [('stem',body)]
        foot=part(str(polygon_path(result['foot'])),'Mushroom · lengthwise foot',cream)
        foot.update(spacing=.4,angle=result['footAngle'],stitchLength=4,underlay=False,paintStage=2,
            smallFillFallback=True,isolateFillIslands=False,trimAfter=False,advanced={'min_stitch_length_mm':.3})
        body=part(str(polygon_path(result['body'])),'Mushroom · crosswise body',cream)
        body.update(spacing=.4,angle=result['bodyAngle'],stitchLength=4,underlay=False,paintStage=3,
            smallFillFallback=True,isolateFillIslands=False,trimAfter=True,advanced={'min_stitch_length_mm':.3})
        return [('stem-foot-ground',foot),('stem',body)]
    foot=part(str(polygon_path(result['foot'])),'Mushroom · longitudinal foot ground',cream)
    foot.update(spacing=.28,angle=result['footAngle'],stitchLength=5.5,underlay=False,paintStage=2,smallFillFallback=True)
    fibers=part(result['fibers'],'Mushroom · flowing foot fibers',cream,'running')
    fibers.update(stitchLength=3.5,trimAfter=False,paintStage=2.1)
    body=part(str(polygon_path(result['body'])),'Mushroom · crosswise stem body',cream)
    body.update(spacing=.25,angle=result['bodyAngle'],stitchLength=5.5,underlay=False,paintStage=3,smallFillFallback=True)
    return [('stem-foot-ground',foot),('stem-foot-fibers',fibers),('stem',body)]
