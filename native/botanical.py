"""Botanical embroidery recipes: organic caps, satin stems and tapered leaves."""
import math
from shapely.geometry import box
from digitizing import inkex, from_path


def cubic(points, t):
    return tuple(sum(points[j][axis]*math.comb(3,j)*t**j*(1-t)**(3-j) for j in range(4)) for axis in (0,1))


def rail_path(points):
    return 'M'+','.join(map(str,points[0]))+' C'+' '.join(','.join(map(str,p)) for p in points[1:])


def satin(left, right, name, color, phase, spacing=.36):
    d=rail_path(left)+' '+rail_path(right)
    for t in (.18,.5,.82):
        a,b=cubic(left,t),cubic(right,t)
        dx,dy=b[0]-a[0],b[1]-a[1]
        d+=f' M{a[0]-.12*dx},{a[1]-.12*dy} L{b[0]+.12*dx},{b[1]+.12*dy}'
    layer=from_path(inkex.Path(d),dict(name=name,color=color,stitch='satin',spacing=spacing,
        stitchLength=2,underlay=False,trimAfter=True,satinCenter=True,satinContour=False,
        satinZigzag=False,satinMaxLength=6,paintStage=phase))
    return layer


def mushroom(p):
    from components import part, ellipse, path_polygon, polygon_path
    from mushroom_layout import cap_path,spots
    w,h=p['width'],p['height']; y=h*p['dome']; cream=p['creamColor'];simple=p.get('sewingProfile')=='simple'
    tilt=p.get('capTilt',0); center=tuple(v*d for v,d in zip(p.get('capPivot',[.5,p['dome']*.56]),(w,h)))
    transform=inkex.Transform(translate=center)@inkex.Transform(rotate=tilt)@inkex.Transform(translate=(-center[0],-center[1]))
    cap=cap_path(p).transform(transform)
    gills=p.get('gillMap')
    if gills:
        upper=[(x*w,yy*h) for x,yy in gills['upper']];lower=[(x*w,yy*h) for x,yy in gills['lower']]
        back=list(reversed(lower));underside=inkex.Path(rail_path(upper)+' C'+' '.join(','.join(map(str,q)) for q in back[1:])+' Z').transform(transform)
    else:underside=inkex.Path(ellipse(w*.5,y+h*.015,w*.475,h*.14)).transform(transform)
    if p.get('gillContours'):
        from digitizing import contour_d
        underside=inkex.Path(contour_d(p['gillContours'],w,h)).transform(transform)
    under=part(str(underside),'Mushroom · ivory gill bed',cream);under.update(spacing=.36,angle=80,paintStage=0)
    out=[('underside',under)]
    # A connected fan returns along each curved ray; no per-ray trim/jump.
    hub=(gills['hub'][0]*w,gills['hub'][1]*h) if gills else (w*.51,y+h*.09); fan=[]
    bed_shape=path_polygon(underside.transform(-transform)) if p.get('gillContours') else None
    count=max(9,min(41 if p.get('detail',2)==3 else 27,int(w*(2 if p.get('detail',2)==3 else 1.4))))
    for i in range(count):
        t=.035+.93*(i+.5)/count; ex=w*t
        up=cubic(upper,t) if gills else cubic([(0,y),(w*.22,y-h*.18),(w*.76,y-h*.18),(w,y)],t)
        down=cubic(lower,t) if gills else (ex,y+h*.015+h*.137*math.sqrt(max(0,1-((t-.5)*2)**2)))
        if not i:fan.append(f'M{hub[0]},{hub[1]}')
        for ex,ey in [up,down]:
            if bed_shape is not None:
                from shapely.geometry import LineString,Point
                dx,dy=ex-hub[0],ey-hub[1]
                line=bed_shape.intersection(LineString([hub,(hub[0]+dx*4,hub[1]+dy*4)]))
                pieces=[line] if line.geom_type=='LineString' else list(getattr(line,'geoms',[]))
                choices=[piece for piece in pieces if piece.geom_type=='LineString' and piece.distance(Point(hub))<.05]
                if choices:ex,ey=max((q for piece in choices for q in piece.coords),key=lambda q:math.dist(q,hub))
            cx=(hub[0]+ex)*.5;cy=(hub[1]+ey)*.5-h*.012
            fan.append(f'Q{cx},{cy} {ex},{ey} Q{cx},{cy} {hub[0]},{hub[1]}')
    gill=part(str(inkex.Path(' '.join(fan)).transform(transform)),'Mushroom · curved gill fan',p['gillColor'],'running')
    gill.update(stitchLength=1.25,trimAfter=False,paintStage=1);out.append(('gills',gill))
    sw=w*p.get('stemWidth',.2);bend=p['bend']*w
    neck=(w*.51,y+h*.04);end=(w*(.5+p['bend']),h-h*.015)
    left=[(neck[0]-sw*.47,neck[1]),(w*.45+bend*.15,y+(h-y)*.45),(w*.45+bend*.35,h-h*.1),(end[0]-sw*.35,end[1])]
    right=[(neck[0]+sw*.47,neck[1]),(w*.45+sw+bend*.15,y+(h-y)*.45),(w*.45+sw+bend*.35,h-h*.1),(end[0]+sw*.35,end[1])]
    if p.get('stemRails'):left,right=[[(x*w,yy*h) for x,yy in rail] for rail in p['stemRails']]
    fan_left,fan_right=list(left),list(right)
    if tilt:
        for rail in (left,right):
            for i,weight in [(0,1),(1,.55)]:
                point=rail[i];turned=transform.apply_to_point(point);rail[i]=(point[0]+(turned.x-point[0])*weight,point[1]+(turned.y-point[1])*weight)
    if p.get('gillContours'):
        from mushroom_anatomy import gill_threads
        fan_path=inkex.Path(gill_threads(bed_shape,fan_left,fan_right,.5 if simple else .21 if p.get('detail',2)==3 else .26,repeats=1 if simple else 2)).transform(transform)
        gill=part(str(fan_path),'Mushroom · neck-shaped radial gill threads',cream,'running')
        gill.update(stitchLength=2.8,trimAfter=False,paintStage=1)
        out[1]=('gills',gill);under['color']=p['gillColor'];under['spacing']=.48
        if simple:
            under.update(color=cream,spacing=.45,underlay=False,trimAfter=False,advanced={'min_stitch_length_mm':.3})
            gill.update(stitchLength=3,advanced={'min_stitch_length_mm':.3})
            if w*p.get('sewingScale',1)<8:out=[out[0]]
    if p.get('stemContours'):
        from digitizing import contour_d
        stem_shape=inkex.Path(contour_d(p['stemContours'],w,h))
        # Only the neck follows cap tilt, matching the existing rail behavior.
        if tilt:
            contours=__import__('digitizing').path_contours(stem_shape)
            neck_y=(left[0][1]+right[0][1])/2
            for contour in contours:
                for n in contour['nodes']:
                    for key in ('node','in','out'):
                        q=[n['x'],n['y']] if key=='node' else n[key]
                        weight=max(0,min(1,1-(q[1]-neck_y)/max(.1,h*.35)))
                        turned=transform.apply_to_point(q);v=[q[0]+(turned.x-q[0])*weight,q[1]+(turned.y-q[1])*weight]
                        if key=='node':n['x'],n['y']=v
                        else:n[key]=v
            from scene_compile import physical_path
            stem_shape=inkex.Path(physical_path(contours))
        from stem_flow import layers as stem_layers
        out.extend(stem_layers(path_polygon(stem_shape),left,right,p))
    else:out.append(('stem',satin(left,right,'Mushroom · shaped satin stem',cream,2)))
    if p.get('detail',2)>=2 and not p.get('stemContours'):
        grain=[]
        for f in (.2,.47,.75):
            a=[(l[0]*(1-f)+r[0]*f,l[1]*(1-f)+r[1]*f) for l,r in zip(left,right)]
            grain.append(rail_path(a))
        layer=part(' '.join(grain),'Mushroom · stem grain',p['gillColor'],'running')
        layer.update(stitchLength=1.6,trimAfter=False,paintStage=3);out.append(('stem-grain',layer))
    # Adjacent fill regions carry different directions without fake drawn thread.
    shape=path_polygon(cap)
    if p.get('detail',2)>=2 and not simple:
        for name,a,b,angle in [('left',-w,w*.34,-28),('crown',w*.34,w*.67,5),('right',w*.67,w*2,32)]:
            piece=shape.intersection(box(a,-h,b,h*2).buffer(.035))
            layer=part(str(polygon_path(piece)),'Mushroom · '+name+' cap',p['capColor'])
            layer.update(spacing=.35,angle=angle,stitchLength=2.5,paintStage=4)
            out.append(('cap-'+name,layer))
    else:
        layer=part(str(cap),'Mushroom · organic cap',p['capColor']);layer.update(spacing=.35,paintStage=4)
        if simple:layer.update(spacing=.42,underlay=False,stitchLength=3,smallFillFallback=True,advanced={'min_stitch_length_mm':.3})
        out.append(('cap',layer))
    lip=inkex.Path(rail_path(upper) if gills else f'M0,{y} C{w*.22},{y-h*.18} {w*.76},{y-h*.18} {w},{y}').transform(transform)
    if p.get('gillContours'):
        edge=shape.boundary.intersection(path_polygon(underside).buffer(.25))
        lines=[edge] if edge.geom_type=='LineString' else list(getattr(edge,'geoms',[]))
        d=' '.join('M'+' L'.join(f'{x},{yy}' for x,yy in line.coords) for line in lines if line.geom_type=='LineString' and line.length>.05)
        if d:lip=inkex.Path(d)
    rim=part(str(lip),'Mushroom · red rolled rim',p.get('rimColor','#9e1020'),'bean')
    rim.update(stitchLength=1.4,trimAfter=False,paintStage=5)
    if not simple:out.append(('cap-rim',rim))
    dots,count=spots(p,transform,shape)
    if count:
        layer=part(str(dots),'Mushroom · isolated ivory spots',cream)
        layer.update(spacing=.32,stitchLength=1.25,angle=65,underlay=False,paintStage=6,smallFillFallback=True,spotCount=count)
        if simple:layer.update(spacing=.4,stitchLength=2,advanced={'min_stitch_length_mm':.3})
        out.append(('spots',layer))
    return out


def branch(p):
    from leaf_layout import branch as build
    return build(p)
