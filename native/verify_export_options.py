"""Compare native PNG/ZIP controls with installed exporters and decoded files."""
from verification import DATA
import copy,io,json,struct,tempfile,urllib.error,zipfile
from pathlib import Path
from PIL import Image,ImageChops
import server as s
from verify_native import api,export,rectangle
from export_options import ZIP_FORMATS,options

FOLDER=(DATA / 'exports')
def file(url):return FOLDER/Path(url).name
def request(id,fmt,opts):return api('/api/export-format',{'id':id,'format':fmt,'options':opts})
def main():
    project={'version':1,'id':'export-options-example','name':'Export options example','fabric':'#e9d2ae','layers':[
        rectangle(x=20,y=20,width=8,height=6,radius=0,color='#123456',stopAfter=True,trimAfter=True),
        rectangle(x=30,y=24,width=5,height=7,radius=0,color='#c34567')],
        'threadBook':{'#123456':{'name':'Océan','brand':'Studio','number':'A1'},'#c34567':{'name':'Rose','brand':'Studio','number':'B2'}}}
    result=export(project);api('/api/save',{'project':project})
    report={'result':'working','originalStitches':result['preview']['stitches'],'images':{},'bundles':{}}
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);source=tmp/'source.svg';root=s.xml(file(result['svg']).read_bytes());view=root.find('{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}namedview')
        if view is None:view=s.ET.SubElement(root,'{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}namedview')
        view.set('pagecolor','#ffffff');source.write_bytes(s.ET.tostring(root))
        for mode in ['png','png-realistic']:
            native=request(result['id'],mode,{'dpi':150,'background':'custom','color':'#ffffff'})
            image=Image.open(file(native['url'])).convert('RGBA')
            args=['--extension='+('png_simple' if mode=='png' else 'png_realistic'),'--dpi=150']
            if mode=='png':args+=['--line_width=0.3']
            reference=Image.open(io.BytesIO(s.run([s.ENGINE,*args,str(source)],240,headless=True))).convert('RGBA')
            assert image.size==reference.size and image.tobytes()==reference.tobytes(),mode
            transparent=request(result['id'],mode,{'dpi':300,'background':'transparent'})
            rgba=Image.open(file(transparent['url'])).convert('RGBA');assert rgba.getextrema()[3][0]==0
            assert abs(rgba.width-image.width*2)<=2 and abs(rgba.height-image.height*2)<=2
            report['images'][mode]={'installedRendererPixels':'exact','dpi150':image.size,'dpi300':rgba.size,'transparent':True}
            print(mode,'pixel match',flush=True)
        thin=request(result['id'],'png',{'dpi':300,'lineWidth':.01,'background':'fabric'})
        thick=request(result['id'],'png',{'dpi':300,'lineWidth':5,'background':'custom','color':'#aaccee'})
        thin_image=Image.open(file(thin['url'])).convert('RGBA');thick_image=Image.open(file(thick['url'])).convert('RGBA')
        assert thick_image.width>thin_image.width and thick_image.height>thin_image.height
        assert dict((c,n) for n,c in thin_image.getcolors(1000000)).get((233,210,174,255),0)>100
        assert dict((c,n) for n,c in thick_image.getcolors(1000000)).get((170,204,238,255),0)>100
        report['lineWidthAndBackground']='passed'
        allopts={'filename':'Échantillon textile','formats':ZIP_FORMATS,'xRepeats':2,'yRepeats':2,'xSpacing':22,'ySpacing':-18,'simpleDpi':100,'realisticDpi':150,'background':'transparent'}
        bundle=request(result['id'],'zip',allopts);z=zipfile.ZipFile(file(bundle['url']));assert len(z.namelist())==len(ZIP_FORMATS),z.namelist()
        assert all(n.startswith('Échantillon textile') for n in z.namelist())
        native_pes=z.read('Échantillon textile.pes');assert native_pes[:8]==b'#PES0060'
        native_pattern=s.pystitch.read_pes(io.BytesIO(native_pes));assert native_pattern.threadlist[0].description=='Océan'
        assert [t.hex_color() for t in native_pattern.threadlist]==['#123456','#c34567']
        ref=s.run([s.ENGINE,'--extension=zip','--format-pes=true','--custom-file-name=reference','--x-repeats=2','--y-repeats=2','--x-spacing=22','--y-spacing=-18',str(source)],240,headless=True)
        with zipfile.ZipFile(io.BytesIO(ref)) as refzip:refpattern=s.pystitch.read_pes(io.BytesIO(refzip.read('reference.pes')))
        assert native_pattern.stitches==refpattern.stitches,'Repeated commands differ from installed ZIP'
        assert z.read('Échantillon textile.svg')==file(result['svg']).read_bytes()
        assert json.loads(z.read('Échantillon textile.project.json'))['layers']==project['layers']
        assert 'Océan' in z.read('Échantillon textile_threadlist.txt').decode()
        for fmt in ZIP_FORMATS:
            if fmt in ('project','svg','threadlist','png_simple','png_realistic'):continue
            path=tmp/('output.'+fmt);path.write_bytes(z.read('Échantillon textile.'+fmt));pattern=s.pystitch.read(str(path))
            assert pattern is not None,fmt
            if fmt not in ('inf','col','edr'):assert len(pattern.stitches)>0,fmt
        assert Image.open(io.BytesIO(z.read('Échantillon textile_realistic.png'))).getextrema()[-1][0]==0
        report['bundles']['allFormats']={'files':z.namelist(),'commands':len(native_pattern.stitches),'stitches':bundle['preview']['stitches'],'width':bundle['preview']['width'],'height':bundle['preview']['height'],'installedRepeatedCommands':'exact','colorsAndNames':'exact'}
        print('all bundle formats and repeats match',flush=True)
        single=request(result['id'],'zip',{});singlezip=zipfile.ZipFile(file(single['url']));singlepes=next(n for n in singlezip.namelist() if n.endswith('.pes'))
        assert s.pystitch.read_pes(io.BytesIO(singlezip.read(singlepes))).stitches==s.pystitch.read(str(file(result['pes']))).stitches
        assert len(singlezip.namelist())==4
        image_only=request(result['id'],'zip',{'formats':['png_simple'],'xRepeats':2,'xSpacing':20,'simpleDpi':100})
        assert len(zipfile.ZipFile(file(image_only['url'])).namelist())==1
        for opts in [{'xRepeats':2,'xSpacing':100},{'formats':[]},{'filename':'../bad'},{'dpi':99},{'lineWidth':0},{'xRepeats':1.5},{'yRepeats':True},{'realisticDpi':2001}]:
            try:request(result['id'],'zip',opts)
            except urllib.error.HTTPError as e:assert e.code==400
            else:raise AssertionError(opts)
        large=request(result['id'],'zip',{'formats':['pes'],'xRepeats':2,'xSpacing':100,'destination':'other'})
        assert large['preview']['width']>100
        report['validationAndOtherMachine']='passed'
        # Runtime resource bounds reject a large PNG before allocating its raster.
        try:request(result['id'],'zip',{'formats':['png_simple'],'xRepeats':20,'xSpacing':1000,'simpleDpi':2000,'destination':'other'})
        except urllib.error.HTTPError as e:assert '64 million' in e.read().decode()
        else:raise AssertionError('Oversized image accepted')
        # Export rotation remains consistent with the regular native PES path.
        rotated=export({**project,'embroiderySettings':{**s.preferences.FACTORY,'rotate_on_export':90}})
        rb=request(rotated['id'],'zip',{'formats':['pes']});rz=zipfile.ZipFile(file(rb['url']))
        assert s.pystitch.read_pes(io.BytesIO(rz.read(rz.namelist()[0]))).stitches==s.pystitch.read(str(file(rotated['pes']))).stitches
        report['rotation']='exact'
    report['result']='passed';report['exampleExport']=result['id']
    (DATA / 'export-options-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
