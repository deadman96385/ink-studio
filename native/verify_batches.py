"""Actual-engine batch acceptance: templates, partial failures, resume and files."""
from verification import DATA, BASE as VERIFY_BASE
import copy
import io
import json
from pathlib import Path
import time
import urllib.request
import uuid
import zipfile
from verify_native import api,export,sewing

BASE=VERIFY_BASE


def get(path):return json.load(urllib.request.urlopen(BASE+path,timeout=300))
def read(path):return urllib.request.urlopen(BASE+path,timeout=300).read()
def wait(key):
    for _ in range(900):
        v=get('/api/batch-jobs/'+key)
        if v['state'] not in ('queued','working'):return v
        time.sleep(.3)
    raise AssertionError('Batch did not finish')


if __name__=='__main__':
    settings={'font':'small_font','text':'AB','scale':100,'align':'center','trim':'glyph','commandSymbols':True}
    text=api('/api/lettering',settings)
    layer=dict(id='batch-text',type='text',name='AB',x=42,y=40,width=text['width'],height=text['height'],rotation=15,color='#123456',lettering=text['settings'],visible=True)
    frame=dict(id='batch-frame',type='rectangle',name='Frame',x=30,y=30,width=40,height=35,rotation=0,color='#336655',stitch='running',stitchLength=2.5,visible=True,stopAfter=True)
    template=dict(version=1,id='batch-template-verification',name='Batch template verification',fabric='#ece4d2',layers=[frame,layer])
    original=copy.deepcopy(template)
    req=dict(mode='lettering',name='Batch acceptance verification',text='A B\nA B C\n\nA B\nA B C\n\n☃',separator='paragraphs',template=template,target='batch-text',anchor='left',verticalAnchor='top',color='#123456',lettering={**settings,'align':'block'},formats=['pes','dst','svg','col'])
    key=api('/api/batches',req)['id'];v=wait(key)
    assert v['state']=='partial' and [r['state'] for r in v['items']]==['done','done','error'],v
    first=get('/api/batch-jobs/'+key+'/0');second=get('/api/batch-jobs/'+key+'/1')
    assert first['export']['preview']==second['export']['preview'],'Duplicate names changed stitches'
    p=first['design'];assert p['layers'][0]==frame and p['fabric']==template['fabric'] and template==original
    assert p['layers'][1]['lettering']['text']=='A B\nA B C' and p['layers'][1]['lettering']['align']=='block' and p['layers'][1]['lettering']['commandSymbols']
    assert first['export']['preview']['stops']>=1
    assert any(t['color']=='#123456' for t in first['export']['preview']['threads'])
    assert read(first['files']['pes']).startswith(b'#PES0060')
    bundle=read(v['bundle'])
    with zipfile.ZipFile(io.BytesIO(bundle)) as z:
        names=z.namelist();assert len(names)==len(set(names))
        assert sum(n.endswith('.pes') for n in names)==2 and sum(n.endswith('.dst') for n in names)==2
        report=json.loads(z.read('batch-report.json'));assert report['items'][2]['state']=='error'
    backup=json.loads(read(first['files']['project.json']));restored=api('/api/restore',{'project':backup})
    assert sewing(export(restored)['preview'])==sewing(first['export']['preview'])
    saved=api('/api/batch-save',{'id':key})['ids'];assert len(saved)==2
    edited=get('/api/projects/'+saved[0]);edited['name']='Batch acceptance edited verification';api('/api/save',{'project':edited})
    api('/api/batch-save',{'id':key});assert get('/api/projects/'+saved[0])['name']==edited['name']
    print('Multiline templates, justification, symbols, RGB/PES, ZIP names, partial errors and portable edits passed',flush=True)
    # Export saved projects, not just lettering, while retaining exact stitches.
    export_key=api('/api/batches',{'mode':'projects','name':'Batch saved export verification','projects':saved,'formats':['pes','jef']})['id'];exports=wait(export_key)
    assert exports['state']=='done',exports
    assert get('/api/batch-jobs/'+export_key+'/0')['export']['preview']==first['export']['preview']
    print('Saved-project batch exports preserve the design stitch plan',flush=True)
    # Cancellation finishes the running engine operation and retains its output.
    cancel_key=api('/api/batches',{**req,'name':'Batch cancellation verification','separator':'lines','text':'\n'.join(['AB']*16),'formats':['pes']})['id']
    for _ in range(900):
        live=get('/api/batch-jobs/'+cancel_key)
        if any(r['ready'] for r in live['items']):break
        time.sleep(.1)
    assert live['state'] in ('queued','working'),live
    api('/api/batch-cancel',{'id':cancel_key});cancelled=wait(cancel_key);assert cancelled['state']=='cancelled',cancelled
    complete={r['index']:get('/api/batch-jobs/'+cancel_key+'/'+str(r['index']))['export']['id'] for r in cancelled['items'] if r['ready']}
    assert complete
    api('/api/batch-resume',{'id':cancel_key});resumed=wait(cancel_key);assert resumed['state']=='done',resumed
    for i,eid in complete.items():assert get('/api/batch-jobs/'+cancel_key+'/'+str(i))['export']['id']==eid
    print('Cancellation and continuation keep completed exports without regenerating them',flush=True)
    result={'partialBatch':key,'savedExportBatch':export_key,'cancelResumeBatch':cancel_key,'savedProjects':saved,'multilineTemplate':True,'justifyWords':True,'commandSymbols':True,'pesV6Rgb':True,'duplicateNamesHaveDistinctFiles':True,'badEntryDoesNotLoseSuccesses':True,'portableStitchesExact':True,'saveDoesNotOverwriteEdits':True,'savedDesignExportsExact':True,'cancelResumeKeepsCompletedExports':len(complete),'templateUnchanged':True}
    (DATA / 'batch-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
