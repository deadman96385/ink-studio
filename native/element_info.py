"""Desktop Element Info, captured from the installed engine without a GUI."""
import studio_runtime
import json,tempfile
from pathlib import Path
from linked import resolve

RUNTIME='/usr/local/bin/native-inkstitch-info'

def command(path,ids,reference=False):
    return studio_runtime.worker_command(*(['--native-reference'] if reference else []),*['--id='+id for id in ids],str(path))

def inspect(data,s):
    project=resolve(data.get('project'),s)
    ids=data.get('ids');eligible={l['id']:i for i,l in enumerate(project['layers']) if l.get('visible',True) and l.get('role','artwork')=='artwork' and l.get('type')!='image'}
    if ids is not None and (not isinstance(ids,list) or not ids or any(not isinstance(id,str) or id not in eligible for id in ids) or len(ids)!=len(set(ids))):raise ValueError('Select visible embroidery to inspect.')
    selected=[i for id,i in eligible.items() if ids is None or id in ids]
    if not selected:raise ValueError('Add visible embroidery to inspect. References and guides do not sew.')
    from stitchplan import selection
    from svgprep import unlink
    from cutwork import prepare_cutwork
    inspected=selection(project,ids)
    # Geometry and inherited helpers are already resolved. Freeze this query
    # copy before hiding unselected sources, so resolving again cannot hide a
    # selected linked copy's inherited guides along with its source layer.
    for layer in inspected['layers']:
        layer.pop('link',None);layer.pop('linkedHelper',None)
    source=s.build_svg(inspected)
    # Desktop Element Info has no method label for Clone and raises before
    # exporting its table. Inspect an engine-unlinked temporary copy instead.
    # This retains layer ownership while leaving saved SVG links untouched.
    source,clones=unlink(source,s)
    # Apply the same cutting-color workaround as actual machine exports.
    source,cutting=prepare_cutwork(source,s)
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-element-info-') as tmp:
        path=Path(tmp)/'source.svg';path.write_bytes(source)
        raw=s.run(command(path,['layer-'+str(i) for i in selected]),240,headless=True)
    if len(raw)>s.MAX_BODY:raise ValueError('This report is too large. Inspect a smaller selection.')
    report=json.loads(raw)
    if report.get('error'):raise ValueError('Ink/Stitch could not inspect '+((report.get('elementId') or 'this artwork')+': '+report['error']))
    summary=[]
    for item in report['items'][1:]:
        if item['headline']:break
        if item['name']:summary.append(item)
    elements=[]
    for i,element in enumerate(report['elements']):
        index=element['layerIndex'];layer=project['layers'][index] if index is not None and 0<=index<len(project['layers']) else None
        items=element['items'];header=next((r for r in items if r['headline']),{})
        elements.append({'number':i+1,'id':element['id'],'layerId':layer['id'] if layer else None,'layerName':layer.get('name','Layer') if layer else header.get('name',element['id']),
                         'label':header.get('name',element['id']),'color':header.get('value',''),'fields':[r for r in items if r['name'] and not r['headline']]})
        needle=cutting.get(elements[-1]['color'])
        if needle:
            elements[-1]['cutworkNeedle']=int(needle['number'])
            elements[-1]['fields'].append({'name':'Cutting needle','value':needle['name'],'headline':False,'warning':False})
    tsv=report['tsv']
    if cutting:
        assignments={(e['id'],next(f['value'] for f in e['fields'] if f['name']=='Type')):str(e.get('cutworkNeedle','')) for e in elements}
        lines=tsv.splitlines();tsv=lines[0]+'\tcutwork_needle\n'+''.join(line+'\t'+assignments.get(tuple(line.split('\t')[:2]),'')+'\n' for line in lines[1:])
    return {'summary':summary,'elements':elements,'tsv':tsv,'scope':'selection' if ids is not None else 'whole','selectedLayers':len(selected),'inspectedLayers':len({e['layerId'] for e in elements if e['layerId']}),'resolvedClones':clones,'cutwork':bool(cutting),'engine':studio_runtime.resource('VERSION').read_text().strip()}
