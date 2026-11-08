"""Reusable small-patch recipes that reduce cuts, restarts and needle buildup."""
import copy
from functools import lru_cache
import hashlib
import json
import math


def is_simple(params):return params.get('sewingProfile')=='simple'


def simplify_guide(guide,s):
    from components import path_polygon,settings
    from digitizing import contour_d,inkex
    result=copy.deepcopy(guide);stats=dict(originalLeaves=0,leaves=0,originalSpots=0,spots=0)
    if not isinstance(result.get('scene',{}).get('items'),list):raise ValueError('Choose a scene with attached motifs.')
    for item in result['scene']['items']:
        if item.get('kind') not in ('branch','mushroom'):raise ValueError('Simplification supports mushroom and branch motifs.')
        p=settings(item['kind'],{**item.get('params',{}),'profile':'botanical'},s);item['params']=p
        if item['kind']=='branch' and not p.get('leafMap'):
            from leaf_layout import layout
            p['stemCurve'],p['leafMap']=layout(p)
        if item['kind']=='mushroom' and 'spotDetails' not in p:
            from mushroom_layout import editable
            p=editable(p);item['params']=p
        scale=s.number(item.get('scale',1),.2,2,'Motif scale');w,h=p['width']*scale,p['height']*scale
        p.update(sewingProfile='simple',sewingScale=scale)
        item['pinned']=False
        if item['kind']=='branch':
            leaves=p.get('leafMap',[]);stats['originalLeaves']+=len(leaves)
            kept=[leaf for leaf in leaves if math.hypot((leaf['tip'][0]-leaf['base'][0])*w,(leaf['tip'][1]-leaf['base'][1])*h)>=2.5 and leaf['width']*w*1.34>=1.5]
            if not kept and leaves:kept=[max(leaves,key=lambda l:l['width'])]
            p['leafMap']=[{**leaf,'split':False} for leaf in kept]
            p.update(leafColor='#6c9c39',lightColor='#6c9c39',stemColor='#6c9c39')
            stats['leaves']+=len(kept)
        else:
            details=p.get('spotDetails',[]);stats['originalSpots']+=len(details);kept=[]
            for spot in details:
                shape=path_polygon(inkex.Path(contour_d(spot['contours'],w,h)));a,b,c,d=shape.bounds
                if shape.area>=.55 and min(c-a,d-b)>=.85:kept.append((shape.area,spot))
            if w<8:kept=sorted(kept,key=lambda x:x[0],reverse=True)[:3]
            selected={spot['id'] for area,spot in kept}
            p['spotDetails']=[spot for spot in details if spot['id'] in selected]
            p.update(spots=len(selected),detail=1,gillColor=p['creamColor'])
            stats['spots']+=len(selected)
    result['scene']['sewingProfile']='simple'
    result['scene']['groundUnderlap']=.3
    return dict(guide=result,stats=stats)


@lru_cache(maxsize=96)
def _routed_branch(encoded):
    import server
    from advanced import route
    from leaf_layout import branch
    params=json.loads(encoded);parts=branch(params,routed_source=True)
    prepared=[]
    for i,(key,layer) in enumerate(parts):
        layer['id']='simple-'+hashlib.sha256((encoded+':'+key).encode()).hexdigest()[:24]
        layer.pop('paintStage',None);prepared.append(layer)
    routed=route(dict(kind='satin',layers=prepared,preserveOrder=False,trim=False),server)['layers']
    result=[]
    for i,layer in enumerate(routed):
        satin=str(layer.get('originalParams',{}).get('satin_column','')).lower()=='true'
        layer.update(stitch='satin' if satin else 'running',spacing=.42,stitchLength=2,
            satinCenter=False,satinContour=False,satinZigzag=False,satinMaxLength=5,
            underlay=False,trimAfter=i==len(routed)-1,advanced={'min_stitch_length_mm':.3})
        for key in ('originalParams','originalFill','originalStroke','originalWidth','originalFillRule','paintStage'):layer.pop(key,None)
        result.append((f'route-{i+1:02}',layer))
    return result


def routed_branch(params):return copy.deepcopy(_routed_branch(json.dumps(params,sort_keys=True)))
