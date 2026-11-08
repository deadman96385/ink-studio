"""Editable color bands using Ink/Stitch's satin parameters and stitch engine.

Band parameter mapping follows Ink/Stitch 3.3's Multicolor Satin tool:
https://inkstitch.org/docs/satin-tools/#multicolor-satin
"""
import copy
import json
import math
import tempfile
from pathlib import Path
import inkex
from lxml import etree as ET
from advanced import layer_mode
from digitizing import path_contours


def settings(data,s):
    if not isinstance(data,dict):raise ValueError('Invalid multicolor satin settings.')
    bands=data.get('bands')
    if not isinstance(bands,list) or not 2<=len(bands)<=8:raise ValueError('Use 2–8 satin colors.')
    result=[]
    for i,b in enumerate(bands):
        if not isinstance(b,dict):raise ValueError('Invalid satin color band.')
        result.append({'color':s.color(b.get('color')),'width':s.number(b.get('width'),0,100,'Solid color width'),
                       'blend':s.number(b.get('blend',0),0,100,'Blend width') if i<len(bands)-1 else 0})
    if abs(sum(b['width']+b['blend'] for b in result)-100)>.02:raise ValueError('Solid widths and blends must total 100%.')
    for i,b in enumerate(result):
        if b['width']+b['blend']+(result[i-1]['blend'] if i else 0)<=0:raise ValueError('Each color needs a solid width or a blend.')
    underlay=data.get('underlayPerColor',False)
    if not isinstance(underlay,bool):raise ValueError('Invalid underlay setting.')
    seed=data.get('seed','ink-studio')
    if not isinstance(seed,str) or not 1<=len(seed)<=80:raise ValueError('Enter a random seed of 1–80 characters.')
    return {'bands':result,'overflowLeft':s.number(data.get('overflowLeft',0),0,100,'Left overflow'),
            'overflowRight':s.number(data.get('overflowRight',0),0,100,'Right overflow'),
            'pullCompensation':s.number(data.get('pullCompensation',0),0,2,'Band pull compensation'),
            'underlayPerColor':underlay,'seed':seed}


def aligned_path(content,s):
    """Bake rail orientation before alternating rail order for color bands.

Use curve samples only to identify rail direction; retain the exact Beziers.
"""
    from shapely.geometry import LineString
    paths=list(inkex.Path(content.get('d')).break_apart())
    curves=path_contours(inkex.Path(content.get('d')))
    if len(paths)!=len(curves) or len(paths)<2:raise ValueError('Convert the stroke to satin rails before adding color bands.')
    lines=[]
    for c in curves:
        if c['closed']:raise ValueError('Open closed satin rails in Edit nodes before adding color bands.')
        points=[]
        for a,b in zip(c['nodes'],c['nodes'][1:]):
            for i in range(41):
                t=i/40;u=1-t
                points.append((u**3*a['x']+3*u*u*t*a['out'][0]+3*u*t*t*b['in'][0]+t**3*b['x'],
                               u**3*a['y']+3*u*u*t*a['out'][1]+3*u*t*t*b['in'][1]+t**3*b['y']))
        lines.append(LineString(points))
    if len(lines)==2:indices=[0,1]
    else:
        counts=[sum(p.intersects(q) for j,q in enumerate(lines) if i!=j) for i,p in enumerate(lines)]
        indices=[i for i,n in enumerate(counts) if (n==1 if len(lines)==3 else n>2) and lines[i].length>.03]
        if len(indices)!=2:indices=sorted(range(len(lines)),key=lambda i:lines[i].length,reverse=True)[:2]
        indices.sort()
    if any(lines[i].length<.01 for i in indices):raise ValueError('Both satin rails need a measurable length.')
    attr=lambda key:content.get('{'+s.STITCH+'}'+key)
    if str(attr('swap_satin_rails')).lower()=='true':indices.reverse()
    first,second=[lines[i] for i in indices];choice=attr('reverse_rails') or 'automatic'
    reverse=[choice in ('first','both'),choice in ('second','both')]
    if choice=='automatic':
        same=sum(first.interpolate(i/10,normalized=True).distance(second.interpolate(i/10,normalized=True)) for i in range(10))
        opposite=sum(first.interpolate(i/10,normalized=True).distance(second.interpolate(1-i/10,normalized=True)) for i in range(10))
        reverse[1]=opposite<same
    for index,turn in zip(indices,reverse):
        if turn:paths[index]=paths[index].reverse()
    return ' '.join(str(paths[i]) for i in indices+[i for i in range(len(paths)) if i not in indices])


def decorate_multisatin(content,layer,s):
    if not layer.get('multicolorSatin'):return content
    # A stale recipe is dormant if the user changes the layer's stitch type.
    if layer_mode(layer)!='satin':return content
    if layer.get('type')!='path' or ET.QName(content).localname!='path':raise ValueError('Separate SVG or lettering paths before adding satin color bands.')
    data=settings(layer['multicolorSatin'],s);d=aligned_path(content,s)
    group=ET.Element('{'+s.SVG+'}g');group.set('{'+s.INK+'}label','Multicolor Satin Group')
    desktop={'equidistance':False,'monochrome_width':data['bands'][0]['width'],
             'overflow_left':data['overflowLeft'],'overflow_right':data['overflowRight'],
             'pull_compensation':data['pullCompensation'],'seed':data['seed'],'adjust_underlay_per_color':data['underlayPerColor'],
             'colors':[{'value':b['color'],'width':b['width'],'margin_right':b['blend']} for b in data['bands']]}
    group.set('{'+s.STITCH+'}satin-multicolor',json.dumps(desktop))
    position=0;previous=data['overflowLeft']
    for i,b in enumerate(data['bands']):
        band=copy.deepcopy(content);band.set('d',d);band.attrib.pop('id',None)
        style=dict(v.split(':',1) for v in band.get('style','').split(';') if ':' in v)
        style.update(fill='none',stroke=b['color']);band.set('style',';'.join(k+':'+v for k,v in style.items()))
        def put(key,value):band.set('{'+s.STITCH+'}'+key,str(value))
        margin=b['blend'] if i<len(data['bands'])-1 else data['overflowRight'];width=b['width'];odd=i%2
        put('reverse_rails','none');put('swap_satin_rails',bool(odd));put('random_seed',data['seed'])
        put('pull_compensation_mm',data['pullCompensation'])
        put('random_width_increase_percent',f'0 {margin}' if odd else f'{margin} 0')
        put('random_width_decrease_percent',f'{-previous} 0' if odd else f'0 {-previous}')
        put('pull_compensation_percent',f'{-position} {position+width-100}' if odd else f'{position+width-100} {-position}')
        put('running_stitch_position',position+width/2 if odd else 100-position-width/2)
        if data['underlayPerColor']:
            put('center_walk_underlay_position',position+width/2 if odd else 100-position-width/2)
            inset=f'{position} {100-position-width}' if odd else f'{100-position-width} {position}'
            for key in ('contour_underlay_inset_percent','zigzag_underlay_inset_percent'):put(key,inset)
        elif i:
            for key in ('center_walk_underlay','contour_underlay','zigzag_underlay'):put(key,False)
        if i<len(data['bands'])-1:put('stop_after',False)
        group.append(band);position+=width+margin;previous=margin
    return group


def layer_preview(data,s):
    layers=data.get('layers')
    if not isinstance(layers,list) or not 1<=len(layers)<=30:raise ValueError('Preview 1–30 layers.')
    raw=s.build_svg({'version':1,'layers':layers})
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='layer-preview-') as tmp:
        path=Path(tmp)/'preview.svg';path.write_bytes(raw)
        x,y,w,h=s.bounds(path)
        if x<-.1 or y<-.1 or x+w>100.1 or y+h>100.1:raise ValueError('Move or resize the artwork to fit inside the 100 mm hoop.')
        pes=Path(tmp)/'preview.pes';pes.write_bytes(s.run([s.ENGINE,'--extension=output','--format=pes','--version=6',str(path)],headless=True))
        preview=s.stitch_data(pes)
        if preview['width']>100 or preview['height']>100:raise ValueError('The generated stitches exceed the 100 mm hoop.')
    return {'preview':preview}
