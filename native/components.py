"""Reusable vector recipes. Generated parts are ordinary native editable paths.

This module does not save projects or mutate input layers. Both the touch UI and
future scene/AI tools can use the same generate, refresh-area and fit operations.
All geometry and recipe dimensions are millimeters, before the instance pose.
"""
import copy
import math
import uuid

from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

from digitizing import inkex, from_path, geometry, path_contours
from applique import flattened

AREA_ROLE = 'content-area'
VERSION = 1


def field(key, label, default, low=None, high=None, kind='number', options=None):
    return dict(key=key, label=label, default=default, min=low, max=high, kind=kind, options=options)


def profile():
    return field('profile','Construction style','classic',kind='select',options=[['classic','Simple study'],['botanical','Botanical embroidery']])


PATCH_SHAPES = [['circle', 'Circle'], ['oval', 'Oval'], ['rectangle', 'Rectangle'], ['rounded', 'Rounded rectangle'],
                ['shield', 'Shield'], ['hexagon', 'Hexagon'], ['arch', 'Arch top'], ['custom', 'Selected shape']]


def border_fields():
    return [field('borderStyle','Border style','zigzag',kind='select',options=[['zigzag','Satin / zigzag'],['merrow','Faux merrow']]),
        field('merrowSpacing','Fan stitch spacing (mm)',.4,.2,1.2),field('merrowFanLength','Fan length along border (mm)',2.4,1,8),
        field('merrowSpread','Gathered fan spread (%)',30,10,80),field('merrowBinding','Binding depth (mm)',.45,.1,2),
        field('merrowSide','Gather on','inside',kind='select',options=[['inside','Inside edge'],['outside','Outside edge']]),
        field('merrowUnderlay','Border underlay','center',kind='select',options=[['none','None'],['center','Center run'],['center-contour','Center + contour runs'],['full','Center, contour + zigzag']])]


def merrow_params(p):
    return dict(width=p['borderWidth'],spacing=p['merrowSpacing'],fanLength=p['merrowFanLength'],spread=p['merrowSpread']/100,
        bindingDepth=p['merrowBinding'],side=p['merrowSide'],underlay=p['merrowUnderlay'])

CATALOG = [
    dict(key='patch', label='Patch', fields=[
        field('shape', 'Shape', 'rounded', kind='select', options=PATCH_SHAPES),
        field('construction', 'Construction', 'embroidered', kind='select',
              options=[['embroidered', 'Embroidered background'], ['applique', 'Fabric appliqué']]),
        field('width', 'Width (mm)', 80, 15, 98), field('height', 'Height (mm)', 50, 15, 98),
        field('cornerRadius', 'Corner radius (mm)', 8, 0, 40),
        field('borderWidth', 'Border width (mm)', 3, .8, 6),
        *border_fields(),
        field('clearance', 'Content gap inside border (mm)', 1.5, 0, 8),
        field('spacing', 'Background row spacing (mm)', .45, .3, 1),
        field('tackInset', 'Tack-down inset (mm)', .6, 0, 3),
        field('bodyColor', 'Background thread', '#1f3a5f', kind='color'),
        field('edgeColor', 'Border thread', '#d9b44a', kind='color'),
        field('placementColor', 'Placement / tack-down thread', '#8c9a86', kind='color')]),
    dict(key='crescent', label='Crescent patch', fields=[
        profile(),
        field('width', 'Width (mm)', 74, 25, 94), field('height', 'Height (mm)', 88, 30, 94),
        field('borderWidth', 'Cover edge width (mm)', 2, .6, 4),
        *border_fields(),
        field('clearance', 'Content gap beyond edge (mm)', .8, 0, 5),
        field('spacing', 'Background row spacing (mm)', .5, .3, 1),
        field('bodyColor', 'Background thread', '#087c9b', kind='color'),
        field('edgeColor', 'Edge thread', '#073b4b', kind='color')]),
    dict(key='mushroom', label='Mushroom', fields=[
        profile(),
        field('width', 'Cap width (mm)', 22, 10, 45), field('height', 'Full height (mm)', 28, 15, 55),
        field('bend', 'Stem bend', .12, -.3, .3), field('dome', 'Cap height fraction', .38, .25, .62),
        field('spots', 'Cap spots', 5, 0, 12, 'integer'),
        field('capTilt','Cap tilt (degrees)',0,-25,25),field('stemWidth','Stem width / cap width',.2,.12,.35),
        field('detail','Stitch detail',2,1,3,'integer'),field('spotSeed','Spot variation',0,0,999,'integer'),
        field('capColor', 'Cap thread', '#c91830', kind='color'),
        field('creamColor', 'Stem and spots thread', '#f4e9c9', kind='color'),
        field('gillColor', 'Gill thread', '#b8a17a', kind='color')]),
    dict(key='branch', label='Leafy branch', fields=[
        profile(),
        field('width', 'Spread (mm)', 18, 8, 40), field('height', 'Height (mm)', 32, 15, 60),
        field('bend', 'Branch bend', .18, -.3, .3), field('pairs', 'Leaf pairs', 3, 2, 5, 'integer'),
        field('leafWidth','Leaf fullness',.36,.2,.6),
        field('leafSide','Leaf placement','both',kind='select',options=[['both','Both sides'],['left','Left side'],['right','Right side']]),
        field('lightColor','Leaf highlight thread','#add046',kind='color'),
        field('leafColor', 'Leaf thread', '#64a638', kind='color'),
        field('stemColor', 'Stem and veins thread', '#315b2c', kind='color')])]


def catalog(s):
    """Recipe catalog for the UI, including the user's saved motifs."""
    import motifs
    saved = motifs.listing(s)
    entry = dict(key='motif', label='Saved motif', fields=[
        field('motif', 'Motif', saved[0]['id'] if saved else '', kind='select', options=[[m['id'], m['name']] for m in saved]),
        field('width', 'Width (mm)', 20, 2, 98)])
    return CATALOG + [entry]


def settings(kind, raw, s):
    if kind == 'motif':
        import motifs
        return motifs.settings(raw if isinstance(raw, dict) else {}, s)
    spec = next((c for c in CATALOG if c['key'] == kind), None)
    if spec is None:
        raise ValueError('Choose a patch, crescent, mushroom or branch.')
    if not isinstance(raw, dict):
        raise ValueError('Send component settings as an object.')
    result = {}
    for f in spec['fields']:
        v = raw.get(f['key'], f['default'])
        if f['kind'] == 'select':
            if v not in [o[0] for o in f['options']]:raise ValueError('Choose a supported '+f['label'].lower()+'.')
        elif f['kind'] == 'color':
            v = s.color(v)
        else:
            v = s.number(v, f['min'], f['max'], f['label'])
            if f['kind'] == 'integer':
                if int(v) != v:
                    raise ValueError(f['label'] + ' must be a whole number.')
                v = int(v)
        result[f['key']] = v
    if kind in ('patch','crescent') and result['borderStyle']=='merrow':
        if result['merrowBinding']>result['borderWidth']*.8:raise ValueError('Binding depth must be at most 80% of the border width.')
    if kind == 'patch':
        if result['shape'] == 'circle':
            result['height'] = result['width']
        if result['shape'] == 'custom':
            outline = raw.get('outline')
            if not isinstance(outline, str) or len(outline) > 60000:
                raise ValueError('Select a closed shape to turn into a patch.')
            try:
                path = inkex.Path(outline)
            except Exception:
                raise ValueError('The selected shape could not be read.')
            contours = path_contours(path)
            if not contours or any(not c['closed'] for c in contours) or sum(len(c['nodes']) for c in contours) > 2000:
                raise ValueError('Patches need a closed outline with at most 2,000 nodes. Close or simplify the path first.')
            result['outline'] = str(path)
    if kind=='mushroom' and 'spotMap' in raw:
        spots=raw['spotMap']
        if not isinstance(spots,list) or len(spots)>12:raise ValueError('Use at most 12 custom spots.')
        result['spotMap']=[]
        for spot in spots:
            if not isinstance(spot,list) or len(spot)!=3:raise ValueError('A spot needs normalized X, Y and radius.')
            result['spotMap'].append([s.number(spot[0],0,1,'Spot X'),s.number(spot[1],0,1,'Spot Y'),s.number(spot[2],.015,.16,'Spot radius')])
    if kind=='branch':
        from leaf_layout import validate,layout
        result.update(validate(raw,s))
        if result.get('leafMap') and not result.get('stemCurve'):result['stemCurve']=layout(result)[0]
    if kind=='mushroom':
        from mushroom_layout import validate
        result.update(validate(raw,s))
    if kind in ('mushroom','branch') and 'sewingProfile' in raw:
        if raw['sewingProfile'] not in ('detailed','simple'):raise ValueError('Choose a supported sewing profile.')
        result['sewingProfile']=raw['sewingProfile']
        result['sewingScale']=s.number(raw.get('sewingScale',1),.2,2,'Sewing scale')
    return result


def path_polygon(path, fill_rule='evenodd'):
    """Resolve compound rings by fill rule, rather than assuming ring order."""
    contours = path_contours(path)
    if not contours or any(not c['closed'] for c in contours):
        raise ValueError('The patch and content area need closed paths.')
    rings = [flattened(c, .025) for c in contours]
    def winding(x, y):
        n = 0
        for ring in rings:
            for a, b in zip(ring, ring[1:]):
                cross = (b[0]-a[0])*(y-a[1]) - (x-a[0])*(b[1]-a[1])
                if a[1] <= y < b[1] and cross > 0:
                    n += 1
                elif b[1] <= y < a[1] and cross < 0:
                    n -= 1
        return n
    faces = []
    for face in polygonize(unary_union([LineString(r) for r in rings])):
        p = face.representative_point()
        n = winding(p.x, p.y)
        inside = n % 2 != 0 if fill_rule == 'evenodd' else n != 0
        if inside:
            faces.append(face)
    return unary_union(faces)


def polygon_path(shape):
    pieces = list(shape.geoms) if shape.geom_type == 'MultiPolygon' else [shape]
    chunks = []
    for piece in pieces:
        if piece.geom_type != 'Polygon':
            continue
        for ring in [piece.exterior, *piece.interiors]:
            chunks.append('M' + ' L'.join(f'{x:.5f},{y:.5f}' for x, y in ring.coords) + ' Z')
    return inkex.Path(' '.join(chunks))


def fit_path(d, width, height):
    path = inkex.Path(d)
    b = path.bounding_box()
    return path.transform(inkex.Transform(scale=(width/float(b.width), height/float(b.height)))).transform(
        inkex.Transform(translate=(-float(b.left)*width/float(b.width), -float(b.top)*height/float(b.height))))


def ellipse(cx, cy, rx, ry):
    return f'M{cx-rx},{cy} A{rx},{ry} 0 1 0 {cx+rx},{cy} A{rx},{ry} 0 1 0 {cx-rx},{cy} Z'


def part(d, name, color, stitch='fill', **extra):
    return from_path(inkex.Path(d), dict(name=name, color=color, stitch=stitch,
        spacing=.42, angle=45, stitchLength=2.2, underlay=True, trimAfter=True, **extra))


def crescent(p):
    if p.get('profile')=='botanical':
        outline=fit_path('M839,35 C684,-5 489,24 334,109 C152,210 39,392 18,604 '
            'C-7,849 70,1042 220,1176 C404,1345 642,1360 854,1276 C974,1229 1079,1161 1149,1107 '
            'Q1164,1090 1141,1100 C933,1166 702,1096 558,941 C426,797 404,622 442,451 '
            'C483,263 635,111 839,52 Q854,47 839,35 Z',p['width'],p['height'])
    else:
        outline = fit_path('M.72,.015 C.34,-.035 -.01,.25 .015,.52 '
        'C.015,.83 .33,1.09 .69,.965 C.83,.92 .94,.85 .985,.82 '
        'C.64,.90 .365,.68 .365,.425 C.365,.23 .49,.085 .72,.015 Z', p['width'], p['height'])
    base = part(str(outline), 'Crescent · blue ground', p['bodyColor'])
    base.update(spacing=p['spacing'], angle=25)
    edge = part(str(outline), 'Crescent · cover edge', p['edgeColor'], 'zigzag',
                strokeWidth=p['borderWidth'])
    edge.update(spacing=.35, underlay=False)
    if p.get('profile')=='botanical':base.update(spacing=p['spacing'],angle=15,stitchLength=2.8)
    if p.get('borderStyle')=='merrow':
        from merrow import from_outline
        edge=from_outline(outline,merrow_params(p),p['edgeColor'],'Crescent · faux merrow border')
        return [('body',base),('edge',edge)]
    if p.get('profile')=='botanical':
        base.update(spacing=p['spacing'],angle=15,stitchLength=2.8)
        edge.update(color='#062c39',strokeWidth=p['borderWidth']+.35,spacing=.32)
        rim=part(str(outline),'Crescent · blue satin cover',p['edgeColor'],'zigzag',strokeWidth=p['borderWidth'])
        rim.update(spacing=.32,underlay=False)
        return [('body',base),('edge-shadow',edge),('edge',rim)]
    return [('body', base), ('edge', edge)]


def mushroom(p):
    if p.get('profile')=='botanical':
        from botanical import mushroom as build
        return build(p)
    w, h, dome = p['width'], p['height'], p['dome']
    y = h*dome
    cream, red = p['creamColor'], p['capColor']
    underside = part(ellipse(w*.5, y, w*.49, h*.10), 'Mushroom · underside', cream)
    bend = p['bend']*w
    stem = part(f'M{w*.43},{y} C{w*.34+bend},{h*.60} {w*.62+bend},{h*.77} {w*.40},{h} '
        f'C{w*.74},{h*.99} {w*.72+bend},{h*.83} {w*.65+bend},{h*.66} '
        f'C{w*.59+bend},{h*.54} {w*.62},{y+h*.02} {w*.59},{y} Z', 'Mushroom · curved stem', cream)
    stem.update(angle=0)
    gills = []
    for i in range(11):
        t = (i+1)/12
        x = w*(.02+.96*t)
        ey = y+h*.095*math.sqrt(max(0, 1-((t-.5)*2)**2))
        gills.append(f'M{w*.51},{y-h*.02} Q{x*.6+w*.2},{y+h*.045} {x},{ey}')
    gill = part(' '.join(gills), 'Mushroom · fan gills', p['gillColor'], 'running')
    cap = part(f'M0,{y} C{w*.04},{y*.4} {w*.27},0 {w*.48},0 '
        f'C{w*.73},0 {w*.95},{y*.45} {w},{y} '
        f'C{w*.76},{y-h*.075} {w*.26},{y-h*.075} 0,{y} Z', 'Mushroom · red cap', red)
    cap.update(angle=-25)
    spots = []
    locations = [(.48,.28,.075),(.25,.56,.065),(.72,.57,.07),(.1,.84,.04),
                 (.9,.85,.04),(.48,.76,.05),(.62,.34,.037),(.34,.32,.036),(.20,.76,.035),(.78,.75,.03),(.42,.48,.03),(.58,.58,.03)]
    for x, yy, r in locations[:p['spots']]:
        spots.append(ellipse(w*x, y*yy, w*r, w*r*.88))
    result = [('underside', underside), ('gills', gill), ('stem', stem), ('cap', cap)]
    if spots:
        result.append(('spots', part(' '.join(spots), 'Mushroom · cream spots', cream)))
    return result


def branch(p):
    if p.get('profile')=='botanical':
        from botanical import branch as build
        return build(p)
    w, h = p['width'], p['height']
    bend = p['bend']*w
    def centre(t):
        return w*.5 + math.sin(t*math.pi)*bend, h*(1-t)
    left, right, veins = [], [], []
    for i in range(p['pairs']):
        t = .17 + i*.62/(p['pairs']-1)
        for side, target in [(-1, left), (1, right)]:
            x, y = centre(t+(0.035 if side==1 else 0))
            tx = x+side*w*(.47-.12*t)
            ty = y-h*(.16-.04*t)
            dx, dy = tx-x, ty-y
            nx, ny = -dy*.25, dx*.25
            target.append(f'M{x},{y} C{x+dx*.25+nx},{y+dy*.25+ny} '
                f'{tx+nx*.7},{ty+ny*.7} {tx},{ty} '
                f'C{tx-nx*.7},{ty-ny*.7} {x+dx*.25-nx},{y+dy*.25-ny} {x},{y} Z')
            veins.append(f'M{x},{y} Q{x+dx*.55},{y+dy*.45} {tx},{ty}')
    stem = f'M{w*.5},{h} C{w*.5+bend*1.3},{h*.66} {w*.5+bend*1.3},{h*.33} {w*.5},0'
    result = [('stem', part(stem, 'Branch · curved stem', p['stemColor'], 'bean')),
        ('left-leaves', part(' '.join(left), 'Branch · left leaves', p['leafColor'])),
        ('right-leaves', part(' '.join(right), 'Branch · right leaves', p['leafColor'])),
        ('veins', part(' '.join(veins), 'Branch · leaf veins', p['stemColor'], 'running'))]
    result[1][1]['angle'] = -40
    result[2][1]['angle'] = 40
    return result


def rounded_rect(w, h, r):
    r = max(0, min(r, w / 2, h / 2))
    if not r:
        return f'M0,0 H{w} V{h} H0 Z'
    k = r * .5523
    return (f'M{r},0 H{w-r} C{w-r+k},0 {w},{r-k} {w},{r} V{h-r} C{w},{h-r+k} {w-r+k},{h} {w-r},{h} '
            f'H{r} C{r-k},{h} 0,{h-r+k} 0,{h-r} V{r} C0,{r-k} {r-k},0 {r},0 Z')


def patch_outline(p):
    w, h, shape = p['width'], p['height'], p['shape']
    if shape in ('circle', 'oval'):
        return inkex.Path(ellipse(w / 2, h / 2, w / 2, h / 2))
    if shape == 'rectangle':
        return inkex.Path(rounded_rect(w, h, 0))
    if shape == 'rounded':
        return inkex.Path(rounded_rect(w, h, p['cornerRadius']))
    if shape == 'shield':
        return fit_path('M0,0 H1 V.52 C1,.78 .76,.92 .5,1 C.24,.92 0,.78 0,.52 Z', w, h)
    if shape == 'hexagon':
        return fit_path('M.25,0 L.75,0 L1,.5 L.75,1 L.25,1 L0,.5 Z', w, h)
    if shape == 'arch':
        r = w / 2
        if h <= r:
            raise ValueError('An arch-top patch must be taller than half its width.')
        k = r * .5523
        return inkex.Path(f'M0,{h} V{r} C0,{r-k} {r-k},0 {r},0 C{r+k},0 {w},{r-k} {w},{r} V{h} Z')
    return fit_path(p['outline'], w, h)


def patch(p):
    """Any patch shape, embroidered or appliqué, finished with a satin cover border."""
    outline = str(patch_outline(p))
    edge = part(outline, 'Patch · border', p['edgeColor'], 'zigzag', strokeWidth=p['borderWidth'])
    edge.update(spacing=.35, underlay=False)
    if p.get('borderStyle')=='merrow':
        from merrow import from_outline
        edge=from_outline(inkex.Path(outline),merrow_params(p),p['edgeColor'],'Patch · faux merrow border')
    if p['construction'] == 'embroidered':
        body = part(outline, 'Patch · background', p['bodyColor'])
        body.update(spacing=p['spacing'], angle=30)
        return [('body', body), ('edge', edge)]
    from applique import inset_path
    # Machine stops after placement (lay fabric) and after tack-down (trim fabric).
    # A thread change already stops the PP1, so only add a stop when colors match.
    place_line = part(outline, 'Patch · 1 placement · lay fabric', p['placementColor'], 'running', stopAfter=True)
    tack = part(str(inset_path(inkex.Path(outline), p['tackInset'], 'nonzero')), 'Patch · 2 tack-down · trim fabric',
                p['placementColor'], 'running', stopAfter=p['edgeColor'] == p['placementColor'])
    for l in (place_line, tack):
        l.update(stitchLength=2.0, underlay=False)
    return [('body', place_line), ('tackdown', tack), ('edge', edge)]


def pose_of(layers):
    anchor = next((l for l in layers if l.get('component', {}).get('localBox')), None)
    if anchor is None:
        raise ValueError('The original component parts are missing. Add a new component.')
    recipe = anchor['component']
    p = recipe['params']
    bx, by, bw, bh = recipe['localBox']
    sx, sy = anchor['width']/bw, anchor['height']/bh
    a = math.radians(anchor.get('rotation', 0))
    x = (p['width']/2-bx)*sx-anchor['width']/2
    y = (p['height']/2-by)*sy-anchor['height']/2
    if anchor.get('flipX'): x = -x
    if anchor.get('flipY'): y = -y
    return dict(cx=anchor['x']+anchor['width']/2+x*math.cos(a)-y*math.sin(a),
        cy=anchor['y']+anchor['height']/2+x*math.sin(a)+y*math.cos(a),
        rotation=anchor.get('rotation', 0), flipX=bool(anchor.get('flipX')), flipY=bool(anchor.get('flipY')))


def pad_frame(layer, minimum=.2):
    """Keep sub-mm path geometry intact inside a valid native editor frame."""
    for axis,key in [(0,'width'),(1,'height')]:
        size=layer[key]
        if size>=minimum:continue
        factor=size/minimum;layer[key]=minimum
        for contour in layer.get('contours',[]):
            for n in contour['nodes']:
                n['x' if axis==0 else 'y']*=factor
                for handle in ('in','out'):n[handle][axis]*=factor
    return layer


def place(layers, p, pose):
    a = math.radians(pose['rotation'])
    for l in layers:
        x = l['x']+l['width']/2-p['width']/2
        y = l['y']+l['height']/2-p['height']/2
        if pose['flipX']: x = -x
        if pose['flipY']: y = -y
        # A part's own rotation (saved motifs) adds to the pose; mirroring reverses it.
        own = l.get('rotation', 0) * (-1 if pose['flipX'] != pose['flipY'] else 1)
        l.update(x=pose['cx']+x*math.cos(a)-y*math.sin(a)-l['width']/2,
            y=pose['cy']+x*math.sin(a)+y*math.cos(a)-l['height']/2,
            rotation=pose['rotation']+own, flipX=pose['flipX'] != bool(l.get('flipX')), flipY=pose['flipY'] != bool(l.get('flipY')))


def world_path(layer, s):
    source = {**layer, 'visible': True, 'role': 'artwork', 'borderEnabled': False, 'stitch': 'fill', 'smallFillFallback':False,'feather':None}
    if source.get('fillMethod') in ('streamline_fill','wave_fill'):source['fillMethod']='tatami_fill'
    items = geometry(s.build_svg({'version': 1, 'layers': [source]}))
    path = inkex.Path()
    for _, item, _ in items:
        path.extend(item)
    return path


def refresh_area(data, s):
    source = data.get('source')
    if not isinstance(source, dict) or source.get('type') not in ('path', 'ellipse', 'rectangle'):
        raise ValueError('Select a closed native patch shape.')
    border = s.number(data.get('borderWidth', 2), .6, 6, 'Border width')
    gap = s.number(data.get('clearance', .8), 0, 5, 'Content clearance')
    compensation = s.number(data.get('compensation', source.get('pullCompensation', 0)), 0, 1, 'Compensation allowance')
    inset = border/2 + gap + compensation
    shape = path_polygon(world_path(source, s)).buffer(-inset, join_style='round', quad_segs=8)
    if shape.is_empty:
        raise ValueError('The content inset removes this patch. Reduce the edge or gap, or enlarge the shape.')
    result = part(str(polygon_path(shape)), 'Usable inner area · does not sew', '#24b6b0', 'running')
    result.update(role=AREA_ROLE, areaSource=source['id'], areaInset=inset,
        areaSettings=dict(borderWidth=border, clearance=gap, compensation=compensation))
    if source.get('groupId'):
        result['groupId'] = source['groupId']
    pieces = len(shape.geoms) if shape.geom_type == 'MultiPolygon' else 1
    warnings = ['The inset splits into multiple usable regions. Narrow tips are excluded.'] if pieces > 1 else []
    return dict(layers=[result], warnings=warnings, areaMm2=round(shape.area, 2))


def generate(data, s):
    kind = data.get('kind')
    p = settings(kind, data.get('params', {}), s)
    targets = data.get('targets', [])
    if not isinstance(targets, list) or len(targets) > 16:
        raise ValueError('Send one component group with at most 16 parts.')
    if targets:
        if any(l.get('locked') for l in targets):
            raise ValueError('Unlock all component parts before rebuilding.')
        if len({l.get('groupId') for l in targets}) != 1 or not targets[0].get('groupId'):
            raise ValueError('Choose one component group.')
        if any(l.get('component', {}).get('version') != VERSION or l.get('component', {}).get('kind') != kind for l in targets):
            raise ValueError('Select parts from one supported component recipe.')
        group = targets[0]['groupId']
        pose = pose_of(targets)
    else:
        group = uuid.uuid4().hex
        raw = data.get('pose', {})
        pose = dict(cx=s.number(raw.get('cx', 50), -100, 200, 'Center X'),
            cy=s.number(raw.get('cy', 50), -100, 200, 'Center Y'),
            rotation=s.number(raw.get('rotation', 0), -360, 360, 'Rotation'),
            flipX=bool(raw.get('flipX')), flipY=bool(raw.get('flipY')))
    import motifs
    parts = {'patch': patch, 'crescent': crescent, 'mushroom': mushroom, 'branch': branch,
             'motif': lambda p: motifs.parts(p, s)}[kind](p)
    old = {l['component']['part']: l for l in targets}
    layers = []
    for key, l in parts:
        if key in old:
            l['id'] = old[key]['id']
        l['groupId'] = group
        l['component'] = dict(version=VERSION, kind=kind, part=key, params=copy.deepcopy(p),
            localBox=[l['x'], l['y'], l['width'], l['height']])
        layers.append(l)
    place(layers, p, pose)
    for layer in layers:
        if layer.get('merrow'):
            from merrow import cache_artwork
            cache_artwork(layer,s)
    warnings = []
    if kind in ('crescent', 'patch'):
        result = refresh_area(dict(source=layers[0], borderWidth=p['borderWidth'], clearance=p['clearance']), s)
        area = result['layers'][0]
        if 'area' in old:
            area['id'] = old['area']['id']
        # A world-space area has no recipe pose. Use the body as anchor in clients.
        area['component'] = dict(version=VERSION, kind=kind, part='area', params=copy.deepcopy(p))
        layers.insert(1, area)
        warnings.extend(result['warnings'])
    return dict(layers=layers, warnings=warnings, recipe=dict(version=VERSION, kind=kind, params=p))


def check_fit(data, s):
    from footprints import envelope
    area, layers = data.get('area'), data.get('layers')
    if not isinstance(area, dict) or area.get('role') != AREA_ROLE:
        raise ValueError('Choose a usable inner area.')
    if not isinstance(layers, list) or not 1 <= len(layers) <= 30:
        raise ValueError('Check 1–30 artwork parts at once.')
    region = path_polygon(world_path(area, s))
    findings = []
    for l in layers:
        if l.get('role', 'artwork') != 'artwork' or l.get('visible') is False:
            continue
        path = world_path(l, s)
        footprint = envelope(l,path,s)
        outside = footprint.difference(region.buffer(.03))
        if not outside.is_empty:
            findings.append(dict(id=l['id'], name=l.get('name', 'Part'), outsideMm2=round(outside.area, 3)))
    return dict(fits=not findings, findings=findings, checked=len(layers), areaMm2=round(region.area, 2))


def starter(data, s):
    """A reusable composition fixture, not an independent drawing script."""
    patch = generate(dict(kind='crescent', params=data.get('params', {})), s)
    p = patch['recipe']['params']
    w, h = p['width'], p['height']
    if w < 55 or h < 65:
        raise ValueError('The starter assembly needs at least 55 × 65 mm. For a smaller design, add a crescent and individual motifs separately.')
    branch_result = generate(dict(kind='branch', params=dict(width=w*(.28 if p['profile']=='botanical' else .2973), height=h*(.32 if p['profile']=='botanical' else .34),profile=p['profile']),
        pose=dict(cx=50-w*.20, cy=50+h*.295, rotation=-35)), s)
    mushroom_result = generate(dict(kind='mushroom', params=dict(width=w*.28, height=h*.31,profile=p['profile']),
        pose=dict(cx=50-w*(.27 if p['profile']=='botanical' else .24), cy=50+h*.17, rotation=-13)), s)
    # Ground, branch, mushroom, then the cover edge. The guide does not sew.
    edge=next(i for i,l in enumerate(patch['layers']) if l['component']['part'] in ('edge','edge-shadow'))
    layers = patch['layers'][:edge]+branch_result['layers']+mushroom_result['layers']+patch['layers'][edge:]
    area = next(l for l in layers if l.get('role') == AREA_ROLE)
    fit = check_fit(dict(area=area, layers=branch_result['layers']+mushroom_result['layers']), s)
    return dict(layers=layers, warnings=patch['warnings'], fit=fit)


def patch_from_shape(data, s):
    """Turn any closed native shape into a Patch recipe, keeping its position."""
    source = data.get('source')
    if not isinstance(source, dict) or source.get('type') not in ('path', 'ellipse', 'rectangle'):
        raise ValueError('Select one closed shape (path, ellipse or rectangle).')
    shape = path_polygon(world_path(source, s))
    if shape.is_empty or shape.area < 1:
        raise ValueError('The selected shape is not closed or is too small for a patch.')
    x0, y0, x1, y1 = shape.bounds
    local = str(polygon_path(shape).transform(inkex.Transform(translate=(-x0, -y0))))
    params = {**data.get('params', {}), 'shape': 'custom', 'outline': local, 'width': round(x1 - x0, 3), 'height': round(y1 - y0, 3)}
    if params['width'] > 98 or params['height'] > 98:
        raise ValueError('The selected shape is larger than the hoop allows for a patch (98 mm).')
    return generate(dict(kind='patch', params=params, pose=dict(cx=(x0 + x1) / 2, cy=(y0 + y1) / 2)), s)


def operate(data, s):
    action = data.get('action', 'generate')
    if action == 'patch-from-shape': return patch_from_shape(data, s)
    if action == 'generate': return generate(data, s)
    if action == 'refresh-area': return refresh_area(data, s)
    if action == 'check-fit': return check_fit(data, s)
    if action == 'starter': return starter(data, s)
    if action == 'branch-layout':
        from leaf_layout import layout
        params=settings('branch',{**data.get('params',{}),'profile':'botanical'},s)
        curve,leaves=layout(params)
        return dict(params={**params,'stemCurve':curve,'leafMap':leaves})
    if action == 'mushroom-layout':
        from mushroom_layout import editable
        return dict(params=editable(settings('mushroom',{**data.get('params',{}),'profile':'botanical'},s)))
    raise ValueError('Unknown component action.')
