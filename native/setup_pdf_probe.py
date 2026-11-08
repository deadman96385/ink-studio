"""Fixed, disposable PDF capability check; no project or custom font is opened."""
import json
import os
from weasyprint import HTML

pdf = HTML(string='<html><body><p>Ink Studio setup check</p></body></html>').write_pdf()
if not pdf.startswith(b'%PDF'):
    raise ValueError('PDF initialization failed.')
if os.name == 'nt':
    import pypdfium2
    with pypdfium2.PdfDocument(pdf) as document:
        if len(document) != 1:
            raise ValueError('PDF preview initialization failed.')
print(json.dumps({'ok': True}))
