"""Fixed adapter to the installed Ink/Stitch plan compiler."""
import copy,io,json,re,sys
from pathlib import Path
from lib.extensions.base import InkstitchExtension
from lib.svg import PIXELS_PER_MM
from lib.stitch_plan import stitch_groups_to_stitch_plan
from sewing_optimizer_geometry import optimize

def main():
    config=json.loads(Path(sys.argv[1]).read_text());report={}
    class Capture(InkstitchExtension):
        def effect(self):
            if not self.get_elements():raise ValueError('No stitchable geometry was found.')
            groups=[]
            for i,element in enumerate(self.elements):
                source=next((int(n.get('id')[6:]) for n in [element.node,*element.node.iterancestors()] if re.fullmatch(r'layer-\d+',n.get('id',''))),-1)
                if config.get('independentElements'):source=i
                new=copy.deepcopy(element.embroider(groups[-1] if groups else None,self.elements[i+1] if i+1<len(self.elements) else None))
                for group in new:
                    for stitch in group.stitches:stitch.tags=set(stitch.tags)|{'native_source_'+str(source)}
                groups.extend(new)
            meta=self.get_inkstitch_metadata()
            plan=stitch_groups_to_stitch_plan(groups,collapse_len=meta['collapse_len_mm'],min_stitch_len=meta['min_stitch_len_mm'])
            if plan.num_stitches>150000:raise ValueError('Optimize a design with fewer than 150,000 stitches.')
            blocks=[{'color':'#'+b.color.hex_digits,'points':[[p.x/PIXELS_PER_MM,p.y/PIXELS_PER_MM,
                'JUMP' if p.jump else 'TRIM' if p.trim else 'STOP' if p.stop else 'COLOR' if p.color_change else 'STITCH',
                next((int(t[14:]) for t in p.tags if t.startswith('native_source_')),-1)] for p in b.stitches]} for b in plan]
            optimized,stats=optimize(blocks,config)
            report.update(blocks=optimized,stats=stats)
            if config.get('probe'):report['originalBlocks']=blocks
    try:
        Capture().run([config['source']],output=io.BytesIO());print(json.dumps(report))
    except Exception as error:print(json.dumps({'error':str(error) or type(error).__name__}))
