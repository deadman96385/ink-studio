"""Offline setup checks and shareable diagnostics, independent of the server.

Reports contain only fixed messages, check codes and numeric versions. We never
copy environment variables, file paths, exception text, logs or project data.
"""
import argparse
from datetime import datetime, timezone
import importlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile

import app_config
import studio_runtime
import studio_version

SCHEMA = 1
SUPPORTED_ENGINE = '3.3.0'
EDITOR_MODULES = ('lxml.etree', 'numpy', 'pystitch', 'PIL', 'shapely', 'fontTools',
                  'pillow_heif', 'diskcache', 'tinycss2', 'cssselect')
LOG = logging.getLogger('inkstudio.setup')


def enable_private_log(destination=None):
    """Keep bounded exception detail locally; this log never enters a report."""
    try:
        path = Path(destination) if destination else app_config.state_home() / 'logs/setup-private.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=128*1024, backupCount=1, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        LOG.addHandler(handler); LOG.setLevel(logging.DEBUG); LOG.propagate = False
        return handler
    except (OSError, ValueError):
        return None


def numeric_version(value):
    match = re.search(r'(?<![\d.])(\d+\.\d+(?:\.\d+)?)(?![\d.])', str(value))
    return match[1] if match else 'unknown'


def writable(path):
    """Probe the nearest existing directory without creating a project folder."""
    path = Path(path)
    try:
        while not path.exists():
            if path.parent == path:
                return False
            path = path.parent
        if not path.is_dir() or not path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            return False
        with tempfile.TemporaryFile(prefix='.inkstudio-write-check-', dir=path) as stream:
            stream.write(b'Ink Studio setup check'); stream.flush()
        return True
    except OSError:
        return False


def archive_python(engine):
    # The PyInstaller cookie records the embedded Python ABI. Read a bounded
    # tail, including room for the vendor's Windows signature overlay.
    with Path(engine).open('rb') as stream:
        stream.seek(0, 2); size = stream.tell()
        stream.seek(max(0, size - 4 * 1024 * 1024)); tail = stream.read()
    index = tail.rfind(b'MEI\014\013\012\013\016')
    if index < 0 or len(tail) - index < 88:
        return None
    return struct.unpack('!8sIIII64s', tail[index:index + 88])[4]


def _runtime(inkscape, engine, env, windows):
    data = Path(env.get('STUDIO_DATA', str(app_config.state_home() / 'data'))).expanduser().absolute()
    resources = Path(env.get('STUDIO_INKSTITCH_RESOURCES', str(engine.parent.parent))).absolute()
    extensions = Path(env.get('STUDIO_INKSCAPE_EXTENSIONS', str(inkscape.parent.parent / 'share/inkscape/extensions'))).absolute()
    config = Path(env.get('STUDIO_ENGINE_CONFIG', str(data / 'config/inkstitch'))).absolute()
    return studio_runtime.Runtime(windows, inkscape, engine, resources, extensions, data, config,
                                  env.get('STUDIO_HOST', '127.0.0.1'), int(env.get('STUDIO_PORT', '8801')))


def _engine_path(env, windows):
    if env.get('STUDIO_INKSTITCH'):
        return studio_runtime._executable(env['STUDIO_INKSTITCH'], ('inkstitch.exe', 'bin/inkstitch.exe') if windows else ('inkstitch', 'bin/inkstitch'))
    profile = Path(env.get('INKSCAPE_PROFILE_DIR') or (Path(env.get('APPDATA', Path.home())) / 'inkscape' if windows else Path(env.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'inkscape'))
    choices = [profile / 'extensions/inkstitch/bin' / ('inkstitch.exe' if windows else 'inkstitch')]
    if not windows:
        choices += [Path(shutil.which('inkstitch', path=env.get('PATH')) or '/opt/inkstitch/bin/inkstitch')]
    return next((p for p in choices if p.is_file()), choices[0])


def _inkscape_paths(env, windows):
    if env.get('STUDIO_INKSCAPE'):
        return [studio_runtime._executable(env['STUDIO_INKSCAPE'], ('inkscape.com', 'inkscape.exe') if windows else ('inkscape',))]
    found = shutil.which('inkscape.com' if windows else 'inkscape', path=env.get('PATH'))
    if windows:
        found = found or studio_runtime._windows_inkscape(env)
    choices = [Path(found)] if found else []
    if windows:
        from setup_windows import VERSION
        choices.append(app_config.state_home() / 'cache' / ('inkscape-' + VERSION) / 'inkscape/bin/inkscape.com')
    return choices


def _linux_tools(env):
    return [name for name in ('xvfb-run', 'Xvfb', 'pdftoppm') if not shutil.which(name, path=env.get('PATH'))]


def collect(env=None, system=None, apply=False):
    env = dict(os.environ if env is None else env)
    windows = (system or platform.system()) == 'Windows'
    checks = []
    report = {'schema': SCHEMA, 'appVersion': numeric_version(studio_version.current()),
              'platform': 'Windows' if windows else 'Linux', 'python': numeric_version(platform.python_version()),
              'architecture': '64-bit' if sys.maxsize > 2**32 else '32-bit',
              'installation': 'portable' if (app_config.app_root() / 'portable.txt').is_file() else 'installed' if app_config.packaged() else 'source',
              'createdAt': datetime.now(timezone.utc).isoformat(), 'privacy': 'No designs, personal paths, environment values or raw logs.',
              'versions': {}, 'checks': checks}

    def add(code, ok, message, action=''):
        checks.append({'code': code, 'status': 'ok' if ok else 'error', 'message': message, 'action': '' if ok else action})

    try:
        port = int(env.get('STUDIO_PORT', '8801'))
        if not 1 <= port <= 65535:
            raise ValueError()
        paths = _inkscape_paths(env, windows)
        engine = _engine_path(env, windows)
        inkscape = next((p for p in paths if p.is_file()), Path('/missing-inkscape'))
        runtime = _runtime(inkscape, engine, env, windows)
    except (ValueError, TypeError, OSError):
        LOG.debug('configuration failed', exc_info=True)
        add('configuration', False, 'The tool, folder or port configuration is invalid.', 'Open Settings or correct the saved configuration; choose port 1024–65535.')
        return finish(report), None

    state_ok = writable(app_config.state_home()) and writable(app_config.settings_path().parent)
    data_ok = all(writable(path) for path in (runtime.data, runtime.engine_config,
                  *(runtime.data / name for name in ('projects', 'exports', 'assets', 'cache'))))
    add('state-writable', state_ok, 'Application state and settings folder access.', 'Choose a writable portable folder or fix access to your user settings folder.')
    add('data-writable', data_ok, 'Projects and private engine settings folder access.', 'Choose a writable Projects folder in Settings or with --data. Existing designs are not moved.')
    add('inkstitch-found', engine.is_file(), 'Ink/Stitch installation discovery.', 'Install Ink/Stitch 3.3.0, then choose its executable or installation folder in Settings or with --inkstitch.')
    engine_ok = False
    if engine.is_file():
        try:
            version = numeric_version((runtime.resources / 'VERSION').read_text(encoding='utf-8'))
            report['versions']['inkstitch'] = version
            add('inkstitch-version', version == SUPPORTED_ENGINE, 'Ink/Stitch version compatibility.', 'This adapter supports Ink/Stitch 3.3.0. Select that bundle; other versions need a validated adapter.')
            library = engine.parent / ('python311.dll' if windows else 'libpython3.11.so.1.0')
            bundle_ok = archive_python(engine) == 311 and library.is_file() and (engine.parent / 'base_library.zip').is_file()
            add('engine-bundle', bundle_ok, 'Ink/Stitch Python 3.11 bundle compatibility.', 'Select the complete Ink/Stitch 3.3.0 installation, including its bundled Python 3.11 files.')
            resources_ok = (runtime.resources / 'fonts').is_dir()
            add('engine-resources', resources_ok, 'Bundled embroidery font resources.', 'Reinstall the complete Ink/Stitch bundle or correct the resources override.')
            engine_ok = version == SUPPORTED_ENGINE and bundle_ok and resources_ok
        except (OSError, ValueError, struct.error):
            LOG.debug('engine bundle validation failed', exc_info=True)
            add('engine-bundle', False, 'The Ink/Stitch bundle is incomplete or unreadable.', 'Reinstall Ink/Stitch 3.3.0 or choose its complete installation folder.')

    inkscape_ok = False
    if state_ok and data_ok:
        for candidate in paths:
            if not candidate.is_file():
                continue
            candidate_runtime = _runtime(candidate, engine, env, windows)
            try:
                build = studio_runtime.execute([str(candidate), '--version'], runtime=candidate_runtime, timeout=20).decode('utf-8', 'replace')
                actions = studio_runtime.execute([str(candidate), '--action-list'], runtime=candidate_runtime, timeout=30)
                report['versions']['inkscape'] = numeric_version(build)
                if b'object-trace ' in actions:
                    runtime = candidate_runtime; inkscape_ok = True; break
            except (OSError, ValueError):
                LOG.debug('Inkscape probe failed', exc_info=True)
                pass
    message = 'Inkscape execution and image tracing support.'
    action = 'Choose a compatible Inkscape with object-trace support in Settings or with --inkscape.'
    if windows and not env.get('STUDIO_INKSCAPE'):
        action += ' Prepare private Inkscape to use the verified cache or download it once; offline instructions are in the guide.'
    add('inkscape-tracing', inkscape_ok, message, action)
    extensions_ok = (runtime.extensions / 'inkex').is_dir()
    add('inkscape-extensions', extensions_ok if inkscape_ok else False, 'Inkscape Python extension modules.', 'Select a complete Inkscape installation or set STUDIO_INKSCAPE_EXTENSIONS to its extensions folder.')

    missing = []
    for name in (*EDITOR_MODULES, *(('pypdfium2',) if windows else ())):
        try:
            importlib.import_module(name)
        except (ImportError, OSError):
            LOG.debug('editor module import failed: %s', name, exc_info=True)
            missing.append(name)
    add('editor-dependencies', not missing, 'Editor Python dependencies.' + (' Missing: ' + ', '.join(missing) + '.' if missing else ''),
        'Reinstall the full Windows package, or install native/requirements.txt into the Linux editor environment.')
    helper_ok = True
    if windows and app_config.packaged():
        helper_ok = all((studio_runtime.ROOT / name).is_file() for name in ('engine-host.exe', 'windows-command.exe'))
    elif not windows:
        helper_ok = runtime.bridge().is_file() and os.access(runtime.bridge(), os.X_OK)
        absent = _linux_tools(env)
        add('linux-tools', not absent, 'Linux tracing and PDF tools.' + (' Missing: ' + ', '.join(absent) + '.' if absent else ''),
            'Install Xvfb (including xvfb-run) and Poppler utilities using your distribution package manager; see the Linux guide.')
    add('engine-helper', helper_ok, 'Platform engine helpers.', 'Reinstall the complete Windows package, or install a C compiler and run the Linux launcher again.')
    if engine_ok and inkscape_ok and extensions_ok and state_ok and data_ok and helper_ok:
        try:
            # Runtime.environment isolates the worker from the desktop engine's
            # settings. Use the supplied paths even before current() is cached.
            output = studio_runtime.execute(runtime.worker_command('--native-diagnostics'), runtime=runtime, timeout=60)
            result = json.loads(output)
            probe_ok = result.get('ok') is True and numeric_version(result.get('python', '')).startswith('3.11.')
            if probe_ok:
                report['versions']['enginePython'] = numeric_version(result['python'])
            add('engine-probe', probe_ok, 'Embroidery engine, fonts/PDF runtime imports.', 'Reinstall the supported Ink/Stitch bundle and its required system libraries, then check again.')
        except (OSError, ValueError, TypeError):
            LOG.debug('engine initialization probe failed', exc_info=True)
            add('engine-probe', False, 'The embroidery engine could not initialize.', 'Reinstall the supported Ink/Stitch bundle and its required system libraries, then check again. See the installation guide.')
    else:
        checks.append({'code': 'engine-probe', 'status': 'skipped', 'message': 'Engine initialization waits for the checks above.', 'action': ''})
    if inkscape_ok and not missing and state_ok and data_ok:
        try:
            result = json.loads(studio_runtime.execute([sys.executable, '-X', 'utf8', str(studio_runtime.ROOT / 'setup_pdf_probe.py')], runtime=runtime, timeout=45))
            add('pdf-runtime', result.get('ok') is True, 'PDF generation and preview runtime.', 'Reinstall the Windows package or install the Pango/Cairo and PDF libraries listed in the Linux guide.')
        except (OSError, ValueError, TypeError):
            LOG.debug('PDF initialization probe failed', exc_info=True)
            add('pdf-runtime', False, 'PDF generation could not initialize.', 'Reinstall the Windows package or install the Pango/Cairo and PDF libraries listed in the Linux guide.')
    else:
        checks.append({'code': 'pdf-runtime', 'status': 'skipped', 'message': 'PDF initialization waits for the checks above.', 'action': ''})
    report = finish(report)
    if apply and report['ready']:
        os.environ.update(STUDIO_INKSCAPE=str(runtime.inkscape), STUDIO_INKSTITCH=str(runtime.inkstitch),
                          STUDIO_ENGINE_CONFIG=str(runtime.engine_config))
        studio_runtime.current.cache_clear(); studio_runtime.description.cache_clear()
    return report, runtime


def finish(report):
    report['ready'] = bool(report['checks']) and all(c['status'] == 'ok' for c in report['checks'])
    report['status'] = 'ready' if report['ready'] else 'needs-setup'
    return report


def failure(code, message, action):
    return finish({'schema': SCHEMA, 'appVersion': numeric_version(studio_version.current()),
                   'platform': platform.system(), 'versions': {},
                   'privacy': 'No designs, personal paths, environment values or raw logs.',
                   'checks': [{'code': code, 'status': 'error', 'message': message, 'action': action}]})


def check(prepare_tools=False, apply=False, offline=False):
    try:
        app_config.prepare_environment()
    except (ValueError, TypeError, OSError):
        LOG.debug('saved settings could not be loaded', exc_info=True)
        return failure('settings-invalid', 'The saved settings could not be read.', 'Open Settings and correct the configuration. Keep your existing project folder.'), None
    report, runtime = collect(apply=apply)
    if prepare_tools and runtime and not report['ready']:
        failed = {c['code'] for c in report['checks'] if c['status'] == 'error'}
        if runtime.windows and not os.environ.get('STUDIO_INKSCAPE') and 'inkscape-tracing' in failed and failed <= {'inkscape-tracing', 'inkscape-extensions'}:
            try:
                from setup_windows import install_portable
                executable = install_portable(app_config.state_home() / 'cache', offline=offline)
                os.environ['STUDIO_INKSCAPE'] = str(executable)
                return collect(apply=apply)
            except (OSError, ValueError, subprocess.SubprocessError):
                LOG.debug('private Inkscape preparation failed', exc_info=True)
                report['checks'].append({'code': 'inkscape-download', 'status': 'error',
                    'message': 'Private Inkscape could not be prepared. No installed tools were changed.',
                    'action': 'Check free disk space and the Internet connection, choose a compatible installed Inkscape, or seed the verified archive as described in the offline setup guide.'})
                return finish(report), runtime
    return report, runtime


def emit(report, destination=None):
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if destination:
        path = Path(destination).expanduser().absolute()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite a design or saved configuration through a typo.
        if path.exists():
            try:
                if json.loads(path.read_text(encoding='utf-8')).get('schema') != SCHEMA or 'checks' not in json.loads(path.read_text(encoding='utf-8')):
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise ValueError('Choose a new diagnostics filename; the existing file is not a setup report.') from None
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.diagnostics-', delete=False) as stream:
            temporary = Path(stream.name); stream.write(text + '\n')
        temporary.replace(path)
    print(text, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-tools', action='store_true')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--report', type=Path)
    options = parser.parse_args()
    enable_private_log()
    report, _ = check(prepare_tools=options.prepare_tools, offline=options.offline)
    emit(report, options.report)
    return 0 if report['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
