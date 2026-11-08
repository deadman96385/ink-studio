"""Document-wide embroidery metadata cleanup without flattening native artwork."""
import copy,hashlib,json,tempfile
from pathlib import Path
from lxml import etree as ET
import preferences
from svg_structure import href,SVG,XLINK,INK

OPTIONS=('settings','metadata','origin','frameOut')

def clean_metadata(root,s):
    metas=list(root.iter('{'+SVG+'}metadata'))
    count=sum(1 for meta in metas for node in meta.iterdescendants() if ET.QName(node).namespace==s.STITCH)
    if not count:return 0
    # The desktop extension visits direct-root metadata. Hoist copies so nested
    # imported documents are covered, then put the cleaned metadata back in place.
    probe=s.svg_root()
    for meta in metas:probe.append(copy.deepcopy(meta))
    # Avoid the engine's legacy-document migration dialog for this isolated probe.
    for version in list(probe.iter('{'+s.STITCH+'}inkstitch_svg_version')):version.getparent().remove(version)
    ET.SubElement(probe.find('{'+SVG+'}metadata'),'{'+s.STITCH+'}inkstitch_svg_version').text='4'
    with tempfile.TemporaryDirectory(prefix='document-cleanup-') as tmp:
        path=Path(tmp)/'metadata.svg';path.write_bytes(ET.tostring(probe))
        out=s.xml(s.run([s.ENGINE,'--extension=remove_embroidery_settings','--del_params=none','--del_commands=none','--del_print=True',str(path)],headless=True))
    cleaned=out.findall('{'+SVG+'}metadata')
    if len(cleaned)!=len(metas):raise ValueError('The engine did not retain the document metadata containers.')
    for old,new in zip(metas,cleaned):
        # The desktop code tests the literal prefix, missing equivalent aliases.
        for node in list(new.iterdescendants()):
            if ET.QName(node).namespace==s.STITCH and node.getparent() is not None:node.getparent().remove(node)
        old.getparent().replace(old,new)
    return count

def clear_global(root,command):
    prefix='#inkstitch_'+command
    uses=[e for e in root.iter('{'+SVG+'}use') if href(e)==prefix or href(e).startswith(prefix+'-')]
    ids={e.get('id') for e in uses if e.get('id')}
    for e in uses:e.getparent().remove(e)
    # Keep unrelated symbols and artwork, including groups containing both.
    for e in list(root.iter()):
        if any(e.get('{'+INK+'}connection-'+side,'').lstrip('#') in ids for side in ('start','end')):
            e.getparent().remove(e)
    references={href(e).lstrip('#') for e in root.iter('{'+SVG+'}use')}
    for e in list(root.iter('{'+SVG+'}symbol')):
        id=e.get('id','')
        if (id==prefix[1:] or id.startswith(prefix[1:]+'-')) and id not in references:e.getparent().remove(e)
    return len(uses)

def prepare(data,s):
    original=data.get('project');options=data.get('options',{})
    if not isinstance(original,dict) or original.get('version')!=1 or not isinstance(original.get('layers'),list) or len(original['layers'])>s.MAX_LAYERS:raise ValueError('Choose an Ink Studio design to clean.')
    if not isinstance(options,dict) or set(options)-set(OPTIONS) or any(type(v) is not bool for v in options.values()):raise ValueError('Choose valid document cleanup options.')
    if not any(options.values()):raise ValueError('Choose at least one cleanup option.')
    project=copy.deepcopy(original);assets=[];mapping={}
    report={'settingsReset':False,'metadataEntries':0,'importedSettings':0,'assetsChanged':0,'origin':0,'frameOut':0}
    if options.get('metadata') and 'printSettings' in project:project.pop('printSettings');report['metadataEntries']+=1
    if options.get('settings'):
        report['settingsReset']=preferences.effective(project)!=preferences.FACTORY
        project['embroiderySettings']=dict(preferences.FACTORY)
    for key in ('origin','frameOut'):
        if options.get(key) and key in project:project.pop(key);report[key]+=1
    with s.ENGINE_LOCK:
        for layer in s.asset_layers(project):
            if layer.get('type')!='import':continue
            key=s.safe_id(layer.get('asset'))
            if key in mapping:layer['asset']=mapping[key];continue
            file=s.DATA/'assets'/(key+'.json')
            if not file.exists():raise ValueError('An imported SVG asset is missing. Restore its project backup first.')
            asset=json.loads(file.read_text());new=copy.deepcopy(asset);root=s.xml(asset['svg'].encode());changed=False
            if options.get('metadata'):
                count=clean_metadata(root,s);report['metadataEntries']+=count;changed=bool(count)
                if 'embroiderySettings' in new:new.pop('embroiderySettings');report['importedSettings']+=1;changed=True
            for name,command in [('origin','origin'),('frameOut','stop_position')]:
                if options.get(name):
                    count=clear_global(root,command);report[name]+=count;changed|=bool(count)
            if changed:
                new['svg']=ET.tostring(root,encoding='unicode')
                new['key']=hashlib.sha256(new['svg'].encode()).hexdigest()
                # If only the asset's remembered settings changed, retain a new
                # immutable identity so Undo and other projects keep their copy.
                if new['key']==key:
                    ET.SubElement(root,'{'+SVG+'}metadata')
                    new['svg']=ET.tostring(root,encoding='unicode');new['key']=hashlib.sha256(new['svg'].encode()).hexdigest()
                s.write_atomic(s.DATA/'assets'/(new['key']+'.json'),new)
                assets.append(new);report['assetsChanged']+=1
            mapping[key]=new['key'];layer['asset']=new['key']
        changed=any(report.values())
        preview=None;preview_error=None
        if changed and any(l.get('visible',True) and l.get('type')!='image' and l.get('role','artwork')=='artwork' for l in project['layers']):
            try:preview=preferences.preview({'project':project,'settings':preferences.effective(project)},s)['preview']
            except (ValueError,RuntimeError) as exc:preview_error=str(exc)
    return {'project':project,'assets':assets,'report':report,'changed':changed,'preview':preview,'previewError':preview_error}
