"""Exercise native print settings and compare against installed desktop print data."""
from verification import pdf_text
import base64,copy,hashlib,io,json,re,shutil,tempfile,urllib.request,urllib.error
from pathlib import Path
from lxml import etree as ET,html as LH
from PIL import Image
from weasyprint import HTML
from verify_native import api,export,rectangle,BASE
import server as s
import print_work as pw
from print_render import render,estimates

def main():
    project=api('/api/projects/export-options-example');project['id']='print-workspace-example';project['name']='Native print workspace example'
    original=export(project);report=pw.engine_data(original['id'],'',s,reference=True)
    folder=s.DATA/'print-assets'/report['key'];desktop=LH.fromstring((folder/'desktop.html').read_text(encoding='utf-8'))
    text=desktop.text_content()
    assert report['stitches']==252 and report['machine']['stitches']==246 and report['trims']==2 and report['stops']==1
    assert 'Océan' in text and 'Rose' in text and '141' in text and '111' in text
    # Geometry and styles come verbatim from both installed renderer modes.
    svgs=desktop.xpath('//*[local-name()="svg"]')
    reference_paths={e.get('d') for mode in ['simple','realistic'] for e in ET.parse(str(folder/('desktop-'+mode+'.svg'))).xpath('//*[local-name()="path"]')}
    for name in ['simple-overview.svg','realistic-overview.svg','simple-0.svg','simple-1.svg']:
        root=ET.parse(str(folder/name));paths=root.xpath('//*[local-name()="path"]')
        assert paths and all(e.get('d') in reference_paths for e in paths),name
    palettes=api('/api/palettes');brother=next(p for p in palettes if p['name']=='Brother Embroidery')
    mapped=api('/api/print-data',{'id':original['id'],'palette':brother['key']})
    assert [b['color'] for b in mapped['blocks']]==[b['color'] for b in report['blocks']]
    assert all(b['brand']=='Brother Embroidery' and b['number'] for b in mapped['blocks'])
    svg=b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="30"><rect width="100" height="30" rx="5" fill="#23503e"/><text x="8" y="21" font-size="17" fill="white">STUDIO</text></svg>'
    logo=api('/api/print-logo',{'name':'studio.svg','data':base64.b64encode(svg).decode()})['logo']
    assert Image.open(io.BytesIO(base64.b64decode(logo.split(',')[1]))).size==(1000,300)
    opts=pw.settings({'layouts':pw.LAYOUTS,'title':'Embroidery print sample','client':'Studio client','purchaseOrder':'P-104','date':'2026-10-31',
        'notes':{'0':'Test on matching fabric before sewing the full design.','1':'Change to rose thread.'},'patternFooter':True,
        'placements':{'pattern':{'scale':100,'realistic':True}},'custom':'<h2>Finishing instructions</h2><ol><li>Remove the stabilizer carefully.</li><li>Press from the reverse.</li></ol>',
        'showTime':['clientOverview','clientDetail','operatorOverview','operatorDetail'],'logo':logo,
        'footer':'<p><b>Studio embroidery</b> · <a href="mailto:studio@example.com">studio@example.com</a></p>'},s)
    assert estimates(report,opts)['time']=='00:00:52'
    assert estimates(report,{**opts,'speed':0,'trimSeconds':0,'colorSeconds':0,'extraSeconds':0})['seconds']==252
    assert estimates(report,{**opts,'speed':1200,'extraSeconds':40})['seconds']==82.6
    api('/api/print-settings',{'id':original['id'],'settings':opts})
    assert api('/api/print-context/'+original['id'])['settings']==opts
    project['printSettings']=opts;api('/api/save',{'project':project})
    assert api('/api/projects/'+project['id'])['printSettings']==opts
    backup=api('/api/backup',{'project':project});restored=api('/api/restore',{'project':backup});assert restored['printSettings']==opts
    output=export(restored)
    assert output['preview']['segments']==original['preview']['segments']
    for k in ['stitches','trims','stops','threads','width','height']:assert output['preview'][k]==original['preview'][k],k
    examples={}
    for paper in ['letter','a4']:
        o={**opts,'paper':paper};r=api('/api/print-generate',{'id':original['id'],'settings':o});assert r['pages']==7,r['pages']
        path,info=pw.pdf_path(r['key'],s);width,height=(816,1056) if paper=='letter' else (210*96/25.4,297*96/25.4)
        assert all(abs(w-width)<.01 and abs(h-height)<.01 for w,h in info['sizes'])
        text=pdf_text(path,s.run)
        for value in ['Client overview','thread step 1','thread step 2','Operator overview','Operator detail','Finishing instructions','50 mm','246 needle stitches','Test on matching fabric','studio@example.com']:assert value in text,value
        assert len(text.split('\f'))==8
        for i in range(1,8):pw.page(r['key'],i,s)
        # At 100%, the colored artwork's physical size matches its 15 x 11 mm plan.
        with Image.open(pw.page(r['key'],6,s)).convert('RGB') as im:
            pixels=im.load();coords=[(x,y) for y in range(im.height//3,im.height*2//3) for x in range(im.width//3,im.width*2//3) if (lambda c:c[2]>c[1]+12 and c[0]<c[1])(pixels[x,y]) or (lambda c:c[0]>c[1]*1.3 and c[2]>c[1]+12)(pixels[x,y])]
            bounds=[min(x for x,y in coords),min(y for x,y in coords),max(x for x,y in coords),max(y for x,y in coords)]
            mm_per_pixel=(297 if paper=='a4' else 279.4)/im.height
            assert abs((bounds[2]-bounds[0]+1)*mm_per_pixel-15)<.8,bounds
            assert abs((bounds[3]-bounds[1]+1)*mm_per_pixel-11)<.8,bounds
        examples[paper]={'key':r['key'],'url':r['url'],'pages':r['pages']}
        (s.DATA/('print-'+paper+'-result.json')).write_text(json.dumps(r),encoding='utf-8')
    # Long note + largest thumbnail must paginate without losing its last line.
    long_note='\n'.join(f'Instruction {i:03d}: inspect thread tension.' for i in range(45))
    stress={**opts,'layouts':['operatorDetail','custom'],'thumbnail':110,'notes':{'0':long_note,'1':'LAST OPERATOR NOTE'},'custom':'<h2>Long instructions</h2>'+''.join(f'<p>Step {i}: inspect and finish the embroidery carefully.</p>' for i in range(100))}
    markup=render(report,stress,project,lambda i,real:pw.image_data(report,i,real,s))
    doc=HTML(string=markup).render();overflow=[]
    for n,page in enumerate(doc.pages,1):
        for box in page._page_box.descendants():
            if getattr(box,'text','') and (box.position_y<0 or box.position_y+box.height>page.height):overflow.append([n,box.text,box.position_y])
    assert not overflow,overflow[:5]
    r=api('/api/print-generate',{'id':original['id'],'settings':stress});path,_=pw.pdf_path(r['key'],s)
    text=pdf_text(path,s.run);assert 'Instruction 044' in text and 'LAST OPERATOR NOTE' in text and 'Step 99:' in text
    (s.DATA/'print-stress-result.json').write_text(json.dumps(r),encoding='utf-8')
    for i in range(1,r['pages']+1):pw.page(r['key'],i,s)
    clean=api('/api/document-cleanup',{'project':project,'options':{'metadata':True}})
    assert 'printSettings' not in clean['project'] and clean['report']['metadataEntries']==1
    # Defaults never overwrite client/job-specific fields.
    defaults_path=s.DATA/'print-defaults.json';previous=defaults_path.read_bytes() if defaults_path.exists() else None
    try:
        api('/api/print-defaults',{'settings':{**opts,'paper':'a4','speed':850}});d=api('/api/print-defaults')
        assert d['paper']=='a4' and d['speed']==850 and d['title']=='' and d['notes']=={} and d['placements']=={}
    finally:
        if previous is None:defaults_path.unlink(missing_ok=True)
        else:defaults_path.write_bytes(previous)
    cleaned=pw.settings({'custom':'<script>bad()</script><p onclick="bad()">Good <a href="javascript:bad()">link</a></p><iframe src="https://example.com"></iframe><p>Last</p>'},s)['custom']
    assert cleaned=='<p>Good <a>link</a></p><p>Last</p>',cleaned
    for bad in [{'paper':'a3'},{'layouts':['x']},{'speed':True},{'thumbnail':111},{'upperFactor':0},{'notes':{'0':'x'*2001}}, {'footer':'x'*351},{'placements':{'pattern':{'scale':True}}},{'logo':'data:image/svg+xml,<svg/>'}]:
        try:api('/api/print-settings',{'id':original['id'],'settings':bad})
        except urllib.error.HTTPError as e:assert e.code==400
        else:raise AssertionError(bad)
    cut_source=rectangle(id='print-cutwork-source',type='ellipse',x=30,y=30,width=30,height=30,stitch='running',trimAfter=True)
    cut_layers=api('/api/operate',{'tool':'cutwork_segmentation','layers':[cut_source],'params':{}})['layers']
    cut={'version':1,'id':'print-cutwork-fixture','name':'Cutwork print fixture','fabric':'#faf7f0','layers':cut_layers};cutout=export(cut)
    cuts=api('/api/print-data',{'id':cutout['id'],'palette':brother['key']})
    assert cuts['cutwork'] and all(b['name'].startswith('Cut ') for b in cuts['blocks']),cuts
    result={'result':'passed','exampleExport':original['id'],'designSteps':report['stitches'],'PESStitches':report['machine']['stitches'],
        'desktopGeometryAndCounts':True,'allSixLayouts':True,'actualSizePattern':True,'examples':examples,'stressPages':r['pages'],'longNotesAndCustomPagination':True,
        'paletteNamesAndCutLabels':True,'svgLogo':True,'settingsDefaultsBackupRoundTrip':True,'printPreservesPES':True,'sanitizationAndBounds':True}
    (s.DATA/'print-work-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
