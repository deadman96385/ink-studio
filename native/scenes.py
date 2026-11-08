"""Curve-attached, constrained scene composition over native component paths.

The recipe lives on an editable non-sewing guide. Layout is deterministic and
returns a proposal; saving/applying belongs to the normal project transaction.
"""
import copy
import hashlib
import math
import uuid
from bisect import bisect_left

from shapely.geometry import LineString
from shapely.ops import unary_union
from shapely.affinity import affine_transform

from components import (AREA_ROLE, generate, part, place, path_polygon, world_path,
                        flattened, pose_of)
from digitizing import inkex, from_path, path_contours
from limits import MAX_LAYERS
from footprints import envelope, is_satin

GUIDE_ROLE = 'scene-guide'
VERSION = 1


def order_paths(layers, shapes):
    """Batch independent colors while retaining every overlap and part order."""
    count = len(layers)
    edges = [set() for _ in layers]
    previous = {}
    for i, layer in enumerate(layers):
        group = layer['groupId']
        if layer.get('paintStage') is not None:
            for j in range(i):
                if layers[j]['groupId']==group and layers[j].get('paintStage',0)<layer['paintStage']:edges[j].add(i)
        elif group in previous:
            edges[previous[group]].add(i)
        previous[group] = i
        for j in range(i):
            if layer['color'] != layers[j]['color'] and shapes[layer['id']].intersection(shapes[layers[j]['id']]).area > .00001:
                edges[j].add(i)
    incoming = [0]*count
    for following in edges:
        for i in following: incoming[i] += 1
    available = {i for i in range(count) if not incoming[i]}
    ordered, last = [], None
    while available:
        choices = sorted(available)
        matching = [i for i in choices if layers[i]['color'] == last]
        if not matching:
            colors = {layers[i]['color'] for i in choices}
            color = max(colors, key=lambda c: (sum(layers[i]['color'] == c for i in choices), -min(i for i in choices if layers[i]['color'] == c)))
            matching = [i for i in choices if layers[i]['color'] == color]
        i = matching[0]
        available.remove(i)
        ordered.append(layers[i])
        last = layers[i]['color']
        for j in edges[i]:
            incoming[j] -= 1
            if not incoming[j]: available.add(j)
    return ordered


def guide_samples(guide, s):
    contours = path_contours(world_path(guide, s))
    if len(contours) != 1 or contours[0]['closed']:
        raise ValueError('Use one open guide curve. Separate closed loops and subpaths first.')
    nodes = contours[0]['nodes']
    if not 2 <= len(nodes) <= 24:
        raise ValueError('Use 2–24 nodes in a scene guide.')
    points = flattened(contours[0], .015)
    samples = [(0., points[0])]
    for p in points[1:]:
        distance = math.dist(samples[-1][1], p)
        if distance > 1e-8:
            samples.append((samples[-1][0]+distance, p))
    if samples[-1][0] < 2:
        raise ValueError('The guide must be at least 2 mm long.')
    return samples


def along(samples, t):
    distance = t*samples[-1][0]
    i = max(1, min(len(samples)-1, bisect_left([a[0] for a in samples], distance)))
    d0, p0 = samples[i-1]
    d1, p1 = samples[i]
    f = (distance-d0)/(d1-d0)
    x, y = [p0[k]+(p1[k]-p0[k])*f for k in (0, 1)]
    # Average the local direction across a short distance to avoid polygon seams.
    start, end = max(0, i-2), min(len(samples)-1, i+1)
    a, b = samples[start][1], samples[end][1]
    length = math.dist(a, b) or 1
    return x, y, (b[0]-a[0])/length, (b[1]-a[1])/length


def footprint(layer, s):
    return envelope(layer,world_path(layer,s),s)


def item_settings(raw, s):
    if not isinstance(raw, dict):
        raise ValueError('Invalid scene motif.')
    kind = raw.get('kind')
    if kind not in ('mushroom', 'branch', 'motif'):
        raise ValueError('Scene motifs must be mushrooms, branches or saved motifs.')
    key = s.safe_id(raw.get('id'))
    return dict(id=key, kind=kind, name=str(raw.get('name', kind.title()))[:80],
        t=s.number(raw.get('t', .5), 0, 1, 'Position along guide'),
        offset=s.number(raw.get('offset', 0), -30, 30, 'Offset from guide'),
        angle=s.number(raw.get('angle', 0), -180, 180, 'Motif rotation offset'),
        follow=s.number(raw.get('follow', .5), 0, 1, 'Follow guide direction'),
        scale=s.number(raw.get('scale', 1), .2, 2, 'Motif scale'),
        autoFit=bool(raw.get('autoFit', True)), pinned=bool(raw.get('pinned', False)),
        flipX=bool(raw.get('flipX', False)), params=copy.deepcopy(raw.get('params', {})))


def attachment_pose(params, sample, item, scale, offset):
    w, h = params['width']*scale, params['height']*scale
    x, y, tx, ty = sample
    theta = (math.degrees(math.atan2(ty, tx))-90)*item['follow']+item['angle']
    a = math.radians(theta)
    # Attach the base of the stem/branch, rather than its bounding-box center.
    anchor_x, anchor_y = x-ty*offset, y+tx*offset
    ax=params.get('bend',0)*w if params.get('profile')=='botanical' and 'stemWidth' in params else 0
    ay=h/2
    if params.get('profile')=='botanical' and params.get('stemRails'):
        root=[sum(r[-1][axis] for r in params['stemRails'])/2 for axis in (0,1)]
        ax=(root[0]-.5)*w;ay=(root[1]-.5)*h
    if params.get('profile')=='botanical' and params.get('leafMap') and params.get('stemCurve'):
        root=params['stemCurve'][0];ax=(root[0]-.5)*w;ay=(root[1]-.5)*h
    if item['flipX']:ax=-ax
    pose = dict(cx=anchor_x+ay*math.sin(a)-ax*math.cos(a), cy=anchor_y-ay*math.cos(a)-ax*math.sin(a),
                rotation=theta, flipX=item['flipX'], flipY=False)
    return pose, (anchor_x, anchor_y)


def attach(canonical, params, sample, item, scale, offset):
    layers = copy.deepcopy(canonical)
    w, h = params['width']*scale, params['height']*scale
    for l in layers:
        for key in ('x', 'y', 'width', 'height'):
            l[key] *= scale
        # Tiny dots work as a bean-stitched ring instead of an undersized fill.
        if l['component']['part'] == 'spots' and w < 8 and not l.get('smallFillFallback'):
            l.update(stitch='bean', stitchLength=.5, underlay=False)
    pose, anchor = attachment_pose(params, sample, item, scale, offset)
    from components import pad_frame
    for layer in layers:pad_frame(layer)
    place(layers, dict(width=w, height=h), pose)
    return layers, pose, anchor


def local_geometry(layers, s):
    shapes = []
    for l in layers:
        path = world_path(l, s)
        line = unary_union([LineString(flattened(c, .015)) for c in path_contours(path)])
        if is_satin(l):
            shape,halo=envelope(l,path,s),0
        elif l['stitch'] == 'fill':
            shape, halo = path_polygon(path), float(l.get('pullCompensation', 0))
        else:
            shape, halo = line, .225
        shapes.append((shape, halo, line if l['component']['part'] == 'spots' and not l.get('smallFillFallback') else None))
    return shapes


def transformed_geometry(shapes, params, pose, scale):
    a = math.radians(pose['rotation'])
    c, sn = math.cos(a), math.sin(a)
    flip = -1 if pose['flipX'] else 1
    aa, bb, dd, ee = scale*flip*c, -scale*sn, scale*flip*sn, scale*c
    matrix = [aa, bb, dd, ee, pose['cx']-aa*params['width']/2-bb*params['height']/2,
              pose['cy']-dd*params['width']/2-ee*params['height']/2]
    parts = []
    for shape, halo, dot_line in shapes:
        if dot_line is not None and params['width']*scale < 8:
            shape, halo = dot_line, .225
        parts.append(affine_transform(shape, matrix).buffer(halo))
    return unary_union(parts)


def layout(data, s):
    project, guide = data.get('project'), copy.deepcopy(data.get('guide'))
    if not isinstance(project, dict) or project.get('version') != 1:
        raise ValueError('Open a native project first.')
    if not isinstance(guide, dict) or guide.get('type') != 'path' or guide.get('role') != GUIDE_ROLE:
        raise ValueError('Choose an editable scene guide.')
    s.safe_id(guide.get('id'))
    recipe = guide.get('scene', {})
    if recipe.get('knockoutBackground'):
        recipe['groundUnderlap']=s.number(recipe.get('groundUnderlap',.25),.1,.8,'Background underlap')
    if recipe.get('version') != VERSION:
        raise ValueError('This scene recipe version is not supported.')
    area = next((l for l in project.get('layers', []) if l['id'] == recipe.get('areaId') and l.get('role') == AREA_ROLE), None)
    if not area:
        raise ValueError('The scene’s usable inner area is missing. Choose an existing inner area.')
    if guide.get('locked'):
        raise ValueError('Unlock the scene guide before reflowing it.')
    items = recipe.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 24:
        raise ValueError('Use 1–24 motifs in one scene.')
    items = [item_settings(i, s) for i in items]
    if len({i['id'] for i in items}) != len(items):
        raise ValueError('Scene motif identifiers must be unique.')
    region = path_polygon(world_path(area, s))
    allowed = region.buffer(.025)
    samples = guide_samples(guide, s)
    old = [l for l in project['layers'] if l.get('sceneBinding', {}).get('guideId') == guide['id']]
    if any(l.get('locked') for l in old):
        raise ValueError('Unlock the attached parts before rebuilding this scene. Pin a motif to keep its geometry.')
    generated, findings, placements, shapes_by_id = [], [], [], {}
    for item in items:
        sample = along(samples, item['t'])
        canonical = generate(dict(kind=item['kind'], params=item['params'], pose=dict(cx=0, cy=0)), s)
        params = canonical['recipe']['params']
        canonical = canonical['layers']
        # Recover generator-local coordinates from the initial centered pose.
        for l in canonical:
            l['x'] += params['width']/2
            l['y'] += params['height']/2
        pinned = [copy.deepcopy(l) for l in old if l.get('sceneBinding', {}).get('itemId') == item['id']]
        if item['pinned'] and pinned:
            paths, scale, offset, pose, anchor = pinned, item['scale'], item['offset'], None, None
        else:
            scales = [item['scale']*f for f in ([1, .95, .9, .85, .8, .75, .7, .65, .6] if item['autoFit'] else [1])]
            offsets = [item['offset']+d for d in ([0, .8, -.8, 1.6, -1.6, 2.4, -2.4] if item['autoFit'] else [0])]
            shapes = local_geometry(canonical, s)
            best, best_outside = None, float('inf')
            for scale in scales:
                for offset in offsets:
                    pose, anchor = attachment_pose(params, sample, item, scale, offset)
                    outside = transformed_geometry(shapes, params, pose, scale).buffer(.015).difference(allowed).area
                    if outside < best_outside:
                        best, best_outside = (scale, offset), outside
                    if outside < .00001:
                        break
                if best_outside < .00001:
                    break
            scale, offset = best
            paths, pose, anchor = attach(canonical, params, sample, item, scale, offset)
        actual_shapes = [footprint(l, s) for l in paths]
        best_outside = unary_union(actual_shapes).difference(allowed).area
        if best_outside >= .00001:
            findings.append(dict(itemId=item['id'], name=item['name'], outsideMm2=round(best_outside, 3)))
        group = pinned[0].get('groupId') if pinned else None
        group = group or 'scene-'+hashlib.sha256((guide['id']+':'+item['id']).encode()).hexdigest()[:24]
        prior = {l['component']['part']: l for l in pinned}
        for l, shape in zip(paths, actual_shapes):
            key = l['component']['part']
            l['id'] = prior[key]['id'] if key in prior else group+'-'+key
            l['groupId'] = group
            l['name'] = item['name']+' · '+key.replace('-', ' ')
            l['sceneBinding'] = dict(guideId=guide['id'], itemId=item['id'])
            shapes_by_id[l['id']] = shape
        generated.extend(paths)
        placements.append(dict(itemId=item['id'], name=item['name'], scale=round(scale, 5),
            offset=round(offset, 3), adjusted=abs(scale-item['scale'])>.00001 or abs(offset-item['offset'])>.00001,
            anchor=list(anchor) if anchor else [sample[0], sample[1]], rotation=pose['rotation'] if pose else None,
            fits=best_outside < .00001))
    guide['scene'] = {**recipe,'version':VERSION,'areaId':area['id'],'items':items}
    guide['name'] = str(guide.get('name', 'Scene · flow guide'))[:100]
    guide.pop('component', None)
    guide.pop('groupId', None)
    # All foliage precedes mushrooms, preserving each motif's internal part order.
    kinds = {i['id']: i['kind'] for i in items}
    # Saved motifs sew between foliage and mushrooms (background → middle → foreground).
    foliage = [l for l in generated if kinds[l['sceneBinding']['itemId']] == 'branch']
    saved = [l for l in generated if kinds[l['sceneBinding']['itemId']] == 'motif']
    mushrooms = [l for l in generated if kinds[l['sceneBinding']['itemId']] == 'mushroom']
    generated = order_paths(foliage, shapes_by_id)+order_paths(saved, shapes_by_id)+order_paths(mushrooms, shapes_by_id)
    old_ids = {l['id'] for l in old} | {guide['id']}
    layers = [copy.deepcopy(l) for l in project['layers'] if l['id'] not in old_ids]
    edge = next((n for n, l in enumerate(layers) if l.get('component', {}).get('part') in ('edge','edge-shadow') and l.get('groupId') == area.get('groupId')), len(layers))
    vines=[]
    if recipe.get('sewVine'):
        vine=from_path(world_path(guide,s),dict(name='Scene · continuous vine',color='#3e702b',stitch='bean',
            stitchLength=1.4,spacing=.4,underlay=False,trimAfter=False))
        vine.update(id='vine-'+guide['id'],groupId='vine-'+guide['id'],role='artwork',
            sceneBinding=dict(guideId=guide['id'],itemId='__vine__'),component=dict(kind='vine',part='stem',version=1,params={}))
        vines=[vine]
        outside=footprint(vine,s).difference(allowed).area
        if outside>.00001:findings.append(dict(itemId='__vine__',name='Continuous vine',outsideMm2=round(outside,3)))
    layers[edge:edge] = [guide, *vines, *generated]
    if len(layers) > MAX_LAYERS:
        raise ValueError(f'This scene would make {len(layers)} layers; the limit is {MAX_LAYERS}. Remove or simplify a motif.')
    return dict(layers=layers, guide=guide, placements=placements,
        fits=not findings, findings=findings, count=len(items), guideLengthMm=round(samples[-1][0], 2),
        partCount=len(generated)+len(vines), layerCount=len(layers))


def preset(data, s):
    project, area_id = data.get('project'), data.get('areaId')
    if not isinstance(project, dict):
        raise ValueError('Open a patch project first.')
    area = next((l for l in project.get('layers', []) if l['id'] == area_id and l.get('role') == AREA_ROLE), None)
    if not area:
        raise ValueError('Choose a usable inner area.')
    return any_preset(project, area, data, s)


def any_preset(project, area, data, s):
    """A gentle S-curve across any inner area with an alternating mix of motifs.
    `kinds` picks the mix (mushroom, branch, motif); `motif` names a saved motif."""
    region = path_polygon(world_path(area, s))
    x0, y0, x1, y1 = region.bounds
    w, h = x1 - x0, y1 - y0
    small = min(w, h)
    if small < 12:
        raise ValueError('This inner area is too small for a scene. Enlarge the patch or reduce its border.')
    d = (f'M{x0+w*.14},{y1-h*.22} C{x0+w*.34},{y1-h*.02} {x0+w*.40},{y0+h*.50} {x0+w*.52},{y0+h*.48} '
         f'C{x0+w*.66},{y0+h*.46} {x0+w*.66},{y0+h*.04} {x1-w*.14},{y0+h*.22}')
    guide = part(d, 'Scene · flow guide', '#d48e40', 'running')
    existing = next((l for l in project['layers'] if l.get('role') == GUIDE_ROLE and l.get('scene', {}).get('areaId') == area['id']), None)
    guide.update(id=existing['id'] if existing else uuid.uuid4().hex, role=GUIDE_ROLE)
    kinds = data.get('kinds') or (['branch', 'motif', 'mushroom', 'motif', 'branch'] if data.get('motif') else ['branch', 'mushroom', 'branch', 'mushroom', 'branch'])
    if not isinstance(kinds, list) or not 1 <= len(kinds) <= 12 or any(k not in ('mushroom', 'branch', 'motif') for k in kinds):
        raise ValueError('Choose 1–12 scene motifs: mushroom, branch or motif.')
    if 'motif' in kinds and not data.get('motif'):
        raise ValueError('Choose a saved motif for this scene.')
    items = []
    for n, kind in enumerate(kinds):
        t = .12 + .76 * (n + .5) / len(kinds)  # keep motifs off the guide's ends, near the border
        if kind == 'mushroom':
            params = dict(width=small * .2, height=small * .28, spots=3, bend=.08 if n % 2 else -.08)
        elif kind == 'branch':
            params = dict(width=small * .16, height=small * .28, pairs=3, bend=.12 if n % 2 else -.12)
        else:
            params = dict(motif=data['motif'], width=small * .22)
        items.append(dict(id='motif-' + str(n + 1), kind=kind, name=f'{"Motif" if kind == "motif" else kind.title()} {n + 1}',
                          t=t, offset=small * (.06 if n % 2 else -.06), angle=0, follow=.5, scale=1, params=params, autoFit=True))
    guide['scene'] = dict(version=VERSION, areaId=area['id'], items=items, style='any')
    return dict(guide=guide)


def operate(data, s):
    if data.get('action') == 'simplify':
        from simple_sewing import simplify_guide
        guide=data.get('guide')
        if not isinstance(guide,dict) or guide.get('role')!=GUIDE_ROLE:raise ValueError('Choose a scene guide to simplify.')
        return simplify_guide(guide,s)
    if data.get('action') == 'preset':
        return preset(data, s)
    if data.get('action', 'layout') == 'layout':
        return layout(data, s)
    raise ValueError('Choose a scene preset or layout operation.')
