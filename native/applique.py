"""Placement, tack-down and edge-finishing paths for fabric appliqué."""
import copy
import math
import uuid
import inkex
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union
from digitizing import geometry, path_contours, from_path


def flattened(contour,tolerance=.01):
    nodes=contour['nodes'];out=[(nodes[0]['x'],nodes[0]['y'])]
    def curve(a,b,c,d,depth=0):
        dx,dy=d[0]-a[0],d[1]-a[1];length=math.hypot(dx,dy)
        flat=max(abs(dx*(p[1]-a[1])-dy*(p[0]-a[0]))/length if length else math.dist(a,p) for p in (b,c))
        # Also split loops / collinear reversals whose controls extend past ends.
        if depth>=14 or flat<=tolerance and math.dist(a,b)+math.dist(b,c)+math.dist(c,d)<=length+tolerance:
            out.append(d);return
        mid=lambda p,q:((p[0]+q[0])/2,(p[1]+q[1])/2)
        ab,bc,cd=mid(a,b),mid(b,c),mid(c,d);abc,bcd=mid(ab,bc),mid(bc,cd);m=mid(abc,bcd)
        curve(a,ab,abc,m,depth+1);curve(m,bcd,cd,d,depth+1)
    for a,b in list(zip(nodes,nodes[1:]))+([(nodes[-1],nodes[0])] if contour['closed'] else []):
        curve((a['x'],a['y']),a['out'],b['in'],(b['x'],b['y']))
        if len(out)>20000:raise ValueError('Simplify this outline before making an appliqué.')
    return out


def inset_path(path,distance,fill_rule):
    contours=path_contours(path)
    if not contours or any(not c['closed'] for c in contours):raise ValueError('Appliqué needs closed outlines. Close the path in Edit nodes first.')
    if not distance:return path
    rings=[flattened(c) for c in contours]
    def winding(x,y):
        total=0
        for ring in rings:
            for a,b in zip(ring,ring[1:]):
                cross=(b[0]-a[0])*(y-a[1])-(x-a[0])*(b[1]-a[1])
                if a[1]<=y<b[1] and cross>0:total+=1
                elif b[1]<=y<a[1] and cross<0:total-=1
        return total
    faces=[]
    for face in polygonize(unary_union([LineString(r) for r in rings])):
        point=face.representative_point();n=winding(point.x,point.y)
        if n%2 if fill_rule=='evenodd' else n!=0:faces.append(face)
    shape=unary_union(faces).buffer(-distance,join_style='round',quad_segs=12)
    if shape.is_empty:raise ValueError('The tack-down inset removes this shape. Reduce the inset or enlarge the design.')
    pieces=list(shape.geoms) if shape.geom_type=='MultiPolygon' else [shape]
    d=[]
    for piece in pieces:
        if piece.geom_type!='Polygon':continue
        for ring in [piece.exterior,*piece.interiors]:
            coords=list(ring.coords);d.append('M'+' L'.join(f'{x},{y}' for x,y in coords)+' Z')
    if sum(len(r.coords) for p in pieces if p.geom_type=='Polygon' for r in [p.exterior,*p.interiors])>2400:raise ValueError('Simplify the outline before making an inset appliqué.')
    return inkex.Path(' '.join(d))


def prepare(layers,params,s):
    from multisatin import layer_preview
    if len(layers)>10:raise ValueError('Prepare at most 10 appliqué pieces at once.')
    if params['tackInset']+(.5*params['tackWidth'] if params['tackStitch']=='zigzag' else 0)>params['finishWidth']/2 and params['finishStitch'] in ('zigzag','satin','e_stitch'):
        raise ValueError('The finishing edge will not cover the tack-down. Reduce its inset / width or widen the finishing edge.')
    stage_sets=[];originals=[]
    for layer in layers:
        raw=s.build_svg({'version':1,'layers':[{**layer,'borderEnabled':False}]})
        items=[(path,style) for e,path,style in geometry(raw) if str(style.get('fill','black'))!='none']
        if not items:raise ValueError('Select filled shapes for appliqué. Separate imported SVG paths first.')
        outlines=inkex.Path();insets=inkex.Path()
        for path,style in items:
            outlines.extend(inset_path(path,0,str(style.get('fill-rule','nonzero'))))
            insets.extend(inset_path(path,params['tackInset'],str(style.get('fill-rule','nonzero'))))
        name=layer.get('name','Appliqué');stages=[];group_id=uuid.uuid4().hex
        for i,(stage,path,mode,color) in enumerate([
            ('Placement · add fabric',outlines,'running',params['placementColor']),
            ('Tack-down · trim fabric',insets,params['tackStitch'],params['tackColor']),
            ('Finish edge',outlines,params['finishStitch'],params['finishColor'])]):
            base={'name':f'{name} · {i+1} {stage}','color':color,'stitch':mode,'stitchLength':params['stitchLength'],
                  'spacing':params['finishSpacing'] if i==2 else params['tackSpacing'],'strokeWidth':params['finishWidth'] if i==2 else params['tackWidth'],
                  'trimAfter':True,'stopAfter':False,'underlay':False,'appliqueStage':['placement','tackdown','finish'][i]}
            if mode in ('satin','e_stitch'):
                base.update(stitch='original',originalFill=False,originalStroke=True,originalWidth=params['finishWidth'],
                            originalParams={'satin_column':'True','satin_method':'e_stitch' if mode=='e_stitch' else 'satin_column',
                            'zigzag_spacing_mm':str(params['finishSpacing']),'center_walk_underlay':'True','contour_underlay':'False',
                            'zigzag_underlay':'False','max_stitch_length_mm':'6','random_seed':'applique-edge'})
            created=from_path(path,base);created['groupId']=group_id;stages.append(created)
        stage_sets.append(stages)
        if params['keepSource']:
            original=copy.deepcopy(layer);original.update(id=uuid.uuid4().hex,visible=False,name=name+' · source (hidden)',groupId=group_id);originals.append(original)
    if params['sequence']=='stage':
        result=[]
        for i in range(3):
            group=[stages[i] for stages in stage_sets]
            if i<2:
                # A color change already pauses the machine. Adding STOP too
                # creates redundant empty color blocks in Ink/Stitch's PES.
                group[-1]['stopAfter']=group[-1]['color']==stage_sets[0][i+1]['color']
            result.extend(group)
    else:
        result=[]
        for group in stage_sets:
            group[0]['stopAfter']=group[0]['color']==group[1]['color']
            group[1]['stopAfter']=group[1]['color']==group[2]['color'];result.extend(group)
    preview=layer_preview({'layers':result},s)['preview']
    return {'layers':result+originals,'preview':preview,'tool':'applique'}
