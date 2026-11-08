"""Installed/custom GPL palettes and named threads in the PP1 PES file."""
import studio_runtime
import hashlib
import json
from pathlib import Path
import re
import struct

def parse_palette(raw):
    if not isinstance(raw,str) or not raw.startswith('GIMP Palette') or len(raw)>500000:raise ValueError('Choose a GIMP .gpl thread palette smaller than 500 KB.')
    name='Custom palette';colors=[];details=None
    for line in raw.splitlines():
        if line.startswith('Name:'):name=line[5:].strip().removeprefix('Ink/Stitch:').strip()[:100]
        if line.startswith('# Ink Studio thread: '):
            try:details=json.loads(line.removeprefix('# Ink Studio thread: '))
            except (ValueError,TypeError):details=None
            continue
        m=re.fullmatch(r'\s*(\d+)\s+(\d+)\s+(\d+)\s+(.+?)\s*',line)
        if not m:continue
        rgb=[int(m[i]) for i in (1,2,3)]
        if max(rgb)>255:raise ValueError('Palette RGB channels must be 0–255.')
        label=m[4][:140];parts=label.rsplit(None,1);number=parts[-1] if len(parts)==2 and any(c.isdigit() for c in parts[-1]) else ''
        entry={'color':'#%02x%02x%02x'%tuple(rgb),'name':parts[0] if number else label,'number':number,'brand':name}
        if isinstance(details,dict):
            for key in ('name','number','brand'):
                if isinstance(details.get(key),str) and len(details[key])<=140:entry[key]=details[key]
        details=None;colors.append(entry)
    if not 1<=len(colors)<=5000:raise ValueError('A palette needs 1–5,000 thread colors.')
    return {'key':hashlib.sha256(raw.encode()).hexdigest()[:32],'name':name,'colors':colors,'count':len(colors)}

def palettes(s):
    custom=s.DATA/'palettes';custom.mkdir(exist_ok=True);result=[]
    for p in list(studio_runtime.resource('palettes').glob('*.gpl'))+list(custom.glob('*.gpl')):
        try:r=parse_palette(p.read_text(encoding='utf-8-sig'));r['custom']=p.parent==custom;result.append(r)
        except (ValueError,UnicodeError):continue
    return sorted({p['key']:p for p in result}.values(),key=lambda p:p['name'].lower())

def import_palette(data,s):
    raw=data.get('text','');p=parse_palette(raw);folder=s.DATA/'palettes';folder.mkdir(exist_ok=True)
    (folder/(p['key']+'.gpl')).write_text(raw,encoding='utf-8');return {**p,'custom':True}

def thread_entries(entries,limit=5000):
    if not isinstance(entries,list) or not 1<=len(entries)<=limit:raise ValueError(f'Choose 1–{limit:,} thread colors.')
    result=[]
    for i,t in enumerate(entries):
        if not isinstance(t,dict) or not re.fullmatch(r'#[0-9a-fA-F]{6}',str(t.get('color',''))):raise ValueError(f'Check the color in row {i+1}.')
        row={'color':t['color'].lower()}
        for key in ('name','number','brand'):
            value=t.get(key,'')
            if not isinstance(value,str) or len(value)>140 or any(ord(c)<32 for c in value):raise ValueError(f'Check {key} in row {i+1}; use one line, up to 140 characters.')
            row[key]=value.strip()
        needle=t.get('cutworkNeedle')
        if needle is not None:
            if type(needle)!=int or needle not in (1,2,3,4):raise ValueError('Cutwork needles must be 1–4.')
            row['cutworkNeedle']=needle
        result.append(row)
    return result

def palette_text(name,entries):
    if not isinstance(name,str) or not 1<=len(name.strip())<=100 or any(ord(c)<32 for c in name):raise ValueError('Name the palette on one line, up to 100 characters.')
    rows=['GIMP Palette','Name: Ink/Stitch: '+name.strip(),'Columns: 4','#']
    for t in thread_entries(entries):
        rows.append('# Ink Studio thread: '+json.dumps({k:t[k] for k in ('name','number','brand')},ensure_ascii=False))
        rgb=[int(t['color'][i:i+2],16) for i in (1,3,5)]
        rows.append('%3d %3d %3d\t%s'%(*rgb,' '.join(x for x in [t['name'] or 'Thread',t['number']] if x)))
    return '\n'.join(rows)+'\n'

def save_palette(data,s):
    raw=palette_text(data.get('name'),data.get('colors'));replace=data.get('replaceKey');old=None
    if replace:
        old=s.DATA/'palettes'/(s.safe_id(replace)+'.gpl')
        if not old.is_file():raise ValueError('This custom palette no longer exists. Save a new copy.')
    p=import_palette({'text':raw},s)
    if old and old.stem!=p['key']:old.unlink()
    return {**p,'text':raw}

def inf_bytes(pattern):
    # pystitch 1.0.0 counts Unicode characters in INF record lengths, while
    # writing UTF-8 bytes. Use byte lengths so non-ASCII thread names round-trip.
    records=[]
    for i,t in enumerate(pattern.threadlist):
        details=(t.description or '').encode('utf-8');chart=(t.chart or '').encode('utf-8')
        body=struct.pack('>HBBBH',i,t.get_red(),t.get_green(),t.get_blue(),i+1)+details+b'\0'+chart+b'\0'
        records.append(struct.pack('>H',len(body)+2)+body)
    body=struct.pack('>I',len(records))+b''.join(records)
    return struct.pack('>III',1,8,len(body))+body

def named_pes(encoded,project):
    book=project.get('threadBook',{})
    if not isinstance(book,dict) or len(book)>1000:raise ValueError('Invalid named thread collection.')
    if not book:return encoded
    # Patch only the PES v6 thread table. Re-encoding a decoded pattern can move
    # a STOP when it precedes a color change without an intervening stitch.
    # Retain the entire PEC stream, including its duplicate-color stop encoding.
    if encoded[:8]!=b'#PES0060':raise ValueError('Named threads require a PES version 6 export.')
    offset=struct.unpack_from('<I',encoded,8)[0];pos=16
    def take_string():
        nonlocal pos
        if pos>=len(encoded):raise ValueError('Incomplete PES thread metadata.')
        length=encoded[pos];start=pos;pos+=length+1
        if pos>len(encoded):raise ValueError('Incomplete PES thread metadata.')
        return encoded[start:pos]
    def put_string(value):
        if not isinstance(value,str) or len(value)>140:raise ValueError('Thread names and numbers must be shorter than 140 characters.')
        raw=value.encode('utf-8')[:255].decode('utf-8','ignore').encode('utf-8')
        return bytes([len(raw)])+raw
    for _ in range(5):take_string()
    pos+=36;take_string();pos+=24
    if struct.unpack_from('<HHH',encoded,pos)!=(0,0,0):raise ValueError('Unsupported PES pattern metadata.')
    pos+=6;count=struct.unpack_from('<H',encoded,pos)[0];pos+=2;start=pos;records=[];changed=False
    for _ in range(count):
        record_start=pos;number=take_string();fixed=encoded[pos:pos+8];pos+=8
        name=take_string();brand=take_string();chart=take_string()
        color='#'+fixed[:3].hex();entry=book.get(color)
        if entry is None:records.append(encoded[record_start:pos]);continue
        if not isinstance(entry,dict):raise ValueError('Invalid thread information.')
        records.append(put_string(entry.get('number',''))+fixed+put_string(entry.get('name',''))+put_string(entry.get('brand',''))+chart);changed=True
    if not changed:return encoded
    if pos>offset:raise ValueError('Incomplete PES thread metadata.')
    replacement=b''.join(records);delta=len(replacement)-(pos-start)
    result=bytearray(encoded[:start]+replacement+encoded[pos:]);struct.pack_into('<I',result,8,offset+delta)
    return bytes(result)
