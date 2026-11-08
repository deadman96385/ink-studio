"""Actual Inkscape/Ink-Stitch acceptance checks for native linked artwork."""
from verification import DATA
import copy,json,math,urllib.error,uuid
from pathlib import Path
from verify_native import api,export,rectangle

def link(source,key,kind='copy',**props):
    return {**copy.deepcopy(source),'id':key,'name':kind+' of '+source['name'],'visible':True,'locked':False,
            'link':{'kind':kind,'sourceId':source['id'],'inheritColor':True,'resolvedWidth':source['width'],'resolvedHeight':source['height'],
                    **({'params':{'distance':2,'join':'round','miter':4,'forceMiter':False}} if kind=='offset' else {})},**props}

def main():
    base={'version':1,'id':uuid.uuid4().hex,'name':'Linked artwork example','fabric':'#faf7f0','grid':True,'snap':True}
    source=rectangle(id='linked-source-example',name='Source shape',x=15,y=15,width=20,height=15,radius=2,underlay=False,spacing=.6)
    child=link(source,'linked-copy-example',x=55,y=15,rotation=25,flipX=True,name='Linked copy')
    p={**base,'layers':[copy.deepcopy(source),child]}
    # Export refreshes stale materialized copies even if the browser never did.
    p['layers'][0].update(radius=5,color='#416580',spacing=.75,width=24)
    resolved=api('/api/linked-resolve',{'project':p});r=resolved['layers'][1]
    assert r['radius']==5 and r['spacing']==.75 and r['color']=='#416580' and r['width']==24
    assert r['x']+r['width']/2==65 and r['rotation']==25 and r['flipX'] is True
    manual=copy.deepcopy(resolved)
    for l in manual['layers']:l.pop('link',None)
    actual=export(p)['preview'];expected=export(manual)['preview'];assert actual['segments']==expected['segments']
    # Independent color, source visibility, chain resolution in reverse layer order.
    r['link']['inheritColor']=False;r['color']='#b96548';resolved['layers'][0]['visible']=False
    third=link(r,'linked-chain',x=50,y=50);resolved['layers'].insert(0,third)
    chained=api('/api/linked-resolve',{'project':resolved});assert chained['layers'][0]['color']=='#b96548'
    assert chained['layers'][-1]['visible'] is True
    # Live offset geometry must match the existing native engine operation.
    offset=link(source,'linked-offset-example','offset',name='Linked offset',x=20,y=55)
    p={**base,'layers':[source,offset]};generated=api('/api/linked-resolve',{'project':p,'previewId':offset['id']})
    result=generated['project'];o=result['layers'][1]
    independent=api('/api/operate',{'tool':'path_offset','layers':[source],'params':{'distance':2}})['layers'][0]
    assert o['contours']==independent['contours'] and abs(o['width']-24)<.01 and abs(o['height']-19)<.01
    assert math.isclose(o['x'],18,abs_tol=.00001) and math.isclose(o['y'],53,abs_tol=.00001)
    for _ in range(4):assert api('/api/linked-resolve',{'project':result})==result
    # Changing source size/radius updates inset geometry and keeps a resized copy's ratio.
    o['width']*=1.2;o['height']*=1.2;o['rotation']=20;o['flipY']=True
    result['layers'][0].update(width=26,radius=4)
    changed=api('/api/linked-resolve',{'project':result});co=changed['layers'][1];assert math.isclose(co['width'],36,abs_tol=.01)
    before=export(changed)['preview'];restored=api('/api/restore',{'project':api('/api/backup',{'project':changed})})
    after=export(restored)['preview'];assert before['segments']==after['segments'];assert restored['layers'][1]['link']==co['link']
    errors={}
    for label,mutator in [('cycle',lambda q:q['layers'][0].update(link={'kind':'copy','sourceId':q['layers'][1]['id']})),
                          ('missing',lambda q:q['layers'][1]['link'].update(sourceId='absent')),
                          ('removed inset',lambda q:q['layers'][1]['link']['params'].update(distance=-20))]:
        q=copy.deepcopy(result);mutator(q)
        try:api('/api/linked-resolve',{'project':q});raise AssertionError(label+' accepted')
        except urllib.error.HTTPError as e:errors[label]=json.load(e)['error']
    assert 'circular' in errors['cycle'] and 'missing' in errors['missing'] and 'removes' in errors['removed inset']
    # An open-path offset retains the engine's lateral displacement.
    line={'id':'line','name':'Line','type':'path','x':15,'y':15,'width':20,'height':.2,'rotation':0,'stitch':'running','color':'#203f38','stitchLength':2.5,
          'contours':[{'closed':False,'nodes':[{'x':0,'y':0,'in':[0,0],'out':[0,0]},{'x':1,'y':0,'in':[1,0],'out':[1,0]}]}]}
    lp={**base,'layers':[line,link(line,'line-offset','offset')]};lo=api('/api/linked-resolve',{'project':lp})['layers'][1]
    plain=api('/api/operate',{'tool':'path_offset','layers':[line],'params':{'distance':2}})['layers'][0]
    assert math.isclose(lo['x'],plain['x'],abs_tol=1e-7) and math.isclose(lo['y'],plain['y'],abs_tol=1e-7)
    # Multiline lettering follows text, alignment and dimensions without scaling stitches.
    letters=api('/api/lettering',{'font':'small_font','text':'A\nB','scale':100,'align':'center','lineSpacing':2,'letterSpacing':0})
    text={'id':'text','type':'text','name':'Multiline source','x':15,'y':15,'width':letters['width'],'height':letters['height'],
          'rotation':0,'color':'#416580','lettering':letters['settings']}
    text_project={**base,'layers':[text,link(text,'text-copy',x=50,y=50)]}
    revised=api('/api/lettering',{**letters['settings'],'text':'AB\nBA','align':'right','lineSpacing':3})
    text.update(width=revised['width'],height=revised['height'],lettering=revised['settings'],visible=False)
    text_project=api('/api/linked-resolve',{'project':text_project});text_copy=text_project['layers'][1]
    assert text_copy['lettering']['text']=='AB\nBA' and text_copy['lettering']['align']=='right' and text_copy['width']==text['width']
    text_preview=export(text_project)['preview'];text_copy.pop('link')
    assert text_preview['segments']==export({**base,'layers':[text_copy]})['preview']['segments']
    # Keep one useful project for native-browser acceptance and user exploration.
    p={**base,'layers':[source,link(source,'linked-copy-example',x=55,y=15,name='Linked copy'),link(source,'linked-offset-example','offset',x=20,y=55,name='Linked offset')]}
    p=api('/api/linked-resolve',{'project':p});api('/api/save',{'project':p})
    report={'project':p['id'],'staleCopyExportExact':True,'copyStitches':actual['stitches'],'offsetPreviewStitches':generated['preview']['stitches'],
            'sourceResizeOffsetWidth':co['width'],'backupExact':True,'backupStitches':before['stitches'],'openOffsetMatchesInkscape':True,
            'multilineLinkedStitches':text_preview['stitches'],'multilineExactIndependentPES':True,'rejected':errors}
    (DATA / 'linked-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
