"""Conservative routing of completed engine needle paths, in millimeters.

Never reverse a sewing section or move an overlapping section ahead of its
predecessor. Only replace a cut with a running connector in verified coverage.
"""
import copy,math
from shapely.geometry import LineString,Point
from shapely import wkt
from shapely.ops import unary_union

def distance(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])

def sections(points):
    out=[];current=[];commands=[]
    for p in points:
        if p[2]=='STITCH':
            if commands and current:out.append({'points':current,'after':commands});current=[];commands=[]
            if not current:commands=[]
            current.append(p)
        else:
            commands.append(p)
    if current:out.append({'points':current,'after':commands})
    return out

def metrics(blocks):
    cuts=stitches=0;travel=0;last=None
    for b in blocks:
        for p in b['points']:
            if p[2]=='STITCH':stitches+=1
            elif p[2]=='TRIM':cuts+=1
            elif p[2]=='JUMP' and last is not None:travel+=distance(last,p)
            if p[2] in ('STITCH','JUMP'):last=p
    return {'cuts':cuts,'stitches':stitches,'travelMM':round(travel,2),'threadSteps':len(blocks)}

def optimize(blocks,config):
    masks=[{**m,'shape':wkt.loads(m['mask'])} for m in config['masks']]
    fixed=set(config.get('fixed',[]));result=copy.deepcopy(blocks);bridges=[];moved=0;previous=None
    for block_index,block in enumerate(result):
        spans=sections(block['points'])
        if not spans:continue
        if len(spans)>600:
            previous=spans[-1]['points'][-1];continue
        # Stops are hard barriers. Keep the complete containing block unchanged.
        if any(p[2]=='STOP' for p in block['points']):
            previous=spans[-1]['points'][-1];continue
        for span in spans:
            span['sources']={int(p[3]) for p in span['points'] if len(p)>3 and p[3]>=0}
            coords=[p[:2] for p in span['points']]
            span['footprint']=(LineString(coords) if len(coords)>1 else Point(coords[0])).buffer(.35)
        units=[];unit=[]
        for i,span in enumerate(spans):
            unit.append(i)
            if any(p[2]=='TRIM' for p in span['after']):units.append(unit);unit=[]
        if unit:units.append(unit)
        summaries=[{'sources':set().union(*(spans[i]['sources'] for i in u)),
            'footprint':unary_union([spans[i]['footprint'] for i in u])} for u in units]
        dependencies=[set() for _ in units]
        for j,b in enumerate(summaries):
            for i,a in enumerate(summaries[:j]):
                if (not a['sources'] or not b['sources'] or a['sources']&b['sources'] or
                    (a['sources']|b['sources'])&fixed or a['footprint'].intersects(b['footprint'])):dependencies[j].add(i)
        order=list(range(len(spans)))
        if config['reorder'] and len(units)<=64:
            pending=set(range(len(units)));ordered_units=[];cursor=previous or spans[0]['points'][0]
            while pending:
                available=[i for i in pending if not dependencies[i]&pending]
                pick=min(available,key=lambda i:(distance(cursor,spans[units[i][0]]['points'][0]),i))
                ordered_units.append(pick);pending.remove(pick);cursor=spans[units[pick][-1]]['points'][-1]
            order=[i for u in ordered_units for i in units[u]]
            next_points=result[block_index+1]['points'] if block_index+1<len(result) else []
            exit_point=next((p for p in next_points if p[2]=='STITCH'),None)
            def cost(sequence):
                cursor=previous or spans[0]['points'][0];total=0
                for i in sequence:total+=distance(cursor,spans[i]['points'][0]);cursor=spans[i]['points'][-1]
                if exit_point is not None:total+=distance(cursor,exit_point)
                return total
            # Include the exit to the next color when judging a candidate below
            # at the whole-design level. Never accept a longer local route.
            if cost(order)>cost(list(range(len(spans))))+.00001:order=list(range(len(spans)))
            current=[next(j for j,u in enumerate(units) if u[0]==i) for i in order if any(u[0]==i for u in units)]
            # Improve whole, direction-preserving sections with bounded valid
            # relocations. A greedy nearest neighbor alone can lengthen exits.
            for _ in range(min(40,len(units)*2)):
                best=current;best_cost=cost([i for u in current for i in units[u]])
                for a in range(len(current)):
                    for b in range(len(current)):
                        if a==b:continue
                        candidate=current.copy();candidate.insert(b,candidate.pop(a));positions={u:i for i,u in enumerate(candidate)}
                        changed=current[a]
                        if any(positions[p]>=positions[changed] for p in dependencies[changed]) or any(positions[u]<=positions[changed] for u in candidate if changed in dependencies[u]):continue
                        value=cost([i for u in candidate for i in units[u]])
                        if value<best_cost-.01:best=candidate;best_cost=value
                if best==current:break
                current=best
            order=[i for u in current for i in units[u]]
        moved+=sum(i!=j for j,i in enumerate(order))
        block_sources=set().union(*(a['sources'] for a in spans))
        first=spans[order[0]]['points'][0];output=[[first[0],first[1],'JUMP',-1]]
        for pos,i in enumerate(order):
            span=spans[i];output.extend(span['points'])
            if pos==len(order)-1:
                # Color changes / final trims remain at the end of the block.
                output.extend(spans[-1]['after']);continue
            following=spans[order[pos+1]];a,b=span['points'][-1],following['points'][0]
            sources=span['sources']|following['sources'];length=distance(a,b);safe=None
            coincident=length<=.03
            if config['connect'] and sources and not sources&fixed and coincident:
                safe=True
            elif config['connect'] and sources and not sources&fixed and .001<length<=config['maxBridge']:
                last_source=max(sources)
                covers=[m['shape'] for m in masks if (m['source'] in block_sources and m['color'].lower()==block['color'].lower()) or m['source']>last_source]
                if covers:
                    region=unary_union(covers)
                    # Both needles and the whole thread corridor must have cover.
                    corridor=LineString([a[:2],b[:2]]).buffer(.12,cap_style=1)
                    if region.covers(corridor):safe=corridor
            if safe is not None:
                bridges.append({'from':a[:2],'to':b[:2],'length':length,'coincident':coincident})
                # New points are running stitches, sampled at <=1.2 mm. All
                # original underlay, top stitches and locks are left untouched.
                count=max(1,math.ceil(length/1.2))
                output.extend([[a[0]+(b[0]-a[0])*n/count,a[1]+(b[1]-a[1])*n/count,'STITCH',-1] for n in range(1,count)])
            else:
                if i+1==order[pos+1]:
                    output.extend(span['after']);continue
                if any(p[2]=='TRIM' for p in span['after']):output.append([a[0],a[1],'TRIM',-1])
                # Reordering never creates an untrimmed move between sections.
                elif i+1!=order[pos+1]:output.append([a[0],a[1],'TRIM',-1])
                output.append([b[0],b[1],'JUMP',-1])
        block['points']=output;previous=spans[order[-1]]['points'][-1]
    before=metrics(blocks);after=metrics(result)
    # A local greedy choice can worsen the transition to another color. Fall
    # back to original section order, keeping only verified cut consolidation.
    if config['reorder'] and (after['travelMM']>before['travelMM']+.01 or after['cuts']>before['cuts']):
        return optimize(blocks,{**config,'reorder':False})
    return result,{'before':before,'after':after,'bridges':bridges,'movedSections':moved}
