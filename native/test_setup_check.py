"""Setup failure, offline and diagnostic-privacy contracts without GUI/engines."""
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import app_config
import setup_check as setup
import studio_runtime


class SetupTests(unittest.TestCase):
    def fixture(self, root, windows=False, abi=311, version='v3.3.0 (fixture)'):
        inkscape=root/'PrivateName café/Inkscape/bin'/('inkscape.com' if windows else 'inkscape')
        engine=root/'PrivateName café/Ink Stitch/bin'/('inkstitch.exe' if windows else 'inkstitch')
        for path in (inkscape,engine):path.parent.mkdir(parents=True,exist_ok=True);path.touch()
        engine.write_bytes(struct.pack('!8sIIII64s',b'MEI\014\013\012\013\016',88,0,0,abi,b'python'))
        (engine.parent/('python311.dll' if windows else 'libpython3.11.so.1.0')).touch()
        (engine.parent/'base_library.zip').touch()
        (engine.parent.parent/'VERSION').write_text(version)
        (engine.parent.parent/'fonts').mkdir()
        (inkscape.parent.parent/'share/inkscape/extensions/inkex').mkdir(parents=True)
        state=root/'PrivateName café/State';state.mkdir(parents=True)
        env={'STUDIO_INKSCAPE':str(inkscape),'STUDIO_INKSTITCH':str(engine),'STUDIO_DATA':str(root/'PrivateName café/Projects'),
             'STUDIO_STATE_HOME':str(state),'STUDIO_ENGINE_CONFIG':str(root/'PrivateName café/Engine profile'),
             'APPDATA':str(root/'AppData'),'PATH':''}
        return env

    def probe(self, args, **kwargs):
        if '--action-list' in args:return b'object-trace  trace image\n'
        if '--version' in args:return b'Inkscape 1.4.4 PrivateName secret-path'
        if str(args[-1]).endswith('setup_pdf_probe.py'):return b'{"ok":true}'
        self.assertIn('--native-diagnostics',args)
        self.assertIn('STUDIO_ENGINE_CONFIG',kwargs['runtime'].environment())
        return b'{"ok":true,"python":"3.11.9"}'

    def inspect(self,env,system='Linux',probe=None):
        with patch.dict(os.environ,env,clear=True),patch.object(studio_runtime,'execute',side_effect=probe or self.probe),patch.object(studio_runtime.Runtime,'bridge',return_value=Path(env['STUDIO_INKSTITCH'])),patch.object(setup,'_linux_tools',return_value=[]),patch.object(os,'access',return_value=True),patch.object(setup.importlib,'import_module',return_value=object()):
            return setup.collect(system=system)

    def errors(self,report):return {c['code'] for c in report['checks'] if c['status']=='error'}

    def test_ready_on_both_platforms_with_unicode_and_spaces(self):
        for system in ('Windows','Linux'):
            with self.subTest(system=system),tempfile.TemporaryDirectory() as folder:
                env=self.fixture(Path(folder),system=='Windows')
                report,runtime=self.inspect(env,system)
                self.assertTrue(report['ready'],report)
                self.assertEqual(report['versions']['enginePython'],'3.11.9')
                self.assertIn('café',str(runtime.data))

    def test_missing_tools_report_both_problems_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            env=self.fixture(Path(folder));Path(env['STUDIO_INKSTITCH']).unlink();Path(env['STUDIO_INKSCAPE']).unlink()
            with patch('urllib.request.urlopen',side_effect=AssertionError('No network')):
                report,_=self.inspect(env)
            self.assertTrue({'inkstitch-found','inkscape-tracing'}<=self.errors(report))

    def test_unsupported_engine_version_and_python_abi(self):
        for version,abi,code in [('v3.4.0',311,'inkstitch-version'),('v3.3.0',312,'engine-bundle')]:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as folder:
                report,_=self.inspect(self.fixture(Path(folder),abi=abi,version=version))
                self.assertIn(code,self.errors(report))
                self.assertFalse(report['ready'])

    def test_incomplete_bundle_and_extension_modules(self):
        with tempfile.TemporaryDirectory() as folder:
            env=self.fixture(Path(folder));engine=Path(env['STUDIO_INKSTITCH'])
            (engine.parent/'base_library.zip').unlink()
            (Path(env['STUDIO_INKSCAPE']).parent.parent/'share/inkscape/extensions/inkex').rmdir()
            report,_=self.inspect(env)
            self.assertTrue({'engine-bundle','inkscape-extensions'}<=self.errors(report))

    def test_unwritable_project_folder_does_not_run_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            env=self.fixture(Path(folder));blocker=Path(env['STUDIO_DATA']);blocker.parent.mkdir(exist_ok=True);blocker.write_text('keep')
            report,_=self.inspect(env,probe=lambda *a,**k:self.fail('Tools must wait for writable state'))
            self.assertIn('data-writable',self.errors(report));self.assertEqual(blocker.read_text(),'keep')

    def test_blocked_existing_projects_subfolder_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            env=self.fixture(Path(folder));blocker=Path(env['STUDIO_DATA'])/'projects';blocker.parent.mkdir(parents=True);blocker.write_text('keep')
            report,_=self.inspect(env,probe=lambda *a,**k:self.fail('Tools must wait for writable project folders'))
            self.assertIn('data-writable',self.errors(report));self.assertEqual(blocker.read_text(),'keep')

    def test_timeout_and_dependency_failure_are_private(self):
        with tempfile.TemporaryDirectory() as folder:
            env=self.fixture(Path(folder))
            with patch.dict(os.environ,env,clear=True),patch.object(studio_runtime,'execute',side_effect=ValueError('/PrivateName/secret/design.svg')),patch.object(setup.importlib,'import_module',side_effect=ImportError('/PrivateName/secret/module.py')):
                report,_=setup.collect()
            text=json.dumps(report)
            self.assertNotIn('PrivateName',text);self.assertNotIn(folder,text)
            self.assertIn('editor-dependencies',self.errors(report))

    def test_reports_exclude_paths_environment_and_designs(self):
        with tempfile.TemporaryDirectory() as folder:
            env=self.fixture(Path(folder));env['SECRET_TOKEN']='PrivateName-token'
            project=Path(env['STUDIO_DATA'])/'projects/private-project.json';project.parent.mkdir(parents=True);project.write_text('PrivateName design contents')
            report,_=self.inspect(env)
            text=json.dumps(report)
            for secret in ('PrivateName',folder,'private-project','SECRET_TOKEN','STUDIO_DATA','secret-path'):
                self.assertNotIn(secret,text)
            self.assertEqual(project.read_text(),'PrivateName design contents')

    def test_cached_private_inkscape_is_used_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);env=self.fixture(root,True);private=Path(env.pop('STUDIO_INKSCAPE'))
            with patch('urllib.request.urlopen',side_effect=AssertionError('No network')),patch.dict(os.environ,env,clear=True),patch.object(setup,'_inkscape_paths',return_value=[root/'missing.exe',private]),patch.object(studio_runtime,'execute',side_effect=self.probe),patch.object(studio_runtime.Runtime,'bridge',return_value=Path('fixture-helper')),patch.object(setup.importlib,'import_module',return_value=object()):
                report,_=setup.collect(system='Windows')
            self.assertTrue(report['ready'])

    def test_explicit_checks_never_prepare_tools(self):
        report={'checks':[{'code':'inkscape-tracing','status':'error'}],'ready':False}
        with patch.object(app_config,'prepare_environment'),patch.object(setup,'collect',return_value=(report,object())),patch('setup_windows.install_portable',side_effect=AssertionError('Check must not download')):
            self.assertEqual(setup.check()[0],report)

    def test_offline_repair_failure_has_action_without_raw_error(self):
        with tempfile.TemporaryDirectory() as folder:
            env=self.fixture(Path(folder),True);env.pop('STUDIO_INKSCAPE')
            failed={'schema':1,'versions':{},'checks':[{'code':'inkscape-tracing','status':'error'}],'ready':False}
            runtime=studio_runtime.Runtime(True,Path('missing'),Path('missing'),Path('.'),Path('.'),Path(folder),Path(folder),'127.0.0.1',8801)
            with patch.dict(os.environ,env,clear=True),patch.object(app_config,'prepare_environment'),patch.object(setup,'collect',return_value=(failed,runtime)),patch('setup_windows.install_portable',side_effect=OSError('/PrivateName/secret/download')):
                report,_=setup.check(prepare_tools=True)
            self.assertIn('inkscape-download',self.errors(report));self.assertNotIn('PrivateName',json.dumps(report))

    def test_malformed_settings_produce_a_report(self):
        with patch.object(app_config,'prepare_environment',side_effect=ValueError('/PrivateName/settings.json')):
            report,_=setup.check()
        self.assertIn('settings-invalid',self.errors(report));self.assertNotIn('PrivateName',json.dumps(report))

    def test_export_is_atomic_and_does_not_replace_a_design(self):
        with tempfile.TemporaryDirectory() as folder,patch('builtins.print'):
            path=Path(folder)/'diagnostics.json';report=setup.failure('fixture','Fixture message.','Fixture action.')
            setup.emit(report,path);self.assertEqual(json.loads(path.read_text())['schema'],1)
            setup.emit(report,path)
            path.write_text('{"version":1,"name":"PrivateName project"}')
            original=path.read_bytes()
            with self.assertRaises(ValueError):setup.emit(report,path)
            self.assertEqual(path.read_bytes(),original)

    def test_missing_linux_utilities_and_helper_have_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            env=self.fixture(Path(folder))
            with patch.dict(os.environ,env,clear=True),patch.object(studio_runtime,'execute',side_effect=self.probe),patch.object(setup.importlib,'import_module',return_value=object()):
                report,_=setup.collect(system='Linux')
            self.assertIn('linux-tools',self.errors(report))
            for item in report['checks']:
                if item['status']=='error':self.assertTrue(item['action'])

    def test_private_exception_detail_stays_out_of_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'private.log';handler=setup.enable_private_log(path)
            try:
                with patch.object(app_config,'prepare_environment',side_effect=OSError('/PrivateName/secret/settings.json')):
                    report,_=setup.check()
                handler.flush()
                self.assertIn('/PrivateName/secret/settings.json',path.read_text(encoding='utf-8'))
                self.assertNotIn('PrivateName',json.dumps(report))
            finally:
                setup.LOG.removeHandler(handler);handler.close()


if __name__=='__main__':unittest.main()
