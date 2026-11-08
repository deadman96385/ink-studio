"""Native gradient and tartan settings expressed in Ink/Stitch's SVG format."""
import json
import math
import uuid
from lxml import etree as ET

def gradient_settings(layer,s):
    data=layer.get('gradient') or {'angle':0,'stops':[{'color':layer['color'],'offset':0},{'color':'#e9c878','offset':1}]}
    if not isinstance(data,dict):raise ValueError('Invalid gradient settings.')
    angle=s.number(data.get('angle',0),-360,360,'Gradient angle');stops=data.get('stops')
    if not isinstance(stops,list) or not 2<=len(stops)<=8:raise ValueError('Use 2–8 gradient colors.')
    result=[{'color':s.color(v.get('color')),'offset':s.number(v.get('offset'),0,1,'Gradient stop')} for v in stops]
    if any(a['offset']>=b['offset'] for a,b in zip(result,result[1:])):raise ValueError('Gradient stops must increase from left to right.')
    if result[0]['offset']!=0 or result[-1]['offset']!=1:raise ValueError('The first gradient stop must be 0% and the last 100%.')
    return {'angle':angle,'stops':result}

def tartan_settings(layer,s):
    data=layer.get('tartan') or {'warp':[{'color':layer['color'],'width':5,'render':1},{'color':'#e9c878','width':3,'render':1}]}
    if not isinstance(data,dict):raise ValueError('Invalid tartan settings.')
    def stripes(values):
        if not isinstance(values,list) or not 1<=len(values)<=16:raise ValueError('Use 1–16 stripes per direction.')
        output=[]
        for v in values:
            render=v.get('render',1)
            if type(render)!=int or render not in (0,1,2):raise ValueError('Choose fill, gap, or line for each stripe.')
            output.append({'color':s.color(v.get('color')),'width':s.number(v.get('width'),.2,30,'Stripe width'),'render':render})
        if not any(v['render']==1 for v in output):raise ValueError('Include at least one filled stripe in each direction.')
        return output
    warp=stripes(data.get('warp'));weft=stripes(data['weft']) if data.get('weft') is not None else None
    symmetry=data.get('symmetry',True)
    if not isinstance(symmetry,bool):raise ValueError('Invalid tartan symmetry.')
    def code(values):
        return ' '.join(f'({v["color"]})'+('/' if symmetry and i in (0,len(values)-1) else '')+({0:'?',1:'',2:'*'}[v['render']])+str(v['width']) for i,v in enumerate(values))
    palette=code(warp)+(' | '+code(weft) if weft else '')
    if not symmetry:palette='...'+palette+'...'
    return {'palette':palette,'rotate':s.number(data.get('angle',0),-180,180,'Tartan angle'),
            'offset_x':s.number(data.get('offsetX',0),-100,100,'Horizontal pattern offset'),'offset_y':s.number(data.get('offsetY',0),-100,100,'Vertical pattern offset'),
            'symmetry':symmetry,'scale':s.number(data.get('scale',100),10,500,'Tartan scale'),
            'min_stripe_width':s.number(data.get('minWidth',1),.1,3,'Minimum filled stripe width')}

def decorate_fill(root,content,layer,s):
    if layer.get('stitch')!='fill':return
    method=layer.get('fillMethod');gradient=None;tartan=None
    if method=='linear_gradient_fill':
        settings=gradient_settings(layer,s);angle=math.radians(settings['angle']);x=math.cos(angle)*.5;y=math.sin(angle)*.5
        defs=ET.SubElement(root,'{'+s.SVG+'}defs');key='gradient-'+uuid.uuid4().hex
        gradient=ET.SubElement(defs,'{'+s.SVG+'}linearGradient',id=key,x1=str(.5-x),y1=str(.5-y),x2=str(.5+x),y2=str(.5+y))
        for stop in settings['stops']:ET.SubElement(gradient,'{'+s.SVG+'}stop',offset=str(stop['offset']),style='stop-color:'+stop['color']+';stop-opacity:1')
    elif method=='tartan_fill':tartan=tartan_settings(layer,s)
    else:return
    for e in content.iter():
        if ET.QName(e).localname not in ('path','rect','circle','ellipse','polygon','polyline'):continue
        style=dict(part.split(':',1) for part in e.get('style','').split(';') if ':' in part)
        if style.get('fill')=='none':continue
        if gradient is not None:style['fill']='url(#'+gradient.get('id')+')';e.set('style',';'.join(k+':'+v for k,v in style.items()))
        if tartan is not None:e.set('{'+s.STITCH+'}tartan',json.dumps(tartan))
