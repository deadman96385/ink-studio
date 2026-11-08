"""Physical native stitch envelopes used by both component and scene fitting."""
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from digitizing import path_contours
from applique import flattened


def is_satin(layer):
    return layer.get('stitch') == 'satin' or str(layer.get('originalParams', {}).get('satin_column', '')).lower() == 'true'


def envelope(layer, path, s):
    from components import path_polygon
    contours = path_contours(path)
    if layer.get('merrow') and layer.get('stitch')=='original':
        from merrow import settings
        return unary_union([LineString(flattened(c,.015)) for c in contours]).buffer(settings(layer['merrow'],s)['width']/2)
    halo = s.number(layer.get('pullCompensation', 0), 0, 1, 'Compensation')
    flow_fill=layer.get('stitch')=='fill' and layer.get('fillMethod') in ('streamline_fill','wave_fill')
    if flow_fill:halo=0
    from feather import active,settings
    feather_halo=settings(layer['feather'],s,layer.get('id','feather'))['raggedness'] if active(layer) else 0
    if is_satin(layer):
        if len(contours) < 2:
            raise ValueError('A satin motif needs two editable rails.')
        shape = Polygon(flattened(contours[0], .015)+list(reversed(flattened(contours[1], .015))))
        if shape.is_empty or not shape.is_valid:
            raise ValueError('The satin rails cross or enclose no usable area.')
        return shape.buffer(halo+feather_halo)
    mode = layer.get('stitch', 'fill')
    if mode == 'fill' or mode == 'original' and layer.get('originalFill', True):
        if layer.get('smallFillFallback') and not flow_fill:halo=max(halo,.225)
        if layer.get('borderEnabled'):
            halo = max(halo, s.number(layer.get('borderWidth', 1.5), .3, 6, 'Outline width')/2 if layer.get('borderStitch') == 'zigzag' else .225)
        return path_polygon(path).buffer(halo+feather_halo)
    if mode in ('running', 'bean', 'zigzag'):
        radius = s.number(layer.get('strokeWidth', 1.5), .3, 6, 'Stroke width')/2 if mode == 'zigzag' else .225
        return unary_union([LineString(flattened(c, .015)) for c in contours]).buffer(radius)
    raise ValueError('Fit checks support native fills, satin columns and running/bean/zigzag paths.')
