"""Radial gill threads around a neck, rather than spokes meeting at one point."""
import math
from shapely.geometry import Point


def gill_threads(bed,left,right,spacing=.26,repeats=2):
    if bed.geom_type=='MultiPolygon':bed=max(bed.geoms,key=lambda p:p.area)
    edge=bed.exterior
    neck=[(a+b)/2 for a,b in zip(left[0],right[0])]
    dx,dy=right[0][0]-left[0][0],right[0][1]-left[0][1]
    width=max(.15,math.hypot(dx,dy));ux,uy=dx/width,dy/width
    # The radial inner rail is hidden beneath the stem's rounded neck.
    rx,ry=width*.46,width*.13
    count=max(18,min(320,math.ceil(edge.length/spacing)))
    lines=[]
    for i in range(count):
        q=edge.interpolate((i+.5)*edge.length/count);ex,ey=q.x,q.y
        vx,vy=ex-neck[0],ey-neck[1]
        angle=math.atan2(-vx*uy+vy*ux,vx*ux+vy*uy)
        cx=neck[0]+rx*math.cos(angle)*ux-ry*math.sin(angle)*uy
        cy=neck[1]+rx*math.cos(angle)*uy+ry*math.sin(angle)*ux
        if not lines:lines.append(f'M{cx},{cy}')
        else:lines.append(f'L{cx},{cy}')
        # Each cream thread crosses the bed and returns; movement between rays
        # stays under the subsequently sewn stem instead of crossing open gills.
        lines.extend([f'L{ex},{ey} L{cx},{cy}']*repeats)
    return ' '.join(lines)
