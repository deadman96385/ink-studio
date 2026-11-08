"""HTTP, real PES, editable satin geometry and source-font backup acceptance."""
from verification import TTF, OTF
import base64,copy,hashlib,io,json,tempfile,urllib.error,uuid
from pathlib import Path
from types import SimpleNamespace
from lxml import etree as ET
import pystitch
from shapely.geometry import MultiLineString
import server as s
import ttf_fonts as t
from verify_native import api,export,rectangle


def reject(path,data,contains):
    try:api(path,data)
    except urllib.error.HTTPError as error:assert contains in error.read().decode(),contains
    else:raise AssertionError('Expected rejection: '+contains)


def main():
    def upload(path):
        raw=Path(path).read_bytes();return raw,api('/api/outline-font-import',{'name':Path(path).name,'content':base64.b64encode(raw).decode()})
    raw,font=upload(TTF)
    otf_raw,otf=upload(OTF)
    assert any(f['key']==font['key'] for f in api('/api/outline-fonts'))
    assert otf['format']=='OTF' and font['format']=='TTF'
    def convert(info=font,text='Test',**settings):return api('/api/outline-lettering',{'settings':{'font':info['key'],'text':text,'height':12,**settings},'color':'#326480'})
    result=convert();cff=convert(otf,'Aé fi',height=10)
    assert result['preview']['stitches']>300 and cff['preview']['stitches']>200
    assert result['columns']>4 and result['glyphs']==4
    assert cff['glyphs']<=4,'HarfBuzz must preserve the fi ligature'
    assert result['layer']['ttfLettering']['font']==font['key']
    combined=api('/api/outline-lettering',{'settings':{'font':font['key'],'text':'A\néfi','height':10,'align':'right','lineGap':3},'color':'#9a3255',
        'pose':{'cx':46,'cy':54,'rotation':15,'flipX':True}})
    assert combined['layer']['rotation']==15 and combined['layer']['flipX'] is True
    doc=ET.fromstring(result['asset']['svg'].encode())
    columns=[p for p in doc.iter('{'+s.SVG+'}path') if p.get('{'+s.STITCH+'}satin_column')=='True']
    assert columns and all(p.get('{'+s.STITCH+'}center_walk_underlay')=='True' for p in columns)
    assert all('Z' not in p.get('d').upper() for p in columns),'Satin rails must remain open'
    project={'version':1,'id':'ttf-lettering-verification','name':'TTF lettering verification','fabric':'#faf7f0','layers':[result['layer']]}
    backup=api('/api/backup',{'project':project});assert len(backup['embeddedOutlineFonts'])==1
    assert base64.b64decode(backup['embeddedOutlineFonts'][0]['content'])==raw
    restored=api('/api/restore',{'project':backup});out=export(project);again=export(restored)
    assert out['preview']['segments']==again['preview']['segments']
    assert restored['layers'][0]['ttfLettering']==result['layer']['ttfLettering']
    pes=s.DATA/'exports'/Path(out['pes']).name;pattern=pystitch.read(str(pes))
    assert sum((command&255)==pystitch.STITCH for _,_,command in pattern.stitches)==out['preview']['stitches']
    assert pattern.threadlist[0].hex_color().lower()=='#326480'
    parts=api('/api/vector',{'operation':'explode','layers':[result['layer']]})['layers']
    assert any(str(l.get('originalParams',{}).get('satin_column','')).lower()=='true' for l in parts)
    separate=export({**project,'id':'ttf-separated-verification','layers':parts})['preview']
    lines=lambda preview:MultiLineString([[(seg[0],seg[1]),(seg[2],seg[3])] for seg in preview['segments']])
    # Exposing affine paths can shift a needle's phase along the same line.
    # Compare physical stitch coverage at the machine's 0.1 mm resolution.
    line_delta=lines(result['preview']).hausdorff_distance(lines(separate))
    assert line_delta<.1 and abs(separate['stitches']-result['preview']['stitches'])<=1
    assert all(separate[k]==result['preview'][k] for k in ('bounds','trims','jumps','stops','colorChanges'))
    # Restore source fonts into an empty store, preserving exact bytes and identity.
    with tempfile.TemporaryDirectory() as tmp:
        backend=SimpleNamespace(DATA=Path(tmp),write_atomic=s.write_atomic,asset_layers=s.asset_layers)
        source=copy.deepcopy(backup);t.restore(source,backend)
        assert (Path(tmp)/'outline-fonts'/(font['key']+'.bin')).read_bytes()==raw
        assert t.get(font['key'],backend)['name']==font['name']
    original=api('/api/backup',{'project':{**project,'layers':[rectangle()]}})
    assert not original.get('embeddedOutlineFonts')
    reject('/api/outline-font-import',{'name':'bad.ttf','content':base64.b64encode(b'not-a-font').decode()},'TrueType')
    reject('/api/outline-lettering',{'settings':{'font':font['key'],'text':'  '}},'Enter 1')
    reject('/api/outline-lettering',{'settings':{'font':font['key'],'text':'Hello','spacing':0}},'Satin spacing')
    reject('/api/outline-lettering',{'settings':{'font':font['key'],'text':'Hello','height':100}},'Capital height')
    reject('/api/outline-lettering',{'settings':{'font':font['key'],'text':'Hello','underlay':'yes'}},'underlay')
    reject('/api/outline-lettering',{'settings':{'font':font['key'],'text':'\U0010ffff'}},'missing a character')
    corrupt=copy.deepcopy(backup);corrupt['embeddedOutlineFonts'][0]['content']=base64.b64encode(otf_raw).decode()
    reject('/api/restore',{'project':corrupt},'checksum')
    report={'ttf':{'font':font['name'],'columns':result['columns'],'stitches':result['preview']['stitches'],'trims':result['preview']['trims']},
        'otf':{'font':otf['name'],'glyphs':cff['glyphs'],'stitches':cff['preview']['stitches']},
        'multiline':{'glyphs':combined['glyphs'],'stitches':combined['preview']['stitches'],'rotation':15,'mirrored':True},
        'portable':'exact source font bytes, editable recipe and PES stitches','independentPESReadback':'passed',
        'separatePaths':{'paths':len(parts),'lineDifferenceMm':line_delta,'stitches':separate['stitches'],'commands':'unchanged'},'validation':'passed'}
    (s.DATA/'ttf-fonts-verification.json').write_text(json.dumps(report,indent=2))
    (s.DATA/'ttf-separated-verification.json').write_text(json.dumps({'result':'passed',**report['separatePaths']},indent=2))
    (s.DATA/'ttf-ui-fixture.json').write_text(json.dumps({'font':font,'fontPath':str(TTF),'proposal':result}))
    (s.DATA/'ttf-ui-sample.ttf').write_bytes(raw)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
