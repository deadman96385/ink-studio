"""Exercise color-band composition against real Ink/Stitch and PES output."""
from verification import DATA
import copy,json,urllib.error
from pathlib import Path
from lxml import etree as ET
from verify_native import api,export,STITCH

def main():
    l={'id':'satin','type':'path','name':'Satin','x':20,'y':35,'width':60,'height':8,'color':'#416580','stitch':'satin','spacing':.4,'satinCenter':True,
       'contours':[{'closed':False,'nodes':[{'x':0,'y':y,'in':[0,y],'out':[.3,y]},{'x':1,'y':y,'in':[.7,y],'out':[1,y]}]} for y in [0,1]],
       'multicolorSatin':{'bands':[{'color':'#416580','width':20,'blend':20},{'color':'#b96548','width':20,'blend':20},{'color':'#e9c878','width':20,'blend':0}], 'seed':'example','pullCompensation':.1}}
    p={'version':1,'id':'multisatin-verification','name':'Multicolor satin','layers':[l]};r=export(p);preview=r['preview']
    assert [t['color'] for t in preview['threads']]==[b['color'] for b in l['multicolorSatin']['bands']]
    assert preview['stitches']>500 and preview['height']<9
    means=[sum((s[1]+s[3])/2 for s in preview['segments'] if s[4]==i)/sum(s[4]==i for s in preview['segments']) for i in range(3)]
    assert means[0]>means[1]>means[2],means
    restored=export(api('/api/restore',{'project':api('/api/backup',{'project':p})}))
    assert restored['preview']['segments']==preview['segments']
    raw=((DATA / 'exports')/Path(r['svg']).name).read_bytes();root=ET.fromstring(raw)
    group=root.xpath('//*[@inkstitch:satin-multicolor]',namespaces={'inkstitch':STITCH})[0]
    assert len(group)==3 and len(json.loads(group.get('{'+STITCH+'}satin-multicolor'))['colors'])==3
    assert group[1].get('{'+STITCH+'}center_walk_underlay')=='False'
    # A reversed second rail must yield the same color geometry and exact stitches.
    reversed_layer=copy.deepcopy(l);ns=reversed_layer['contours'][1]['nodes'];ns.reverse()
    for n in ns:n['in'],n['out']=n['out'],n['in']
    rev=export({**p,'layers':[reversed_layer]})['preview'];assert rev['segments']==preview['segments']
    # Native node editing returns one master column and preserves the recipe.
    edited=api('/api/vector',{'operation':'nodes','layers':[l]})['layers'][0]
    assert len(edited['contours'])==2 and edited['multicolorSatin']==l['multicolorSatin']
    assert export({**p,'layers':[edited]})['preview']['segments']==preview['segments']
    # Editable SVG preserves engine band parameters and desktop re-edit metadata.
    asset=api('/api/import',{'svg':raw.decode(),'name':'multicolor.svg'})
    imp={'id':'imported','type':'import','asset':asset['key'],'name':'Multicolor import','x':20,'y':35,'width':asset['width'],'height':asset['height'],'color':'#416580','stitch':'original','recolor':False}
    check=export({**p,'layers':[imp]})['preview'];assert abs(check['stitches']-preview['stitches'])<=4
    separated=api('/api/vector',{'operation':'explode','layers':[l]})['layers'];assert len(separated)==3
    assert export({**p,'layers':separated})['preview']['segments']==preview['segments']
    per=copy.deepcopy(l);per['multicolorSatin']['underlayPerColor']=True
    perpreview=export({**p,'layers':[per]})['preview'];assert perpreview['stitches']>preview['stitches']
    # Entry and exit commands must bind to the first and last thread bands.
    command=export({**p,'layers':[{**l,'entry':[0,1],'exit':[1,0]}]})
    cr=ET.fromstring(((DATA / 'exports')/Path(command['svg']).name).read_bytes())
    ends=cr.xpath('//*[@inkscape:connection-end]/@inkscape:connection-end',namespaces={'inkscape':'http://www.inkscape.org/namespaces/inkscape'})
    assert len(set(ends))==2,ends
    bad=copy.deepcopy(l);bad['multicolorSatin']['bands'][0]['width']=80
    export({**p,'layers':[bad]},expect_error='total 100%')
    output={'stitches':preview['stitches'],'colors':len(preview['threads']),'size':[preview['width'],preview['height']],
            'perColorUnderlay':perpreview['stitches'],'reversedRail':'exact match','backup':'exact match','nativeNodeEditing':'master rails preserved','separatePaths':'exact match','svgImport':check['stitches'],'entryExitTargets':'first and last bands'}
    (DATA/'multisatin-verification.json').write_text(json.dumps(output,indent=2));print(json.dumps(output,indent=2))
if __name__=='__main__':main()
