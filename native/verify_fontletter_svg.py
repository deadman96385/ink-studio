"""SVG-to-font import retains physical zigzag width and exact stitches."""
from verification import DATA
import base64
import json
from pathlib import Path
import server as s
import fonttools as ft
import fontworkspaces as fw
import fontlibrary as fl
from verify_fontglyph_geometry import preview

if __name__=='__main__':
    layer=dict(id='svg-letter-test',name='Wide zigzag',type='path',x=20,y=50,width=20,height=10,rotation=0,color='#224466',stitch='zigzag',strokeWidth=3,spacing=.4,stitchLength=2.5,points=[[0,0],[1,1]],visible=True)
    project={'version':1,'layers':[layer]};before=preview(project);raw=s.build_svg(project)
    w=ft.convert({'kind':'letters','name':'SVG letter import verification','commands':'params','files':[{'name':'Z.svg','glyph':'Z','content':base64.b64encode(raw).decode()}]},s)
    pub=fw.publish({'id':w['id'],'revision':w['revision']},s)
    after=s.lettering({'font':pub['font']['id'],'text':'Z','scale':100,'trim':'off'})['preview']
    report={k:[before[k],after[k]] for k in ('width','height','stitches')}
    assert all(a==b for a,b in report.values()),report
    (DATA / 'font-svg-letter-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    fl.set_state({'font':pub['font']['id'],'hidden':True},s)
