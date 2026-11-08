"""Release gate regressions using tiny synthetic artifacts, not installed data."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).parent))
import build_windows
from verify_release import verify


class ReleaseTests(unittest.TestCase):
    def fixture(self,folder,extra=None,script='export const ready=true;',version='0.1.1'):
        folder=Path(folder);identity='0'*64
        files={'package.json':json.dumps({'version':version,'sourceSha256':identity}).encode(),
               'app/app.js':script.encode(),'app/index.html':b'<title>Ink Studio</title>',
               'NOTICE.txt':b'GPL, either version 3 or later',
               'licenses/components.json':b'{}','licenses/sources.lock.json':b'[]'}
        files.update(extra or {})
        manifest={name:hashlib.sha256(value).hexdigest() for name,value in files.items()}
        files['package-files.json']=json.dumps(manifest).encode();files['portable.txt']=b'portable'
        portable=folder/f'InkStudio-{version}-windows-x64-portable.zip'
        with zipfile.ZipFile(portable,'w') as archive:
            for name,value in files.items():archive.writestr('Ink Studio/'+name,value)
        source=folder/f'InkStudio-{version}-source.tar.gz'
        with tarfile.open(source,'w:gz') as archive:
            names=['LICENSE','NOTICE.txt','VERSION','Build-Studio-Windows.ps1','packaging/build_windows.py',
                   'packaging/windows/ink-studio.ico','.github/workflows/checks.yml','README.md',
                   'CHANGELOG.md','SECURITY.md','PRIVACY.md','CODE_SIGNING_POLICY.md',
                   'CONTRIBUTING.md','packaging/linux/ink-studio']
            for name in names:
                value=version.encode() if name=='VERSION' else b'source'
                info=tarfile.TarInfo(f'ink-studio-{version}/'+name);info.size=len(value)
                info.mode=0o755 if name.endswith('/ink-studio') else 0o644
                archive.addfile(info,io.BytesIO(value))
        vendor=folder/f'InkStudio-{version}-third-party-sources.zip'
        with zipfile.ZipFile(vendor,'w') as archive:archive.writestr('sources.lock.json','[]')
        setup=folder/f'InkStudio-{version}-windows-x64-setup.exe';setup.write_bytes(b'fixture')
        artifacts=[{'file':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (portable,source,vendor,setup)]
        release=folder/'release-manifest.json'
        release.write_text(json.dumps({'version':version,'sourceSha256':identity,'windowsSigning':'unsigned','artifacts':artifacts}))
        (folder/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in (portable,source,vendor,setup,release)))
        return setup

    def test_preview_passes_and_public_gate_rejects_unsigned(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(folder)
            self.assertEqual(verify(folder)['status'],'preview-verified')
            with self.assertRaisesRegex(ValueError,'unsigned'):verify(folder,public=True)
    def test_tampered_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            setup=self.fixture(folder);setup.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):verify(folder)
    def test_user_state_cannot_enter_portable_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(folder,extra={'data/projects/private.json':b'private'})
            with self.assertRaisesRegex(ValueError,'state'):verify(folder)
    def test_missing_frontend_module_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(folder,script="import {a} from './missing.mjs';")
            with self.assertRaisesRegex(ValueError,'Missing front-end'):verify(folder)
    def test_private_deployment_url_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            host="tail"+"abcdef"+".ts.net"
            self.fixture(folder,script="const privateService='https://device."+host+"/';")
            with self.assertRaisesRegex(ValueError,'Personal deployment'):verify(folder)
    def test_icon_staging_does_not_import_an_engine_or_pillow(self):
        import builtins
        real_import=builtins.__import__
        def guarded(name,*args,**kwargs):
            if name in ('studio_runtime','PIL'):raise AssertionError('Build imported an editor dependency')
            return real_import(name,*args,**kwargs)
        with tempfile.TemporaryDirectory() as folder,patch('builtins.__import__',guarded):
            build_windows.make_icon(Path(folder))
            self.assertTrue((Path(folder)/'resources/ink-studio.ico').is_file())


if __name__=='__main__':unittest.main()
