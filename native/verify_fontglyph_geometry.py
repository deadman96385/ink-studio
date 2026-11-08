"""Verify physical stroke widths and clipping across native font generation."""
from verification import DATA
import copy
import json
from pathlib import Path
import tempfile
import uuid
import server as s
import fontworkspaces as fw
import fontlibrary as fl
from operations import operate


def preview(project):
    with tempfile.TemporaryDirectory() as tmp:
        svg=Path(tmp)/'source.svg';pes=Path(tmp)/'source.pes';svg.write_bytes(s.build_svg(project))
        with s.ENGINE_LOCK:pes.write_bytes(s.run([s.ENGINE,'--extension=output','--format=pes',str(svg)]))
        return s.stitch_data(pes)


def check(name,layer,tolerance=.2):
    w=fw.create({'name':name+' glyph verification'},s)
    p=fw.glyph_project({'id':w['id'],'glyph':'Z','variant':'ltr'},s)['project'];p['layers']=layer if isinstance(layer,list) else [layer]
    native=preview(p);saved=fw.save_glyph({'project':p},s);w=saved['workspace']
    published=fw.publish({'id':w['id'],'revision':w['revision']},s);font=published['font']['id']
    result=s.lettering({'font':font,'text':'Z','scale':100,'trim':'off'})['preview']
    reloaded=fw.glyph_project({'id':w['id'],'glyph':'Z','variant':'ltr'},s)['project'];again=preview(reloaded)
    report={k:[native[k],result[k],again[k]] for k in ('width','height','stitches')}
    print(name,json.dumps(report),flush=True)
    for k in ('width','height'):
        assert abs(native[k]-result[k])<tolerance,(name,k,report)
        assert abs(native[k]-again[k])<tolerance,(name,k,report)
    # Fill rows are placed in document coordinates. Moving a glyph to the
    # baseline can shift the last row by one configured row spacing.
    assert abs(native['stitches']-result['stitches'])<=max(4,native['stitches']*.1),(name,report)
    assert [t['color'] for t in native['threads']]==[t['color'] for t in result['threads']]==[t['color'] for t in again['threads']],(name,'colors',report)
    fl.set_state({'font':font,'hidden':True},s)
    return report


if __name__=='__main__':
    zigzag=dict(id=uuid.uuid4().hex,name='Wide zigzag',type='path',x=20,y=50,width=20,height=10,rotation=0,color='#224466',stitch='zigzag',strokeWidth=3,spacing=.4,stitchLength=2.5,points=[[0,0],[1,1]],visible=True)
    reports={'zigzag':check('Zigzag width',zigzag)}
    raw=f'''<svg xmlns="{s.SVG}" xmlns:inkstitch="{s.STITCH}" width="100mm" height="100mm" viewBox="0 0 100 100"><defs><clipPath id="clip"><path d="M0 0H10V12H0Z"/></clipPath></defs><g transform="translate(20,50) scale(1.5)"><path id="clipped" d="M0 0H20V12H0Z" fill="#326655" clip-path="url(#clip)" inkstitch:fill_underlay="False" inkstitch:row_spacing_mm="0.4"/></g></svg>'''
    asset=s.import_svg({'svg':raw});layer=dict(id=uuid.uuid4().hex,name='Clipped fill',type='import',asset=asset['key'],x=20,y=40,width=asset['width'],height=asset['height'],rotation=0,stitch='original',recolor=False,visible=True)
    reports['clipped']=check('Clipped fill',layer,.41)
    gradient=dict(id=uuid.uuid4().hex,name='Gradient fill',type='rectangle',x=20,y=45,width=16,height=18,rotation=25,color='#326655',stitch='fill',fillMethod='linear_gradient_fill',spacing=.4,stitchLength=2.5,underlay=False,angle=45,visible=True)
    try:fw.source_document({'version':1,'layers':[gradient],'fontGlyph':{'originX':20,'baselineY':65}},'Z',s)
    except ValueError as e:assert 'editable color blocks' in str(e)
    else:raise AssertionError('Unsupported live gradient paint was silently accepted')
    blocks=operate({'tool':'gradient_blocks','layers':[gradient],'params':{}},s)['layers']
    reports['gradientColorBlocks']=check('Gradient color blocks',blocks,.41)
    (DATA / 'font-glyph-geometry-verification.json').write_text(json.dumps(reports,indent=2))
