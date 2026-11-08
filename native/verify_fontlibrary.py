"""Real-engine checks for font versions, kerning, ZIPs and portable backups."""
from verification import DATA
import base64,copy,hashlib,io,json,shutil,urllib.error,urllib.request,uuid,zipfile
from pathlib import Path
from verify_native import api,export,BASE

def rejected(route,data,part):
    try:api(route,data)
    except urllib.error.HTTPError as e:
        message=json.loads(e.read())['error'];assert e.code==400 and part.lower() in message.lower(),message
    else:raise AssertionError('Expected rejection: '+part)

def encoded(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in files.items():archive.writestr(name,data)
    return {'content':base64.b64encode(stream.getvalue()).decode()}

def main():
    basic={'font':'small_font','text':'AV\nVA','scale':100,'align':'left'}
    expected=api('/api/lettering',basic)
    first=api('/api/font-metadata',{'font':'small_font','metadata':{'name':'Font library verification','description':'Font version and backup checks.'}})['font']
    path=(DATA / 'fonts')/first['id'];before=hashlib.sha256((path/'font.json').read_bytes()).hexdigest()
    details=api('/api/font-details/'+first['id']);meta=details['metadata']
    assert first['custom'] and set(first['variants'])=={'ltr','rtl'} and 'SIL' in first['license']
    newer=api('/api/font-metadata',{'font':first['id'],'metadata':{'name':'Font library verification · spacing','leading':meta['leading']+96/25.4,'kerning_pairs':{'A V':.5*96/25.4}}})['font']
    assert first['id']!=newer['id'] and hashlib.sha256((path/'font.json').read_bytes()).hexdigest()==before
    old=api('/api/lettering',{**basic,'font':first['id']});changed=api('/api/lettering',{**basic,'font':newer['id']})
    assert old['preview']==expected['preview'], 'Original font stitches changed'
    assert abs(changed['height']-old['height']-1)<.02,(changed['height'],old['height'])
    oldpair=api('/api/lettering',{**basic,'font':first['id'],'text':'AV'});newpair=api('/api/lettering',{**basic,'font':newer['id'],'text':'AV'})
    assert abs(oldpair['width']-newpair['width']-.5)<.02,(oldpair['width'],newpair['width'])
    assert oldpair['preview']['stitches']>100 and newpair['preview']['stitches']>100
    print('Immutable versions, 1 mm leading and 0.5 mm kerning passed',flush=True)
    r=api('/api/font-state',{'font':newer['id'],'favorite':True,'hidden':True})['font'];assert r['favorite'] and r['hidden']
    still=api('/api/lettering',{**basic,'font':newer['id'],'text':'Hidden font'});assert still['preview']['stitches']>100
    download=urllib.request.urlopen(BASE+'/font-packages/'+newer['id']+'.zip').read()
    reimport=api('/api/font-import',{'content':base64.b64encode(download).decode()})['font'];assert reimport['id']==newer['id'],(newer['id'],reimport['id'])
    with zipfile.ZipFile(io.BytesIO(download)) as archive:
        assert any(n.lower().startswith(('license','ofl','copyright')) for n in archive.namelist())
        assert json.loads(archive.read('font.json'))['name']==newer['name']
    png=urllib.request.urlopen(BASE+newer['preview']).read();assert png.startswith(b'\x89PNG\r\n\x1a\n')
    layer={'id':'custom-letters','type':'text','name':'AV / VA','lettering':old['settings'],'width':old['width'],'height':old['height'],'x':30,'y':30,'color':'#203f38','rotation':0}
    project={'version':1,'id':'font-library-verification','name':'Font library verification','fabric':'#faf7f0','layers':[layer]}
    result=export(project);backup=api('/api/backup',{'project':project});assert backup['embeddedFonts'][0]['id']==first['id']
    # Temporarily move only the font created by this test out of the engine's
    # font directory, then prove the self-contained backup reinstalls it.
    hold=(DATA / 'cache')/('font-restore-hold-'+uuid.uuid4().hex);path.rename(hold)
    try:
        restored=api('/api/restore',{'project':backup});assert path.exists()
        assert export(restored)['preview']==result['preview']
        uncached=api('/api/lettering',{**basic,'font':first['id'],'text':'Restored ABC'});assert uncached['preview']['stitches']>100
    finally:
        if not path.exists():hold.rename(path)
        else:shutil.rmtree(hold)
    print('Hidden-font rendering, PNG, ZIP/license and cold backup restore passed',flush=True)
    # No installation should result from an invalid uploaded document.
    font_meta=json.dumps({'name':'Invalid upload','auto_satin':False})
    safe='<svg xmlns="http://www.w3.org/2000/svg" xmlns:i="http://www.inkscape.org/namespaces/inkscape"><g i:label="GlyphLayer-A"><path id="p" d="M0 0 L2 0 L2 2 Z"/></g></svg>'
    rejected('/api/font-import',encoded({'../font.json':font_meta,'ltr.svg':safe}),'unsafe path')
    rejected('/api/font-import',encoded({'font.json':font_meta,'ltr.svg':safe.replace('<g ','<script>alert(1)</script><g ')}),'script')
    rejected('/api/font-import',encoded({'font.json':font_meta,'ltr.svg':safe.replace('<g ','<use href="https://example.com/art.svg"/><g ')}),'inside')
    rejected('/api/font-import',encoded({'font.json':font_meta,'ltr.svg':safe.replace('<g ','<g id="cycle"><use href="#cycle"/></g><g ')}),'loops')
    rejected('/api/font-import',encoded({'font.json':font_meta,'ltr.svg':safe.replace('GlyphLayer-A','Ordinary layer')}),'GlyphLayer')
    rejected('/api/font-metadata',{'font':first['id'],'metadata':{'min_scale':2,'max_scale':1}},'Maximum')
    rejected('/api/font-metadata',{'font':first['id'],'metadata':{'kerning_pairs':{'A V':'nan'}}},'Glyph spacing')
    rejected('/api/font-state',{'font':first['id'],'hidden':'false'},'on/off')
    for f in (first,newer):api('/api/font-state',{'font':f['id'],'hidden':True,'favorite':False})
    report={'result':'passed','fonts':[first['id'],newer['id']],'oldFontStitches':old['preview']['stitches'],'leadingDeltaMM':round(changed['height']-old['height'],3),'kerningDeltaMM':round(oldpair['width']-newpair['width'],3),'oldVersion':'exact stitches and unchanged metadata','backup':'font restored from embedded ZIP with exact PES','zip':'stable content identity and retained license','validation':'unsafe archives/SVGs and invalid metadata rejected'}
    (DATA / 'font-library-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
