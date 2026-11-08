"""Publication checks must reject personal state even when mistakenly allowlisted."""
import json
from pathlib import Path
import subprocess
import tempfile
import tarfile
import unittest
from unittest.mock import patch

from audit_public import inspect_files, audit
import build_windows


class PublicAuditTests(unittest.TestCase):
    def test_internal_plans_and_signing_drafts_are_rejected_even_when_allowlisted(self):
        for name in ('RELEASE_READINESS.md','docs/MOTION_PLAN.md','packaging/signpath/installer.xml'):
            with self.subTest(name=name):
                report=inspect_files({name:b'draft'},[name])
                self.assertEqual(report['findings'][0]['code'],'internal-preparation-file')

    def test_normal_source_and_symbolic_secret_names_are_allowed(self):
        files={'README.md': b'Public project', '.github/workflows/checks.yml': b'${{ secrets.SIGNPATH_API_TOKEN }}'}
        self.assertTrue(inspect_files(files, files)['passed'])

    def test_svg_namespace_allowance_does_not_allow_local_services(self):
        files={'native/effects.py':b'https://inkstudio.local/effects'}
        self.assertTrue(inspect_files(files,files)['passed'])
        for suffix in ('/private-service','/effects/private-service','/effects-extra'):
            files={'native/effects.py':('https:'+ '//inkstudio'+'.local'+suffix).encode()}
            self.assertFalse(inspect_files(files,files)['passed'])

    def test_personal_state_is_rejected_even_when_allowlisted(self):
        for name in ('designs/shape.json', 'native-backups/saved.json', 'config/settings.json', 'work/recovery.json', 'data/fonts/font.json'):
            with self.subTest(name=name):
                result=inspect_files({name:b'private'},[name])
                self.assertEqual(result['findings'][0]['code'],'private-state-path')

    def test_unknown_files_and_project_exports_are_rejected(self):
        self.assertFalse(inspect_files({'native/new.py':b'new'},[])['passed'])
        name='native/personal.project.json'
        self.assertFalse(inspect_files({name:b'{}'},[name])['passed'])
        files={'root/defaults/autostart':('/designs/'+'personal-artwork.svg').encode()}
        self.assertFalse(inspect_files(files,files)['passed'])

    def test_private_values_never_appear_in_findings(self):
        host='tail'+'123abc'+'.ts.net'
        files={'README.md':('https://device.'+host).encode()}
        report=inspect_files(files,files)
        self.assertFalse(report['passed']);self.assertNotIn(host,json.dumps(report))
        self.assertFalse(inspect_files({'README.md':b'contact@example.test'},['README.md'],forbidden_values=['contact@example.test'])['passed'])

    def test_secrets_and_home_paths_are_rejected(self):
        samples=['gh'+'p_'+'A'*40,'tskey-'+'auth-'+'A'*30,'sk-'+'proj-'+'A'*40,
                 'device.'+'private-example'+'.ts.net','100.'+'77.88.99',
                 '192.'+'168.20.30','-----BEGIN '+'PRIVATE KEY-----',
                 'C:'+chr(92)+'Users'+chr(92)+'someone'+chr(92)+'designs']
        for text in samples:
            with self.subTest(text=text):
                self.assertFalse(inspect_files({'README.md':text.encode()},['README.md'])['passed'])

    def test_symlinks_and_missing_sources_are_rejected(self):
        self.assertFalse(inspect_files({'README.md':b''},['README.md'],modes={'README.md':'120000'})['passed'])
        self.assertFalse(inspect_files({},['README.md'])['passed'])

    def test_git_index_is_checked_instead_of_clean_worktree(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'packaging').mkdir()
            def git(*args):
                subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True)
            git('init','-q')
            catalog={'files':['README.md','packaging/public-files.json']}
            (root/'packaging/public-files.json').write_text(json.dumps(catalog))
            (root/'README.md').write_text('https://device.'+'tail'+'123abc'+'.ts.net')
            git('add','.')
            (root/'README.md').write_text('Clean worktree text')
            self.assertFalse(audit(root,tracked=True)['passed'])

    def test_source_archive_and_payload_ignore_unreviewed_local_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'packaging').mkdir();(root/'native').mkdir()
            names=['README.md','native/app.py','packaging/public-files.json']
            (root/'packaging/public-files.json').write_text(json.dumps({'files':names}))
            (root/'README.md').write_text('Public source')
            (root/'native/app.py').write_text('print("public")')
            canary=root/'native/local_artwork.py';canary.write_text('PRIVATE_CANARY')
            with patch.object(build_windows,'ROOT',root):
                self.assertFalse(build_windows.application_file(canary))
                self.assertTrue(build_windows.application_file(root/'native/app.py'))
                target=root/'source.tar.gz';build_windows.source_archive(target,'1.0.0')
                with tarfile.open(target) as archive:
                    self.assertEqual(set(archive.getnames()),{'ink-studio-1.0.0/'+name for name in names})

    def test_builder_rejects_personal_state_added_to_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'packaging').mkdir();(root/'designs').mkdir()
            (root/'designs/personal.json').write_text('PRIVATE_CANARY')
            names=['designs/personal.json','packaging/public-files.json']
            (root/'packaging/public-files.json').write_text(json.dumps({'files':names}))
            with patch.object(build_windows,'ROOT',root),self.assertRaisesRegex(ValueError,'privacy audit'):
                build_windows.reviewed_sources()


if __name__=='__main__':unittest.main()
