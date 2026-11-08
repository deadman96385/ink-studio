"""Platform discovery and process ownership checks, runnable on both OSes."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

import studio_runtime as runtime


class RuntimeTests(unittest.TestCase):
    def fixture(self, directory, windows):
        root = Path(directory)
        inkscape = root / 'Inkscape with spaces' / 'bin' / ('inkscape.com' if windows else 'inkscape')
        engine = root / 'Ink Stitch' / 'bin' / ('inkstitch.exe' if windows else 'inkstitch')
        for executable in (inkscape, engine):
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.touch()
        return {'STUDIO_INKSCAPE': str(inkscape), 'STUDIO_INKSTITCH': str(engine),
                'STUDIO_DATA': str(root / 'Designs café'), 'LOCALAPPDATA': str(root), 'XDG_CONFIG_HOME': str(root / 'config')}

    def test_discovery_on_both_platforms(self):
        for system in ('Windows', 'Linux'):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as directory:
                result = runtime.discover(self.fixture(directory, system == 'Windows'), system)
                self.assertEqual(result.resources, result.inkstitch.parent.parent)
                self.assertEqual(result.command(['inkscape', '--query-all'])[0], str(result.inkscape))
                self.assertEqual(result.host, '127.0.0.1' if system == 'Windows' else '0.0.0.0')
                self.assertIn('café', str(result.data))

    def test_directories_and_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.fixture(directory, True)
            env['STUDIO_INKSCAPE'] = str(Path(env['STUDIO_INKSCAPE']).parent)
            env['STUDIO_INKSTITCH'] = str(Path(env['STUDIO_INKSTITCH']).parent.parent)
            self.assertTrue(runtime.discover(env, 'Windows').inkstitch.is_file())
            env['STUDIO_PORT'] = '70000'
            with self.assertRaisesRegex(ValueError, 'STUDIO_PORT'):
                runtime.discover(env, 'Windows')
            env['STUDIO_INKSCAPE'] = str(Path(directory) / 'missing.exe')
            with self.assertRaisesRegex(ValueError, 'Inkscape executable not found'):
                runtime.discover(env, 'Windows')

    def test_linux_worker_command_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            result = runtime.discover(self.fixture(directory, False), 'Linux')
            args = result.worker_command('--native-feather', 'a b.json', temporary='temp space')
            self.assertEqual(args[0], '/usr/bin/env')
            self.assertIn('LD_LIBRARY_PATH=' + str(result.inkstitch.parent), args)
            self.assertIn('TMPDIR=temp space', args)
            self.assertEqual(args[-2:], ['--native-feather', 'a b.json'])

    def test_binary_output_and_child_failure(self):
        data = runtime.execute([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(bytes(range(256)))'])
        self.assertEqual(data, bytes(range(256)))
        with self.assertRaisesRegex(ValueError, 'specific engine error'):
            runtime.execute([sys.executable, '-c', "import sys;sys.stderr.write('specific engine error');sys.exit(3)"])

    def test_timeout_stops_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'child.pid'
            script = "import subprocess,sys,time,pathlib;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(60)"
            with self.assertRaisesRegex(ValueError, 'took too long'):
                runtime.execute([sys.executable, '-c', script, str(marker)], timeout=2)
            self.assertTrue(marker.exists())
            pid = int(marker.read_text())
            if os.name == 'nt':
                import ctypes
                api = ctypes.WinDLL('kernel32', use_last_error=True)
                api.OpenProcess.restype = ctypes.c_void_p
                handle = api.OpenProcess(0x00100000, False, pid)
                if handle:
                    api.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
                    api.CloseHandle.argtypes = [ctypes.c_void_p]
                    try:self.assertEqual(api.WaitForSingleObject(handle, 3000), 0)
                    finally:api.CloseHandle(handle)
            else:
                # A dead child can briefly remain a zombie until init reaps it.
                proc = Path('/proc') / str(pid) / 'stat'
                if proc.exists():self.assertEqual(proc.read_text().split()[2], 'Z')

    @unittest.skipUnless(os.name=='nt', 'Windows desktop isolation')
    def test_engine_child_uses_private_desktop(self):
        import json
        import windows_desktop
        probe='''import ctypes as c,json
from ctypes import wintypes as w
u=c.WinDLL('user32',use_last_error=True);k=c.WinDLL('kernel32')
u.GetThreadDesktop.argtypes=[w.DWORD];u.GetThreadDesktop.restype=w.HANDLE
u.GetUserObjectInformationW.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.POINTER(w.DWORD)]
handle=u.GetThreadDesktop(k.GetCurrentThreadId());name=c.create_unicode_buffer(256);size=w.DWORD()
if not u.GetUserObjectInformationW(handle,2,name,c.sizeof(name),c.byref(size)):raise c.WinError(c.get_last_error())
print(json.dumps({'desktop':name.value}))
'''
        result=json.loads(runtime.execute([getattr(sys,'_base_executable',sys.executable),'-c',probe]))
        self.assertEqual(result['desktop'],windows_desktop.name())
        self.assertNotEqual(result['desktop'].lower(),'default')

    @unittest.skipUnless(os.name=='nt', 'Windows message-bus isolation')
    def test_parallel_inkscape_jobs_are_independent(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        def actions(_):
            return runtime.execute(['inkscape','--action-list'],timeout=30)
        # Each completed job closes its entire process tree. It must not own a
        # shared message bus used by either another job or desktop Inkscape.
        with patch.dict(os.environ,{'DBUS_SESSION_BUS_ADDRESS':'ambient-sentinel'}):
            with ThreadPoolExecutor(max_workers=3) as pool:
                for result in pool.map(actions,range(9)):
                    self.assertIn(b'export-do',result)
            self.assertEqual(os.environ['DBUS_SESSION_BUS_ADDRESS'],'ambient-sentinel')


if __name__ == '__main__':
    unittest.main()
