"""Paginated client, operator, pattern and instruction layouts."""
import html,math
from interchange import swatch_key,font_sample_key

def estimates(report,o,block=None):
    source=block or report;rate=max(1,math.floor(o['speed']/60))
    seconds=source['stitches']/rate+source['trims']*o['trimSeconds']
    if block is None:seconds+=max(0,len(report['blocks'])-1)*o['colorSeconds']+o['extraSeconds']
    n=math.floor(seconds);return {'seconds':seconds,'time':f'{n//3600:02}:{n%3600//60:02}:{n%60:02}',
        'upper':report['threadMeters']*o['upperFactor'],'bobbin':report['threadMeters']*o['bobbinFactor']}

def render(report,o,project,image):
    esc=lambda v:html.escape(str(v),quote=True)
    paper_w,paper_h=(210,297) if o['paper']=='a4' else (215.9,279.4)
    inner=paper_w-24;estimate=estimates(report,o)
    def thread(b):return {**b,**o['threadNames'].get(b['color'],{})}
    def swatch(b):return f'<i class="swatch" style="background:{b["color"]}"></i>'
    def thread_name(b):
        t=thread(b);return f'{esc(t["name"] or "Thread")}<br><small>{esc(" · ".join(v for v in [t["brand"],t["number"],t["color"]] if v))}</small>'
    def figure(key,index=None,height=145,width=None):
        width=width or inner;aw,ah=report['artSize'];p=o['placements'].get(key,{});scale=p.get('scale',max(1,min(2000,min((width-4)/aw,(height-4)/ah)*100)))/100
        left=(width-aw*scale)/2+p.get('x',0);top=(height-ah*scale)/2+p.get('y',0)
        src=image(index,p.get('realistic',False))
        return f'<div class="art" style="width:{width:g}mm;height:{height:g}mm"><img alt="Stitch artwork" src="{src}" style="left:{left:g}mm;top:{top:g}mm;width:{aw*scale:g}mm;height:{ah*scale:g}mm"></div><p class="scale">Artwork scale {scale*100:.1f}%</p>'
    def summary(layout):
        timing=f'<dt>Estimated time</dt><dd>{estimate["time"]}</dd>' if layout in o['showTime'] else ''
        return f'<dl class="summary"><dt>Design size</dt><dd>{report["width"]:.1f} × {report["height"]:.1f} mm</dd><dt>Design stitch count</dt><dd>{report["stitches"]:,}</dd><dt>Colors / thread steps</dt><dd>{report["colors"]} / {len(report["blocks"])}</dd><dt>Stops / trims</dt><dd>{report["stops"]} / {report["trims"]}</dd><dt>Estimated upper / bobbin</dt><dd>{estimate["upper"]:.2f} m / {estimate["bobbin"]:.2f} m</dd>{timing}</dl>'
    def palette_table():
        return '<table class="threads"><thead><tr><th>Step</th><th>Color</th><th>Thread</th></tr></thead><tbody>'+''.join(f'<tr><td>{b["index"]+1}</td><td>{swatch(b)}</td><td>{thread_name(b)}</td></tr>' for b in report['blocks'])+'</tbody></table>'
    note=f'<p class="method">Ink/Stitch design counts include command steps before machine encoding. The PES contains {report["machine"]["stitches"]:,} needle stitches. Time and thread consumption are estimates; adjust the factors for your setup.</p>'
    machine='<p class="method">Cutwork: keep matching EXP and INF files together. Use a compatible cutting-needle setup.</p>' if report.get('cutwork') else '<p class="method">Brother PP1 · 100 × 100 mm hoop. Check fabric and stabilizer with a test sew.</p>'
    logo=f'<img class="logo" src="{o["logo"]}" alt="Logo">' if o['logo'] else ''
    header=f'<header>{logo}<div class="heading"><h1>{esc(o["title"])}</h1><p>{esc(o["client"])}'+(' · Order '+esc(o['purchaseOrder']) if o['purchaseOrder'] else '')+f'</p><p class="date">{esc(o["date"])}</p></div></header>'
    parts=[]
    for layout in ['clientOverview','clientDetail','operatorOverview','operatorDetail','pattern','custom']:
        if layout not in o['layouts']:continue
        if layout=='clientOverview':parts.append('<section><h2>Client overview</h2>'+summary(layout)+figure(layout,height=120)+palette_table()+'<p class="signature">Client approval / signature: __________________________________</p>'+note+'</section>')
        elif layout=='clientDetail':
            for b in report['blocks']:
                timing=f' · Estimated time {estimates(report,o,b)["time"]}' if layout in o['showTime'] else ''
                parts.append(f'<section><h2>Client detail · thread step {b["index"]+1}</h2><p>{swatch(b)} {thread_name(b)}</p>'+figure('clientDetail-'+str(b['index']),b['index'],height=155)+f'<p>{b["stitches"]:,} design stitches · {b["trims"]} trims · {b["stops"]} stops{timing}</p>'+note+'</section>')
        elif layout=='operatorOverview':parts.append('<section><h2>Operator overview</h2>'+summary(layout)+figure(layout,height=145)+note+machine+'</section>')
        elif layout=='operatorDetail':
            rows=[];size=o['thumbnail']
            for b in report['blocks']:
                timing=f'<br>Time {estimates(report,o,b)["time"]}' if layout in o['showTime'] else ''
                thumb=f'<img class="thumb" style="width:{size:g}mm;height:{size:g}mm" src="{image(b["index"],False)}" alt="Thread step {b["index"]+1}">'
                rows.append(f'<tr><td class="step">{b["index"]+1}<br>{swatch(b)}</td><td>{thumb}</td><td>{thread_name(b)}<p>{b["stitches"]:,} design stitches<br>{b["trims"]} trims · {b["stops"]} stops{timing}</p><p class="operator-note">{esc(o["notes"].get(str(b["index"]),""))}</p></td></tr>')
            parts.append('<section><h2>Operator detail</h2>'+summary(layout)+'<table class="operator"><thead><tr><th>Step</th><th>Stitch preview</th><th>Thread, stitches and operator notes</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'+note+machine+'</section>')
        elif layout=='pattern':
            height=paper_h-24-(18 if o['patternFooter'] else 0)
            parts.append('<section class="pattern">'+figure(layout,height=height,width=paper_w-16)+'<div class="ruler">50 mm</div></section>')
        elif layout=='custom':parts.append('<section class="custom">'+o['custom']+'</section>')
    keys=swatch_key(project)+font_sample_key(project) if o['sampleKeys'] else ''
    if keys:parts.append('<section><h2>Design sample keys</h2>'+keys+'</section>')
    footer=o['footer'];pattern_footer='@bottom-left{content:element(reportFooter)}@bottom-right{content:counter(page) " / " counter(pages)}' if o['patternFooter'] else '@bottom-left{content:none}@bottom-right{content:none}'
    css=f'''
    @page{{size:{paper_w}mm {paper_h}mm;margin:38mm 12mm 26mm;@top-left{{content:element(reportHeader);vertical-align:bottom;padding-bottom:4mm}}@bottom-left{{content:element(reportFooter);vertical-align:top;padding-top:4mm}}@bottom-right{{content:counter(page) " / " counter(pages);font:8pt sans-serif;vertical-align:top;padding-top:4mm}}}}
    @page pattern{{margin:8mm 8mm {26 if o['patternFooter'] else 8}mm;@top-left{{content:none}}{pattern_footer}}}
    *{{box-sizing:border-box}}body{{font:9pt "DejaVu Sans",sans-serif;color:#233a34;margin:0;line-height:1.4}}header{{position:running(reportHeader);width:{inner}mm;border-bottom:.3mm solid #b9c9c0;padding-bottom:3mm}}header .logo{{float:right;max-width:36mm;max-height:23mm;object-fit:contain}}header .heading{{width:{inner-42}mm}}h1{{font-size:16pt;line-height:1.15;margin:0 0 1.5mm;overflow-wrap:anywhere}}header p{{margin:0;font-size:9pt;overflow-wrap:anywhere}}.date{{font-size:8pt;color:#576b62}}footer{{position:running(reportFooter);width:{inner-15}mm;font-size:8pt;line-height:1.2;overflow-wrap:anywhere}}footer p,footer div{{margin:0}}section{{break-before:page}}section:first-of-type{{break-before:auto}}section.pattern{{page:pattern}}h2{{font-size:13pt;margin:0 0 4mm}}h3{{font-size:11pt}}p{{margin:2mm 0 3mm}}small{{font-size:8pt;color:#52685e}}.summary{{margin:0 0 4mm;columns:2;column-gap:6mm;font-size:8pt}}dt{{float:left;clear:left;width:49mm;color:#52685e}}dd{{margin-left:49mm;margin-bottom:1mm;font-weight:bold}}.art{{position:relative;overflow:hidden;margin:0;padding:0;background:white}}.art img{{position:absolute;max-width:none;max-height:none}}.scale{{font-size:7pt;color:#62766c;margin:1mm 0 3mm}}.pattern .scale{{display:none}}.ruler{{width:50mm;border-top:.25mm solid #233a34;font-size:7pt;margin-top:3mm}}.threads,.operator,.custom table{{border-collapse:collapse;width:100%;font-size:8pt;table-layout:auto}}thead{{display:table-header-group}}tr{{break-inside:avoid}}.operator tr{{break-inside:auto}}th,td{{border-bottom:.2mm solid #d3ded7;padding:2mm;text-align:left;vertical-align:top;overflow-wrap:anywhere}}th{{background:#edf3ee;color:#284e3e;font-weight:bold}}.step{{width:13mm;text-align:center}}.thumb{{object-fit:contain;display:block;max-width:110mm}}.swatch{{display:inline-block;width:4mm;height:4mm;border:.2mm solid #99aaa0;vertical-align:middle}}.operator-note{{white-space:pre-wrap;overflow-wrap:anywhere;border-left:.6mm solid #b8cdbf;padding-left:2mm}}.operator-note:empty{{display:none}}.method{{font-size:7pt;color:#607368;margin-top:4mm}}.signature{{margin-top:5mm;font-size:9pt}}.custom{{font-size:10pt;overflow-wrap:anywhere}}a{{color:#245945}}blockquote{{border-left:1mm solid #b8cdbf;padding-left:4mm;margin-left:0}}'''
    return '<!doctype html><html><head><meta charset="utf-8"><title>'+esc(o['title'])+'</title><style>'+css+'</style></head><body>'+header+'<footer>'+footer+'</footer>'+''.join(parts)+'</body></html>'
