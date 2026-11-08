"""Regression checks for source repair, organization stages and lock rules."""
from verification import DATA
import base64
import copy
import json
from pathlib import Path
from lxml import etree as ET
import server as s
import fonttools as ft
import fontworkspaces as fw
from verify_fonttools import prepare,apply,install,letter


def source(w):
    return fw.load(w['id'],s)[1]


def locked(value):
    return {p.get('id') for key in value['files'].values() for p in fw.read_doc(key,s).iter() if p.get('{'+s.STITCH+'}force_lock_stitches')=='True'}


if __name__=='__main__':
    raw=(DATA / 'font-tool-fixture.svg').read_bytes()
    doc=s.xml(raw);font=doc.find('.//{'+s.SVG+'}font')
    for name,char in [('A.alt',None),('private','\ue010'),('aacute','á'),('Aring','Å'),('Aringacute','Ǻ'),('O','O'),('Omacron','Ō'),('Omacrongrave','Ṓ')]:
        g=ET.SubElement(font,'{'+s.SVG+'}glyph',attrib={'glyph-name':name,'d':'M0 0H100V500H0Z'})
        if char:g.set('unicode',char)
    # Existing digitized layers/guides must not leak into new conversion.
    ET.SubElement(doc,'{'+s.SVG+'}g',attrib={'{'+s.INK+'}label':'GlyphLayer-unrelated'})
    nv=ET.SubElement(doc,'{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}namedview')
    ET.SubElement(nv,'{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}guide',position='0,123',orientation='0,1',attrib={'{'+s.INK+'}label':'baseline'})
    w=ft.convert({'kind':'svg-font','content':base64.b64encode(ET.tostring(doc)).decode(),'name':'Font edge verification','reference':'M','height':10},s)
    assert w['name']=='Font edge verification',w['name']
    assert {g['name'] for g in w['glyphs']}=={'M','A','V','e','é','A.alt','\ue010','á','Å','Ǻ','O','Ō','Ṓ'},w['glyphs']
    assert not w['duplicates']
    root=fw.read_doc(next(iter(source(w)['files'].values())),s)
    assert len([g for g in root.namedview.get_guides() if g.label=='baseline'])==1
    before=copy.deepcopy(w['metadata']);w=apply(w,prepare(w,'remove-svg-font'))
    assert w['metadata']==before
    assert not any(fw.read_doc(k,s).findall('.//{'+s.SVG+'}font') for k in source(w)['files'].values())
    print('Alternate and private-use outlines, isolated conversion, and font-table cleanup passed',flush=True)
    # Duplicate names in the same file and in separate files are individually repairable.
    value=source(w);file=next(iter(value['files']));root=fw.read_doc(value['files'][file],s)
    original=next(g for g in fw.glyph_nodes(root,s) if fw.glyph_name(g,s)=='A');clone=copy.deepcopy(original);s.prefix_ids(clone,'duplicate-');root.append(clone)
    value['files'][file]=fw.put_blob(ET.tostring(root),s)
    duplicate=ft.new_workspace(value['metadata'],{f:fw.read_blob(k,s) for f,k in value['files'].items()},'Duplicate source fixture',s)
    assert duplicate['duplicates']
    chosen=[g for g in duplicate['glyphs'] if g['name']=='A'][-1]
    duplicate=fw.update({'id':duplicate['id'],'revision':duplicate['revision'],'action':'rename','glyph':'A','variant':'ltr','name':'A.copy','source':{'file':chosen['file'],'glyphIndex':chosen['glyphIndex']}},s)
    assert not duplicate['duplicates'] and {'A','A.copy'}<={g['name'] for g in duplicate['glyphs']}
    value=source(duplicate);value['files']['ltr/extra.svg']=value['files'][file]
    duplicate=ft.new_workspace(value['metadata'],{f:fw.read_blob(k,s) for f,k in value['files'].items()},'Duplicate files fixture',s)
    chosen=next(g for g in duplicate['glyphs'] if g['name']=='A' and g['file']=='ltr/extra.svg')
    duplicate=fw.update({'id':duplicate['id'],'revision':duplicate['revision'],'action':'remove','glyph':'A','variant':'ltr','source':{'file':chosen['file'],'glyphIndex':chosen['glyphIndex']}},s)
    assert len([g for g in duplicate['glyphs'] if g['name']=='A'])==1
    print('Duplicate source rename/removal preserves the other glyphs',flush=True)
    stages={}
    for stage in ['step'+str(i) for i in range(1,9)]:
        review=prepare(w,'organize',params={'stage':stage});w=apply(w,review)
        for key in source(w)['files'].values():
            doc=fw.read_doc(key,s);ids=[n.get('id') for n in doc.iter() if n.get('id')]
            assert len(ids)==len(set(ids)),stage
        stages[stage]=review['changes'];print(stage,len(w['glyphs']),'glyphs',flush=True)
    # Explicit manual stitches give deterministic 2 mm and 10 mm jumps.
    doc=s.svg_root();doc.set('viewBox','0 0 100 100');ft.mark_version(doc,s)
    g=ET.SubElement(doc,'{'+s.SVG+'}g',id='lock-glyph',attrib={'{'+s.INK+'}label':'GlyphLayer-L','{'+s.INK+'}groupmode':'layer'})
    for i,(a,b) in enumerate([(0,1),(3,4),(14,15)]):
        group=ET.SubElement(g,'{'+s.SVG+'}g',id='subgroup'+str(i))
        path=ET.SubElement(group,'{'+s.SVG+'}path',id='segment'+str(i),d=f'M{a},0L{b},0',style='fill:none;stroke:#223344;stroke-width:.2')
        path.set('{'+s.STITCH+'}stroke_method','manual_stitch')
    lockw=ft.new_workspace({'name':'Lock rules verification','size':10},{'ltr/locks.svg':ET.tostring(doc)},'Lock fixture',s)
    distance=apply(lockw,prepare(lockw,'locks',params={'distance':True,'min_distance':1,'max_distance':3}))
    assert locked(source(distance))=={'segment0'},locked(source(distance))
    initial=fw.load(lockw['id'],s,lockw['revision'])[1]
    groups=ft.new_workspace(initial['metadata'],{f:fw.read_blob(k,s) for f,k in initial['files'].items()},'Group locks fixture',s)
    groups=apply(groups,prepare(groups,'locks',params={'last_group_element':True}))
    assert locked(source(groups))=={'segment0','segment1','segment2'}
    satin=ft.new_workspace(initial['metadata'],{'ltr/locks.svg':ET.tostring(doc)},'Satin locks fixture',s)
    satin=apply(satin,prepare(satin,'locks',params={'satin_only':True,'last_element':True}))
    assert not locked(source(satin))
    print('Distance, group-ending, and satin-only lock rules passed',flush=True)
    # Native path index is carried into generated source SVG.
    layer=dict(id='indexed',type='path',name='Indexed line',x=20,y=20,width=10,height=10,rotation=0,color='#223344',stitch='running',points=[[0,0],[1,1]],advanced={'color_sort_index':7})
    built=s.xml(s.build_svg({'version':1,'layers':[layer]}))
    assert any(p.get('{'+s.STITCH+'}color_sort_index')=='7' for p in built.iter()),ET.tostring(built)
    report={'isolatedSvgConversion':True,'alternateAndPrivateGlyphs':True,'duplicateRepair':True,'tableCleanupKeepsSpacing':True,'organizationStages':stages,'distanceLocks':True,'groupLocks':True,'satinOnly':True,'nativePathColorIndex':True}
    (DATA / 'font-tools-edge-verification.json').write_text(json.dumps(report,indent=2));print('All source edge checks passed',flush=True)
