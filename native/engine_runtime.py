"""Bootstrap the unmodified modules in the installed PyInstaller bundle.

The archive layout is the documented PyInstaller CArchive format. Bootstrap
modules, runtime hooks, Python libraries and extension modules all come from
the installed engine; only the final desktop entry point is replaced.
"""
import sys,marshal,_struct as struct,zlib,os

ENGINE=os.environ.get('STUDIO_INKSTITCH','/opt/inkstitch/bin/inkstitch')
BUNDLE=os.path.dirname(ENGINE)
data=open(ENGINE,'rb').read()
cookie=data.rfind(b'MEI\014\013\012\013\016')
if cookie<0:raise RuntimeError('Ink/Stitch has no supported Python archive.')
magic,length,offset,size,version,library=struct.unpack('!8sIIII64s',data[cookie:cookie+88])
if version!=311 or sys.version_info[:2]!=(3,11):raise RuntimeError('The native engine adapter requires the installed Python 3.11 bundle.')
start=cookie+88-length;position=start+offset;end=position+size;entries=[]
while position<end:
    n,off,packed,plain,compressed,kind=struct.unpack('!IIIIBc',data[position:position+18])
    if n<18 or position+n>end:raise RuntimeError('Invalid Ink/Stitch archive directory.')
    name=data[position+18:position+n].rstrip(b'\0').decode()
    entries.append((name,kind,off,packed,plain,compressed));position+=n
pyz=next(e for e in entries if e[0]=='PYZ.pyz')
sys._MEIPASS=BUNDLE
sys._pyinstaller_pyz=ENGINE+'?'+str(start+pyz[2])
sys.executable=ENGINE
for name,kind,off,packed,plain,compressed in entries:
    if name=='inkstitch' or kind not in (b'm',b's'):continue
    raw=data[start+off:start+off+packed]
    if compressed:raw=zlib.decompress(raw)
    if len(raw)!=plain:raise RuntimeError('Invalid Ink/Stitch bootstrap module.')
    module=type(sys)(name);module.__file__=BUNDLE+'/'+name+'.pyc';sys.modules[name]=module
    exec(marshal.loads(raw),module.__dict__)
del data
from pathlib import Path

# Keep the desktop installation's custom-font setting and cache untouched.
# Install this before importing lib, whose settings are initialized on import.
if os.environ.get('STUDIO_ENGINE_CONFIG'):
    import platformdirs
    original_config_dir=platformdirs.user_config_dir
    def studio_config_dir(appname=None,*args,**kwargs):
        if appname=='inkstitch':return os.environ['STUDIO_ENGINE_CONFIG']
        return original_config_dir(appname,*args,**kwargs)
    platformdirs.user_config_dir=studio_config_dir
for stream in (sys.stdout,sys.stderr):
    if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')

if sys.platform=='win32' and os.environ.get('STUDIO_WINDOWS_LAUNCHER'):
    # Installed extensions can launch Inkscape through inkex themselves. Keep
    # these descendants on the same private desktop as the parent engine job.
    import subprocess,shutil,uuid
    original_popen=subprocess.Popen
    def hidden_popen(args,*positional,**kwargs):
        if isinstance(args,(list,tuple)) and args and os.path.basename(str(args[0])).lower() in ('inkscape','inkscape.exe','inkscape.com'):
            executable=shutil.which(str(args[0])) or str(args[0])
            remaining=list(args[1:])
            if not any(str(arg).startswith('--app-id-tag=') for arg in remaining):remaining.insert(0,'--app-id-tag=inkstudio-'+uuid.uuid4().hex)
            args=[os.environ['STUDIO_WINDOWS_LAUNCHER'],os.environ['STUDIO_WINDOWS_DESKTOP'],executable,*remaining]
            kwargs['creationflags']=kwargs.get('creationflags',0)|subprocess.CREATE_NO_WINDOW
        return original_popen(args,*positional,**kwargs)
    subprocess.Popen=hidden_popen

# Private, fixed entry points; no user-supplied Python is executed.
sys.path.append(str(Path(globals().get('__file__','/native/engine_runtime.py')).absolute().parent))
if '--native-diagnostics' in sys.argv:
    # Fixed imports only: no project, custom font inventory or user log is read.
    import json,platform
    import inkex,lxml.etree,numpy,PIL,pystitch,fontTools
    from lib.extensions.lettering import Lettering
    from lib.extensions.print_pdf import Print
    print(json.dumps({'ok':True,'python':platform.python_version()}))
    raise SystemExit(0)
elif '--native-cli' in sys.argv:
    sys.argv.remove('--native-cli')
    from engine_cli_worker import main
elif '--native-select' in sys.argv:
    sys.argv.remove('--native-select')
    from selection_worker import main
elif '--native-sewing-optimize' in sys.argv:
    sys.argv.remove('--native-sewing-optimize')
    from sewing_optimizer_worker import main
elif '--native-feather' in sys.argv:
    sys.argv.remove('--native-feather')
    from feather_worker import main
elif '--native-print' in sys.argv:
    sys.argv.remove('--native-print')
    from print_worker import main
elif '--native-export' in sys.argv:
    sys.argv.remove('--native-export')
    from export_worker import main
elif '--native-troubleshoot' in sys.argv:
    sys.argv.remove('--native-troubleshoot')
    from troubleshoot_worker import main
else:
    from element_info_worker import main
main()
