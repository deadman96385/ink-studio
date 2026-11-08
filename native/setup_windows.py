"""Configure a private, verified portable Inkscape when tracing needs one."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
import urllib.request

ROOT = Path(__file__).absolute().parent.parent
VERSION = '1.4.4'
URL = 'https://media.inkscape.org/dl/resources/file/inkscape-1.4.4_2026-05-05_dcaf3e7-x64_mHK170m.7z'
SHA256 = 'c4dbd64a92628abe7d7316c43f9325396e4d48417866027ee3d993d4f5b54c6a'


def install_portable(runtime, offline=False):
    """Download directly from the vendor into the user's chosen cache."""
    runtime = Path(runtime)
    archive = runtime / 'downloads' / ('inkscape-' + VERSION + '-x64.7z')
    archive.parent.mkdir(parents=True, exist_ok=True)
    def digest(path):
        with path.open('rb') as stream:return hashlib.file_digest(stream, 'sha256').hexdigest()
    if not archive.exists() or digest(archive) != SHA256:
        if offline:
            raise ValueError('Offline setup needs the verified Inkscape archive in cache/downloads. See the user guide.')
        print('Downloading portable Inkscape ' + VERSION + ' from inkscape.org (about 110 MB)…', file=sys.stderr, flush=True)
        temporary = archive.with_suffix('.download')
        with urllib.request.urlopen(URL, timeout=60) as response, temporary.open('wb') as target:
            while block := response.read(1024 * 1024):target.write(block)
        if digest(temporary) != SHA256:
            temporary.unlink()
            raise ValueError('The portable Inkscape download failed its SHA256 check.')
        temporary.replace(archive)
    import studio_runtime
    runtime = runtime.absolute()
    folder = runtime / ('inkscape-' + VERSION)

    def probe(candidate):
        executable = candidate / 'inkscape/bin/inkscape.com'
        if not executable.is_file():
            return False
        context = studio_runtime.Runtime(True, executable, candidate / 'unused-engine.exe', candidate, candidate, runtime / 'helper-state',
                                         runtime / 'helper-state/config', '127.0.0.1', 8801)
        try:
            return b'object-trace ' in studio_runtime.execute([str(executable), '--action-list'], runtime=context, timeout=30)
        except (OSError, ValueError):
            return False

    if probe(folder):
        return folder / 'inkscape/bin/inkscape.com'
    # Validate the complete extraction before publishing it. TemporaryDirectory
    # owns only the fresh directory created by this call.
    with tempfile.TemporaryDirectory(prefix='.inkscape-setup-', dir=runtime) as staging:
        stage = Path(staging) / 'payload'; stage.mkdir()
        subprocess.run(['tar.exe', '-xf', str(archive), '-C', str(stage)], check=True,
                       timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
        if not probe(stage):
            raise ValueError('The private Inkscape extraction is incomplete or does not support tracing. Check available disk space.')
        if not stage.resolve().is_relative_to(runtime.resolve()) or folder.resolve().parent != runtime.resolve():
            raise ValueError('Unexpected private tool cache destination.')
        if folder.exists():
            folder.rename(runtime / (folder.name + '.previous-' + uuid.uuid4().hex[:8]))
        stage.rename(folder)
    return folder / 'inkscape/bin/inkscape.com'


def main():
    if os.name != 'nt':
        raise SystemExit('This configuration helper is for Windows; Linux uses its installed Inkscape.')
    import studio_runtime
    try:
        if studio_runtime.description()['imageTracing']:
            print('The configured Inkscape supports tracing.')
            return
    except ValueError:
        pass
    runtime = ROOT / '.native-runtime'
    executable = install_portable(runtime)
    settings = runtime / 'settings.json'
    previous = json.loads(settings.read_text(encoding='utf-8-sig')) if settings.exists() else {}
    previous['inkscape'] = str(executable)
    previous['portableInkscape'] = {'version': VERSION, 'url': URL, 'sha256': SHA256}
    stage = settings.with_suffix('.tmp')
    stage.write_text(json.dumps(previous, indent=2), encoding='utf-8')
    stage.replace(settings)
    print('Studio will use portable Inkscape ' + VERSION + '. The desktop installation is unchanged.')


if __name__ == '__main__':
    main()
