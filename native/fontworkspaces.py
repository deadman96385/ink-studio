"""Editable font sources with immutable revisions and native glyph projects."""
import base64
import copy
import preferences
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unicodedata
import uuid
import zipfile
import inkex
from lxml import etree as ET
import fontlibrary as fl

LOCK=threading.RLock()


def locations(s):
    base=s.DATA/'font-workspaces'
    for name in ('drafts','revisions','blobs'):(base/name).mkdir(parents=True,exist_ok=True)
    return base


def put_blob(raw,s):
    key=hashlib.sha256(raw).hexdigest();path=locations(s)/'blobs'/key
    if not path.exists():
        stage=path.with_suffix('.'+uuid.uuid4().hex+'.tmp');stage.write_bytes(raw);stage.replace(path)
    return key


def read_blob(key,s):return (locations(s)/'blobs'/s.safe_id(key)).read_bytes()


def load(key,s,revision=None):
    base=locations(s);draft=json.loads((base/'drafts'/(s.safe_id(key)+'.json')).read_text())
    target=revision or draft['revision']
    if target not in [r['id'] for r in draft['history']]:raise ValueError('Choose a revision from this font workspace.')
    value=json.loads((base/'revisions'/(s.safe_id(target)+'.json')).read_text())
    return draft,value


def commit(draft,value,label,s,expected=None):
    with LOCK:
        path=locations(s)/'drafts'/(draft['id']+'.json')
        current=json.loads(path.read_text()) if path.exists() else draft
        if expected is not None and current.get('revision')!=expected:raise ValueError('This font workspace changed. Reload it before saving, or keep the glyph as a project and reopen the workspace.')
        revision=uuid.uuid4().hex;now=time.time()
        s.write_atomic(locations(s)/'revisions'/(revision+'.json'),value)
        result={**current,'name':value['metadata']['name'],'revision':revision,'updated':now,
                'history':current.get('history',[])+[{'id':revision,'label':label,'created':now}]}
        s.write_atomic(path,result)
        return result


def read_doc(key,s):
    return inkex.load_svg(io.BytesIO(read_blob(key,s))).getroot()


def glyph_nodes(doc,s):
    return [g for g in doc.iter('{'+s.SVG+'}g') if g.get('{'+s.INK+'}label','').startswith('GlyphLayer-')]


def glyph_name(g,s):return unicodedata.normalize('NFC',g.get('{'+s.INK+'}label','')[11:])


def valid_name(value):
    if not isinstance(value,str):raise ValueError('Enter a character, ligature or alternate glyph name.')
    name=unicodedata.normalize('NFC',str(value))
    if not 1<=len(name)<=32 or not name.strip() or any(unicodedata.category(c) in ('Cc','Cs') for c in name):raise ValueError('Enter a character, ligature or alternate glyph name, up to 32 characters.')
    return name


def variant_name(value):
    if value not in fl.VARIANTS:raise ValueError('Choose left-to-right, right-to-left, top-to-bottom or bottom-to-top stitches.')
    return value


def inventory(value,s):
    items=[]
    for file,key in value['files'].items():
        if not file.endswith('.svg'):continue
        variant=file.split('/')[0].removesuffix('.svg');doc=read_doc(key,s)
        for index,g in enumerate(glyph_nodes(doc,s)):
            name=glyph_name(g,s);paths=[p for p in g.iter('{'+s.SVG+'}path') if p.get('d','').strip()]
            items.append({'name':name,'variant':variant,'file':file,'glyphIndex':index,'locked':g.get('{'+fl.SODI+'}insensitive') is not None,
                          'paths':len(paths),'category':unicodedata.category(name[0]) if name else '',
                          'group':g.getparent().get('{'+s.INK+'}label','') if g.getparent() is not None else ''})
    return items


def summary(draft,value,s):
    items=inventory(value,s);seen=set();duplicates=[]
    for g in items:
        pair=(g['variant'],g['name'])
        if pair in seen:duplicates.append({'variant':pair[0],'name':pair[1]})
        seen.add(pair)
    return {**draft,'sourceFont':value.get('sourceFont'),'installedFont':value.get('installedFont'),'metadata':value['metadata'],
            'glyphs':items,'variants':sorted({g['variant'] for g in items}),'duplicates':duplicates}


def detail(key,s):
    draft,value=load(key,s);return summary(draft,value,s)


def listing(s):
    result=[]
    for path in (locations(s)/'drafts').glob('*.json'):
        draft=json.loads(path.read_text());result.append({k:draft[k] for k in ('id','name','revision','updated')})
    return sorted(result,key=lambda d:d['updated'],reverse=True)


def create(data,s):
    source=data.get('font');font=fl.get_font(source,s) if source else None
    if font and font.get('_internal'):raise ValueError('Choose a font from the library.')
    if data.get('content'):meta,files=fl.decode_package(data,s)
    elif font:meta=fl.metadata(font);files=fl.files_for(font,s)
    else:
        meta={'name':data.get('name','My embroidery font'),'size':15,'leading':20/s.PX_MM,'horiz_adv_x_space':5/s.PX_MM,
              'min_scale':1,'max_scale':1,'auto_satin':False,'reversible':False,'sortable':False,'default_variant':'ltr'};files={}
    meta['name']=str(data.get('name') or (font['name']+' · working copy' if font else meta['name']))[:120]
    meta=fl.validate_metadata(meta,s);refs={}
    for name,raw in files.items():
        if name.endswith('.svg'):raw,_=fl.clean_svg(raw,s)
        refs[name]=put_blob(raw,s)
    value={'metadata':meta,'files':refs,'sourceFont':source};draft={'id':uuid.uuid4().hex,'history':[]}
    draft=commit(draft,value,'Created working copy' if font else 'Created new font',s)
    return summary(draft,value,s)


def find_glyph(value,variant,name,s,source=None):
    matches=[]
    if source is not None and (not isinstance(source,dict) or not isinstance(source.get('file'),str) or type(source.get('glyphIndex')) is not int):raise ValueError('Choose a source glyph from the current workspace.')
    for file,key in value['files'].items():
        if file.split('/')[0].removesuffix('.svg')!=variant or not file.endswith('.svg'):continue
        if source is not None and source['file']!=file:continue
        doc=read_doc(key,s)
        for index,g in enumerate(glyph_nodes(doc,s)):
            if glyph_name(g,s)==name and (source is None or source['glyphIndex']==index):matches.append((file,doc,g))
    if len(matches)>1:raise ValueError('This direction contains duplicate glyph names. Rename or remove the duplicates before editing this glyph.')
    return matches[0] if matches else None


def definitions(doc,group,s):
    """Only copy resources used by this glyph, not unrelated SVG-font tables."""
    result=ET.Element('{'+s.SVG+'}defs');ids={e.get('id'):e for e in doc.iter() if e.get('id')};present={e.get('id') for e in group.iter() if e.get('id')};pending=[]
    def refs(node):
        for e in node.iter():
            for attr,value in e.attrib.items():
                if ET.QName(attr).localname in ('href','connection-start','connection-end') and value.startswith('#'):pending.append(value[1:])
                pending.extend(re.findall(r'url\([\s\'"]*#([\w.:-]+)',value))
    refs(group)
    while pending:
        key=pending.pop()
        if key in present:continue
        e=ids.get(key)
        if e is None:raise ValueError('The glyph refers to a missing SVG resource.')
        result.append(copy.deepcopy(e));present.update(n.get('id') for n in e.iter() if n.get('id'));refs(e)
    return result


def glyph_project(data,s):
    draft,value=load(data.get('id'),s);variant=variant_name(data.get('variant','ltr'));name=valid_name(data.get('glyph','A'))
    found=find_glyph(value,variant,name,s);layers=[];assets=[];origin=20;baseline=65;advance=value['metadata'].get('horiz_adv_x',{}).get(name)
    document_preferences=(preferences.imported(found[1]) or preferences.validate(None)) if found else preferences.new_document(s)
    guides={'baseline':baseline};bearing=0
    if found and not any((e.tag=='{'+s.SVG+'}path' and e.get('d','').strip() and not e.get('{'+s.INK+'}connection-end')) or ET.QName(e).localname in ('rect','ellipse','circle','line','polygon','polyline') for e in found[2].iter()):
        # Organization stages intentionally create empty glyph placeholders.
        # They must open as a blank, guided canvas ready for digitizing.
        doc=found[1];source_guides={g.label:inkex.units.convert_unit(doc.get_page_bbox().y.size-g.raw_position.y,'px',doc.unit) for g in doc.namedview.get_guides()}
        source_baseline=source_guides.get('baseline',0)
        guides.update({k:baseline+(y-source_baseline)*s.PX_MM for k,y in source_guides.items() if k in ('baseline','ascender','caps','xheight','descender','decender')})
        if advance is None:advance=value['metadata'].get('horiz_adv_x_default')
        context={'workspace':draft['id'],'revision':draft['revision'],'glyph':name,'variant':variant,'originX':origin,'baselineY':baseline,'advance':(advance if advance is not None else 18/s.PX_MM)*s.PX_MM,'guides':guides,'locked':found[2].get('{'+fl.SODI+'}insensitive') is not None}
        return {'project':dict(version=1,id=uuid.uuid4().hex,name=f'{value["metadata"]["name"]} · {name} ({variant})',fabric='#faf7f0',grid=True,snap=False,layers=[],fontGlyph=context,embroiderySettings=document_preferences),'assets':[]}
    if found:
        file,doc,g=found
        # Font sources are rendered in px after the SVG viewport transform.
        # Keep the original left bearing and baseline in physical millimeters.
        baseline_px=0
        def guide_pixels(guide):
            return inkex.units.convert_unit(doc.get_page_bbox().y.size-guide.raw_position.y,'px',doc.unit)
        for guide in doc.namedview.get_guides():
            if guide.label=='baseline':baseline_px=guide_pixels(guide)
        root=s.svg_root();defs=definitions(doc,g,s)
        if len(defs):root.append(defs)
        factor=float(doc.scale)*s.PX_MM
        outer=ET.SubElement(root,'{'+s.SVG+'}g',transform=f'translate({origin},{baseline-baseline_px*s.PX_MM}) scale({factor})')
        # Preserve inherited appearance and transforms before detaching.
        copy_g=copy.deepcopy(g);copy_g.set('transform',str(g.composed_transform()))
        style=g.specified_style();style.pop('display',None);style.pop('visibility',None);copy_g.set('style',str(style));copy_g.attrib.pop('display',None)
        copy_g.attrib.pop('{'+fl.SODI+'}insensitive',None);outer.append(copy_g)
        for item in copy_g.iter('{'+s.SVG+'}path'):
            if item.get('id') and not item.get('{'+s.STITCH+'}random_seed'):item.set('{'+s.STITCH+'}random_seed',item.get('id'))
        with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='glyph-edit-') as tmp:
            p=Path(tmp)/'glyph.svg';p.write_bytes(ET.tostring(root));x,y,w,h=s.bounds(p)
        if w>96 or h>96:raise ValueError('This glyph exceeds the 100 mm editor at its source size. Use a smaller font source.')
        # Keep source scale. Move only the workspace guides if it would fall
        # outside the hoop; the saved glyph stays at its original baseline.
        dx=max(0,2-x)-max(0,x+w-98);dy=max(0,2-y)-max(0,y+h-98)
        origin+=dx;baseline+=dy;x+=dx;y+=dy
        outer.set('transform',f'translate({origin},{baseline-baseline_px*s.PX_MM}) scale({factor})')
        group=ET.Element('{'+s.SVG+'}g',nsmap=s.NS,transform=f'translate({-x},{-y})')
        for child in root:group.append(copy.deepcopy(child))
        raw=ET.tostring(group,encoding='unicode');key=hashlib.sha256(raw.encode()).hexdigest()
        asset={'key':key,'svg':raw,'width':max(.2,w),'height':max(.2,h),'name':name+' · source glyph'}
        # Source-only typography tables were pruned above. The remaining SVG
        # must be safe to render and restore as ordinary editable artwork.
        check=s.svg_root();check.append(copy.deepcopy(group));s.sanitize_svg(ET.tostring(check),max_shapes=20000)
        s.write_atomic(s.DATA/'assets'/(key+'.json'),asset);assets.append(asset)
        layers=[dict(id=uuid.uuid4().hex,name=name+' · glyph paths',type='import',asset=key,x=x,y=y,width=asset['width'],height=asset['height'],rotation=0,color='#305c50',stitch='original',recolor=False,visible=True)]
        bearing=x-origin
        for guide in doc.namedview.get_guides():
            if guide.label in ('baseline','ascender','caps','xheight','descender','decender'):guides[guide.label]=baseline+(guide_pixels(guide)-baseline_px)*s.PX_MM
        if advance is None:advance=value['metadata'].get('horiz_adv_x_default')
        if advance is None:
            boxes=[p.path.transform(p.composed_transform()).bounding_box() for p in g.iter('{'+s.SVG+'}path') if p.get('d') and not p.get('{'+s.INK+'}connection-end')]
            advance=max(float(box.right) for box in boxes)*float(doc.scale) if boxes else (bearing+w)/s.PX_MM
    if advance is None:advance=18/s.PX_MM
    guides['baseline']=baseline
    context={'workspace':draft['id'],'revision':draft['revision'],'glyph':name,'variant':variant,'originX':origin,'baselineY':baseline,
             'advance':advance*s.PX_MM,'guides':guides,'locked':bool(found and found[2].get('{'+fl.SODI+'}insensitive') is not None)}
    return {'project':dict(version=1,id=uuid.uuid4().hex,name=f'{value["metadata"]["name"]} · {name} ({variant})',fabric='#faf7f0',grid=True,snap=False,layers=layers,fontGlyph=context,embroiderySettings=document_preferences),'assets':assets}


def source_document(project,name,s):
    context=project.get('fontGlyph',{});origin=s.number(context.get('originX'),-100,200,'Glyph origin');baseline=s.number(context.get('baselineY'),-100,200,'Baseline')
    raw=s.build_svg(project);art=s.xml(raw);root=s.svg_root();root.set('viewBox',f'0 0 {100/s.PX_MM} {100/s.PX_MM}')
    nv=ET.SubElement(root,'{'+fl.SODI+'}namedview')
    ET.SubElement(nv,'{'+fl.SODI+'}guide',position=f'0,{100/s.PX_MM}',orientation='0,1',attrib={'{'+s.INK+'}label':'baseline'})
    for label,y in (context.get('guides') or {}).items():
        if label not in ('ascender','caps','xheight','descender','decender'):continue
        y=s.number(y,-1000,1000,'Font height guide')
        ET.SubElement(nv,'{'+fl.SODI+'}guide',position=f'0,{(100+baseline-y)/s.PX_MM}',orientation='0,1',attrib={'{'+s.INK+'}label':label})
    g=ET.SubElement(root,'{'+s.SVG+'}g',id='glyph-source',attrib={'{'+s.INK+'}label':'GlyphLayer-'+name,'{'+s.INK+'}groupmode':'layer'})
    if context.get('locked'):g.set('{'+fl.SODI+'}insensitive','true')
    wrap=ET.SubElement(g,'{'+s.SVG+'}g',transform=f'scale({1/s.PX_MM}) translate({-origin},{-baseline})')
    for child in art:
        if child.tag=='{'+s.SVG+'}metadata':
            old=root.find('{'+s.SVG+'}metadata')
            if old is not None:root.remove(old)
            root.insert(0,copy.deepcopy(child))
        elif child.tag in ('{'+s.SVG+'}g','{'+s.SVG+'}defs'):wrap.append(copy.deepcopy(child))
    used=set()
    for i,node in enumerate(root.iter()):
        for attr in ('lettering','letter-group'):node.attrib.pop('{'+s.STITCH+'}'+attr,None)
        if node is not g:
            node.attrib.pop('{'+s.INK+'}groupmode',None)
            if node.get('{'+s.INK+'}label','').startswith('GlyphLayer-'):node.set('{'+s.INK+'}label','Glyph artwork')
        if not node.get('id'):node.set('id',f'glyph-item-{i}')
        used.add(node.get('id'))
    root=canonical_paths(root,s)
    used=set()
    for node in root.iter():
        if not node.get('id') or node.get('id') in used:node.set('id','glyph-resource-'+uuid.uuid4().hex)
        used.add(node.get('id'))
    clean,_=fl.clean_svg(ET.tostring(root),s);return clean


def canonical_paths(root,s):
    """Store real px geometry, including stroke widths and local resources.

    Ink/Stitch's font loader flattens source transforms but doesn't multiply
    stroke widths. Saving millimeter artwork under a scale alone would shrink
    zigzag glyphs. Resolve the transforms while the full SVG tree is attached.
    """
    doc=inkex.load_svg(io.BytesIO(ET.tostring(root))).getroot()
    # Resources use the referencing object's coordinates, not the transforms
    # of artwork groups that happen to contain a nested defs element.
    definitions=list(doc.iter('{'+s.SVG+'}defs'));defs=inkex.Defs();doc.insert(0,defs)
    for old in definitions:
        for child in list(old):defs.append(child)
        old.getparent().remove(old)
    # Imported SVGs can put descriptions and metadata inside a glyph. The
    # font loader assumes every descendant there has a shape's clip property.
    # Retain these annotations at document level, outside the stitched groups.
    for group in glyph_nodes(doc,s):
        for annotation in list(group.iterdescendants()):
            if annotation.tag in ('{'+s.SVG+'}title','{'+s.SVG+'}desc','{'+s.SVG+'}metadata'):
                doc.append(annotation)
    nodes=[e for e in doc.iter() if not any(a.tag in ('{'+s.SVG+'}defs','{'+s.SVG+'}symbol') for a in e.iterancestors())]
    for e in nodes:
        clip=e.clip if isinstance(e,inkex.ShapeElement) else None
        if clip is not None:
            if clip.get('clipPathUnits','userSpaceOnUse')!='userSpaceOnUse':raise ValueError('Convert bounding-box clipping to a user-space clip before saving this glyph.')
            clone=copy.deepcopy(clip);clone.set('id','glyph-clip-'+uuid.uuid4().hex);matrix=e.composed_transform()
            original_paths=[n for n in clip.iterdescendants() if ET.QName(n).localname in ('path','rect','ellipse','circle','line','polyline','polygon')]
            del clone[:]
            for p in original_paths:
                c=inkex.PathElement();c.path=p.path.transform(matrix @ p.composed_transform());c.style=p.specified_style();clone.append(c)
            clone.attrib.pop('transform',None);defs.append(clone);e.clip=clone
    for e in nodes:
        local=ET.QName(e).localname
        if local=='use':
            x,y=e.composed_transform().apply_to_point((float(e.get('x',0)),float(e.get('y',0))));e.set('x',str(x));e.set('y',str(y));e.attrib.pop('transform',None)
        elif isinstance(e,inkex.ShapeElement) and local in ('path','rect','ellipse','circle','line','polyline','polygon'):
            matrix=e.composed_transform();style=e.specified_style();box=e.path.bounding_box()
            if str(style.get('stroke','none'))!='none':
                width=inkex.units.convert_unit(str(style.get('stroke-width',1)),'px')
                style['stroke-width']=width*s.stroke_scale(e)
            for paint in ('fill','stroke'):
                match=re.fullmatch(r'url\(#([\w.:-]+)\)',str(style.get(paint,'')))
                gradient=doc.getElementById(match[1]) if match else None
                if gradient is None or gradient.tag!='{'+s.SVG+'}linearGradient':continue
                raise ValueError('Convert gradient fills to editable color blocks in Digitize → Embroidery tools before saving this glyph. The font loader cannot retain gradient paint definitions.')
            # The font engine normalizes inline fill:none strokes to 1 px
            # for displaying satin rails. Zigzag width is sewing geometry,
            # so retain fill:none as an equivalent presentation attribute.
            if e.get('{'+s.STITCH+'}stroke_method')=='zigzag_stitch' and str(style.get('fill'))=='none':
                style.pop('fill',None);e.set('fill','none')
            path=e.path.transform(matrix)
            e.tag='{'+s.SVG+'}path';e.set('d',str(path));e.set('style',str(style));e.attrib.pop('transform',None)
    for e in nodes:
        if e.tag=='{'+s.SVG+'}g':e.attrib.pop('transform',None)
    return doc


def remove_glyph(value,variant,name,s):
    for file,key in list(value['files'].items()):
        if not file.endswith('.svg') or file.split('/')[0].removesuffix('.svg')!=variant:continue
        doc=read_doc(key,s);found=[g for g in glyph_nodes(doc,s) if glyph_name(g,s)==name]
        for g in found:g.getparent().remove(g)
        if found:
            if glyph_nodes(doc,s):value['files'][file]=put_blob(ET.tostring(doc),s)
            else:del value['files'][file]


def remove_selected(value,file,doc,g,s):
    g.getparent().remove(g)
    if glyph_nodes(doc,s):value['files'][file]=put_blob(ET.tostring(doc),s)
    else:value['files'].pop(file,None)


def save_glyph(data,s):
    project=data.get('project')
    if not isinstance(project,dict) or not isinstance(project.get('fontGlyph'),dict):raise ValueError('Open or assign a glyph workspace first.')
    context=project['fontGlyph'];draft,value=load(context.get('workspace'),s);name=valid_name(context.get('glyph'));variant=variant_name(context.get('variant'))
    find_glyph(value,variant,name,s)  # Never replace several ambiguous source glyphs.
    raw=source_document(project,name,s);advance=s.number(context.get('advance'),0,500,'Glyph advance')/s.PX_MM
    remove_glyph(value,variant,name,s)
    file=variant+'/studio-'+hashlib.sha256(name.encode()).hexdigest()[:20]+'.svg';value['files'][file]=put_blob(raw,s)
    value['metadata'].setdefault('horiz_adv_x',{})[name]=advance
    draft=commit(draft,value,f'Saved {name} ({variant})',s,context.get('revision'))
    return {'workspace':summary(draft,value,s),'context':{**context,'revision':draft['revision']}}


def update(data,s):
    draft,value=load(data.get('id'),s);action=data.get('action');expected=data.get('revision')
    if expected!=draft['revision']:raise ValueError('The font workspace changed. Reload it before applying this change.')
    if action=='metadata':
        changes=data.get('metadata')
        if not isinstance(changes,dict):raise ValueError('Enter the font settings.')
        value['metadata']=fl.validate_metadata({**value['metadata'],**changes},s);label='Updated font settings'
    elif action=='restore':
        _,value=load(draft['id'],s,data.get('restoreRevision'));label='Restored earlier revision'
    elif action in ('rename','copy','remove','lock'):
        variant=variant_name(data.get('variant'));name=valid_name(data.get('glyph'));found=find_glyph(value,variant,name,s,data.get('source'))
        if not found:raise ValueError('Choose a glyph in this workspace.')
        file,doc,g=found
        if action=='remove':remove_selected(value,file,doc,g,s)
        elif action=='lock':
            if type(data.get('locked')) is not bool:raise ValueError('Choose whether to lock this glyph.')
            g.set('{'+fl.SODI+'}insensitive','true') if data['locked'] else g.attrib.pop('{'+fl.SODI+'}insensitive',None)
            value['files'][file]=put_blob(ET.tostring(doc),s)
        else:
            target=valid_name(data.get('name'));target_variant=variant_name(data.get('targetVariant',variant))
            if find_glyph(value,target_variant,target,s):raise ValueError('That glyph already exists in the destination direction.')
            if action=='rename' and variant==target_variant:
                g.set('{'+s.INK+'}label','GlyphLayer-'+target);value['files'][file]=put_blob(ET.tostring(doc),s)
            else:
                # Keep its original viewport, guides, resources and ancestors.
                original_doc=copy.deepcopy(doc);original_index=glyph_nodes(doc,s).index(g)
                for other in list(glyph_nodes(doc,s)):
                    if other is not g:other.getparent().remove(other)
                g.set('{'+s.INK+'}label','GlyphLayer-'+target)
                destination=target_variant+'/copy-'+uuid.uuid4().hex+'.svg';value['files'][destination]=put_blob(ET.tostring(doc),s)
                if action=='rename':remove_selected(value,file,original_doc,glyph_nodes(original_doc,s)[original_index],s)
            advances=value['metadata'].setdefault('horiz_adv_x',{})
            if name in advances:advances[target]=advances[name]
        label=action.title()+' '+name
    elif action=='copy-variant':
        source=variant_name(data.get('variant'));target=variant_name(data.get('targetVariant'))
        if any(file.startswith(target+'/') or file==target+'.svg' for file in value['files']):raise ValueError('That stitch direction already exists.')
        files={file:key for file,key in value['files'].items() if file==source+'.svg' or file.startswith(source+'/')}
        if not files:raise ValueError('Choose an existing source direction.')
        value['files'].update({target+file[len(source):]:key for file,key in files.items()});label=f'Copied {source} to {target}'
    else:raise ValueError('Choose a font workspace action.')
    draft=commit(draft,value,label,s,expected);return summary(draft,value,s)


def publish(data,s):
    with LOCK:return _publish(data,s)


def _publish(data,s):
    draft,value=load(data.get('id'),s)
    if data.get('revision')!=draft['revision']:raise ValueError('Reload the current font workspace before installing it.')
    if summary(draft,value,s)['duplicates']:raise ValueError('Resolve duplicate glyph names before installing this font.')
    files={name:read_blob(key,s) for name,key in value['files'].items()}
    if not any(name.endswith('.svg') for name in files):raise ValueError('Save at least one digitized glyph first.')
    font=fl.install(value['metadata'],files,s)
    fl.set_state({'font':font['id'],'hidden':False},s)
    value['installedFont']=font['id'];draft=commit(draft,value,'Installed font version',s,data['revision'])
    return {'font':font,'workspace':summary(draft,value,s)}


def package(key,s,revision=None):
    draft,value=load(key,s,revision);out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('font.json',json.dumps(value['metadata'],ensure_ascii=False,indent=2))
        for name,key in value['files'].items():archive.writestr(name,read_blob(key,s))
    return out.getvalue()


def embed(project,s):
    context=project.get('fontGlyph')
    if not isinstance(context,dict):return None
    return {'id':context.get('workspace'),'revision':context.get('revision'),
            'content':base64.b64encode(package(context.get('workspace'),s,context.get('revision'))).decode()}


def restore(project,s):
    embedded=project.pop('embeddedFontWorkspace',None);context=project.get('fontGlyph')
    if context is None:return
    if not isinstance(context,dict):raise ValueError('Invalid glyph workspace context.')
    valid_name(context.get('glyph'));variant_name(context.get('variant'))
    for key,lo,hi in [('originX',-100,200),('baselineY',-100,200),('advance',0,500)]:s.number(context.get(key),lo,hi,key)
    try:load(context.get('workspace'),s,context.get('revision'));return
    except (FileNotFoundError,ValueError):pass
    if not isinstance(embedded,dict):raise ValueError('This glyph project needs its embedded font workspace to restore the font source.')
    result=create({'content':embedded.get('content')},s)
    context.update(workspace=result['id'],revision=result['revision'])
