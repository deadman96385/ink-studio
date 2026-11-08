"""Native, non-sewing troubleshooting reports from installed validation code."""
import studio_runtime
import copy,json,tempfile,uuid
from pathlib import Path
from lxml import etree as ET
from element_info import RUNTIME

DEFAULTS={'errors':True,'warnings':True,'types':True,'pointerSize':5,'fontSize':2,'labels':'number'}
MAX_PROBLEMS=10000

def options(value,s):
    if not isinstance(value,dict) or set(value)-set(DEFAULTS):raise ValueError('Invalid troubleshooting options.')
    result={**DEFAULTS,**value}
    if any(type(result[k]) is not bool for k in ('errors','warnings','types')) or result['labels'] not in ('number','name'):raise ValueError('Invalid troubleshooting display.')
    for k in ('pointerSize','fontSize'):result[k]=s.number(result[k],1,800,'Troubleshooting '+k)
    return result

def settings(project,s):
    row=project.get('troubleshootDisplay')
    if row is None:return
    if not isinstance(row,dict) or type(row.get('visible')) is not bool or not isinstance(row.get('signature'),str) or len(row['signature'])>100:raise ValueError('Invalid troubleshooting report.')
    options(row.get('options',{}),s)
    problems=row.get('problems')
    if not isinstance(problems,list) or len(problems)>MAX_PROBLEMS:raise ValueError('Inspect a smaller selection: a report supports 10,000 findings.')
    for number,p in enumerate(problems,1):
        if not isinstance(p,dict) or p.get('severity') not in ('error','warning','type') or not isinstance(p.get('position'),list) or len(p['position'])!=2:raise ValueError('Invalid troubleshooting finding.')
        if type(p.get('number')) is not int or p['number']!=number:raise ValueError('Invalid troubleshooting finding number.')
        for n in p['position']:s.number(n,-100000,100000,'Problem position')
        for k in ('name','description','elementId','layerName','layerId'):
            if p.get(k) is not None and (not isinstance(p[k],str) or len(p[k])>20000):raise ValueError('Invalid troubleshooting message.')
        if not isinstance(p.get('steps'),list) or len(p['steps'])>100 or any(not isinstance(v,str) or len(v)>20000 for v in p['steps']):raise ValueError('Invalid troubleshooting guidance.')
    ids=row.get('ids')
    if ids is not None and (not isinstance(ids,list) or not ids or any(not isinstance(id,str) for id in ids)):raise ValueError('Invalid troubleshooting scope.')

def command(path,ids,opts):
    return studio_runtime.worker_command('--native-troubleshoot',
        '--pointer-size='+str(opts['pointerSize']),'--font-size='+str(opts['fontSize']),
        '--show-errors='+str(opts['errors']),'--show-warnings='+str(opts['warnings']),'--show-type-warning='+str(opts['types']),
        *['--id=layer-'+str(i) for i in ids],str(path))

def generate(data,s,download=False):
    from linked import resolve
    from stitchplan import selection
    project=resolve(data.get('project'),s);opts=options(data.get('options',{}),s);ids=data.get('ids')
    if ids is not None and (not isinstance(ids,list) or any(not isinstance(id,str) for id in ids)):raise ValueError('Select visible artwork to troubleshoot.')
    inspected=selection(project,ids)
    for l in inspected['layers']:l.pop('link',None);l.pop('linkedHelper',None)
    source=s.build_svg(inspected)
    selected=[i for i,l in enumerate(project['layers']) if l.get('visible',True) and l.get('role','artwork')=='artwork' and l.get('type')!='image' and (ids is None or l['id'] in ids)]
    if not selected:raise ValueError('Select visible artwork to troubleshoot.')
    # Inspect every category for immediate display filtering. The optional SVG
    # download runs the requested desktop filters, including descriptions.
    engine_options=opts if download else {**opts,'errors':True,'warnings':True,'types':True}
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-troubleshoot-') as tmp:
        path=Path(tmp)/'source.svg';path.write_bytes(source)
        raw=s.run(command(path,selected,engine_options),240,headless=True)
    if len(raw)>s.MAX_BODY:raise ValueError('This report is too large. Inspect a smaller selection.')
    report=json.loads(raw)
    if report.get('error'):raise ValueError('Ink/Stitch could not check this artwork: '+report['error'])
    for number,p in enumerate(report['problems'],1):
        i=p.pop('layerIndex');layer=project['layers'][i] if i is not None and 0<=i<len(project['layers']) else None
        p.update(number=number,layerId=layer['id'] if layer else None,layerName=layer.get('name','Layer') if layer else 'Imported object')
    result={'problems':report['problems'],'options':opts,'ids':ids}
    settings({'troubleshootDisplay':{**result,'visible':True,'signature':''}},s)
    if download:
        original=s.xml(source);rendered=s.xml(report['svg'].encode() or source);group=rendered.find(".//*[@id='__validation_layer__']")
        if group is not None:
            existing={e.get('id') for e in original.iter() if e.get('id')};defs=ET.SubElement(original,'{'+s.SVG+'}defs')
            for d in rendered.findall('{'+s.SVG+'}defs'):
                for child in d:
                    if child.get('id') and child.get('id') not in existing:defs.append(copy.deepcopy(child));existing.add(child.get('id'))
            if not len(defs):original.remove(defs)
            original.append(copy.deepcopy(group));s.command_symbols.hide(original)
        filename='troubleshoot-'+uuid.uuid4().hex+'.svg'
        (s.DATA/'exports'/filename).write_bytes(ET.tostring(original,xml_declaration=True,encoding='UTF-8'))
        result['url']='/files/'+filename
    return result
