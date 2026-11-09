"""Publication regressions: source identity, complete drafts, and safe retries."""
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import publish_release as release


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'packaging').mkdir()
        (self.root/'VERSION').write_text('1.2.3\n')
        (self.root/'CHANGELOG.md').write_text('# Changelog\n\n## 1.2.3 — Preview\n\n- A change.\n\n## 1.2.2\n\n- Older.\n', encoding='utf-8')
        self.names = ['CHANGELOG.md', 'VERSION', 'packaging/public-files.json']
        (self.root/'packaging/public-files.json').write_text(json.dumps({'files': self.names}))
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=Release test', '-c', 'user.email=release@example.test', 'commit', '-qm', 'Fixture')
        self.commit = self.git('rev-parse', 'HEAD').decode().strip()
        self.info = release.metadata(self.root, 'v1.2.3', self.commit)
        self.folder = self.root/'dist'
        self.folder.mkdir()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE)

    def archive(self, tamper=None, duplicate=False, extra=False):
        identity = hashlib.sha256()
        with tarfile.open(self.folder/'InkStudio-1.2.3-source.tar.gz', 'w:gz') as archive:
            for name in self.names:
                raw = self.git('show', self.commit+':'+name)
                identity.update(name.encode()+b'\0'+raw+b'\0')
                content = b'changed' if name == tamper else raw
                member = tarfile.TarInfo('ink-studio-1.2.3/'+name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
                if duplicate and name == 'VERSION':
                    archive.addfile(member, io.BytesIO(content))
            if extra:
                archive.addfile(tarfile.TarInfo('ink-studio-1.2.3/unreviewed.txt'), io.BytesIO())
        return {'sourceSha256': identity.hexdigest()}

    def test_exact_tag_and_changelog_metadata(self):
        self.assertEqual(self.info['version'], '1.2.3')
        self.assertIn('A change.', self.info['changes'])
        self.assertNotIn('Older.', self.info['changes'])
        self.assertEqual(release.metadata(self.root, '', self.commit)['tag'], 'v1.2.3')

    def test_mismatched_tags_and_checkout_are_rejected(self):
        for tag in ('v1.2.4', '1.2.3', 'v1.2.3-rc.1', 'v1.2.3; echo unsafe', 'v01.2.3'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.metadata(self.root, tag, self.commit)
        with self.assertRaisesRegex(ValueError, 'checkout'):
            release.metadata(self.root, 'v1.2.3', 'f'*40)

    def test_missing_changelog_fails_before_build(self):
        (self.root/'CHANGELOG.md').write_text('# Changelog\n\n## 1.2.2\n\n- Older.\n')
        with self.assertRaisesRegex(ValueError, 'changelog'):
            release.metadata(self.root, 'v1.2.3', self.commit)

    def test_source_bytes_and_identity_match_the_tag(self):
        manifest = self.archive()
        release.verify_source(self.root, self.folder, self.info, manifest)
        with self.assertRaisesRegex(ValueError, 'identity'):
            release.verify_source(self.root, self.folder, self.info, {'sourceSha256': '0'*64})

    def test_tampered_extra_and_duplicate_source_files_fail(self):
        for kwargs in ({'tamper': 'VERSION'}, {'extra': True}, {'duplicate': True}):
            with self.subTest(kwargs=kwargs):
                manifest = self.archive(**kwargs)
                with self.assertRaises(ValueError):
                    release.verify_source(self.root, self.folder, self.info, manifest)

    def test_extra_files_cannot_be_published(self):
        (self.folder/'unexpected.txt').write_text('not a release asset')
        with self.assertRaisesRegex(ValueError, 'seven expected assets'):
            release.verify_candidate(self.root, self.folder, 'v1.2.3', self.commit,
                                     'owner/project', 'https://github.com/owner/project/actions/runs/123')


class FakeGitHub:
    def __init__(self, info, draft=None):
        self.info = info
        self.release = copy.deepcopy(draft)
        self.calls = []
        self.fail_upload = False
        self.remote_commit = info['commit']
        self.corrupt_upload = False

    def api(self, endpoint, *, method='GET', data=None, missing_ok=False):
        self.calls.append((method, endpoint, copy.deepcopy(data)))
        if '/commits/' in endpoint:
            return {'sha': self.remote_commit}
        if method == 'POST':
            self.release = {**data, 'id': 7, 'assets': [], 'html_url': 'https://github.com/owner/project/releases/tag/v1.2.3'}
        elif method == 'PATCH':
            self.release.update(data)
        return copy.deepcopy(self.release)

    def gh(self, args, **kwargs):
        self.calls.append(('UPLOAD', args, None))
        if self.fail_upload:
            raise RuntimeError('Upload interrupted')
        for value in args[5:]:
            name = Path(value).name
            asset = self.info['assets'][name]
            self.release['assets'].append({'name': name, 'size': asset['size'], 'state': 'uploaded',
                                           'digest': 'sha256:bad' if self.corrupt_upload else asset['digest']})
        return ''


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.info = {'version': '1.2.3', 'tag': 'v1.2.3', 'commit': 'a'*40,
                     'repository': 'owner/project', 'run_url': 'https://github.com/owner/project/actions/runs/123',
                     'changes': '- A change.', 'assets': {}}
        for i, name in enumerate(release.asset_names('1.2.3')):
            self.info['assets'][name] = {'path': Path('staging')/name, 'size': i+1, 'digest': 'sha256:'+str(i)*64}

    def draft(self):
        return {'id': 7, 'tag_name': 'v1.2.3', 'target_commitish': self.info['commit'],
                'draft': True, 'prerelease': True, 'assets': [],
                'html_url': 'https://github.com/owner/project/releases/tag/v1.2.3'}

    def invoke(self, fake):
        with patch.object(release, 'api', fake.api), patch.object(release, 'gh', fake.gh):
            return release.publish(self.info)

    def test_complete_upload_is_verified_before_publishing(self):
        fake = FakeGitHub(self.info)
        self.assertEqual(self.invoke(fake)['status'], 'published')
        self.assertEqual(len(fake.release['assets']), 7)
        self.assertTrue(fake.release['prerelease'])
        self.assertEqual(fake.release['make_latest'], 'false')
        methods = [call[0] for call in fake.calls]
        self.assertLess(methods.index('UPLOAD'), methods.index('PATCH'))
        self.assertIn('unsigned previews', fake.release['body'])

    def test_interrupted_upload_leaves_a_draft(self):
        fake = FakeGitHub(self.info)
        fake.fail_upload = True
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            self.invoke(fake)
        self.assertTrue(fake.release['draft'])
        self.assertNotIn('PATCH', [call[0] for call in fake.calls])

    def test_corrupt_upload_is_not_published(self):
        fake = FakeGitHub(self.info)
        fake.corrupt_upload = True
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.invoke(fake)
        self.assertTrue(fake.release['draft'])

    def test_retry_resumes_a_matching_draft_without_replacing_assets(self):
        fake = FakeGitHub(self.info, self.draft())
        name, asset = next(iter(self.info['assets'].items()))
        fake.release['assets'].append({'name': name, 'size': asset['size'], 'digest': asset['digest'], 'state': 'uploaded'})
        self.invoke(fake)
        uploads = [call for call in fake.calls if call[0] == 'UPLOAD']
        self.assertEqual(len(uploads), 1)
        self.assertNotIn(str(asset['path']), uploads[0][1])
        self.assertNotIn('--clobber', uploads[0][1])
        self.assertEqual(len(fake.release['assets']), 7)

    def test_published_release_is_left_untouched(self):
        draft = self.draft(); draft['draft'] = False
        fake = FakeGitHub(self.info, draft)
        self.assertEqual(self.invoke(fake)['status'], 'already-published')
        self.assertTrue(all(call[0] == 'GET' for call in fake.calls))

    def test_changed_remote_tag_cannot_publish(self):
        fake = FakeGitHub(self.info)
        fake.remote_commit = 'b'*40
        with self.assertRaisesRegex(ValueError, 'remote version tag'):
            self.invoke(fake)
        self.assertIsNone(fake.release)

    def test_other_revision_or_unexpected_draft_assets_are_not_overwritten(self):
        draft = self.draft(); draft['target_commitish'] = 'b'*40
        with self.assertRaisesRegex(ValueError, 'different source'):
            self.invoke(FakeGitHub(self.info, draft))
        draft = self.draft(); draft['assets'] = [{'name': 'unrelated.txt'}]
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            self.invoke(FakeGitHub(self.info, draft))

    def test_only_actual_404_is_treated_as_missing(self):
        for status in (403, 404):
            completed = SimpleNamespace(returncode=1, stdout=json.dumps({'status': str(status)}), stderr='API failed')
            with patch.object(release.subprocess, 'run', return_value=completed):
                if status == 404:
                    self.assertIsNone(release.api('repos/owner/project/releases/tags/v1.2.3', missing_ok=True))
                else:
                    with self.assertRaises(RuntimeError):
                        release.api('repos/owner/project/releases/tags/v1.2.3', missing_ok=True)


if __name__ == '__main__':
    unittest.main()
