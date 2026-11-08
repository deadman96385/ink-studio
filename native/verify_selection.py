"""Installed-engine selection filters, nested-path exposure and input isolation."""
from verification import DATA
import copy,json
from pathlib import Path
import server as s
from selection import query
from verify_native import rectangle,api,export
from verify_linked import link
import pystitch

def main():
    fills=[rectangle(id=method,name=method,x=5+i*10,y=5,width=8,height=8,fillMethod=method,underlay=i%2==0) for i,method in enumerate(['tatami_fill','circular_fill','contour_fill','guided_fill','linear_gradient_fill','meander_fill','tartan_fill','legacy_fill','cross_stitch'])]
    strokes=[rectangle(id=mode,name=mode,x=5+i*12,y=30,width=8,height=8,stitch=mode) for i,mode in enumerate(['running','bean','manual','ripple','zigzag'])]
    satins=[]
    for i,method in enumerate(['satin_column','e_stitch','s_stitch','zigzag']):
        satins.append({'id':'satin-'+method,'name':method,'type':'path','stitch':'satin','x':10+i*20,'y':55,'width':15,'height':3,'color':'#203f38','satinCenter':i==0,'satinContour':i==1,'satinZigzag':i==2,'advanced':{'satin_method':method},'contours':[{'closed':False,'nodes':[{'x':x,'y':y,'in':[x,y],'out':[x,y]} for x in [0,1]]} for y in [0,1]]})
    satin_rungs=copy.deepcopy(satins[0]);satin_rungs.update(id='satin-rungs',name='Two rungs',y=70)
    satin_rungs['contours'] += [{'closed':False,'nodes':[{'x':x,'y':y,'in':[x,y],'out':[x,y]} for y in [0,1]]} for x in [.33,.66]]
    clone=link(fills[0],'linked-fill',y=80)
    p={'version':1,'id':'selection-fixtures','layers':fills+strokes+satins+[satin_rungs,clone]};report={}
    def find(types,expected,**options):
        before=copy.deepcopy(p);r=query({'project':p,'options':{'types':types,**options}},s);assert p==before
        ids=r['selectedIds'];assert set(ids)==set(expected),(types,options,ids,expected)
        report[str(types)+str(options)]=ids;print(types,options,ids,flush=True);return r
    for key,id in [('circular-fill','circular_fill'),('contour-fill','contour_fill'),('guided-fill','guided_fill'),('linear-gradient-fill','linear_gradient_fill'),('meander-fill','meander_fill'),('tartan-fill','tartan_fill'),('legacy-fill','legacy_fill'),('cross-fill','cross_stitch')]:find([key],[id])
    find(['tatami-fill'],['tatami_fill','linked-fill'])
    find(['tatami-fill'],[],fillUnderlay='no');find(['cross-fill'],[],fillUnderlay='no')
    find(['running-stitch'],['running','bean']);find(['running-stitch'],['bean'],beanRepeats='1');find(['running-stitch'],['running'],beanRepeats='0')
    for key,id in [('manual','manual'),('ripples','ripple'),('zigzag','zigzag'),('e','satin-e_stitch'),('s','satin-s_stitch'),('satin-zigzag','satin-zigzag')]:find([key],[id])
    find(['satin'],['satin-satin_column','satin-rungs']);find(['satin'],['satin-satin_column'],rungCount='zero');find(['satin'],['satin-rungs'],rungCount='two')
    find(['satin','e','s','satin-zigzag'],['satin-e_stitch'],satinUnderlay='contour');find(['satin','e','s','satin-zigzag'],['satin-zigzag'],satinUnderlay='no')
    find(['clone'],['linked-fill']);find(['running-stitch'],['bean'],scopeIds=['bean','tatami_fill'])
    strokes[0]['locked']=True;find(['running-stitch'],['bean']);find(['running-stitch'],['running','bean'],includeLocked=True);strokes[0].pop('locked')
    strokes[0]['visible']=False;find(['running-stitch'],['bean']);strokes[0].pop('visible')
    strokes[0]['advanced']={'path_type':'autorun-top'}
    # path_type is generated engine metadata, not an editable Advanced field.
    strokes[0].pop('advanced');strokes[0].update(stitch='original',originalFill=False,originalStroke=True,originalParams={'stroke_method':'running_stitch','path_type':'redwork-top'})
    find(['running-stitch'],['running'],runningCondition='autorun-top')
    strokes[0]['originalParams']['path_type']='satin-underpath';find(['running-stitch'],['running'],runningCondition='autosatin-underpath')
    strokes[0]['originalParams']['path_type']='redwork-underpath';find(['running-stitch'],['running'],runningCondition='autorun-underpath')
    # Fill and outline remain two separate editable paths, with only the outline selected.
    bordered=rectangle(id='bordered',name='Fill with outline',x=20,y=20,width=20,height=15,underlay=False,borderEnabled=True,borderStitch='bean',borderColor='#416580')
    guide={'id':'hidden-guide','role':'guide-line','helperTarget':'bordered','type':'path','name':'Hidden guide','visible':False,'x':10,'y':15,'width':40,'height':5,'points':[[0,0],[1,1]],'stitch':'running','color':'#83759d'}
    mixed={'version':1,'id':'mixed-selection','layers':[bordered,guide]};r=query({'project':mixed,'options':{'types':['running-stitch'],'exposePaths':True}},s)
    assert r['matches'][0]['matchedPaths']==1 and r['matches'][0]['totalPaths']==2
    assert len(r['selectedIds'])==1 and len(r['replacements']['bordered'])==4 and r['removeIds']==['hidden-guide']
    selected=next(l for l in r['replacements']['bordered'] if l['id'] in r['selectedIds']);assert selected['color']=='#416580' and not selected['originalFill']
    # Comparison is against the real exporter, including independent PES decoding.
    before=export(mixed);after=export({**mixed,'layers':r['replacements']['bordered']})
    read=lambda ex:pystitch.read(str((DATA / 'exports'))+'/'+Path(ex['pes']).name)
    assert read(before).stitches==read(after).stitches
    restored=api('/api/restore',{'project':api('/api/backup',{'project':{**mixed,'layers':r['replacements']['bordered']}})});assert read(export(restored)).stitches==read(after).stitches
    # Exposing a matching native layer must not attempt to flatten unrelated gradients.
    query({'project':{**mixed,'layers':[bordered,fills[4]]},'options':{'types':['running-stitch'],'exposePaths':True}},s)
    report.update(result='passed',exposeOnlyMatchingPaths=True,hiddenHelpersRetained=True,exposureExactPES=True,backupExactPES=True,inputUnchanged=True)
    (DATA / 'selection-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('All selection and exposure checks passed',flush=True)
if __name__=='__main__':main()
