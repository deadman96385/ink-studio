"""Connected image-region selection; tracing and stitches use installed engines."""
import copy
import hashlib
import json
from PIL import Image, ImageChops, ImageDraw, ImageOps
from references import validate_reference, crop_settings, trace_bitmap


def region_mask(source,seed,tolerance):
    """Select only seed-connected pixels, comparing every color to the seed.

    Fixed-seed comparison prevents a smooth gradient from leaking across an
    entire image. Four-neighbor connectivity keeps corner-touching marks apart.
    Transparent pixels are barriers, even when their hidden RGB matches.
    """
    x=min(source.width-1,int(seed[0]*source.width))
    y=min(source.height-1,int(seed[1]*source.height))
    if source.getpixel((x,y))[3]<32:
        raise ValueError('That point is transparent. Tap inside a visible region.')
    rgb=Image.new('RGBA',source.size,'white');rgb.alpha_composite(source);rgb=rgb.convert('RGB')
    sample=rgb.getpixel((x,y))
    channels=ImageChops.difference(rgb,Image.new('RGB',rgb.size,sample)).split()
    difference=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
    allowed=difference.point(lambda v:255 if v<=tolerance*2.55 else 0)
    opaque=source.getchannel('A').point(lambda v:255 if v>=32 else 0)
    allowed=ImageChops.multiply(allowed,opaque)
    ImageDraw.floodfill(allowed,(x,y),128,border=0)
    mask=allowed.point(lambda v:255 if v==128 else 0)
    count=mask.histogram()[255]
    if count<4:raise ValueError('That region is too small to trace. Tap farther inside it or increase color tolerance.')
    return mask,sample,count


def pick_region(data,s):
    layer=copy.deepcopy(data.get('layer'));params=data.get('params',{});seed=data.get('seed')
    if not isinstance(layer,dict) or layer.get('type')!='image' or not isinstance(params,dict):
        raise ValueError('Select one reference image for click-to-stitch.')
    if not isinstance(seed,list) or len(seed)!=2 or any(isinstance(v,bool) for v in seed):
        raise ValueError('Tap a point inside the reference image.')
    seed=[s.number(v,0,1,'Region position') for v in seed]
    tolerance=s.number(params.get('tolerance',12),0,100,'Color tolerance')
    stitch=params.get('stitch','fill')
    if stitch not in ('fill','running','bean'):raise ValueError('Choose a fill, running outline or bean outline.')
    spacing=s.number(params.get('spacing',.4),.2,3,'Row spacing')
    angle=s.number(params.get('angle',45),-360,360,'Fill angle')
    length=s.number(params.get('stitchLength',2.5),.5,6,'Stitch length')
    underlay=params.get('underlay',True);use_source=params.get('useSourceColor',True)
    if not isinstance(underlay,bool) or not isinstance(use_source,bool):raise ValueError('Invalid region stitch option.')
    custom=s.color(params.get('color','#203f38'))
    validate_reference(layer,s)
    with Image.open(s.DATA/'images'/(layer['image']+'.bin')) as image:
        source=image.convert('RGBA')
    left,top,right,bottom=crop_settings(layer,s)
    source=source.crop((round(left*source.width),round(top*source.height),round(right*source.width),round(bottom*source.height)))
    if min(source.size)<2:raise ValueError('Keep at least 2 × 2 source pixels when cropping.')
    # Match the existing tracer's bounded resolution and physical image frame.
    source.thumbnail((1024,1024),Image.Resampling.LANCZOS)
    mask,sample,count=region_mask(source,seed,tolerance)
    key=hashlib.sha256(layer['image'].encode()+json.dumps([layer.get('crop'),source.size]).encode()+mask.tobytes()).hexdigest()
    bitmap=ImageOps.invert(mask).convert('RGB')
    layers=trace_bitmap(bitmap,layer,[2,'false','false','true',0,1,.2],s)
    if not layers:raise ValueError('The region has no traceable outline. Increase color tolerance or select a larger region.')
    if len(layers)>12:raise ValueError('This region has too much scattered detail. Choose a simpler region or lower color tolerance.')
    color='#%02x%02x%02x'%sample if use_source else custom
    recipe={'seed':seed,'tolerance':tolerance,'stitch':stitch,'spacing':spacing,'angle':angle,
            'stitchLength':length,'underlay':underlay,'useSourceColor':use_source,'color':custom}
    for i,layer_out in enumerate(layers):
        layer_out.pop('originalParams',None)
        layer_out.update(stitch=stitch,color=color,fillMethod='tatami_fill',spacing=spacing,angle=angle,
                         stitchLength=length,underlay=underlay,trimAfter=True,
                         name='Picked region'+(f' {i+1}' if len(layers)>1 else ''))
        layer_out['clickStitch']={'sourceId':layer.get('id'),'regionKey':key,**recipe}
    # Validate native path/node bounds before returning anything to the browser.
    s.build_svg({'version':1,'layers':layers})
    return {'layers':layers,'regionKey':key,'seed':seed,'sampleColor':'#%02x%02x%02x'%sample,
            'pixelCount':count,'sourcePixels':list(source.size),'params':recipe}
