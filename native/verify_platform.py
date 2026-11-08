"""Run the real advanced-engine checks against a disposable local instance.

The same tests and assertions run on Windows and Linux. Only fixture locations
and the API URL vary. Logs and the JSON report remain available for diagnosis.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import studio_runtime

ROOT = Path(__file__).absolute().parent
CASES = ['native','advanced','operations','selection','references','linked',
         'fontlibrary','fontworkspaces','fonttools','fonttools_edges','fontletter_svg',
         'ttf_fonts','fontsamples','export_options','print_work','preparation',
         'feather','wave_fill','sewing_optimizer','merrow','multisatin','svgprep',
         'masks','threadwork','swatches','helpers','commands','batches','transforms']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases', nargs='*', default=CASES)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true', help='Retain previous passes and run only missing or failed cases')
    options=parser.parse_args()
    folder=(options.output or Path(tempfile.mkdtemp(prefix='inkstudio-platform-'))).absolute()
    folder.mkdir(parents=True,exist_ok=True)
    data=folder/'Designs café with spaces';data.mkdir(exist_ok=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    instance=uuid.uuid4().hex
    runtime=studio_runtime.current()
    env={**runtime.environment(),'STUDIO_DATA':str(data),'STUDIO_ENGINE_CONFIG':str(data/'config'/'inkstitch'),
         'STUDIO_HOST':'127.0.0.1','STUDIO_PORT':str(port),'STUDIO_URL':base,'STUDIO_INSTANCE_ID':instance}
    if not runtime.windows:env['XDG_CONFIG_HOME']=str(data/'config')
    logs=folder/'logs';logs.mkdir(exist_ok=True)
    results=[]
    if options.resume and (folder/'results.json').is_file():
        results=[r for r in json.loads((folder/'results.json').read_text(encoding='utf-8'))['results']
                 if r['case'] in options.cases]
    previous={r['case']:r['exitCode'] for r in results}
    cases=[case for case in options.cases if not options.resume or previous.get(case)!=0]
    settings={}
    if runtime.windows:
        profile=Path(os.environ['LOCALAPPDATA'])/'inkstitch'/'inkstitch'
        settings={p:p.read_bytes() if p.exists() else None for p in [profile/'settings.json',profile/'custom_dirs.json']}
    with (logs/'server.log').open('wb') as server_log:
        server=subprocess.Popen([sys.executable,'-X','utf8',str(ROOT/'server.py')],env=env,stdout=server_log,stderr=subprocess.STDOUT,
                                **({'creationflags':subprocess.CREATE_NO_WINDOW} if runtime.windows else {}))
        job=studio_runtime._WindowsJob(server) if runtime.windows else None
        health=None
        try:
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                if server.poll() is not None:raise RuntimeError('Server stopped; see '+str(logs/'server.log'))
                try:
                    with urllib.request.urlopen(base+'/api/health',timeout=10) as response:health=json.load(response)
                    if health['instance']==instance:break
                except OSError:time.sleep(.25)
            if not health:raise RuntimeError('Server startup timed out')
            print('Running '+health['runtime']['platform']+' checks with '+health['runtime']['inkscape'],flush=True)
            for name in cases:
                script=ROOT/('verify_'+name+'.py')
                if not script.is_file() or name not in CASES:raise ValueError('Unknown verification case: '+name)
                started=time.monotonic()
                with (logs/(name+'.log')).open('wb') as log:
                    process=subprocess.Popen([sys.executable,'-X','utf8',str(script)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                                             **({'creationflags':subprocess.CREATE_NO_WINDOW} if runtime.windows else {'start_new_session':True}))
                    test_job=studio_runtime._WindowsJob(process) if runtime.windows else None
                    try:
                        code=process.wait(timeout=1200)
                    except subprocess.TimeoutExpired:
                        code=124
                        if test_job:test_job.close()
                        else:
                            import signal
                            os.killpg(process.pid,signal.SIGKILL)
                        process.wait()
                    finally:
                        if test_job:test_job.close()
                row={'case':name,'exitCode':code,'seconds':round(time.monotonic()-started,1),'log':str(logs/(name+'.log'))}
                results=[r for r in results if r['case']!=name]+[row]
                print(name+': '+('PASS' if code==0 else 'FAIL')+' ('+str(row['seconds'])+'s)',flush=True)
                (folder/'results.json').write_text(json.dumps({'runtime':health['runtime'],'results':results},indent=2),encoding='utf-8')
            for path,original in settings.items():
                if (path.read_bytes() if path.exists() else None)!=original:
                    results.append({'case':'desktop-profile-preservation','exitCode':1})
            report={'runtime':health['runtime'],'results':results,'passed':sum(r['exitCode']==0 for r in results),
                    'failed':sum(r['exitCode']!=0 for r in results),'desktopProfilePreserved':all((p.read_bytes() if p.exists() else None)==v for p,v in settings.items())}
            (folder/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps({'passed':report['passed'],'failed':report['failed'],'report':str(folder/'results.json')}),flush=True)
            return 1 if report['failed'] else 0
        finally:
            if job:job.close()
            elif server.poll() is None:server.terminate()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':raise SystemExit(main())
