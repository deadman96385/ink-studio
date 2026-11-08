"""Partition filled glyph outlines into editable satin rails and direction rungs.

This prepares geometry only. Ink/Stitch remains responsible for all stitches,
underlays, compensation, routing and machine-file generation.
"""
import math
from shapely import constrained_delaunay_triangles,segmentize
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import polygonize,unary_union
from fontTools.pens.basePen import BasePen


class OutlinePen(BasePen):
    def __init__(self,glyphs,scale):
        super().__init__(glyphs);self.scale=scale;self.rings=[];self.current=[];self.count=0

    def point(self,p):return (p[0]*self.scale,-p[1]*self.scale)
    def add(self,p):
        self.count+=1
        if self.count>12000:raise ValueError('A glyph has too much outline detail. Choose a simpler font.')
        if not self.current or math.dist(p,self.current[-1])>1e-8:self.current.append(p)

    def _moveTo(self,p):self.finish();self.add(self.point(p))
    def _lineTo(self,p):self.add(self.point(p))
    def _curveToOne(self,a,b,c):self.cubic(self.current[-1],self.point(a),self.point(b),self.point(c))
    def _qCurveToOne(self,b,c):
        a=self.current[-1];b=self.point(b);c=self.point(c)
        self.cubic(a,tuple(a[i]+2/3*(b[i]-a[i]) for i in (0,1)),tuple(c[i]+2/3*(b[i]-c[i]) for i in (0,1)),c)

    def cubic(self,a,b,c,d,depth=0):
        line=LineString([a,d])
        if depth>=16 or max(line.distance(Point(p)) for p in (b,c))<=.012:
            self.add(d);return
        mid=lambda p,q:tuple((p[i]+q[i])/2 for i in (0,1))
        ab=mid(a,b);bc=mid(b,c);cd=mid(c,d);abc=mid(ab,bc);bcd=mid(bc,cd);center=mid(abc,bcd)
        self.cubic(a,ab,abc,center,depth+1);self.cubic(center,bcd,cd,d,depth+1)

    def finish(self):
        if len(self.current)>2:
            if self.current[0]!=self.current[-1]:self.current.append(self.current[0])
            self.rings.append(self.current)
        self.current=[]

    def _closePath(self):self.finish()
    def _endPath(self):self.finish()

    def shape(self):
        self.finish()
        if not self.rings:return Polygon()
        # TrueType/CFF use nonzero winding, including overlapping components.
        faces=list(polygonize(unary_union([LineString(r) for r in self.rings])))
        def winding(p):
            x,y=p.x,p.y;value=0
            for ring in self.rings:
                for a,b in zip(ring,ring[1:]):
                    cross=(b[0]-a[0])*(y-a[1])-(x-a[0])*(b[1]-a[1])
                    if a[1]<=y<b[1] and cross>0:value+=1
                    elif b[1]<=y<a[1] and cross<0:value-=1
            return value
        return unary_union([p for p in faces if winding(p.representative_point())])


def _clean(points):
    result=[]
    for p in points:
        if not result or math.dist(p,result[-1])>1e-7:result.append(p)
    return result


def _rungs(pairs):
    centers=[tuple((a[i]+b[i])/2 for i in (0,1)) for a,b in pairs]
    distances=[0]
    for a,b in zip(centers,centers[1:]):distances.append(distances[-1]+math.dist(a,b))
    if distances[-1]<1e-5:raise ValueError('A glyph contains an outline too small to form a satin column.')
    count=max(3,min(180,math.ceil(distances[-1]/.9)));out=[];index=1
    for n in range(1,count+1):
        target=distances[-1]*n/(count+1)
        while index<len(distances)-1 and distances[index]<target:index+=1
        t=(target-distances[index-1])/max(1e-12,distances[index]-distances[index-1])
        a,b=[tuple(pairs[index-1][side][i]*(1-t)+pairs[index][side][i]*t for i in (0,1)) for side in (0,1)]
        if math.dist(a,b)<1e-6:continue
        center=tuple((a[i]+b[i])/2 for i in (0,1))
        out.append([tuple(center[i]+(a[i]-center[i])*1.04 for i in (0,1)),tuple(center[i]+(b[i]-center[i])*1.04 for i in (0,1))])
    if len(out)<3:raise ValueError('A glyph contains a degenerate satin column. Choose a simpler font or larger height.')
    return out


def satin_columns(shape):
    polygons=[shape] if shape.geom_type=='Polygon' else list(shape.geoms)
    columns=[]
    for polygon in polygons:
        if polygon.area<.0001:raise ValueError('A font detail is too small to convert. Increase capital height or choose a simpler font.')
        # Boundary sampling makes cross-sections follow the stroke, rather than
        # drawing a long diagonal across an otherwise rectangular letter stem.
        polygon=segmentize(polygon.simplify(.006,preserve_topology=True),.55)
        triangles=list(constrained_delaunay_triangles(polygon).geoms)
        if not triangles or len(triangles)>10000:raise ValueError('The font outline is too complex to convert automatically.')
        vertices=[];owners={};neighbors=[{} for _ in triangles]
        for i,triangle in enumerate(triangles):
            points=[tuple(round(v,8) for v in p) for p in list(triangle.exterior.coords)[:-1]];vertices.append(points)
            for a,b in zip(points,points[1:]+points[:1]):owners.setdefault(tuple(sorted((a,b))),[]).append(i)
        for edge,ids in owners.items():
            if len(ids)==2:
                a,b=ids;neighbors[a][b]=edge;neighbors[b][a]=edge
        visited=set()
        def edge_key(a,b):return tuple(sorted((a,b)))
        def cap(index,edge):
            return tuple(triangles[index].centroid.coords[0]) if len(neighbors[index])==3 else next(p for p in vertices[index] if p not in edge)
        def column(edges,start=None,end=None):
            pairs=[list(edges[0])]
            for edge in edges[1:]:
                a,b=pairs[-1]
                if a in edge:pairs.append([a,next(p for p in edge if p!=a)])
                elif b in edge:pairs.append([next(p for p in edge if p!=b),b])
                else:raise ValueError('The font outline could not be partitioned into satin strokes.')
            if start is not None:pairs.insert(0,[start,start])
            if end is not None:pairs.append([end,end])
            rails=[_clean([p[side] for p in pairs]) for side in (0,1)]
            if any(len(r)<2 for r in rails):raise ValueError('A font stroke has no usable rail.')
            columns.append({'rails':rails,'rungs':_rungs(pairs),'width':max(math.dist(a,b) for a,b in pairs)})
        for i,adj in enumerate(neighbors):
            if len(adj)==0:
                points=vertices[i];a,b=max([(a,b) for a,b in zip(points,points[1:]+points[:1])],key=lambda e:math.dist(*e));tip=next(p for p in points if p not in (a,b))
                columns.append({'rails':[[a,tip],[b,tip]],'rungs':_rungs([[a,b],[tip,tip]]),'width':math.dist(a,b)})
            elif len(adj)!=2:
                for nxt in adj:
                    if edge_key(i,nxt) in visited:continue
                    chain=[i,nxt];visited.add(edge_key(i,nxt))
                    while len(neighbors[chain[-1]])==2:
                        nxt=next(n for n in neighbors[chain[-1]] if n!=chain[-2]);visited.add(edge_key(chain[-1],nxt));chain.append(nxt)
                    edges=[neighbors[a][b] for a,b in zip(chain,chain[1:])]
                    column(edges,cap(chain[0],edges[0]),cap(chain[-1],edges[-1]))
        # An O-shaped stroke has no tips or junctions: cut its rail loops at a
        # common cross-section, keeping explicit open SVG paths (no Z command).
        for i,adj in enumerate(neighbors):
            for nxt in adj:
                if edge_key(i,nxt) in visited:continue
                chain=[i,nxt];visited.add(edge_key(i,nxt))
                while chain[-1]!=i:
                    nxt=next(n for n in neighbors[chain[-1]] if n!=chain[-2]);visited.add(edge_key(chain[-1],nxt));chain.append(nxt)
                edges=[neighbors[a][b] for a,b in zip(chain,chain[1:])];column([edges[-1],*edges])
        if len(columns)>800:raise ValueError('These letters need too many satin columns. Use fewer characters or a simpler font.')
    return columns


def path_data(points,close=False):
    return 'M'+' L'.join(f'{x:.7f},{y:.7f}' for x,y in points)+(' Z' if close else '')


def polygon_data(shape):
    polygons=[shape] if shape.geom_type=='Polygon' else list(shape.geoms)
    return ' '.join(path_data(list(r.coords),True) for p in polygons for r in [p.exterior,*p.interiors])
