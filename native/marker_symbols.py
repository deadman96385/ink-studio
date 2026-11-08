"""Installed helper-marker artwork and presentation, separate from stitches."""
import studio_runtime
import copy,math,re
from functools import lru_cache
from pathlib import Path
from lxml import etree as ET
from command_symbols import SVG,style
ROLES=('guide-line','anchor-line','pattern')

def settings(project):
    raw=project.get('markerDisplay',{})
    if not isinstance(raw,dict) or set(raw)-{'visible','size'}:raise ValueError('Invalid marker display settings.')
    result={'visible':False,'size':100,**raw}
    if type(result['visible']) is not bool or type(result['size']) not in (int,float) or not math.isfinite(result['size']) or not 0<=result['size']<=400:raise ValueError('Marker size must be from 0 to 400 percent.')
    return result

def helper_role(node):
    value=node.get('marker-start','')
    for item in node.get('style','').split(';'):
        if ':' in item:
            key,v=item.split(':',1)
            if key.strip()=='marker-start':value=v.strip()
    match=re.fullmatch(r'url\(\s*[\'"]?#inkstitch-(guide-line|anchor-line|pattern)-marker(?:-[\w.:-]+)?[\'"]?\s*\)',value)
    return match[1] if match else None

def hide(root):
    for e in root.iter():
        if helper_role(e):style(e,'display','none')

@lru_cache(maxsize=1)
def artwork():
    root=ET.parse(str(studio_runtime.resource('symbols','marker.svg'))).getroot()
    return ET.tostring(root.find('{'+SVG+'}defs'))

def present(root,project):
    config=settings(project)
    if 'markerDisplay' not in project:return
    installed=ET.fromstring(artwork())
    for marker in root.iter('{'+SVG+'}marker'):
        id=marker.get('id','')
        if not id.startswith('inkstitch'):continue
        if not len(marker):
            source=next((m for m in installed if id==m.get('id') or id.startswith(m.get('id')+'-')),None)
            if source is not None:
                marker.attrib.clear();marker.attrib.update(source.attrib);marker.set('id',id)
                for child in source:
                    child=copy.deepcopy(child)
                    for e in child.iter():e.attrib.pop('id',None)
                    marker.append(child)
        # This is the installed Scale Command Symbols extension's marker rule.
        marker.set('markerWidth',str(.125*config['size']/100 if config['visible'] else 0))
    if config['visible']:
        for e in root.iter():
            if helper_role(e):style(e,'display',None)
