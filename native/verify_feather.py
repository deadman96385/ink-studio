"""Real engine edge effects, native recipes, protected holes and exact PES backups."""
import copy,json,urllib.error
from pathlib import Path
import pystitch
from digitizing import inkex,from_path
from components import world_path,path_polygon
from verify_native import api,export,rectangle
import server as s

def main():
    source=rectangle(id='feather-shape',name='Feather sample',x=25,y=25,width=30,height=24,radius=3,angle=0)
    project={'version':1,'id':'feather-verification','name':'Feather verification','layers':[source]}
    def prepare(layer=source,**settings):return api('/api/feather',{'project':{**project,'layers':[layer]},'id':layer['id'],'settings':{'seed':'feather-check',**settings}})
    result=prepare(raggedness=.6);layer=result['layer'];assert result['stats']['edges']>60 and result['stats']['maxExtension']<=.6
    normal=api('/api/layer-preview',{'layers':[source]})['preview'];off=prepare(enabled=False)
    assert normal['segments']==off['preview']['segments']
    assert result['preview']['segments']!=normal['segments'];assert result['preview']['segments']==prepare(raggedness=.6)['preview']['segments']
    assert result['preview']['segments']!=prepare(raggedness=.6,seed='different')['preview']['segments']
    left=prepare(raggedness=.6,balance=-100);right=prepare(raggedness=.6,balance=100)
    def extents(value):
        paths=[inkex.Path(p['d']).bounding_box() for p in value['layer']['featherPreview']['paths']]
        return min(float(b.left) for b in paths),max(float(b.right) for b in paths)
    assert extents(left)[0]<-.1 and extents(left)[1]<=source['width']+.01
    assert extents(right)[0]>=-.01 and extents(right)[1]>source['width']+.1
    fine=prepare(raggedness=.2);assert result['preview']['width']>fine['preview']['width']
    hole=from_path(inkex.Path('M20,20 H80 V80 H20 Z M38,38 H62 V62 H38 Z'),{'color':'#326480','stitch':'fill','name':'Feather holes','angle':0,'spacing':.6,'stitchLength':3,'underlay':False})
    protected=prepare(hole,raggedness=1);included=prepare(hole,raggedness=1,includeHoles=True)
    assert protected['preview']['segments']!=included['preview']['segments']
    assert protected['stats']['edges']<included['stats']['edges']
    leaf={'id':'feather-satin','type':'path','name':'Satin edge fixture','x':25,'y':25,'width':20,'height':4,
          'color':'#326480','stitch':'satin','spacing':.4,
          'contours':[{'closed':False,'nodes':[{'x':x,'y':y,'in':[x,y],'out':[x,y]} for x in [0,1]]} for y in [0,1]]}
    satin=prepare(leaf,raggedness=.2);assert satin['stats']['edges']>10
    import streamlines
    wave=api('/api/flow-fill',{'layer':source,'method':'wave_fill','settings':{'separation':1.2,'guides':copy.deepcopy(streamlines.DEFAULT_GUIDES)}})['layer']
    waved=prepare(wave,raggedness=.25);assert waved['stats']['edges']>5
    moved={**layer,'width':24,'height':19.2,'x':35,'y':35,'rotation':25,'flipX':True}
    transformed=prepare(moved,raggedness=.6);assert transformed['layer']['rotation']==25 and transformed['layer']['flipX']
    assert transformed['layer']['feather']['raggedness']==.6
    nodes=api('/api/vector',{'operation':'nodes','layers':[layer]})['layers'][0];assert sum(len(c['nodes']) for c in nodes['contours'])<40 and all(c['closed'] for c in nodes['contours'])
    assert abs(path_polygon(world_path(layer,s)).area-path_polygon(world_path(source,s)).area)<.001
    bordered=prepare({**source,'borderEnabled':True,'borderColor':'#993366','borderStitch':'running'},raggedness=.6)
    assert bordered['preview']['colorChanges']==1
    sewn_project={**project,'layers':[{**layer,'stopAfter':True},rectangle(id='feather-later',x=62,y=65,width=12,height=9,color='#884477')]}
    sewn=export(sewn_project);assert sewn['preview']['stops']>=1
    backup=api('/api/backup',{'project':sewn_project});restored=api('/api/restore',{'project':backup});again=export(restored)
    assert sewn['preview']['segments']==again['preview']['segments'] and sewn['preview']['stops']==again['preview']['stops']
    pes=pystitch.read(str(s.DATA/'exports'/Path(sewn['pes']).name));assert sum((cmd&255)==pystitch.STITCH for _,_,cmd in pes.stitches)==sewn['preview']['stitches']
    for bad,contains in [({'raggedness':3},'raggedness'),({'balance':101},'balance')]:
        try:prepare(**bad)
        except urllib.error.HTTPError as e:assert contains in e.read().decode()
        else:raise AssertionError('Invalid settings accepted')
    report={'fill':{'edges':result['stats']['edges'],'stitches':result['preview']['stitches'],'cuts':result['preview']['trims']},
        'satinEdges':satin['stats']['edges'],'waveEdges':waved['stats']['edges'],'balance':'left and right verified',
        'holes':{'preservedEdges':protected['stats']['edges'],'includedEdges':included['stats']['edges']},
        'disable':'original exact stitches','seed':'repeatable and independently variable','transforms':'physical depth, rotation and mirror retained',
        'outlineAndStop':'preserved','backup':'exact PES stitches','PESReadback':'passed','validation':'passed'}
    (s.DATA/'feather-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
