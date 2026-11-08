"""Portable cap outlines and individually editable, isolated spot contours."""
import copy
import math
import re
from digitizing import inkex,contour_d,path_contours


def validate(raw,s):
    def xy(p,label):
        if not isinstance(p,list) or len(p)!=2:raise ValueError(label+' needs X and Y.')
        return [s.number(v,-.5,1.5,label) for v in p]
    def contours(value,label):
        if not isinstance(value,list) or not 1<=len(value)<=3:raise ValueError(label+' needs 1–3 closed contours.')
        result=[]
        for c in value:
            ns=c.get('nodes') if isinstance(c,dict) else None
            if not isinstance(c,dict) or not c.get('closed') or not isinstance(ns,list) or not 2<=len(ns)<=200:raise ValueError(label+' needs 2–200 nodes per closed contour.')
            result.append(dict(closed=True,nodes=[dict(x=s.number(n.get('x'),-.5,1.5,label+' X'),
                y=s.number(n.get('y'),-.5,1.5,label+' Y'),**{key:xy(n.get(key),label+' handle') for key in ('in','out')}) for n in ns]))
        return result
    def rail(value,label):
        if not isinstance(value,list) or len(value)!=4:raise ValueError(label+' needs four cubic points.')
        return [xy(p,label) for p in value]
    result={}
    if 'capContours' in raw:result['capContours']=contours(raw['capContours'],'Cap outline')
    if 'gillContours' in raw:result['gillContours']=contours(raw['gillContours'],'Gill bed outline')
    if 'stemContours' in raw:result['stemContours']=contours(raw['stemContours'],'Stem outline')
    if 'stemFlow' in raw:
        flow=raw['stemFlow']
        if not isinstance(flow,dict):raise ValueError('Invalid stem stitch flow.')
        result['stemFlow']=dict(transition=s.number(flow.get('transition',.5),.2,.85,'Stem transition'),
            spread=s.number(flow.get('spread',1.45),.5,2.5,'Foot fiber spread'),repair=s.number(flow.get('repair',.55),0,1,'Stem edge repair'))
    if 'capPivot' in raw:result['capPivot']=xy(raw['capPivot'],'Cap pivot')
    if 'gillMap' in raw:
        value=raw['gillMap']
        if not isinstance(value,dict):raise ValueError('Invalid gill layout.')
        result['gillMap']=dict(upper=rail(value.get('upper'),'Upper gill edge'),lower=rail(value.get('lower'),'Lower gill edge'),hub=xy(value.get('hub'),'Gill fan centre'))
    if 'stemRails' in raw:
        if not isinstance(raw['stemRails'],list) or len(raw['stemRails'])!=2:raise ValueError('The stem needs two satin rails.')
        result['stemRails']=[rail(r,'Stem rail') for r in raw['stemRails']]
    if 'spotDetails' in raw:
        details=raw['spotDetails']
        if not isinstance(details,list) or len(details)>12:raise ValueError('Use at most 12 individual spots.')
        result['spotDetails']=[];ids=set()
        for i,spot in enumerate(details):
            if not isinstance(spot,dict):raise ValueError('Invalid spot layout.')
            key=spot.get('id',str(i+1))
            if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,30}',key) or key in ids:raise ValueError('Spots need unique short identifiers.')
            ids.add(key)
            result['spotDetails'].append(dict(id=key,name=str(spot.get('name',f'Spot {i+1}'))[:60],
                contours=contours(spot.get('contours'),'Spot outline'),rotation=s.number(spot.get('rotation',0),-180,180,'Spot rotation')))
        result['spots']=len(details)
    return result


def cap_path(p):
    w,h=p['width'],p['height'];y=h*p['dome']
    if p.get('capContours'):return inkex.Path(contour_d(p['capContours'],w,h))
    return inkex.Path(f'M0,{y} C{w*.025},{y*.52} {w*.25},{-y*.045} {w*.48},0 '
        f'C{w*.72},{-y*.025} {w*.97},{y*.57} {w},{y} '
        f'C{w*.76},{y-h*.18} {w*.22},{y-h*.18} 0,{y} Z')


def normalized(path,w,h):return path_contours(path.transform(inkex.Transform(scale=(1/w,1/h))))


def spot_details(p):
    if 'spotDetails' in p:return copy.deepcopy(p['spotDetails'])
    from components import ellipse,path_polygon
    w,h=p['width'],p['height'];y=h*p['dome'];seed=p.get('spotSeed',0)
    locations=p.get('spotMap') or [[.38,.16,.068],[.65,.25,.088],[.24,.50,.066],[.52,.48,.045],
        [.82,.65,.06],[.12,.72,.035],[.72,.52,.03],[.40,.67,.045],[.91,.81,.027],
        [.17,.39,.03],[.56,.17,.032],[.31,.75,.028]]
    result=[];shapes=[];cap=path_polygon(cap_path(p))
    for i,(x,yy,r) in enumerate(locations[:p['spots']]):
        jitter=math.sin(seed*7.13+i*13.17)*.025 if seed else 0
        cx,cy=w*(x+jitter),y*(yy+jitter)
        if not p.get('spotMap'):
            from shapely.geometry import Point
            a,b,c,d=cap.bounds
            candidates=[(cx,cy)]+sorted([(a+(c-a)*xx/24,b+(d-b)*yy/18) for xx in range(1,24) for yy in range(1,18)],key=lambda q:math.dist(q,(cx,cy)))
            for attempt in range(20):
                inner=cap.buffer(-w*r)
                candidate=next((q for q in candidates if inner.covers(Point(q)) and all(Point(q).distance(prior)>w*r+.025 for prior in shapes)),None)
                if candidate is not None:cx,cy=candidate;break
                r*=.85
        for attempt in range(24):
            path=inkex.Path(ellipse(cx,cy,w*r,w*r*(.82+.12*math.sin(i*2.5))))
            shape=path_polygon(path).intersection(cap)
            if p.get('spotMap') or not any(shape.buffer(.025).intersects(prior) for prior in shapes):break
            r*=.85
        shapes.append(shape)
        result.append(dict(id=str(i+1),name=f'Spot {i+1}',contours=normalized(path,w,h),rotation=0))
    return result


def editable(p):
    return {**copy.deepcopy(p),'capContours':copy.deepcopy(p.get('capContours') or normalized(cap_path(p),p['width'],p['height'])),
        'capPivot':p.get('capPivot',[.5,p['dome']*.56]),'spotDetails':spot_details(p)}


def spots(p,transform,cap):
    from components import path_polygon,polygon_path
    w,h=p['width'],p['height'];paths=[];shapes=[];names=[]
    for detail in spot_details(p):
        raw=inkex.Path(contour_d(detail['contours'],w,h)).transform(transform)
        shape=path_polygon(raw).intersection(cap)
        if shape.is_empty or shape.area<.0001:raise ValueError(detail['name']+' is outside the cap. Move it into the cap or remove it.')
        # Explicit spots never merge. A collision is editable feedback, instead
        # of silently replacing two spots with a single white patch.
        for prior,name in zip(shapes,names):
            if prior.intersection(shape).area>.0001:raise ValueError(detail['name']+' overlaps '+name+'. Move or resize the spots to keep them separate.')
        shapes.append(shape);names.append(detail['name'])
        paths.append(raw if cap.buffer(.001).covers(path_polygon(raw)) else polygon_path(shape))
    result=inkex.Path()
    for path in paths:result+=path
    return result,len(paths)
