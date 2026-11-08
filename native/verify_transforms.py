"""Installed transforms: actual fill directions, commands, helpers and backups."""
import copy,io,json,math
from pathlib import Path
import server as s
from operations import operate
from verify_native import rectangle
from digitizing import inkex,geometry
from transforms import transform_helper
import preferences

def run(layers,helpers=(),**params):
    return operate({'tool':'transform_elements','layers':layers,'helpers':list(helpers),'params':{'rotate':30,'flip-horizontally':False,'flip-vertically':False,'followAngles':True,'keepSource':False,**params}},s)
def paths(result):return [(e,path,style) for e,path,style in geometry(s.build_svg({'version':1,'layers':result['layers']})) if not e.get('{'+s.INK+'}connection-start')]
def angle(result,key='angle'):return float(paths(result)[0][0].get('{'+s.STITCH+'}'+key))
def stitch_angle(plan):
    bins={}
    for x0,y0,x1,y1,_ in plan['segments']:
        dx,dy=x1-x0,y1-y0;length=math.hypot(dx,dy)
        if length<2:continue
        a=round(math.degrees(math.atan2(dy,dx)))%180;bins[a]=bins.get(a,0)+length
    return max(bins,key=bins.get)

base=rectangle(id='transform-fill',name='Fill with stitch directions',x=30,y=35,width=30,height=20,radius=0,angle=25,underlay=False,groupId='transform-group',entry=[.1,.2],exit=[.8,.9],stopAfter=True)
hidden={'id':'transform-hidden-guide','name':'Hidden guide','type':'path','role':'guide-line','helperTarget':base['id'],'x':32,'y':38,'width':20,'height':10,'rotation':12,'stitch':'running','color':'#9453b1','points':[[0,0],[1,1]],'visible':False}
original=copy.deepcopy([base,hidden]);rotated=run([base],[hidden]);assert [base,hidden]==original
assert abs(angle(rotated)+5)<1e-7 and stitch_angle(rotated['preview']) in (4,5,6)
assert rotated['layers'][0]['id']==base['id'] and rotated['layers'][0]['groupId']=='transform-group'
assert rotated['layers'][1]['visible'] is False and rotated['layers'][1]['helperTarget']==base['id']
center=rotated['center'];matrix=inkex.Transform(f'rotate(30,{center[0]},{center[1]})')
assert math.dist(center,[45,45])<.002,center
root=inkex.load_svg(io.BytesIO(s.build_svg({'version':1,'layers':rotated['layers']}))).getroot()
use=next(e for e in root.iter() if e.tag=='{'+s.SVG+'}use' and 'starting_point' in e.get('{http://www.w3.org/1999/xlink}href',''))
actual=use.composed_transform().apply_to_point((float(use.get('x')),float(use.get('y'))));expected=matrix.apply_to_point((33,39))
assert math.dist(actual,expected)<.002,(actual,expected)
assert paths(rotated)[0][0].get('{'+s.STITCH+'}stop_after').lower()=='true'
tail={'id':'transform-tail','name':'After the pause','type':'path','x':80,'y':80,'width':5,'height':.2,'points':[[0,0],[1,0]],'color':'#416580','stitch':'running'}
with_tail=preferences.preview({'project':{'version':1,'layers':rotated['layers']+[tail]},'settings':preferences.effective()},s)['preview']
assert with_tail['stops']==1
fixed=run([base],followAngles=False);assert angle(fixed)==25 and stitch_angle(fixed['preview']) in (154,155,156)
underlay={**base,'underlay':True,'advanced':{'fill_underlay_angle':'10 -40'}}
multi=run([underlay],**{'flip-horizontally':True});node=paths(multi)[0][0]
assert float(node.get('{'+s.STITCH+'}angle'))==5
assert node.get('{'+s.STITCH+'}fill_underlay_angle')=='20 70'
both=run([base],**{'flip-horizontally':True,'flip-vertically':True});assert abs(angle(both)+5)<1e-8
project={'version':1,'id':'transform-example','name':'Stitch-direction transform example','fabric':'#faf7f0','grid':True,'snap':True,'layers':original}
s.write_atomic(s.DATA/'projects/transform-example.json',project)
project.update(id='transform-result-example',name='Rotated stitch-direction example',layers=rotated['layers'])
s.write_atomic(s.DATA/'projects/transform-result-example.json',project)
backup=s.portable_project(project);restored=s.restore_project({'project':backup});assert s.build_svg(restored)==s.build_svg(project)
for bad in [[{**base,'locked':True}], [{**base,'visible':False}]]:
    try:run(bad)
    except ValueError:pass
    else:raise AssertionError('Protected source accepted')
try:run([base],[{**hidden,'locked':True}])
except ValueError:pass
else:raise AssertionError('Protected helper accepted')
report={'status':'passed','followedAngle':angle(rotated),'fixedAngle':angle(fixed),'rotatedPESDirection':stitch_angle(rotated['preview']),'fixedPESDirection':stitch_angle(fixed['preview']),'underlayAngles':node.get('{'+s.STITCH+'}fill_underlay_angle'),'entryPositionFollows':True,'hiddenGuideRetained':True,'sourceUnchanged':True,'identityAndGroupPreserved':True,'portableRoundTripExact':True,'stopsBeforeNextThread':with_tail['stops']}
s.write_atomic(s.DATA/'transform-verification.json',report);print(json.dumps(report,indent=2),flush=True)
