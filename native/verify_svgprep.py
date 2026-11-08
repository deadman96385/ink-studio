"""SVG clipping, local-clone import and native preparation integration checks."""
import copy,json,uuid,io
from pathlib import Path
from lxml import etree as ET
from shapely.geometry import Point
import server as s
import svgprep
from svg_clipping import prepare as clip_prepare
from svg_structure import features
from digitizing import geometry
from components import path_polygon

def svg(body):return f'<svg xmlns="{s.SVG}" xmlns:inkscape="{s.INK}" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:inkstitch="{s.STITCH}" width="100mm" height="100mm" viewBox="0 0 100 100">{body}</svg>'
def fixture(body):
    raw=svg(body);asset=s.import_svg({'name':'SVG preparation fixture','svg':raw})
    layer=dict(id='svg-source',type='import',name='SVG preparation fixture',asset=asset['key'],x=20,y=20,width=asset['width'],height=asset['height'],color='#203f38',stitch='original',recolor=False)
    return dict(version=1,id=uuid.uuid4().hex,name='SVG preparation verification',fabric='#faf7f0',grid=True,snap=True,layers=[layer]),asset
def prepare(p,**options):return svgprep.prepare(dict(project=p,ids=['svg-source'],options=options),s)

def main():
    report={}
    raw=svg('<defs><clipPath id="clip"><circle cx="30" cy="30" r="10"/></clipPath></defs><path id="shape" d="M10,10H50V50H10Z" clip-path="url(#clip)" fill="#b96548"/>').encode()
    out,info=clip_prepare(raw,'vector');assert features(s.xml(out))['clips']==0
    shape=path_polygon(geometry(out)[0][1],'evenodd');assert abs(shape.area-314.159)<1 and shape.contains(Point(30,30)) and not shape.contains(Point(15,15))
    raw=svg('<defs><clipPath id="clip" clipPathUnits="objectBoundingBox"><rect x=".25" y=".25" width=".5" height=".5"/></clipPath></defs><g transform="translate(10,5) scale(2,1)"><rect x="10" y="20" width="20" height="20" fill="#b96548" clip-path="url(#clip)"/></g>').encode()
    out,_=clip_prepare(raw,'vector');assert path_polygon(geometry(out)[0][1]).bounds==(40,30,60,40)
    raw=svg('<defs><clipPath id="clip"><path clip-rule="evenodd" d="M20,20H50V50H20Z M30,30H40V40H30Z"/></clipPath></defs><g clip-path="url(#clip)"><path d="M10,35H60" fill="none" stroke="#203f38"/><path d="M10,10H60V60H10Z" fill="#b96548"/></g>').encode()
    out,_=clip_prepare(raw,'vector');items=geometry(out);assert len(items)==3
    assert not path_polygon(items[2][1],'evenodd').contains(Point(35,35));report['clipping']='Circle, transformed object bounding boxes, group clips, even-odd holes, and split running centerlines.'
    print('Clipping geometry verified.',flush=True)
    p,a=fixture('<defs><path id="original" d="M10,10H25V25H10Z" fill="#b96548" inkstitch:angle="30"/></defs><use id="copy" xlink:href="#original" x="15" y="10"/>')
    assert a['svgFeatures']['clones']==1
    r=prepare(p,operation='unlink');assert r['preview']['stitches']>0 and not r['assets'][0]['svgFeatures']['clones'];assert r['selectedIds']==['svg-source'] and r['project']['layers'][-1]['id']=='svg-source'
    report['clones']={'before':1,'after':0,'stitches':r['preview']['stitches']};print('Clone import and installed engine unlink verified.',flush=True)
    p,a=fixture('<defs><clipPath id="clip"><circle cx="30" cy="30" r="10"/></clipPath></defs><path id="shape" d="M10,10H50V50H10Z" clip-path="url(#clip)" fill="#b96548" inkstitch:angle="35"/>')
    r=prepare(p);assert r['preview']['width']<21 and r['preview']['height']<21
    release=prepare(p,operation='release');assert release['preview']['width']>39
    needle=prepare(p,output='needle');assert not needle['assets'][0]['svgFeatures']['clips'] and 'manual_stitch' in needle['assets'][0]['svg']
    report['preparation']={'baked':r['preview']['stitches'],'released':release['preview']['stitches'],'needlePoints':needle['preview']['stitches']}
    report['status']='passed';(s.DATA/'svgprep-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
