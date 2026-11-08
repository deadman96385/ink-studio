"""End-to-end engine regression checks, against a running native service.

Uses real Ink/Stitch jobs and reads PES files independently with pystitch.
Run inside the native container: python /native/verify_native.py
"""
from verification import DATA, BASE as VERIFY_BASE
import copy
import json
from pathlib import Path
import time
import urllib.request
import urllib.error
import uuid
from lxml import etree as ET
import pystitch
from preferences import FACTORY

BASE=VERIFY_BASE
STITCH = 'http://inkstitch.org/namespace'
SVG = 'http://www.w3.org/2000/svg'


def api(path, data=None):
    payload = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(BASE + path, data=payload,
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def export(project, expect_error=None):
    deadline = time.monotonic() + 240
    while True:
        try:
            job=api('/api/export',{'project':project})
            break
        except urllib.error.HTTPError as e:
            if e.code!=429 or time.monotonic()>=deadline:raise
            time.sleep(1)
    while time.monotonic() < deadline:
        state = api('/api/jobs/' + job['id'])
        if state['state'] == 'error':
            assert expect_error and expect_error in state['message'], state
            return state
        if state['state'] == 'done':
            assert not expect_error, state
            return state['result']
        time.sleep(.5)
    raise TimeoutError('Export did not finish.')


def rectangle(**props):
    return {'id': str(uuid.uuid4()), 'type': 'rectangle', 'name': 'Background', 'x': 15, 'y': 20,
            'width': 70, 'height': 60, 'rotation': 0, 'radius': 3, 'color': '#d4ac59',
            'stitch': 'fill', 'spacing': .4, 'angle': 45, 'stitchLength': 3, 'underlay': True, **props}


def main():
    assert api('/api/health')['ok']
    font = {'font': 'medium_font', 'text': 'Test\nStudio', 'scale': 80,
            'align': 'center', 'lineSpacing': 2, 'letterSpacing': 0}
    blocks = {}
    for align in ('left', 'center', 'right'):
        r = api('/api/lettering', {**font, 'align': align})
        root = ET.fromstring(r['svg'].encode())
        lines = root.findall(f'.//{{{SVG}}}g[@{{{STITCH}}}letter-group="line"]')
        assert len(lines) == 2, len(lines)
        settings = json.loads(root.find(f'.//{{{SVG}}}g[@{{{STITCH}}}lettering]').get(f'{{{STITCH}}}lettering'))
        assert settings['text'] == 'Test\nStudio' and settings['text_align'] == ('left','center','right').index(align)
        assert r['width'] > 40 and r['height'] > 25 and r['preview']['stitches'] > 1000
        blocks[align] = r
    r0 = api('/api/lettering', {**font, 'lineSpacing': 0})
    r = blocks['center']
    assert abs((r['height'] - r0['height']) - 2) < .1, (r['height'], r0['height'])
    text_layer = {'id': str(uuid.uuid4()), 'type': 'text', 'name': 'Test / Studio', 'x': (100-r['width'])/2,
                  'y': (100-r['height'])/2, 'width': r['width'], 'height': r['height'], 'rotation': 0,
                  'lettering': r['settings'], 'color': '#203f38'}
    project = {'version': 1, 'id': 'native-engine-verification', 'name': 'Multiline engine verification',
               'fabric': '#faf7f0', 'grid': True, 'snap': True, 'embroiderySettings':dict(FACTORY), 'layers': [rectangle(), text_layer]}
    api('/api/save', {'project': project})
    assert api('/api/projects/' + project['id']) == project
    result = export(project)
    path = (DATA / 'exports') / result['pes'].split('/')[-1]
    pattern = pystitch.read(str(path))
    b = pattern.bounds()
    assert abs((b[2]-b[0])/10 - 70) < .2 and abs((b[3]-b[1])/10 - 60) < .2, b
    assert len(pattern.threadlist) == 2
    assert [t.hex_color() for t in pattern.threadlist] == ['#d4ac59', '#203f38']
    svg = (path.with_suffix('.svg')).read_text()
    assert 'row_spacing_mm="0.4"' in svg and 'angle="45.0"' in svg
    assert 'fill_underlay="True"' in svg
    # Fabric preview color never produces embroidery.
    preview_only = copy.deepcopy(project); preview_only['fabric'] = '#ff00ff'
    result2 = export(preview_only)
    assert result2['preview']['stitches'] == result['preview']['stitches']
    assert result2['preview']['threads'] == result['preview']['threads']
    # Changing fill density must alter actual stitches, not just UI state.
    sparse = copy.deepcopy(project); sparse['layers'][0]['spacing'] = .8
    sparse_result = export(sparse)
    assert sparse_result['preview']['stitches'] < result['preview']['stitches']
    outside = copy.deepcopy(project); outside['layers'][0]['x'] = 60
    export(outside, 'outside')
    original = rectangle(x=35,y=35,width=30,height=20,radius=0,underlay=False,stitch='running')
    modes = {}
    for mode in ('running','bean','zigzag'):
        simple = {**project,'layers':[{**original,'stitch':mode}]}
        modes[mode] = export(simple)['preview']['stitches']
    assert modes['bean'] > modes['running'] * 2, modes
    assert modes['zigzag'] > modes['running'], modes
    # Plain vector import stays at physical millimeter scale.
    imported = api('/api/import', {'name':'test.svg','svg':'<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="20mm" viewBox="0 0 40 20"><path d="M0 0 H40 V20 H0Z" fill="#416580"/></svg>'})
    assert abs(imported['width']-40)<.01 and abs(imported['height']-20)<.01, imported
    imp_layer = {**rectangle(x=30,y=40,width=40,height=20),'type':'import','asset':imported['key'],'stitch':'original'}
    imported_result = export({**project,'layers':[imp_layer]})
    assert imported_result['preview']['width'] == 40
    backup_path = (DATA / 'exports') / imported_result['project'].split('/')[-1]
    backup = json.loads(backup_path.read_text())
    assert len(backup['embeddedAssets']) == 1
    restored = api('/api/restore', {'project': backup})
    restored_result = export(restored)
    assert restored_result['preview']['width'] == 40
    assert restored_result['preview']['height'] == 20
    for bad in ('<svg xmlns="http://www.w3.org/2000/svg"><path onclick="alert(1)" d="M0 0H1V1Z"/></svg>',
                '<!DOCTYPE svg [<!ENTITY a SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>'):
        try:
            api('/api/import', {'svg':bad})
        except urllib.error.HTTPError as e:
            assert e.code == 400
        else:
            raise AssertionError('Unsafe SVG accepted')
    report = {'result':'passed','multiline':['left','center','right'],'lineGapDeltaMm':round(r['height']-r0['height'],3),
              'sizeMm':[result['preview']['width'],result['preview']['height']], 'stitches':result['preview']['stitches'],
              'sparseFillStitches':sparse_result['preview']['stitches'],'stitchModes':modes,
              'threads':result['preview']['threads'],'pes':result['pes'],'svg':result['svg']}
    (DATA / 'verification.json').write_text(json.dumps(report,indent=2))
    saved_check = (DATA / 'projects') / (project['id'] + '.json')
    if saved_check.exists() and json.loads(saved_check.read_text()) == project:
        saved_check.replace((DATA / 'verification-project.json'))
    print(json.dumps(report,indent=2),flush=True)


if __name__ == '__main__':
    main()


def sewing(preview):
    """Preview minus simulator-only command data (batch exports omit it)."""
    return {k: v for k, v in preview.items() if k not in ('commands', 'commandTypes')}
