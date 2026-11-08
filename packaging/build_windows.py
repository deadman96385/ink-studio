"""Build a Windows installer, portable ZIP and matching source archive."""
import argparse
import email
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / '.native-runtime' / 'packaging'
PYTHON_VERSION = '3.14.10'
PYTHON_URL = 'https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip'
PYTHON_SHA256 = '90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'
INNO_URL = 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe'
INNO_SHA256 = '8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0'


def run(args, **kwargs):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, encoding='utf-8',
                            errors='replace', creationflags=subprocess.CREATE_NO_WINDOW, **kwargs)
    if result.returncode:
        raise RuntimeError('Command failed: ' + str(args[0]) + '\n' + result.stdout[-6000:] + result.stderr[-6000:])
    return result.stdout


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, digest, target, offline=False):
    if target.exists() and sha256(target) == digest:
        return target
    if offline:
        raise ValueError('Missing verified build input: ' + str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.download')
    with urllib.request.urlopen(url, timeout=90) as response, temporary.open('wb') as output:
        shutil.copyfileobj(response, output)
    if sha256(temporary) != digest:
        temporary.unlink()
        raise ValueError('Download checksum mismatch: ' + url)
    temporary.replace(target)
    return target


def application_file(path):
    try:
        reviewed=path.relative_to(ROOT).as_posix() in source_names()
    except ValueError:
        return False
    return reviewed and path.is_file() and not path.name.startswith(('test', 'verify', 'create_', 'render_', 'trace_')) and path.name != 'desktop-audit.json' and path.suffix in {'.py','.mjs','.js','.css','.svg','.html','.json','.webmanifest'}


def wheel_metadata(path):
    with zipfile.ZipFile(path) as archive:
        return email.message_from_bytes(archive.read(next(name for name in archive.namelist() if name.endswith('.dist-info/METADATA'))))


def stage_python(stage, offline):
    archive = download(PYTHON_URL, PYTHON_SHA256, CACHE / ('python-' + PYTHON_VERSION + '-embed-amd64.zip'), offline)
    folder = stage / 'runtime' / 'python'
    folder.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        source.extractall(folder)
    (folder / 'python314._pth').write_text('python314.zip\n.\nLib\\site-packages\n..\\..\\app\nimport site\n', encoding='utf-8')
    wheels = CACHE / 'wheels'
    args = [sys.executable, '-m', 'pip', 'download', '--disable-pip-version-check', '--only-binary=:all:',
            '--require-hashes', '--platform', 'win_amd64', '--python-version', '3.14', '--implementation', 'cp', '--abi', 'cp314',
            '--dest', wheels, '-r', ROOT / 'packaging/windows/requirements.lock']
    if offline:
        args += ['--no-index', '--find-links', wheels]
    run(args, timeout=300)
    # Vendoring wheels is the supported embedding model. No pip, global Python
    # installation, generated console-script paths or first-run pip are shipped.
    site = folder / 'Lib/site-packages'
    site.mkdir(parents=True)
    requirements = {}
    for line in (ROOT / 'packaging/windows/requirements.lock').read_text().splitlines():
        if line and not line.startswith('#'):
            spec, digest = line.split(' --hash=sha256:')
            requirements[spec.lower().replace('_','-')] = digest
    components = []
    for wheel in sorted(wheels.glob('*.whl')):
        meta = wheel_metadata(wheel)
        spec = (meta['Name']+'=='+meta['Version']).lower().replace('_','-')
        if spec not in requirements:
            continue
        if sha256(wheel) != requirements.pop(spec):
            raise ValueError('Wheel checksum mismatch: ' + wheel.name)
        with zipfile.ZipFile(wheel) as archive:
            for entry in archive.infolist():
                path = Path(entry.filename)
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError('Unsafe wheel member')
                parts = path.parts
                if parts and parts[0].endswith('.data'):
                    if len(parts)<3 or parts[1] not in ('purelib','platlib'):
                        continue
                    path=Path(*parts[2:])
                target=site/path
                if entry.is_dir():
                    target.mkdir(parents=True,exist_ok=True)
                else:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(archive.read(entry))
                if not entry.is_dir() and any(word in path.name.lower() for word in ('license','copying','notice','copyright')):
                    notice=stage/'licenses/python-packages'/meta['Name']/path
                    notice.parent.mkdir(parents=True,exist_ok=True)
                    notice.write_bytes(archive.read(entry))
        components.append({'name':meta['Name'],'version':meta['Version'],'wheel':wheel.name,'sha256':sha256(wheel),
                           'projectUrls':meta.get_all('Project-URL',[]),'homePage':meta.get('Home-page',''),
                           'sourceIndex':'https://pypi.org/project/'+meta['Name']+'/'+meta['Version']+'/#files'})
    if requirements:
        raise ValueError('Missing wheels: ' + ', '.join(requirements))
    (site/'sitecustomize.py').write_text('import sys\nsys.dont_write_bytecode = True\n',encoding='utf-8')
    python_notice=stage/'licenses/Python-LICENSE.txt';python_notice.parent.mkdir(exist_ok=True)
    shutil.copy2(folder/'LICENSE.txt',python_notice)
    (stage/'licenses/components.json').write_text(json.dumps({'python':{'version':PYTHON_VERSION,'url':PYTHON_URL,'sha256':PYTHON_SHA256},'packages':components},indent=2),encoding='utf-8')
    return folder/'python.exe'


def make_icon(stage):
    directory=stage/'resources';directory.mkdir()
    # Checked-in renditions of native/icon.svg remove the requirement for an
    # installed Inkscape/Ink-Stitch or Pillow on a clean build machine.
    for name in ('ink-studio.ico','ink-studio.png'):
        shutil.copy2(ROOT/'packaging/windows'/name,directory/name)


def verify_compiler_publisher(setup):
    # PowerShell 7 can pass its module paths through Python to Windows
    # PowerShell, which then tries to load incompatible versions of Security.
    # Let Windows PowerShell construct its own default module paths.
    env={key:value for key,value in os.environ.items() if key.upper()!='PSMODULEPATH'}
    env['INK_STUDIO_COMPILER_SETUP']=str(setup)
    signature=run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
                   '$ErrorActionPreference="Stop"; $s=Get-AuthenticodeSignature -LiteralPath $env:INK_STUDIO_COMPILER_SETUP; if($s.Status -ne "Valid"){exit 1}; $s.SignerCertificate.Subject'],
                  timeout=60,env=env)
    if 'Pyrsys B.V.' not in signature:raise ValueError('Unexpected Inno Setup publisher.')
    return signature


def installer_compiler(explicit=None, bootstrap=False, offline=False):
    if explicit:
        result=Path(explicit)
        if not result.is_file():raise ValueError('Installer compiler not found: '+str(result))
        return result
    result=CACHE/'inno/ISCC.exe'
    if result.is_file():return result
    if not bootstrap:
        raise ValueError('Pass --bootstrap-tools, or install Inno Setup 7 and pass --compiler with its ISCC.exe path.')
    setup=download(INNO_URL,INNO_SHA256,CACHE/'innosetup-7.1.1-x64.exe',offline)
    verify_compiler_publisher(setup)
    run([setup,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS','/DIR='+str(CACHE/'inno')],timeout=120)
    if not result.is_file():raise ValueError('Inno Setup bootstrap did not install ISCC.exe.')
    return result


def source_names():
    names=json.loads((ROOT/'packaging/public-files.json').read_text(encoding='utf-8'))['files']
    if not isinstance(names,list) or len(names)!=len(set(names)):
        raise ValueError('Invalid reviewed source catalog.')
    return sorted(names)


def reviewed_sources():
    from audit_public import inspect_files,safe_path
    files={}
    for name in source_names():
        path=ROOT/name
        if not safe_path(name) or not path.resolve().is_relative_to(ROOT.resolve()) or not path.is_file() or path.is_symlink():
            raise ValueError('Missing or unsafe reviewed source file.')
        files[name]=path.read_bytes()
    report=inspect_files(files,source_names())
    if not report['passed']:
        raise ValueError('Source privacy audit failed. Run packaging/audit_public.py to review the findings.')
    return files


def source_identity():
    digest=hashlib.sha256()
    for name,raw in sorted(reviewed_sources().items()):
        digest.update(name.encode()+b'\0'+raw+b'\0')
    return digest.hexdigest()


def source_archive(target, version):
    def permissions(info):
        info.uid=info.gid=0
        info.uname=info.gname=''
        info.mode=0o755 if info.name.endswith(('/packaging/linux/ink-studio','/.githooks/pre-commit','/.githooks/pre-push','/root/defaults/autostart','/root/custom-cont-init.d/10-ink-settings')) else 0o644
        return info
    with tarfile.open(target,'w:gz',format=tarfile.PAX_FORMAT) as archive:
        prefix='ink-studio-'+version
        for name in reviewed_sources():
            archive.add(ROOT/name,arcname=prefix+'/'+name,filter=permissions)


def dependency_sources(target, offline):
    """Provide the original codec sources, Python and package source releases."""
    manifest=json.loads((ROOT/'packaging/windows/sources.lock.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(target,'w',zipfile.ZIP_STORED) as archive:
        for item in manifest:
            source=download(item['url'],item['sha256'],CACHE/'sources'/item['filename'],offline)
            archive.write(source,'sources/'+source.name)
        archive.writestr('sources.lock.json',json.dumps(manifest,indent=2))
        archive.writestr('README.txt','Original upstream sources for bundled Python, available Python package source distributions, and the libheif/libde265/x265 codec versions identified by pillow-heif 1.8.1. Each source archive retains its own build instructions and license. The pillow-heif source contains its Windows wheel build configuration; pair it with these codec sources to rebuild the bindings. All source URLs and SHA256 hashes are recorded in sources.lock.json. Other dependency source links and notices are in the application licenses directory.\n')


def main():
    global CACHE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'dist')
    parser.add_argument('--compiler',type=Path)
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--stage-only',action='store_true')
    parser.add_argument('--bootstrap-tools',action='store_true')
    parser.add_argument('--cache-dir',type=Path,default=CACHE)
    options=parser.parse_args()
    if os.name!='nt':
        raise SystemExit('Build Windows binaries on Windows. The source package and Linux runtime remain shared.')
    version=(ROOT/'VERSION').read_text().strip()
    CACHE=options.cache_dir.absolute()
    if not __import__('re').fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('VERSION must contain three numeric components.')
    inno=None if options.stage_only else installer_compiler(options.compiler,options.bootstrap_tools,options.offline)
    identity=source_identity()
    output=options.output.absolute();output.mkdir(parents=True,exist_ok=True)
    stage=ROOT/'build/windows'/('InkStudio-'+version+'-'+uuid.uuid4().hex[:8])
    stage.mkdir(parents=True)
    app=stage/'app';app.mkdir()
    for source in (ROOT/'native').iterdir():
        if application_file(source):
            shutil.copy2(source,app/source.name)
    for name in ('LICENSE','NOTICE.txt'):
        shutil.copy2(ROOT/name,stage/name)
    (stage/'docs').mkdir()
    (stage/'docs/INSTALL.txt').write_text((ROOT/'packaging/INSTALL.txt').read_text(encoding='utf-8').replace('@VERSION@',version),encoding='utf-8')
    (stage/'package.json').write_text(json.dumps({'name':'Ink Studio','version':version,'channel':'preview','architecture':'x64','python':PYTHON_VERSION,'license':'GPL-3.0-or-later','sourceSha256':identity}),encoding='utf-8')
    print('Staging bundled Python and pinned wheels…',flush=True)
    python=stage_python(stage,options.offline)
    (stage/'licenses/SOURCE_INFO.txt').write_text('Distribute this release with InkStudio-'+version+'-source.tar.gz and InkStudio-'+version+'-third-party-sources.zip. The latter contains original Python, package and bundled GPL/LGPL codec source archives and their build instructions. See components.json, sources.lock.json and the original dependency license notices for versions, source URLs and hashes.\n',encoding='utf-8')
    shutil.copy2(ROOT/'packaging/windows/sources.lock.json',stage/'licenses/sources.lock.json')
    make_icon(stage)
    compiler=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    assembly=stage/'version.cs'
    assembly.write_text('using System.Reflection;\n[assembly:AssemblyTitle("Ink Studio")]\n[assembly:AssemblyProduct("Ink Studio")]\n[assembly:AssemblyCompany("Ink Studio contributors")]\n[assembly:AssemblyVersion("'+version+'.0")]\n[assembly:AssemblyFileVersion("'+version+'.0")]\n',encoding='utf-8')
    run([compiler,'/nologo','/platform:x64','/target:winexe','/out:'+str(stage/'Ink Studio.exe'),'/win32icon:'+str(stage/'resources/ink-studio.ico'),
         '/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:System.Web.Extensions.dll',ROOT/'packaging/windows/Launcher.cs',assembly],timeout=60)
    for source,name in [('engine_runtime_windows.cs','engine-host.exe'),('windows_command.cs','windows-command.exe')]:
        run([compiler,'/nologo','/platform:x64','/out:'+str(app/name),ROOT/'native'/source,assembly],timeout=60)
    assembly.unlink()
    print(run([python,'-X','utf8','-c','import lxml.etree,numpy,pystitch,PIL,pillow_heif,shapely,fontTools,pypdfium2;print("Bundled Python imports passed")'],timeout=60).strip(),flush=True)
    manifest={path.relative_to(stage).as_posix():sha256(path) for path in sorted(stage.rglob('*')) if path.is_file()}
    (stage/'package-files.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (ROOT/'build/windows/latest-stage.txt').write_text(str(stage),encoding='utf-8')
    if options.stage_only:
        print('Staged application: '+str(stage));return
    print('Building standard Setup.exe…',flush=True)
    run([inno,'/Qp','/DStageDir='+str(stage),'/DAppVersion='+version,'/DReleaseDir='+str(output),ROOT/'packaging/windows/InkStudio.iss'],timeout=600)
    portable=output/('InkStudio-'+version+'-windows-x64-portable.zip')
    print('Building portable ZIP and corresponding source…',flush=True)
    with zipfile.ZipFile(portable,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        prefix='Ink Studio/'
        for path in sorted(stage.rglob('*')):
            if path.is_file():archive.write(path,prefix+path.relative_to(stage).as_posix())
        archive.writestr(prefix+'portable.txt','Keep this file beside Ink Studio.exe to store projects, settings and logs here.\n')
    source=output/('InkStudio-'+version+'-source.tar.gz');source_archive(source,version)
    vendor=output/('InkStudio-'+version+'-third-party-sources.zip');dependency_sources(vendor,options.offline)
    artifacts=[output/('InkStudio-'+version+'-windows-x64-setup.exe'),portable,source,vendor]
    release={'name':'Ink Studio','version':version,'channel':'preview','sourceSha256':identity,
             'builtAt':datetime.now(timezone.utc).isoformat(),'windowsSigning':'unsigned',
             'buildPython':sys.version.split()[0],'bundledPython':PYTHON_VERSION,
             'artifacts':[{'file':path.name,'sha256':sha256(path),'bytes':path.stat().st_size} for path in artifacts]}
    release_path=output/'release-manifest.json';release_path.write_text(json.dumps(release,indent=2),encoding='utf-8')
    artifacts.append(release_path)
    (output/'SHA256SUMS.txt').write_text(''.join(sha256(path)+'  '+path.name+'\n' for path in artifacts),encoding='utf-8')
    print(json.dumps({'version':version,'stage':str(stage),'artifacts':[{'file':str(path),'bytes':path.stat().st_size} for path in artifacts]},indent=2),flush=True)


if __name__=='__main__':
    main()
