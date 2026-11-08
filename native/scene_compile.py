"""Sewing-only compilation: background underlaps and tiny-detail fallback.

The editable project retains its source outline and motifs. SVG/PES receives
the derived stitch geometry, so moving/reflowing a scene cannot leave stale holes.
"""
import copy
from lxml import etree as ET
from shapely.ops import unary_union
from digitizing import inkex, path_contours


def physical_path(contours):
    # These are already validated SVG millimeter coordinates, not the native
    # editor's normalized node coordinates accepted by contour_d.
    chunks=[]
    for c in contours:
        nodes=c['nodes'];chunks.append(f'M{nodes[0]["x"]},{nodes[0]["y"]}')
        pairs=list(zip(nodes,nodes[1:]))+([(nodes[-1],nodes[0])] if c['closed'] else [])
        for a,b in pairs:chunks.append(f'C{a["out"][0]},{a["out"][1]} {b["in"][0]},{b["in"][1]} {b["x"]},{b["y"]}')
        if c['closed']:chunks.append('Z')
    return ' '.join(chunks)


def ground(content, layer, project, s):
    from components import world_path, path_polygon, polygon_path
    from scenes import footprint
    guides=[]
    for guide in project.get('layers',[]):
        recipe=guide.get('scene',{})
        if guide.get('role')!='scene-guide' or not recipe.get('knockoutBackground'):continue
        area=next((l for l in project['layers'] if l['id']==recipe.get('areaId')),None)
        if area and area.get('areaSource')==layer['id']:guides.append(guide)
    if not guides or layer.get('stitch')!='fill' or layer.get('type')!='path':return content
    masks=[]
    for guide in guides:
        underlap=s.number(guide['scene'].get('groundUnderlap',.25),.1,.8,'Background underlap')
        for piece in project['layers']:
            if piece.get('sceneBinding',{}).get('guideId')!=guide['id'] or piece.get('visible') is False:continue
            # Thin running details do not justify tiny needle-island holes.
            if piece.get('stitch') not in ('fill','satin'):continue
            shape=footprint(piece,s).buffer(-underlap)
            if not shape.is_empty and shape.area>.2:masks.append(shape)
    if not masks:return content
    shape=path_polygon(world_path(layer,s)).difference(unary_union(masks))
    if shape.is_empty:raise ValueError('The foreground removes the entire background. Reduce the knockout underlap.')
    w,h=layer['width'],layer['height']
    transform=(inkex.Transform(translate=(layer['x'],layer['y'])) @ inkex.Transform(rotate=(layer.get('rotation',0),w/2,h/2))
        @ inkex.Transform(translate=(w if layer.get('flipX') else 0,h if layer.get('flipY') else 0))
        @ inkex.Transform(scale=(-1 if layer.get('flipX') else 1,-1 if layer.get('flipY') else 1)))
    # Separate islands avoid nested exterior rings being read as crossing holes
    # by the embroidery engine. This is still one editable background layer.
    pieces=list(shape.geoms) if shape.geom_type=='MultiPolygon' else [shape]
    wrapper=ET.Element('{'+s.SVG+'}g')
    for piece in pieces:
        path=copy.deepcopy(content)
        path.set('d',str(polygon_path(piece).transform(-transform)))
        path.set('fill-rule','evenodd');wrapper.append(path)
    return wrapper


def small_fills(content, layer, s):
    if not layer.get('smallFillFallback') or layer.get('stitch')!='fill':return content
    from components import path_polygon,polygon_path
    from shapely.geometry import LineString
    shape=path_polygon(inkex.Path(content.get('d','')))
    pieces=list(shape.geoms) if shape.geom_type=='MultiPolygon' else [shape]
    small=[];large=[]
    for piece in pieces:
        minx,miny,maxx,maxy=piece.bounds
        (small if piece.area<1.4 or min(maxx-minx,maxy-miny)<.9 else large).append(piece)
    wrapper=ET.Element('{'+s.SVG+'}g')
    # Each island is a separate embroidery object with an explicit trim. A
    # compound fill/bean path otherwise routes white travel stitches over red.
    for piece in large:
        filled=copy.deepcopy(content);filled.set('d',str(polygon_path(piece)))
        filled.set('{'+s.STITCH+'}trim_after',str(True if layer.get('isolateFillIslands',True) else bool(layer.get('trimAfter',True))));wrapper.append(filled)
    for piece in small:
        strokes=[]
        strokes.append(str(polygon_path(piece)))
        x,y=piece.representative_point().coords[0];a,b,c,d=piece.bounds
        # Two clipped cross stitches fill the middle of a tiny outlined spot.
        for line in [LineString([(a,y),(c,y)]),LineString([(x,b),(x,d)])]:
            clipped=piece.intersection(line)
            for segment in ([clipped] if clipped.geom_type=='LineString' else getattr(clipped,'geoms',[])):
                if segment.geom_type=='LineString' and segment.length>.05:
                    coords=list(segment.coords);strokes.append('M'+' L'.join(f'{px},{py}' for px,py in coords))
        dots=ET.SubElement(wrapper,'{'+s.SVG+'}path',d=' '.join(strokes))
        s.stitch_settings(dots,{**layer,'stitch':'bean','stitchLength':.5 if layer.get('isolateFillIslands',True) else .7,'trimAfter':True if layer.get('isolateFillIslands',True) else bool(layer.get('trimAfter',True))})
    return wrapper
