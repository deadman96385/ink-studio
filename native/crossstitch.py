"""Native cross-stitch preparation; final stitches use installed Ink/Stitch.

Grid semantics follow Ink/Stitch 3.3.0 CrossGeometries. Preparation uses
millimeters, Pillow and Shapely rather than opening the desktop-only wx dialog.
"""
import base64,copy,io,math,re,uuid
from collections import defaultdict
import numpy as np
from PIL import Image,ImageEnhance
from lxml import etree as ET
from shapely import make_valid,unary_union
from shapely.geometry import box,Polygon
from shapely.affinity import affine_transform
from digitizing import geometry,from_path,inkex
from components import path_polygon,polygon_path
from references import validate_reference,crop_settings
from operations import editable_output
from limits import MAX_LAYERS
import preferences

METHODS=[v+s for v in ('simple_cross','half_cross','upright_cross','dense_upright_cross','double_cross','smyrna_cross') for s in ('','_flipped')]
DEFAULTS=dict(square=True,boxX=3,boxY=3,method='simple_cross',coverage=50,offsetX=0,offsetY=0,alignCanvas=True,
              setParams=True,pixelize=True,removeOverlaps=True,addNodes=False,setGrid=True,gridColor='#0099e5',removeGrids=True,snapGrid=False,
              convertImages=True,pixelByPixel=False,colorMethod='count',colors=5,quantize=1,palette='',rgbColors='',
              saturation=1,brightness=1,contrast=1,opacityThreshold=50,background='#ffffff',removeBackground='none',keepOriginals=True,hideImages=True,replacePrevious=True)
MAX_CELLS=20000

def settings(raw,s):
    if not isinstance(raw,dict) or set(raw)-set(DEFAULTS):raise ValueError('Unknown cross-stitch setting.')
    result={**DEFAULTS,**raw}
    for k,v in DEFAULTS.items():
        if type(v) is bool and type(result[k]) is not bool:raise ValueError('Check '+k+'.')
    for k,lo,hi in [('boxX',.1,100),('boxY',.1,100),('coverage',0,100),('offsetX',0,100),('offsetY',0,100),('colors',1,100),('quantize',0,2),('saturation',0,2),('brightness',0,2),('contrast',0,2),('opacityThreshold',0,99)]:
        if type(result[k]) not in (int,float):raise ValueError('Check '+k+'.')
        result[k]=s.number(result[k],lo,hi,k)
    for k in ('coverage','colors','quantize','opacityThreshold'):
        if result[k]!=int(result[k]):raise ValueError(k+' must be a whole number.')
        result[k]=int(result[k])
    if result['square']:result['boxY']=result['boxX']
    if result['method'] not in METHODS or result['colorMethod'] not in ('count','strokes','rgb','palette') or result['removeBackground'] not in ('none','chosen','dominant'):raise ValueError('Choose a supported cross-stitch or color option.')
    for key in ('gridColor','background'):result[key]=s.color(result[key])
    if not isinstance(result['palette'],str) or len(result['palette'])>80 or not isinstance(result['rgbColors'],str) or len(result['rgbColors'])>8000:raise ValueError('Choose a palette or RGB list with at most 256 colors.')
    return result

def grids(value,s):
    if value is None:return []
    if not isinstance(value,list) or len(value)>12:raise ValueError('Keep at most 12 cross-stitch page grids.')
    result=[]
    for row in value:
        if not isinstance(row,dict):raise ValueError('Invalid cross-stitch grid.')
        if any(type(row.get(k,0)) not in (int,float) for k in ('width','height','x','y')):raise ValueError('Invalid grid dimensions.')
        item={k:s.number(row.get(k,0),.1 if k in ('width','height') else -100,100,'Cross grid '+k) for k in ('width','height','x','y')}
        item.update(id=s.safe_id(row.get('id')),color=s.color(row.get('color')),visible=row.get('visible',True))
        if type(item['visible']) is not bool:raise ValueError('Invalid grid visibility.')
        result.append(item)
    return result

def append_grids(root,project,s):
    rows=grids(project.get('crossGrids'),s)
    if not rows:return
    named=ET.SubElement(root,'{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}namedview')
    for g in rows:ET.SubElement(named,'{'+s.INK+'}grid',id='inkstitch_cross_stitch_grid_'+g['id'],type='xygrid',units='mm',originx=str(g['x']),originy=str(g['y']),spacingx=str(g['width']),spacingy=str(g['height']),color=g['color'],empcolor=g['color'],opacity='.22',empopacity='.35',empspacing='1',enabled=str(g['visible']).lower(),visible=str(g['visible']).lower())

def imported_grids(root,s):
    """Read assistant grids before SVG sanitizing removes editor metadata."""
    found=root.findall('.//{'+s.INK+'}grid')
    found=[g for g in found if g.get('id','').startswith('inkstitch_cross_stitch_grid_') and g.get('type','xygrid')=='xygrid']
    if not found:return []
    vb=[float(v) for v in re.split(r'[ ,]+',root.get('viewBox','0 0 300 150').strip())]
    if len(vb)!=4 or min(vb[2:])<=0:raise ValueError('The SVG needs a positive viewport size.')
    sx=float(inkex.units.convert_unit(root.get('width',str(vb[2])),'mm'))/vb[2]
    sy=float(inkex.units.convert_unit(root.get('height',str(vb[3])),'mm'))/vb[3]
    result=[]
    for g in found:
        def length(key):
            value=g.get(key,'0')
            return float(value) if re.fullmatch(r'[-+\d.eE]+',value) else float(inkex.units.convert_unit(value,'mm'))/(sx if key.endswith('x') else sy)
        color='#%02x%02x%02x'%tuple(inkex.Color(g.get('color','#0099e5')).to_rgb())
        result.append(dict(id=uuid.uuid4().hex,width=length('spacingx')*sx,height=length('spacingy')*sy,x=(length('originx')-vb[0])*sx,y=(length('originy')-vb[1])*sy,color=color,visible=g.get('visible','true')!='false' and g.get('enabled','true')!='false'))
    return grids(result,s)

def grid_result(project,p,s):
    old=grids(project.get('crossGrids'),s)
    if not p['setGrid']:return old
    rows=[] if p['removeGrids'] else old
    if len(rows)>=12:raise ValueError('Remove previous grids before adding another.')
    return rows+[dict(id=uuid.uuid4().hex,width=p['boxX'],height=p['boxY'],x=-p['offsetX'],y=p['offsetY'],color=p['gridColor'],visible=True)]

def cells(shape,p,coverage=None):
    """Same half-open lattice and coverage tolerance as the installed engine."""
    if shape.is_empty:return []
    w,h=p['boxX'],p['boxY'];x0,y0,x1,y1=shape.bounds;ox,oy=p['offsetX'],p['offsetY']
    if not p['alignCanvas']:ox-=x0%w;oy+=y0%h
    start_x=x0-x0%w-ox;start_y=y0-y0%h+oy
    nx=max(0,int(math.floor((x1+w-x1%w-start_x)/w+1e-8))+1);ny=max(0,int(math.floor((y1+h-y1%h-start_y)/h+1e-8))+1)
    if nx*ny>MAX_CELLS:raise ValueError('This grid exceeds 20,000 cells. Increase the cell size or use a smaller selection.')
    result=[];threshold=p['coverage'] if coverage is None else coverage
    for iy in range(ny):
        for ix in range(nx):
            tile=box(start_x+ix*w,start_y+iy*h,start_x+(ix+1)*w,start_y+(iy+1)*h)
            if shape.contains(tile) or shape.intersects(tile) and shape.intersection(tile).area/(w*h)*100+.0001>=threshold:result.append(tile)
    return result

def outline(tiles,p,s):
    # Match the desktop assistant's small px buffers, expressed in mm.
    return make_valid(unary_union(tiles).buffer(.001*s.PX_MM).simplify(.1*s.PX_MM))

def add_grid_nodes(path,p):
    # Insert nodes on grid crossings, including rectangular vertical spacing.
    output=inkex.Path()
    for sub in path.break_apart():
        points=[tuple(c.args[-2:]) for c in sub.to_absolute() if c.letter in ('M','L')]
        if not points:continue
        expanded=[]
        for a,b in zip(points,points[1:]+points[:1]):
            expanded.append(a);axis=0 if abs(b[0]-a[0])>=abs(b[1]-a[1]) else 1;step=p['boxX'] if axis==0 else p['boxY'];origin=-p['offsetX'] if axis==0 else p['offsetY']
            low,high=sorted((a[axis],b[axis]));cuts=[origin+n*step for n in range(math.floor((low-origin)/step)+1,math.ceil((high-origin)/step))]
            if b[axis]<a[axis]:cuts.reverse()
            for value in cuts:
                t=(value-a[axis])/(b[axis]-a[axis]);expanded.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
        output.extend(inkex.Path('M'+' L'.join(f'{x},{y}' for x,y in expanded)+' Z'))
    return output

def set_params(layer,p):
    params=layer.setdefault('originalParams',{})
    params.update(fill_method='cross_stitch',cross_stitch_method=p['method'],pattern_size_mm=f'{p["boxX"]} {p["boxY"]}',expand_mm='.1',fill_coverage=str(p['coverage']),cross_offset_mm=f'{p["offsetX"]} {p["offsetY"]}',canvas_grid_origin=str(p['alignCanvas']).lower(),cross_rotation='0')
    layer.update(stitch='original',originalFill=True,originalStroke=False)

def palette(p,strokes,s):
    book={}
    if p['colorMethod']=='count':return None,book
    if p['colorMethod']=='strokes':colors=list(dict.fromkeys(strokes))
    elif p['colorMethod']=='rgb':
        if not re.fullmatch(r'[\d\s,;]+',p['rgbColors']):raise ValueError('Enter RGB triples using numbers from 0 to 255.')
        values=list(map(int,re.findall(r'\d+',p['rgbColors'])))
        if not values or len(values)%3 or len(values)>768 or max(values)>255:raise ValueError('Enter 1–256 complete RGB triples, each channel from 0 to 255.')
        colors=['#%02x%02x%02x'%tuple(values[i:i+3]) for i in range(0,len(values),3)]
    else:
        from threads import palettes
        item=next((v for v in palettes(s) if v['key']==p['palette']),None)
        if item is None:raise ValueError('Choose a thread palette, or import a GIMP .gpl palette.')
        colors=[v['color'] for v in item['colors'][:256]];book={v['color']:{k:v[k] for k in ('name','number','brand')} for v in item['colors'][:256]}
    if not colors:raise ValueError('Select an outline with a thread color to use as the image palette.')
    return colors[:256],book

def corrected(image,p,colors):
    alpha=image.getchannel('A').point(lambda a:255 if a>p['opacityThreshold']*255//100 else 0)
    image=ImageEnhance.Color(image).enhance(p['saturation']);image=ImageEnhance.Brightness(image).enhance(p['brightness']);image=ImageEnhance.Contrast(image).enhance(p['contrast']);image.putalpha(alpha)
    bg=Image.new('RGBA',image.size,'white');bg.alpha_composite(image);rgb=bg.convert('RGB')
    if colors:
        values=[int(c[i:i+2],16) for c in colors for i in (1,3,5)];values=(values+values[:3]*(256-len(colors)))[:768]
        pal=Image.new('P',(1,1));pal.putpalette(values);rgb=rgb.quantize(palette=pal,dither=Image.Dither.NONE)
    else:rgb=rgb.quantize(p['colors'],method=p['quantize'],kmeans=5)
    out=rgb.convert('RGBA');out.putalpha(alpha)
    if p['removeBackground']!='none':
        values=[(n,c) for n,c in out.getcolors(out.width*out.height) if c[3]]
        if values:
            target=tuple(int(p['background'][i:i+2],16) for i in (1,3,5))
            color=max(values)[1][:3] if p['removeBackground']=='dominant' else min(values,key=lambda v:sum((v[1][i]-target[i])**2 for i in range(3)))[1][:3]
            pixels=np.array(out);pixels[np.all(pixels[:,:,:3]==color,axis=2),3]=0;out=Image.fromarray(pixels)
    return out

def image_cells(layer,p,colors,s):
    layer=copy.deepcopy(layer);validate_reference(layer,s)
    image=Image.open(s.DATA/'images'/(layer['image']+'.bin')).convert('RGBA');left,top,right,bottom=crop_settings(layer,s)
    image=image.crop((round(left*image.width),round(top*image.height),round(right*image.width),round(bottom*image.height)))
    if not image.width or not image.height:raise ValueError('The image crop is empty.')
    pixel_size=image.size
    if p['pixelByPixel']:
        if abs(layer.get('rotation',0)%360)>1e-7:raise ValueError('Use Fit image for a rotated reference. One cell per source pixel requires rotation 0° so every pixel stays on the cross-stitch grid.')
        w,h=image.width*p['boxX'],image.height*p['boxY']
        if image.width*image.height>MAX_CELLS or max(w,h)>100:raise ValueError('One cross per source pixel exceeds the 100 mm hoop or 20,000 cells. Crop the image or reduce cell size; use Fit image for photos.')
        if p['alignCanvas']:
            layer['x']=round((layer['x']+p['offsetX'])/p['boxX'])*p['boxX']-p['offsetX']
            layer['y']=round((layer['y']-p['offsetY'])/p['boxY'])*p['boxY']+p['offsetY']
    else:w,h=layer['width'],layer['height'];image.thumbnail((1024,1024),Image.Resampling.BOX)
    image=corrected(image,p,colors);r=math.radians(layer.get('rotation',0));c,t=math.cos(r),math.sin(r);fx=-1 if layer.get('flipX') else 1;fy=-1 if layer.get('flipY') else 1
    a,b,d,e=c*fx,-t*fy,t*fx,c*fy;cx,cy=layer['x']+w/2,layer['y']+h/2;tx,ty=cx-a*w/2-b*h/2,cy-d*w/2-e*h/2
    matrix=[a,b,d,e,tx,ty];shape=affine_transform(box(0,0,w,h),matrix);groups=defaultdict(list)
    if p['pixelByPixel']:
        for y in range(image.height):
            for x in range(image.width):
                rgba=image.getpixel((x,y))
                if rgba[3]:groups['#%02x%02x%02x'%rgba[:3]].append(affine_transform(box(x*p['boxX'],y*p['boxY'],(x+1)*p['boxX'],(y+1)*p['boxY']),matrix))
    else:
        x0,y0,x1,y1=shape.bounds;ppm=min(16,1024/max(x1-x0,y1-y0));size=(max(1,math.ceil((x1-x0)*ppm)),max(1,math.ceil((y1-y0)*ppm)))
        determinant=a*e-b*d;ia,ib,id,ie=e/determinant,-b/determinant,-d/determinant,a/determinant
        sx,sy=image.width/w,image.height/h
        affine=(ia/ppm*sx,ib/ppm*sx,(ia*(x0-tx)+ib*(y0-ty))*sx,id/ppm*sy,ie/ppm*sy,(id*(x0-tx)+ie*(y0-ty))*sy)
        world=image.transform(size,Image.Transform.AFFINE,affine,Image.Resampling.NEAREST)
        for tile in cells(shape,p,max(75,p['coverage'])):
            bx,by,ex,ey=tile.bounds;region=world.crop((round((bx-x0)*ppm),round((by-y0)*ppm),round((ex-x0)*ppm),round((ey-y0)*ppm)))
            counts=region.getcolors(max(1,region.width*region.height)) or []
            if counts:
                rgba=max(counts)[1]
                if rgba[3]:groups['#%02x%02x%02x'%rgba[:3]].append(tile)
    out=io.BytesIO();thumb=image.copy();thumb.thumbnail((512,512),Image.Resampling.NEAREST);thumb.save(out,format='PNG')
    image_preview={'name':layer.get('name','Image'),'data':'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode(),'pixels':list(pixel_size),'width':w,'height':h}
    return [(color,unary_union(tiles)) for color,tiles in groups.items()],image_preview

def prepare(data,s):
    project=data.get('project');ids=data.get('ids',[]);p=settings(data.get('settings',{}),s)
    if not isinstance(project,dict) or project.get('version')!=1 or not isinstance(ids,list) or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):raise ValueError('Choose a valid design and selection.')
    layers=project.get('layers')
    if not isinstance(layers,list) or len(layers)>MAX_LAYERS or any(not isinstance(l,dict) for l in layers):raise ValueError('Choose a valid design.')
    if len({s.safe_id(l.get('id')) for l in layers})!=len(layers):raise ValueError('Design layer IDs must be unique.')
    from linked import resolve
    materialized=resolve(project,s);selected=[l for l in materialized['layers'] if l['id'] in ids]
    if len(selected)!=len(ids):raise ValueError('The selection changed. Reopen the cross-stitch assistant.')
    originals={l['id']:l for l in selected};images=[l for l in selected if l['type']=='image' and p['convertImages']]
    candidates=[l for l in selected if l['type']!='image' and l.get('role','artwork')=='artwork' and l.get('visible',True)]
    helpers=[l for l in materialized['layers'] if l.get('helperTarget') in originals]
    output=[];strokes=[];sources=set();image_previews=[];fill_items=[];per_source=defaultdict(list);pieces=[];converted=defaultdict(list)
    if candidates and (p['pixelize'] or p['setParams'] or images and p['colorMethod']=='strokes'):
        raw=s.build_svg({**materialized,'layers':candidates+helpers});doc=s.xml(raw)
        if any(e.get('clip-path') or e.get('mask') or re.search(r'(?:clip-path|mask)\s*:',e.get('style','')) for e in doc.iter()):raise ValueError('Apply clipping or masking to paths before cross-stitch conversion.')
        pieces=editable_output(raw,s,'Cross stitch',candidates,element_ids=True)
        for part in pieces:
            sid=part.get('_sourceId')
            if sid not in originals or part.get('role','artwork')!='artwork':continue
            if part.get('originalStroke'):strokes.append(part['color'])
            per_source[sid].append(part)
        for source in candidates:
            parts=per_source[source['id']];fills=[v for v in parts if v.get('originalFill')]
            if not fills or not (p['setParams'] or p['pixelize']):continue
            if source.get('locked'):raise ValueError('Unlock selected fill artwork before converting it.')
            sources.add(source['id'])
            for part in parts:
                if not part.get('originalFill'):converted[source['id']].append((part,part));continue
                if p['pixelize']:
                    raw=s.build_svg({'version':1,'layers':[part]});_,path,style=geometry(raw)[0]
                    # SVG fills implicitly close open subpaths.
                    path=inkex.Path(' '.join(str(sub)+('' if sub[-1].letter=='Z' else ' Z') for sub in path.break_apart()))
                    shape=path_polygon(path,part.get('originalFillRule','nonzero'))
                    fill_items.append({'color':part['color'],'shape':shape,'base':part,'source':source['id']})
                else:
                    if p['setParams']:set_params(part,p)
                    converted[source['id']].append((part,part))
    colors,book=palette(p,strokes,s) if images else (None,{})
    for layer in images:
        regions,thumb=image_cells(layer,p,colors,s);image_previews.append(thumb)
        if not regions:raise ValueError('No image cells remain. Keep more colors, lower the opacity threshold or disable background removal.')
        sources.add(layer['id'])
        for color,shape in regions:fill_items.append({'color':color,'shape':shape,'base':None,'source':layer['id']})
        if sum(v['shape'].area/(p['boxX']*p['boxY']) for v in fill_items if v['base'] is None)>MAX_CELLS:raise ValueError('These images exceed 20,000 cells together. Convert a smaller selection.')
    # Keep document rendering order when fills and images are mixed.
    positions={l['id']:i for i,l in enumerate(materialized['layers'])};fill_items.sort(key=lambda v:positions[v['source']])
    def add_shape(shape,item):
        if shape.is_empty:return
        color,base=item['color'],item['base']
        path=polygon_path(shape)
        if p['addNodes']:path=add_grid_nodes(path,p)
        l=from_path(path,base or dict(stitch='original',originalFill=True,originalStroke=False,originalFillRule='evenodd',originalParams={}))
        l.update(name='Cross stitch · '+color,color=color,originalFillRule='evenodd');l.pop('link',None)
        if p['setParams']:set_params(l,p)
        converted[item['source']].append((l,base))
    cell_count=0
    if p['removeOverlaps'] and fill_items:
        occupied=Polygon();by_color=defaultdict(list);visible_items=[]
        for index,item in reversed(list(enumerate(fill_items))):
            visible=item['shape'].difference(occupied)
            if not visible.is_empty:by_color[item['color']].append(visible);visible_items.append((index,visible))
            occupied=unary_union([occupied,item['shape'].buffer(.1*s.PX_MM)])
        areas={color:make_valid(unary_union(shapes)) for color,shapes in by_color.items()};colored=defaultdict(list)
        for tile in cells(occupied,p):
            color,area=max(((color,tile.intersection(shape).area) for color,shape in areas.items()),key=lambda v:v[1])
            if area>0:
                # Keep each contributing source's commands, settings and guides.
                index=max(((i,tile.intersection(shape).area) for i,shape in visible_items if fill_items[i]['color']==color),key=lambda v:v[1])[0]
                colored[index].append(tile)
        for index,tiles in sorted(colored.items()):cell_count+=len(tiles);add_shape(outline(tiles,p,s),fill_items[index])
    else:
        for item in fill_items:
            tiles=cells(item['shape'].buffer(.1*s.PX_MM),p) if item['base'] else None
            cell_count+=len(tiles) if tiles is not None else round(item['shape'].area/(p['boxX']*p['boxY']))
            if cell_count>MAX_CELLS:raise ValueError('This selection exceeds 20,000 filled cells. Use larger cells or convert fewer objects.')
            add_shape(outline(tiles,p,s) if tiles is not None else item['shape'],item)
    groups={sid:uuid.uuid4().hex for sid in sources};replacements={};selected_ids=[]
    for sid,pairs in converted.items():
        # Restore original compound-path paint order (fill before its outline).
        part_order={part['id']:i for i,part in enumerate(per_source[sid])}
        pairs.sort(key=lambda pair:part_order.get((pair[1] or {}).get('id'),0))
        rows=[]
        for layer,base in pairs:
            layer.pop('_sourceId',None);layer.pop('_elementId',None);layer['groupId']=groups[sid];layer['crossSourceId']=sid
            selected_ids.append(layer['id']);rows.append(layer)
            attached=[h for h in pieces if base and h.get('helperTarget')==base['id']]
            attached.extend(h for h in helpers if h.get('helperTarget')==sid and not h.get('visible',True))
            for h in attached:
                clone=copy.deepcopy(h);clone.update(id=uuid.uuid4().hex,helperTarget=layer['id'],groupId=groups[sid]);clone.pop('linkedHelper',None);rows.append(clone)
        replacements[sid]=rows;output.extend(rows)
    if len(output)>MAX_LAYERS:raise ValueError('Too many output layers. Reduce image colors or convert a smaller selection.')
    if sources and not output:raise ValueError('No filled cells remain. Reduce coverage, use smaller cells or keep more image colors.')
    if ids and not sources and not p['setGrid'] and (p['pixelize'] or p['convertImages'] or p['setParams']):raise ValueError('Select visible filled artwork or an image. Outlines can provide palette colors but do not become cross fills.')
    if not p['keepOriginals']:
        if any(l.get('link',{}).get('sourceId') in sources and l['id'] not in sources for l in project['layers']):raise ValueError('Keep originals hidden while linked copies still refer to them.')
        if any(l.get('locked') for l in helpers if l.get('helperTarget') in sources):raise ValueError('Unlock attached helpers before replacing their original artwork.')
    result=copy.deepcopy(project);result['layers']=[]
    remove_helpers={l['id'] for l in helpers if l.get('helperTarget') in sources and not p['keepOriginals']}
    previous={l['id'] for l in project['layers'] if p['replacePrevious'] and l.get('crossSourceId') in sources and l['id'] not in sources}
    previous.update(l['id'] for l in project['layers'] if l.get('helperTarget') in previous)
    if any(l.get('locked') for l in project['layers'] if l['id'] in previous):raise ValueError('Unlock earlier cross-stitch output and its guides before replacing it, or turn off Replace earlier output.')
    if any(l.get('link',{}).get('sourceId') in previous and l['id'] not in previous for l in project['layers']):raise ValueError('A linked copy uses the earlier cross-stitch output. Detach the copy or turn off Replace earlier output.')
    for i,layer in enumerate(project['layers']):
        if layer['id'] in previous:continue
        if layer['id'] in sources:
            if layer['type']=='image' or p['keepOriginals']:
                kept=copy.deepcopy(layer)
                if kept['type']!='image' or p['hideImages']:kept['visible']=False
                result['layers'].append(kept)
            result['layers'].extend(copy.deepcopy(replacements.get(layer['id'],[])))
        elif layer['id'] not in remove_helpers:result['layers'].append(copy.deepcopy(layer))
    result['crossGrids']=grid_result(project,p,s);result['crossAssistant']=p
    if p['setGrid']:result['grid']=False;result['crossSnap']=p['snapGrid']
    result['threadBook']={**result.get('threadBook',{}),**book}
    if len(result['layers'])>MAX_LAYERS:raise ValueError(f'The result exceeds {MAX_LAYERS} layers. Turn off Keep originals or convert a smaller selection.')
    preview=None;artwork=None
    if output:
        proposed={**result,'layers':output};artwork=s.build_svg(proposed).decode()
        preview=preferences.preview({'project':proposed,'settings':preferences.effective(project)},s)['preview']
    return {'project':result,'selectedIds':selected_ids,'settings':p,'preview':preview,'artwork':artwork,'images':image_previews,'cells':cell_count,'outputLayers':len(selected_ids),'sources':list(sources)}
