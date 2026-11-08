"""Real-engine acceptance checks for advanced parameters, routing and inspection."""
from verification import DATA
import copy,json,math,urllib.error
from pathlib import Path
from verify_native import api,export,rectangle
from advanced import density_points,validate_advanced

def expect_invalid(values):
    try:validate_advanced(values)
    except ValueError:return
    raise AssertionError(values)

def main():
    schema=api('/api/stitch-schema');assert len(schema)>40
    for values in [{'ties':True},{'min_stitch_length_mm':float('nan')},{'repeats':0},{'satin_method':'unknown'},{'fill_underlay_angle':'1 bad'},{'bogus':2}]:expect_invalid(values)
    # The overlay includes every overlapping thread color, using exact distances.
    segs=[[0,0,x,y,i%2] for i,(x,y) in enumerate([(0,0),(.1,0),(.2,0),(4,4),(4.1,4),(10,10)])]
    d=density_points(segs,.5,2,3);assert d['counts']==[1,2,3],d
    project={'version':1,'id':'advanced-verification','name':'Advanced verification','layers':[]}
    base=rectangle(x=30,y=30,width=30,height=20,radius=0,underlay=False)
    a=export({**project,'layers':[base]})['preview']
    b=export({**project,'layers':[{**base,'advanced':{'end_row_spacing_mm':1.2,'ties':3}}]})['preview']
    assert b['stitches']<a['stitches'],(a['stitches'],b['stitches'])
    satin={'id':'sat','type':'path','name':'Satin','x':20,'y':30,'width':30,'height':5,'color':'#203f38','stitch':'satin','spacing':.4,
      'contours':[{'closed':False,'nodes':[{'x':x,'y':y,'in':[x,y],'out':[x,y]} for x in [0,1]]} for y in [0,1]]}
    standard=export({**project,'layers':[satin]})['preview']
    underlay=export({**project,'layers':[{**satin,'advanced':{'center_walk_underlay_repeats':6}}]})['preview']
    assert underlay['stitches']>standard['stitches']
    estitch=export({**project,'layers':[{**satin,'advanced':{'satin_method':'e_stitch'}}]})['preview']
    assert estitch['segments']!=standard['segments']
    routes={}
    running=[{'id':f'run{i}','type':'path','name':f'Run {i}','x':x,'y':y,'width':w,'height':h,'color':'#203f38','stitch':'running','points':points,'stitchLength':2}
       for i,(x,y,w,h,points) in enumerate([(20,30,20,.2,[[0,0],[1,0]]),(40,30,20,.2,[[0,0],[1,0]]),(40,30,.2,20,[[0,0],[0,1]])])]
    for kind,layers in [('running',running),('satin',[satin,{**copy.deepcopy(satin),'id':'sat2','x':50}])]:
        r=api('/api/route',{'layers':layers,'kind':kind,'trim':True,'preserveOrder':False,'breakUp':True})
        assert r['layers'] and all(l['type']=='path' and l['stitch']=='original' for l in r['layers']),r
        assert r['preview']['stitches']>30,r
        backup=api('/api/backup',{'project':{**project,'layers':r['layers']}})
        restored=api('/api/restore',{'project':backup});out=export(restored)['preview']
        assert out['stitches']==r['preview']['stitches'],(out['stitches'],r['preview']['stitches'])
        routes[kind]={'editablePaths':len(r['layers']),'stitches':out['stitches'],'trims':out['trims'],'size':[out['width'],out['height']]}
    check=api('/api/inspect',{'project':{**project,'layers':[base]}})
    assert not any(f['severity']=='error' for f in check['findings']),check['findings']
    assert check['density'] and check['preview']['stitches']>100
    invalid=copy.deepcopy(satin);invalid['contours']=invalid['contours'][:1]
    errors=api('/api/inspect',{'project':{**project,'layers':[invalid]}})
    assert any(f['severity']=='warning' and 'narrow' in f['message'].lower() for f in errors['findings']),errors
    outside=api('/api/inspect',{'project':{**project,'layers':[{**base,'x':90}]}})
    assert any('hoop' in f['message'] for f in outside['findings']),outside
    report={'result':'passed','advancedFields':len(schema),'fillStitchesBeforeAfter':[a['stitches'],b['stitches']],'satinUnderlayStitchesBeforeAfter':[standard['stitches'],underlay['stitches']],
       'routes':routes,'densityCounts':check['density']['counts'],'narrowSatinFindings':errors['findings'],'backupRoundTrip':'passed'}
    (DATA / 'advanced-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
