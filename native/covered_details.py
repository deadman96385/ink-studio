"""Undersew interior detail islands; leave the editable paint stack untouched.

Small contrasting details can share travel beneath a later dense cover. Matching
knockouts leave their original visible shapes. Edge details remain on top.
"""
import studio_runtime
import copy,hashlib,json,tempfile
from pathlib import Path
from lxml import etree as ET
from shapely.ops import unary_union
from digitizing import inkex,path_contours

def dense(l):
    a=l.get('advanced',{})
    return (l.get('type') in ('path','rectangle','ellipse') and l.get('stitch')=='fill' and
        l.get('fillMethod','tatami_fill') in ('tatami_fill','legacy_fill') and l.get('spacing',.4)<=.5 and
        not(set(a)-{'min_stitch_length_mm','min_jump_stitch_length_mm','ties'}) and a.get('min_stitch_length_mm',0)<=.3 and
        not any(l.get(k) for k in ('locked','link','borderEnabled','ignoreLayer','ignoreObject','entry','exit','targetPoint','routeStart','routeEnd','stopAfter','trimCommand','stopCommand')))

def transform(l):
    w,h=l['width'],l['height']
    return (inkex.Transform(translate=(l['x'],l['y']))@inkex.Transform(rotate=(l.get('rotation',0),w/2,h/2))@
        inkex.Transform(translate=(w if l.get('flipX') else 0,h if l.get('flipY') else 0))@
        inkex.Transform(scale=(-1 if l.get('flipX') else 1,-1 if l.get('flipY') else 1)))

def contours(shape,l):
    from components import polygon_path
    result=path_contours(polygon_path(shape).transform(-transform(l)));w,h=l['width'],l['height']
    for c in result:
        for n in c['nodes']:
            n['x']/=w;n['y']/=h
            for k in ('in','out'):n[k]=[n[k][0]/w,n[k][1]/h]
    return result

def shaped(l,shape):
    out=copy.deepcopy(l);out.update(type='path',contours=contours(shape,l));out.pop('points',None);out.pop('featherPreview',None)
    return out

def prepare(project,s):
    from components import world_path,path_polygon
    from footprints import envelope
    from feather import active
    from limits import MAX_LAYERS
    layers=project['layers'];shapes={};candidates=[]
    def shape(i):
        if i not in shapes:shapes[i]=path_polygon(world_path(layers[i],s))
        return shapes[i]
    for i,detail in enumerate(layers):
        if not dense(detail) or active(detail) or detail.get('visible',True)is False or detail.get('role','artwork')!='artwork' or not detail.get('groupId'):continue
        if any(h.get('helperTarget')==detail['id'] for h in layers):continue
        outline=shape(i);pieces=list(outline.geoms) if outline.geom_type=='MultiPolygon' else [outline]
        if not 2<=len(pieces)<=32:continue
        possible=[j for j,c in enumerate(layers[:i]) if c.get('groupId')==detail['groupId'] and c.get('color')!=detail['color'] and dense(c) and c.get('visible',True) and c.get('role','artwork')=='artwork']
        possible=[j for j in possible if outline.difference(shape(j).buffer(.04)).area<.01 and outline.area<shape(j).area*.35]
        if not possible:continue
        j=max(possible,key=lambda j:shape(j).area);cover=layers[j]
        if any(h.get('helperTarget')==cover['id'] for h in layers):continue
        ragged=cover.get('feather',{}).get('raggedness',.5) if active(cover) else 0
        # The pad has 0.18 mm registration overlap; the extra inset protects the
        # original outer edge, including its possible inward feather movement.
        routing_mask=shape(j).buffer(-(.12+ragged+abs(cover.get('pullCompensation',0))))
        interior=[p for p in pieces if routing_mask.covers(p.buffer(.18))]
        if len(interior)<2:continue
        hidden=unary_union(interior);pad=hidden.buffer(.18)
        matching=[k for k in range(j) if layers[k].get('color')==detail['color'] and layers[k].get('visible',True) and layers[k].get('role','artwork')=='artwork' and layers[k].get('type')!='image']
        local=[k for k in matching if layers[k].get('groupId')==detail['groupId']]
        anchor=(local or matching or [j-1])[-1]
        # Every intervening paint that used to lie below this detail needs the
        # same opening. Sparse flow layers may be clipped, but never hide travel.
        occluders=[];safe=True
        for k in range(anchor+1,i):
            l=layers[k]
            if l.get('visible',True)is False or l.get('role','artwork')!='artwork' or l.get('type')=='image' or l.get('color')==detail['color']:continue
            if l.get('stitch')=='fill' and l.get('type') in ('path','rectangle','ellipse'):
                overlap=shape(k).intersection(hidden)
                if overlap.area<.000001:continue
                # Cutting holes into a sparse texture fragments its running
                # paths and can cost more cuts than the details saved. Keep
                # those caps and their texture stitches exactly as authored.
                if l.get('fillMethod') in ('streamline_fill','wave_fill'):safe=False;break
                if l.get('locked') or l.get('link') or l.get('borderEnabled') or any(h.get('helperTarget')==l['id'] for h in layers):safe=False;break
                occluders.append(k)
            else:
                try:
                    if envelope(l,world_path(l,s),s).intersects(hidden):safe=False;break
                except ValueError:
                    # Imported/unmeasurable intervening artwork cannot be used
                    # to prove an unchanged visible stack.
                    safe=False;break
        if safe:candidates.append({'detail':i,'cover':j,'anchor':anchor,'hidden':hidden,'pad':pad,'mask':routing_mask,'occluders':occluders,'islands':len(interior),'totalIslands':len(pieces)})
    if not candidates:return project,{'groups':0,'interiorIslands':0,'edgeIslands':0,'treatments':[]}
    result=copy.deepcopy(project);remove={};holes={};insert={};treatments=[];used_ids={l['id']for l in layers}
    for c in candidates:
        i=c['detail'];source=layers[i];residual=shape(i).difference(c['hidden']);remove[i]=None if residual.is_empty else shaped(source,residual)
        identifier=source['id']+'-undersew';salt=0
        while len(identifier)>80 or identifier in used_ids:
            identifier='undersew-'+hashlib.sha256((source['id']+':'+str(salt)).encode()).hexdigest()[:40];salt+=1
        used_ids.add(identifier)
        pad=shaped(source,c['pad']);pad.update(id=identifier,name=source.get('name','Details')+' · covered undersew',smallFillFallback=False,
            underlay=False,spacing=.32,stitchLength=2,trimAfter=True,pullCompensation=0)
        pad.pop('feather',None);pad.pop('component',None);pad.pop('sceneBinding',None)
        pad['_coveredDetailMask']=c['mask'].wkt
        insert.setdefault(c['anchor'],[]).append(pad)
        for k in c['occluders']:holes.setdefault(k,[]).append(c['hidden'])
        treatments.append({'detailId':source['id'],'coverId':layers[c['cover']]['id'],'islands':c['islands'],'topIslands':c['totalIslands']-c['islands'],
            'visibleArea':c['hidden'].area,'underlap':.18,'mask':c['mask'].wkt})
    output=[]
    for i,original in enumerate(layers):
        l=remove.get(i,copy.deepcopy(original))
        if l is not None:
            if i in holes:
                cut=unary_union(holes[i]);original_shape=shape(i)
                # Preserve the original curved outside contour when every new
                # hole is internal. Otherwise use the exact boolean result.
                if original.get('contours') and original_shape.buffer(-.025).covers(cut):
                    l['contours']=copy.deepcopy(original['contours'])+contours(cut,l);l.pop('featherPreview',None)
                else:l=shaped(l,original_shape.difference(cut))
                l['_coveredDetailCover']=True
            output.append(l)
        output.extend(insert.get(i,[]))
    if len(output)>MAX_LAYERS:raise ValueError('Undersewing details exceeds the editable sewing-layer limit. Reduce the number of details.')
    result['layers']=output
    # Exact paint-mask proof: each promoted region is still cream through an
    # identically shaped opening; pads and their travel stay within the cover.
    for c in candidates:
        assert c['pad'].covers(c['hidden']) and c['mask'].covers(c['pad'])
        assert shape(c['cover']).difference(c['hidden']).union(c['hidden']).symmetric_difference(shape(c['cover'])).area<.000001
    return result,{'groups':len(candidates),'interiorIslands':sum(c['islands']for c in candidates),
        'edgeIslands':sum(c['totalIslands']-c['islands']for c in candidates),'treatments':treatments,'paintMasksPreserved':True}

def split_pads(content,layer,s):
    if not layer.get('_coveredDetailMask'):return content
    from components import path_polygon,polygon_path
    shape=path_polygon(inkex.Path(content.get('d','')));wrapper=ET.Element('{'+s.SVG+'}g')
    for piece in (shape.geoms if shape.geom_type=='MultiPolygon' else [shape]):
        e=copy.deepcopy(content);e.set('d',str(polygon_path(piece)));e.set('{'+s.STITCH+'}trim_after','True');wrapper.append(e)
    return wrapper

def route(root,group,layer,s):
    if not layer.get('_coveredDetailMask'):return
    from sewing_optimizer import write_plan
    isolated=s.svg_root()
    for child in root:
        if ET.QName(child).localname in ('defs','metadata'):isolated.append(copy.deepcopy(child))
    isolated.append(copy.deepcopy(group));raw=ET.tostring(isolated)
    config={'masks':[{'source':100000,'color':layer['color'],'mask':layer['_coveredDetailMask']}],
        'fixed':[],'reorder':True,'connect':True,'maxBridge':32,'independentElements':True}
    digest=hashlib.sha256(b'covered-details-v1'+raw+json.dumps(config,sort_keys=True).encode()).hexdigest();cache=s.DATA/'cache'/('covered-details-'+digest+'.json')
    if cache.exists():data=json.loads(cache.read_text())
    else:
        with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='covered-details-') as tmp:
            source=Path(tmp)/'source.svg';source.write_bytes(raw);params=Path(tmp)/'settings.json';params.write_text(json.dumps({**config,'source':str(source)}))
            data=json.loads(s.run(studio_runtime.worker_command('--native-sewing-optimize',str(params)),240,headless=True))
        if data.get('error'):raise ValueError('Could not route covered details: '+data['error'])
        s.write_atomic(cache,data)
    for child in list(group):group.remove(child)
    group.attrib.pop('transform',None);group.set('data-covered-details',json.dumps({k:v for k,v in data['stats'].items()if k!='bridges'}))
    write_plan(group,data['blocks'],s,'undersew-'+layer['id'])

def validate(root,source,report,s):
    """An edited design must still save real machine cuts, or use its old route."""
    if not report.get('groups'):return
    from sewing_optimizer import machine_metrics
    baseline=copy.deepcopy(source);baseline['sewingOptimization'].pop('undersewDetails',None)
    before_svg=s.build_svg(baseline,sewing=True);after_svg=ET.tostring(root)
    digest=hashlib.sha256(b'covered-readback-v1'+before_svg+after_svg).hexdigest();cache=s.DATA/'cache'/('covered-readback-'+digest+'.json')
    if cache.exists():result=json.loads(cache.read_text())
    else:
        previews=[]
        with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='covered-readback-') as tmp:
            for name,raw in [('before',before_svg),('after',after_svg)]:
                path=Path(tmp)/(name+'.svg');path.write_bytes(raw);pes=Path(tmp)/(name+'.pes')
                pes.write_bytes(s.run([s.ENGINE,'--extension=output','--format=pes','--version=6',str(path)],240,headless=True))
                previews.append(s.stitch_data(pes,True))
        before,after=map(machine_metrics,previews)
        same_colors={t['color']for t in previews[0]['threads']}=={t['color']for t in previews[1]['threads']}
        same_bounds=all(abs(a-b)<=.1 for a,b in zip(previews[0]['bounds'],previews[1]['bounds']))
        result={'accepted':after['cuts']<before['cuts'] and same_colors and same_bounds and previews[0]['stops']==previews[1]['stops'],
            'before':before,'after':after,'sameColors':same_colors,'sameBounds':same_bounds}
        s.write_atomic(cache,result)
    if not result['accepted']:
        baseline_root=s.xml(before_svg)
        for child in list(root):root.remove(child)
        root.attrib.clear();root.attrib.update(baseline_root.attrib)
        for child in baseline_root:root.append(copy.deepcopy(child))
    visible={**report,'treatments':[{k:v for k,v in t.items()if k!='mask'}for t in report['treatments']],**result}
    root.set('data-covered-detail-study',json.dumps(visible))
