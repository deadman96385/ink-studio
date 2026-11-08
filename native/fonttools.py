"""Native font conversion and source preparation using the installed engine."""
import base64
import copy
import io
import json
from pathlib import Path
import tempfile
import unicodedata
import uuid
import inkex
from lxml import etree as ET
import fontlibrary as fl
import fontworkspaces as fw
from interchange import INPUTS, import_embroidery


def decode(value,limit=8*1024*1024):
    try:raw=base64.b64decode(value,validate=True)
    except (ValueError,TypeError):raise ValueError('The source file could not be read.')
    if not 0<len(raw)<=limit:raise ValueError('Choose source files totaling at most 8 MB.')
    return raw


def finish_source(raw,s):
    doc=s.xml(raw)
    for node in doc.iter('{'+s.SVG+'}path'):
        if node.get('id') and not node.get('{'+s.STITCH+'}random_seed'):node.set('{'+s.STITCH+'}random_seed',node.get('id'))
    seen=set()
    def unique(node):
        if node.get('id') in seen:s.prefix_ids(node,'copy-'+uuid.uuid4().hex+'-')
        if node.get('id'):seen.add(node.get('id'))
        for child in node:unique(child)
    unique(doc)
    used=set()
    for node in doc.iter():
        if not node.get('id') or node.get('id') in used:node.set('id','font-tool-'+uuid.uuid4().hex)
        used.add(node.get('id'))
    return fl.clean_svg(ET.tostring(doc),s)[0]


def mark_version(doc,s):
    meta=doc.find('{'+s.SVG+'}metadata')
    if meta is None:meta=ET.SubElement(doc,'{'+s.SVG+'}metadata')
    version=meta.find('{'+s.STITCH+'}inkstitch_svg_version')
    if version is None:version=ET.SubElement(meta,'{'+s.STITCH+'}inkstitch_svg_version')
    version.text='4'


def new_workspace(meta,files,label,s):
    meta=fl.validate_metadata(meta,s)
    value={'metadata':meta,'files':{name:fw.put_blob(raw,s) for name,raw in files.items()},'sourceFont':None}
    draft=fw.commit({'id':uuid.uuid4().hex,'history':[]},value,label,s)
    return fw.summary(draft,value,s)


def svg_font(data,s):
    raw=decode(data.get('content'));raw,_=fl.clean_svg(raw,s,allow_outline=True);doc=s.xml(raw)
    fonts=doc.findall('.//{'+s.SVG+'}font')
    if not fonts:raise ValueError('Choose an SVG outline font containing <font> and <glyph> elements. A regular drawing belongs in Import stitched letters.')
    index=s.number(data.get('fontIndex',0),0,len(fonts)-1,'Font index')
    if index!=int(index):raise ValueError('Choose a whole font index.')
    font=copy.deepcopy(fonts[int(index)])
    # Conversion starts from the selected font, not previously digitized layers
    # or guides in the uploaded document. The source file remains unchanged.
    original=doc;doc=s.svg_root();defs=ET.SubElement(doc,'{'+s.SVG+'}defs');defs.append(font)
    for metadata in original.findall('{'+s.SVG+'}metadata'):doc.append(copy.deepcopy(metadata))
    glyphs=font.findall('{'+s.SVG+'}glyph')
    if not 1<=len(glyphs)<=6000:raise ValueError('Use an SVG font with 1–6,000 glyphs.')
    reference=fw.valid_name(data.get('reference','M'));height=s.number(data.get('height',20),1,96,'Reference height')
    # The extension searches glyph-name, while designers naturally enter the
    # visible character. Resolve both and supply a unique internal name.
    found=next((g for g in glyphs if g.get('unicode')==reference or g.get('glyph-name')==reference),None)
    if found is None or not found.get('d'):raise ValueError('The reference character is missing or has no outline. Choose a character present in the SVG font.')
    if not inkex.Path(found.get('d')).bounding_box().height:raise ValueError('The reference character must have a nonzero height.')
    private_labels={}
    for g in glyphs:
        if not g.get('glyph-name'):g.set('glyph-name',g.get('unicode') or 'unassigned')
        if not g.get('unicode'):
            name=g.get('glyph-name')
            if name=='unassigned':raise ValueError('Every outline needs a Unicode value or glyph-name before conversion.')
            # Avoid the engine's duplicate-layer branch for absent Unicode.
            g.set('unicode',name.split('.')[0] if len(name.split('.'))==2 else name)
        if ord(g.get('unicode')[0])>=57344 and len(g.get('glyph-name').split('.'))!=2:
            label=g.get('unicode');g.set('glyph-name',label+'.native_pua');private_labels[label+'.native_pua']=label
    reference_name=found.get('glyph-name')
    face=font.find('{'+s.SVG+'}font-face')
    if face is None or float(face.get('units-per-em',0))<=0:raise ValueError('The SVG font needs a font-face with positive units-per-em.')
    name=str(data.get('name') or face.get('font-family') or 'Converted outline font')
    variant=fw.variant_name(data.get('variant','ltr'))
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='svg-font-') as tmp:
        source=Path(tmp)/'source.svg';source.write_bytes(ET.tostring(doc))
        converted=s.run([s.ENGINE,'--extension=lettering_svg_font_to_layers','--reference='+reference_name,'--height='+str(height),str(source)],headless=True)
        source.write_bytes(converted)
        # Preserve the engine's scaled advances, kerning, space and em size.
        s.run([s.ENGINE,'--extension=lettering_generate_json','--font-file='+str(source),'--font-name='+name,'--font_license='+str(data.get('license','')),'--size='+str(height),'--auto-satin=False','--reversible=False','--default_variant='+variant,str(source)],headless=True)
        meta=json.loads((Path(tmp)/'font.json').read_text())
    doc=s.xml(converted)
    for g in fw.glyph_nodes(doc,s):
        glyph_label=fw.glyph_name(g,s)
        if glyph_label in private_labels:g.set('{'+s.INK+'}label','GlyphLayer-'+private_labels[glyph_label])
    # Space stays in metadata; empty separator/control layers are not glyphs.
    for g in list(fw.glyph_nodes(doc,s)):
        glyph=fw.glyph_name(g,s)
        if not glyph.strip() or any(ord(c)<32 for c in glyph):g.getparent().remove(g)
    if not fw.glyph_nodes(doc,s):raise ValueError('No editable glyph outlines were produced.')
    meta['name']=name;meta['auto_satin']=False;meta['reversible']=False
    return new_workspace(meta,{variant+'/converted.svg':finish_source(ET.tostring(doc),s)},'Converted SVG outline font',s)


def imported_commands(doc,mode,s):
    # Normalize existing SVG command symbols too, then express the requested
    # representation without disturbing positioning or routing commands.
    ids={e.get('id'):e for e in doc.iter() if e.get('id')}
    for connector in list(doc.xpath('//*[@inkscape:connection-start]',namespaces={'inkscape':s.INK})):
        a=ids.get(connector.get('{'+s.INK+'}connection-start','')[1:]);b=ids.get(connector.get('{'+s.INK+'}connection-end','')[1:])
        if a is None or b is None:continue
        if b.tag=='{'+s.SVG+'}use':a,b=b,a
        href=a.get('{http://www.w3.org/1999/xlink}href',a.get('href',''))
        command=next((c for c in ('trim','stop') if href=='#inkstitch_'+c or href.startswith('#inkstitch_'+c+'-')),None)
        if command:
            b.set('{'+s.STITCH+'}'+command+'_after','True');a.getparent().remove(a);connector.getparent().remove(connector)
    if mode=='params':return
    for path in list(doc.iter('{'+s.SVG+'}path')):
        for command in ('trim','stop'):
            attr='{'+s.STITCH+'}'+command+'_after'
            enabled=path.attrib.pop(attr,None)
            if str(enabled).lower()!='true' or mode=='none':continue
            target=path.get('id') or 'target-'+uuid.uuid4().hex;path.set('id',target)
            from digitizing import command_symbol
            href=command_symbol(doc,command);token=uuid.uuid4().hex
            group=ET.SubElement(path.getparent(),'{'+s.SVG+'}g',id='command_group-'+token,style='display:none')
            symbol=ET.SubElement(group,'{'+s.SVG+'}use',id='command-'+token,x='0',y='0');symbol.set('{http://www.w3.org/1999/xlink}href',href)
            connector=ET.SubElement(group,'{'+s.SVG+'}path',id='command_connector-'+token,d='M0,0L.001,.001')
            connector.set('{'+s.INK+'}connection-start','#command-'+token);connector.set('{'+s.INK+'}connection-end','#'+target)


def letters(data,s):
    entries=data.get('files');variant=fw.variant_name(data.get('variant','ltr'));mode=data.get('commands','params')
    if mode not in ('params','symbols','none'):raise ValueError('Choose parameters, symbols or no imported commands.')
    if not isinstance(entries,list) or not 1<=len(entries)<=128:raise ValueError('Choose 1–128 letter files.')
    margin=s.number(data.get('margin',0),0,20,'Left margin');total=0;names=set();prepared=[]
    # Decode and validate the whole batch before creating any workspace.
    for item in entries:
        glyph=fw.valid_name(item.get('glyph'));ext=Path(str(item.get('name',''))).suffix.lower().lstrip('.')
        if ext not in INPUTS|{'svg'}:raise ValueError('Unsupported letter file: '+str(item.get('name')))
        if glyph in names:raise ValueError('Assign a different glyph name to each file. Duplicate: '+glyph)
        names.add(glyph);raw=decode(item.get('content'));total+=len(raw)
        if total>8*1024*1024:raise ValueError('Choose source files totaling at most 8 MB.')
        prepared.append((item,glyph,ext,raw))
    assets=[];advance={};maxheight=0;mapping={}
    with tempfile.TemporaryDirectory(prefix='letters-font-') as tmp:
        folder=Path(tmp)/'letters';folder.mkdir()
        for i,(item,glyph,ext,raw) in enumerate(prepared):
            if ext=='svg':asset=s.import_svg({'svg':raw.decode('utf-8-sig'),'name':item['name']})
            else:asset=import_embroidery({'name':item['name'],'data':item['content']},s)['asset']
            if asset['width']+margin>96 or asset['height']>96:raise ValueError(glyph+' exceeds the font editor at its original size. Import a smaller letter.')
            # Normalize SVG viewports through the existing importer. The
            # desktop letters tool expects glyph coordinates in pixels.
            doc=s.svg_root();mark_version(doc,s);g=ET.SubElement(doc,'{'+s.SVG+'}g',transform=f'scale({1/s.PX_MM})');g.append(s.xml(asset['svg'].encode()))
            imported_commands(doc,mode,s)
            # Keep definitions inside the group copied by letters_to_font.
            for defs in list(doc.findall('{'+s.SVG+'}defs')):g.append(defs)
            s.prefix_ids(doc,f'letter{i}-');alias=chr(0xE000+i);mapping[alias]=glyph
            (folder/(alias+'.SVG')).write_bytes(ET.tostring(doc));advance[glyph]=(asset['width']+margin)/s.PX_MM;maxheight=max(maxheight,asset['height']);assets.append(asset)
        source=Path(tmp)/'blank.svg';source.write_bytes(ET.tostring(s.svg_root()))
        with s.ENGINE_LOCK:converted=s.run([s.ENGINE,'--extension=letters_to_font','--font-dir='+str(folder),'--file-format=*.SVG','--margin-left='+str(margin),'--import-commands=params',str(source)],headless=True)
    doc=s.xml(converted);mark_version(doc,s);count=0
    for g in fw.glyph_nodes(doc,s):
        alias=fw.glyph_name(g,s)
        if alias in mapping:g.set('{'+s.INK+'}label','GlyphLayer-'+mapping[alias]);count+=1
    if count!=len(entries):raise ValueError('The engine did not import every letter. The source files are unchanged.')
    # Loading SVG letters changes the extension's current SVG internally,
    # so its baseline can land in the last input instead of the output.
    # Store a real output baseline and canonical px geometry for the font
    # loader, including non-manual stroke widths and local clip resources.
    inkdoc=inkex.load_svg(io.BytesIO(ET.tostring(doc))).getroot();factor=float(inkdoc.scale)
    wrap=ET.SubElement(doc,'{'+s.SVG+'}g',transform=f'scale({factor})')
    for child in list(doc):
        if child is not wrap and child.tag=='{'+s.SVG+'}g':wrap.append(child)
    doc.set('viewBox',f'0 0 {100/s.PX_MM} {100/s.PX_MM}')
    nv=doc.find('{'+fl.SODI+'}namedview')
    if nv is None:nv=ET.SubElement(doc,'{'+fl.SODI+'}namedview')
    ET.SubElement(nv,'{'+fl.SODI+'}guide',position='0,0',orientation='0,1',attrib={'{'+s.INK+'}label':'baseline'})
    doc=fw.canonical_paths(doc,s)
    meta={'name':str(data.get('name') or 'Imported stitched letters'),'font_license':str(data.get('license','')),'size':maxheight,'leading':(maxheight+5)/s.PX_MM,'horiz_adv_x_space':5/s.PX_MM,'horiz_adv_x':advance,'min_scale':1,'max_scale':1,'auto_satin':False,'reversible':False,'sortable':False,'default_variant':variant}
    return new_workspace(meta,{variant+'/letters.svg':finish_source(ET.tostring(doc),s)},'Imported stitched letters',s)


def convert(data,s):
    if data.get('kind')=='svg-font':return svg_font(data,s)
    if data.get('kind')=='letters':return letters(data,s)
    raise ValueError('Choose an SVG outline font or stitched letters.')


def merge_variant(value,variant,s):
    """Resolve multiple source viewports into one physical font baseline."""
    root=s.svg_root();root.set('width','1000px');root.set('height','1000px');root.set('viewBox','0 0 1000 1000')
    mark_version(root,s)
    nv=ET.SubElement(root,'{'+fl.SODI+'}namedview');ET.SubElement(nv,'{'+fl.SODI+'}guide',position='0,1000',orientation='0,1',attrib={'{'+s.INK+'}label':'baseline'})
    for i,(file,key) in enumerate(value['files'].items()):
        if file.split('/')[0].removesuffix('.svg')!=variant or not file.endswith('.svg'):continue
        doc=fw.read_doc(key,s);baseline=0
        for guide in doc.namedview.get_guides():
            if guide.label=='baseline':baseline=inkex.units.convert_unit(doc.get_page_bbox().y.size-guide.raw_position.y,'px',doc.unit)
        for original in fw.glyph_nodes(doc,s):
            bundle=ET.Element('{'+s.SVG+'}g');defs=fw.definitions(doc,original,s);bundle.append(defs)
            g=copy.deepcopy(original);g.set('style',str(original.specified_style()));g.set('transform',str(inkex.Transform(translate=(0,-baseline)) @ inkex.Transform(scale=float(doc.scale)) @ original.composed_transform()));bundle.append(g)
            for p in g.iter('{'+s.SVG+'}path'):
                if p.get('id') and not p.get('{'+s.STITCH+'}random_seed'):p.set('{'+s.STITCH+'}random_seed',p.get('id'))
            s.prefix_ids(bundle,'merged-'+uuid.uuid4().hex+'-');root.append(bundle)
    if not fw.glyph_nodes(root,s):raise ValueError('Choose a direction with glyphs.')
    return finish_source(ET.tostring(fw.canonical_paths(root,s)),s)


def prepare(data,s):
    draft,value=fw.load(data.get('id'),s);expected=data.get('revision');variant=fw.variant_name(data.get('variant','ltr'));action=data.get('action');params=data.get('params') or {}
    if expected!=draft['revision']:raise ValueError('Reload the workspace before preparing this operation.')
    before=fw.inventory(value,s);selected=data.get('glyphs') or []
    if not isinstance(selected,list) or any(not isinstance(n,str) for n in selected):raise ValueError('Choose glyph names from this workspace.')
    selected=[fw.valid_name(n) for n in selected]
    valid={g['name'] for g in before if g['variant']==variant}
    if any(n not in valid for n in selected):raise ValueError('A selected glyph is missing from this direction.')
    target_files={f:k for f,k in value['files'].items() if f.endswith('.svg') and f.split('/')[0].removesuffix('.svg')==variant}
    if not target_files:raise ValueError('Choose a direction with source files.')
    if action=='organize':
        if len(valid)!=sum(g['variant']==variant for g in before):raise ValueError('Rename or remove duplicate glyph sources in this direction before organizing it.')
        stage=params.get('stage','sort')
        if stage not in ('sort','step1','step2','step3','step4','step5','step6','step7','step8'):raise ValueError('Choose an organization stage.')
        raw=fw.read_blob(next(iter(target_files.values())),s) if len(target_files)==1 else merge_variant(value,variant,s)
        sources={'organized.svg':raw};extension='lettering_organize_glyphs';args=['--action='+stage];label='Organized glyphs: '+stage
    elif action=='locks':
        extension='lettering_force_lock_stitches';args=[];sources={f:fw.read_blob(k,s) for f,k in target_files.items()};label='Prepared forced lock stitches'
        for key in ('satin_only','distance','last_element','last_group_element'):
            v=params.get(key,False)
            if type(v) is not bool:raise ValueError('Choose valid lock stitch options.')
            args.append('--'+key+'='+str(v))
        lo=s.number(params.get('min_distance',1),0,50,'Minimum jump');hi=s.number(params.get('max_distance',3),.1,500,'Maximum jump')
        if hi<lo:raise ValueError('Maximum jump must be at least the minimum.')
        if not any(params.get(k) for k in ('distance','last_element','last_group_element')):raise ValueError('Enable at least one lock stitch rule.')
        args+=['--min_distance='+str(lo),'--max_distance='+str(hi)]
    elif action=='color-index':
        index=s.number(params.get('index',0),0,100,'Color sort index')
        if index!=int(index):raise ValueError('Use a whole color sort index.')
        extension='lettering_set_color_sort_index';args=['--color-sort-index='+str(int(index))];sources={f:fw.read_blob(k,s) for f,k in target_files.items()};label='Set glyph color index '+str(int(index))
    elif action=='remove-svg-font':
        extension='lettering_remove_kerning';args=[];sources={f:fw.read_blob(k,s) for f,k in target_files.items()};label='Removed SVG font tables; metadata spacing retained'
    else:raise ValueError('Choose a font source operation.')
    with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='font-source-tool-') as tmp:
        for i,(file,raw) in enumerate(sources.items()):
            source=Path(tmp)/(str(i)+'.svg');doc=s.xml(raw);groups=fw.glyph_nodes(doc,s)
            targets=[g for g in groups if not selected or fw.glyph_name(g,s) in selected]
            if action in ('locks','color-index') and not targets:continue
            # Lock rules work on all glyph layers regardless of selection.
            # Temporarily detach other glyphs, then put their exact originals
            # back in the result after the installed extension finishes.
            original=copy.deepcopy(doc)
            protected_names={}
            if action=='organize' and stage in ('step5','step6'):
                # 3.3.0 asks Unicode for names without a default; private-use
                # glyphs have no Unicode name. Keep them outside that lookup.
                for g in groups:
                    name=fw.glyph_name(g,s)
                    if len(name)==1 and not unicodedata.name(name,''):
                        temporary='private-'+uuid.uuid4().hex;protected_names[temporary]=name
                        g.set('{'+s.INK+'}label','GlyphLayer-'+temporary)
            if action=='locks' and selected:
                for g in groups:
                    if g not in targets:g.getparent().remove(g)
            source.write_bytes(ET.tostring(doc));selection=['--id='+g.get('id') for g in targets] if action=='color-index' else []
            call_args=[s.ENGINE,'--extension='+extension,*args,*selection]
            if action=='remove-svg-font':call_args+=['--font-files='+str(source)]
            raw=s.run(call_args+[str(source)],headless=True)
            # inkex deliberately emits no SVG when an effect makes no change.
            result=s.xml(source.read_bytes() if action=='remove-svg-font' or not raw.strip() else raw)
            for g in fw.glyph_nodes(result,s):
                name=fw.glyph_name(g,s)
                if name in protected_names:g.set('{'+s.INK+'}label','GlyphLayer-'+protected_names[name])
            if action=='organize':
                old_glyphs={fw.glyph_name(g,s):g for g in fw.glyph_nodes(original,s)}
                for g in fw.glyph_nodes(result,s):
                    name=fw.glyph_name(g,s);old=old_glyphs.get(name)
                    # 3.3.0's lookup accidentally unlocks every layer it
                    # traverses. Keep sampling locks scoped to the stage.
                    if stage=='step1':locked=name not in (',','.','-')
                    elif stage=='sort':locked=old is not None and old.get('{'+fl.SODI+'}insensitive') is not None
                    else:locked=old is not None and old.getparent().get('id')==g.getparent().get('id') and old.get('{'+fl.SODI+'}insensitive') is not None
                    if locked:g.set('{'+fl.SODI+'}insensitive','true')
                    else:g.attrib.pop('{'+fl.SODI+'}insensitive',None)
            if action in ('locks','color-index'):
                attr='{'+s.STITCH+'}'+('force_lock_stitches' if action=='locks' else 'color_sort_index')
                old_ids={e.get('id'):e for e in original.iter() if e.get('id')}
                for e in result.iter():
                    if e.get(attr) is not None and e.get('id') in old_ids:old_ids[e.get('id')].set(attr,e.get(attr))
                result=original
            target=variant+'/organized.svg' if action=='organize' else file
            value['files'][target]=fw.put_blob(finish_source(ET.tostring(result),s),s)
    if action=='organize':
        for file in target_files:
            if file!=variant+'/organized.svg':value['files'].pop(file,None)
    after=fw.inventory(value,s);old={(g['variant'],g['name']):g for g in before};new={(g['variant'],g['name']):g for g in after}
    changes={'added':[n for v,n in new.keys()-old.keys()],'removed':[n for v,n in old.keys()-new.keys()],
             'glyphsBefore':len(before),'glyphsAfter':len(after),'pathsBefore':sum(g['paths'] for g in before),'pathsAfter':sum(g['paths'] for g in after),
             'lockedBefore':sum(g['locked'] for g in before),'lockedAfter':sum(g['locked'] for g in after),'affected':len(selected) if selected else len(valid)}
    key=uuid.uuid4().hex;folder=fw.locations(s)/'prepared';folder.mkdir(exist_ok=True)
    s.write_atomic(folder/(key+'.json'),{'workspace':draft['id'],'revision':expected,'value':value,'label':label,'changes':changes})
    return {'id':key,'label':label,'changes':changes,'glyphs':[g for g in after if g['variant']==variant]}


def apply(data,s):
    p=fw.locations(s)/'prepared'/(s.safe_id(data.get('prepared'))+'.json');prepared=json.loads(p.read_text())
    draft,_=fw.load(prepared['workspace'],s)
    if data.get('id')!=draft['id']:raise ValueError('This preview belongs to another workspace.')
    draft=fw.commit(draft,prepared['value'],prepared['label'],s,prepared['revision'])
    return fw.summary(draft,prepared['value'],s)
