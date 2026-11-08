"""Guides, patterns and anchors influence embroidery without sewing themselves."""
from verification import DATA
import copy,json
from pathlib import Path
from verify_native import api,export,rectangle

def main():
    project={'version':1,'id':'helper-verification','name':'Guided fill verification','fabric':'#ffffff'}
    target=rectangle(id='target',x=30,y=30,width=30,height=20,radius=0,underlay=False)
    guide={'id':'guide','type':'path','name':'Direction guide','role':'guide-line','helperTarget':'target','x':-10,'y':38,'width':100,'height':8,
        'stitch':'running','color':'#ff0000','points':[[0,.5],[.5,0],[1,.5]]}
    plain=export({**project,'layers':[target]})['preview']
    guided_target={**target,'fillMethod':'guided_fill'}
    guided=export({**project,'layers':[guided_target,guide]});g=guided['preview']
    assert g['segments']!=plain['segments'];assert len(g['threads'])==1 and g['width']<31 and g['height']<21,g
    parallel=export({**project,'layers':[{**guided_target,'advanced':{'guided_fill_strategy':1}},guide]})['preview'];assert parallel['segments']!=g['segments']
    export({**project,'layers':[guided_target]},expect_error='Assign a visible guide line')
    # A filled pattern removes top needle points inside the mask, not thread color.
    mask=rectangle(id='mask',name='Embossing mask',x=36,y=34,width=18,height=12,role='pattern',helperTarget='target',helperFilled=True,color='#ff0000')
    embossed=export({**project,'layers':[target,mask]})['preview'];assert embossed['stitches']<plain['stitches']
    line={**guide,'id':'pattern','role':'pattern','x':45,'y':30,'width':.2,'height':20,'points':[[0,0],[0,1]],'patternInterval':'1','patternOffset':0}
    patterned=export({**project,'layers':[target,line]})['preview'];assert patterned['stitches']>plain['stitches']
    # Markers stay recognized after prefixes are assigned to imported SVG IDs.
    raw=((DATA / 'exports')/Path(guided['svg']).name).read_text();asset=api('/api/import',{'name':'guided.svg','svg':raw})
    imported={'id':'import','type':'import','asset':asset['key'],'name':'Guided SVG','x':30,'y':30,'width':asset['width'],'height':asset['height'],'color':target['color'],'stitch':'original','recolor':False}
    reopened=export({**project,'layers':[imported]})['preview'];assert abs(reopened['stitches']-g['stitches'])<=g['stitches']*.03,(reopened['stitches'],g['stitches'])
    separated=api('/api/vector',{'operation':'explode','layers':[imported]})['layers']
    assert any(l.get('role')=='guide-line' for l in separated)
    separated_preview=export({**project,'layers':separated})['preview']
    assert abs(separated_preview['stitches']-g['stitches'])<=g['stitches']*.03
    restored=api('/api/restore',{'project':api('/api/backup',{'project':{**project,'layers':[guided_target,guide]}})})
    assert restored['layers']==[guided_target,guide]
    # Ink/Stitch 3.3.0 extends guide endpoints with an unseeded <0.01px
    # perturbation to avoid a GEOS issue. Compare geometry/parameters exactly
    # and generated stitch counts with a narrow tolerance.
    restored_output=export(restored)
    assert ((DATA / 'exports')/Path(restored_output['svg']).name).read_text()==raw
    assert abs(restored_output['preview']['stitches']-g['stitches'])<=g['stitches']*.03
    # Helpers are independently editable via the same node conversion API.
    edited=api('/api/vector',{'operation':'nodes','layers':[guide]})['layers'][0];assert edited['role']=='guide-line' and edited['helperTarget']=='target'
    # Ripple guide and anchor share the same native helper relationship.
    ripple={**target,'stitch':'ripple','type':'path','points':[[0,0],[.5,1],[1,0]],'advanced':{'line_count':10,'scale_start':100,'scale_end':50}}
    ripple_guide={**guide,'x':30,'y':30,'width':30,'height':20,'points':[[0,0],[1,1]]}
    rp=export({**project,'layers':[ripple,ripple_guide]})['preview'];assert rp['stitches']>10
    satin_guide={**ripple_guide,'id':'satin-guide','stitch':'satin','height':10,'contours':[{'closed':False,'nodes':[{'x':x,'y':y,'in':[x,y],'out':[x,y]} for x in (0,1)]} for y in (0,1)]}
    sp=export({**project,'layers':[ripple,satin_guide]})['preview']
    anchor={**line,'id':'anchor','role':'anchor-line','x':30,'y':40,'width':15,'height':.2,'points':[[0,0],[1,0]]}
    ap=export({**project,'layers':[ripple,satin_guide,anchor]})['preview'];assert ap['stitches']>10 and ap['segments']!=sp['segments']
    report={'result':'passed','plain':plain['stitches'],'guided':g['stitches'],'parallelGuide':parallel['stitches'],'embossed':embossed['stitches'],'linePattern':patterned['stitches'],'rippleGuide':rp['stitches'],'rippleSatinGuide':sp['stitches'],'rippleAnchor':ap['stitches'],'anchorChangesGeometry':True,'guideOutsideHoopIgnored':True,'svgRoundTrip':reopened['stitches'],'backupRoundTrip':'passed'}
    (DATA / 'helpers-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
