"""Opt-in manual finishing: retain needle paths, leave a few locked spot floats.

These are exposed thread floats, never claimed to be hidden travel. They must
be trimmed at both ends after sewing. Every retained spot anchor stays intact.
"""
import copy,hashlib,json,math,tempfile
from collections import Counter
from pathlib import Path
from lxml import etree as ET
from shapely.geometry import LineString,Point

MAX_LENGTH=4
MAX_FLOATS=5

def targets(project,s):
    from covered_details import dense
    from components import path_polygon,world_path
    waves={l.get('groupId') for l in project['layers'] if l.get('fillMethod')=='wave_fill' and l.get('visible',True) and not l.get('locked')}
    result={}
    for i,l in enumerate(project['layers']):
        if not l.get('groupId') or l.get('groupId')not in waves or not dense(l) or l.get('visible',True)is False:continue
        if any(h.get('helperTarget')==l['id']for h in project['layers']):continue
        covers=[c for c in project['layers'][:i]if c.get('groupId')==l['groupId'] and dense(c) and c['color']!=l['color'] and c.get('visible',True)]
        if not covers:continue
        outline=path_polygon(world_path(l,s));cover=max(covers,key=lambda c:path_polygon(world_path(c,s)).area);shape=path_polygon(world_path(cover,s))
        if outline.geom_type!='MultiPolygon' or outline.area>shape.area*.35 or outline.difference(shape.buffer(.04)).area>.01:continue
        result[i]={'id':l['id'],'name':l.get('name','Wave cap spots'),'coverId':cover['id'],'bounds':list(shape.bounds),'shape':shape.buffer(.2)}
    return result

def locked(points,incoming):
    # The installed plan compiler generated these tie walks. Repeated outer
    # and return points distinguish them from ordinary fill/bean geometry.
    p=points[:5] if incoming else points[-4:]
    if len(p)<(5 if incoming else 4) or any(q[3]!=-1 for q in p):return False
    same=lambda a,b:math.dist(a[:2],b[:2])<.00001
    if incoming:return same(p[0],p[4]) and same(p[1],p[3]) and math.dist(p[0][:2],p[2][:2])>.3
    return same(p[0],p[2]) and math.dist(p[0][:2],p[1][:2])>.15

def apply(blocks,project,s):
    from sewing_optimizer_geometry import sections
    eligible=targets(project,s);candidates=[]
    for bi,b in enumerate(blocks):
        spans=sections(b['points'])
        for i,(a,z)in enumerate(zip(spans,spans[1:])):
            sa={p[3]for p in a['points']if p[3]>=0};sz={p[3]for p in z['points']if p[3]>=0}
            if sa!=sz or len(sa)!=1 or next(iter(sa))not in eligible:continue
            owner=next(iter(sa));before=a['points'][-1];after=z['points'][0];length=math.dist(before[:2],after[:2])
            if not .25<=length<=MAX_LENGTH or not any(p[2]=='TRIM'for p in a['after']):continue
            if any(p[2]not in ('TRIM','JUMP')for p in a['after']):continue
            if not locked(a['points'],False) or not locked(z['points'],True):continue
            if not eligible[owner]['shape'].covers(LineString([before[:2],after[:2]])):continue
            candidates.append({'block':bi,'span':i,'source':owner,'from':before[:2],'to':after[:2],'length':length,
                'layerId':eligible[owner]['id'],'name':eligible[owner]['name'],'coverId':eligible[owner]['coverId'],'capBoundsWorld':eligible[owner]['bounds']})
    selected=sorted(sorted(candidates,key=lambda c:(c['length'],c['block'],c['span']))[:MAX_FLOATS],key=lambda c:(c['block'],c['span']))
    chosen={(c['block'],c['span'])for c in selected};result=copy.deepcopy(blocks)
    for bi,b in enumerate(result):
        spans=sections(b['points']);prefix=[]
        for p in b['points']:
            if p[2]=='STITCH':break
            prefix.append(p)
        out=prefix
        for i,a in enumerate(spans):
            out.extend(a['points'])
            if (bi,i)not in chosen:out.extend(a['after'])
            # Omit only this TRIM/JUMP. The next original needle position forms
            # one long thread float, without inserting penetrations in the gap.
        b['points']=out
    for n,c in enumerate(selected,1):c['number']=n
    return result,{'floats':selected,'floatCount':len(selected),'manualTrimEnds':2*len(selected),'maxLength':MAX_LENGTH,
        'anchorsRetained':True,'manualFinishingRequired':True}

def needle_sequence(p):
    thread=0;out=[]
    for x,y,c in p['commands']:
        if c==p['commandTypes']['color']:thread+=1
        elif c==p['commandTypes']['stitch']:out.append((thread,round(x*10),round(y*10)))
    return out

def nonzero(p):return [tuple(e)for e in p['segments']if math.dist(e[:2],e[2:4])>.00001]

def finished_preview(before,after):
    """Remove only the documented floats from a machine readback preview."""
    available=Counter(nonzero(before));clean=[];floats=[]
    for e in after['segments']:
        if math.dist(e[:2],e[2:4])<.00001:continue
        key=tuple(e)
        if available[key]:available[key]-=1;clean.append(e)
        else:floats.append(e)
    return {**after,'segments':clean},floats,not any(available.values())

def validate(root,source,s):
    report=json.loads(root.get('data-manual-wave-snips','null'))
    if not report or not report['floatCount']:return
    from sewing_optimizer import machine_metrics
    baseline=copy.deepcopy(source);baseline['sewingOptimization'].pop('manualWaveSnips',None)
    before_svg=s.build_svg(baseline,sewing=True);after_svg=ET.tostring(root)
    digest=hashlib.sha256(b'manual-wave-readback-v1'+before_svg+after_svg).hexdigest();cache=s.DATA/'cache'/('manual-wave-readback-'+digest+'.json')
    if cache.exists():result=json.loads(cache.read_text())
    else:
        previews=[]
        with s.ENGINE_LOCK,tempfile.TemporaryDirectory(prefix='manual-wave-readback-') as tmp:
            for name,raw in [('before',before_svg),('after',after_svg)]:
                path=Path(tmp)/(name+'.svg');path.write_bytes(raw);pes=Path(tmp)/(name+'.pes')
                pes.write_bytes(s.run([s.ENGINE,'--extension=output','--format=pes','--version=6',str(path)],240,headless=True))
                previews.append(s.stitch_data(pes,True))
        before,after=map(machine_metrics,previews);clean,edges,no_missing=finished_preview(*previews)
        exact=needle_sequence(previews[0])==needle_sequence(previews[1])
        same_threads=previews[0]['threads']==previews[1]['threads']
        accepted=exact and same_threads and no_missing and len(edges)==report['floatCount'] and before['cuts']-after['cuts']==len(edges) and previews[0]['stops']==previews[1]['stops']
        floats=[]
        for old,edge in zip(report['floats'],edges):floats.append({**old,'pesFrom':edge[:2],'pesTo':edge[2:4],'thread':edge[4],'length':round(math.dist(edge[:2],edge[2:4]),3)})
        result={'accepted':accepted,'before':before,'after':after,'needleSequenceExact':exact,'finishedStitchesExact':no_missing,
            'floats':floats,'floatCount':len(floats),'manualTrimEnds':2*len(floats),'manualFinishingRequired':True,'anchorsRetained':True}
        s.write_atomic(cache,result)
    if not result['accepted']:
        old=s.xml(before_svg)
        for child in list(root):root.remove(child)
        root.attrib.clear();root.attrib.update(old.attrib)
        for child in old:root.append(copy.deepcopy(child))
    root.set('data-manual-wave-snips',json.dumps(result))

def guide_svg(preview,report):
    """Portable numbered front-side cleanup map, generated for this export."""
    import html,statistics
    def f(n):return f'{n:.3f}'
    chunks=[];current=None;d=[]
    for a,b,x,y,t in preview['segments']:
        if t!=current:
            if d:chunks.append('<path stroke="'+preview['threads'][current]['color']+'" d="'+' '.join(d)+'"/>')
            d=[];current=t
        d.append(f'M{f(a)},{f(b)}L{f(x)},{f(y)}')
    if d:chunks.append('<path stroke="'+preview['threads'][current]['color']+'" d="'+' '.join(d)+'"/>')
    marks=[];groups={};labels=[]
    routes=[LineString([c['pesFrom'],c['pesTo']])for c in report['floats']]
    for c in report['floats']:
        a,b=c['pesFrom'],c['pesTo'];x,y=(a[0]+b[0])/2,(a[1]+b[1])/2
        length=math.dist(a,b);nx,ny=-(b[1]-a[1])/length,(b[0]-a[0])/length
        choice=None
        for distance in (1.5,2.1,2.7,3.3):
            for vx,vy in ((nx,ny),(-nx,-ny),(1,0),(-1,0),(0,1),(0,-1)):
                candidate=Point(x+vx*distance,y+vy*distance)
                if all(candidate.distance(line)>.95 for line in routes) and all(candidate.distance(old)>1.5 for old in labels):choice=candidate;break
            if choice is not None:break
        if choice is None:choice=Point(x+nx*3.3,y+ny*3.3)
        labels.append(choice);lx,ly=choice.x,choice.y
        ends=''.join(f'<circle cx="{f(q[0])}" cy="{f(q[1])}" r=".19" fill="none" stroke="#bd6700" stroke-width=".11"/>'for q in (a,b))
        marks.append(f'<path d="M{f(a[0])},{f(a[1])}L{f(b[0])},{f(b[1])}" stroke="#e39517" stroke-width=".25" stroke-dasharray=".45 .2" fill="none"/>{ends}<path d="M{f(x)},{f(y)}L{f(lx)},{f(ly)}" stroke="#77511b" stroke-width=".08"/><circle cx="{f(lx)}" cy="{f(ly)}" r=".65" fill="#ffdc82" stroke="#573b18" stroke-width=".1"/><text x="{f(lx)}" y="{f(ly+.31)}" text-anchor="middle" font-family="sans-serif" font-size=".9" font-weight="bold" fill="#35260f">{c['number']}</text>')
        groups.setdefault(c['coverId'],[]).append(c)
    dx=statistics.median(c['pesFrom'][0]-c['from'][0]for c in report['floats']);dy=statistics.median(c['pesFrom'][1]-c['from'][1]for c in report['floats'])
    definitions='<defs><g id="stitches" fill="none" stroke-width=".2" stroke-linecap="round">'+''.join(chunks)+'</g><g id="marks">'+''.join(marks)+'</g></defs>'
    serial=0
    def window(x,y,w,h,view):
        nonlocal serial
        serial+=1;key='snip-clip-'+str(serial)
        return f'<defs><clipPath id="{key}"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath></defs><g clip-path="url(#{key})"><svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="'+ ' '.join(f(n)for n in view)+'"><use href="#stitches"/><use href="#marks"/></svg></g>'
    n=report['floatCount'];bounds=preview['bounds'];full=[bounds[0]-2,bounds[1]-2,preview['width']+4,preview['height']+4]
    out=f'<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1330" viewBox="0 0 1800 1330">{definitions}<rect width="1800" height="1330" fill="#faf7ee"/><g font-family="sans-serif" fill="#173f38"><text x="40" y="60" font-size="35">Manual float cleanup map</text><text x="40" y="102" font-size="23">{n} marked cream floats · trim BOTH ENDS after sewing · leave the stitched spot anchors intact</text><rect x="30" y="145" width="680" height="1000" rx="16" fill="white"/>'+window(40,160,660,970,full)
    y=170
    for group in groups.values():
        c=group[0];a,b,x,z=c['capBoundsWorld'];view=[a+dx-1,b+dy-1,x-a+2,z-b+2]
        title=html.escape(c['name'].replace(' · spots',''));ids=', '.join(str(c['number'])for c in group)
        out+=f'<text x="750" y="{y}" font-size="25">{title} · floats {ids}</text><rect x="730" y="{y+20}" width="1030" height="390" rx="16" fill="white"/>'+window(740,y+30,1010,370,view)
        y+=465
    out+='<text x="40" y="1200" font-size="24">1. Lift each marked cream float clear of the Wave stitches. Trim the float at both ends.</text><text x="40" y="1240" font-size="24">2. Remove the loose thread; retain the small anchor stitches on the spots. Inspect the reverse.</text><text x="40" y="1285" font-size="21" fill="#617267">Numbers follow sewing order. The PES intentionally includes these floats; the finished texture matches after cleanup.</text></g></svg>'
    return out
