"""Real border stitches, patches/appliqué, editable outlines and exact backups."""
import copy,json,urllib.error
from pathlib import Path
import pystitch
from digitizing import inkex,from_path
from verify_native import api,export,rectangle
import server as s


def reject(path,data,contains):
    try:api(path,data)
    except urllib.error.HTTPError as e:assert contains in e.read().decode(),contains
    else:raise AssertionError('Expected rejection: '+contains)


def main():
    source=rectangle(id='merrow-outline',name='Border sample',x=20,y=25,width=60,height=40,radius=7)
    project={'version':1,'id':'merrow-verification','name':'Faux merrow verification','fabric':'#faf7f0','layers':[source]}
    def border(layer=source,**settings):return api('/api/merrow',{'layer':copy.deepcopy(layer),'settings':settings,'color':'#b49a57'})
    result=border();edge=result['layer'];assert edge['merrowSourceId']==source['id'] and edge['contours']
    assert result['stats']['fans']>50 and result['preview']['stitches']>800
    assert abs(result['preview']['width']-63)<.2 and abs(result['preview']['height']-43)<.2
    fine=border(spacing=.2);coarse=border(spacing=.8);assert fine['preview']['stitches']>coarse['preview']['stitches']
    flipped=border(side='outside');assert flipped['preview']['segments']!=result['preview']['segments']
    changed=border(edge,fanLength=3.2,spread=.5,bindingDepth=.7,underlay='full');assert changed['layer']['id']==edge['id']
    assert changed['preview']['segments']!=result['preview']['segments']
    hole=from_path(inkex.Path('M20,20 H80 V80 H20 Z M35,35 H65 V65 H35 Z'),{'color':'#326480','stitch':'fill','name':'Hole sample'})
    holed=border(hole);assert holed['stats']['outlines']==2
    # A node editor must expose the closed backbone, not thousands of needle points.
    nodes=api('/api/vector',{'operation':'nodes','layers':[edge]})['layers'][0]
    assert all(c['closed'] for c in nodes['contours']) and sum(len(c['nodes']) for c in nodes['contours'])<40
    moved={**edge,'x':27,'y':30,'width':48,'height':32,'rotation':20,'flipX':True}
    repositioned=border(moved);assert repositioned['layer']['rotation']==20 and repositioned['layer']['flipX'] is True
    assert repositioned['layer']['merrow']['width']==3,'Resizing must regenerate physical border width'
    sewn=export({**project,'layers':[source,edge]});backup=api('/api/backup',{'project':{**project,'layers':[source,edge]}})
    restored=api('/api/restore',{'project':backup});again=export(restored)
    assert sewn['preview']['segments']==again['preview']['segments']
    pes=pystitch.read(str(s.DATA/'exports'/Path(sewn['pes']).name))
    assert sum((command&255)==pystitch.STITCH for _,_,command in pes.stitches)==sewn['preview']['stitches']
    cases=[]
    for construction in ('embroidered','applique'):
        value=api('/api/components',{'kind':'patch','params':{'borderStyle':'merrow','construction':construction,'shape':'shield','width':55,'height':65}})
        assert value['layers'][-1]['merrow'] and value['layers'][-1]['component']['part']=='edge'
        pv=api('/api/layer-preview',{'layers':value['layers']})['preview'];assert pv['stitches']>800
        if construction=='applique':assert pv['stops']>=1
        rebuilt=api('/api/components',{'kind':'patch','params':{'borderStyle':'merrow','construction':construction,'shape':'shield','width':55,'height':65,'merrowSpread':50},'targets':value['layers']})
        assert [l['id'] for l in rebuilt['layers']]==[l['id'] for l in value['layers']]
        cases.append({'construction':construction,'stitches':pv['stitches'],'stops':pv['stops']})
    reject('/api/merrow',{'layer':source,'settings':{'width':0}},'Border width')
    reject('/api/merrow',{'layer':source,'settings':{'spacing':0}},'Fan stitch spacing')
    reject('/api/merrow',{'layer':source,'settings':{'width':1,'bindingDepth':2}},'80%')
    reject('/api/merrow',{'layer':{**source,'locked':True}},'unlock')
    open_path=from_path(inkex.Path('M20,20 L60,20 L60,60'),{'color':'#123456','stitch':'running'})
    reject('/api/merrow',{'layer':open_path},'closed outlines')
    outside={**source,'x':0};reject('/api/merrow',{'layer':outside},'100 mm hoop')
    report={'border':{'stitches':result['preview']['stitches'],'fans':result['stats']['fans'],'size':[result['preview']['width'],result['preview']['height']]},
        'densityStitches':[fine['preview']['stitches'],coarse['preview']['stitches']],'holes':2,'nodeEditing':'closed editable backbone',
        'transforms':'physical width, rotation and mirror retained','patches':cases,'backup':'exact PES stitches','PESReadback':'passed','validation':'passed'}
    (s.DATA/'merrow-verification.json').write_text(json.dumps(report,indent=2))
    (s.DATA/'merrow-ui-fixture.json').write_text(json.dumps(project))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
