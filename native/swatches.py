"""Native test-swatch grids, with real Ink/Stitch geometry and stitch previews."""
import copy
from limits import MAX_LAYERS
import hashlib
from pathlib import Path
import re
import tempfile
import uuid
from lxml import etree as ET
from digitizing import geometry
from advanced import FIELDS
from cutwork import prepare_cutwork
from threads import named_pes

# Include the desktop swatch choices plus numeric controls already exposed in
# the native editor. Parameter values are always written in physical units.
BASE=[
 ('row_spacing_mm','Fill row spacing (mm)',.2,5,.35,.05,'fill'),
 ('angle','Fill angle (degrees)',-180,180,0,15,'fill'),
 ('max_stitch_length_mm','Maximum stitch length (mm)',.5,12,2,1,'fill satin manual'),
 ('running_stitch_length_mm','Running / travel stitch length (mm)',.5,10,1.5,.5,'fill running bean ripple'),
 ('zigzag_spacing_mm','Satin / zigzag spacing (mm)',.1,5,.3,.05,'satin zigzag fill'),
 ('pull_compensation_mm','Pull compensation (mm)',0,3,0,.1,'fill satin zigzag'),
 ('pull_compensation_percent','Pull compensation (%)',-90,100,0,5,'satin'),
 ('fill_underlay_angle','Fill underlay angle (degrees)',-180,180,0,15,'fill'),
 ('fill_underlay_inset_mm','Fill underlay inset (mm)',0,5,0,.2,'fill'),
 ('fill_underlay_max_stitch_length_mm','Fill underlay stitch length (mm)',.5,10,2,.5,'fill'),
 ('fill_underlay_row_spacing_mm','Fill underlay row spacing (mm)',.3,10,1,.2,'fill'),
]
CATALOG={k:dict(key=k,label=label,min=lo,max=hi,start=start,step=step,modes=modes.split(),kind='number') for k,label,lo,hi,start,step,modes in BASE}
for f in CATALOG.values():
    f['variants']=[{'modes':f['modes'],'methods':['meander_fill'] if f['key']=='zigzag_spacing_mm' else None,'min':f['min'],'max':f['max']}]
for f in FIELDS:
    key=f.get('parameter',f['key'])
    if f['kind'] not in ('number','integer','pair','angles'):continue
    variant={'modes':f['modes'],'methods':f.get('methods'),'min':f['min'],'max':f['max']}
    if key in CATALOG:
        existing=CATALOG[key];existing['variants'].append(variant)
        existing['modes']=sorted(set(existing['modes']+f['modes']))
        existing['min']=min(existing['min'],f['min']);existing['max']=max(existing['max'],f['max'])
        continue
    start=max(f['min'],0);step=1 if f['kind']=='integer' or f['max']>=20 else .1
    CATALOG[key]={**{k:f[k] for k in ('label','min','max','modes','kind')},'key':key,'start':start,'step':step,'variants':[variant]}

def catalog():return list(CATALOG.values())

def source_layers(data,s):
    source=data.get('source','selection')
    if source=='selection':
        layers=copy.deepcopy(data.get('layers'))
        if not isinstance(layers,list) or not 1<=len(layers)<=30 or any(not isinstance(l,dict) for l in layers):raise ValueError('Select 1–30 source layers including their helpers.')
        if any(l.get('type')=='image' for l in layers):raise ValueError('Trace the image before making stitch swatches from it.')
        if not any(l.get('role','artwork')=='artwork' for l in layers):raise ValueError('Select stitched artwork for the swatch source.')
        for l in layers:l['visible']=True
        s.require_guides({'layers':layers})
        return layers
    if source not in ('fill','satin','running','zigzag'):raise ValueError('Choose selected artwork, fill, satin, running or zigzag.')
    width=s.number(data.get('sampleWidth',18),2,90,'Sample width');height=s.number(data.get('sampleHeight',12),.5,90,'Sample height')
    layer={'id':str(uuid.uuid4()),'name':source.title()+' sample','type':'rectangle','x':10,'y':10,'width':width,'height':height,'rotation':0,'radius':1,
           'color':s.color(data.get('color','#416580')),'stitch':source,'spacing':.4,'stitchLength':2.5,'underlay':True,'satinCenter':True,'visible':True}
    if source in ('satin','running','zigzag'):
        layer['type']='path';ys=[0,1] if source=='satin' else [0]
        layer['contours']=[{'closed':False,'nodes':[{'x':0,'y':y,'in':[0,y],'out':[.33,y]},{'x':1,'y':y,'in':[.67,y],'out':[1,y]}]} for y in ys]
        if source!='satin':layer['contours'][0]['nodes'][1].update(y=1,**{'in':[.67,1],'out':[1,1]})
        if source=='zigzag':layer['strokeWidth']=2
    return [layer]

def axis(value,count,s):
    if not isinstance(value,dict):raise ValueError('Choose the parameter to vary.')
    key=value.get('key','');custom=key=='custom';param=value.get('parameter','') if custom else key
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,79}',str(param)):raise ValueError('Enter an Ink/Stitch numeric parameter name, without the namespace prefix.')
    f=CATALOG.get(param)
    if not custom and not f:raise ValueError('Choose a supported swatch parameter.')
    f=f or dict(key=param,label=param,min=-1000,max=1000,kind='number',modes=[])
    start=s.number(value.get('start'),f['min'],f['max'],f['label']+' starting value')
    step=s.number(value.get('step'),-1000,1000,'Increment')
    values=[round(start+i*step,8) for i in range(count)]
    if any(not f['min']<=v<=f['max'] or f['kind']=='integer' and v!=int(v) for v in values):raise ValueError(f'{f["label"]}: keep every sample between {f["min"]:g} and {f["max"]:g}'+(' using whole numbers.' if f['kind']=='integer' else '.'))
    return {**f,'key':param,'values':values,'start':start,'step':step,'custom':custom}

def element_modes(e,style,s):
    modes=set()
    if str(style.get('fill','black'))!='none':modes.add('fill')
    if str(style.get('stroke','none'))!='none':
        if str(e.get('{'+s.STITCH+'}satin_column','')).lower() in ('true','1'):modes.add('satin')
        else:
            mode={'manual_stitch':'manual','ripple_stitch':'ripple','zigzag_stitch':'zigzag'}.get(e.get('{'+s.STITCH+'}stroke_method'),'running');modes.add(mode)
            if mode=='running':modes.add('bean')
    return modes

def applicable(a,e,style,s):
    if not a.get('variants'):return a['custom']
    modes=element_modes(e,style,s);method=e.get('{'+s.STITCH+'}fill_method','tatami_fill')
    return any(mode in v['modes'] and (mode!='fill' or not v['methods'] or method in v['methods']) and all(v['min']<=value<=v['max'] for value in a['values']) for v in a['variants'] for mode in modes)

def prepare(data,s):
    rows=int(s.number(data.get('rows',2),1,10,'Rows'));cols=int(s.number(data.get('columns',3),1,10,'Columns'))
    if data.get('rows',2)!=rows or data.get('columns',3)!=cols:raise ValueError('Rows and columns must be whole numbers.')
    count=rows*cols
    if count>36:raise ValueError('Use at most 36 samples per 100 mm swatch sheet.')
    gapx=s.number(data.get('gapX',4),0,30,'Horizontal gap');gapy=s.number(data.get('gapY',4),0,30,'Vertical gap')
    second=data.get('secondAxis')
    axes=[axis(data.get('axis'),cols if second else count,s)]
    if second:
        axes.append(axis(second,rows,s))
        if axes[0]['key']==axes[1]['key']:raise ValueError('Choose different parameters for columns and rows.')
    sources=source_layers(data,s)
    if count+len(sources)>MAX_LAYERS:raise ValueError(f'The swatches and hidden sources exceed {MAX_LAYERS} layers. Use fewer samples.')
    source=s.build_svg({'version':1,'layers':sources})
    # geometry() supplies style inheritance and hides helpers/command symbols.
    items=geometry(source);doc=items[0][0].getroottree().getroot() if items else None
    if doc is None:raise ValueError('The source has no visible embroidery geometry.')
    # Embedded SVGs can contain document-wide origin/frame-out symbols. A
    # swatch sheet has one hoop and must not duplicate those per sample.
    for use in list(doc.iter('{'+s.SVG+'}use')):
        href=use.get('{http://www.w3.org/1999/xlink}href',use.get('href',''))
        if re.match(r'#inkstitch_(origin|stop_position)(?:-|$)',href):use.getparent().remove(use)
    targets={}
    for a in axes:
        targets[a['key']]=[e.get('id') for e,_,style in items if not e.get('{'+s.INK+'}connection-start') and applicable(a,e,style,s)]
        if not targets[a['key']]:raise ValueError(a['label']+' does not apply to the source stitch method or chosen values.')
    labels=data.get('labels',True)
    if not isinstance(labels,bool):raise ValueError('Choose whether to stitch sample numbers.')
    label_color=s.color(data.get('labelColor','#272829'));label_scale=s.number(data.get('labelScale',80),70,160,'Label font scale')
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='swatch-bounds-') as tmp:
        p=Path(tmp)/'source.svg';p.write_bytes(source);x,y,w,h=s.bounds(p)
    if cols*w+(cols-1)*gapx>96 or rows*h+(rows-1)*gapy>96:raise ValueError('The source artwork is too large for this grid. Use fewer rows/columns, smaller source artwork or smaller gaps.')
    # Lettering owns ENGINE_LOCK: generate it before entering the preview lock.
    label_art=[s.lettering({'font':'small_font','text':str(i+1),'scale':label_scale,'align':'center'}) for i in range(count)] if labels else []
    label_h=max((l['height'] for l in label_art),default=0);label_w=max((l['width'] for l in label_art),default=0)
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='swatches-') as tmp:
        p=Path(tmp)/'source.svg'
        cellw=max(w,label_w);cellh=h+(label_h+2 if labels else 0)
        width=cols*cellw+(cols-1)*gapx;height=rows*cellh+(rows-1)*gapy
        if width>96 or height>96:raise ValueError(f'This grid needs {width:.1f} × {height:.1f} mm. Use fewer rows/columns, smaller source artwork or smaller gaps to fit the 100 mm hoop.')
        left=(100-width)/2;top=(100-height)/2
        layers=[];assets=[];samples=[]
        order=data.get('order','rows')
        if order not in ('rows','snake','columns'):raise ValueError('Choose a swatch sewing order.')
        sequence=([(r,c) for c in range(cols) for r in range(rows)] if order=='columns' else [(r,c) for r in range(rows) for c in (range(cols-1,-1,-1) if order=='snake' and r%2 else range(cols))])
        for r,c in sequence:
            i=r*cols+c;sample=copy.deepcopy(doc);values={}
            for j,a in enumerate(axes):
                value=a['values'][c if j==0 and second else r if j else i];values[a['key']]=value
                for e in sample.iter():
                    if e.get('id') in targets[a['key']]:e.set('{'+s.STITCH+'}'+a['key'],f'{value:g}')
            group=ET.Element('{'+s.SVG+'}g',nsmap=s.NS)
            artwork=ET.SubElement(group,'{'+s.SVG+'}g',transform=f'translate({(cellw-w)/2-x},{-y})')
            for e in sample:artwork.append(copy.deepcopy(e))
            s.prefix_ids(artwork,f'swatch-{i+1}-')
            if labels:
                info=label_art[i];text=s.xml(info['svg'].encode());s.paint(text,label_color);s.prefix_ids(text,f'label-{i+1}-')
                label=ET.SubElement(group,'{'+s.SVG+'}g',transform=f'translate({(cellw-info["width"])/2},{h+2})');label.append(text)
            raw=ET.tostring(group,encoding='unicode');key=hashlib.sha256(raw.encode()).hexdigest()
            asset={'key':key,'svg':raw,'width':cellw,'height':cellh,'name':f'Swatch {i+1}'};s.write_atomic(s.DATA/'assets'/(key+'.json'),asset);assets.append(asset)
            descriptions=[a['label']+' '+f'{values[a["key"]]:g}' for a in axes]
            layer={'id':str(uuid.uuid4()),'name':f'{i+1}. '+', '.join(descriptions),'type':'import','asset':key,'x':left+c*(cellw+gapx),'y':top+r*(cellh+gapy),'width':cellw,'height':cellh,
                   'rotation':0,'stitch':'original','recolor':False,'color':sources[0].get('color','#416580'),'visible':True,'swatchNumber':i+1,'swatchValues':values}
            layers.append(layer);samples.append({'number':i+1,'row':r+1,'column':c+1,'values':values,'layerId':layer['id']})
        sheet={'version':1,'layers':layers}
        encoded=s.build_svg(sheet);machine,cut_threads=prepare_cutwork(encoded,s);p.write_bytes(machine)
        bx,by,bw,bh=s.bounds(p)
        if bx<-.1 or by<-.1 or bx+bw>100.1 or by+bh>100.1:raise ValueError('A sample extends outside the hoop. Reduce compensation, increase spacing or use fewer samples.')
        pes=Path(tmp)/'preview.pes';pes.write_bytes(named_pes(s.run([s.ENGINE,'--extension=output','--format=pes','--version=6',str(p)],240,headless=True),{'threadBook':cut_threads}))
        preview=s.stitch_data(pes)
        if preview['width']>100 or preview['height']>100:raise ValueError('Generated swatch stitches exceed the hoop. Reduce compensation or grid size.')
    recipe={k:copy.deepcopy(v) for k,v in data.items() if k!='layers'}
    recipe['sourceIds']=[l['id'] for l in sources];recipe['generatedIds']=[l['id'] for l in layers]
    plan={'columns':cols,'rows':rows,'labels':labels,'axes':[{k:a[k] for k in ('key','label','start','step')} for a in axes], 'samples':sorted(samples,key=lambda v:v['number'])}
    return {'layers':layers,'sources':[{**l,'visible':False} for l in sources],'assets':assets,'preview':preview,'recipe':recipe,'plan':plan,'width':round(width,2),'height':round(height,2)}
