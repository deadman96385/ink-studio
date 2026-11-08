"""End-to-end specimens: exact glyphs, variants, multi-page PES and backups."""
from verification import DATA, BASE as VERIFY_BASE
import base64
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import zipfile
import pystitch

BASE=VERIFY_BASE


def api(path,data=None):
    req=urllib.request.Request(BASE+path,None if data is None else json.dumps(data).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=300) as response:return json.load(response)


def raw(path):return urllib.request.urlopen(BASE+path,timeout=300).read()


def start(**config):return api('/api/font-samples',config)['id']


def wait(key):
    last=None
    for _ in range(1800):
        job=api('/api/font-sample-jobs/'+key)
        if job['message']!=last:print(job['state'],job['message'],flush=True);last=job['message']
        if job['state'] not in ('queued','working'):
            assert job['state']=='done',job
            return job
        time.sleep(1)
    raise AssertionError('Sampling job did not complete')


def fixture():
    meta={'name':'Sampler verification fixture','size':10,'leading':50,'min_scale':1,'max_scale':1,'default_variant':'ltr','auto_satin':False,'reversible':False,'sortable':True,'glyphs':['A','fi','A.alt']}
    def svg(reverse=False):
        groups=[]
        for i,name in enumerate(meta['glyphs']):
            width=(12 if reverse else 8)+i*3
            locked=' sodipodi:insensitive="true"' if name=='A.alt' else ''
            groups.append(f'<g inkscape:groupmode="layer" inkscape:label="GlyphLayer-{name}"{locked}><path id="a{i}" d="M0,-20 L{width},-20 L{width},0 L0,0" style="fill:none;stroke:#e02323;stroke-width:.3" inkstitch:stroke_method="manual_stitch" inkstitch:color_sort_index="1"/><path id="b{i}" d="M0,-10 L{width},-10" style="fill:none;stroke:#2355ee;stroke-width:.3" inkstitch:stroke_method="manual_stitch" inkstitch:color_sort_index="2"/></g>')
        return '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" xmlns:inkstitch="http://inkstitch.org/namespace" xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" width="100mm" height="100mm" viewBox="0 0 377.952756 377.952756">'+''.join(groups)+'</svg>'
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('font.json',json.dumps(meta));archive.writestr('ltr.svg',svg());archive.writestr('rtl.svg',svg(True));archive.writestr('LICENSE','Test fixture made for Ink Studio verification.')
    return api('/api/font-import',{'content':base64.b64encode(out.getvalue()).decode()})['font']['id']


def verify_page(key,index):
    p=api(f'/api/font-sample-jobs/{key}/{index}');e=p['export'];preview=e['preview'];design=p['design']
    assert preview['width']<=100 and preview['height']<=100
    assert all(0<=l['x'] and 0<=l['y'] and l['x']+l['width']<=100.01 and l['y']+l['height']<=100.01 for l in design['layers'])
    encoded=raw(e['pes']);assert encoded[:8]==b'#PES0060'
    backup=json.loads(raw(e['project']));assert len(backup['embeddedAssets'])==len({l['asset'] for l in design['layers']})
    restored=api('/api/restore',{'project':backup});assert restored['fontSamplePlan']==design['fontSamplePlan']
    # The key is in the bundled printable sheet; the print workspace adds it via sampleKeys.
    import server as s
    from interchange import print_sheet
    sheet=print_sheet(e['id'],s);sheet=sheet.decode() if isinstance(sheet,bytes) else sheet
    assert 'Font sample key' in sheet
    return p,restored


def reject(data):
    try:api('/api/font-samples',data)
    except urllib.error.HTTPError as e:assert e.code==400;return
    raise AssertionError('Invalid sample configuration accepted')


if __name__=='__main__':
    # Reuse the completed full-font run if supplied by the interactive audit.
    # Caller may pass an existing completed full-font job ID.
    import sys
    full=sys.argv[1] if len(sys.argv)>1 else start(font='small_font',scale=220,lineWidth=88)
    result=wait(full);assert len(result['pages'])>=2
    found=[];summaries=[]
    for i in range(len(result['pages'])):
        p,_=verify_page(full,i);found.extend(g['name'] for g in p['design']['fontSamplePlan']['glyphs']);summaries.append({'glyphs':len(p['design']['layers']),'stitches':p['export']['preview']['stitches']})
    expected=[g['name'] for g in api('/api/font-sample-glyphs/small_font')['glyphs'] if not g['locked']]
    assert found==expected,(len(found),len(expected))
    with zipfile.ZipFile(io.BytesIO(raw(result['bundle']))) as z:
        assert len(z.namelist())==len(result['pages'])*5
        assert all('Font sample key' in z.read(n).decode() for n in z.namelist() if n.endswith('.html'))
    font=fixture();cat=api('/api/font-sample-glyphs/'+font)
    assert {g['name'] for g in cat['glyphs']}=={'A','fi','A.alt'}
    assert next(g for g in cat['glyphs'] if g['name']=='A.alt')['locked']
    plain=start(font=font,glyphs=['A','fi','A.alt'],variant='ltr',trim=False)
    reverse=start(font=font,glyphs=['A','fi','A.alt'],variant='rtl',trim=False)
    a=wait(plain);b=wait(reverse)
    p,restored=verify_page(plain,0);q,_=verify_page(reverse,0)
    assert len(p['design']['layers'])==3
    assert q['design']['layers'][0]['width']>p['design']['layers'][0]['width']+.9
    assert [l['name'] for l in p['design']['layers']]==['A','fi','A.alt']
    assert len(json.loads(raw(p['export']['project']))['embeddedFonts'])==1
    sorted_id=start(font=font,glyphs=['A','fi','A.alt'],colorSort=True,trim=False)
    wait(sorted_id);sorted_page,_=verify_page(sorted_id,0)
    assert len(p['export']['preview']['threads'])==6,p['export']['preview']['threads']
    assert len(sorted_page['export']['preview']['threads'])==2,sorted_page['export']['preview']['threads']
    for glyph in p['design']['layers']:
        assert 'inkstitch:lettering=' not in api('/api/assets/'+glyph['asset'])['svg']
    installed_plain=start(font='emilio_20_applique',glyphs=['A','B'],trim=False)
    installed_sort=start(font='emilio_20_applique',glyphs=['A','B'],trim=False,colorSort=True)
    wait(installed_plain);wait(installed_sort)
    ip,_=verify_page(installed_plain,0);isp,_=verify_page(installed_sort,0)
    assert len(ip['export']['preview']['threads'])==6
    assert len(isp['export']['preview']['threads'])==3
    exported=api('/api/export',{'project':restored})['id']
    for _ in range(300):
        j=api('/api/jobs/'+exported)
        if j['state'] not in ('queued','working'):break
        time.sleep(1)
    assert j['state']=='done',j
    from verify_native import sewing
    assert sewing(j['result']['preview'])==sewing(p['export']['preview']),'Backup changed stitches'
    default=start(font=font);wait(default);default_page,_=verify_page(default,0)
    assert [l['name'] for l in default_page['design']['layers']]==['A','fi']
    cancel_id=start(font='small_font',scale=221)
    api('/api/font-sample-cancel',{'id':cancel_id})
    for _ in range(180):
        cancelled=api('/api/font-sample-jobs/'+cancel_id)
        if cancelled['state']=='cancelled':break
        time.sleep(1)
    assert cancelled['state']=='cancelled',cancelled
    for data in [dict(font=font,glyphs=[]),dict(font=font,glyphs=['missing']),dict(font=font,glyphs=['A','A']),dict(font=font,scale=0),dict(font=font,gapX=-1),dict(font=font,lineWidth=101),dict(font=font,variant='invalid'),dict(font='small_font',colorSort=True)]:reject(data)
    # Clips are retained in editable backups but resource cycles are rejected.
    clip='<svg xmlns="http://www.w3.org/2000/svg"><defs><clipPath id="a"><path d="M0,0 H10 V10 H0Z"/></clipPath></defs><path clip-path="url(#a)" d="M0,0 H20 V20 H0Z"/></svg>'
    api('/api/import',{'svg':clip})
    try:api('/api/import',{'svg':clip.replace('<clipPath id="a">','<clipPath id="a" clip-path="url(#a)">')})
    except urllib.error.HTTPError as e:assert e.code==400
    else:raise AssertionError('Clip cycle accepted')
    api('/api/font-state',{'font':font,'hidden':True})
    assert not any(f['name'].startswith('Sampler custom-') or f['name']=='Sorted font specimen' for f in api('/api/fonts'))
    report=dict(fullFontGlyphs=len(found),sheets=summaries,ligaturesAndLockedGlyphs=True,stitchDirections=True,colorSteps={'original':6,'sorted':2},installedAppliqueColorSteps={'original':6,'sorted':3},portableBackupExact=True,cancellation=True,invalidOptionsRejected=True,clipCycleRejected=True)
    (DATA / 'font-samples-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
