"""Additional installed-engine preparation workflows."""
from verification import DATA
import json,urllib.error,zipfile,io,struct
import pystitch
from pathlib import Path
from verify_native import api,export,rectangle

def main():
 report={};project={'version':1,'id':'preparation-verification','name':'Preparation verification'}
 def op(key,layers,params=None):
  try:r=api('/api/operate',{'tool':key,'layers':layers,'params':params or {}})
  except urllib.error.HTTPError as e:raise AssertionError(e.read().decode())
  assert r['layers'] and r['preview']['stitches']>10
  report[key]={'paths':len(r['layers']),'stitches':r['preview']['stitches'],'colors':len({t['color'] for t in r['preview']['threads']})};print(key,report[key],flush=True);return r
 gradient=rectangle(id='gradient',x=30,y=30,width=30,height=20,radius=0,underlay=False,fillMethod='linear_gradient_fill',gradient={'angle':0,'stops':[{'color':'#123456','offset':0},{'color':'#d4ac59','offset':1}]})
 blocks=op('gradient_blocks',[gradient]);assert len(blocks['layers'])>=2 and report['gradient_blocks']['colors']==2
 assert all(l['originalParams'].get('fill_method')=='tatami_fill' for l in blocks['layers'])
 circle=rectangle(id='cutwork',type='ellipse',x=30,y=30,width=30,height=30,stitch='running',trimAfter=True)
 cut=op('cutwork_segmentation',[circle]);assert report['cutwork_segmentation']['colors']==4
 cut_export=export({**project,'layers':cut['layers']});assert cut_export['cutwork'] and cut_export['cutworkBundle']
 bundle=(DATA / 'exports')/Path(cut_export['cutworkBundle']).name
 with zipfile.ZipFile(bundle) as z:
  names=z.namelist();exp=next(n for n in names if n.endswith('.exp'));inf=next(n for n in names if n.endswith('.inf'));assert exp[:-4]==inf[:-4]
  raw=z.read(inf);count=struct.unpack_from('>I',raw,12)[0];offset=16;charts=[]
  for i in range(count):
   size,index=struct.unpack_from('>HH',raw,offset);assert index==i;description,chart,_=raw[offset+9:offset+size].split(b'\0');charts.append(chart.decode());offset+=size
  assert set(charts)=={'Cut 1','Cut 2','Cut 3','Cut 4'} and offset==len(raw),charts
  stitches=pystitch.read_exp(io.BytesIO(z.read(exp)));assert stitches.count_color_changes()==3
 try:api('/api/export-format',{'id':cut_export['id'],'format':'pes'})
 except urllib.error.HTTPError as e:assert e.code==400
 else:raise AssertionError('Cutwork was offered as ordinary PES')
 report['cutwork_segmentation']['bundle']='EXP + INF, four verified needle labels'
 running=[{'id':f'run{i}','type':'path','name':'Running line','x':20+i*30,'y':40,'width':15,'height':.2,'color':'#203f38','stitch':'running','points':[[0,0],[1,0]],'trimAfter':False} for i in range(2)]
 before=export({**project,'layers':running})['preview'];joined=op('jump_to_stroke',running);assert len(joined['layers'])==3
 assert joined['preview']['jumps']<before['jumps'];report['jump_to_stroke']['jumpsBeforeAfter']=[before['jumps'],joined['preview']['jumps']]
 bow=rectangle(id='bow',type='path',x=30,y=30,width=30,height=30,points=[[0,0],[1,1],[0,1],[1,0]],closed=True,radius=0)
 repaired=op('break_apart',[bow]);assert len(repaired['layers'])==2
 restored=api('/api/restore',{'project':api('/api/backup',{'project':{**project,'layers':blocks['layers']}})})
 assert export(restored)['preview']['stitches']==blocks['preview']['stitches']
 (DATA / 'preparation-verification.json').write_text(json.dumps({'result':'passed','tools':report,'backupRoundTrip':'passed'},indent=2));print('Preparation checks passed.',flush=True)
if __name__=='__main__':main()
