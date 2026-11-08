"""Local SVG references and visibility shared by import and path preparation."""
import re
from lxml import etree as ET
SVG='http://www.w3.org/2000/svg';XLINK='http://www.w3.org/1999/xlink';INK='http://www.inkscape.org/namespaces/inkscape'
SHAPES={'path','rect','circle','ellipse','polygon','polyline','line'}
COMMANDS=('starting_point','ending_point','target_point','autoroute_start','autoroute_end','stop','trim','ignore_object','satin_cut_point','ignore_layer','origin','stop_position')
def tag(e):return ET.QName(e).localname
def href(e):return e.get('{'+XLINK+'}href',e.get('href',''))
def command_id(value):return any(value=='inkstitch_'+c or value.startswith('inkstitch_'+c+'-') for c in COMMANDS)
def clone(e):return tag(e)=='use' and not command_id(href(e).lstrip('#'))
def properties(e):return {**{ET.QName(k).localname:v for k,v in e.attrib.items()},**{k.strip():v.strip() for part in e.get('style','').split(';') if ':' in part for k,v in [part.split(':',1)]}}
def visible(e):
    visibility=None
    for n in [e,*e.iterancestors()]:
        p=properties(n)
        if tag(n) in ('defs','clipPath','mask','symbol') or p.get('display')=='none':return False
        if visibility is None and p.get('visibility') not in (None,'inherit'):visibility=p['visibility']
    return visibility not in ('hidden','collapse')
def features(root):
    result={'clones':0,'clips':0,'masks':0}
    for e in root.iter():
        if not visible(e):continue
        p=properties(e)
        result['clones']+=bool(clone(e));result['clips']+=p.get('clip-path','none')!='none';result['masks']+=p.get('mask','none')!='none'
    return result
def normalize_clone_styles(root):
    # Ink/Stitch 3.3.0 merges only inline style when resolving a clone. Put
    # explicit presentation paints in that style without computing inherited
    # defaults, so the SVG source still wins over its use's inherited paint.
    if not any(clone(e) for e in root.iter()):return
    paints={'fill','fill-rule','fill-opacity','stroke','stroke-width','stroke-opacity','stroke-linecap','stroke-linejoin','stroke-miterlimit','stroke-dasharray','stroke-dashoffset','color'}
    for e in root.iter():
        values={k:v for k,v in e.attrib.items() if k in paints}
        values.update({k.strip():v.strip() for part in e.get('style','').split(';') if ':' in part for k,v in [part.split(':',1)]})
        if values:e.set('style',';'.join(k+':'+v for k,v in values.items()))
def has_masks(root):
    ids={e.get('id'):e for e in root.iter() if e.get('id')}
    def nested(node,seen):
        if node is None or id(node) in seen or properties(node).get('display')=='none':return False
        seen=seen|{id(node)}
        if properties(node).get('mask','none')!='none':return True
        if clone(node):return nested(ids.get(href(node).lstrip('#')),seen)
        return any(nested(child,seen) for child in node if tag(child) not in ('defs','mask','clipPath','symbol'))
    return any(visible(e) and (properties(e).get('mask','none')!='none' or clone(e) and nested(ids.get(href(e).lstrip('#')),set())) for e in root.iter())
def require_geometry(root):
    f=features(root)
    if any(f.values()):raise ValueError('Use Digitize → Prepare SVG artwork to unlink clones or bake masks and clipping before editing individual paths.')
def validate_clones(root,ids,max_shapes):
    """Bound expansion and reject cycles before handing local SVG to an engine."""
    memo={}
    def count(node,chain=()):
        key=node.get('id')
        if key in chain or len(chain)>32:raise ValueError('SVG clones cannot contain reference loops or deep chains.')
        if key in memo:return memo[key]
        branch=chain+(key,) if key else chain
        if clone(node):
            target=ids.get(href(node).lstrip('#'))
            if target is None or tag(target) not in SHAPES|{'g','symbol','use'}:raise ValueError('SVG clones must reference local vector shapes, groups or symbols.')
            n=count(target,branch)
        else:n=int(tag(node) in SHAPES)+sum(count(child,branch) for child in node)
        if n>max_shapes:raise ValueError(f'Expanded SVG clones exceed {max_shapes:,} shapes. Import a smaller drawing.')
        if key:memo[key]=n
        return n
    count(root)
