"""Inkscape-rendered opacity masks, coordinate systems and embroidery cutoff."""
import base64,json,io,math,tempfile
from PIL import Image
from pathlib import Path
from shapely.geometry import Point
from lxml import etree as ET
import server as s,svg_masks
from svg_clipping import prepare as clip_prepare
from svg_structure import features,has_masks
from digitizing import geometry
from components import path_polygon
from verify_svgprep import svg,fixture,prepare

def region(body,cutoff=.5):
    raw=svg(body).encode();s.sanitize_svg(raw);converted,report=svg_masks.convert(raw,cutoff,.05,s)
    assert not has_masks(s.xml(converted));out,_=clip_prepare(converted,'vector')
    parts=[path_polygon(path,str(style.get('fill-rule','nonzero'))) for e,path,style in geometry(out)]
    from shapely import unary_union
    return unary_union(parts),report

report={}
body='<defs><mask id="m" maskUnits="userSpaceOnUse" x="10" y="10" width="40" height="40"><rect x="10" y="10" width="40" height="40" fill="white"/><circle cx="30" cy="30" r="8" fill="black"/></mask></defs><rect x="10" y="10" width="40" height="40" fill="#b96548" mask="url(#m)"/>'
a,r=region(body);assert abs(a.area-(1600-math.pi*64))<4 and not a.covers(Point(30,30)) and a.covers(Point(15,15)),(a.area,a.bounds)
report['hole']={'area':a.area,'maskedPaths':r['maskedPaths']};print('Luminance hole verified',flush=True)
body='<defs><mask id="m" maskContentUnits="objectBoundingBox"><rect width=".5" height="1" fill="white"/></mask></defs><g transform="translate(10,5) scale(2,1)"><rect x="10" y="20" width="20" height="20" fill="#b96548" mask="url(#m)"/></g>'
a,r=region(body);assert abs(a.area-400)<3 and all(abs(x-y)<.1 for x,y in zip(a.bounds,(30,25,50,45))),a.bounds
report['objectBounds']=a.bounds;print('Object-bounding-box content and transforms verified',flush=True)
body='<defs><mask id="m"><rect x="10" y="10" width="40" height="40" fill="white" opacity=".5"/></mask></defs><g mask="url(#m)"><rect x="10" y="10" width="40" height="40" fill="#b96548" mask="url(#m)"/></g>'
a,r=region(body,.4);assert a.is_empty
a,r=region(body,.2);assert abs(a.area-1600)<5
report['nested']='Two 50% masks combine before applying the cutoff.';print('Nested opacity multiplication verified',flush=True)
body='<defs><linearGradient id="g"><stop offset="0" stop-color="black"/><stop offset="1" stop-color="white"/></linearGradient><mask id="m"><rect x="10" y="10" width="40" height="20" fill="url(#g)"/></mask></defs><rect x="10" y="10" width="40" height="20" fill="#b96548" mask="url(#m)"/>'
a,_=region(body,.25);b,_=region(body,.75);assert a.area>b.area+100
report['gradientAreas']=[a.area,b.area];print('Gradient cutoff changes the stitchable region',flush=True)
body='<defs><radialGradient id="g"><stop offset="0" stop-color="white"/><stop offset="1" stop-color="black"/></radialGradient><mask id="m"><rect x="10" y="10" width="40" height="40" fill="url(#g)"/></mask></defs><rect x="10" y="10" width="40" height="40" fill="#b96548" mask="url(#m)"/>'
a,_=region(body);assert 300<a.area<330,a.area;report['radialArea']=a.area
body='<defs><mask id="m" style="mask-type:alpha"><rect x="10" y="10" width="20" height="20" fill="black"/></mask></defs><rect x="10" y="10" width="20" height="20" fill="#b96548" mask="url(#m)"/>'
a,_=region(body);assert abs(a.area-400)<3,a.area;report['alphaArea']=a.area
body='<defs><mask id="alpha" style="mask-type:alpha"><rect x="10" y="10" width="20" height="20" fill="black"/></mask><mask id="outer"><rect x="10" y="10" width="20" height="20" fill="white" mask="url(#alpha)"/></mask></defs><rect x="10" y="10" width="20" height="20" fill="#b96548" mask="url(#outer)"/>'
a,_=region(body);assert abs(a.area-400)<3,a.area;report['nestedAlphaArea']=a.area
picture=Image.new('RGBA',(80,40),'black');picture.paste('white',(0,0,40,40));buffer=io.BytesIO();picture.save(buffer,format='PNG');encoded=base64.b64encode(buffer.getvalue()).decode()
body='<defs><mask id="m"><image href="data:image/png;base64,'+encoded+'" x="10" y="10" width="40" height="20"/></mask></defs><rect x="10" y="10" width="40" height="20" fill="#b96548" mask="url(#m)"/>'
a,_=region(body);assert abs(a.area-400)<3,a.area;report['imageArea']=a.area
body='<defs><mask id="alpha" style="mask-type:alpha"><rect x="10" y="10" width="40" height="20" fill="black"/></mask><mask id="m"><g mask="url(#alpha)"><image href="data:image/png;base64,'+encoded+'" x="10" y="10" width="40" height="20"/></g></mask></defs><rect x="10" y="10" width="40" height="20" fill="#b96548" mask="url(#m)"/>'
a,_=region(body);assert abs(a.area-400)<3,a.area;report['nestedImageArea']=a.area
for resource in ['https://example.com/mask.png','data:image/svg+xml;base64,PHN2Zy8+']:
 try:s.sanitize_svg(svg('<defs><mask id="m"><image href="'+resource+'" width="10" height="10"/></mask></defs><rect width="10" height="10" mask="url(#m)"/>').encode())
 except ValueError:pass
 else:raise AssertionError('Unsafe mask image accepted')
print('Radial, alpha and embedded-image masks verified',flush=True)
p,asset=fixture('<defs><mask id="m"><rect x="10" y="10" width="20" height="20" fill="white"/><circle cx="20" cy="20" r="4" fill="black"/></mask></defs><rect x="10" y="10" width="20" height="20" fill="#b96548" mask="url(#m)"/>')
assert asset['svgFeatures']['masks']>0
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp)/'masked.svg';path.write_bytes(s.build_svg(p))
 try:s.run([s.ENGINE,'--extension=output','--format=pes','--version=6',str(path)],headless=True)
 except ValueError as e:assert 'mask cutoff' in str(e)
 else:raise AssertionError('An unconverted mask was silently ignored by the stitch engine')
r=prepare(p);assert r['preview']['stitches']>0 and not r['assets'][0]['svgFeatures']['masks'];report['machine']={'stitches':r['preview']['stitches'],'maskedPaths':r['reports'][0]['maskedPaths']}
restored=s.restore_project({'project':s.portable_project(r['project'])})
assert [{k:v for k,v in l.items() if k!='asset'} for l in restored['layers']]==[{k:v for k,v in l.items() if k!='asset'} for l in r['project']['layers']]
import preferences
assert preferences.preview({'project':restored,'settings':preferences.effective(restored)},s)['preview']['segments']==r['preview']['segments']
report['status']='passed';(s.DATA/'masks-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
