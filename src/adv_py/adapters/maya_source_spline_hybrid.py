"""ADV Spline IKhybrid hierarchy and original endpoint parenting."""
from __future__ import annotations

from math import sqrt

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.body_controller_layers import audit_body_extra_controller
from .maya_adv_icons import create_adv_icon


def create(host,plan):
    c = host._cmds
    if plan.source_follow_parent:
        # MEL 81481: the constrained frame is aligned by the parent
        # constraint, before the already-bound Hybrid Offset is parented.
        # Binding it at the Spline start with -mo rotates Main scale into
        # the child's axes, changing the curve even with untouched controls.
        if plan.source_native_follow:
            matrix,axes=host._spine_world_frame(plan.source_follow_parent)
            position=tuple(matrix[12:15])
        else:position,axes=plan.positions[0],plan.axes
        host._spine_frame('AdvPy_SplineIKOffsetConstrained',plan.source_controls_root,
                          position,axes)
        host._spine_frame('AdvPy_SplineHybridFollow',plan.source_controls_root,
                          plan.positions[0],plan.axes)
    distance = sqrt(sum((a-b)**2 for a,b in zip(plan.positions[0],plan.positions[1])))/10.
    if plan.joints[0].side.value=='L':
        distance=-distance
    for index, control in enumerate(plan.hybrid_controls):
        offset = plan.hybrid_offsets[index]
        parent = offset.rsplit('|',1)[0]
        axes = plan.source_control_axes[index] if plan.source_control_axes else plan.axes
        host._spine_frame(f'AdvPy_SplineHybrid{index}Offset',parent,
                          plan.positions[index],axes)
        extra = plan.hybrid_extras[index] if plan.hybrid_extras else None
        if extra:
            extra_parent = plan.hybrid_follow if index==0 and plan.source_follow_parent else offset
            host._create_body_extra_layer(extra_parent,extra.rsplit('|',1)[-1],extra)
            for attribute in ('scaleX','scaleY','scaleZ','visibility'):
                c.setAttr(extra+'.'+attribute,lock=True,keyable=False)
        create_adv_icon(c,name=f'AdvPy_SplineHybrid{index}',parent=extra or offset,
                        template='IKhybrid_icon',radius=1.5,fallback_normal=(1.,0.,0.))
        c.move(distance if index==0 else -distance,0.,0.,control+'.cv[*]',
               relative=True,objectSpace=True,worldSpaceDistance=True)
        for axis in 'XYZ':
            c.setAttr(control+'.scale'+axis,lock=True,keyable=False)


def install_visibility(host,plan):
    c = host._cmds
    c.addAttr(plan.settings,longName='ikHybridVis',attributeType='bool',defaultValue=True)
    c.setAttr(plan.settings+'.ikHybridVis',keyable=False,channelBox=True)
    # Hide the curve shapes, not the transforms: IK endpoints live below
    # this hierarchy and must remain independently visible/selectable.
    for control in plan.hybrid_controls:
        shapes = c.listRelatives(control,shapes=True,fullPath=True) or []
        for shape in shapes:
            c.connectAttr(plan.settings+'.ikHybridVis',shape+'.visibility')


def audit(host,plan,*,visibility_ready=True):
    c = host._cmds
    for index,control in enumerate(plan.hybrid_controls):
        offset = plan.hybrid_offsets[index]
        parent = plan.hybrid_extras[index] if plan.hybrid_extras else offset
        if plan.hybrid_extras:
            extra_parent=plan.hybrid_follow if index==0 and plan.source_follow_parent else offset
            issues=audit_body_extra_controller(extra_parent,control,parent,
                host._capture_body_extra_layer(parent,control),extra_curve=False,
                authored_shapes=getattr(host,'_allow_authored_control_state',False))
            if issues:
                raise FitSkeletonValidationError('来源 Spline IKhybrid Extra 层改变：'+'；'.join(issues))
        if ((c.listRelatives(control,parent=True,fullPath=True) or [])!=[parent]
                or (c.listRelatives(offset,parent=True,fullPath=True) or [])!=[offset.rsplit('|',1)[0]]):
            raise FitSkeletonValidationError('来源 Spline IKhybrid 父子链改变')
        shapes = c.listRelatives(control,shapes=True,fullPath=True) or []
        source = ('AdvPy_SplineHybridVisibility.output1D' if visibility_ready
                  else plan.settings+'.ikHybridVis')
        if not getattr(host,'_allow_authored_control_state',False) and (
                not shapes or any(not c.isConnected(source,shape+'.visibility')
                                  for shape in shapes)):
            raise FitSkeletonValidationError('来源 Spline IKhybrid 显示连接改变')
