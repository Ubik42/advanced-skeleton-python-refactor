"""Capture the failing native graph before the Body transaction rolls back.

Never bypasses the production readback or changes the build algorithm.
"""
from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from adv_py.adapters.maya_body_fk_scale_compensation import MayaBodyFkScaleCompensationMixin
from adv_py.adapters.maya_fit_inbetween import MayaFitInbetweenMixin
from adv_py.adapters.maya_fit_bendy import MayaFitBendyMixin
from maya_partial_joints_lifecycle_smoke import main

OUTPUT=ROOT/'validation/results/opm-body-diagnostic'
OUTPUT.mkdir(parents=True,exist_ok=True)


def capture(host, kind, plan):
    from dataclasses import asdict
    c=host._cmds
    nodes=[]
    def read(node):
        data={'node':node, 'type':c.nodeType(node)}
        for attribute in ('matrix','worldMatrix[0]','parentMatrix[0]',
            'offsetParentMatrix','inheritsTransform','translate','rotate',
            'rotateAxis','scale','shear','rotateOrder','jointOrient',
            'rotatePivot','rotatePivotTranslate','scalePivot','scalePivotTranslate',
            'matrixSum','outputMatrix','useScale','useShear','matrixIn[0]',
            'matrixIn[1]','matrixIn[2]'):
            if c.objExists(node+'.'+attribute):
                try:data[attribute]=c.getAttr(node+'.'+attribute)
                except RuntimeError:pass
        data['inputs']=c.listConnections(node,s=True,d=False,p=True,c=True) or []
        return data
    for field,value in asdict(plan).items():
        if isinstance(value,str) and c.objExists(value):
            nodes.append(read(value))
    for node in getattr(plan,'node_names',getattr(getattr(plan,'chain',None),'node_names',())):
        if c.objExists(node):
            nodes.append(read(node))
    report={'kind':kind,'plan':asdict(plan),'nodes':nodes}
    (OUTPUT/(kind+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    c.file(rename=str(OUTPUT/(kind+'.mb')))
    c.file(save=True,type='mayaBinary',force=True)


original_scale=MayaBodyFkScaleCompensationMixin.capture_body_fk_scale_compensation
def scale(host, plan):
    try:return original_scale(host,plan)
    except Exception:
        capture(host,'scale',plan)
        raise
MayaBodyFkScaleCompensationMixin.capture_body_fk_scale_compensation=scale

original_inbetween=MayaFitInbetweenMixin.apply_inbetween_fk_rewire
def inbetween(host, plan):
    try:return original_inbetween(host,plan)
    except Exception:
        capture(host,'inbetween',plan)
        raise
MayaFitInbetweenMixin.apply_inbetween_fk_rewire=inbetween

def traced_bendy(method):
    def run(host,plan,*args):
        previous=sys.gettrace()
        returns=[]
        def trace(frame,event,value):
            if frame.f_code.co_filename.endswith('maya_fit_bendy.py') and event=='return' and value is False:
                returns.append({'method':frame.f_code.co_name,'line':frame.f_lineno,
                    'locals':{key:repr(item) for key,item in frame.f_locals.items()
                              if key not in ('self','c','spec')}})
            return trace
        sys.settrace(trace)
        try:result=method(host,plan,*args)
        finally:sys.settrace(previous)
        if not result:
            kind=method.__name__
            (OUTPUT/(kind+'-return.json')).write_text(json.dumps(returns,indent=2),encoding='utf-8')
            capture(host,kind,plan)
        return result
    return run
for name in ('capture_fit_bendy_guides','capture_fit_bendy_follow',
             'capture_fit_bendy_micro','capture_fit_bendy_secondary',
             'capture_fit_bendy_circular','capture_fit_bendy_deform'):
    setattr(MayaFitBendyMixin,name,traced_bendy(getattr(MayaFitBendyMixin,name)))

if __name__=='__main__':
    if '--bendy' in sys.argv:
        from maya_original_biped_current_smoke import main as body_main
        body_main(ROOT/'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma',
                  OUTPUT,opm=True,bendy=True)
    else:
        main(ROOT/'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma',
             OUTPUT,opm=True,no_parts='--no-parts' in sys.argv)
