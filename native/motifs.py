"""Motif library: save any selected shapes as a reusable, scalable motif.

Saved motifs work like the built-in recipes: the Patches dialog adds them, and
scenes arrange them along a guide inside a patch's inner area.
Geometry is stored un-rotated in millimeters with the motif's box at (0, 0).
"""
import copy
import json
import time
import uuid

MAX_PARTS = 40
SHAPES = ('path', 'rectangle', 'ellipse')
# Links to the source design are dropped; geometry and stitch settings are kept.
IDENTITY_KEYS = {'id', 'groupId', 'component', 'sceneBinding', 'link', 'linkedHelper', 'locked', 'helperTarget'}


def folder(s):
    d = s.DATA / 'motifs'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(key, s):
    return folder(s) / (s.safe_id(key) + '.json')


def load(key, s):
    p = _path(key, s)
    if not p.exists():
        raise ValueError('That saved motif no longer exists.')
    return json.loads(p.read_text(encoding='utf-8'))


def listing(s):
    out = []
    for f in sorted(folder(s).glob('*.json'), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            m = json.loads(f.read_text(encoding='utf-8'))
            out.append({k: m[k] for k in ('id', 'name', 'width', 'height')} | {'parts': len(m['layers'])})
        except (ValueError, KeyError, OSError):
            continue
    return out


def save(data, s):
    from components import world_path
    layers = data.get('layers')
    name = str(data.get('name') or '').strip()[:80]
    if not name:
        raise ValueError('Name the motif.')
    if not isinstance(layers, list) or not 1 <= len(layers) <= MAX_PARTS:
        raise ValueError(f'Select 1–{MAX_PARTS} shapes to save as a motif.')
    if any(not isinstance(l, dict) or l.get('type') not in SHAPES or l.get('role', 'artwork') != 'artwork' or l.get('visible') is False for l in layers):
        raise ValueError('Motifs can contain visible paths, rectangles and ellipses. Separate lettering or imported SVG paths first.')
    parts, boxes = [], []
    for l in layers:
        # Bounds come from the real (rotated) outline; the part itself is kept
        # exactly as drawn (satin rails, rotation, stitch settings) and only moved.
        box = world_path(l, s).bounding_box()
        if box is None or not float(box.width) and not float(box.height):
            continue
        parts.append({k: copy.deepcopy(v) for k, v in l.items() if k not in IDENTITY_KEYS})
        boxes.append((float(box.left), float(box.top), float(box.right), float(box.bottom)))
    if not parts:
        raise ValueError('The selection has no drawable geometry.')
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    if x1 - x0 < .5 or y1 - y0 < .5:
        raise ValueError('The motif is too small to reuse.')
    for p in parts:
        p['x'] -= x0
        p['y'] -= y0
        p.pop('id', None)
    key = uuid.uuid4().hex
    motif = dict(id=key, name=name, width=round(x1 - x0, 4), height=round(y1 - y0, 4), layers=parts, created=time.time())
    s.write_atomic(_path(key, s), motif)
    return {k: motif[k] for k in ('id', 'name', 'width', 'height')} | {'parts': len(parts)}


def delete(data, s):
    p = _path(data.get('id', ''), s)
    if p.exists():
        p.unlink()
    return {'deleted': True}


def settings(raw, s):
    """Recipe parameters for a saved motif: which motif and its width (height follows)."""
    m = load(raw.get('motif', ''), s)
    width = s.number(raw.get('width', m['width']), 2, 98, 'Motif width')
    height = width * m['height'] / m['width']
    if height > 98:
        raise ValueError('At this width the motif is taller than the hoop. Reduce the width.')
    return dict(motif=m['id'], name=m['name'], width=width, height=height)


def parts(p, s):
    """Layers for the generic recipe pipeline, scaled uniformly to p['width']."""
    m = load(p['motif'], s)
    k = p['width'] / m['width']
    out = []
    for i, l in enumerate(m['layers']):
        l = copy.deepcopy(l)
        for key in ('x', 'y', 'width', 'height'):
            l[key] *= k
        l['name'] = f"{m['name']} · {l.get('name', 'part')}"
        l['id'] = uuid.uuid4().hex
        out.append((f'p{i}', l))
    return out


def operate(data, s):
    action = data.get('action')
    if action == 'list': return listing(s)
    if action == 'save': return save(data, s)
    if action == 'delete': return delete(data, s)
    raise ValueError('Unknown motif action.')
