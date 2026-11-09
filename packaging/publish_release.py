"""Verify tagged build inputs and publish complete unsigned preview releases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

from verify_release import verify

ROOT = Path(__file__).resolve().parent.parent
VERSION_PATTERN = r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)'


def git(root, *args, data=None):
    return subprocess.check_output(['git', '-C', str(root), *args], input=data)


def metadata(root, tag, commit):
    version = (root/'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(VERSION_PATTERN, version) or (tag and tag != 'v'+version):
        raise ValueError('Use a vMAJOR.MINOR.PATCH tag matching VERSION exactly.')
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or git(root, 'rev-parse', 'HEAD').decode().strip() != commit:
        raise ValueError('The checkout must match the requested source commit.')
    changelog = (root/'CHANGELOG.md').read_text(encoding='utf-8')
    section = re.search(r'^## '+re.escape(version)+r'(?:[ \t][^\n]*)?\n(.*?)(?=^## |\Z)',
                        changelog, re.MULTILINE | re.DOTALL)
    if not section or not section[1].strip():
        raise ValueError('Add a nonempty changelog section for VERSION before releasing.')
    return {'version': version, 'tag': 'v'+version, 'commit': commit, 'changes': section[1].strip()}


def asset_names(version):
    return [f'InkStudio-{version}-windows-x64-setup.exe',
            f'InkStudio-{version}-windows-x64-portable.zip',
            f'InkStudio-{version}-source.tar.gz',
            f'InkStudio-{version}-third-party-sources.zip',
            'SHA256SUMS.txt', 'release-manifest.json', 'verification-summary.json']


def verify_source(root, folder, info, release):
    """Compare every archived source byte with the exact Git commit and hash."""
    catalog = json.loads(git(root, 'show', info['commit']+':packaging/public-files.json'))
    names = sorted(catalog['files'])
    entries = {}
    for row in git(root, 'ls-tree', '-r', '-z', info['commit']).split(b'\0'):
        if not row:
            continue
        entry, name = row.split(b'\t', 1)
        mode, kind, oid = entry.decode().split()
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('Release source must contain ordinary Git files.')
        entries[name.decode()] = oid
    if set(entries) != set(names) or len(names) != len(set(names)):
        raise ValueError('Git source differs from the reviewed source catalog.')
    batch = git(root, 'cat-file', '--batch', data=''.join(entries[name]+'\n' for name in names).encode())
    identity = hashlib.sha256()
    prefix = 'ink-studio-'+info['version']+'/'
    offset = 0
    with tarfile.open(folder/f'InkStudio-{info["version"]}-source.tar.gz') as archive:
        if len(archive.getnames()) != len(names) or set(archive.getnames()) != {prefix+name for name in names}:
            raise ValueError('The source archive inventory differs from the tagged commit.')
        for name in names:
            end = batch.index(b'\n', offset)
            header = batch[offset:end].split()
            if header[1] != b'blob':
                raise ValueError('Unexpected Git object in release source.')
            size = int(header[2]); offset = end+1
            raw = batch[offset:offset+size]; offset += size+1
            member = archive.getmember(prefix+name)
            if not member.isfile() or archive.extractfile(member).read() != raw:
                raise ValueError('Source archive differs from tagged source: '+name)
            identity.update(name.encode()+b'\0'+raw+b'\0')
    if identity.hexdigest() != release['sourceSha256']:
        raise ValueError('Tagged source hash differs from the packaged source identity.')


def verify_candidate(root, folder, tag, commit, repository, run_url):
    info = metadata(root, tag, commit)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Choose a GitHub owner/repository.')
    if not re.fullmatch(r'https://github\.com/'+re.escape(repository)+r'/actions/runs/[0-9]+', run_url):
        raise ValueError('Provide the matching GitHub Actions run URL.')
    names = asset_names(info['version'])
    if {path.name for path in folder.iterdir()} != set(names):
        raise ValueError('The release must contain exactly the seven expected assets.')
    if any(not (folder/name).is_file() or (folder/name).is_symlink() for name in names):
        raise ValueError('Release assets must be ordinary files.')
    report = verify(folder)
    release = json.loads((folder/'release-manifest.json').read_text(encoding='utf-8'))
    if release['version'] != info['version'] or release['windowsSigning'] != 'unsigned':
        raise ValueError('This workflow publishes matching, explicitly unsigned previews only.')
    if json.loads((folder/'verification-summary.json').read_text(encoding='utf-8')) != report:
        raise ValueError('The uploaded verification report differs from the package audit.')
    verify_source(root, folder, info, release)
    assets = {}
    for name in names:
        path = folder/name
        with path.open('rb') as stream:
            digest = 'sha256:'+hashlib.file_digest(stream, 'sha256').hexdigest()
        assets[name] = {'path': path, 'size': path.stat().st_size, 'digest': digest}
    info.update(repository=repository, run_url=run_url, assets=assets)
    return info


def notes(info):
    base = 'https://github.com/'+info['repository']
    return (f"## Changes\n\n{info['changes']}\n\n"
            '## Downloads\n\n'
            'Choose the Windows x64 installer or portable ZIP under **Assets**. '
            'Matching application and third-party sources, SHA-256 checksums, the '
            'release manifest, and the verification report are included.\n\n'
            '**Windows packages are unsigned previews.** Publisher signing is not active. '
            'Checksums verify file integrity, not publisher identity.\n\n'
            'Inkscape and Ink/Stitch 3.3.0 are required. Windows packages include Python '
            'and application dependencies. Linux runs from source.\n\n'
            f"[Installation]({base}/blob/{info['tag']}/packaging/INSTALL.txt) · "
            f"[Linux setup]({base}/blob/{info['tag']}/packaging/README.md#linux)\n\n"
            '## Build provenance\n\n'
            f"[Verified build]({info['run_url']}) from commit `{info['commit']}`. "
            'Windows/Linux checks and the package audit passed. The source archive '
            'was checked byte for byte against this commit.\n')


def gh(args, data=None, missing_ok=False):
    result = subprocess.run(['gh', *args], input=json.dumps(data) if data is not None else None,
                            capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        try:
            body = json.loads(result.stdout)
        except ValueError:
            body = {}
        if missing_ok and str(body.get('status')) == '404':
            return ''
        raise RuntimeError('GitHub command failed: '+result.stderr.strip())
    return result.stdout


def api(endpoint, *, method='GET', data=None, missing_ok=False):
    args = ['api', '--method', method, endpoint]
    if data is not None:
        args += ['--input', '-']
    raw = gh(args, data=data, missing_ok=missing_ok)
    return json.loads(raw) if raw.strip() else None


def check_uploaded(release, assets, *, complete=False):
    found = set()
    for uploaded in release['assets']:
        name = uploaded['name']
        if name not in assets or name in found:
            raise ValueError('Unexpected or duplicate asset in release draft.')
        expected = assets[name]
        if (uploaded['state'] != 'uploaded' or uploaded['size'] != expected['size']
                or uploaded.get('digest') != expected['digest']):
            raise ValueError('Release asset does not match the verified build: '+name)
        found.add(name)
    if complete and found != set(assets):
        raise ValueError('Release upload is incomplete; the release remains a draft.')
    return found


def publish(info):
    endpoint = 'repos/'+info['repository']
    remote = api(endpoint+'/commits/'+info['tag'])
    if remote['sha'] != info['commit']:
        raise ValueError('The remote version tag differs from the verified source commit.')
    release = api(endpoint+'/releases/tags/'+info['tag'], missing_ok=True)
    if release:
        if release['tag_name'] != info['tag'] or release['target_commitish'] != info['commit']:
            raise ValueError('An existing release belongs to a different source revision.')
        if not release['draft']:
            return {'status': 'already-published', 'url': release['html_url']}
        if not release['prerelease']:
            raise ValueError('An existing draft is not marked as an unsigned preview prerelease.')
    else:
        release = api(endpoint+'/releases', method='POST', data={
            'tag_name': info['tag'], 'target_commitish': info['commit'],
            'name': 'Ink Studio '+info['version']+' - Unsigned preview',
            'body': notes(info), 'draft': True, 'prerelease': True, 'make_latest': 'false'})
    found = check_uploaded(release, info['assets'])
    missing = [str(asset['path']) for name, asset in info['assets'].items() if name not in found]
    if missing:
        # No --clobber: published files and mismatched draft assets are never replaced.
        gh(['release', 'upload', info['tag'], '--repo', info['repository'], *missing])
    uploaded = api(endpoint+'/releases/'+str(release['id']))
    check_uploaded(uploaded, info['assets'], complete=True)
    # Recheck the remote tag before making any download public.
    if api(endpoint+'/commits/'+info['tag'])['sha'] != info['commit']:
        raise ValueError('The remote version tag moved during upload; release remains a draft.')
    result = api(endpoint+'/releases/'+str(release['id']), method='PATCH', data={
        'draft': False, 'prerelease': True, 'make_latest': 'false',
        'name': 'Ink Studio '+info['version']+' - Unsigned preview', 'body': notes(info)})
    if result['draft'] or not result['prerelease']:
        raise ValueError('GitHub did not confirm the expected published preview state.')
    return {'status': 'published', 'url': result['html_url']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('metadata', 'verify', 'publish'))
    parser.add_argument('--tag', default='')
    parser.add_argument('--commit', required=True)
    parser.add_argument('--dist', type=Path, default=ROOT/'dist')
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', ''))
    parser.add_argument('--run-url', default='')
    args = parser.parse_args()
    if args.command == 'metadata':
        info = metadata(ROOT, args.tag, args.commit)
        result = {key: info[key] for key in ('version', 'tag', 'commit')}
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
                output.write(''.join(f'{key}={value}\n' for key, value in result.items()))
    else:
        info = verify_candidate(ROOT, args.dist.resolve(), args.tag, args.commit, args.repository, args.run_url)
        if args.command == 'publish':
            if not args.tag:
                raise ValueError('Publishing requires an explicit version tag.')
            result = publish(info)
        else:
            result = {'status': 'verified-without-publishing', 'tag': info['tag'],
                      'commit': info['commit'], 'assets': list(info['assets'])}
            if os.environ.get('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
                    summary.write('## Verified unsigned preview\n\n'+notes(info)+'\n\nAssets: '
                                  +', '.join(info['assets'])+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
