"""Exercise every native conversion against installed Ink/Stitch and PES output."""
from verification import DATA
import copy,json,urllib.error
from pathlib import Path
from verify_native import api,export,rectangle

def main():
    run={'id':'run','type':'path','name':'Line','x':20,'y':30,'width':40,'height':.2,'color':'#203f38','stitch':'running','points':[[0,0],[1,0]],'stitchLength':2}
    fill=rectangle(x=20,y=30,width=40,height=6,radius=0,color='#203f38',underlay=False)
    report={}
    def op(key,layers,params=None):
        try:r=api('/api/operate',{'tool':key,'layers':layers,'params':params or {}})
        except urllib.error.HTTPError as e:raise AssertionError(key+': '+e.read().decode())
        if key!='cleanup':assert r['layers'] and r['preview']['stitches']>10,(key,r)
        assert all(l['type']=='path' and l['stitch']=='original' for l in r['layers'])
        report[key]={'paths':len(r['layers']),'stitches':r['preview']['stitches'] if r['preview'] else 0,'size':[r['preview']['width'],r['preview']['height']] if r['preview'] else []}
        print(key,report[key],flush=True);return r
    satin=op('stroke_to_satin',[run],{'sourceWidth':4})
    assert satin['layers'][0]['originalParams']['satin_column'].lower()=='true'
    assert abs(satin['preview']['height']-4)<.3
    filled=op('fill_to_satin',[fill]);assert any(l['originalParams'].get('satin_column','').lower()=='true' for l in filled['layers'])
    running=op('satin_to_stroke',satin['layers']);assert running['preview']['stitches']<satin['preview']['stitches']
    flipped=op('flip',satin['layers']);assert flipped['layers'][0]['contours']!=satin['layers'][0]['contours']
    cutline={**run,'id':'cutline','x':40,'y':25,'width':.2,'height':10,'points':[[0,0],[0,1]]}
    cut=op('cut_satin',satin['layers']+[cutline]);assert len(cut['layers'])==2
    zig={**run,'height':4,'points':[[i/10,i%2] for i in range(11)]}
    zigzag=op('zigzag_line_to_satin',[zig]);assert zigzag['layers'][0]['originalParams']['satin_column'].lower()=='true'
    patterned=op('stroke_to_lpe_satin',[run]);assert len(patterned['layers'][0]['contours'])>2
    op('fill_to_stroke',[fill]);op('outline',[fill]);op('redwork',[run,{**cutline,'x':40,'y':30}])
    knockdown=op('knockdown_fill',[fill]);assert len(knockdown['layers'])>1
    clean=op('cleanup',[fill,{**fill,'id':'tiny','x':70,'width':1,'height':1}]);assert len(clean['layers'])==1
    removed=op('cleanup',[{**fill,'id':'tiny','width':1,'height':1}]);assert not removed['layers'] and removed['preview'] is None
    # The source-defined entry/exit points survive non-destructive conversion.
    positioned={**fill,'entry':[0,0],'exit':[1,1]}
    kept=op('cleanup',[positioned]);assert kept['layers'][0]['entry']==[0,0] and kept['layers'][0]['exit']==[1,1]
    project={'id':'operations-verification','version':1,'name':'Conversion verification','layers':cut['layers']}
    backup=api('/api/backup',{'project':project});restored=api('/api/restore',{'project':backup});preview=export(restored)['preview']
    assert preview['stitches']==cut['preview']['stitches']
    for data in [dict(tool='unknown',layers=[run]),dict(tool='stroke_to_satin',layers=[run],params={'sourceWidth':float('nan')}),dict(tool='stroke_to_satin',layers=[{**run,'locked':True}]),dict(tool='stroke_to_satin',layers=[run],params={'evil':1}),dict(tool='cut_satin',layers=satin['layers'])]:
        try:api('/api/operate',data)
        except urllib.error.HTTPError as e:assert e.code==400
        else:raise AssertionError(data)
    assert set(report)<={t['key'] for t in api('/api/embroidery-tools')}
    (DATA / 'operations-verification.json').write_text(json.dumps({'result':'passed','tools':report,'backupRoundTrip':'passed','entryExitPreserved':True},indent=2))
    print('All conversion checks passed.',flush=True)

if __name__=='__main__':main()
