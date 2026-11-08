"""Isolated, bounded PDF rendering; artwork is embedded and no URLs are fetched."""
import json,sys
from pathlib import Path
from weasyprint import HTML,default_url_fetcher

def fetch(url,*args,**kwargs):
    if not url.startswith('data:'):raise ValueError('Print assets must be embedded.')
    return default_url_fetcher(url,*args,**kwargs)

document=HTML(string=Path(sys.argv[1]).read_text(encoding='utf-8'),url_fetcher=fetch).render()
if len(document.pages)>500:raise ValueError('This print job exceeds 500 pages. Choose fewer layouts or shorten the notes.')
for page in document.pages:
    for box in page._page_box.descendants():
        if getattr(box,'text','') and (box.position_y < -1 or box.position_y+box.height > page.height+1 or box.position_x < -1 or box.position_x+box.width > page.width+1):
            raise ValueError('Some print text extends beyond the paper. Shorten the title or footer, remove extra line breaks, or simplify wide custom tables.')
document.write_pdf(sys.argv[2])
print(json.dumps({'pages':len(document.pages),'sizes':[[p.width,p.height] for p in document.pages]}))
