"""Audit release artifacts without an engine, installation or user data."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def safe_member(name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe archive member: '+name)


def verify(folder, public=False):
    folder=Path(folder).resolve()
    release=json.loads((folder/'release-manifest.json').read_text(encoding='utf-8'))
    version=release['version'];checks=[]
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Invalid release version.')
    sums={}
    for line in (folder/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        expected,name=line.split('  ',1);safe_member(name)
        if '/' in name or not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('Invalid checksum entry.')
        if digest(folder/name)!=expected:raise ValueError('Artifact checksum mismatch: '+name)
        sums[name]=expected
    for artifact in release['artifacts']:
        name=artifact['file'];safe_member(name)
        if sums.get(name)!=artifact['sha256'] or (folder/name).stat().st_size!=artifact['bytes']:
            raise ValueError('Release manifest mismatch: '+name)
    checks.append('artifact checksums and provenance')
    portable=folder/f'InkStudio-{version}-windows-x64-portable.zip'
    with zipfile.ZipFile(portable) as archive:
        names=archive.namelist()
        for name in names:
            safe_member(name)
            if not name.startswith('Ink Studio/'):raise ValueError('Unexpected portable layout.')
            if name.startswith(tuple('Ink Studio/'+value+'/' for value in ('data','cache','logs','config','.native-runtime','.venv-native','designs'))):
                raise ValueError('User/developer state in portable package: '+name)
        if 'Ink Studio/portable.txt' not in names:raise ValueError('Portable marker is missing.')
        package=json.loads(archive.read('Ink Studio/package.json'))
        if package['version']!=version or package['sourceSha256']!=release['sourceSha256']:
            raise ValueError('Package and release identity differ.')
        manifest=json.loads(archive.read('Ink Studio/package-files.json'))
        expected={'Ink Studio/'+name for name in manifest}|{'Ink Studio/package-files.json','Ink Studio/portable.txt'}
        if set(names)!=expected:raise ValueError('Unlisted or missing payload files.')
        for name,value in manifest.items():
            safe_member(name)
            if hashlib.sha256(archive.read('Ink Studio/'+name)).hexdigest()!=value:
                raise ValueError('Payload checksum mismatch: '+name)
        checks.append('portable layout, all payload hashes and absence of user data')
        frontend={name[15:] for name in names if name.startswith('Ink Studio/app/')}
        for name in names:
            if name.startswith('Ink Studio/app/') and Path(name).suffix in ('.py','.html','.js','.mjs','.css'):
                text=archive.read(name).decode('utf-8')
                if re.search(r'\btail[0-9a-f]+\.ts\.net\b|[A-Za-z]:\\Users\\',text,re.I):
                    raise ValueError('Personal deployment reference in payload: '+name)
                if Path(name).suffix in ('.js','.mjs'):
                    for imported in re.findall(r'(?:from\s+|import\s*\()[\'\"](\./[^\'\"]+)[\'\"]',text):
                        if imported[2:] not in frontend:raise ValueError('Missing front-end module: '+imported)
        checks.append('front-end imports and public deployment defaults')
        notice=archive.read('Ink Studio/NOTICE.txt').decode()
        if 'either version 3' not in notice:raise ValueError('GPL project notice is missing.')
        if 'Ink Studio/licenses/components.json' not in names or 'Ink Studio/licenses/sources.lock.json' not in names:
            raise ValueError('Dependency notices or source provenance are missing.')
        expected_sources=json.loads(archive.read('Ink Studio/licenses/sources.lock.json'))
    source=folder/f'InkStudio-{version}-source.tar.gz'
    with tarfile.open(source) as archive:
        prefix=f'ink-studio-{version}/'
        names=archive.getnames()
        for name in names:
            safe_member(name)
            if not name.startswith(prefix):raise ValueError('Unexpected source layout.')
        for name in ('LICENSE','NOTICE.txt','VERSION','Build-Studio-Windows.ps1','packaging/build_windows.py',
                     'packaging/windows/ink-studio.ico','.github/workflows/checks.yml',
                     'README.md','CHANGELOG.md','SECURITY.md','PRIVACY.md',
                     'CODE_SIGNING_POLICY.md','CONTRIBUTING.md'):
            if prefix+name not in names:raise ValueError('Missing release source: '+name)
        if archive.extractfile(prefix+'VERSION').read().decode().strip()!=version:raise ValueError('Source version mismatch.')
        if not archive.getmember(prefix+'packaging/linux/ink-studio').mode&0o111:raise ValueError('Linux launcher is not executable.')
        for name in names:
            if name.startswith(tuple(prefix+folder+'/' for folder in ('designs','patterns','work','build','.native-runtime'))):
                raise ValueError('Non-release data in source archive.')
            if name.startswith(prefix+'root/') and name.endswith(('.html','.js')):
                text=archive.extractfile(name).read().decode('utf-8')
                if re.search(r'\btail[0-9a-f]+\.ts\.net\b|[A-Za-z]:\\Users\\',text,re.I):
                    raise ValueError('Personal deployment reference in Linux dashboard source: '+name)
        checks.append('corresponding source, Linux executable and release documentation')
    with zipfile.ZipFile(folder/f'InkStudio-{version}-third-party-sources.zip') as archive:
        sources=json.loads(archive.read('sources.lock.json'))
        if sources!=expected_sources:raise ValueError('Package and dependency-source inventories differ.')
        for item in sources:
            safe_member(item['filename'])
            if hashlib.sha256(archive.read('sources/'+item['filename'])).hexdigest()!=item['sha256']:
                raise ValueError('Dependency source checksum mismatch: '+item['filename'])
        checks.append('original dependency source archives')
    if public:
        if release.get('windowsSigning')!='verified':
            raise ValueError('Public release is blocked: Windows artifacts are unsigned. Configure and verify publisher signing first.')
        # A manifest assertion alone must never grant signed-release status.
        raise ValueError('Public signing verification is not configured for this preview toolchain.')
    return {'version':version,'status':'preview-verified','passed':len(checks),'checks':checks,
            'windowsSigning':release['windowsSigning'],'publicReleaseReady':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist',type=Path,default=Path(__file__).resolve().parent.parent/'dist')
    parser.add_argument('--public',action='store_true',help='Require public-release gates; unsigned previews fail')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    report=verify(args.dist,args.public)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
