"""Read tagged stitch groups from the installed engine, before plan filtering."""
import io,json,sys
from pathlib import Path
from lib.extensions.base import InkstitchExtension
from lib.svg import PIXELS_PER_MM
from lib.stitch_plan import stitch_groups_to_stitch_plan
import copy
from feather_geometry import apply


def main():
    config=json.loads(Path(sys.argv[1]).read_text());report={}
    class Capture(InkstitchExtension):
        def effect(self):
            if not self.get_elements():raise ValueError('No stitchable geometry was found.')
            groups=[]
            for i,element in enumerate(self.elements):
                new=element.embroider(groups[-1] if groups else None,self.elements[i+1] if i+1<len(self.elements) else None)
                new=copy.deepcopy(new)
                if element.node.get('{https://inkstudio.local/effects}flow-top')=='true':
                    for group in new:
                        for stitch in group.stitches:stitch.tags=set(stitch.tags)
                        group.add_tags(('native_flow_top',))
                groups.extend(new)
            rows=[]
            for group in groups:
                rows.append({'tags':sorted({tag for p in group.stitches for tag in p.tags}),'color':'#%02x%02x%02x'%tuple(group.color.to_rgb()),
                    'trim':bool(getattr(group,'trim_after',False)),'stop':bool(getattr(group,'stop_after',False)),
                    'points':[[p.x/PIXELS_PER_MM,p.y/PIXELS_PER_MM,sorted(p.tags)] for p in group.stitches]})
            if config.get('probe'):report['groups']=rows;return
            changed,stats=apply(rows,config)
            for group,row in zip(groups,changed):
                for stitch,p in zip(group.stitches,row['points']):stitch.x=p[0]*PIXELS_PER_MM;stitch.y=p[1]*PIXELS_PER_MM
            metadata=self.get_inkstitch_metadata()
            plan=stitch_groups_to_stitch_plan(groups,collapse_len=metadata['collapse_len_mm'],min_stitch_len=metadata['min_stitch_len_mm'])
            if plan.num_stitches>400000:raise ValueError('Feather a smaller selection; this exceeds 400,000 stitches.')
            report.update(stats=stats,blocks=[{'color':'#'+block.color.hex_digits,'points':[[p.x/PIXELS_PER_MM,p.y/PIXELS_PER_MM,
                'JUMP' if p.jump else 'TRIM' if p.trim else 'STOP' if p.stop else 'COLOR' if p.color_change else 'STITCH'] for p in block.stitches]} for block in plan])
    try:
        Capture().run([config['source']],output=io.BytesIO());print(json.dumps(report))
    except Exception as error:print(json.dumps({'error':str(error) or type(error).__name__}))
