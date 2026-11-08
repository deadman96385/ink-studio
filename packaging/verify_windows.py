"""Unattended installer/portable lifecycle checks, using disposable user state."""
import argparse
import base64
import copy
import hashlib
import http.client
import io
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import uuid
import winreg
import zipfile

ROOT=Path(__file__).resolve().parent.parent
APP_ID='{D995F88D-982B-4AD1-8346-43FA20FE0F66}_is1'
UNINSTALL_KEY='Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\'+APP_ID


def registered(app_id=APP_ID):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,UNINSTALL_KEY[:-len(APP_ID)]+app_id) as key:
            return winreg.QueryValueEx(key,'InstallLocation')[0]
    except FileNotFoundError:
        return None


def command(args,env,timeout=120):
    result=subprocess.run(list(map(str,args)),env=env,capture_output=True,timeout=timeout,
                          creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==0,(args,result.returncode,result.stderr.decode('utf-8','replace'))
    return result


class Session:
    def __init__(self,app,state,env):
        self.app,self.state,self.env=app,state,env
        self.process=None
    def start(self):
        self.process=subprocess.Popen([str(self.app/'Ink Studio.exe'),'--headless','--no-browser'],env=self.env,
                                      cwd=os.environ['TEMP'],creationflags=subprocess.CREATE_NO_WINDOW)
        deadline=time.monotonic()+300
        while time.monotonic()<deadline:
            if self.process.poll() is not None:
                raise AssertionError((self.state/'logs/launcher.log').read_text(encoding='utf-8-sig'))
            try:
                self.session=json.loads((self.state/'runtime/session.json').read_text(encoding='utf-8-sig'))
                self.base='http://127.0.0.1:'+str(self.session['port'])
                log=(self.state/'logs/launcher.log').read_text(encoding='utf-8-sig')
                if 'Ready: '+self.base+'/' not in log:
                    time.sleep(.25)
                    continue
                health=self.api('/api/health')
                if health['instance']==self.session['instance']:
                    assert Path(health['runtime']['sourceDirectory'])==self.app/'app'
                    assert Path(health['runtime']['dataDirectory'])==self.state/'data'
                    assert health['runtime']['engineDisplay']=='private-desktop'
                    return health
            except (OSError,ValueError,KeyError,http.client.HTTPException):
                time.sleep(.25)
        raise AssertionError('Packaged startup timed out')
    def raw(self,path):
        with urllib.request.urlopen(self.base+path,timeout=180) as response:return response.read()
    def api(self,path,data=None):
        request=urllib.request.Request(self.base+path,None if data is None else json.dumps(data).encode(),{'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=180) as response:return json.load(response)
    def export(self,project):
        job=self.api('/api/export',{'project':project})
        deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            result=self.api('/api/jobs/'+job['id'])
            assert result['state']!='error',result
            if result['state']=='done':return result['result']
            time.sleep(.2)
        raise AssertionError('Export timed out')
    def stop(self):
        command([self.app/'Ink Studio.exe','--stop','--quiet'],self.env)
        if self.process:
            self.process.wait(timeout=20)
            assert self.process.returncode==0,self.process.returncode
        status=subprocess.run([str(self.app/'Ink Studio.exe'),'--status'],env=self.env,creationflags=subprocess.CREATE_NO_WINDOW)
        assert status.returncode==1


def verify_design(session):
    import pystitch
    from PIL import Image,ImageDraw
    health=session.api('/api/health')
    assert health['runtime']['imageTracing']
    assert health['runtime']['appVersion']==(ROOT/'VERSION').read_text().strip()
    assert b'Ink Studio' in session.raw('/')
    assert not re.search(rb'\btail[0-9a-f]+\.ts\.net\b', session.raw('/'))
    for headers in ({'Host':'untrusted.example:8801'},{'Origin':'https://untrusted.example'},
                    {'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'no-cors','Sec-Fetch-Dest':'image'}):
        request=urllib.request.Request(session.base+'/api/projects',headers=headers)
        try:urllib.request.urlopen(request,timeout=10)
        except urllib.error.HTTPError as error:assert error.code==403
        else:raise AssertionError('Foreign request reached the project API')
    # Check every shipped front-end module using the actual HTTP server.
    for path in (session.app/'app').iterdir():
        if path.suffix in ('.mjs','.js','.css') and path.name not in ('sitecustomize.py',):
            assert session.raw('/'+path.name),path.name
    project={'version':1,'id':'packaged-cafe','name':'Packaged café design','fabric':'#faf7f0','layers':[
        {'id':'shape','type':'rectangle','name':'Shape','x':15,'y':20,'width':30,'height':20,'rotation':0,'radius':0,
         'color':'#235c48','stitch':'fill','spacing':.4,'angle':45,'stitchLength':3,'underlay':True}]}
    session.api('/api/save',{'project':project})
    result=session.export(project)
    pes=session.state/'readback.pes';pes.write_bytes(session.raw(result['pes']))
    pattern=pystitch.read(str(pes));bounds=pattern.bounds()
    assert len(pattern.stitches)>100 and abs((bounds[2]-bounds[0])/10-30)<.2 and abs((bounds[3]-bounds[1])/10-20)<.2
    letter=session.api('/api/lettering',{'font':'medium_font','text':'Ink','scale':80,'align':'center','lineSpacing':0,'letterSpacing':0})
    lettering={'id':'letters','type':'text','name':'Ink','x':20,'y':20,'width':letter['width'],'height':letter['height'],
               'rotation':0,'lettering':letter['settings'],'color':'#173f38'}
    assert session.export({**project,'layers':[lettering]})['preview']['stitches']>100
    assert session.api('/api/element-info',{'project':project})['elements']
    image=Image.new('RGB',(120,100),'white');ImageDraw.Draw(image).ellipse((20,10,100,90),fill='#235c48')
    output=io.BytesIO();image.save(output,format='PNG')
    imported=session.api('/api/import-image',{'name':'Trace test','data':base64.b64encode(output.getvalue()).decode()})
    reference={'id':'reference','type':'image','name':'Trace test','image':imported['key'],'pixelWidth':120,'pixelHeight':100,
               'x':20,'y':20,'width':30,'height':25,'opacity':.5,'color':'#235c48','crop':[0,0,1,1]}
    trace=session.api('/api/trace-image',{'layer':reference,'params':{'mode':'threshold','threshold':150}})
    assert trace['layers'] and trace['preview']['stitches']>0
    pdf=session.api('/api/print-generate',{'id':result['id'],'settings':{'layouts':['operatorOverview','operatorDetail','pattern'],'paper':'a4'}})
    assert pdf['pages']==3 and session.raw(pdf['url']).startswith(b'%PDF')
    # Exercise the UI's page endpoint, not only the PDF generation worker.
    preview=session.raw('/print-page/'+pdf['key']+'/1')
    assert preview.startswith(b'\x89PNG'),preview[:80]
    (session.state/'pdf-preview.png').write_bytes(preview)
    return {'project':project,'stitches':result['preview']['stitches'],'fonts':len(session.api('/api/fonts')),
            'pdfPages':pdf['pages'],'tracingStitches':trace['preview']['stitches'],'health':health}


def setup_report(app,env,path,flags=(),expected=None):
    result=subprocess.run([str(app/'Ink Studio.exe'),*flags,'--diagnostics',str(path)],env=env,
                          capture_output=True,timeout=300,creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode in ((0,2) if expected is None else (expected,)),result.returncode
    report=json.loads(path.read_text(encoding='utf-8'))
    assert report['ready']==(result.returncode==0)
    text=json.dumps(report)
    for secret in (str(app),env.get('STUDIO_STATE_HOME','UNUSED_SENTINEL'),os.environ.get('USERNAME','UNUSED_SENTINEL'),
                   'PRIVATE_DIAGNOSTIC_SENTINEL','packaged-cafe','settings.json'):
        assert secret not in text,secret
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist',type=Path,default=ROOT/'dist')
    parser.add_argument('--output',type=Path,default=ROOT/'.native-runtime/verification/windows-m3')
    parser.add_argument('--compressed-work',action='store_true',help='Use NTFS compression only for disposable test files')
    args=parser.parse_args()
    production_install=registered()
    try:
        with urllib.request.urlopen('http://127.0.0.1:8801/api/health',timeout=2) as response:production_health=json.load(response)
    except OSError:production_health=None
    version=(ROOT/'VERSION').read_text().strip()
    setup=args.dist/('InkStudio-'+version+'-windows-x64-setup.exe')
    archive=args.dist/('InkStudio-'+version+'-windows-x64-portable.zip')
    output=args.output.absolute();output.mkdir(parents=True,exist_ok=True)
    # Destination is deliberately outside the development checkout.
    work=Path(tempfile.mkdtemp(prefix='InkStudio verification café ')).resolve()
    if args.compressed_work:
        compressed=subprocess.run(['compact.exe','/C',str(work),'/I','/Q'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        assert compressed.returncode==0,'Could not enable temporary NTFS compression'
    test_uuid=str(uuid.uuid4()).upper()
    test_app_id='{'+test_uuid+'}_is1'
    env=dict(os.environ)
    for key in list(env):
        if key.startswith(('STUDIO_','PYTHON')):env.pop(key,None)
    env['PATH']=os.environ['WINDIR']+r'\System32;'+os.environ['WINDIR']
    env['PYTHONHOME']=str(work/'invalid-system-python')
    env['PYTHONPATH']=str(work/'invalid-system-modules')
    profile=Path(os.environ['LOCALAPPDATA'])/'inkstitch/inkstitch'
    original={p:p.read_bytes() if p.exists() else None for p in [profile/'settings.json',profile/'custom_dirs.json']}
    results=[]
    def passed(name,**details):
        results.append({'case':name,'passed':True,**details});print(name+': PASS',flush=True)
        (output/'results.json').write_text(json.dumps({'workDirectory':str(work),'results':results},indent=2),encoding='utf-8')
    with zipfile.ZipFile(archive) as source:
        for member in source.namelist():
            assert not Path(member).is_absolute() and '..' not in Path(member).parts
        source.extractall(work/'portable')
    portable=work/'portable'/'Ink Studio'
    # Compile the exact public payload under a disposable installer identity.
    # The production AppId, Installed apps entry and Start menu group are never
    # used by lifecycle tests, even when a real copy is already installed.
    parser_compiler=ROOT/'.native-runtime/packaging/inno/ISCC.exe'
    compiler=os.environ.get('STUDIO_INSTALLER_COMPILER',str(parser_compiler))
    installer_stage=work/'installer-payload'
    shutil.copytree(portable,installer_stage)
    command([compiler,'/Qp','/DStageDir='+str(installer_stage),'/DAppVersion='+version,
             '/DReleaseDir='+str(work/'test-setup'),'/DInstallerAppId={{'+test_uuid+'}',
             '/DInstallerName=Ink Studio Verification',ROOT/'packaging/windows/InkStudio.iss'],env,timeout=300)
    test_setup=work/'test-setup'/setup.name
    # Preseed the verified vendor archive, not an extracted development install.
    # First launch must verify and extract it into the portable cache itself.
    cache=portable/'cache/downloads';cache.mkdir(parents=True)
    download=ROOT/'.native-runtime/downloads/inkscape-1.4.4-x64.7z'
    if download.exists():shutil.copy2(download,cache/download.name)
    portable_env={**env}
    current=Session(portable,portable,portable_env)
    installed=None
    try:
        invalid=work/'state-is-a-file';invalid.write_text('not a directory')
        bad=subprocess.run([str(portable/'Ink Studio.exe'),'--headless','--no-browser'],
                           env={**env,'STUDIO_STATE_HOME':str(invalid)},timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        assert bad.returncode==2,bad.returncode
        passed('unwritable-state-reports-error-without-ui')
        report=setup_report(portable,portable_env,work/'cold-check.json')
        assert not (portable/'cache/inkscape-1.4.4/inkscape/bin/inkscape.com').exists()
        assert not (portable/'runtime/session.json').exists()
        passed('cold-offline-check-does-not-download-or-start-server',ready=report['ready'])
        report=setup_report(portable,{**portable_env,'STUDIO_INKSTITCH':str(work/'PRIVATE_DIAGNOSTIC_SENTINEL/missing.exe')},work/'missing-engine.json',expected=2)
        assert any(c['code']=='inkstitch-found' and c['status']=='error' for c in report['checks'])
        passed('missing-engine-has-private-actionable-diagnostics')
        config=portable/'config/settings.json';config.parent.mkdir(parents=True,exist_ok=True)
        try:
            config.write_text('{malformed PRIVATE_DIAGNOSTIC_SENTINEL')
            report=setup_report(portable,portable_env,work/'malformed-settings.json',expected=2)
            assert report['checks'][0]['code']=='settings-invalid'
            passed('malformed-settings-have-private-diagnostics')
            config.write_text(json.dumps({'dataDirectory':str(invalid)}))
            report=setup_report(portable,portable_env,work/'unwritable-projects.json',expected=2)
            assert any(c['code']=='data-writable' and c['status']=='error' for c in report['checks'])
            passed('unwritable-projects-have-actionable-diagnostics')
        finally:
            config.unlink(missing_ok=True)
        setup_report(portable,portable_env,work/'offline-prepared.json',flags=['--setup-tools','--offline'],expected=0)
        passed('verified-cache-offline-preparation')
        setup_report(portable,{**portable_env,'STUDIO_DIAG_SECRET':'PRIVATE_DIAGNOSTIC_SENTINEL'},work/'headless-setup.json',flags=['--setup','--headless'],expected=0)
        assert not (portable/'runtime/session.json').exists()
        passed('headless-setup-and-private-diagnostics-export')
        health=current.start()
        assert registered()==production_install
        passed('portable-first-launch',backendDirectory=health['runtime']['sourceDirectory'],inkscape=health['runtime']['inkscape'])
        data=verify_design(current);passed('portable-editor-pes-fonts-tracing-pdf',stitches=data['stitches'],pdfPages=data['pdfPages'])
        pid=current.session['pid']
        command([portable/'Ink Studio.exe','--headless','--no-browser'],portable_env)
        assert json.loads((portable/'runtime/session.json').read_text())['pid']==pid
        passed('single-instance')
        other_state=work/'Other session state';(other_state/'config').mkdir(parents=True)
        (other_state/'config/settings.json').write_text(json.dumps({'dataDirectory':str(portable/'data'),'port':18881}))
        other=subprocess.run([str(portable/'Ink Studio.exe'),'--headless','--no-browser'],
                             env={**env,'STUDIO_STATE_HOME':str(other_state)},timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        assert other.returncode==2 and current.api('/api/health')['pid']==pid
        passed('shared-project-folder-protection')
        current.stop();passed('stop-and-status')
        moved=work/'Relocated portable café with spaces'
        assert portable.is_relative_to(work) and moved.is_relative_to(work)
        portable.rename(moved)
        current=Session(moved,moved,portable_env);current.start()
        tools=Path(current.api('/api/health')['runtime']['inkscapePath'])
        assert current.api('/api/projects/packaged-cafe')['name']=='Packaged café design'
        assert current.export(data['project'])['preview']['stitches']==data['stitches']
        current.stop();passed('portable-relocation-preserves-projects')
        install=work/'Installed Ink Studio café'
        state=work/'Installed user state café'
        installed_env={**env,'STUDIO_STATE_HOME':str(state)}
        group='Ink Studio Packaging Test '+uuid.uuid4().hex[:10]
        flags=['/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS','/TASKS=', '/GROUP='+group,'/DIR='+str(install)]
        command([test_setup,*flags,'/LOG='+str(output/'install.log')],installed_env)
        assert Path(registered(test_app_id)).resolve()==install.resolve()
        passed('silent-current-user-install')
        config=state/'config/settings.json';config.parent.mkdir(parents=True,exist_ok=True)
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1',0));occupied.listen();preferred=occupied.getsockname()[1]
            config.write_text(json.dumps({'inkscape':str(tools),'port':preferred}),encoding='utf-8')
            installed=Session(install,state,installed_env);installed.start()
            assert installed.session['port']!=preferred
            passed('occupied-port-fallback')
        installed.api('/api/save',{'project':data['project']})
        assert installed.export(data['project'])['preview']['stitches']==data['stitches']
        passed('installed-bundled-runtime-pes')
        saved_config=config.read_bytes()
        # Upgrade stops the owned running session, then replaces program files.
        command([test_setup,*flags,'/LOG='+str(output/'upgrade.log')],installed_env)
        installed.process.wait(timeout=20)
        assert config.read_bytes()==saved_config
        installed=Session(install,state,installed_env);installed.start()
        assert installed.api('/api/projects/packaged-cafe')['name']=='Packaged café design'
        installed.stop();passed('upgrade-preserves-projects-and-settings')
        unknown=install/'user-file.keep';unknown.write_text('not owned by the installer')
        command([install/'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/LOG='+str(output/'uninstall.log')],installed_env)
        assert not (install/'Ink Studio.exe').exists() and not registered(test_app_id)
        assert unknown.exists() and config.read_bytes()==saved_config and (state/'data/projects/packaged-cafe.json').exists()
        passed('uninstall-retains-user-data-and-unowned-files')
        assert all((p.read_bytes() if p.exists() else None)==value for p,value in original.items())
        passed('desktop-inkstitch-settings-unchanged')
        assert registered()==production_install
        if production_health:
            with urllib.request.urlopen('http://127.0.0.1:8801/api/health',timeout=5) as response:after=json.load(response)
            assert after['instance']==production_health['instance'] and after['pid']==production_health['pid']
        passed('installed-production-session-untouched')
        report={'passed':len(results),'failed':0,'workDirectory':str(work),'results':results,
                'installer':str(setup.absolute()),'portable':str(archive.absolute()),'noSystemPythonRequired':True,
                'headless':True,'temporaryNtfsCompression':args.compressed_work,'desktopProfilePreserved':True,'testInstallerAppId':test_app_id,
                'productionInstallPreserved':True,'testedInstaller':str(test_setup),'publicPayloadIdentity':health['runtime'].get('appVersion')}
        (output/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({'passed':len(results),'report':str(output/'results.json')}),flush=True)
    finally:
        for session in (current,installed):
            if session and session.process and session.process.poll() is None:
                try:session.stop()
                except Exception:session.process.kill()
        # A failed test must not leave its temporary Installed apps entry.
        location=registered(test_app_id)
        test_install=work/'Installed Ink Studio café'
        if location and Path(location).resolve()==test_install.resolve() and (test_install/'unins000.exe').exists():
            cleanup_env={**env,'STUDIO_STATE_HOME':str(work/'Installed user state café')}
            command([test_install/'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],cleanup_env)


if __name__=='__main__':main()
