"""Supporting embroidery geometry through the installed Inkscape path engine."""
import copy,tempfile,uuid
import inkex
from pathlib import Path
from lxml import etree as ET
from digitizing import geometry,from_path
INK='http://www.inkscape.org/namespaces/inkscape'

def prepare(key,layers,params,s,preview=True):
    from multisatin import layer_preview
    if len(layers)>10:raise ValueError('Prepare at most 10 design paths at once.')
    prepared=[];root=s.svg_root();defs=ET.SubElement(root,'{'+s.SVG+'}defs')
    for i,layer in enumerate(layers):
        items=geometry(s.build_svg({'version':1,'layers':[{**layer,'borderEnabled':False}]}))
        if len(items)!=1:raise ValueError('Separate imported SVG or lettering paths first to preserve their individual settings.')
        element,path,style=items[0];base=copy.deepcopy(layer);source_id='source-'+str(i)
        # Flatten imported styles and parameters before changing their bounds.
        if base.get('stitch')=='original':
            base['originalParams']={ET.QName(k).localname:v for k,v in element.attrib.items() if k.startswith('{'+s.STITCH+'}')}
            if str(base['originalParams'].get('satin_column','')).lower()=='true':raise ValueError('Use the satin tools for columns; offsets work on outlines or filled shapes.')
            filled=str(style.get('fill','black'))!='none';stroked=str(style.get('stroke','none'))!='none'
            if key=='stroke_area' and (filled or not stroked):raise ValueError('Choose an outline with a stroke and no fill.')
            if filled and stroked:raise ValueError('Separate the fill and outline before offsetting this imported path.')
            base.update(originalFill=filled,originalStroke=stroked,originalFillRule=str(style.get('fill-rule','nonzero')),
                        originalWidth=float(inkex.units.convert_unit(str(style.get('stroke-width',.3)),'px'))*s.stroke_scale(element))
            base['color']='#%02x%02x%02x'%tuple(inkex.Color(style.get('fill') if filled else style.get('stroke')).to_rgb())
        if key=='path_offset':
            node=ET.SubElement(root,'{'+s.SVG+'}path',id=source_id,d=str(path),style='fill:#203f38;stroke:none;fill-rule:'+str(style.get('fill-rule','nonzero')))
            effect=ET.SubElement(defs,'{'+INK+'}path-effect',id='offset-'+str(i),effect='offset',lpeversion='1.3',unit='mm',offset=str(params['distance']),
                linejoin_type=params['join'],miter_limit=str(params['miter']),attempt_force_join=str(params['forceMiter']).lower(),is_visible='true')
            node.set('{'+INK+'}original-d',str(path));node.set('{'+INK+'}path-effect','#'+effect.get('id'))
        else:
            node=ET.SubElement(root,'{'+s.SVG+'}path',id=source_id,d=str(path),style=f'fill:none;stroke:#203f38;stroke-width:{params["width"]};stroke-linecap:{params["cap"]};stroke-linejoin:{params["join"]};stroke-miterlimit:{params["miter"]}')
            base.update(stitch='fill',fillMethod='tatami_fill',spacing=.4,angle=45,stitchLength=2.5,underlay=True,borderEnabled=False,originalParams={})
        prepared.append(base)
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='design-path-') as tmp:
        src=Path(tmp)/'source.svg';out=Path(tmp)/'result.svg';src.write_bytes(ET.tostring(root))
        action='object-to-path' if key=='path_offset' else 'object-stroke-to-path'
        # Offset LPE updates require an initialized document/view in Inkscape 1.4.
        s.run(['xvfb-run','-a','inkscape','--with-gui','--batch-process',str(src),'--actions=select-by-element:path;'+action+';export-filename:'+str(out)+';export-do'])
        outputs=geometry(out.read_bytes())
    result=[]
    for i,base in enumerate(prepared):
        found=[path for element,path,_ in outputs if element.get('id')=='source-'+str(i) or any(a.get('id')=='source-'+str(i) for a in element.iterancestors())]
        if not found:raise ValueError('The offset removes an entire path. Reduce the inset; the source has not changed.')
        combined=inkex.Path()
        for path in found:combined.extend(path)
        layer=from_path(combined,base);layer['id']=base['id'];layer['name']=base.get('name','Path')+(' · offset' if key=='path_offset' else ' · stroke area')
        if base.get('groupId'):layer['groupId']=base['groupId']
        result.append(layer)
        if params['keepSource']:
            original=copy.deepcopy(layers[i]);original.update(id=uuid.uuid4().hex,visible=False,name=original.get('name','Path')+' · source (hidden)');result.append(original)
    plan=layer_preview({'layers':[l for l in result if l.get('visible',True)]},s)['preview'] if preview else None
    return {'layers':result,'preview':plan,'tool':key}
