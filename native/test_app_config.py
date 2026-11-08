"""Layout and precompiled-helper checks without touching real user settings."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app_config
import studio_runtime


class LayoutTests(unittest.TestCase):
    def test_installed_and_portable_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);app=root/'Application';app.mkdir()
            local=root/'Local App Data'
            env={**os.environ,'LOCALAPPDATA':str(local)}
            env.pop('STUDIO_STATE_HOME',None)
            with patch.dict(os.environ,env,clear=True),patch.object(app_config,'app_root',return_value=app),patch.object(app_config.platform,'system',return_value='Windows'):
                self.assertEqual(app_config.state_home(),local/'Ink Studio')
                (app/'portable.txt').write_text('')
                self.assertEqual(app_config.state_home(),app)
                with patch.dict(os.environ,{'STUDIO_STATE_HOME':str(root/'Isolated café')}):
                    self.assertEqual(app_config.state_home(),root/'Isolated café')

    def test_linux_uses_xdg_and_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            env={'XDG_CONFIG_HOME':str(root/'Config café'),'XDG_STATE_HOME':str(root/'State café'),'XDG_DATA_HOME':str(root/'Data café'),'HOME':str(root),'USERPROFILE':str(root)}
            with patch.dict(os.environ,env,clear=True),patch.object(app_config.platform,'system',return_value='Linux'),patch.object(app_config,'packaged',return_value=False):
                self.assertEqual(app_config.state_home(),root/'State café/ink-studio')
                self.assertEqual(app_config.settings_path(),root/'Config café/ink-studio/settings.json')
                app_config.save_settings({'port':8809,'extensionKey':True})
                app_config.save_settings({'inkstitch':'/example/inkstitch'})
                self.assertTrue(app_config.load_settings()['extensionKey'])
                app_config.prepare_environment()
                self.assertEqual(os.environ['STUDIO_DATA'],str(root/'Data café/ink-studio'))
                self.assertEqual(os.environ['STUDIO_PORT'],'8809')

    def test_portable_settings_relocate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);before=root/'Before';after=root/'After café'
            before.mkdir();(before/'portable.txt').touch();(before/'config').mkdir()
            (before/'config/settings.json').write_text(json.dumps({'port':8802}))
            env=dict(os.environ);env.pop('STUDIO_STATE_HOME',None)
            with patch.dict(os.environ,env,clear=True),patch.object(app_config,'app_root',return_value=before):
                self.assertEqual(app_config.load_settings()['port'],8802)
            before.rename(after)
            with patch.dict(os.environ,env,clear=True),patch.object(app_config,'app_root',return_value=after):
                self.assertEqual(app_config.settings_path(),after/'config/settings.json')
                self.assertEqual(app_config.load_settings()['port'],8802)

    def test_settings_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'settings.json'
            with patch.object(app_config,'settings_path',return_value=file):
                self.assertEqual(app_config.load_settings(),{})
                for value in [{'port':True},{'port':1},{'port':65536},{'inkscape':[]},[]]:
                    file.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):app_config.load_settings()

    def test_packaged_helpers_need_no_compiler(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('engine-host.exe','windows-command.exe'):(root/name).touch()
            runtime=studio_runtime.Runtime(True,root/'inkscape.com',root/'inkstitch.exe',root,root,root/'data',root/'config','127.0.0.1',8801)
            with patch.object(studio_runtime,'ROOT',root),patch.object(studio_runtime.subprocess,'run',side_effect=AssertionError('Compiler should not run')):
                self.assertEqual(runtime.bridge(),root/'engine-host.exe')
                self.assertEqual(runtime.windows_launcher(),root/'windows-command.exe')


if __name__=='__main__':unittest.main()
