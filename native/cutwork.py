"""Preserve cutting-direction colors around Ink/Stitch 3.3.0's color wrapper bug."""
import io
import zipfile
from lxml import etree as ET
from digitizing import geometry,inkex,STITCH

def prepare_cutwork(raw,s):
    doc=inkex.load_svg(io.BytesIO(raw)).getroot();book={};ordinary=set()
    if not any(e.get('{'+STITCH+'}cutwork_needle') not in (None,'0') for e in doc.iter()):return raw,{}
    from svg_structure import clone
    if any(clone(e) for e in doc.iter()):
        from svgprep import unlink
        raw,_=unlink(raw,s);doc=inkex.load_svg(io.BytesIO(raw)).getroot()
    if doc.xpath('//*[local-name()="linearGradient"]'):raise ValueError('Convert gradients to color blocks before combining them with cutwork.')
    for e,_,style in geometry(raw,allow_effects=True):
        value=e.get('{'+STITCH+'}cutwork_needle')
        if value=='0':value=None
        paint=str(style.get('stroke','none'))
        if value is None and str(style.get('fill','none'))!='none':
            try:ordinary.add('#%02x%02x%02x'%tuple(inkex.Color(str(style.get('fill'))).to_rgb()))
            except (ValueError,TypeError):pass
        if paint=='none':continue
        color='#%02x%02x%02x'%tuple(inkex.Color(paint).to_rgb())
        if value is None:ordinary.add(color);continue
        if value not in ('1','2','3','4'):raise ValueError('Cutwork needle numbers must be 1–4.')
        if color in book and book[color]['number']!=value:raise ValueError('Use a different identification color for each cutting needle.')
        book[color]={'name':'Cut '+value,'number':value,'brand':'Cutwork','chart':'Cut '+value}
    if not book:return raw,{}
    if ordinary & set(book):raise ValueError('Use different colors for cutting directions and ordinary sewing threads.')
    # Stroke.color wraps an existing ThreadColor as ThreadColor, which turns
    # every cutting direction black in 3.3.0. Generate their same running
    # stitches without that wrapper; retain Cut N metadata in the INF export.
    for e in doc.iter():e.attrib.pop('{'+STITCH+'}cutwork_needle',None)
    return ET.tostring(doc),book

def cutwork_pattern(pes,book,s):
    pattern=s.pystitch.read_pes(io.BytesIO(pes))
    for thread in pattern.threadlist:
        item=book.get(thread.hex_color())
        if item:
            thread.description=item['name'];thread.chart=item['chart'];thread.catalog_number=item['number'];thread.brand=item['brand']
    return pattern

def bundle(base,pes,book,s):
    folder=s.DATA/'exports';pattern=cutwork_pattern(pes,book,s)
    for ext in ('exp','inf'):s.pystitch.write(pattern,str(folder/(base+'.'+ext)),{'encode':False})
    name=base+'-cutwork.zip'
    with zipfile.ZipFile(folder/name,'w',zipfile.ZIP_DEFLATED) as z:
        for ext in ('exp','inf','svg','project.json','txt'):
            f=folder/(base+'.'+ext)
            if f.exists():z.write(f,base[33:]+'.'+ext)
    return '/files/'+name
