"""Connected branch recipes with individually editable leaves and petioles.

All coordinates are normalized to the branch frame. Leaf blades have explicit
bases/tips; a join along the cubic stem creates their connecting petiole.
"""
import math
import re
from botanical import cubic,rail_path,satin


def validate(raw,s):
    def xy(value,label):
        if not isinstance(value,list) or len(value)!=2:raise ValueError(label+' needs X and Y.')
        return [s.number(v,-.5,1.5,label) for v in value]
    result={}
    if 'stemCurve' in raw:
        curve=raw['stemCurve']
        if not isinstance(curve,list) or len(curve)!=4:raise ValueError('A branch stem needs four cubic points.')
        result['stemCurve']=[xy(p,'Stem point') for p in curve]
    if 'leafMap' in raw:
        leaves=raw['leafMap']
        if not isinstance(leaves,list) or not 1<=len(leaves)<=12:raise ValueError('Use 1–12 editable leaves per branch.')
        result['leafMap']=[];ids=set()
        for i,leaf in enumerate(leaves):
            if not isinstance(leaf,dict):raise ValueError('Invalid leaf layout.')
            key=leaf.get('id',str(i+1))
            if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,30}',key) or key in ids:raise ValueError('Leaves need unique short identifiers using letters, digits, dashes or underscores.')
            ids.add(key)
            result['leafMap'].append(dict(id=key,name=str(leaf.get('name',f'Leaf {i+1}'))[:60],
                base=xy(leaf.get('base'),'Leaf base'),tip=xy(leaf.get('tip'),'Leaf tip'),
                join=s.number(leaf.get('join',.5),0,1,'Stem junction'),
                width=s.number(leaf.get('width',.15),.015,.8,'Leaf width'),
                bend=s.number(leaf.get('bend',0),-.4,.4,'Leaf curve'),split=bool(leaf.get('split',True))))
    return result


def layout(p):
    curve=p.get('stemCurve') or [[.5,1],[.5+p['bend']*1.3,.66],[.5+p['bend']*1.3,.33],[.5,0]]
    if p.get('leafMap'):return curve,p['leafMap']
    w,h=p['width'],p['height'];physical=[(x*w,y*h) for x,y in curve];leaves=[]
    for i in range(p['pairs']):
        t=.13+i*.63/max(1,p['pairs']-1)
        for side in (-1,1):
            if p.get('leafSide')=='left' and side>0 or p.get('leafSide')=='right' and side<0:continue
            join=t+(.035 if side>0 else 0);x,y=cubic(physical,join)
            tip=(x+side*w*(.46-.10*t),y-h*(.19-.035*t));length=math.dist((x,y),tip)
            leaves.append(dict(id=f'{i+1}-'+('left' if side<0 else 'right'),name=f'Leaf {len(leaves)+1}',
                join=join,base=[x/w,y/h],tip=[tip[0]/w,tip[1]/h],width=min(.8,length*p.get('leafWidth',.36)/w),bend=side*.045,split=True))
    base=cubic(physical,.62)
    leaves.append(dict(id='terminal',name='Terminal leaf',join=.62,base=[base[0]/w,base[1]/h],
        tip=curve[-1],width=min(.25,h*.38*p.get('leafWidth',.36)/w),bend=.03,split=True))
    return curve,leaves


def branch(p,routed_source=False):
    from components import part
    from simple_sewing import is_simple,routed_branch
    simple=is_simple(p)
    if simple and not routed_source:return routed_branch(p)
    w,h=p['width'],p['height'];curve,leaves=layout(p)
    physical=[(x*w,y*h) for x,y in curve];stems=[rail_path(physical)];veins=[];out=[]
    for i,leaf in enumerate(leaves):
        base=(leaf['base'][0]*w,leaf['base'][1]*h);tip=(leaf['tip'][0]*w,leaf['tip'][1]*h)
        dx,dy=tip[0]-base[0],tip[1]-base[1];length=math.hypot(dx,dy)
        if length<.2:raise ValueError(leaf['name']+': move the leaf tip farther from its base.')
        nx,ny=-dy/length,dx/length;bend=leaf['bend']*length
        centre=[base,(base[0]+dx*.25+nx*bend*.8,base[1]+dy*.25+ny*bend*.8),
            (base[0]+dx*.74+nx*bend,base[1]+dy*.74+ny*bend),tip]
        breadth=leaf['width']*w*.67;eps=min(.175/p.get('sewingScale',1),breadth*.35) if simple else min(.025,breadth*.08)
        outer=[]
        for sign in (1,-1):
            outer.append([(point[0]+nx*sign*distance,point[1]+ny*sign*distance)
                for point,distance in zip(centre,[eps,breadth,breadth*.92,eps])])
        key='leaf-'+leaf['id'];name=leaf['name']
        if leaf['split'] and not simple:
            # Each half is a real, independently editable satin column. Small
            # overlap at the midrib prevents a slit between the two colors.
            mid_a=[(x-nx*eps,y-ny*eps) for x,y in centre]
            mid_b=[(x+nx*eps,y+ny*eps) for x,y in centre]
            out.append((key+'-light',satin(outer[0],mid_a,name+' · light half',p['lightColor'],1,.30)))
            out.append((key+'-dark',satin(mid_b,outer[1],name+' · dark half',p['leafColor'],1,.30)))
        else:
            out.append((key,satin(outer[0],outer[1],name,p['leafColor'] if i%2 else p['lightColor'],1,.30)))
        veins.append(rail_path(centre))
        join=cubic(physical,leaf['join'])
        if math.dist(join,base)>.035:
            # An explicit petiole connects every blade to the stem, even when
            # its blade base is offset to form a fan or a fork.
            stems.append(rail_path([join,(join[0]*.65+base[0]*.35,join[1]*.65+base[1]*.35),
                (join[0]*.2+base[0]*.8,join[1]*.2+base[1]*.8),base]))
    if simple:
        for key,layer in out:layer.update(color=p['leafColor'],spacing=.42,satinCenter=False,trimAfter=False)
    stem=part(' '.join(stems),'Branch · connected stem and petioles',p['leafColor'] if simple else p['stemColor'],'running' if simple else 'bean')
    stem.update(stitchLength=2 if simple else 1.2,paintStage=0,trimAfter=False)
    vein=part(' '.join(veins),'Branch · leaf midribs',p['stemColor'],'running')
    vein.update(stitchLength=1,paintStage=2,trimAfter=False)
    return [('stem',stem),*out] if simple else [('stem',stem),*out,('veins',vein)]
