"""Adapters around the installed maintenance extensions; preserve native attachments."""
import copy
import io
import re
import uuid
import inkex
from lxml import etree as ET
from digitizing import SVG,STITCH,geometry

INK='http://www.inkscape.org/namespaces/inkscape'
ROLES=('guide-line','anchor-line','pattern')

def validate_helpers(helpers,layers):
    if not isinstance(helpers,list) or len(helpers)>180:raise ValueError('Invalid attached helpers.')
    targets={l['id'] for l in layers}
    if any(not isinstance(h,dict) or h.get('role') not in ROLES or h.get('helperTarget') not in targets for h in helpers):raise ValueError('Choose helpers attached to the selected artwork.')
    if any(h.get('locked') for h in helpers):raise ValueError('Unlock attached guides and patterns before converting their artwork.')
    return copy.deepcopy(helpers)

def source_id(e,layers):
    for a in e.iterancestors():
        m=re.fullmatch(r'layer-(\d+)',a.get('id',''))
        if m and int(m[1])<len(layers):return layers[int(m[1])]['id']

class Maintenance:
    def __init__(self,key,params,source,layers,s):
        self.key=key;self.params=copy.deepcopy(params);self.original={};self.parts={};self.trims={}
        doc=inkex.load_svg(io.BytesIO(source)).getroot()
        ids=[e.get('id') for e,_,_ in geometry(source) if not e.get('{'+INK+'}connection-start')]
        nodes=[doc.getElementById(id) for id in ids]
        if not nodes:raise ValueError('No stitched paths were selected.')
        self.original={n.get('id'):{k:v for k,v in n.attrib.items() if k.startswith('{'+STITCH+'}')} for n in nodes}
        if key=='duplicate_params':
            chosen=self.params.pop('source_id')
            sources=[n for n in nodes if source_id(n,layers)==chosen]
            if len(sources)!=1:raise ValueError('Choose a source containing exactly one path. Separate lettering or SVG first.')
            if len(nodes)<2:raise ValueError('Select a source and at least one target path.')
            ids=[sources[0].get('id')]+[id for id in ids if id!=sources[0].get('id')]
        elif key=='apply_attribute':
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,79}',params['key']):raise ValueError('Use an Ink/Stitch parameter name without a namespace or spaces.')
            if not params['remove'] and not params['value'].strip():raise ValueError('Enter a value for the parameter.')
            self.params['namespace']='inkstitch'
            # The engine's remove operation expects the attribute to exist.
            if params['remove']:
                for n in nodes:
                    if n.get('{'+STITCH+'}'+params['key']) is None:n.set('{'+STITCH+'}'+params['key'],'')
        elif key=='remove_duplicated_points':
            # Engine compares physical SVG pixels, whereas our form uses mm.
            self.params['distance']=params['distance']/s.PX_MM
            ids=[]
            for n in nodes:
                if str(n.specified_style().get('fill','black'))!='none' or str(n.get('{'+STITCH+'}satin_column','')).lower()=='true':raise ValueError('Repeated-point cleanup needs running, bean or manual paths. Separate filled or satin artwork first.')
                path=inkex.PathElement();path.attrib.update(n.attrib);path.set('d',str(n.path))
                n.getparent().replace(n,path);chunks=[]
                for command in path.path.to_absolute():
                    if command.letter=='M':chunks.append([])
                    if chunks:chunks[-1].append(command)
                if not chunks:raise ValueError('The selected path is empty.')
                parts=[]
                for i,chunk in enumerate(chunks):
                    part=path if i==0 else copy.deepcopy(path)
                    part_id=path.get('id') if i==0 else 'clean-part-'+uuid.uuid4().hex
                    part.set('id',part_id);part.set('d',str(inkex.Path(chunk)))
                    if i: path.addnext(part)
                    ids.append(part_id);parts.append((part_id,chunk[-1].letter=='Z'))
                self.parts[path.get('id')]=parts
        elif key=='jump_to_trim':
            if params['maximum-jump-length'] and params['maximum-jump-length']<params['minimum-jump-length']:raise ValueError('Maximum jump length must be zero or at least the minimum.')
            if params['command']=='stop':
                # Ink/Stitch 3.3 skips a requested stop when trim_after is true.
                # Temporarily mask that flag, retaining it in the final result.
                for n in nodes:
                    value=n.get('{'+STITCH+'}trim_after')
                    if value is not None:self.trims[n.get('id')]=value;n.set('{'+STITCH+'}trim_after','False')
        self.ids=ids;self.source=ET.tostring(doc)

    def finish(self,raw):
        doc=inkex.load_svg(io.BytesIO(raw)).getroot()
        if doc.xpath('//*[local-name()="use"][@*[local-name()="href" and (starts-with(.,"#inkstitch_ignore_object") or starts-with(.,"#inkstitch_ignore_layer"))]]'):
            raise ValueError('This SVG contains ignore-object or ignore-layer commands. Remove those commands first, or separate the artwork before changing its settings.')
        for owner,parts in self.parts.items():
            first=doc.getElementById(owner);paths=[]
            if first is None:raise ValueError('The cleanup did not retain its source path.')
            for id,closed in parts:
                part=doc.getElementById(id)
                if part is None:raise ValueError('The cleanup did not retain every subpath.')
                d=part.get('d','')
                if closed and not d.rstrip().lower().endswith('z'):d+=' Z'
                paths.append(d)
                if id!=owner:part.delete()
            first.set('d',' '.join(paths))
        if self.key=='remove_embroidery_settings':
            param=self.params['del_params'];command=self.params['del_commands']
            for id,original in self.original.items():
                n=doc.getElementById(id)
                if n is None:continue
                # Correct suffix matching and the all-commands trim/stop elif
                # in the installed extension, without changing other settings.
                for k,v in original.items():
                    name=ET.QName(k).localname
                    if param not in ('all',name):n.set(k,v)
                    else:n.attrib.pop(k,None)
                for name in ('trim','stop'):
                    if command in ('all',name):n.attrib.pop('{'+STITCH+'}'+name+'_after',None)
        for id,value in self.trims.items():
            n=doc.getElementById(id)
            if n is not None:n.set('{'+STITCH+'}trim_after',value)
        return ET.tostring(doc)

def preserve_identity(result,layers,helpers):
    by_source={l['id']:[] for l in layers};remap={}
    for l in result:
        source=l.pop('_sourceId',None)
        if source in by_source:by_source[source].append(l)
        elif l.get('role','artwork')=='artwork':raise ValueError('The engine changed the source grouping. Separate SVG paths before using this tool.')
    for source in layers:
        outputs=by_source[source['id']]
        for i,l in enumerate(outputs):
            l['name']=source.get('name','Path')+(f' · {i+1}' if len(outputs)>1 else '')
            l['background']=bool(source.get('background',False))
            if source.get('groupId'):l['groupId']=source['groupId']
            if len(outputs)==1:
                remap[l['id']]=source['id'];l['id']=source['id']
    for l in result:
        if l.get('helperTarget') in remap:l['helperTarget']=remap[l['helperTarget']]
    # Visible attachments were reconstructed from the engine SVG. Hidden ones
    # cannot enter that SVG, so retain their native geometry explicitly.
    for h in helpers:
        if h.get('visible',True):continue
        for i,target in enumerate(by_source.get(h['helperTarget'],[])):
            copied=copy.deepcopy(h);copied.pop('linkedHelper',None)
            copied.update(id=h['id'] if i==0 else uuid.uuid4().hex,helperTarget=target['id'])
            result.append(copied)
    return result,{source:[l['id'] for l in outputs] for source,outputs in by_source.items()}
