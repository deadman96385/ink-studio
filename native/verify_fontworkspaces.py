"""Actual-engine checks for native font authoring and portable source revisions."""
from verification import DATA, RESOURCE, BASE as VERIFY_BASE
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid
import zipfile

BASE=VERIFY_BASE


def api(path,data=None):
    req=urllib.request.Request(BASE+path,None if data is None else json.dumps(data).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=300) as r:return json.load(r)


def export(project):
    key=api('/api/export',{'project':project})['id']
    for _ in range(300):
        result=api('/api/jobs/'+key)
        if result['state'] not in ('queued','working'):break
        time.sleep(1)
    assert result['state']=='done',result
    return result['result']


def lettering(font,text):return api('/api/lettering',{'font':font,'text':text,'scale':100,'align':'left','trim':'off'})


def action(workspace,action,**data):return api('/api/font-workspace-update',{'id':workspace['id'],'revision':workspace['revision'],'action':action,**data})


def install(w):return api('/api/font-workspace-publish',{'id':w['id'],'revision':w['revision']})


def rejected(path,data):
    try:api(path,data)
    except urllib.error.HTTPError as e:assert e.code==400,(e.code,e.read());return
    raise AssertionError('Invalid authoring operation accepted')


if __name__=='__main__':
    original_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (RESOURCE / 'fonts/src/small_font').rglob('*') if p.is_file()}
    w=api('/api/font-workspace-create',{'font':'small_font','name':'Font authoring verification'})
    first=w['revision'];r=api('/api/font-workspace-glyph',{'id':w['id'],'variant':'ltr','glyph':'A'});p=r['project']
    assert 'baseline' in p['fontGlyph']['guides'] and p['fontGlyph']['advance']>0
    saved=api('/api/font-workspace-save-glyph',{'project':p});w=saved['workspace'];p['fontGlyph']=saved['context']
    reopened=api('/api/font-workspace-glyph',{'id':w['id'],'variant':'ltr','glyph':'A'})['project']
    for key,y in p['fontGlyph']['guides'].items():assert abs(reopened['fontGlyph']['guides'][key]-y)<1e-5
    installed=install(w);w=installed['workspace'];font=installed['font']['id'];p['fontGlyph']['revision']=w['revision']
    original=lettering('small_font','AAbg');roundtrip=lettering(font,'AAbg')
    assert original['preview']==roundtrip['preview'],'Source glyph round trip changed stitches'
    print('Original glyph and untouched letters preserve exact stitches',flush=True)
    # Native Separate paths, then changing advance, is a complete editable
    # path workflow; an extra 2 mm advance adds 2 mm between two As.
    separated=api('/api/vector',{'operation':'explode','layers':p['layers']})['layers'];assert separated
    p['layers']=separated;p['fontGlyph']['advance']+=2
    saved=api('/api/font-workspace-save-glyph',{'project':p});w=saved['workspace'];p['fontGlyph']=saved['context']
    installed=install(w);w=installed['workspace'];font2=installed['font']['id'];p['fontGlyph']['revision']=w['revision']
    before=lettering(font,'AA');after=lettering(font2,'AA');assert abs(after['width']-before['width']-2)<.01
    assert font!=font2 and lettering(font,'AA')['preview']==before['preview']
    print('Separated native paths and exact 2 mm advance verified',flush=True)
    # Preserve optimistic revision checks: stale iPad tabs cannot overwrite.
    stale=copy.deepcopy(p);w=action(w,'lock',glyph='A',variant='ltr',locked=True)
    rejected('/api/font-workspace-save-glyph',{'project':stale})
    assert next(g for g in w['glyphs'] if g['name']=='A' and g['variant']=='ltr')['locked']
    w=action(w,'copy',glyph='A',variant='ltr',name='fi',targetVariant='ltr')
    w=action(w,'copy-variant',variant='ltr',targetVariant='ttb')
    w=action(w,'rename',glyph='fi',variant='ttb',name='A.alt',targetVariant='ttb')
    assert any(g['name']=='A.alt' and g['variant']=='ttb' for g in w['glyphs'])
    before_remove=w['revision'];w=action(w,'remove',glyph='A.alt',variant='ttb')
    assert not any(g['name']=='A.alt' for g in w['glyphs'])
    w=action(w,'restore',restoreRevision=before_remove);assert any(g['name']=='A.alt' for g in w['glyphs'])
    # Embed a source snapshot and force a cold workspace restore using a new
    # absent ID. No installed fonts or existing sources are removed.
    p['fontGlyph']['revision']=w['revision'];result=export(p)
    backup=json.load(urllib.request.urlopen(BASE+result['project']));assert backup['embeddedFontWorkspace']['content']
    cold=copy.deepcopy(backup);cold['fontGlyph']['workspace']=uuid.uuid4().hex;cold['fontGlyph']['revision']=uuid.uuid4().hex
    restored=api('/api/restore',{'project':cold});assert restored['fontGlyph']['workspace']!=cold['fontGlyph']['workspace']
    assert export(restored)['preview']==result['preview']
    print('Revision history, stale-save protection and cold portable workspace verified',flush=True)
    # Create a new font from native artwork, independent of any existing font.
    blank=api('/api/font-workspace-create',{'name':'Native icon font verification'})
    icon=api('/api/font-workspace-glyph',{'id':blank['id'],'variant':'ltr','glyph':'X'})['project']
    icon['layers']=[dict(id=uuid.uuid4().hex,name='X test artwork',type='rectangle',x=20,y=50,width=8,height=15,rotation=0,radius=1,color='#336655',stitch='fill',spacing=.4,angle=45,underlay=True,stitchLength=2.5,visible=True)]
    saved=api('/api/font-workspace-save-glyph',{'project':icon});blank=saved['workspace'];published=install(blank)
    letters=lettering(published['font']['id'],'XX');assert letters['preview']['stitches']>200
    raw=urllib.request.urlopen(BASE+'/font-workspace-packages/'+w['id']+'.zip').read()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:assert 'font.json' in archive.namelist() and any(n.endswith('.svg') for n in archive.namelist())
    imported=api('/api/font-workspace-create',{'content':base64.b64encode(raw).decode(),'name':'Restored font source verification'})
    assert len(imported['glyphs'])==len(w['glyphs'])
    for name,digest in original_files.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest
    rejected('/api/font-workspace-glyph',{'id':w['id'],'variant':'ltr','glyph':'bad\nname'})
    for key in [font,font2,published['font']['id']]:api('/api/font-state',{'font':key,'hidden':True})
    report=dict(sourceRoundTripExact=True,nativePathsEditable=True,advanceIncreaseMm=after['width']-before['width'],immutableInstalledVersions=True,copyRenameVariants=True,lockAndRestore=True,staleSavesRejected=True,coldWorkspaceBackupExact=True,nativeNewFontStitches=letters['preview']['stitches'],sourceZipRestored=True,installedSourcesUnchanged=True,workspace=w['id'])
    (DATA / 'font-workspaces-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
