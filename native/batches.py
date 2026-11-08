"""Persistent native lettering/template and saved-design export batches."""
import copy
import preferences
import json
import math
from pathlib import Path
import re
import threading
import time
import unicodedata
import uuid
import zipfile
import fontlibrary as fl
from interchange import OUTPUTS,export_format,print_sheet
from digitizing import curved_lettering,curve_frame

LOCK=threading.RLock()
LIVE=set()
CANCEL=set()


def folder(key,s):return s.DATA/'batches'/s.safe_id(key)


def entries(text,separator):
    if not isinstance(text,str) or len(text)>50000:raise ValueError('Enter up to 128 names or multiline entries.')
    text=unicodedata.normalize('NFC',text.replace('\r\n','\n').replace('\r','\n').lstrip('\ufeff'))
    mode=separator.get('mode') if isinstance(separator,dict) else separator
    token=separator.get('value') if isinstance(separator,dict) else separator
    if mode=='lines':parts=text.split('\n')
    elif mode=='paragraphs':parts=re.split(r'\n[ \t]*\n',text)
    elif isinstance(token,str) and 1<=len(token)<=32:parts=text.split(token)
    else:raise ValueError('Choose a line break, blank line, or custom entry separator.')
    parts=[p.strip() for p in parts if p.strip()]
    if not 1<=len(parts)<=128:raise ValueError('Use 1–128 entries per batch.')
    if any(len(p)>180 or len(p.splitlines())>12 for p in parts):raise ValueError('Each entry can contain up to 180 characters on 12 lines.')
    return parts


def plan(data,s):
    mode=data.get('mode');formats=data.get('formats',['pes'])
    if not isinstance(formats,list) or not formats or len(formats)>30 or any(f not in OUTPUTS|{'png'} for f in formats):raise ValueError('Choose supported batch output formats.')
    config={'mode':mode,'formats':list(dict.fromkeys(formats)),'name':str(data.get('name') or 'Embroidery batch')[:100],'embroiderySettings':preferences.new_document(s)}
    tasks=[]
    if mode=='lettering':
        texts=entries(data.get('text'),data.get('separator','lines'));settings=data.get('lettering')
        if not isinstance(settings,dict):raise ValueError('Choose the lettering settings.')
        font=fl.get_font(settings.get('font'),s)
        common=s.lettering_settings({**settings,'text':fl.probe_text(font)});common.pop('text')
        template=copy.deepcopy(data.get('template'));target=data.get('target');guide=data.get('guide')
        if template is not None:
            if not isinstance(template,dict) or template.get('version')!=1:raise ValueError('Choose the current design as a template.')
            template=preferences.freeze(template)
            layer=next((l for l in template.get('layers',[]) if l.get('id')==(guide or target)),None)
            if guide:
                if target or layer is None or layer.get('type') not in ('path','rectangle','ellipse'):raise ValueError('Choose one continuous guide path for batch lettering.')
            else:
                if layer is None or not (layer.get('type')=='text' or layer.get('curveSource')):raise ValueError('Choose a text or curved-lettering layer to replace.')
                if layer.get('visible') is False:raise ValueError('Choose a visible lettering layer for the template.')
        elif target or guide:raise ValueError('Include the template design for this lettering layer or guide.')
        anchor=data.get('anchor','center');vertical=data.get('verticalAnchor','center')
        if anchor not in ('left','center','right') or vertical not in ('top','center','bottom'):raise ValueError('Choose how replacement text stays positioned.')
        position=data.get('pathPosition','center');path_vertical=data.get('pathVertical','baseline');reverse=data.get('reverseGuide',False)
        if position not in ('left','center','right','stretch') or path_vertical not in ('top','baseline','bottom') or type(reverse) is not bool:raise ValueError('Choose valid lettering-along-path options.')
        config.update(lettering=common,anchor=anchor,verticalAnchor=vertical,color=s.color(data.get('color','#203f38')),preserveFontColors=bool(data.get('preserveFontColors',False)),target=target,guide=guide,template=template,pathPosition=position,pathVertical=path_vertical,reverseGuide=reverse)
        for text in texts:tasks.append({'name':text.replace('\n',' / '),'text':text})
    elif mode=='projects':
        ids=data.get('projects',[])
        if not isinstance(ids,list):raise ValueError('Choose saved projects to export.')
        for key in dict.fromkeys(ids):
            p=s.DATA/'projects'/(s.safe_id(key)+'.json')
            if not p.exists():raise ValueError('A selected project is no longer available.')
            value=preferences.freeze(json.loads(p.read_text()));tasks.append({'name':value.get('name','Untitled'),'project':value})
        if data.get('current') is not None:
            p=copy.deepcopy(data['current'])
            if not isinstance(p,dict) or p.get('version')!=1:raise ValueError('The current project is invalid.')
            tasks.append({'name':p.get('name','Current design'),'project':preferences.freeze(p)})
        if not 1<=len(tasks)<=128:raise ValueError('Choose 1–128 designs per batch.')
    else:raise ValueError('Choose batch lettering or saved-design exports.')
    return config,tasks


def anchored(old,w,h,horizontal,vertical):
    ax={'left':0,'center':.5,'right':1}[horizontal]-.5;ay={'top':0,'center':.5,'bottom':1}[vertical]-.5
    angle=math.radians(old.get('rotation',0));dx=ax*(old['width']-w);dy=ay*(old['height']-h)
    return old['x']+(old['width']-w)/2+math.cos(angle)*dx-math.sin(angle)*dy,old['y']+(old['height']-h)/2+math.sin(angle)*dx+math.cos(angle)*dy



def design(task,config,s):
    if config['mode']=='projects':return copy.deepcopy(task['project'])
    settings={**config['lettering'],'text':task['text']};rendered=s.lettering(settings)
    if rendered['width']>100 or rendered['height']>100:raise ValueError('This entry exceeds the PP1 hoop at the chosen font scale. Reduce the scale or use multiple lines.')
    p=copy.deepcopy(config.get('template')) or dict(version=1,layers=[],fabric='#f8f5ee',grid=True,snap=True,embroiderySettings=preferences.validate(config.get('embroiderySettings')))
    old=next((l for l in p['layers'] if l['id']==config.get('target')),None)
    base=copy.deepcopy(old.get('curveSource',{}).get('textLayer',old)) if old else dict(id=uuid.uuid4().hex,type='text',x=50,y=50,width=0,height=0,rotation=0,visible=True)
    x,y=anchored(base,rendered['width'],rendered['height'],config['anchor'],config['verticalAnchor']) if old else ((100-rendered['width'])/2,(100-rendered['height'])/2)
    base.update(type='text',lettering=rendered['settings'],name=task['name'],color=config['color'],preserveFontColors=config['preserveFontColors'],width=rendered['width'],height=rendered['height'],x=x,y=y,visible=True,locked=False)
    if config.get('guide') or old and old.get('curveSource'):
        if old:
            original_recipe=copy.deepcopy(old['curveSource'])
            for k in ('textLayer','guideLayer'):original_recipe[k].update(locked=False,visible=True)
            reference=original_recipe.get('frame') or curved_lettering(original_recipe,s)['layer'];recipe=copy.deepcopy(original_recipe)
        else:recipe={'guideLayer':copy.deepcopy(next(l for l in p['layers'] if l['id']==config['guide']))}
        recipe.update(textLayer=base,position=config['pathPosition'],vertical=config['pathVertical'],reverse=config['reverseGuide']);recipe['guideLayer'].update(locked=False,visible=True)
        generated=curved_lettering(recipe,s)['layer']
        result={**(old or {}),**generated}
        if old:result.update(id=old['id'],**curve_frame(old,reference,generated))
        for key in ('trimAfter','stopAfter','groupId','entry','exit','routeStart','routeEnd'):
            if old and key in old:result[key]=old[key]
        for l in p['layers']:
            if l['id']==base['id']:l.update({**base,'visible':False})
            if l['id']==config.get('guide'):l['visible']=False
    else:result=base
    if old:p['layers'][p['layers'].index(old)]=result
    else:p['layers'].append(result)
    p.update(id=uuid.uuid4().hex,name=(config['name']+' · '+task['name'])[:120])
    # A variant is an ordinary editable design, not a source glyph edit.
    p.pop('fontGlyph',None)
    return p


def status(key,s):
    with LOCK:
        value=json.loads((folder(key,s)/'status.json').read_text())
        if value['state'] in ('queued','working') and key not in LIVE:
            value.update(state='interrupted',message='The service restarted. Continue this batch to keep completed designs and finish the rest.')
            for row in value['items']:
                if row['state']=='working':row['state']='paused'
        return value


def listing(s):
    parent=s.DATA/'batches';parent.mkdir(exist_ok=True)
    result=[]
    for p in parent.glob('*/status.json'):
        v=status(p.parent.name,s);result.append({k:v[k] for k in ('id','name','created','state')})
    return sorted(result,key=lambda v:v['created'],reverse=True)[:30]


def enqueue(key,s):
    with s.JOBS_LOCK:
        if sum(j['state'] in ('queued','working') for j in s.JOBS.values())>=3:raise ValueError('Wait for a current preview or batch to finish.')
        s.JOBS[key]={'state':'queued','created':time.time()}
    LIVE.add(key);CANCEL.discard(key);s.POOL.submit(generate,key,s)


def start(data,s):
    config,tasks=plan(data,s);key=uuid.uuid4().hex;path=folder(key,s)
    with LOCK:
        path.mkdir(parents=True)
        s.write_atomic(path/'config.json',config)
        for i,task in enumerate(tasks):s.write_atomic(path/(str(i)+'-input.json'),task)
        s.write_atomic(path/'status.json',dict(id=key,name=config['name'],created=time.time(),mode=config['mode'],state='queued',message='Waiting for Ink/Stitch…',items=[{'index':i,'name':t['name'],'state':'pending','ready':False} for i,t in enumerate(tasks)]))
        try:enqueue(key,s)
        except ValueError:
            v=status(key,s);v.update(state='interrupted',message='The queue is full. Continue this batch when a slot is available.');s.write_atomic(path/'status.json',v);raise
    return {'id':key}


def resume(key,s):
    with LOCK:
        value=status(key,s)
        if key in LIVE:return {'id':key}
        if value['state']=='done':return {'id':key}
        enqueue(key,s);value.update(state='queued',message='Continuing unfinished designs…',bundle=None);s.write_atomic(folder(key,s)/'status.json',value)
    return {'id':key}


def cancel(key,s):
    with LOCK:
        value=status(key,s)
        if key in LIVE:CANCEL.add(key)
        return value


def item(key,index,s):
    value=status(key,s)
    if not str(index).isdigit() or not 0<=int(index)<len(value['items']) or not value['items'][int(index)]['ready']:raise ValueError('Choose a completed design.')
    return json.loads((folder(key,s)/(str(int(index))+'-result.json')).read_text())


def save(key,s):
    value=status(key,s);ids=[]
    for row in value['items']:
        if not row['ready']:continue
        p=item(key,row['index'],s)['design'];target=s.DATA/'projects'/(s.safe_id(p['id'])+'.json')
        if not target.exists():s.write_atomic(target,p)
        ids.append(p['id'])
    if not ids:raise ValueError('Wait for at least one completed design.')
    return {'ids':ids}


class Cancelled(Exception):pass


def generate(key,s):
    path=folder(key,s);config=json.loads((path/'config.json').read_text())
    def update(**values):
        with LOCK:
            v=json.loads((path/'status.json').read_text());v.update(values);s.write_atomic(path/'status.json',v)
    def check():
        with LOCK:
            if key in CANCEL:raise Cancelled()
    try:
        with s.JOBS_LOCK:s.JOBS[key]['state']='working'
        rows=status(key,s)['items'];update(state='working',message='Preparing the batch…')
        for i,row in enumerate(rows):
            check()
            if row['state']=='done':continue
            row.update(state='working',error='');update(items=rows,message=f'Design {i+1} / {len(rows)}: {row["name"]}')
            try:
                task=json.loads((path/(str(i)+'-input.json')).read_text());resultfile=path/(str(i)+'-result.json')
                if resultfile.exists():result=json.loads(resultfile.read_text())
                else:
                    p=design(task,config,s);p['id']=uuid.uuid4().hex;export_id=uuid.uuid4().hex
                    with s.JOBS_LOCK:s.JOBS[export_id]={'state':'queued','created':time.time()}
                    s.export_job(export_id,p)
                    with s.JOBS_LOCK:job=s.JOBS.pop(export_id)
                    if job['state']!='done':raise ValueError(job.get('message','This design could not be exported.'))
                    r=job['result'];result={'design':p,'export':r,'files':{'pes':r['pes'],'source.svg':r['svg'],'project.json':r['project'],'threads.txt':r['threadlist']}}
                    s.write_atomic(resultfile,result)
                row.update(ready=True,stitches=result['export']['preview']['stitches']);update(items=rows)
                problems=[]
                for fmt in config['formats']:
                    check()
                    if fmt in result['files']:continue
                    try:result['files'][fmt]=export_format({'id':result['export']['id'],'format':fmt},s)['url'];s.write_atomic(resultfile,result)
                    except Exception as exc:problems.append(fmt.upper()+': '+str(exc))
                row.update(state='partial' if problems else 'done',error='; '.join(problems))
            except Cancelled:raise
            except Exception as exc:row.update(state='error',error=str(exc))
            update(items=rows)
        check();update(message='Packing completed designs and the batch report…')
        archive=s.DATA/'exports'/(key+'-batch.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('batch-report.json',json.dumps({'name':config['name'],'formats':config['formats'],'items':rows},ensure_ascii=False,indent=2))
            for row in rows:
                if not row['ready']:continue
                check();r=item(key,row['index'],s);slug=re.sub(r'[^a-zA-Z0-9_-]+','-',row['name']).strip('-')[:50] or 'design';prefix=f'{row["index"]+1:03d}-{slug}'
                for fmt,url in r['files'].items():
                    ext={'source.svg':'svg','project.json':'project.json','threads.txt':'threads.txt','svg':'stitch-plan.svg','txt':'thread-list.txt'}.get(fmt,fmt)
                    z.write(s.DATA/'exports'/Path(url).name,prefix+'/'+slug+'.'+ext)
                z.writestr(prefix+'/'+slug+'-print.html',print_sheet(r['export']['id'],s))
        good=sum(row['ready'] for row in rows);errors=sum(row['state']!='done' for row in rows)
        update(state='partial' if errors else 'done',message=f'{good} / {len(rows)} designs ready'+(f' · {errors} need attention' if errors else ''),bundle='/files/'+archive.name)
    except Cancelled:
        for row in rows:
            if row['state']=='working':row['state']='paused'
        update(state='cancelled',items=rows,message='Cancelled after the current engine operation. Completed designs remain available.')
    except Exception as exc:update(state='error',message=str(exc))
    finally:
        with LOCK:LIVE.discard(key);CANCEL.discard(key)
        terminal=status(key,s)['state']
        with s.JOBS_LOCK:s.JOBS[key]['state']='done' if terminal=='done' else 'error'
