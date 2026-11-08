"""Acceptance checks for swatch parameters, helpers, labels, placement and PES."""
from verification import DATA
import copy,json,urllib.error,urllib.request
from pathlib import Path
from lxml import etree as ET
from verify_native import sewing,api,export,rectangle,BASE,STITCH,SVG

def reject(data,text):
    try:api('/api/swatches',data)
    except urllib.error.HTTPError as e:
        message=json.loads(e.read())['error'];assert e.code==400 and text.lower() in message.lower(),message
    else:raise AssertionError('Expected '+text)

def project(r):return {'version':1,'id':'swatch-verification','name':'Test swatches verification','fabric':'#faf7f0','layers':r['sources']+r['layers'],'swatchRecipe':r['recipe'],'swatchPlan':r['plan']}

def main():
    base={'source':'fill','rows':2,'columns':3,'axis':{'key':'row_spacing_mm','start':.3,'step':.05},'labels':True}
    r=api('/api/swatches',base);assert len(r['layers'])==6 and len(r['sources'])==1
    assert all(l['visible'] is False for l in r['sources'])
    assert [s['values']['row_spacing_mm'] for s in r['plan']['samples']]==[.3,.35,.4,.45,.5,.55]
    assert (r['width'],r['height'])==(62,41.59)
    for i,a in enumerate(r['assets']):
        doc=ET.fromstring(a['svg'].encode());sample=doc[0];label=doc[1]
        assert sample.xpath('//*[@inkstitch:row_spacing_mm]',namespaces={'inkstitch':STITCH})
        assert {float(e.get('{'+STITCH+'}row_spacing_mm')) for e in sample.iter() if e.get('{'+STITCH+'}row_spacing_mm')}=={.3+i*.05} or all(abs(float(e.get('{'+STITCH+'}row_spacing_mm'))-(.3+i*.05))<1e-8 for e in sample.iter() if e.get('{'+STITCH+'}row_spacing_mm'))
        assert not any(e.get('{'+STITCH+'}row_spacing_mm') for e in label.iter())
        assert all(e.get('{'+STITCH+'}random_seed') for e in sample.iter('{'+SVG+'}path'))
    output=export(project(r));assert sewing(output['preview'])==sewing(r['preview'])
    restored=api('/api/restore',{'project':api('/api/backup',{'project':project(r)})});back=export(restored)
    assert sewing(back['preview'])==sewing(output['preview']) and restored['swatchPlan']==r['plan']
    # The key prints in the print workspace (sampleKeys, on by default) and in
    # the printable sheet bundled with batch/sample ZIPs.
    import server as s,print_work
    from interchange import swatch_key,print_sheet
    for sheet in (swatch_key(project(r)),print_sheet(output['id'],s).decode() if isinstance(print_sheet(output['id'],s),bytes) else print_sheet(output['id'],s)):
        assert 'Swatch settings' in sheet and 'Fill row spacing (mm)' in sheet and '<td>6</td><td>2 / 3</td>' in sheet
    assert print_work.DEFAULTS['sampleKeys'] is True
    print('Six labels, parameter map, print key, exact PES and backup passed',flush=True)
    # Independent single-sample exports demonstrate the parameter's effect.
    simple=api('/api/swatches',{**base,'labels':False,'rows':1,'columns':3,'axis':{'key':'row_spacing_mm','start':.3,'step':.15}})
    counts=[export({**project(simple),'layers':[l]})['preview']['stitches'] for l in simple['layers']]
    assert counts[0]>counts[1]>counts[2],counts
    matrix=api('/api/swatches',{**base,'labels':False,'secondAxis':{'key':'angle','start':0,'step':45},'order':'snake'})
    assert [l['swatchNumber'] for l in matrix['layers']]==[1,2,3,6,5,4]
    assert [(s['values']['row_spacing_mm'],s['values']['angle']) for s in matrix['plan']['samples']]==[(.3,0),(.35,0),(.4,0),(.3,45),(.35,45),(.4,45)]
    assert matrix['preview']['stitches']>1000
    print('Density changes stitch count; two-parameter snake grid passed',flush=True)
    target=rectangle(id='guided',name='Guided sample',x=25,y=30,width=18,height=12,fillMethod='guided_fill',underlay=False)
    guide={'id':'guide','type':'path','name':'Curve guide','role':'guide-line','helperTarget':'guided','x':5,'y':32,'width':70,'height':7,'stitch':'running','color':'#ff0000','points':[[0,.5],[.5,0],[1,.5]]}
    guided=api('/api/swatches',{**base,'source':'selection','layers':[target,guide],'rows':1,'columns':2,'labels':False})
    assert len(guided['sources'])==2 and len(guided['preview']['threads'])==1 and guided['preview']['width']<41
    for a in guided['assets']:
        doc=ET.fromstring(a['svg'].encode());helpers=[e for e in doc.iter() if 'inkstitch-guide-line-marker' in e.get('style','')]
        assert helpers and all(e.get('{'+STITCH+'}row_spacing_mm') is None for e in helpers)
    separated=api('/api/vector',{'operation':'explode','layers':[guided['layers'][0]]})['layers']
    assert any(l.get('role')=='guide-line' for l in separated)
    satin=api('/api/swatches',{**base,'source':'satin','sampleWidth':20,'sampleHeight':4,'rows':1,'columns':3,'labels':False,'axis':{'key':'zigzag_spacing_mm','start':.25,'step':.1}})
    assert satin['preview']['stitches']>400
    running=api('/api/swatches',{**base,'source':'running','rows':1,'columns':3,'labels':False,'axis':{'key':'running_stitch_length_mm','start':1,'step':1}})
    assert running['preview']['stitches']>20
    custom=api('/api/swatches',{**base,'rows':1,'columns':2,'labels':False,'axis':{'key':'custom','parameter':'angle','start':45,'step':-45}})
    assert [s['values']['angle'] for s in custom['plan']['samples']]==[45,0]
    for bad,message in [({**base,'rows':1.5},'whole'),({**base,'rows':10,'columns':10},'36'),({**base,'sampleWidth':80},'too large'),
                        ({**base,'axis':{'key':'row_spacing_mm','start':.2,'step':-.1}},'every sample'),
                        ({**base,'axis':{'key':'custom','parameter':'row_spacing_mm','start':0,'step':.1}},'starting value'),
                        ({**base,'axis':{'key':'pattern_size_mm','start':2,'step':1}},'does not apply'),
                        ({**base,'source':'running','axis':{'key':'line_count','start':3,'step':1}},'does not apply'),
                        ({**base,'source':'satin','axis':{'key':'zigzag_spacing_mm','start':0,'step':.1}},'does not apply'),
                        ({**base,'source':'running'},'does not apply'),({**base,'secondAxis':base['axis']},'different parameters'),
                        ({**base,'source':'selection','layers':[target]},'visible guide')]:reject(bad,message)
    api('/api/save',{'project':{**project(r),'id':'test-swatches-example','name':'Test swatches example','grid':True,'snap':True}})
    report={'result':'passed','samples':6,'stitches':r['preview']['stitches'],'grid':[r['width'],r['height']],'densityCounts':counts,
            'matrix':'two parameters with snake sewing order','labels':'numbered with unchanged font parameters','printKey':'all sample settings included','backup':'exact PES preview',
            'guides':'attached and non-sewing; independently editable after separation','satinStitches':satin['preview']['stitches'],'runningStitches':running['preview']['stitches'],'validation':'passed'}
    (DATA / 'swatches-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
