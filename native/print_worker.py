"""Capture the installed print extension's calculations and artwork, without GUI."""
import io,json,sys
from pathlib import Path
from lxml import etree as ET
import lib.extensions.print_pdf as desktop
from lib.svg import PIXELS_PER_MM
from lib.threads import ThreadCatalog
from lib.threads.palette import ThreadPalette

class Captured(Exception):pass

def main():
    try:run()
    except Exception as error:
        print(str(error) or type(error).__name__,file=sys.stderr);raise SystemExit(1)

def run():
    config=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));folder=Path(config['folder']);report={};applied=False
    def stats(plan):
        return {'stitches':plan.num_stitches,'trims':plan.num_trims,'stops':plan.num_stops,'jumps':plan.num_jumps}
    class Print(desktop.Print):
        def render_svgs(self,plan,realistic=False):
            nonlocal applied
            if plan.num_stitches>400000:raise ValueError('Print at most 400,000 stitch commands. Choose a smaller selection.')
            if not applied:
                if config.get('palette'):ThreadCatalog().apply_palette(plan,ThreadPalette(config['palette']))
                book=config.get('cutThreads',{}) if config.get('palette') else {**config.get('threadBook',{}),**config.get('cutThreads',{})}
                for block in plan:
                    entry=book.get('#'+block.color.hex_digits.lower())
                    if entry:
                        block.color.name=entry.get('name','');block.color.number=entry.get('number','');block.color.manufacturer=entry.get('brand','')
                applied=True
            overview,blocks=super().render_svgs(plan,realistic)
            prefix='realistic' if realistic else 'simple'
            if config.get('reference'):(folder/('desktop-'+prefix+'.svg')).write_text(overview,encoding='utf-8')
            x1,y1,x2,y2=[v/PIXELS_PER_MM for v in plan.bounding_box];w=max(.1,x2-x1)+2;h=max(.1,y2-y1)+2
            for label,raw in [('overview',overview),*[(str(i),raw) for i,raw in enumerate(blocks)]]:
                root=ET.fromstring(raw.encode());root.set('viewBox',f'{x1-1} {y1-1} {w} {h}');root.set('width',f'{w}mm');root.set('height',f'{h}mm')
                (folder/(prefix+'-'+label+'.svg')).write_bytes(ET.tostring(root))
            report['artSize']=[w,h];report['bounds']=[x1,y1,x2,y2]
            return overview,blocks
        def render_html(self,plan,overview,palette):
            report.update(**stats(plan),width=plan.dimensions_mm[0],height=plan.dimensions_mm[1],threadMeters=plan.estimated_thread,colors=plan.num_colors,
                blocks=[{**stats(b),'index':i,'color':'#'+b.color.hex_digits.lower(),'name':b.color.name or '',
                    'number':b.color.number or '','brand':b.color.manufacturer or '', 'threadMeters':b.estimated_thread/PIXELS_PER_MM/1000} for i,b in enumerate(plan)])
            if config.get('reference'):(folder/'desktop.html').write_text(super().render_html(plan,overview,palette),encoding='utf-8')
            raise Captured()
    try:Print().run([config['source']],output=io.BytesIO())
    except Captured:pass
    if not report.get('blocks'):raise ValueError('The design has no printable stitches.')
    print(json.dumps(report,ensure_ascii=False))
