"""Audit the actual Git index or a fresh source tree before publication.

Only reviewed paths in public-files.json are allowed. Reports contain check
categories and relative filenames, never matched secrets or file contents.
"""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
CATALOG = 'packaging/public-files.json'
PRIVATE_ROOTS = frozenset({'designs', 'patterns', 'native-backups', 'backups', 'work', 'data', 'config',
                           'logs', 'cache', 'runtime', 'build', 'dist', '.native-runtime', '.venv-native', '.venv', 'node_modules'})
PRIVATE_SUFFIXES = ('.project.json', '.pes', '.dst', '.exp', '.jef', '.vp3', '.hus', '.xxx', '.emb',
                    '.zip', '.7z', '.bak', '.backup', '.db', '.sqlite', '.sqlite3', '.log', '.pyc',
                    '.pfx', '.p12', '.pem', '.key', '.exe', '.dll', '.pyd')
BINARY_FILES = frozenset({'packaging/windows/ink-studio.ico', 'packaging/windows/ink-studio.png',
                          'docs/assets/editor.jpg', 'docs/assets/stitches.jpg', 'docs/assets/print.jpg',
                          'native/test-fixtures/fonts/DejaVuSans-Bold.ttf', 'native/test-fixtures/fonts/SourceSans3-Bold.otf'})
PRIVATE_DOC_STEMS = frozenset({'release_readiness', 'architecture_diagram', 'motion_plan',
                               'web_port_viability', 'work_map'})
PATTERNS = {
    'private-network': re.compile(r'\btail[0-9a-f]{5,}(?:\.ts\.net)?\b|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net\b|https?://[^\s/]+\.local(?:[:/]|\b)', re.I),
    'private-network-address': re.compile(r'\b(?:100\.(?:6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])|192\.168|10\.[0-9]{1,3}|172\.(?:1[6-9]|2[0-9]|3[01]))\.[0-9]{1,3}\.[0-9]{1,3}\b'),
    'personal-home-path': re.compile(r'[A-Z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]+|/mnt/[a-z]/Users/[A-Za-z0-9_.-]+|/home/(?!user(?:/|\b)|example(?:/|\b))[A-Za-z0-9_.-]+/', re.I),
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'stored-project-reference': re.compile(r'''/designs/[^\s'"/]+\.(?:svg|pes|dst|exp|jef|project\.json)\b''', re.I),
    'credential-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{20,}|tskey-(?:auth|api|client)-[A-Za-z0-9_-]{15,}|sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{35})\b'),
}
# Fixed SVG namespace identifiers identify attributes, not network services.
XML_NAMESPACE_URIS = ('https://inkstudio.local/effects', 'https://inkstudio.local/svg-preparation')


def safe_path(name):
    path = PurePosixPath(name)
    return bool(path.parts) and path.as_posix()==name and not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name and not any(ord(c)<32 for c in name)


def inspect_files(files, approved, modes=None, forbidden_values=()):
    findings = []
    modes = modes or {}
    approved = set(approved)
    for name, raw in files.items():
        path = PurePosixPath(name)
        code = None
        if not safe_path(name):
            code = 'unsafe-path'
        elif name not in approved:
            code = 'unreviewed-path'
        elif path.parts[0].lower() in PRIVATE_ROOTS or '__pycache__' in path.parts or '.git' in path.parts:
            code = 'private-state-path'
        elif path.stem.lower() in PRIVATE_DOC_STEMS or name.startswith('packaging/signpath/'):
            code = 'internal-preparation-file'
        elif name.lower().endswith(PRIVATE_SUFFIXES) or path.name.startswith('.env'):
            code = 'private-or-generated-file'
        elif modes.get(name) == '120000':
            code = 'symbolic-link'
        elif len(raw) > 5*1024*1024:
            code = 'oversized-source-file'
        if code:
            findings.append({'path': name, 'code': code}); continue
        text = raw.decode('utf-8', errors='ignore')
        for category, pattern in PATTERNS.items():
            candidate = text
            if category == 'private-network':
                for namespace in XML_NAMESPACE_URIS:
                    candidate = re.sub(re.escape(namespace)+r'''(?=[\s'"<>)}\],;]|$)''', '', candidate)
            if pattern.search(candidate):
                findings.append({'path': name, 'code': category})
        if any(value and value.casefold() in text.casefold() for value in forbidden_values):
            findings.append({'path': name, 'code': 'private-value'})
        if path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.ico', '.ttf', '.otf') and name not in BINARY_FILES:
            findings.append({'path': name, 'code': 'unreviewed-binary-asset'})
    for name in sorted(approved-set(files)):
        findings.append({'path': name, 'code': 'missing-reviewed-source'})
    return {'passed': not findings, 'checkedFiles': len(files), 'findings': findings}


def index_files(root):
    entries = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--stage', '-z'])
    rows = [entry.split(b'\t', 1) for entry in entries.split(b'\0') if entry]
    modes, objects = {}, []
    for metadata, name in rows:
        mode, oid, stage = metadata.decode().split()
        if stage != '0':
            raise ValueError('Resolve merge conflicts before publication.')
        name = name.decode('utf-8'); modes[name] = mode; objects.append((name, oid))
    if not objects:
        raise ValueError('Stage the reviewed source files before auditing the index.')
    payload = ''.join(oid+'\n' for _, oid in objects).encode()
    result = subprocess.run(['git', '-C', str(root), 'cat-file', '--batch'], input=payload, capture_output=True, check=True).stdout
    files = {}; offset = 0
    for name, _ in objects:
        end = result.index(b'\n', offset)
        header = result[offset:end].split(); size = int(header[2]); offset = end+1
        if header[1] != b'blob':
            raise ValueError('Only ordinary source blobs may be published.')
        files[name] = result[offset:offset+size]; offset += size+1
    return files, modes


def audit(root=ROOT, tracked=False, forbidden_values=()):
    root = Path(root).resolve()
    if tracked:
        files, modes = index_files(root)
        if CATALOG not in files:
            raise ValueError('The reviewed source catalog must be staged.')
        catalog = json.loads(files[CATALOG])
    else:
        catalog = json.loads((root/CATALOG).read_text(encoding='utf-8'))
        files, modes = {}, {}
        for path in root.rglob('*'):
            relative = path.relative_to(root)
            if '.git' in relative.parts or '__pycache__' in relative.parts:
                continue
            if path.is_symlink():
                files[relative.as_posix()] = b''; modes[relative.as_posix()] = '120000'
            elif path.is_file():
                files[relative.as_posix()] = path.read_bytes()
    names = catalog['files']
    if not isinstance(names, list) or len(names) != len(set(names)) or not all(safe_path(n) for n in names):
        raise ValueError('Invalid reviewed source catalog.')
    return inspect_files(files, names, modes, forbidden_values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--tracked', '--index', dest='tracked', action='store_true', help='Inspect staged Git blobs, including their real contents')
    args = parser.parse_args()
    try:
        report = audit(args.root, args.tracked)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        report = {'passed': False, 'findings': [{'code': 'audit-could-not-complete'}]}
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
