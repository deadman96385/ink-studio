"""Native positional commands validated in real PES files and SVG imports."""
from verification import DATA
import copy,json,math
from pathlib import Path
import pystitch
from verify_native import api,export,rectangle
from digitizing import from_path,inkex

def pattern(result):return pystitch.read(str(DATA / 'exports')+'/'+Path(result['pes']).name)
def main():
 p={'version':1,'id':'commands-verification','name':'Position controls','layers':[]}
 base=rectangle(id='circle',x=30,y=30,width=30,height=20,radius=0,fillMethod='circular_fill',underlay=False)
 a=export({**p,'layers':[base]})['preview'];b=export({**p,'layers':[{**base,'targetPoint':[.2,.2]}]})['preview']
 assert a['segments']!=b['segments'];print('Circular target changes stitch geometry',flush=True)
 sat={'id':'sat','type':'path','name':'Satin','x':20,'y':30,'width':40,'height':5,'color':'#203f38','stitch':'satin','spacing':.4,'satinCut':[.5,.5],
      'contours':[{'closed':False,'nodes':[{'x':x,'y':y,'in':[x,y],'out':[x,y]} for x in [0,1]]} for y in [0,1]]}
 cut=api('/api/operate',{'tool':'cut_satin','layers':[sat],'params':{}})
 assert len(cut['layers'])==2;print('Satin cut point produced two columns',flush=True)
 runs=[{'id':f'run{i}','type':'path','name':f'Run {i}','x':20+i*20,'y':30,'width':20,'height':.2,'color':'#203f38','stitch':'running','points':[[0,0],[1,0]],'stitchLength':2} for i in range(2)]
 routes=[]
 for reverse in (False,True):
  ls=copy.deepcopy(runs);ls[0 if not reverse else 1]['routeStart']=[0,0] if not reverse else [1,0];ls[1 if not reverse else 0]['routeEnd']=[1,0] if not reverse else [0,0]
  r=api('/api/route',{'kind':'running','layers':ls,'preserveOrder':False,'trim':False,'breakUp':True});routes.append(r['preview'])
 assert routes[0]['segments'][0][0]<routes[1]['segments'][0][0];print('Route commands reverse the starting end',flush=True)
 layers=[rectangle(id='first',x=30,y=30,width=20,height=15,radius=0,stopAfter=True),rectangle(id='second',x=55,y=55,width=10,height=10,radius=0)]
 project={**p,'layers':layers,'origin':[50,50],'frameOut':[80,10]}
 frame=export(project);fp=pattern(frame);stops=[s for s in fp.stitches if s[2]&255==pystitch.STOP]
 assert stops and all(abs(stops[0][i]-[300,-400][i])<=1 for i in (0,1)),stops
 moved=pattern(export({**project,'origin':[45,40]}));assert len(moved.stitches)==len(fp.stitches)
 for old,new in zip(fp.stitches,moved.stitches):
  assert new[2]==old[2] and abs(new[0]-old[0]-50)<=1 and abs(new[1]-old[1]-100)<=1,(old,new)
 print('PES retains the selected origin and frame-out position',flush=True)
 pos=rectangle(id='positions',x=30,y=30,width=30,height=20,radius=0,entry=[.1,.3],exit=[.9,.7],rotation=25,flipX=True)
 ex=export({**p,'layers':[pos]});raw=((DATA / 'exports')/Path(ex['svg']).name).read_text()
 asset=api('/api/import',{'svg':raw,'name':'commands.svg'});imp={'id':'imp','type':'import','asset':asset['key'],'name':'Command SVG','x':25,'y':25,'width':asset['width'],'height':asset['height'],'color':'#d4ac59','stitch':'original','recolor':False}
 exp=api('/api/vector',{'operation':'explode','layers':[imp]})['layers'];assert exp and 'entry' in exp[0] and 'exit' in exp[0]
 ip=export({**p,'layers':[imp]})['preview'];ep=export({**p,'layers':exp})['preview'];assert abs(ep['stitches']-ip['stitches'])<8,(ep['stitches'],ip['stitches'])
 restored=api('/api/restore',{'project':api('/api/backup',{'project':project})});assert restored['origin']==project['origin'] and restored['frameOut']==project['frameOut'];assert pattern(export(restored)).stitches==fp.stitches
 # Node conversion keeps positions fixed in world space when geometry bounds change.
 original={**pos,'targetPoint':[.2,.8],'routeStart':[.5,.5]};nodes=api('/api/vector',{'operation':'nodes','layers':[original]})['layers'][0]
 assert all(k in nodes for k in ('entry','exit','targetPoint','routeStart'))
 def world(l,q):
  a=math.radians(l.get('rotation',0));x=((1-q[0]) if l.get('flipX') else q[0])*l['width']-l['width']/2;y=((1-q[1]) if l.get('flipY') else q[1])*l['height']-l['height']/2
  return[l['x']+l['width']/2+x*math.cos(a)-y*math.sin(a),l['y']+l['height']/2+x*math.sin(a)+y*math.cos(a)]
 for key in ('entry','exit','targetPoint','routeStart'):assert math.dist(world(original,original[key]),world(nodes,nodes[key]))<.001
 # Curved-lettering recipes may refer to imports not otherwise in the layer list.
 nested={**p,'layers':[{**base,'curveSource':{'guideLayer':imp,'textLayer':{**base,'id':'source-text'}}}]}
 backup=api('/api/backup',{'project':nested});assert any(a['key']==imp['asset'] for a in backup['embeddedAssets'])
 restored_nested=api('/api/restore',{'project':backup});guide=restored_nested['layers'][0]['curveSource']['guideLayer'];assert ((DATA / 'assets')/(guide['asset']+'.json')).exists()
 report={'nestedGuideBackup':'passed','result':'passed','circularTarget':[a['stitches'],b['stitches']],'satinCutPaths':len(cut['layers']),'routeStartEnd':'reversed as requested','frameOutMm':[v/10 for v in stops[0][:2]],'originShiftMm':[5,10],'connectedSvgImport':'passed','nodePositions':'preserved','backupRoundTrip':'exact PES commands'}
 (DATA / 'commands-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
