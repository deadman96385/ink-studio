"""Shared-guide styles through HTTP, actual PES, transforms and portable recipes."""
import copy,json,urllib.error
from pathlib import Path
import pystitch
from shapely.geometry import LineString,Point
from components import world_path,path_polygon
from digitizing import inkex,from_path
from verify_native import api,export,rectangle
import server as s
import streamlines as flow

def main():
    source=rectangle(id='wave-source',name='Wave sample',x=20,y=25,width=60,height=45,radius=6)
    guides=copy.deepcopy(flow.DEFAULT_GUIDES)+[{'id':'second','points':[[.1,.8],[.55,.6],[.9,.65]]}]
    params={'separation':1.2,'guides':guides};pristine=copy.deepcopy(source)
    def make(method='wave_fill',layer=source,settings=params,length=2.5):return api('/api/flow-fill',{'layer':layer,'method':method,'settings':settings,'stitchLength':length})
    result=make();wave=result['layer'];assert source==pristine and wave['id']==source['id']
    stream=make('streamline_fill',wave);assert stream['layer']['streamlines']==wave['streamlines']==params
    assert stream['preview']['segments']!=result['preview']['segments']
    back=make(layer=stream['layer']);assert back['preview']['segments']==result['preview']['segments']
    fine=make(settings={**params,'separation':.6});coarse=make(settings={**params,'separation':2.4})
    assert fine['preview']['stitches']>coarse['preview']['stitches']*2
    shorter=make(length=1);assert shorter['preview']['stitches']>result['preview']['stitches']
    moved={**wave,'width':42,'height':31.5,'x':30,'y':30,'rotation':23,'flipX':True}
    transformed=make(layer=moved);assert transformed['layer']['streamlines']==params and transformed['layer']['rotation']==23
    for layer in (wave,stream['layer']):assert abs(path_polygon(world_path(layer,s)).area-path_polygon(world_path(source,s)).area)<.01
    nodes=api('/api/vector',{'operation':'nodes','layers':[moved]})['layers'][0]
    assert all(c['closed'] for c in nodes['contours']) and sum(len(c['nodes']) for c in nodes['contours'])<40
    assert nodes['fillMethod']=='wave_fill' and nodes['streamlines']['guides']
    hole=from_path(inkex.Path('M20,20 H80 V80 H20 Z M38,38 H62 V62 H38 Z'),{'color':'#326480','stitch':'fill','name':'Wave hole'})
    holed=make(layer=hole);inner=Point(0,0).buffer(10)
    assert all(not LineString([(a,b),(c,d)]).intersects(inner) for a,b,c,d,_ in holed['preview']['segments'])
    project={'version':1,'id':'wave-verification','name':'Wave verification','fabric':'#faf7f0','layers':[wave]}
    sewn=export(project);backup=api('/api/backup',{'project':project});restored=api('/api/restore',{'project':backup});again=export(restored)
    assert restored['layers'][0]['streamlines']==params and sewn['preview']['segments']==again['preview']['segments']
    pes=pystitch.read(str(s.DATA/'exports'/Path(sewn['pes']).name));assert sum((cmd&255)==pystitch.STITCH for _,_,cmd in pes.stitches)==sewn['preview']['stitches']
    exploded=api('/api/vector',{'operation':'explode','layers':[wave]})['layers'];assert exploded and all(not l.get('streamlines') for l in exploded)
    try:make('invalid')
    except urllib.error.HTTPError as e:assert 'Choose Streamlines or Wave Fill' in e.read().decode()
    else:raise AssertionError('Invalid style was accepted')
    report={'wave':{'lines':result['stats']['lines'],'stitches':result['preview']['stitches'],'cuts':result['preview']['trims']},
        'streamlines':{'lines':stream['stats']['lines'],'stitches':stream['preview']['stitches'],'cuts':stream['preview']['trims']},
        'sharedGuides':'identical guides across both styles','styleRoundTrip':'identical Wave PES after switch back',
        'densityStitches':[fine['preview']['stitches'],coarse['preview']['stitches']],'holes':'actual needle paths avoid hole',
        'boundaryGeometry':'closed source retained for both styles','transforms':'resize, rotation, mirror and boundary nodes retained',
        'backup':'exact PES stitches','PESReadback':'passed','validation':'passed'}
    (s.DATA/'wave-fill-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
