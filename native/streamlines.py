"""Editable multi-guide flow fields, sewn by the installed running-stitch engine."""
import copy
import functools
import json
import math
import numpy as np
from lxml import etree as ET
from shapely.geometry import LineString, Point
from shapely.prepared import prep
from shapely.ops import linemerge
from digitizing import inkex, path_contours
from applique import flattened

METHOD='streamline_fill'
WAVE_METHOD='wave_fill'
METHODS=(METHOD,WAVE_METHOD)
DEFAULT_GUIDES=[{'id':'flow-1','points':[[.12,.65],[.5,.35],[.88,.5]]}]
MAX_POINTS=180000


def active(layer):return layer.get('stitch')=='fill' and layer.get('fillMethod') in METHODS


def settings(value,s):
    if not isinstance(value,dict):raise ValueError('Enter flow-field fill settings.')
    result={'separation':s.number(value.get('separation',1.2),.4,8,'Line separation')}
    guides=value.get('guides',DEFAULT_GUIDES)
    if not isinstance(guides,list) or not 1<=len(guides)<=12:raise ValueError('Draw 1–12 flow guides.')
    result['guides']=[];ids=set()
    for guide in guides:
        if not isinstance(guide,dict):raise ValueError('Invalid flow guide.')
        key=guide.get('id');points=guide.get('points')
        if not isinstance(key,str) or not 1<=len(key)<=80 or key in ids:raise ValueError('Flow guides need unique identifiers.')
        ids.add(key)
        if not isinstance(points,list) or not 2<=len(points)<=32:raise ValueError('Each flow guide needs 2–32 points.')
        clean=[]
        for p in points:
            if not isinstance(p,list) or len(p)!=2:raise ValueError('Invalid flow-guide point.')
            clean.append([s.number(v,-.5,1.5,'Flow-guide position') for v in p])
        result['guides'].append({'id':key,'points':clean})
    return result


def guide_contour(guide,w,h):
    """Interpolating Catmull-Rom curve; identical controls in the touch editor."""
    pts=[(p[0]*w,p[1]*h) for p in guide['points']];nodes=[]
    for i,p in enumerate(pts):
        before=pts[max(0,i-1)];after=pts[min(len(pts)-1,i+1)]
        dx=(after[0]-before[0])/6;dy=(after[1]-before[1])/6
        nodes.append({'x':p[0],'y':p[1],'in':[p[0]-dx,p[1]-dy],'out':[p[0]+dx,p[1]+dy]})
    return {'closed':False,'nodes':nodes}


def d_path(points):return 'M'+' L'.join(f'{x:.5f},{y:.5f}' for x,y in points)


class FlowField:
    """Blend unoriented tangent tensors, so reversing a guide changes nothing.

    Nearest tangent per guide prevents a long/densely sampled guide from
    outweighing a shorter one. A fixed physical lattice bounds evaluation cost.
    """
    def __init__(self,guides,w,h):
        self.cell=.7;self.nx=max(2,math.ceil(w/self.cell)+1);self.ny=max(2,math.ceil(h/self.cell)+1)
        xs,ys=np.meshgrid(np.arange(self.nx)*self.cell,np.arange(self.ny)*self.cell)
        tx=np.zeros_like(xs);ty=np.zeros_like(xs);weight=np.zeros_like(xs)
        nearest=np.full_like(xs,np.inf);fallback_x=np.ones_like(xs);fallback_y=np.zeros_like(xs)
        for guide in guides:
            line=LineString(flattened(guide_contour(guide,w,h),.04))
            if line.length<.5:raise ValueError('A flow guide is too short. Move its points farther apart.')
            count=max(2,math.ceil(line.length/.65));best=np.full_like(xs,np.inf);bx=np.zeros_like(xs);by=np.zeros_like(xs)
            if count>1500:raise ValueError('Simplify the flow guide or keep it closer to the shape.')
            for i in range(count+1):
                d=line.length*i/count;p=line.interpolate(d);a=line.interpolate(max(0,d-.15));b=line.interpolate(min(line.length,d+.15))
                dx,dy=b.x-a.x,b.y-a.y;n=math.hypot(dx,dy)
                if n<1e-8:continue
                dx/=n;dy/=n;dist=(xs-p.x)**2+(ys-p.y)**2;use=dist<best
                best=np.where(use,dist,best);bx=np.where(use,dx*dx-dy*dy,bx);by=np.where(use,2*dx*dy,by)
            near=best<nearest;nearest=np.minimum(nearest,best)
            fallback_x=np.where(near,bx,fallback_x);fallback_y=np.where(near,by,fallback_y)
            influence=1/(best+4);tx+=bx*influence;ty+=by*influence;weight+=influence
        weak=np.hypot(tx,ty)<weight*.12
        self.tx=np.where(weak,fallback_x,tx);self.ty=np.where(weak,fallback_y,ty)

    def direction(self,p,previous=None):
        x=max(0,min(self.nx-1.00001,p[0]/self.cell));y=max(0,min(self.ny-1.00001,p[1]/self.cell));i=int(x);j=int(y);u=x-i;v=y-j
        def sample(a):return (a[j,i]*(1-u)+a[j,i+1]*u)*(1-v)+(a[j+1,i]*(1-u)+a[j+1,i+1]*u)*v
        angle=math.atan2(sample(self.ty),sample(self.tx))/2;d=(math.cos(angle),math.sin(angle))
        if previous and d[0]*previous[0]+d[1]*previous[1]<0:return (-d[0],-d[1])
        return d


class Occupancy:
    def __init__(self,distance):self.size=distance;self.rows={}
    def nearby(self,p,distance):
        x,y=math.floor(p[0]/self.size),math.floor(p[1]/self.size);n=math.ceil(distance/self.size)
        for i in range(x-n,x+n+1):
            for j in range(y-n,y+n+1):
                for a,b,index in self.rows.get((i,j),[]):
                    dx,dy=b[0]-a[0],b[1]-a[1];t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy or 1)))
                    if (p[0]-a[0]-dx*t)**2+(p[1]-a[1]-dy*t)**2<distance*distance:yield index
    def add(self,a,b,index=0):
        for i in range(math.floor(min(a[0],b[0])/self.size),math.floor(max(a[0],b[0])/self.size)+1):
            for j in range(math.floor(min(a[1],b[1])/self.size),math.floor(max(a[1],b[1])/self.size)+1):self.rows.setdefault((i,j),[]).append((a,b,index))


@functools.lru_cache(maxsize=16)
def _pattern(d,encoded,w,h):
    from components import path_polygon
    params=json.loads(encoded);shape=path_polygon(inkex.Path(d));shape=shape.buffer(-.035)
    if shape.is_empty or shape.area<.3:raise ValueError('This shape is too small for Streamlines.')
    if shape.area/params['separation']>30000:raise ValueError('This fill needs too many stitches. Increase streamline separation.')
    inside=prep(shape);field=FlowField(params['guides'],w,h);sep=params['separation'];step=min(.35,sep*.32)
    occupied=Occupancy(sep);rows=[];total=0;seeds=[]
    for guide in params['guides']:
        curve=LineString(flattened(guide_contour(guide,w,h),.04))
        for i in range(5):
            p=curve.interpolate(curve.length*(i+.5)/5);seeds.append((p.x,p.y))
    p=shape.representative_point();seeds.append((p.x,p.y))
    def trace(seed,sign):
        previous=field.direction(seed);previous=(previous[0]*sign,previous[1]*sign);points=[seed];own=Occupancy(sep);travel=0
        for index in range(16000):
            a=points[-1];v=field.direction(a,previous);mid=(a[0]+v[0]*step/2,a[1]+v[1]*step/2);v=field.direction(mid,v)
            b=(a[0]+v[0]*step,a[1]+v[1]*step)
            if not inside.covers(LineString([a,b])):
                # Clip the final short segment to the boundary, including holes.
                cut=shape.intersection(LineString([a,b]));pieces=[cut] if cut.geom_type=='LineString' else list(getattr(cut,'geoms',[]))
                for piece in pieces:
                    if piece.geom_type=='LineString' and piece.length>1e-6 and Point(a).distance(piece)<1e-6:
                        endpoint=tuple(piece.coords[-1]);
                        if math.dist(endpoint,a)>.01:points.append(endpoint)
                        break
                break
            if next(occupied.nearby(b,sep*.83),None) is not None:break
            if index>12 and any(old<index-10 for old in own.nearby(b,step*.7)):break
            own.add(a,b,index);points.append(b);previous=v;travel+=step
            if travel>1000:break
        return points
    def accept(seed):
        nonlocal total
        if not inside.contains(Point(seed)) or next(occupied.nearby(seed,sep*.95),None) is not None:return
        forward=trace(seed,1);backward=trace(seed,-1);points=list(reversed(backward[1:]))+forward
        if len(points)<3 or LineString(points).length<max(.6,sep*.7):return
        # Use only a small geometric simplification; never shortcut a hole.
        line=LineString(points);simple=line.simplify(.018)
        if inside.covers(simple):points=list(simple.coords)
        for a,b in zip(points,points[1:]):occupied.add(a,b)
        rows.append(points);total+=len(points)
        if total>MAX_POINTS or len(rows)>2500:raise ValueError('This fill is too complex. Increase separation or simplify the guides.')
        stride=max(1,round(sep*2/step))
        for i in range(0,len(forward),stride):
            p=forward[i];dx,dy=field.direction(p)
            seeds.extend([(p[0]-dy*sep,p[1]+dx*sep),(p[0]+dy*sep,p[1]-dx*sep)])
        for i in range(0,len(backward),stride):
            p=backward[i];dx,dy=field.direction(p)
            seeds.extend([(p[0]-dy*sep,p[1]+dx*sep),(p[0]+dy*sep,p[1]-dx*sep)])
    # Queue growth is bounded; a deterministic grid catches disconnected areas
    # and regions behind holes which the advancing fronts cannot reach.
    cursor=0
    while cursor<len(seeds):
        accept(seeds[cursor]);cursor+=1
        if cursor>160000:raise ValueError('The flow field is too complex. Increase separation.')
    minx,miny,maxx,maxy=shape.bounds
    for y in np.arange(miny+sep*.5,maxy,sep):
        for x in np.arange(minx+sep*.5,maxx,sep):accept((float(x),float(y)))
    if not rows:raise ValueError('No streamlines fit. Reduce separation or enlarge the shape.')
    return route_rows(rows,inside,sep,len(params['guides']))


def route_rows(rows,inside,sep,guides):
    # Route nearby rows back and forth. Only sew a connection if its complete
    # segment stays in the material; holes and disconnected islands stay jumps.
    pending=list(rows);ordered=[pending.pop(0)]
    while pending:
        end=ordered[-1][-1];index,reverse=min(((i,r) for i in range(len(pending)) for r in (False,True)),key=lambda ir:math.dist(end,pending[ir[0]][-1 if ir[1] else 0]))
        row=pending.pop(index)
        if reverse:row=list(reversed(row))
        if math.dist(end,row[0])<=sep*2.1 and inside.covers(LineString([end,row[0]])):ordered[-1].extend(row)
        else:ordered.append(row)
    stats={'lines':len(rows),'runs':len(ordered),'guides':guides,'pathLength':round(sum(LineString(row).length for row in ordered),2)}
    return ordered,stats


def cosine_transform(a,axis,inverse=False):
    """DCT-II and its inverse, using NumPy's existing FFT dependency."""
    a=np.moveaxis(a,axis,-1);n=a.shape[-1];phase=np.exp(1j*np.pi*np.arange(n)/(2*n))
    if inverse:
        spectrum=np.zeros((*a.shape[:-1],2*n),dtype=complex);spectrum[...,:n]=a*phase
        spectrum[...,n+1:]=np.conj(spectrum[...,1:n][...,::-1]);out=np.fft.ifft(spectrum,axis=-1).real[...,:n]
    else:out=(np.fft.fft(np.concatenate([a,a[...,::-1]],axis=-1),axis=-1)[...,:n]/phase).real
    return np.moveaxis(out,-1,axis)


def wave_phase(field,w,h,separation):
    """Coordinate neighboring waves with a least-squares phase potential.

    The phase gradient follows the normal to the shared tangent field. A
    Neumann Poisson solve on a rectangular physical lattice avoids periodic
    seams; contours of that phase are coherent, noncrossing wave bands.
    """
    cell=max(.32,min(.65,separation/2));nx=max(3,math.ceil(w/cell)+1);ny=max(3,math.ceil(h/cell)+1)
    xs=np.linspace(0,w,nx);ys=np.linspace(0,h,ny);dx=xs[1]-xs[0];dy=ys[1]-ys[0]
    tangent=np.empty((ny,nx,2))
    for j,y in enumerate(ys):
        for i,x in enumerate(xs):
            previous=tangent[j,i-1] if i else tangent[j-1,i] if j else None
            tangent[j,i]=field.direction((x,y),tuple(previous) if previous is not None else None)
    # Coordinate scales are carried into both the gradient and Laplacian.
    gx=-(tangent[:,:-1,1]+tangent[:,1:,1])/2/dx
    gy=(tangent[:-1,:,0]+tangent[1:,:,0])/2/dy
    rhs=np.zeros((ny,nx));rhs[:,:-1]-=gx;rhs[:,1:]+=gx;rhs[:-1,:]-=gy;rhs[1:,:]+=gy
    eigen=(2-2*np.cos(np.pi*np.arange(nx)/nx))[None,:]/dx**2+(2-2*np.cos(np.pi*np.arange(ny)/ny))[:,None]/dy**2
    eigen[0,0]=1;coeff=cosine_transform(cosine_transform(rhs,0),1)/eigen;coeff[0,0]=0
    phase=cosine_transform(cosine_transform(coeff,1,True),0,True)
    grad_y,grad_x=np.gradient(phase,dy,dx);magnitude=np.hypot(grad_x,grad_y);scale=float(np.median(magnitude))
    if scale<.08:raise ValueError('These guides turn too sharply for coordinated waves. Use Streamlines or straighten a guide.')
    phase/=scale
    return xs,ys,phase


def phase_contours(xs,ys,phase,separation):
    """March triangles with shared, rounded edge intersections for clean joins."""
    segments={}
    for j in range(len(ys)-1):
        for i in range(len(xs)-1):
            corners=[(xs[i],ys[j],phase[j,i]),(xs[i+1],ys[j],phase[j,i+1]),
                     (xs[i+1],ys[j+1],phase[j+1,i+1]),(xs[i],ys[j+1],phase[j+1,i])]
            for indices in ((0,1,2),(0,2,3)):
                tri=[corners[k] for k in indices];low=min(p[2] for p in tri);high=max(p[2] for p in tri)
                for level in range(math.ceil(low/separation),math.floor(high/separation)+1):
                    value=level*separation;cross=[]
                    for a,b in zip(tri,tri[1:]+tri[:1]):
                        if (a[2]<=value<b[2]) or (b[2]<=value<a[2]):
                            t=(value-a[2])/(b[2]-a[2]);cross.append((round(float(a[0]+t*(b[0]-a[0])),6),round(float(a[1]+t*(b[1]-a[1])),6)))
                    if len(cross)==2 and cross[0]!=cross[1]:segments.setdefault(level,[]).append(cross)
    for level in sorted(segments):
        merged=linemerge(segments[level]);pieces=[merged] if merged.geom_type=='LineString' else list(merged.geoms)
        yield from pieces


@functools.lru_cache(maxsize=16)
def _wave_pattern(d,encoded,w,h):
    from components import path_polygon
    params=json.loads(encoded);shape=path_polygon(inkex.Path(d)).buffer(-.035)
    if shape.is_empty or shape.area<.3:raise ValueError('This shape is too small for Wave Fill.')
    inside=prep(shape);sep=params['separation'];field=FlowField(params['guides'],w,h);rows=[];total=0
    xs,ys,phase=wave_phase(field,w,h,sep)
    for line in phase_contours(xs,ys,phase,sep):
        clipped=shape.intersection(line);pieces=[clipped] if clipped.geom_type=='LineString' else list(getattr(clipped,'geoms',[]))
        for piece in pieces:
            if piece.geom_type!='LineString' or piece.length<max(.5,sep*.4):continue
            simple=piece.simplify(.015)
            if inside.covers(simple):piece=simple
            row=list(piece.coords);rows.append(row);total+=len(row)
            if total>MAX_POINTS or len(rows)>2500:raise ValueError('This Wave Fill is too complex. Increase separation or simplify the guides.')
    if not rows:raise ValueError('No wave lines fit. Reduce separation or enlarge the shape.')
    return route_rows(rows,inside,sep,len(params['guides']))


def pattern(path,params,w,h,method=METHOD):
    if method not in METHODS:raise ValueError('Choose Streamlines or Wave Fill.')
    return (_wave_pattern if method==WAVE_METHOD else _pattern)(str(path),json.dumps(params,sort_keys=True,separators=(',',':')),w,h)


def cache_artwork(layer,s):
    params=settings(layer.get('streamlines',{}),s);rows,stats=pattern(inkex.Path(s.shape_path(layer).get('d')),params,layer['width'],layer['height'],layer.get('fillMethod',METHOD))
    layer['streamlinePreview']={'method':layer.get('fillMethod',METHOD),'shape':shape_key(layer),'settings':copy.deepcopy(params),'d':' '.join(d_path(row) for row in rows)}
    return stats


def shape_key(layer):return {k:layer.get(k) for k in ('type','width','height','radius','contours','points','closed')}


def decorate(content,layer,s):
    if not active(layer):return content
    if layer.get('type') not in ('path','rectangle','ellipse'):raise ValueError('Separate SVG paths before applying a flow-field fill.')
    params=settings(layer.get('streamlines',{}),s)
    # Background subtraction can produce several islands. Convert every fill
    # boundary while retaining an optional ordinary outline and its own color.
    targets=[e for e in content.iter('{'+s.SVG+'}path') if e.get('{'+s.STITCH+'}fill_method') in METHODS]
    if not targets:raise ValueError('A flow-field fill needs a closed native shape.')
    length=s.number(layer.get('stitchLength',2.5),.5,6,'Stitch length')
    for target in targets:
        rows,_=pattern(inkex.Path(target.get('d','')),params,layer['width'],layer['height'],layer['fillMethod'])
        group=ET.Element('{'+s.SVG+'}g')
        for row in rows:
            for i in range(0,len(row)-1,1799):
                node=ET.SubElement(group,'{'+s.SVG+'}path',d=d_path(row[i:i+1800]),style=f'fill:none;stroke:{s.color(layer["color"])};stroke-width:.15')
                node.set('{https://inkstudio.local/effects}flow-top','true')
                for key,value in {'stroke_method':'running_stitch','running_stitch_length_mm':length,'running_stitch_tolerance_mm':'.025','min_stitch_length_mm':'.05','ties':'3','trim_after':'False'}.items():node.set('{'+s.STITCH+'}'+key,str(value))
        if target is content:return group
        target.getparent().replace(target,group)
    return content


def prepare(data,s):
    from multisatin import layer_preview
    source=data.get('layer')
    if not isinstance(source,dict) or source.get('type') not in ('path','ellipse','rectangle'):raise ValueError('Select one closed native shape for a flow-field fill.')
    if source.get('locked') or source.get('visible',True) is False or source.get('role','artwork')!='artwork':raise ValueError('Show and unlock the selected shape first.')
    if source.get('link') or source.get('linkedHelper'):raise ValueError('Detach the linked shape before applying a flow-field fill.')
    if source.get('type')=='path' and (source.get('contours') and any(not c.get('closed') for c in source['contours']) or not source.get('contours') and not source.get('closed') and source.get('stitch')!='fill'):raise ValueError('A flow-field fill needs a closed shape. Close the path first.')
    method=data.get('method',source.get('fillMethod') if source.get('fillMethod') in METHODS else METHOD)
    if method not in METHODS:raise ValueError('Choose Streamlines or Wave Fill.')
    layer=copy.deepcopy(source);layer.update(stitch='fill',fillMethod=method,streamlines=settings(data.get('settings',{}),s),
        stitchLength=s.number(data.get('stitchLength',source.get('stitchLength',2.5)),.5,6,'Stitch length'),color=s.color(data.get('color',source.get('color','#203f38'))))
    stats=cache_artwork(layer,s);preview=layer_preview({'layers':[layer]},s)['preview']
    return {'layer':layer,'stats':stats,'preview':preview}
