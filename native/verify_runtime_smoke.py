"""Start an isolated editor and verify real files on either Windows or Linux.

Uses a temporary data store and random loopback port, never saved user projects.
Run with the editor's Python: python -X utf8 native/verify_runtime_smoke.py
"""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

import pystitch
import studio_runtime

ROOT = Path(__file__).absolute().parent


def main():
    with tempfile.TemporaryDirectory(prefix='inkstudio-smoke-') as temporary:
        folder = Path(temporary) / 'Designs café with spaces'
        folder.mkdir()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0));port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        instance=uuid.uuid4().hex
        env = dict(os.environ, STUDIO_DATA=str(folder), STUDIO_HOST='127.0.0.1', STUDIO_PORT=str(port), STUDIO_INSTANCE_ID=instance)
        if os.name != 'nt':
            env['XDG_CONFIG_HOME'] = str(folder / 'config')
        settings = {}
        if os.name == 'nt':
            config = Path(os.environ['LOCALAPPDATA']) / 'inkstitch' / 'inkstitch'
            settings = {p:p.read_bytes() if p.exists() else None for p in (config/'settings.json',config/'custom_dirs.json')}
        with (folder / 'server.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT/'server.py')], env=env,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
            job=studio_runtime._WindowsJob(process) if os.name=='nt' else None
            def get(path):
                with urllib.request.urlopen(base+path, timeout=180) as response:return response.read()
            def api(path, data=None):
                req = urllib.request.Request(base+path, data=json.dumps(data).encode() if data is not None else None,
                                             headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req, timeout=180) as response:return json.load(response)
            def export(project):
                job = api('/api/export', {'project':project})
                deadline = time.monotonic()+240
                while time.monotonic()<deadline:
                    state = api('/api/jobs/'+job['id'])
                    if state['state']=='error':raise AssertionError(state)
                    if state['state']=='done':return state['result']
                    time.sleep(.2)
                raise AssertionError('Export timed out')
            try:
                deadline=time.monotonic()+90
                while True:
                    if process.poll() is not None:raise AssertionError((folder/'server.log').read_text(encoding='utf-8',errors='replace'))
                    try:health=api('/api/health');break
                    except (OSError,urllib.error.URLError):
                        if time.monotonic()>deadline:raise
                        time.sleep(.2)
                assert health['ok'] and health['instance']==instance,health
                assert health['runtime']['dataDirectory']==str(folder),health
                assert b'Ink Studio' in get('/'), 'Editor HTML did not load'
                assert b'import ' in get('/app.js'), 'Editor code did not load'
                assert api('/api/formats')['outputs']
                assert api('/api/preferences')['factory']
                fonts=api('/api/fonts');assert any(f['id']=='medium_font' for f in fonts)
                shape={'id':uuid.uuid4().hex,'type':'rectangle','name':'Café shape','x':15,'y':20,'width':30,'height':20,
                       'rotation':0,'radius':0,'color':'#235c48','stitch':'fill','spacing':.4,'angle':45,'stitchLength':3,'underlay':True}
                project={'version':1,'id':uuid.uuid4().hex,'name':'Windows / Linux café','fabric':'#faf7f0','grid':True,'snap':True,'layers':[shape]}
                api('/api/save',{'project':project});saved=api('/api/projects/'+project['id']);assert saved['name']==project['name']
                result=export(project);raw=get(result['pes']);assert raw.startswith(b'#PES0060')
                pes=folder/'readback.pes';pes.write_bytes(raw);pattern=pystitch.read(str(pes));bounds=pattern.bounds()
                assert len(pattern.stitches)>100 and len(pattern.threadlist)==1
                assert abs((bounds[2]-bounds[0])/10-30)<.2 and abs((bounds[3]-bounds[1])/10-20)<.2,bounds
                info=api('/api/element-info',{'project':project})
                assert len(info['elements'])==1 and info['summary'],info
                checked=api('/api/inspect',{'project':project})
                assert checked['preview']['stitches']>100 and not any(f['severity']=='error' for f in checked['findings']),checked
                sparse=copy.deepcopy(project);sparse['layers'][0]['spacing']=.8
                assert export(sparse)['preview']['stitches']<result['preview']['stitches']
                backup=api('/api/backup',{'project':project});restored=api('/api/restore',{'project':backup})
                restored_pattern=folder/'restored.pes';restored_pattern.write_bytes(get(export(restored)['pes']))
                assert pystitch.read(str(restored_pattern)).stitches==pattern.stitches,'Backup changed needle commands'
                lettering=api('/api/lettering',{'font':'medium_font','text':'Ink','scale':80,'align':'center','lineSpacing':0,'letterSpacing':0})
                text={'id':uuid.uuid4().hex,'type':'text','name':'Ink lettering','x':20,'y':20,'width':lettering['width'],'height':lettering['height'],
                      'rotation':0,'lettering':lettering['settings'],'color':'#173f38'}
                text_result=export({**project,'layers':[text]});assert text_result['preview']['stitches']>100
                imported=api('/api/import',{'name':'fixture.svg','svg':'<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="15mm" viewBox="0 0 20 15"><path d="M0,0 H20 V15 H0 Z" fill="#235c48"/></svg>'})
                assert abs(imported['width']-20)<.1 and abs(imported['height']-15)<.1,imported
                for path,original in settings.items():assert (path.read_bytes() if path.exists() else None)==original,'Desktop setting changed: '+str(path)
                report={'platform':health['runtime']['platform'],'engine':health['engine'],'inkscape':health['runtime']['inkscape'],
                        'fonts':len(fonts),'shapeStitches':result['preview']['stitches'],'letteringStitches':text_result['preview']['stitches'],
                        'passed':['editor assets','formats and preferences','Unicode save/reopen','PES readback','engine object info','design check','density changes',
                                  'exact backup round-trip','lettering PES','SVG import','desktop settings preserved']}
                print(json.dumps(report,indent=2))
            finally:
                if job:job.close()
                elif process.poll() is None:process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':main()
