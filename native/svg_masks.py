"""Convert rendered SVG opacity masks into explicit embroidery clip regions."""
import base64,binascii,copy,io,math,re,tempfile,uuid,warnings
from pathlib import Path
from lxml import etree as ET
from PIL import Image
from shapely import unary_union,make_valid
from shapely.geometry import Polygon,box
from digitizing import inkex,geometry
from svg_structure import SVG,INK,SHAPES,tag,properties,visible
from svg_clipping import local_path,polygon_path,polygon,clear_clip

def validate_image(value):
    match=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=\s]+)',value)
    if not match:raise ValueError('Mask images must be embedded PNG, JPEG or WebP data. External image links are not supported.')
    try:
        raw=base64.b64decode(re.sub(r'\s','',match[2]),validate=True)
        if len(raw)>8*1024*1024:raise ValueError('Use mask images smaller than 8 MB.')
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            image=Image.open(io.BytesIO(raw))
            if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>25000000 or max(image.size)>16000:raise ValueError('Use a mask image with fewer than 25 million pixels.')
            mime={'PNG':'png','JPEG':'jpeg','WEBP':'webp'}[image.format];image.verify()
        return 'data:image/'+mime+';base64,'+base64.b64encode(raw).decode()
    except (OSError,binascii.Error,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:raise ValueError('The embedded mask image is invalid or too large.') from exc

def reference(element):
    value=properties(element).get('mask','none');ancestor=element.getparent()
    while value=='inherit' and ancestor is not None:value=properties(ancestor).get('mask','none');ancestor=ancestor.getparent()
    if value in ('none','inherit'):return None
    match=re.fullmatch(r'url\(#([\w.:-]+)\)',value)
    if not match:raise ValueError('The SVG has an invalid opacity-mask reference.')
    return match[1]

def clear_mask(element):
    element.attrib.pop('mask',None);style=inkex.Style(element.get('style',''));style.pop('mask',None)
    if style:element.set('style',str(style))
    else:element.attrib.pop('style',None)

def release(raw):
    root=inkex.load_svg(io.BytesIO(raw)).getroot()
    for e in root.iter():
        if visible(e):clear_mask(e)
    return ET.tostring(root)

def freeze_viewport(root,width,height):
    """Resolve viewport-relative mask lengths before the importer reparents them.

    Object-bounding-box fractions remain fractions; those are frozen per owner
    later. This also freezes user-space gradients, which may be shared by a
    mask and ordinary artwork. Opacity and gradient stop offsets are untouched.
    """
    ids={e.get('id'):e for e in root.iter() if e.get('id')}
    def inherited(e,key,default):
        while e is not None:
            if key in e.attrib:return e.get(key)
            ref=e.get('href',e.get('{http://www.w3.org/1999/xlink}href',''))
            e=ids.get(ref[1:]) if ref.startswith('#') else None
        return default
    def resolve(e,key,basis,default=None):
        value=e.get(key,default)
        if value is not None and value.strip().endswith('%'):
            try:number=float(value.strip()[:-1])*basis/100
            except ValueError:raise ValueError('Mask percentages must be numeric.')
            if not math.isfinite(number):raise ValueError('Mask coordinates must be finite.')
            e.set(key,str(number))
    for e in root.iter():
        kind=tag(e)
        if kind=='mask' and e.get('maskUnits','objectBoundingBox')=='userSpaceOnUse':
            for key,basis,default in [('x',width,'-10%'),('y',height,'-10%'),('width',width,'120%'),('height',height,'120%')]:resolve(e,key,basis,default)
        masks=[a for a in e.iterancestors() if tag(a)=='mask']
        bbox=bool(masks and masks[0].get('maskContentUnits','userSpaceOnUse')=='objectBoundingBox')
        w,h=(1,1) if bbox else (width,height);diagonal=math.hypot(w,h)/math.sqrt(2)
        if kind in ('linearGradient','radialGradient'):
            if inherited(e,'gradientUnits','objectBoundingBox')!='userSpaceOnUse':continue
            defaults={'x1':'0%','y1':'0%','x2':'100%','y2':'0%'} if kind=='linearGradient' else {'cx':'50%','cy':'50%','r':'50%'}
            for key,default in defaults.items():resolve(e,key,w if key.startswith('x') or key=='cx' else h if key.startswith('y') or key=='cy' else diagonal,inherited(e,key,default))
            for key,basis in [('fx',w),('fy',h),('fr',diagonal)]:resolve(e,key,basis,inherited(e,key,None))
        elif masks and kind in SHAPES|{'image','use'}:
            for key in ('x','x1','x2','cx','width','rx'):resolve(e,key,w)
            for key in ('y','y1','y2','cy','height','ry'):resolve(e,key,h)
            resolve(e,'r',diagonal)

def canonicalize(root,s):
    """Freeze original object bounds before replacing mask owners with probes."""
    masks={};temporary=[];viewport=root.get_viewbox()[2:]
    def prepare_owner(owner,chain=()):
        ref=reference(owner)
        if not ref:return None
        if ref in chain or len(chain)>24:raise ValueError('Opacity masks cannot contain circular or deep references.')
        if len(temporary)>256:raise ValueError('Prepare fewer nested masks at once.')
        source=root.getElementById(ref)
        if source is None or tag(source)!='mask':raise ValueError('The opacity mask is missing.')
        bounds=local_path(owner).bounding_box()
        if bounds is None:return None
        units=source.get('maskUnits','objectBoundingBox');content=source.get('maskContentUnits','userSpaceOnUse')
        if units not in ('objectBoundingBox','userSpaceOnUse') or content not in ('objectBoundingBox','userSpaceOnUse'):raise ValueError('The mask uses unsupported coordinate units.')
        mask=copy.deepcopy(source);mask.set('id','native-mask-'+uuid.uuid4().hex);mask.set('maskUnits','userSpaceOnUse');mask.set('maskContentUnits','userSpaceOnUse')
        values={}
        for key,default,axis in [('x','-10%',0),('y','-10%',1),('width','120%',0),('height','120%',1)]:
            value=source.get(key,default);fraction=float(value[:-1])/100 if value.endswith('%') else None
            if units=='objectBoundingBox':
                number=fraction if fraction is not None else float(value)
                number*=float(bounds.width if axis==0 else bounds.height)
                if key in ('x','y'):number+=float(bounds.left if axis==0 else bounds.top)
            else:number=fraction*viewport[axis] if fraction is not None else owner.to_dimensionless(value)
            if not math.isfinite(number):raise ValueError('Mask coordinates must be finite.')
            values[key]=number;mask.set(key,str(number))
        if content=='objectBoundingBox':
            group=ET.Element('{'+SVG+'}g',transform=str(inkex.Transform(translate=(bounds.left,bounds.top))@inkex.Transform(scale=(bounds.width,bounds.height))))
            for child in list(mask):group.append(child)
            mask.append(group)
        if properties(source).get('mask-type','luminance')=='alpha':
            # Inkscape 1.4 renders every mask as luminance. Whiten the combined
            # mask RGB while retaining alpha, using a private render-only filter.
            # The original source and returned SVG never receive this filter.
            filter=ET.SubElement(root.defs,'{'+SVG+'}filter',id='alpha-mask-'+uuid.uuid4().hex,filterUnits='userSpaceOnUse',**{k:str(v) for k,v in values.items()})
            filter.set('color-interpolation-filters','sRGB')
            ET.SubElement(filter,'{'+SVG+'}feColorMatrix',type='matrix',values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1 0')
            group=ET.Element('{'+SVG+'}g',filter='url(#'+filter.get('id')+')')
            for child in list(mask):group.append(child)
            mask.append(group);temporary.append(filter)
        s.prefix_ids(mask,'mask-'+uuid.uuid4().hex+'-')
        root.defs.append(mask);temporary.append(mask);clear_mask(owner);owner.set('mask','url(#'+mask.get('id')+')')
        for nested in list(mask.iter()):
            if isinstance(nested,inkex.ShapeElement) and reference(nested):prepare_owner(nested,chain+(ref,))
        if not owner.get('id'):owner.set('id','mask-owner-'+uuid.uuid4().hex)
        x,y,w,h=[values[k] for k in ('x','y','width','height')]
        if w<=0 or h<=0:region=Polygon()
        else:
            corners=[owner.composed_transform().apply_to_point(p) for p in [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]]
            region=Polygon([(p.x,p.y) for p in corners]).envelope
        return region
    for owner in list(root.iter()):
        if isinstance(owner,inkex.ShapeElement) and visible(owner):
            region=prepare_owner(owner)
            if region is not None:masks[owner.get('id')]=region
    return masks,temporary

def trace_alpha(image,bounds,cutoff,s,tmp):
    threshold=max(1,math.ceil(cutoff*255));alpha=image.getchannel('A')
    if alpha.getextrema()[1]<threshold:return Polygon()
    if alpha.getextrema()[0]>=threshold:return box(*bounds)
    bitmap=alpha.point(lambda v:0 if v>=threshold else 255).convert('RGB');buffer=io.BytesIO();bitmap.save(buffer,format='PNG')
    x0,y0,x1,y1=bounds;doc=s.svg_root();node=ET.SubElement(doc,'{'+SVG+'}image',id='mask-bitmap',x=str(x0),y=str(y0),width=str(x1-x0),height=str(y1-y0),preserveAspectRatio='none')
    node.set('{http://www.w3.org/1999/xlink}href','data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode())
    source=tmp/'trace.svg';out=tmp/'traced.svg';source.write_bytes(ET.tostring(doc))
    s.run(['xvfb-run','-a','inkscape','--with-gui','--batch-process',str(source),'--actions=select-by-id:mask-bitmap;object-trace:2,false,false,true,0,0,0;export-filename:'+str(out)+';export-do'],120)
    if not out.exists():raise ValueError('The mask could not be traced. Adjust its cutoff or detail.')
    shapes=[polygon(path,str(style.get('fill-rule','nonzero'))) for e,path,style in geometry(out.read_bytes()) if str(style.get('fill','none'))!='none']
    result=make_valid(unary_union(shapes))
    if len(str(polygon_path(result)))>4*1024*1024:raise ValueError('The mask boundary is too detailed. Choose a coarser mask detail.')
    return result

def render_region(root,chain,frames,cutoff,detail,s):
    region=None
    for id in chain:region=frames[id] if region is None else region.intersection(frames[id])
    if region is None or region.is_empty:return Polygon()
    bounds=region.bounds;x0,y0,x1,y1=bounds
    width=max(1,math.ceil((x1-x0)/detail));height=max(1,math.ceil((y1-y0)/detail))
    if max(width,height)>4096 or width*height>16000000:raise ValueError('The mask is too large at this detail. Choose a coarser mask detail or resize the artwork.')
    doc=inkex.load_svg(io.BytesIO(ET.tostring(root))).getroot();owner=doc.getElementById(chain[0]);parent=owner.getparent()
    probe=inkex.PathElement();probe.set('id',owner.get('id'));probe.set('transform',str(owner.transform));probe.set('mask',properties(owner)['mask'])
    probe.set('d',str(polygon_path(box(*bounds)).transform(-owner.composed_transform())));probe.set('style','fill:#ffffff;fill-opacity:1;stroke:none;opacity:1')
    parent.replace(owner,probe)
    # Probe only the opacity-mask stack. Ordinary clips are resolved separately,
    # and artwork/group paint opacity is not a request for lighter thread.
    for e in [probe,*probe.iterancestors()]:
        clear_clip(e);style=inkex.Style(e.get('style',''));style['opacity']='1';e.set('style',str(style));e.attrib.pop('opacity',None)
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='svg-mask-') as folder:
        tmp=Path(folder);source=tmp/'mask.svg';output=tmp/'mask.png';source.write_bytes(ET.tostring(doc))
        area=':'.join(str(v/s.PX_MM) for v in bounds)
        s.run(['inkscape',str(source),'--export-id='+probe.get('id'),'--export-id-only','--export-area='+area,'--export-width='+str(width),'--export-height='+str(height),'--export-background-opacity=0','--export-filename='+str(output)],120)
        image=Image.open(output).convert('RGBA');image.load()
        return trace_alpha(image,bounds,cutoff,s,tmp)

def convert(raw,cutoff,detail,s):
    root=inkex.load_svg(io.BytesIO(raw)).getroot();frames,temporary=canonicalize(root,s);regions={};targets=[]
    for e in root.iter():
        if tag(e) not in SHAPES or not visible(e) or e.get('{'+INK+'}connection-start') or 'inkstitch-' in properties(e).get('marker-start',''):continue
        chain=tuple(a.get('id') for a in [e,*e.iterancestors()] if a.get('id') in frames)
        if not chain:continue
        if chain not in regions:
            if len(regions)>=32:raise ValueError('Prepare at most 32 distinct mask stacks at a time.')
            regions[chain]=render_region(root,chain,frames,cutoff,detail,s)
        targets.append((e,regions[chain]))
    for e in root.iter():
        if visible(e):clear_mask(e)
    for e in temporary:e.getparent().remove(e)
    for e,region in targets:
        clip=ET.SubElement(root.defs,'{'+SVG+'}clipPath',id='mask-clip-'+uuid.uuid4().hex,clipPathUnits='userSpaceOnUse')
        if not region.is_empty:ET.SubElement(clip,'{'+SVG+'}path',d=str(polygon_path(region).transform(-e.composed_transform())),**{'clip-rule':'evenodd'})
        # A wrapper intersects the new mask boundary with any existing clip.
        parent=e.getparent();group=ET.Element('{'+SVG+'}g',transform=str(e.transform),**{'clip-path':'url(#'+clip.get('id')+')'})
        e.attrib.pop('transform',None);parent.replace(e,group);group.append(e)
    return ET.tostring(root),{'maskedPaths':len(targets),'maskStacks':len(regions),'maskCutoff':cutoff*100,'maskDetail':detail}
