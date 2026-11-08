"""Installed-engine acceptance for font conversion and source preparation."""
from verification import DATA
import base64
import copy
import io
import json
from pathlib import Path
import tempfile
import server as s
import fonttools as ft
import fontworkspaces as fw
import fontlibrary as fl


def install(w):return fw.publish({'id':w['id'],'revision':w['revision']},s)
def letter(font,text):return s.lettering({'font':font,'text':text,'scale':100,'trim':'off'})['preview']
def prepare(w,action,**data):return ft.prepare({'id':w['id'],'revision':w['revision'],'variant':'ltr','action':action,**data},s)
def apply(w,p):return ft.apply({'id':w['id'],'prepared':p['id']},s)


if __name__=='__main__':
    raw=f'''<svg xmlns="{s.SVG}" width="1000" height="1000"><defs><font id="outline" horiz-adv-x="600"><font-face font-family="Native outline fixture" units-per-em="1000" ascent="800" descent="-200" cap-height="700" x-height="500"/><glyph glyph-name="uni004D" unicode="M" horiz-adv-x="700" d="M0 0H100V700H0Z M500 0H600V700H500Z"/><glyph glyph-name="A" unicode="A" d="M0 0H400V700H0Z"/><glyph glyph-name="V" unicode="V" d="M0 0H300V700H0Z"/><glyph glyph-name="e" unicode="e" d="M0 0H300V500H0Z"/><glyph glyph-name="eacute" unicode="é" d="M0 0H300V500H0Z M100 600H200V700H100Z"/><glyph glyph-name="space" unicode=" " horiz-adv-x="250"/><hkern u1="A" u2="V" k="80"/></font></defs></svg>'''.encode()
    (DATA / 'font-tool-fixture.svg').write_bytes(raw)
    w=ft.convert({'kind':'svg-font','content':base64.b64encode(raw).decode(),'name':'Font conversion verification','reference':'M','height':10},s)
    assert len(w['glyphs'])==5,w['glyphs'];assert abs(w['metadata']['kerning_pairs']['A V']*s.PX_MM-80/700*10)<.003,w['metadata']
    p=fw.glyph_project({'id':w['id'],'variant':'ltr','glyph':'M'},s)['project'];assert abs(p['layers'][0]['height']-10)<.01,p
    published=install(w);w=published['workspace'];font=published['font']['id'];original=letter(font,'AMV')
    review=prepare(w,'organize',params={'stage':'sort'});assert fw.detail(w['id'],s)['revision']==w['revision']
    w=apply(w,review);assert any(g['group']=='Upper Case Letters' for g in w['glyphs'])
    published2=install(w);w=published2['workspace'];assert letter(published2['font']['id'],'AMV')==original,'Organizing altered stitches'
    print('SVG outlines, physical reference height, kerning and geometry-preserving organization passed',flush=True)
    # A selection-scoped index must not modify the other glyphs.
    review=prepare(w,'color-index',glyphs=['A'],params={'index':4});w=apply(w,review)
    _,v=fw.load(w['id'],s)
    for name,expected in [('A','4'),('M',None)]:
        _,doc,g=fw.find_glyph(v,'ltr',name,s);paths=list(g.iter('{'+s.SVG+'}path'));assert paths and all(e.get('{'+s.STITCH+'}color_sort_index')==expected for e in paths)
    review=prepare(w,'locks',glyphs=['M'],params={'last_element':True});w=apply(w,review)
    _,v=fw.load(w['id'],s);_,doc,g=fw.find_glyph(v,'ltr','M',s);assert any(e.get('{'+s.STITCH+'}force_lock_stitches')=='True' for e in g.iter())
    # Prepared changes are rejected after intervening workspace edits.
    stale=prepare(w,'remove-svg-font');w=fw.update({'id':w['id'],'revision':w['revision'],'action':'metadata','metadata':{'description':'Fresh revision'}},s)
    try:apply(w,stale)
    except ValueError:pass
    else:raise AssertionError('Stale prepared source accepted')
    review=prepare(w,'organize',params={'stage':'step1'});assert {',','.','-'}.issubset(set(review['changes']['added']));w=apply(w,review)
    assert any(g['locked'] for g in w['glyphs'])
    placeholder=fw.glyph_project({'id':w['id'],'variant':'ltr','glyph':','},s)['project'];assert placeholder['layers']==[] and placeholder['fontGlyph']['guides']['baseline']==65
    print('Named glyph color indices, lock stitches, staged organization and stale-preview rejection passed',flush=True)
    # Test actual PES letters with explicit trims and a same-color pause.
    pattern=s.pystitch.EmbPattern();pattern.add_thread('#336699')
    for x,y in [(0,0),(20,0),(20,30),(0,30),(0,0)]:pattern.add_stitch_absolute(s.pystitch.STITCH,x,y)
    pattern.add_command(s.pystitch.STOP)
    for x,y in [(30,0),(50,0),(50,30)]:pattern.add_stitch_absolute(s.pystitch.STITCH,x,y)
    pattern.add_command(s.pystitch.TRIM);pattern.add_command(s.pystitch.END)
    fonts=[font,published2['font']['id']];results={}
    with tempfile.TemporaryDirectory() as tmp:
        pes=Path(tmp)/'LetterA.pes';s.pystitch.write_pes(pattern,str(pes),{'version':6});content=base64.b64encode(pes.read_bytes()).decode()
        (DATA / 'font-tool-letter.pes').write_bytes(pes.read_bytes())
        for mode in ('params','symbols','none'):
            imported=ft.convert({'kind':'letters','name':'Letter import verification '+mode,'commands':mode,'margin':1,'files':[{'name':'LetterA.pes','glyph':'A.alt','content':content},{'name':'LetterB.pes','glyph':'B','content':content}]},s)
            assert {g['name'] for g in imported['glyphs']}=={'A.alt','B'}
            pub=install(imported);fonts.append(pub['font']['id']);plan=letter(pub['font']['id'],'B')
            assert plan['width']==5 and plan['height']==3,plan
            assert plan['stops']==(0 if mode=='none' else 1),plan
            results[mode]={k:plan[k] for k in ('stitches','width','height','stops','trims')}
            if mode=='params':
                settings={'font':pub['font']['id'],'text':'B','scale':100,'trim':'off'};generated=s.lettering(settings)
                project={'version':1,'layers':[dict(id='letter-color',name='Imported B',type='text',lettering=settings,x=20,y=20,width=generated['width'],height=generated['height'],rotation=0,color='#000000',preserveFontColors=True)]}
                svg=Path(tmp)/'native-letter.svg';svg.write_bytes(s.build_svg(project));native=Path(tmp)/'native-letter.pes'
                with s.ENGINE_LOCK:native.write_bytes(s.run([s.ENGINE,'--extension=output','--format=pes','--version=6',str(svg)]))
                verified=s.stitch_data(native);assert verified['threads'][0]['color']=='#336699' and verified['stops']==1,verified
                results[mode]['nativePesColor']=verified['threads'][0]['color']
            print('Imported letter',mode,results[mode],flush=True)
    for key in fonts:fl.set_state({'font':key,'hidden':True},s)
    report={'svgReferenceHeightMm':p['layers'][0]['height'],'scaledKerningMm':80/700*10,'organizePreservesStitches':True,'namedColorIndex':True,'forcedLocks':True,'stage1AddsPunctuation':True,'staleReviewRejected':True,'machineLetters':results}
    (DATA / 'font-tools-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
