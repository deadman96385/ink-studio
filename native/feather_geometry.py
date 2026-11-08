"""Seeded displacement of engine-tagged top-stitch endpoints, in millimeters."""
import copy,hashlib,math
from shapely import wkt
from shapely.geometry import LineString,Point
from shapely.ops import unary_union


def unit(dx,dy):
    length=math.hypot(dx,dy)
    return (dx/length,dy/length) if length>1e-8 else None


def ray_points(geometry):
    if geometry.geom_type=='Point':return [(geometry.x,geometry.y)]
    if geometry.geom_type in ('LineString','LinearRing'):return list(geometry.coords)
    return [p for g in getattr(geometry,'geoms',[]) for p in ray_points(g)]


def apply(groups,config):
    """Keep interiors, underlay, travel points and group commands untouched."""
    rows=copy.deepcopy(groups);settings=config['settings'];shape=wkt.loads(config['mask'])
    pieces=[shape] if shape.geom_type=='Polygon' else list(shape.geoms)
    outside=unary_union([p.exterior for p in pieces]);holes=unary_union([r for p in pieces for r in p.interiors])
    boundary=shape.boundary;reach=max(shape.bounds[2]-shape.bounds[0],shape.bounds[3]-shape.bounds[1])*3+10
    axis=config.get('axis',[1,0]);rails=[LineString(r) for r in config.get('rails',[])]
    moved=0;hole_skips=0;max_extension=0;motion=[]
    for gi,row in enumerate(rows):
        points=row['points'];seen={}
        for i,p in enumerate(points):
            tags=set(p[2]);underlay=any('underlay' in t or t=='satin_center_walk' for t in tags)
            if underlay or 'travel' in tags:continue
            original=groups[gi]['points'][i];pos=(original[0],original[1]);pt=Point(pos)
            # Some installed-engine satin caches omit edge tags. Recognize
            # those rail points geometrically, excluding underlay transitions.
            near_rail=len(rails)==2 and min(r.distance(pt) for r in rails)<.15+config.get('compensation',0)
            adjacent_underlay=any(any('underlay' in t for t in groups[gi]['points'][j][2]) for j in (i-1,i+1) if 0<=j<len(points))
            satin='satin_column_edge' in tags or near_rail and not adjacent_underlay
            start='fill_row_start' in tags;end='fill_row_end' in tags
            flowing='native_flow_top' in tags
            if not (satin or start or end or flowing):continue
            neighbors=[]
            for sign in ((1,) if start else (-1,) if end else (-1,1)):
                for offset in range(1,9):
                    j=i+sign*offset
                    if not 0<=j<len(points):break
                    q=groups[gi]['points'][j]
                    if math.dist(pos,q[:2])>.025:
                        if flowing and (boundary.distance(pt)>.12 or boundary.distance(Point(q[:2]))<.13):break
                        direction=unit(pos[0]-q[0],pos[1]-q[1])
                        if direction:neighbors.append(direction)
                        break
            if not neighbors:continue
            direction=unit(sum(n[0] for n in neighbors),sum(n[1] for n in neighbors))
            if not direction:direction=neighbors[0]
            dx,dy=direction
            # Find the material exit along the row, including a row shortened
            # by Skip last stitch. Already compensated endpoints stay outside.
            crossings=ray_points(boundary.intersection(LineString([pos,(pos[0]+dx*reach,pos[1]+dy*reach)])))
            distances=sorted((q[0]-pos[0])*dx+(q[1]-pos[1])*dy for q in crossings if (q[0]-pos[0])*dx+(q[1]-pos[1])*dy>=-1e-6)
            inside=shape.covers(pt);distance=max(0,distances[0]) if distances and inside else 0
            if not inside and boundary.distance(pt)>settings['raggedness']+1.5:continue
            edge=(pos[0]+dx*distance,pos[1]+dy*distance);ep=Point(edge)
            hole=not holes.is_empty and holes.distance(ep)<outside.distance(ep)
            if hole and not settings['includeHoles']:hole_skips+=1;continue
            if satin and len(rails)==2:side=-1 if rails[0].distance(ep)<=rails[1].distance(ep) else 1
            else:side=-1 if dx*axis[0]+dy*axis[1]<0 else 1
            balance=settings['balance']/100;weight=1-max(0,balance) if side<0 else 1+min(0,balance)
            if weight<=0:continue
            key=(round(pos[0],7),round(pos[1],7),'start' if start else 'end' if end else 'edge')
            if key in seen:p[0],p[1]=seen[key];continue
            digest=hashlib.sha256((settings['seed']+f':{gi}:{i}').encode()).digest()
            random=int.from_bytes(digest[:8],'big')/(2**64-1)
            extension=settings['raggedness']*weight*random**.8
            # Do not bridge a narrow hole or a gap to another piece.
            opposite=[d-distance for d in distances if d-distance>.015]
            if opposite:extension=min(extension,min(opposite)*.45)
            if extension<.005:continue
            p[0]=edge[0]+dx*extension;p[1]=edge[1]+dy*extension;seen[key]=(p[0],p[1]);moved+=1
            max_extension=max(max_extension,extension);motion.append([pos[0],pos[1],p[0],p[1]])
    return rows,{'edges':moved,'holeEdgesPreserved':hole_skips,'maxExtension':round(max_extension,4),'motion':motion}
