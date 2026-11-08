"""Check the buildless public showcase without third-party dependencies."""
from html.parser import HTMLParser
import json
import math
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent / 'docs'


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []
        self.images = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if 'id' in attrs:
            assert attrs['id'] not in self.ids, 'Duplicate HTML ID'
            self.ids.add(attrs['id'])
        for name in ('href', 'src'):
            if name in attrs:
                self.links.append(attrs[name])
        if tag == 'img':
            assert 'alt' in attrs, 'Image missing alt text'
            if attrs.get('src'):
                self.images.append(attrs['src'])


def main():
    page = Page()
    page.feed((ROOT / 'index.html').read_text(encoding='utf-8'))
    for link in page.links:
        url = urlsplit(link)
        if url.scheme or url.netloc:
            assert url.scheme == 'https', 'Only HTTPS external links are allowed'
            continue
        assert not url.path.startswith('/'), 'Use project-path-safe relative links'
        if url.path:
            target = (ROOT / unquote(url.path)).resolve()
            assert target.is_relative_to(ROOT.resolve()), 'Link escapes the public site'
            assert target.exists(), f'Missing site asset: {url.path}'
        elif url.fragment:
            assert url.fragment in page.ids, f'Missing anchor: {url.fragment}'
    for source in page.images:
        path = ROOT / source
        if path.suffix == '.jpg':
            assert path.read_bytes().startswith(b'\xff\xd8\xff'), 'Screenshot is not JPEG'
    sample = json.loads((ROOT / 'assets/field-notes-stitches.json').read_text(encoding='utf-8'))
    assert sample['stitches'] == len(sample['segments']) == 3065, 'Update sample facts when replacing the export'
    assert len({thread['color'] for thread in sample['threads']}) == 5
    assert sample['width'] == 62.4 and sample['height'] == 68
    for segment in sample['segments']:
        assert len(segment) == 5 and all(math.isfinite(n) for n in segment)
        assert isinstance(segment[4], int) and 0 <= segment[4] < len(sample['threads'])
    allowed_suffixes = {'.html', '.css', '.js', '.svg', '.jpg', '.json', '.md'}
    files = [path for path in ROOT.rglob('*') if path.is_file()]
    for path in files:
        assert path.name == '.nojekyll' or path.suffix in allowed_suffixes, 'Unexpected file in publish directory'
        assert path.stat().st_size < 2_000_000, f'Oversized site asset: {path.name}'
    assert sum(path.stat().st_size for path in files) < 4_000_000, 'Keep the tour small'
    print(f'PASS: {len(page.links)} links, {len(page.images)} images, {len(files)} static files, 3,065 real stitch segments')


if __name__ == '__main__':
    main()
