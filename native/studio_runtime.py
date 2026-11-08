"""Platform boundary for the local editor; Linux containers remain supported.

Only this module discovers installations, constructs engine commands and owns
child processes. Windows workers use the Python shipped with Ink/Stitch in an
isolated process, never in the editor's Python interpreter.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).absolute().parent
_BUILD_LOCK = threading.Lock()


def _executable(value, names):
    path = Path(value).expanduser().absolute()
    if path.is_dir():
        path = next((path / name for name in names if (path / name).is_file()), path / names[0])
    return path


def _windows_inkscape(env):
    candidates = []
    for key in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
        if env.get(key):
            candidates.append(Path(env[key]) / 'Inkscape' / 'bin' / 'inkscape.com')
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\inkscape.exe') as key:
                    candidates.insert(0, Path(winreg.QueryValue(key, None)).with_suffix('.com'))
            except OSError:
                pass
    return next((p for p in candidates if p.is_file()), None)


@dataclass(frozen=True)
class Runtime:
    windows: bool
    inkscape: Path
    inkstitch: Path
    resources: Path
    extensions: Path
    data: Path
    engine_config: Path
    host: str
    port: int

    def resource(self, *parts):
        return self.resources.joinpath(*parts)

    def environment(self):
        env = dict(os.environ)
        env['PATH'] = str(self.inkscape.parent) + os.pathsep + env.get('PATH', '')
        env['INKSCAPE_COMMAND'] = str(self.inkscape.with_suffix('.exe') if self.windows else self.inkscape)
        env['STUDIO_INKSTITCH'] = str(self.inkstitch)
        env['LANGUAGE'] = 'en'
        env['PYTHONUTF8'] = '1'
        env['STUDIO_ENGINE_CONFIG'] = str(self.engine_config)
        if self.windows:
            env['STUDIO_ENGINE_CONFIG'] = str(self.engine_config)
            env['INKSCAPE_PROFILE_DIR'] = str(self.data / 'inkscape-profile')
            env['WEASYPRINT_DLL_DIRECTORIES'] = str(self.inkscape.parent)
            # GLib otherwise autostarts a shared gdbus.exe inside a temporary
            # engine Job Object. Closing that job disconnects unrelated jobs.
            # An unavailable bus makes GApplication use its local, non-unique
            # mode. Studio's workers need no desktop IPC (selection is captured
            # directly); this environment is private to our child processes.
            # See gio/gapplicationimpl-dbus.c:g_application_impl_register.
            env['DBUS_SESSION_BUS_ADDRESS'] = 'disabled:'
        else:
            env['LC_ALL'] = 'C.UTF-8'
        return env

    def bridge(self):
        if not self.windows:
            return Path(os.environ.get('STUDIO_ENGINE_HELPER', '/usr/local/bin/native-inkstitch-info'))
        packaged = ROOT / 'engine-host.exe'
        if packaged.is_file():
            return packaged
        source = ROOT / 'engine_runtime_windows.cs'
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        target = self.data / 'runtime' / ('engine-host-' + digest + '.exe')
        with _BUILD_LOCK:
            if not target.exists():
                compiler = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319' / 'csc.exe'
                if not compiler.is_file():
                    raise ValueError('The Windows engine helper needs the .NET Framework 4 C# compiler (64-bit).')
                target.parent.mkdir(parents=True, exist_ok=True)
                result = subprocess.run([str(compiler), '/nologo', '/platform:x64', '/out:' + str(target), str(source)],
                                        capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode:
                    target.unlink(missing_ok=True)
                    raise ValueError('Could not build the Windows engine helper: ' + result.stdout.decode('utf-8', 'replace')[-1600:])
        return target

    def windows_launcher(self):
        packaged=ROOT/'windows-command.exe'
        if packaged.is_file():return packaged
        source=ROOT/'windows_command.cs'
        digest=hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        target=self.data/'runtime'/('windows-command-'+digest+'.exe')
        with _BUILD_LOCK:
            if not target.exists():
                compiler=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
                target.parent.mkdir(parents=True,exist_ok=True)
                result=subprocess.run([str(compiler),'/nologo','/platform:x64','/out:'+str(target),str(source)],capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode:raise ValueError('Could not build the hidden Windows launcher: '+result.stdout.decode('utf-8','replace'))
        return target

    def worker_command(self, *args, temporary=None):
        if self.windows:
            return [str(self.bridge()), str(self.inkstitch.parent), str(ROOT / 'engine_runtime.py'), *map(str, args)]
        return ['/usr/bin/env', 'LD_LIBRARY_PATH=' + str(self.inkstitch.parent), 'LANGUAGE=en',
                'STUDIO_ENGINE_BOOTSTRAP=' + str(ROOT / 'engine_runtime.py'),
                *(['TMPDIR=' + str(temporary)] if temporary else []), str(self.bridge()), *map(str, args)]

    def command(self, args):
        args = list(map(str, args))
        if self.windows and args[0] == 'xvfb-run':
            args = args[2:]  # Linux's "xvfb-run -a"; Windows has its own GUI session.
            if any('object-trace:' in arg for arg in args) and not description()['imageTracing']:
                raise ValueError('Image tracing requires Inkscape 1.4 or newer. Upgrade the installed Inkscape to use this tool.')
        if args[0] == 'inkscape':
            args[0] = str(self.inkscape)
        elif self.windows and args[0] == str(self.inkstitch):
            # This also isolates custom-font settings and the stitch cache.
            args = self.worker_command('--native-cli', *args[1:])
        if self.windows and Path(args[0]).name.lower() in ('inkscape.exe','inkscape.com') and not any(arg.startswith('--app-id-tag=') for arg in args):
            args.insert(1,'--app-id-tag=inkstudio-'+uuid.uuid4().hex)
        return args


def discover(env=None, system=None):
    env = os.environ if env is None else env
    windows = (system or platform.system()) == 'Windows'
    settings={}
    if windows:
        config=ROOT.parent/'.native-runtime'/'settings.json'
        if config.is_file():settings=json.loads(config.read_text(encoding='utf-8-sig'))
    inkscape = env.get('STUDIO_INKSCAPE') or settings.get('inkscape') or (shutil.which('inkscape.com') if windows else shutil.which('inkscape'))
    if not inkscape and windows:
        inkscape = _windows_inkscape(env)
    if not inkscape:
        raise ValueError('Inkscape was not found. Set STUDIO_INKSCAPE to its executable or bin directory.')
    inkscape = _executable(inkscape, ('inkscape.com', 'inkscape.exe') if windows else ('inkscape',))
    if not inkscape.is_file():
        raise ValueError('Inkscape executable not found: ' + str(inkscape))
    engine = env.get('STUDIO_INKSTITCH')
    if not engine and windows:
        profile = Path(env.get('INKSCAPE_PROFILE_DIR') or Path(env.get('APPDATA', Path.home())) / 'inkscape')
        candidate = profile / 'extensions' / 'inkstitch' / 'bin' / 'inkstitch.exe'
        if not candidate.is_file():
            # Inkscape can use a non-default profile/extension directory.
            result = subprocess.run([str(inkscape), '--user-data-directory'], capture_output=True, timeout=20,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            profile = Path(result.stdout.decode('utf-8', 'replace').strip())
            candidate = profile / 'extensions' / 'inkstitch' / 'bin' / 'inkstitch.exe'
        engine = candidate
    engine = _executable(engine or '/opt/inkstitch/bin/inkstitch', ('inkstitch.exe', 'bin/inkstitch.exe') if windows else ('inkstitch', 'bin/inkstitch'))
    if not engine.is_file():
        raise ValueError('Ink/Stitch was not found. Set STUDIO_INKSTITCH to its executable or installation directory.')
    resources = Path(env.get('STUDIO_INKSTITCH_RESOURCES', engine.parent.parent)).absolute()
    extensions = Path(env.get('STUDIO_INKSCAPE_EXTENSIONS', inkscape.parent.parent / 'share' / 'inkscape' / 'extensions')).absolute()
    if windows:
        default_data = Path(env.get('LOCALAPPDATA', Path.home())) / 'Ink Studio' / 'data'
    else:
        default_data = Path('/designs/native') if Path('/designs').exists() else Path(env.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'ink-studio'
    data = Path(env.get('STUDIO_DATA', default_data)).expanduser().absolute()
    config = Path(env.get('STUDIO_ENGINE_CONFIG') or (data / 'config' / 'inkstitch' if windows else Path(env.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'inkstitch')).absolute()
    port = int(env.get('STUDIO_PORT', '8797'))
    if not 1 <= port <= 65535:
        raise ValueError('STUDIO_PORT must be between 1 and 65535.')
    return Runtime(windows, inkscape, engine, resources, extensions, data, config,
                   env.get('STUDIO_HOST', '127.0.0.1' if windows else '0.0.0.0'), port)


@lru_cache(maxsize=1)
def current():
    return discover()


def configure_imports():
    path = str(current().extensions)
    if path not in sys.path:
        sys.path.append(path)


def resource(*parts):
    return current().resource(*parts)


def worker_command(*args, temporary=None):
    return current().worker_command(*args, temporary=temporary)


class _WindowsJob:
    """Close-on-exit ownership of an engine process and all its descendants."""
    def __init__(self, process):
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [('ProcessTime', c.c_int64), ('JobTime', c.c_int64), ('Flags', w.DWORD),
                        ('MinWorkingSet', c.c_size_t), ('MaxWorkingSet', c.c_size_t), ('ActiveProcesses', w.DWORD),
                        ('Affinity', c.c_size_t), ('Priority', w.DWORD), ('Scheduling', w.DWORD)]
        class IO(c.Structure):
            _fields_ = [(name, c.c_uint64) for name in ('ReadOps', 'WriteOps', 'OtherOps', 'ReadBytes', 'WriteBytes', 'OtherBytes')]
        class Extended(c.Structure):
            _fields_ = [('Basic', Basic), ('IO', IO), ('ProcessMemory', c.c_size_t), ('JobMemory', c.c_size_t),
                        ('PeakProcessMemory', c.c_size_t), ('PeakJobMemory', c.c_size_t)]
        self.api = c.WinDLL('kernel32', use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        self.api.SetInformationJobObject.restype = w.BOOL
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.AssignProcessToJobObject.restype = w.BOOL
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.api.CloseHandle.restype = w.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)
        info = Extended()
        info.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.api.SetInformationJobObject(self.handle, 9, c.byref(info), c.sizeof(info)) or not self.api.AssignProcessToJobObject(self.handle, w.HANDLE(process._handle)):
            error = c.get_last_error()
            self.close()
            raise OSError(error, 'Could not contain the engine process in a Windows Job Object')

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def execute(args, timeout=180, headless=False, runtime=None):
    runtime = runtime or current()
    env = runtime.environment()
    if headless and not runtime.windows:
        env['DISPLAY'] = ''
    if runtime.windows:
        from windows_desktop import startup_info,name
        launcher=str(runtime.windows_launcher())
        env['STUDIO_WINDOWS_LAUNCHER']=launcher
        env['STUDIO_WINDOWS_DESKTOP']=name()
        options = {'creationflags': subprocess.CREATE_NO_WINDOW, 'startupinfo': startup_info()}
    else:options = {'start_new_session': True}
    command=runtime.command(args)
    if runtime.windows:command=[launcher,name(),*command]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, **options)
    job = None
    try:
        if runtime.windows:
            job = _WindowsJob(process)
        try:
            out, err = process.communicate(timeout=timeout)
        except BaseException as error:
            if job:
                job.close()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL) if not runtime.windows else process.kill()
                except (ProcessLookupError, PermissionError):
                    pass
            process.communicate()
            if isinstance(error, subprocess.TimeoutExpired):
                raise ValueError('Ink/Stitch took too long. Try fewer objects or a smaller design.') from error
            raise
        if process.returncode:
            raise ValueError('Ink/Stitch could not generate this design. ' + err.decode('utf-8', 'replace').strip()[-1800:])
        return out
    finally:
        if job:
            job.close()
        if process.poll() is None:
            process.kill()
            process.communicate()


@lru_cache(maxsize=1)
def description():
    import studio_version
    runtime = current()
    version = runtime.resource('VERSION').read_text(encoding='utf-8').strip()
    build = execute([str(runtime.inkscape), '--version'], timeout=20).decode('utf-8', 'replace').strip()
    actions = execute([str(runtime.inkscape), '--action-list'], timeout=30).decode('utf-8', 'replace')
    return {'appVersion': studio_version.current(), 'platform': platform.system(), 'inkscape': build, 'inkstitchVersion': version,
            'sourceDirectory': str(ROOT),
            'inkscapePath': str(runtime.inkscape), 'inkstitchPath': str(runtime.inkstitch),
            'dataDirectory': str(runtime.data), 'imageTracing': 'object-trace ' in actions,
            'engineDisplay': 'private-desktop' if runtime.windows else 'linux-display',
            'desktopUrl': os.environ.get('STUDIO_DESKTOP_URL', ''),
            'respiraUrl': os.environ.get('STUDIO_RESPIRA_URL', '')}
