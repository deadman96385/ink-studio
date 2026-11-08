"""Upgrade SVGs saved by older Ink/Stitch releases before import.

Mirrors Ink/Stitch's own rules (lib/update.py): a file without a version but
with Ink/Stitch attributes is version 0; files without any Ink/Stitch data
need no update. The installed update_svg extension does the actual upgrade.
"""
import tempfile
from lxml import etree as ET
from pathlib import Path

CURRENT = 4
STITCH = 'http://inkstitch.org/namespace'
HISTORY = {0: 'before Ink/Stitch 3.0', 1: 'Ink/Stitch 3.0', 2: 'Ink/Stitch 3.1', 3: 'Ink/Stitch 3.2', 4: 'Ink/Stitch 3.3'}


def detect(root):
    """Return (file_version, has_inkstitch_data)."""
    found = root.xpath("//*[local-name()='inkstitch_svg_version']/text()")
    try:
        version = int(str(found[0]).strip()) if found else 0
    except ValueError:
        version = 0
    data = bool(root.xpath("//*[namespace-uri()=$ns or @*[namespace-uri()=$ns] or @*[starts-with(name(),'embroider_')]]", ns=STITCH))
    return version, data


def choose(root, requested='auto'):
    """Version to update from, or None when no update is needed."""
    version, data = detect(root)
    if requested not in (None, 'auto'):
        if type(requested) is not int or not 0 <= requested < CURRENT:
            raise ValueError('Choose an Ink/Stitch file version from 0 to 3, or automatic.')
        return requested
    # Unversioned files are only upgraded on request: desktop asks first, and
    # hand-made SVGs with Ink/Stitch attributes are usually already current.
    if not data or version >= CURRENT or not found_version(root):
        return None
    return version


def found_version(root):
    return bool(root.xpath("//*[local-name()='inkstitch_svg_version']"))


def offer(root):
    """True when an unversioned file has Ink/Stitch data the user may want upgraded."""
    version, data = detect(root)
    return data and not found_version(root)


def upgrade(raw, s, requested='auto'):
    """Return (svg_bytes, info). info is None when the file was already current."""
    root = s.xml(raw)
    start = choose(root, requested)
    if start is None:
        return raw, ({'offer': True, 'from': 0, 'label': HISTORY[0], 'to': CURRENT} if requested in (None, 'auto') and offer(root) else None)
    # Stamp the current version so the engine's automatic check (which shows a
    # confirmation window for unversioned files) is skipped; update_svg then
    # resets the version to `start` and upgrades without asking, like desktop.
    for old in root.xpath("//*[local-name()='inkstitch_svg_version']"):
        old.getparent().remove(old)
    meta = root.find('{http://www.w3.org/2000/svg}metadata')
    if meta is None:
        meta = ET.Element('{http://www.w3.org/2000/svg}metadata')
        root.insert(0, meta)
    ET.SubElement(meta, '{%s}inkstitch_svg_version' % STITCH).text = str(CURRENT)
    with s.ENGINE_LOCK, tempfile.TemporaryDirectory(prefix='svg-update-') as tmp:
        path = Path(tmp) / 'legacy.svg'
        path.write_bytes(ET.tostring(root))
        out = s.run([s.ENGINE, '--extension=update_svg', '--update-from=' + str(start), str(path)], 240, headless=True)
    if not out.strip():
        raise ValueError('Ink/Stitch could not update this older SVG.')
    return out, {'from': start, 'label': HISTORY[start], 'to': CURRENT}
