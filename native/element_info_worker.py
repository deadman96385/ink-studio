"""Capture the installed Element Info report without opening a desktop window."""
import io,json,re,sys
import lib.extensions.element_info as desktop

def main():
    report={'items':[],'elements':[],'tsv':''};current=[None]
    def item(value):
        return {'name':str(value.name),'value':str(value.value),'headline':bool(value.headline),'warning':bool(value.warning)}
    class Report:
        def __init__(self,items,tsv):report.update(items=[item(i) for i in items],tsv=tsv)
        def MainLoop(self):pass
    class Abort:
        def __init__(self,message,*args,**kwargs):raise ValueError(str(message))
    class ElementInfo(desktop.ElementInfo):
        def _element_info(self,element,previous_stitch_group,next_element):
            node=element.node;current[0]=node.get_id();start=len(self.list_items)
            result=super()._element_info(element,previous_stitch_group,next_element)
            owner=next((int(a.get('id').removeprefix('layer-')) for a in node.iterancestors() if re.fullmatch(r'layer-\d+',a.get('id',''))),None)
            report['elements'].append({'id':current[0],'layerIndex':owner,'items':[item(i) for i in self.list_items[start:]]})
            return result
    desktop.ElementInfoApp=Report;desktop.AbortMessageApp=Abort
    args=sys.argv[1:];reference='--native-reference' in args
    if reference:args.remove('--native-reference')
    extension=desktop.ElementInfo() if reference else ElementInfo()
    try:
        extension.run(args,output=io.BytesIO())
        if not report['items']:raise ValueError('The selected artwork produced no stitch information.')
        print(json.dumps(report,ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error':str(error) or type(error).__name__,'elementId':current[0]},ensure_ascii=False))
