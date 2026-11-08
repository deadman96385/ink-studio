"""Sewing-quality findings for the design check: cut/restart load and too-small detail.

Calibrated on the crescent mushroom patch (27k stitches, 258 trims), which
frayed on the PP1 from repeated automatic trims, versus its simplified
version (68 trims), which did not use most of the cuts.
"""
import math

# Thresholds are deliberately conservative warnings, not errors.
TRIMS_WARN = 80                 # absolute trims in one design
TRIMS_PER_1000_WARN = 6.0       # roughly one cut per ~170 stitches
ISLAND_STITCHES = 15            # a run between cuts this short is a "tiny island"
ISLANDS_WARN = 12
MIN_FILL_MM = 2.0               # fills narrower than this rarely stitch cleanly
MIN_TEXT_LINE_MM = 4.0          # lettering below ~4 mm per line loses legibility
MIN_SATIN_MM = 0.8              # narrower satin columns pile up / break thread


def islands(commands, types):
    """Stitch runs separated by trims, stops or color changes."""
    cut = {types['trim'], types['stop'], types['color']}
    runs, current, start = [], 0, None
    for x, y, c in commands:
        if c == types['stitch']:
            current += 1
            if start is None:
                start = (x, y)
            end = (x, y)
        elif c in cut and current:
            runs.append((current, start, end)); current, start = 0, None
    if current:
        runs.append((current, start, end))
    return runs


def _finding(message, description, layer=None, position=None, kind='sewing'):
    f = {'severity': 'warning', 'kind': kind, 'message': message, 'description': description}
    if layer:
        f['layerId'] = layer['id']
    if position:
        f['position'] = position
    return f


def layer_findings(project):
    out = []
    for l in project.get('layers', []):
        if l.get('visible', True) is False or l.get('role', 'artwork') != 'artwork' or l.get('type') == 'image':
            continue
        name = l.get('name') or 'Layer'
        w, h = float(l.get('width', 0)), float(l.get('height', 0))
        center = [float(l.get('x', 0)) + w / 2, float(l.get('y', 0)) + h / 2]
        if l.get('type') == 'text':
            lines = max(1, len(str((l.get('lettering') or {}).get('text', '')).splitlines()))
            per_line = h / lines
            if 0 < per_line < MIN_TEXT_LINE_MM:
                out.append(_finding(f'{name}: lettering is only {per_line:.1f} mm per line',
                                    f'Text under {MIN_TEXT_LINE_MM:g} mm tall usually closes up on the PP1. Enlarge it or use a font marked "Tiny".',
                                    l, center, 'small-detail'))
        elif l.get('stitch') == 'fill' and l.get('type') in ('rectangle', 'ellipse', 'path') and 0 < min(w, h) < MIN_FILL_MM:
            out.append(_finding(f'{name}: fill is only {min(w, h):.1f} mm across',
                                f'Fills under {MIN_FILL_MM:g} mm wide sew as a lump with a cut on each side. Use a satin or running stitch, or merge it with a neighbour.',
                                l, center, 'small-detail'))
        elif l.get('stitch') == 'satin' and l.get('type') in ('rectangle', 'ellipse') and 0 < min(w, h) < MIN_SATIN_MM:
            out.append(_finding(f'{name}: satin is only {min(w, h):.1f} mm wide',
                                f'Satin narrower than {MIN_SATIN_MM:g} mm piles up and can break thread. Use a running or bean stitch.',
                                l, center, 'small-detail'))
    return out


def analyze(project, preview):
    """Return (findings, stats). `preview` must include commands."""
    findings = []
    stitches, trims = preview['stitches'], preview['trims']
    per_1000 = trims * 1000 / stitches if stitches else 0
    runs = islands(preview.get('commands', []), preview.get('commandTypes', {})) if preview.get('commands') else []
    tiny = [r for r in runs if r[0] <= ISLAND_STITCHES]
    stats = {'trims': trims, 'stitches': stitches, 'trimsPer1000': round(per_1000, 1), 'islands': len(runs), 'tinyIslands': len(tiny),
             'limits': {'trims': TRIMS_WARN, 'trimsPer1000': TRIMS_PER_1000_WARN, 'tinyIslands': ISLANDS_WARN}}
    if trims > TRIMS_WARN or per_1000 > TRIMS_PER_1000_WARN:
        findings.append(_finding(
            f'{trims} thread cuts ({per_1000:.1f} per 1,000 stitches)',
            'Many automatic trims make the PP1 cut and restart the thread repeatedly, which can fray it. '
            'Try Auto-route running stitches or satins, group nearby small pieces in the same color, raise '
            '"Join jumps shorter than" in Embroidery preferences so short moves stay as travel stitches, or simplify tiny details.'))
    if len(tiny) > ISLANDS_WARN:
        x, y = tiny[0][1]
        findings.append(_finding(
            f'{len(tiny)} tiny sections need their own cut and restart',
            f'Each section has {ISLAND_STITCHES} stitches or fewer between cuts (common with small leaves, spots or separate letters). '
            'Merge or remove small pieces, or route them together, to cut fewer times.', position=[x, y]))
    small = layer_findings(project)
    stats['smallDetails'] = len(small)
    findings += summarize(small)
    return findings, stats


def summarize(small, keep=3):
    """Show a few small-detail findings individually, then one summary."""
    if len(small) <= keep + 1:
        return small
    rest = small[keep:]
    names = [f['message'].split(':')[0] for f in rest]
    listed = ', '.join(names[:6]) + (f' and {len(names) - 6} more' if len(names) > 6 else '')
    return small[:keep] + [{'severity': 'warning', 'kind': 'small-detail', 'message': f'{len(rest)} more layers are very small for their stitch type',
                            'description': 'Also check: ' + listed + '. Small fills and thin satins stitch poorly and add cuts.',
                            'layerId': rest[0].get('layerId'), 'position': rest[0].get('position'), 'layerIds': [f.get('layerId') for f in rest]}]
