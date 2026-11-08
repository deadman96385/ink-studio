"""Locations shared by repeatable engine checks on Windows and Linux."""
import os
from pathlib import Path
import studio_runtime

DATA = studio_runtime.current().data
RESOURCE = studio_runtime.resource()
BASE = os.environ.get('STUDIO_URL', 'http://127.0.0.1:8797').rstrip('/')
FIXTURES = Path(__file__).absolute().parent / 'test-fixtures' / 'fonts'
TTF = Path(os.environ.get('STUDIO_TEST_TTF', FIXTURES / 'DejaVuSans-Bold.ttf'))
OTF = Path(os.environ.get('STUDIO_TEST_OTF', FIXTURES / 'SourceSans3-Bold.otf'))


def pdf_text(path, run):
    if os.name == 'nt':
        from pypdf import PdfReader
        return '\f'.join(page.extract_text(extraction_mode='layout') or '' for page in PdfReader(path).pages)+'\f'
    return run(['pdftotext','-layout',str(path),'-']).decode('utf-8')
