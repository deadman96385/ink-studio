"""Non-sewing reference images and installed Inkscape bitmap tracing."""
import base64
from limits import MAX_LAYERS
import copy
import hashlib
import io
import json
import tempfile
import uuid
import warnings
from pathlib import Path
from PIL import Image,ImageOps,ImageCms
from pillow_heif import register_heif_opener
from lxml import etree as ET

Image.MAX_IMAGE_PIXELS=25000000
register_heif_opener(thumbnails=False)

def import_image(data,s):
    value=data.get('data')
    if not isinstance(value,str) or len(value)>12*1024*1024:raise ValueError('Choose a reference image smaller than 8 MB.')
    try:raw=base64.b64decode(value,validate=True)
    except Exception:raise ValueError('This reference image is not valid base64.')
    if len(raw)>8*1024*1024:raise ValueError('Choose a reference image smaller than 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            image=Image.open(io.BytesIO(raw))
            if image.format not in ('PNG','JPEG','WEBP','GIF','BMP','TIFF','HEIF'):raise ValueError('Use a PNG, JPEG, HEIC, WebP, GIF, BMP or TIFF image.')
            image.load();image=ImageOps.exif_transpose(image)
            profile=image.info.get('icc_profile')
            if profile:
                try:image=ImageCms.profileToProfile(image,ImageCms.ImageCmsProfile(io.BytesIO(profile)),ImageCms.createProfile('sRGB'),outputMode='RGBA')
                except (OSError,ValueError,ImageCms.PyCMSError):image=image.convert('RGBA')
            else:image=image.convert('RGBA')
            image.thumbnail((1600,1600),Image.Resampling.LANCZOS)
            image.info.clear()
    except (Image.DecompressionBombError,Image.DecompressionBombWarning):raise ValueError('Use an image with fewer than 25 million pixels.')
    except (OSError,ValueError) as exc:raise ValueError('Cannot read this image. Export it as PNG or JPEG first.') from exc
    if image.width<2 or image.height<2:raise ValueError('The reference image must be at least 2 × 2 pixels.')
    # Re-encoding removes orientation/metadata and limits portable backup size.
    output=io.BytesIO();image.save(output,format='PNG',optimize=True);mime='image/png'
    if output.tell()>2*1024*1024:
        output=io.BytesIO();image.save(output,format='WEBP',quality=95,method=4);mime='image/webp'
    encoded=output.getvalue();key=hashlib.sha256(encoded).hexdigest()
    folder=s.DATA/'images';folder.mkdir(exist_ok=True)
    (folder/(key+'.bin')).write_bytes(encoded)
    metadata={'key':key,'pixelWidth':image.width,'pixelHeight':image.height,'mime':mime,'name':str(data.get('name','Reference image'))[:120]}
    s.write_atomic(folder/(key+'.json'),metadata)
    return metadata

def image_info(key,s):
    key=s.safe_id(key);path=s.DATA/'images'/(key+'.json')
    if not path.exists():raise ValueError('A reference image is missing. Import it again or restore its portable backup.')
    return json.loads(path.read_text())

def crop_settings(layer,s):
    crop=layer.get('crop',[0,0,1,1])
    if not isinstance(crop,list) or len(crop)!=4:raise ValueError('Invalid reference crop.')
    left,top,right,bottom=[s.number(n,0,1,'Image crop') for n in crop]
    if right-left<.01 or bottom-top<.01:raise ValueError('Keep at least 1% of the image in each direction.')
    return [left,top,right,bottom]

def validate_reference(layer,s):
    info=image_info(layer.get('image'),s);crop_settings(layer,s)
    for key in ('width','height'):s.number(layer.get(key),.2,100,'Reference '+key)
    for key in ('x','y'):s.number(layer.get(key),-100,200,'Reference position')
    s.number(layer.get('rotation',0),-360,360,'Reference rotation');s.number(layer.get('opacity',.45),.05,1,'Reference opacity')
    layer['pixelWidth']=info['pixelWidth'];layer['pixelHeight']=info['pixelHeight']
    return info

def embed_images(project,s):
    keys={s.safe_id(l.get('image')) for l in s.asset_layers(project) if l.get('type')=='image'}
    return [{**image_info(key,s),'data':base64.b64encode((s.DATA/'images'/(key+'.bin')).read_bytes()).decode()} for key in sorted(keys)]

def restore_images(project,s):
    embedded=project.pop('embeddedImages',[])
    if not isinstance(embedded,list) or len(embedded)>MAX_LAYERS:raise ValueError('Invalid reference image backup.')
    mapping={}
    for image in embedded:
        if not isinstance(image,dict):raise ValueError('Invalid reference image backup.')
        original=s.safe_id(image.get('key'))
        try:
            raw=base64.b64decode(image['data'],validate=True)
            if len(raw)>8*1024*1024 or hashlib.sha256(raw).hexdigest()!=original:raise ValueError('Reference checksum mismatch.')
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                picture=Image.open(io.BytesIO(raw))
                if picture.format not in ('PNG','WEBP') or not 2<=picture.width<=1600 or not 2<=picture.height<=1600:raise ValueError('Invalid saved reference dimensions or format.')
                mime='image/png' if picture.format=='PNG' else 'image/webp';width,height=picture.size;picture.verify()
        except Exception as exc:raise ValueError('This backup contains an invalid reference image.') from exc
        # Keep the exact normalized bytes: repeatedly re-encoding lossy WebP
        # during restore would change subsequent traces.
        folder=s.DATA/'images';folder.mkdir(exist_ok=True);(folder/(original+'.bin')).write_bytes(raw)
        s.write_atomic(folder/(original+'.json'),{'key':original,'pixelWidth':width,'pixelHeight':height,'mime':mime,'name':str(image.get('name','Reference image'))[:120]})
        mapping[original]=original
    for layer in s.asset_layers(project):
        if layer.get('type')=='image':
            layer['image']=mapping.get(layer.get('image'),layer.get('image'));validate_reference(layer,s)

def trace_bitmap(source,layer,options,s):
    """Trace an already prepared bitmap in the reference's physical frame."""
    from operations import editable_output
    output=io.BytesIO();source.save(output,format='PNG')
    root=s.svg_root();w,h=layer['width'],layer['height']
    group=ET.SubElement(root,'{'+s.SVG+'}g',transform=f'translate({layer["x"]} {layer["y"]}) rotate({layer.get("rotation",0)},{w/2},{h/2}) translate({w if layer.get("flipX") else 0},{h if layer.get("flipY") else 0}) scale({-1 if layer.get("flipX") else 1},{-1 if layer.get("flipY") else 1})')
    image=ET.SubElement(group,'{'+s.SVG+'}image',id='reference',x='0',y='0',width=str(w),height=str(h),preserveAspectRatio='none')
    image.set('{http://www.w3.org/1999/xlink}href','data:image/png;base64,'+base64.b64encode(output.getvalue()).decode())
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='trace-') as tmp:
        src=Path(tmp)/'source.svg';out=Path(tmp)/'traced.svg';src.write_bytes(ET.tostring(root))
        # Inkscape 1.4 needs its GDK image loader initialized for object-trace.
        s.run(['xvfb-run','-a','inkscape','--with-gui','--batch-process',str(src),
               '--actions=select-by-id:reference;object-trace:'+','.join(map(str,options))+';export-filename:'+str(out)+';export-do'],timeout=120)
        if not out.exists():raise ValueError('Tracing produced no paths. Adjust the threshold or color count.')
        return editable_output(out.read_bytes(),s,'Traced '+layer.get('name','image'))


def trace_image(data,s):
    from operations import operate
    from multisatin import layer_preview
    layer=data.get('layer');params=data.get('params',{})
    if not isinstance(layer,dict) or layer.get('type')!='image' or not isinstance(params,dict):raise ValueError('Select one reference image to trace.')
    info=validate_reference(layer,s);mode=params.get('mode','colors')
    if mode not in ('colors','threshold','centerline'):raise ValueError('Choose color regions, a silhouette, or centerlines.')
    def integer(key,default,low,high):
        n=s.number(params.get(key,default),low,high,key)
        if n!=int(n):raise ValueError(key+' must be a whole number.')
        return int(n)
    scans=integer('colors',4,2,16) if mode=='colors' else 2
    speckles=integer('speckles',4,0,128);threshold=integer('threshold',140,0,255)
    corners=s.number(params.get('corners',1),0,1.34,'Corner smoothing');optimize=s.number(params.get('optimize',.2),0,2,'Curve optimization')
    flags={}
    for key,default in [('smooth',True),('stack',False),('removeBackground',True),('invert',False)]:
        flags[key]=params.get(key,default)
        if not isinstance(flags[key],bool):raise ValueError('Invalid trace option: '+key)
    source=Image.open(s.DATA/'images'/(layer['image']+'.bin')).convert('RGBA')
    left,top,right,bottom=crop_settings(layer,s);source=source.crop((round(left*source.width),round(top*source.height),round(right*source.width),round(bottom*source.height)))
    if source.width<2 or source.height<2:raise ValueError('Keep at least 2 × 2 source pixels when cropping.')
    source.thumbnail((1024,1024),Image.Resampling.LANCZOS)
    background=Image.new('RGBA',source.size,'white');background.alpha_composite(source);source=background.convert('RGB')
    if mode!='colors':
        source=source.convert('L')
        if flags['invert']:source=ImageOps.invert(source)
        source=source.point(lambda v:0 if v<threshold else 255).convert('RGB')
    options=[scans,str(flags['smooth']).lower(),str(flags['stack'] if mode=='colors' else False).lower(),str(flags['removeBackground'] if mode=='colors' else True).lower(),speckles,corners,optimize]
    result=trace_bitmap(source,layer,options,s)
    if not result:raise ValueError('No regions remain. Adjust the threshold, background or speckle settings.')
    if len(result)>24:raise ValueError('The trace contains too many color layers. Reduce the color count.')
    group_id=uuid.uuid4().hex
    for i,l in enumerate(result):
        l.update(stitch='fill',fillMethod='tatami_fill',spacing=.4,angle=45,stitchLength=2.5,underlay=True,groupId=group_id,
                 name=f'{layer.get("name","Image")} · traced {i+1}')
        l.pop('originalParams',None)
        if mode!='colors':l['color']=s.color(params.get('color',layer.get('color','#203f38')))
    if mode=='centerline':
        converted=operate({'tool':'fill_to_stroke','layers':result,'params':{}},s)
        result=converted['layers'];preview=converted['preview']
        for l in result:l['groupId']=group_id
    else:preview=layer_preview({'layers':result},s)['preview']
    return {'layers':result,'preview':preview,'nodes':sum(len(c['nodes']) for l in result for c in l.get('contours',[])),
            'sourcePixels':[source.width,source.height],'note':'Traced shapes are editable. Check small details, stitch density and sewing order before export.'}
