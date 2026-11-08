"""Non-sewing density overlays from the installed desktop Density Map tool."""
import copy,tempfile,uuid
from pathlib import Path
from lxml import etree as ET
import inkex

DEFAULTS={'red':6,'radiusRed':.5,'yellow':3,'radiusYellow':.5,'size':.5}
MAX_POINTS=150000

def options(value,s):
    if not isinstance(value,dict) or set(value)-set(DEFAULTS):raise ValueError('Invalid density-map settings.')
    result={**DEFAULTS,**value}
    for k in result:
        result[k]=s.number(result[k],0,99 if k in ('red','yellow') else 50,'Density '+k)
        if k in ('red','yellow') and result[k]!=int(result[k]):raise ValueError('Density thresholds must be whole numbers.')
    return result

def settings(project,s):
    row=project.get('densityMap')
    if row is None:return None
    if not isinstance(row,dict):raise ValueError('Invalid density map.')
    options(row.get('options',{}),s)
    if type(row.get('visible')) is not bool or row.get('designView') not in ('unchanged','hidden','lower_opacity'):raise ValueError('Invalid density-map display.')
    points=row.get('points')
    if not isinstance(points,list) or len(points)>MAX_POINTS:raise ValueError('A density map supports up to 150,000 stitch positions. Inspect a smaller selection.')
    for p in points:
        if not isinstance(p,list) or len(p)!=3 or type(p[2]) is not int or p[2] not in (0,1,2):raise ValueError('Invalid density marker.')
        for v in p[:2]:s.number(v,-100000,100000,'Density marker position')
    if not isinstance(row.get('signature'),str) or len(row['signature'])>100:raise ValueError('Invalid density snapshot.')
    ids=row.get('ids')
    if ids is not None and (not isinstance(ids,list) or not ids or any(not isinstance(id,str) for id in ids)):raise ValueError('Invalid density scope.')
    return row

def generate(data,s,download=False):
    from linked import resolve
    from stitchplan import selection
    from cutwork import prepare_cutwork
    project=resolve(data.get('project'),s);ids=data.get('ids');opts=options(data.get('options',{}),s)
    if ids is not None and (not isinstance(ids,list) or any(not isinstance(id,str) for id in ids)):raise ValueError('Select visible artwork for the density map.')
    selected=selection(project,ids)
    # Resolve linked guides before narrowing scope, then freeze this query copy.
    for l in selected['layers']:l.pop('link',None);l.pop('linkedHelper',None)
    source=s.build_svg(selected,sewing=True);render_source,_=prepare_cutwork(source,s)
    args=['--num-neighbors-red='+str(int(opts['red'])),'--density-radius-red='+str(opts['radiusRed']),
          '--num-neighbors-yellow='+str(int(opts['yellow'])),'--density-radius-yellow='+str(opts['radiusYellow']),
          '--indicator-size='+str(opts['size']),'--layer-visibility=0']
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='native-density-') as tmp:
        path=Path(tmp)/'source.svg';path.write_bytes(render_source)
        raw=s.run([s.ENGINE,'--extension=density_map',*args,str(path)],240,headless=True)
    if len(raw)>48*1024*1024:raise ValueError('This density map is too large. Inspect a smaller selection.')
    root=s.xml(raw);group=root.find(".//*[@id='__inkstitch_density_plan__']")
    if group is None:raise ValueError('Ink/Stitch did not return a density map.')
    points=[];counts=[0,0,0]
    for level,name in enumerate(('green','yellow','red')):
        color_group=group.find(".//*[@id='__"+name+"_density_layer__']")
        if color_group is None:continue
        for circle in color_group.iter('{'+s.SVG+'}circle'):
            transform=inkex.Transform()
            for ancestor in list(circle.iterancestors())[::-1]+[circle]:transform=transform@inkex.Transform(ancestor.get('transform',''))
            x,y=transform.apply_to_point((float(circle.get('cx')),float(circle.get('cy'))))
            points.append([x,y,level]);counts[level]+=1
    if not points:raise ValueError('No stitch positions to inspect. Check visibility and embroidery exclusions.')
    result={'points':points,'counts':counts,'options':opts,'ids':ids}
    settings({'densityMap':{**result,'visible':True,'designView':'unchanged','signature':''}},s)
    if download:
        # Preserve original artwork precision/attributes. Only the new ignored
        # annotation layer and its missing definitions come from engine output.
        original=s.xml(source);existing={e.get('id') for e in original.iter() if e.get('id')}
        definitions=ET.SubElement(original,'{'+s.SVG+'}defs')
        for defs in root.findall('{'+s.SVG+'}defs'):
            for child in defs:
                if child.get('id') and child.get('id') not in existing:
                    definitions.append(copy.deepcopy(child));existing.add(child.get('id'))
        if not len(definitions):original.remove(definitions)
        original.append(copy.deepcopy(group));s.command_symbols.hide(original)
        filename='density-map-'+uuid.uuid4().hex+'.svg'
        (s.DATA/'exports'/filename).write_bytes(ET.tostring(original,xml_declaration=True,encoding='UTF-8'))
        result['url']='/files/'+filename
    return result
