"""Real color-list / palette round trips and recolored SVG/PES acceptance checks."""
from verification import DATA
import base64,copy,io,json,urllib.error,uuid
from pathlib import Path
import pystitch
from verify_native import sewing,api,export,rectangle

def reject(path,data,contains):
    try:api(path,data)
    except urllib.error.HTTPError as e:
        message=json.loads(e.read())['error'];assert e.code==400 and contains.lower() in message.lower(),message
    else:raise AssertionError('Expected rejection: '+contains)

def main():
    rows=[{'color':'#134a76','name':'Ocean 2','number':'A-1','brand':'Studio'},
          {'color':'#e8a900','name':'Café gold','number':'214','brand':'Brother Embroidery'},
          {'color':'#a04080','name':'Berry','number':'X-2','brand':'Other brand'}]
    name='Thread verification '+uuid.uuid4().hex[:8]
    pal=api('/api/save-palette',{'name':name,'colors':rows});key=pal['key']
    assert pal['colors']==rows and pal['custom']
    assert api('/api/palettes/'+key)['colors']==rows
    raw=api('/api/palette-file',{'name':name,'colors':rows})['text']
    assert api('/api/import-palette',{'text':raw})['colors']==rows
    modified=list(reversed(rows));modified[0]={**modified[0],'number':'NEW'}
    updated=api('/api/save-palette',{'name':name,'colors':modified,'replaceKey':key})
    assert updated['colors']==modified and updated['key']!=key
    assert not ((DATA / 'palettes')/(key+'.gpl')).exists()
    # Remove only this test-created custom palette.
    ((DATA / 'palettes')/(updated['key']+'.gpl')).unlink()
    reject('/api/save-palette',{'name':'Bad\nname','colors':rows},'Name the palette')
    reject('/api/save-palette',{'name':'Bad','colors':[{**rows[0],'color':'#ff00'}]},'color')
    reject('/api/save-palette',{'name':'Bad','colors':rows,'replaceKey':'missing'},'no longer exists')
    brother=next(p for p in api('/api/palettes') if p['name']=='Brother Embroidery')
    reject('/api/save-palette',{'name':'Bad','colors':rows,'replaceKey':brother['key']},'no longer exists')
    def read(name,raw,**opts):return api('/api/import-threadlist',{'name':name,'data':base64.b64encode(raw).decode(),**opts})['colors']
    text='Thread Order\n================\n\n'+''.join(f'{i+1} {t["name"]} #{t["number"]} - {t["brand"]} ({t["color"]})\n' for i,t in enumerate(rows))+'\nThread Used\nOcean 2 #A-1 - Studio (#134a76)\n'
    assert read('colors.txt',text.encode())==rows
    catalog=read('catalog.txt',b'1 Thread #900\n2 Thread #214\n',method='catalog',palette=brother['key'])
    assert [t['color'] for t in catalog]==['#000000','#e8a900']
    assert read('old-studio.txt',b'1. #123456 Brand 2 Old Name')[0]['color']=='#123456'
    reject('/api/import-threadlist',{'name':'colors.txt','data':base64.b64encode(b'1 #900\n2 #9999999').decode()},'RGB')
    reject('/api/import-threadlist',{'name':'catalog.txt','data':base64.b64encode(b'1 Thread #900 #214').decode(),'method':'catalog','palette':brother['key']},'unique')
    reject('/api/import-threadlist',{'name':'bad.edr','data':'AAAA'},'four-byte')
    reject('/api/import-threadlist',{'name':'bad.inf','data':base64.b64encode(b'bad').decode()},'complete')
    # Four steps, including return to the same source RGB, outline, trim and pause.
    p={'version':1,'id':'threadwork-verification','name':'Thread color controls example','fabric':'#faf7f0','grid':True,'snap':True,'origin':[50,50],'frameOut':[50,8],
       'layers':[rectangle(id='left',x=18,y=25,width=22,height=18,color='#134a76',borderEnabled=True,borderColor='#b96548',borderStitch='bean',stopAfter=True,trimAfter=True),
                 rectangle(id='middle',x=45,y=30,width=15,height=20,color='#416580'),
                 rectangle(id='right',x=65,y=45,width=16,height=14,color='#134a76')]}
    original=export(p);inventory=api('/api/thread-colors',{'project':p});assert len(inventory['colors'])==4
    assert inventory['preview']['segments']==original['preview']['segments']
    sequence=[rows[0],rows[1],rows[2],{**rows[0],'color':'#3b7051','name':'Meadow'}]
    r=api('/api/thread-colors',{'project':p,'colors':sequence})
    assert [t['color'] for t in r['preview']['threads']]==[t['color'] for t in sequence]
    for field in ('segments','stitches','stops','trims','jumps','bounds'):
        assert r['preview'][field]==original['preview'][field],field
    colored={**p,'threadBook':r['threadBook'],'layers':[{**l,'visible':False} for l in p['layers']]+[r['layer']]}
    final=export(colored)
    assert sewing(final['preview'])==sewing(r['preview'])
    restored=export(api('/api/restore',{'project':api('/api/backup',{'project':colored})}))
    assert sewing(restored['preview'])==sewing(final['preview'])
    # Every color file is read independently and then through the new importer.
    formats={}
    for fmt in ('edr','col','inf','txt'):
        url=api('/api/export-format',{'id':final['id'],'format':fmt})['url'];file=(DATA / 'exports')/Path(url).name
        imported=read('colors.'+fmt,file.read_bytes());assert [t['color'] for t in imported]==[t['color'] for t in sequence]
        if fmt=='txt':assert imported==sequence
        if fmt=='inf':assert imported[1]['name']=='Café gold'
        formats[fmt]=len(imported)
    reject('/api/thread-colors',{'project':p,'colors':rows},'4 thread steps')
    reject('/api/thread-colors',{'project':{**p,'layers':[{**p['layers'][0],'locked':True}]},'colors':rows},'Unlock')
    # Original font geometry, multicolor satin recipe and cutting needles.
    satin={'id':'satin','type':'path','name':'Satin','x':20,'y':35,'width':60,'height':8,'color':'#416580','stitch':'satin','spacing':.4,'satinCenter':True,
       'contours':[{'closed':False,'nodes':[{'x':0,'y':y,'in':[0,y],'out':[.3,y]},{'x':1,'y':y,'in':[.7,y],'out':[1,y]}]} for y in [0,1]],
       'multicolorSatin':{'bands':[{'color':'#416580','width':20,'blend':20},{'color':'#b96548','width':20,'blend':20},{'color':'#e9c878','width':20,'blend':0}], 'seed':'example'}}
    sp={**p,'layers':[satin]};sr=api('/api/thread-colors',{'project':sp,'colors':rows});so=export(sp)
    assert sr['preview']['segments']==so['preview']['segments']
    assert 'Café' not in sr['asset']['svg'] # names are PES metadata, never geometry
    font={'font':'medium_font','text':'INK','scale':80,'align':'center'};f=api('/api/lettering',font)
    fp={**p,'layers':[{'id':'letters','type':'text','name':'INK','x':20,'y':35,'width':f['width'],'height':f['height'],'lettering':font,'color':'#416580','stitch':'original'}]}
    fr=api('/api/thread-colors',{'project':fp,'colors':[rows[0]]});fo=export(fp)
    assert fr['preview']['segments']==fo['preview']['segments']
    cp={**p,'layers':[rectangle(id='cut',width=20,height=15,x=30,y=40,stitch='running',color='#416580')]}
    cr=api('/api/thread-colors',{'project':cp,'colors':[{**rows[0],'cutworkNeedle':2}]})
    cut=export({**cp,'layers':[cr['layer']],'threadBook':cr['threadBook']});assert cut['cutwork'] and cut['preview']['threads'][0]['name']=='Cut 2'
    re=api('/api/thread-colors',{'project':{**cp,'layers':[cr['layer']]}});assert re['colors'][0]['cutworkNeedle']==2
    api('/api/thread-colors',{'project':{**cp,'layers':[cr['layer']]},'colors':re['colors']})
    # Persist a small example for browser acceptance checks, not user artwork.
    api('/api/save',{'project':{**p,'id':'thread-color-controls-example','name':'Thread color controls example'}})
    (DATA / 'thread-colors-example.txt').write_text('Thread Order\n'+''.join(f'{i+1} {t["name"]} #{t["number"]} - {t["brand"]} ({t["color"]})\n' for i,t in enumerate(sequence)),encoding='utf-8')
    report={'result':'passed','palette':'mixed brands, numeric names, Unicode, update and GPL round trip','formats':formats,
      'steps':4,'stitches':final['preview']['stitches'],'commandsAndGeometry':'exact match including origin, frame-out, trims and stop',
      'backup':'exact match','satinStitches':sr['preview']['stitches'],'letteringStitches':fr['preview']['stitches'],'cutwork':'needle retained; compatible export required'}
    (DATA / 'threadwork-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
