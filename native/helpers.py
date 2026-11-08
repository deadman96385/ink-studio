"""Live, editable guide/anchor/pattern layers attached to embroidery objects."""
import copy
from lxml import etree as ET
from digitizing import geometry, inkex

ROLES=('guide-line','anchor-line','pattern')

def attach_helpers(root,content,target,layers,s):
    helpers=[l for l in layers if l.get('helperTarget')==target['id'] and l.get('role') in ROLES and l.get('visible',True)]
    if not helpers:return
    if len(helpers)>16:raise ValueError('Use at most 16 helper paths for one layer.')
    parents=[]
    for e in content.iter():
        if ET.QName(e).localname in ('path','rect','ellipse','circle','polygon','polyline','line') and e.getparent() not in parents:
            if any(ET.QName(a).localname=='defs' for a in e.iterancestors()):continue
            parents.append(e.getparent())
    for helper in helpers:
        if helper.get('type') not in ('rectangle','ellipse','path'):raise ValueError('Separate SVG or lettering paths before using them as a helper.')
        source=copy.deepcopy(helper);source.pop('role',None);source.pop('helperTarget',None)
        source['borderEnabled']=False;source.pop('entry',None);source.pop('exit',None)
        source['advanced']={};role=helper['role']
        filled=role=='pattern' and helper.get('helperFilled',helper.get('stitch')=='fill')
        satin_guide=role=='guide-line' and (helper.get('stitch')=='satin' or str(helper.get('originalParams',{}).get('satin_column','')).lower()=='true')
        source['stitch']='satin' if satin_guide else 'fill' if filled else 'running';source['fillMethod']='tatami_fill'
        source.pop('linkedHelper',None)
        items=geometry(s.build_svg({'version':1,'layers':[source]},helper_mode=True))
        marker_id='inkstitch-'+role+'-marker'
        if not root.xpath('//*[@id=$id]',id=marker_id):
            defs=ET.SubElement(root,'{'+s.SVG+'}defs');ET.SubElement(defs,'{'+s.SVG+'}marker',id=marker_id,markerWidth='.1',markerHeight='.1')
        for parent in parents:
            transform=inkex.Transform()
            for ancestor in reversed([parent,*parent.iterancestors()]):transform @=inkex.Transform(ancestor.get('transform',''))
            for _,path,_ in items:
                d=str(path.transform(-transform));style=f'display:none;fill:{"#000000" if filled else "none"};stroke:{"none" if filled else "#000000"};stroke-width:.2;marker-start:url(#{marker_id})'
                element=ET.SubElement(parent,'{'+s.SVG+'}path',d=d,style=style)
                element.set('{'+s.INK+'}label',str(helper.get('name',role))[:100])
                if satin_guide:element.set('{'+s.STITCH+'}satin_column','True')
                if role=='pattern' and not filled:
                    values=str(helper.get('patternInterval','1')).split()
                    if not 1<=len(values)<=20 or any(not v.isdigit() or not 1<=int(v)<=100 for v in values):raise ValueError('Pattern intervals must be 1–20 whole numbers from 1 to 100.')
                    offset=s.number(helper.get('patternOffset',0),0,1000,'Pattern offset')
                    if int(offset)!=offset:raise ValueError('Pattern offset must be a whole number.')
                    element.set('{'+s.STITCH+'}pattern_interval',' '.join(values));element.set('{'+s.STITCH+'}pattern_offset',str(int(offset)))

def require_guides(project):
    layers=project.get('layers',[])
    for layer in layers:
        if layer.get('visible',True) and layer.get('role','artwork')=='artwork' and layer.get('stitch')=='fill' and layer.get('fillMethod')=='guided_fill':
            if not any(l.get('role')=='guide-line' and l.get('helperTarget')==layer['id'] and l.get('visible',True) for l in layers):
                raise ValueError('Assign a visible guide line to '+layer.get('name','the guided fill')+' using Digitize → Guides & patterns.')
        if layer.get('role')=='anchor-line' and layer.get('visible',True):
            target=next((t for t in layers if t['id']==layer.get('helperTarget')),None)
            if target and ((target.get('stitch')=='fill' and target.get('fillMethod')=='guided_fill') or target.get('originalParams',{}).get('fill_method')=='guided_fill'):continue
            if not any(l.get('role')=='guide-line' and l.get('helperTarget')==layer.get('helperTarget') and l.get('visible',True) and (l.get('stitch')=='satin' or str(l.get('originalParams',{}).get('satin_column','')).lower()=='true') for l in layers):
                raise ValueError('An anchor line needs a guided fill or a satin-column guide attached to the same ripple layer.')
