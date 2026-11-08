"""Reusable TTF/OTF files and shaped, editable satin-lettering blocks."""
import base64
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import re
import tempfile
import unicodedata
import uuid
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from lxml import etree as ET
from shapely import make_valid
from shapely.affinity import translate,scale as scale_shape
from shapely.geometry import Polygon
from shapely.ops import unary_union
from outline_satin import OutlinePen,satin_columns,path_data,polygon_data
from font_shaping import shape as shape_text

MAX_FONT=8*1024*1024


def folder(s):
    path=s.DATA/'outline-fonts';path.mkdir(parents=True,exist_ok=True);return path


def font_key(key):
    if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{64}',key):raise ValueError('Choose an uploaded TTF or OTF font.')
    return key


def parse(raw):
    if not 0<len(raw)<=MAX_FONT or raw[:4] not in (b'\x00\x01\x00\x00',b'OTTO'):
        raise ValueError('Choose a TrueType (.ttf) or OpenType (.otf) file smaller than 8 MB.')
    try:
        font=TTFont(io.BytesIO(raw),lazy=False)
        if not {'head','hhea','hmtx','maxp','cmap'}.issubset(font.keys()) or not any(k in font for k in ('glyf','CFF ','CFF2')):
            raise ValueError('The font has no supported vector outlines.')
        if len(font.keys())>128 or not 16<=font['head'].unitsPerEm<=16384 or not font.getBestCmap():raise ValueError('Invalid font metrics or character map.')
        font.getGlyphSet()
        return font
    except Exception as error:
        raise ValueError('This font could not be read as TTF/OTF vector outlines. Try another font file.') from error


def description(font,key,filename):
    def name(*ids):
        for index in ids:
            for item in font['name'].names if 'name' in font else []:
                if item.nameID==index:
                    try:value=item.toUnicode()
                    except (UnicodeError,LookupError):continue
                    value=''.join(c for c in value if unicodedata.category(c) not in ('Cc','Cs')).strip()
                    if value:return value
        return ''
    family=name(16,1) or 'Uploaded font';style=name(17,2)
    return {'key':key,'name':(family+(' · '+style if style else ''))[:160],'family':family[:120],
            'filename':str(filename)[:150],'format':'OTF' if font.sfntVersion=='OTTO' else 'TTF',
            'glyphCount':len(font.getGlyphOrder()),'license':name(13)[:8000],'copyright':name(0)[:4000],
            'variable':bool('fvar' in font)}


def import_font(data,s):
    value=data.get('content')
    if not isinstance(value,str) or len(value)>MAX_FONT*4//3+8:raise ValueError('Choose a TTF/OTF font smaller than 8 MB.')
    try:raw=base64.b64decode(value,validate=True)
    except (ValueError,TypeError):raise ValueError('The font file could not be read.')
    font=parse(raw)
    try:
        key=hashlib.sha256(raw).hexdigest();info=description(font,key,data.get('name','Uploaded font'))
    finally:font.close()
    directory=folder(s);path=directory/(key+'.bin')
    if not path.exists():
        stage=directory/(key+'.'+uuid.uuid4().hex+'.tmp');stage.write_bytes(raw);stage.replace(path)
    s.write_atomic(directory/(key+'.json'),info)
    return info


def get(key,s):
    key=font_key(key);path=folder(s)/(key+'.json')
    if not path.exists() or not path.with_suffix('.bin').exists():raise ValueError('This lettering font is missing. Import the original TTF/OTF or restore its project backup.')
    return json.loads(path.read_text())


def catalog(s):return sorted([json.loads(p.read_text()) for p in folder(s).glob('*.json')],key=lambda f:f['name'].casefold())


def embed(project,s):
    keys={font_key(l['ttfLettering'].get('font')) for l in s.asset_layers(project) if isinstance(l.get('ttfLettering'),dict)}
    return [{**get(key,s),'content':base64.b64encode((folder(s)/(key+'.bin')).read_bytes()).decode()} for key in sorted(keys)]


def restore(project,s):
    fonts=project.pop('embeddedOutlineFonts',[])
    if not isinstance(fonts,list) or len(fonts)>240:raise ValueError('Invalid TTF/OTF font backup.')
    for row in fonts:
        if not isinstance(row,dict):raise ValueError('Invalid TTF/OTF font backup.')
        key=font_key(row.get('key'))
        content=row.get('content')
        if not isinstance(content,str) or len(content)>MAX_FONT*4//3+8:raise ValueError('Invalid TTF/OTF font backup.')
        try:raw=base64.b64decode(content,validate=True)
        except (ValueError,TypeError):raise ValueError('Invalid TTF/OTF font backup.')
        if hashlib.sha256(raw).hexdigest()!=key:raise ValueError('The TTF/OTF font checksum does not match this backup.')
        import_font({'content':content,'name':row.get('filename','Restored font')},s)


def settings(data,s):
    if not isinstance(data,dict):raise ValueError('Enter lettering settings.')
    text=data.get('text','')
    if not isinstance(text,str):raise ValueError('Enter the text to stitch.')
    text=unicodedata.normalize('NFC',text.replace('\r\n','\n').replace('\r','\n').replace('\t','    '))
    if not text.strip() or len(text)>120 or len(text.split('\n'))>6 or any(unicodedata.category(c) in ('Cc','Cs') and c!='\n' for c in text):
        raise ValueError('Enter 1–120 characters on up to six lines.')
    result={'font':font_key(data.get('font')),'text':text}
    for key,default,low,high,label in [('height',12,3,50,'Capital height'),('widthScale',100,25,400,'Letter width'),
        ('lineGap',2,0,30,'Extra line gap'),('letterSpacing',0,-1,10,'Letter spacing'),
        ('spacing',.4,.2,1.5,'Satin spacing'),('pullCompensation',.1,0,1,'Pull compensation'),('maxLength',6,1,12,'Maximum satin stitch length')]:
        result[key]=s.number(data.get(key,default),low,high,label)
    for key,choices,default in [('align',('left','center','right'),'center'),('direction',('auto','ltr','rtl'),'auto')]:
        value=data.get(key,default)
        if value not in choices:raise ValueError('Choose a valid lettering '+key+'.')
        result[key]=value
    result['underlay']=data.get('underlay',True)
    if type(result['underlay'])is not bool:raise ValueError('Choose whether to use center-walk underlay.')
    return result


def layout(raw,font,opts):
    glyphs=font.getGlyphSet();order=font.getGlyphOrder();cmap=font.getBestCmap();cap=getattr(font['OS/2'],'sCapHeight',0) if 'OS/2' in font else 0
    if not cap:
        name=cmap.get(ord('H')) or cmap.get(ord('M'))
        pen=BoundsPen(glyphs)
        if name:glyphs[name].draw(pen)
        cap=(pen.bounds[3]-pen.bounds[1]) if pen.bounds else font['hhea'].ascent
    if cap<=0:raise ValueError('The font has no usable height metrics.')
    unit=opts['height']/cap;horizontal=opts['widthScale']/100
    leading=(font['hhea'].ascent-font['hhea'].descent+font['hhea'].lineGap)*unit+opts['lineGap']
    if leading<=0:raise ValueError('The font has invalid line spacing.')
    lines=[];cache={};glyph_count=0
    for line_index,text in enumerate(opts['text'].split('\n')):
        positioned=[];x=y=0;previous=None
        for item in shape_text(raw,text,font['head'].unitsPerEm,opts['direction'],opts['letterSpacing']!=0):
            index=item['glyph']
            if index==0 or index>=len(order):raise ValueError('This font is missing a character in the text. Choose another font or remove that character.')
            if previous is not None and item['cluster']!=previous:x+=opts['letterSpacing']
            previous=item['cluster'];name=order[index]
            if name not in cache:
                pen=OutlinePen(glyphs,unit)
                try:glyphs[name].draw(pen);cache[name]=scale_shape(pen.shape(),xfact=horizontal,yfact=1,origin=(0,0))
                except Exception as error:raise ValueError('A glyph outline could not be converted. Try a simpler font or different text.') from error
            shape=cache[name]
            if not shape.is_empty:
                positioned.append({'shape':translate(shape,xoff=x+item['x_offset']*unit*horizontal,yoff=line_index*leading-y-item['y_offset']*unit),
                                   'glyph':name,'line':line_index,'cluster':item['cluster']});glyph_count+=1
            x+=item['x_advance']*unit*horizontal;y+=item['y_advance']*unit
        lines.append((x,positioned))
    if not glyph_count:raise ValueError('The text has no stitchable vector outlines.')
    longest=max(width for width,_ in lines);result=[]
    for width,items in lines:
        offset=(longest-width)*{'left':0,'center':.5,'right':1}[opts['align']]
        for item in items:result.append({**item,'shape':translate(item['shape'],xoff=offset)})
    combined=unary_union([item['shape'] for item in result]);minx,miny,maxx,maxy=combined.bounds
    if maxx-minx>97 or maxy-miny>97:raise ValueError(f'This lettering is {maxx-minx:.1f} × {maxy-miny:.1f} mm. Reduce capital height, use fewer characters or add line breaks for the 100 mm hoop.')
    return [{**item,'shape':translate(item['shape'],xoff=-minx,yoff=-miny)} for item in result],maxx-minx,maxy-miny


def convert(data,s):
    opts=settings(data.get('settings',{}),s);info=get(opts['font'],s);raw=(folder(s)/(opts['font']+'.bin')).read_bytes()
    font=parse(raw)
    try:letters,width,height=layout(raw,font,opts)
    finally:font.close()
    color=s.color(data.get('color','#203f38'));root=s.svg_root()
    meta=ET.SubElement(root,'{'+s.SVG+'}metadata');ET.SubElement(meta,'{'+s.STITCH+'}inkstitch_svg_version').text='4'
    group=ET.SubElement(root,'{'+s.SVG+'}g',id='ttf-satin-columns');count=0;max_width=0;min_width=1000
    artwork=polygon_data(unary_union([letter['shape'] for letter in letters]))
    for glyph_index,letter in enumerate(letters):
        columns=satin_columns(letter['shape'])
        coverage=unary_union([make_valid(Polygon(col['rails'][0]+list(reversed(col['rails'][1])))) for col in columns])
        if letter['shape'].symmetric_difference(coverage).area>max(.005,letter['shape'].area*.002):
            raise ValueError('Automatic satin conversion could not retain an entire letter. Choose a simpler font or edit its outlines manually.')
        for col in columns:
            count+=1
            if count>800:raise ValueError('These letters need too many satin columns. Use fewer characters or a simpler font.')
            max_width=max(max_width,col['width']);min_width=min(min_width,col['width'])
            path=ET.SubElement(group,'{'+s.SVG+'}path',id=f'ttf-glyph-{glyph_index}-column-{count}',
                d=' '.join(path_data(points) for points in [*col['rails'],*col['rungs']]),style=f'fill:none;stroke:{color};stroke-width:.03')
            for key,value in {'satin_column':True,'zigzag_spacing_mm':opts['spacing'],'pull_compensation_mm':opts['pullCompensation'],
                'max_stitch_length_mm':opts['maxLength'],'center_walk_underlay':opts['underlay'],'reverse_rails':'none','trim_after':False}.items():
                path.set('{'+s.STITCH+'}'+key,str(value))
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='ttf-satin-') as tmp:
        source=Path(tmp)/'source.svg';source.write_bytes(ET.tostring(root))
        routed=s.run([s.ENGINE,'--extension=auto_satin','--id=ttf-satin-columns','--preserve_order=False','--trim=False','--keep_originals=False',str(source)],180,headless=True)
        doc=s.sanitize_svg(routed,max_shapes=20000)
        normalized=ET.Element('{'+s.SVG+'}g',nsmap=s.NS)
        for child in doc:
            if ET.QName(child).localname not in ('metadata','title','desc'):normalized.append(copy.deepcopy(child))
        svg=ET.tostring(normalized,encoding='unicode');key=hashlib.sha256(svg.encode()).hexdigest()
        asset={'key':key,'svg':svg,'width':width,'height':height,'name':info['name']+' lettering','svgFeatures':__import__('svg_structure').features(normalized)}
        s.write_atomic(s.DATA/'assets'/(key+'.json'),asset)
        pose=data.get('pose',{})
        if not isinstance(pose,dict):raise ValueError('Invalid lettering position.')
        cx=s.number(pose.get('cx',50),-100,200,'Lettering center X');cy=s.number(pose.get('cy',50),-100,200,'Lettering center Y')
        rotation=s.number(pose.get('rotation',0),-360,360,'Lettering rotation')
        flips={k:pose.get(k,False) for k in ('flipX','flipY')}
        if any(type(v)is not bool for v in flips.values()):raise ValueError('Invalid lettering mirror setting.')
        recipe={**opts,'version':1,'fontName':info['name'],'width':width,'blockHeight':height,'artwork':artwork}
        layer={'id':uuid.uuid4().hex,'type':'import','name':opts['text'].replace('\n',' / '),'asset':key,
               'x':cx-width/2,'y':cy-height/2,'width':width,'height':height,'rotation':rotation,**flips,
               'stitch':'original','color':color,'recolor':False,'visible':True,'locked':False,'ttfLettering':recipe}
        from multisatin import layer_preview
        preview=layer_preview({'layers':[layer]},s)['preview']
    if not preview['stitches']:raise ValueError('These outlines produced no stitches. Increase the height or use a simpler font.')
    warnings=[]
    if min_width<.8:warnings.append('Some satin strokes are narrower than 0.8 mm. Increase the height or use a bolder font for clearer stitching.')
    if max_width>opts['maxLength']:warnings.append('Wide satin stitches are split at the maximum stitch length.')
    if preview['trims']>30:warnings.append('This lettering needs many thread cuts. Review the stitch sequence before sewing.')
    if info['variable']:warnings.append('This variable font uses its default weight and width.')
    return {'asset':asset,'layer':layer,'preview':preview,'columns':count,'glyphs':len(letters),'warnings':warnings,'font':info}
