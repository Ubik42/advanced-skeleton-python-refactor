"""Python ports of ADV's two bundled MoCapZeroOut template procedures.

The values and namespace concatenation below are literal source behavior.
Custom user MEL files are not silently executed by the Python refactor.
"""
from .maya_source_name_matcher import source_name_matcher_template_path


def apply_zero_out_hook(host,template_name,namespace):
    path=source_name_matcher_template_path(template_name,mocap=True)
    if not path.with_suffix('.mel').is_file():return ()
    c=getattr(host._cmds,'raw',host._cmds)
    if template_name=='Mixamo':
        values=((namespace+':Spine','rotate',(0.,0.,0.)),)
    elif template_name=='Plask':
        # Plask.mel uses the namespace field as-is (without adding ':').
        # Changing this would silently alter the original custom procedure.
        values=((namespace+'hips','rotate',(-90.,0.,90.)),
            (namespace+'rightUpLeg','rotateZ',(180.,)),
            (namespace+'leftUpLeg','rotateZ',(180.,)),
            (namespace+'rightFoot','rotateZ',(-90.,)),
            (namespace+'leftFoot','rotateZ',(-90.,)),
            (namespace+'rightShoulder','rotate',(90.,90.,0.)),
            (namespace+'leftShoulder','rotate',(-90.,-90.,0.)))
    else:
        raise ValueError('该自定义 MoCapZeroOut MEL 尚未复刻为 Python：'+str(path.with_suffix('.mel')))
    applied=[]
    for target,attribute,value in values:
        if not c.objExists(target):continue
        host._transaction_changed=True
        c.setAttr(target+'.'+attribute,*value,**({'type':'float3'} if len(value)==3 else {}))
        applied.append(target+'.'+attribute)
    return tuple(applied)
