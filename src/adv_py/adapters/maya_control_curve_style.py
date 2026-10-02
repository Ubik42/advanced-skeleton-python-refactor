"""Original asSetCurveColor, asSetCurveWidth and asSnapRotateCurve writes."""
from adv_py.core.control_curve_style import validate_curve_width,snap_rotation
from adv_py.core.control_curves import ControlCurveValidationError


def _shapes(host,controls):
    c=host._cmds
    result=[]
    seen=set()
    for requested in controls:
        matches=c.ls(requested,long=True,type='transform') or []
        if len(matches)!=1:
            raise ControlCurveValidationError('控制器不存在或名称不唯一：'+requested)
        control=matches[0]
        if control in seen:
            raise ControlCurveValidationError('控制器重复：'+control)
        seen.add(control)
        result.append((control,tuple(c.listRelatives(control,shapes=True,fullPath=True) or [])))
    return tuple(result)


def set_palette(host,controls,palette):
    host._require_transaction()
    c=host._cmds;raw=getattr(c,'raw',c)
    rows=_shapes(host,controls)
    default=raw.colorIndex(palette.index,query=True) if palette.index else (0.,0.,0.)
    rgb=palette.rgb if palette.rgb is not None else tuple(default)
    version=float(raw.about(version=True).split()[0])
    use_rgb=palette.uses_rgb(default,version)
    count=0
    for _,shapes in rows:
        for shape in shapes:
            host._transaction_changed=True
            c.setAttr(shape+'.overrideEnabled',True)
            c.setAttr(shape+'.overrideColor',palette.index)
            c.setAttr(shape+'.overrideRGBColors',use_rgb)
            if use_rgb:c.setAttr(shape+'.overrideColorRGB',*rgb,type='double3')
            count+=1
    return count


def set_width(host,controls,width):
    host._require_transaction()
    width=validate_curve_width(width)
    c=host._cmds
    rows=_shapes(host,controls)
    count=0
    for _,shapes in rows:
        for shape in shapes:
            if not c.attributeQuery('lineWidth',node=shape,exists=True):
                continue
            host._transaction_changed=True
            c.setAttr(shape+'.lineWidth',width)
            count+=1
    return count


def snap_rotate(host,controls,axis):
    host._require_transaction()
    rotation=snap_rotation(axis)
    c=host._cmds
    rows=_shapes(host,controls)
    count=0
    for _,shapes in rows:
        for shape in shapes:
            host._transaction_changed=True
            c.rotate(*rotation,shape+'.cv[0:999]',relative=True,
                     objectCenterPivot=True,objectSpace=True)
            count+=1
    return count
