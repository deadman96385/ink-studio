"""Real PES, non-botanical reuse, edits, pauses and source-tool integration."""
import copy,json
from pathlib import Path
import server as s
from verify_native import api,export,rectangle
from sewing_optimizer import settings

def line(id,x,y,end):
    return {'id':id,'name':id,'type':'path','x':x,'y':y,'width':end-x,'height':.2,'points':[[0,0],[1,0]],'color':'#286b45',
        'stitch':'running','stitchLength':2,'trimAfter':True}

def main():
    p={'version':1,'id':'optimizer-reuse-fixture','name':'Reusable sewing fixture','layers':[line('a',10,20,20),line('b',20,20,30),line('c',50,40,60)]}
    before=export(p)['preview'];chosen=settings({},s);result=api('/api/optimize-sewing',{'project':p,'settings':chosen})
    assert result['stats']['accepted'] and result['preview']['trims']<before['trims'],result['stats']
    q={**p,'sewingOptimization':chosen};after=export(q)['preview'];assert after['segments']==result['preview']['segments']
    original=s.build_svg(p);assert s.build_svg(q)==original
    report=api('/api/element-info',{'project':q});assert report['inspectedLayers']==3,report
    restored=api('/api/restore',{'project':api('/api/backup',{'project':q})});assert export(restored)['preview']['segments']==after['segments']
    off={**q,'sewingOptimization':{**chosen,'enabled':False}};assert export(off)['preview']['segments']==before['segments']
    # Moving the touching section invalidates the derived route. The new exposed
    # gap must regain its trim, without needing to hand-edit a hidden connector.
    moved=copy.deepcopy(q);moved['layers'][1]['x']+=7;changed=export(moved)['preview'];assert changed['trims']>=before['trims']
    paused=copy.deepcopy(q);paused['layers'][0]['stopAfter']=True;assert export(paused)['preview']['stops']==1
    # Coverage cannot come from a sparse flow layer or an altered fill setting.
    altered=rectangle(id='advanced',advanced={'max_stitch_length_mm':4})
    from sewing_optimizer import configuration
    config=configuration({'layers':[altered]},s.xml(s.build_svg({'version':1,'layers':[altered]})),chosen,s);assert not config['masks']
    for value in ({'version':2},{'maxBridge':float('nan')},{'maxBridge':9},{'connect':'yes'},{'unknown':True}):
        try:settings(value,s)
        except ValueError:pass
        else:raise AssertionError(value)
    bad={**q,'origin':[20,20]}
    try:s.build_svg(bad,sewing=True)
    except ValueError as e:assert 'origin' in str(e)
    else:raise AssertionError('Custom origin accepted')
    result={'reusableNonBotanicalFixture':True,'beforeCuts':before['trims'],'afterCuts':after['trims'],'sourceToolsRetained':True,
        'editedGapRegainsCut':True,'pauseRetained':True,'disabledExactBaseline':True,'portableBackupExact':True,'invalidSettingsRejected':True}
    (s.DATA/'sewing-optimizer-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
