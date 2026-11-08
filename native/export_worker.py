"""Run installed image and ZIP exporters with bounded native export settings."""
import io,json,sys
from pathlib import Path
import lib.extensions.png_simple as simple
import lib.extensions.png_realistic as realistic
import lib.extensions.zip as bundle

def main():
    try:run_export()
    except Exception as error:
        print(str(error) or type(error).__name__,file=sys.stderr)
        raise SystemExit(1)

def run_export():
    config=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    opts=config['options'];source=config['source'];mode=config['mode']
    original_inkscape=simple.inkscape
    def inkscape(*args,**kwargs):
        kwargs['actions']=kwargs['actions'].replace('export-do','export-background-opacity:'+('0' if opts['background']=='transparent' else '1')+'; export-do')
        return original_inkscape(*args,**kwargs)
    simple.inkscape=inkscape
    def check(plan,dpi=None):
        if plan.num_stitches>400000:raise ValueError('Export at most 400,000 stitch commands. Reduce the repeats or split the design.')
        width,height=plan.dimensions_mm
        if mode=='zip' and opts['destination']=='pp1' and max(width,height)>100:
            raise ValueError('The repeated layout exceeds the PP1 100 × 100 mm hoop. Reduce spacing or repeats, or choose another machine.')
        if dpi and (width+2)*(height+2)*(dpi/25.4)**2>64000000:
            raise ValueError('This image would exceed 64 million pixels. Lower its DPI or reduce the repeated layout.')
    render=simple.render_stitch_plan
    def checked_render(svg,plan,*args,**kwargs):
        check(plan,opts['dpi']);return render(svg,plan,*args,**kwargs)
    simple.render_stitch_plan=checked_render;realistic.render_stitch_plan=checked_render
    if mode!='zip':
        args=['--dpi='+str(opts['dpi'])]
        if mode=='png':args+=['--line_width='+str(opts['lineWidth'])]
        extension=simple.PngSimple() if mode=='png' else realistic.PngRealistic()
        extension.run([*args,source],output=io.BytesIO())
        return
    write=bundle.write_embroidery_file
    class Zip(bundle.Zip):
        def _make_offsets(self,plan):
            if plan.num_stitches*self.options.x_repeats*self.options.y_repeats>400000:
                raise ValueError('Export at most 400,000 stitch commands. Reduce the repeats or split the design.')
            return super()._make_offsets(plan)
        def generate_output_files(self,plan,path,name):
            check(plan)
            for key,dpi in [('png_simple','simpleDpi'),('png_realistic','realisticDpi')]:
                if key in opts['formats']:check(plan,opts[dpi])
            return super().generate_output_files(plan,path,name)
    extension=Zip()
    def write_file(path,plan,svg):
        # The desktop ZIP defaults to PES v1; preserve native RGB colors in v6.
        settings={'rotate':extension.metadata.get('rotate_on_export',0)}
        if str(path).endswith('.pes'):settings['version']=6
        return write(path,plan,svg,settings)
    bundle.write_embroidery_file=write_file
    args=['--custom-file-name=design']
    for key in set(opts['formats'])|{'pes'}:
        if key!='project':args+=['--format-'+key.replace('_','-')+'=true']
    for key,option in [('xRepeats','x-repeats'),('yRepeats','y-repeats'),('xSpacing','x-spacing'),('ySpacing','y-spacing'),('simpleDpi','dpi-simple'),('realisticDpi','dpi-realistic'),('lineWidth','png-simple-line-width')]:
        args+=['--'+option+'='+str(opts[key])]
    extension.run([*args,source],output=io.BytesIO())
