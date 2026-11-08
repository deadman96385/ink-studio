"""Real bitmap tracing, non-sewing references, and portable image acceptance checks."""
from verification import DATA
import base64,copy,io,json,tempfile,urllib.error
from pathlib import Path
from types import SimpleNamespace
from PIL import Image,ImageDraw,ImageCms
from pillow_heif import register_heif_opener
from verify_native import api,export,rectangle

def reject(path,data,contains):
    try:api(path,data)
    except urllib.error.HTTPError as e:
        body=e.read().decode();assert contains in body,(contains,body)
    else:raise AssertionError('Expected rejection: '+path)

def main():
    picture=Image.new('RGBA',(300,220),'white');draw=ImageDraw.Draw(picture)
    draw.ellipse((25,35,165,175),fill='#40647e');draw.rectangle((145,50,270,150),fill='#b76447')
    buf=io.BytesIO();picture.save(buf,format='PNG')
    info=api('/api/import-image',{'name':'Trace acceptance','data':base64.b64encode(buf.getvalue()).decode()})
    # Browser photos respect orientation and very large sources are normalized.
    photo=Image.new('RGB',(8,4),'blue');exif=Image.Exif();exif[274]=6;exif[315]='Private test author'
    jpeg=io.BytesIO();photo.save(jpeg,format='JPEG',exif=exif,icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
    oriented=api('/api/import-image',{'data':base64.b64encode(jpeg.getvalue()).decode()})
    assert (oriented['pixelWidth'],oriented['pixelHeight'])==(4,8)
    clean_photo=Image.open((DATA / 'images')/(oriented['key']+'.bin'))
    assert not clean_photo.getexif() and 'icc_profile' not in clean_photo.info
    register_heif_opener(thumbnails=False)
    heic=io.BytesIO();picture.convert('RGB').save(heic,format='HEIF',quality=95)
    heic_info=api('/api/import-image',{'name':'iPad photo.heic','data':base64.b64encode(heic.getvalue()).decode()})
    assert (heic_info['pixelWidth'],heic_info['pixelHeight'])==(300,220)
    (DATA/'trace-sample.heic').write_bytes(heic.getvalue())
    wide=io.BytesIO();Image.new('RGBA',(1800,900),(20,100,80,125)).save(wide,format='PNG')
    resized=api('/api/import-image',{'data':base64.b64encode(wide.getvalue()).decode()})
    assert (resized['pixelWidth'],resized['pixelHeight'])==(1600,800)
    normalized=Image.open((DATA / 'images')/(resized['key']+'.bin'))
    assert normalized.getpixel((800,400))[3]==125
    ref={'id':'reference','type':'image','name':'Trace acceptance','image':info['key'],'pixelWidth':300,'pixelHeight':220,
         'x':20,'y':25,'width':60,'height':44,'opacity':.45,'color':'#203f38','locked':True,'crop':[0,0,1,1]}
    project={'version':1,'id':'reference-verification','name':'Reference verification','layers':[ref]}
    trace=lambda layer=ref,**params:api('/api/trace-image',{'layer':copy.deepcopy(layer),'params':params})
    result=trace(mode='colors',colors=3)
    assert len(result['layers'])==2 and result['nodes']<100,result['nodes']
    # Quantization/smoothing can shift channel values slightly at boundaries.
    rgb=lambda color:tuple(int(color[i:i+2],16) for i in (1,3,5))
    colors=[rgb(l['color']) for l in result['layers']]
    assert all(min(sum((a-b)**2 for a,b in zip(rgb(expected),actual)) for actual in colors)<100 for expected in ['#40647e','#b76447']),colors
    assert all(l['type']=='path' and l['stitch']=='fill' for l in result['layers'])
    preview=result['preview'];assert preview['stitches']>1000 and abs(preview['width']-49)<.3
    colored={**project,'layers':[ref,*result['layers']]}
    saved=api('/api/backup',{'project':colored});assert len(saved['embeddedImages'])==1
    restored=api('/api/restore',{'project':saved})
    assert export(restored)['preview']['segments']==export(colored)['preview']['segments']
    # Restore without the original store; the source bytes must remain exact.
    from references import restore_images
    import server as s
    with tempfile.TemporaryDirectory() as temp:
        backend=SimpleNamespace(DATA=Path(temp),safe_id=s.safe_id,number=s.number,asset_layers=s.asset_layers,write_atomic=s.write_atomic)
        backup=copy.deepcopy(saved);restore_images(backup,backend)
        exact=base64.b64decode(saved['embeddedImages'][0]['data'])
        assert (Path(temp)/'images'/(info['key']+'.bin')).read_bytes()==exact
        assert 'embeddedImages' not in backup
    image_only=api('/api/restore',{'project':api('/api/backup',{'project':project})});assert image_only['layers'][0]['type']=='image'
    export(project,expect_error='visible stitched layer')
    shape=rectangle(id='only-sewing',x=35,y=40,width=15,height=10)
    plain=export({**project,'layers':[shape]})['preview']
    outside={**ref,'x':-80,'y':-80}
    assert export({**project,'layers':[outside,shape]})['preview']['segments']==plain['segments']
    # Crop to the colored rectangle, preserving the original image's scale.
    cropped={**ref,'crop':[.6,.25,.85,.6],'x':56,'y':36,'width':15,'height':15.4,'rotation':90,'flipX':True}
    crop_trace=trace(cropped,mode='threshold',threshold=150,smooth=False)
    assert abs(crop_trace['preview']['width']-15.4)<.3 and abs(crop_trace['preview']['height']-15)<.3,crop_trace['preview']
    b=crop_trace['layers'][0];assert abs(b['x']-55.8)<.3 and abs(b['y']-36.2)<.3,(b['x'],b['y'])
    mono=trace(mode='threshold',threshold=105,smooth=False)
    darker=trace(mode='threshold',threshold=150,smooth=False)
    assert mono['preview']['stitches']<darker['preview']['stitches']
    inverted=trace(mode='threshold',threshold=150,invert=True)
    assert inverted['preview']['width']>=59.5
    background=trace(mode='colors',colors=3,removeBackground=False)
    assert len(background['layers'])==3 and abs(background['preview']['width']-60)<.3
    stacked=trace(mode='colors',colors=3,stack=True)
    assert stacked['preview']['stitches']>preview['stitches']
    center=trace(mode='centerline',threshold=150)
    assert center['layers'] and center['preview']['stitches']>0
    assert all(l.get('originalFill') is False or l['stitch']=='running' for l in center['layers'])
    reject('/api/import-image',{'data':'invalid'},'base64')
    reject('/api/trace-image',{'layer':{**ref,'crop':[0,0,0,1]}},'1%')
    reject('/api/trace-image',{'layer':ref,'params':{'colors':3.5}},'whole number')
    corrupt=copy.deepcopy(saved);corrupt['embeddedImages'][0]['data']=base64.b64encode(b'broken').decode()
    reject('/api/restore',{'project':corrupt},'invalid reference image')
    report={'colorTrace':{'layers':2,'nodes':result['nodes'],'stitches':preview['stitches'],'size':[preview['width'],preview['height']]},
            'silhouetteStitches':[mono['preview']['stitches'],darker['preview']['stitches']],
            'centerlines':{'layers':len(center['layers']),'stitches':center['preview']['stitches']},
            'backgroundStitches':background['preview']['stitches'],'stackedStitches':stacked['preview']['stitches'],
            'cropRotateMirror':'physical dimensions and position match','backup':'exact image bytes and stitches',
            'imageImport':'HEIC, EXIF orientation, color profiles, dimensions, transparency and metadata removal passed',
            'references':'never stitch or affect hoop bounds','validation':'passed'}
    (DATA/'reference-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
