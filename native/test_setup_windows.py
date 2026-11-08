"""Verified-cache and interrupted-extraction contracts without GUI or downloads."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import setup_windows as setup
import studio_runtime


class PrivateToolTests(unittest.TestCase):
    def setUp(self):
        # The Windows extraction command is mocked in every applicable test;
        # expose its Windows-only flag while running these contracts on Linux.
        flag=patch.object(setup.subprocess,'CREATE_NO_WINDOW',0,create=True)
        flag.start();self.addCleanup(flag.stop)

    def cache(self,root):
        archive=root/'downloads'/('inkscape-'+setup.VERSION+'-x64.7z')
        archive.parent.mkdir();archive.write_bytes(b'fixture archive')
        return archive

    def test_offline_cache_miss_never_connects(self):
        with tempfile.TemporaryDirectory() as folder,patch('urllib.request.urlopen',side_effect=AssertionError('No network')):
            with self.assertRaisesRegex(ValueError,'Offline setup'):
                setup.install_portable(Path(folder),offline=True)

    def test_corrupt_archive_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.cache(root)
            with patch.object(setup.subprocess,'run',side_effect=AssertionError('Corrupt archive must not extract')):
                with self.assertRaises(ValueError):setup.install_portable(root,offline=True)

    def test_failed_extraction_preserves_previous_cache_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=self.cache(root)
            previous=root/('inkscape-'+setup.VERSION);(previous/'inkscape/bin').mkdir(parents=True)
            marker=previous/'inkscape/bin/inkscape.com';marker.write_bytes(b'incomplete previous cache')
            with patch.object(setup,'SHA256',hashlib.sha256(archive.read_bytes()).hexdigest()),patch.object(studio_runtime,'execute',side_effect=ValueError('incomplete')),patch.object(setup.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'tar.exe')):
                with self.assertRaises(subprocess.CalledProcessError):setup.install_portable(root,offline=True)
            self.assertEqual(marker.read_bytes(),b'incomplete previous cache')
            self.assertFalse(list(root.glob('.inkscape-setup-*')))

    def test_verified_extraction_is_published_after_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=self.cache(root)
            def extract(args,**kwargs):
                target=Path(args[-1]);(target/'inkscape/bin').mkdir(parents=True);(target/'inkscape/bin/inkscape.com').write_bytes(b'verified fixture')
            def probe(args,**kwargs):
                command=kwargs['runtime'].command(args)
                self.assertEqual(command[0],args[0],'Inkscape must not be dispatched through the Ink/Stitch host')
                self.assertIn('--action-list',command)
                return b'object-trace  trace image'
            with patch.object(setup,'SHA256',hashlib.sha256(archive.read_bytes()).hexdigest()),patch.object(setup.subprocess,'run',side_effect=extract),patch.object(studio_runtime,'execute',side_effect=probe):
                executable=setup.install_portable(root,offline=True)
            self.assertEqual(executable.read_bytes(),b'verified fixture')
            self.assertFalse(list(root.glob('.inkscape-setup-*')))


if __name__=='__main__':unittest.main()
