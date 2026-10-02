"""Ordered original asSelectCurve filters, without changing selection scope."""
from fnmatch import fnmatchcase

from .control_curves import ControlCurveValidationError


CONTROL_CURVE_TYPES=('FK','IK','FKIK','Fingers','*Slider','Bend','*All',
                     'Face:A','Face:B','Face:C','Face:Aim')
CONTROL_CURVE_SIDES=('Right','Left','Middle','*All')


def select_curve_members(members,controller_type,side,*,face_connections=()):
    if controller_type not in CONTROL_CURVE_TYPES or side not in CONTROL_CURVE_SIDES:
        raise ControlCurveValidationError('控制器选择类型或侧别无效')
    pattern='FK*Finger*' if controller_type=='Fingers' else controller_type
    suffix={'Right':'_R','Left':'_L','Middle':'_M','*All':''}[side]
    selected=[]
    for member in members:
        name=member.rsplit('|',1)[-1].rsplit(':',1)[-1]
        if 'Extra' in name:
            continue
        if pattern!='*All':
            if not fnmatchcase(name,pattern+'*'):
                continue
            if pattern=='FK' and fnmatchcase(name,'FKIK*'):
                continue
        if suffix and not name.endswith(suffix):
            continue
        selected.append(member)
    if controller_type.startswith('Face:'):
        for node in face_connections:
            name=node.rsplit('|',1)[-1].rsplit(':',1)[-1]
            if not suffix or name.endswith(suffix):selected.append(node)
    return tuple(selected)
