"""Capture installed validation messages while retaining desktop validation."""
import io,json,re,sys
from lib.extensions.troubleshoot import Troubleshoot
from lib.elements.validation import ValidationError,ValidationWarning
from lib.svg import PIXELS_PER_MM

def main():
    problems=[];owners={}
    class EngineValidationFailure(ValidationError):
        name='Engine could not validate this object'
        steps_to_solve=['Inspect this object and its stitch settings. For imported artwork or text, separate its paths to inspect individual pieces.',
                        'Repair the shape, then run troubleshooting and preview its actual stitches again.']
    class Report(Troubleshoot):
        def get_elements(self,*args,**kwargs):
            result=super().get_elements(*args,**kwargs)
            for element in self.elements:
                for name in ('validation_errors','validation_warnings'):
                    original=getattr(element,name)
                    def track(original=original,node=element.node,element=element):
                        try:
                            for problem in original():
                                owners[id(problem)]=node
                                yield problem
                        except Exception as error:
                            # Some malformed satins make the desktop validator
                            # itself raise. Keep other objects inspectable and
                            # attach the failure to its source, without inventing
                            # a geometric diagnosis or changing engine logic.
                            try:position=element.paths[0][0]
                            except Exception:position=(0,0)
                            problem=EngineValidationFailure(position)
                            problem.description='Ink/Stitch could not finish this check: '+type(error).__name__+': '+str(error)
                            owners[id(problem)]=node
                            yield problem
                    setattr(element,name,track)
            return result
        def insert_pointer(self,problem):
            node=owners.get(id(problem));owner=None
            if node is not None:
                owner=next((int(a.get('id').removeprefix('layer-')) for a in node.iterancestors() if re.fullmatch(r'layer-\d+',a.get('id',''))),None)
            problems.append({'kind':type(problem).__name__,'severity':'error' if isinstance(problem,ValidationError) else 'warning' if isinstance(problem,ValidationWarning) else 'type',
                'name':str(problem.name),'description':str(problem.description or ''),'steps':[str(v) for v in problem.steps_to_solve],
                'label':str(problem.label or ''),'position':[problem.position.x/PIXELS_PER_MM,problem.position.y/PIXELS_PER_MM],
                'elementId':node.get_id() if node is not None else None,'layerIndex':owner})
            return super().insert_pointer(problem)
    out=io.BytesIO()
    try:
        Report().run(sys.argv[1:],output=out)
        print(json.dumps({'problems':problems,'svg':out.getvalue().decode()},ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error':str(error) or type(error).__name__},ensure_ascii=False))
