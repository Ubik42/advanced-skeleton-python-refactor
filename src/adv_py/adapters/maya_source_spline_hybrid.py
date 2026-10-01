"""ADV Spline IKhybrid hierarchy and original endpoint parenting."""
from __future__ import annotations

from math import sqrt

from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_adv_icons import create_adv_icon


def create(host,plan):
    c = host._cmds
    distance = sqrt(sum((a-b)**2 for a,b in zip(plan.positions[0],plan.positions[1])))/10.
    for index, control in enumerate(plan.hybrid_controls):
        offset = control.rsplit('|',1)[0]
        parent = offset.rsplit('|',1)[0]
        axes = plan.source_control_axes[index] if plan.source_control_axes else plan.axes
        host._spine_frame(f'AdvPy_SplineHybrid{index}Offset',parent,
                          plan.positions[index],axes)
        create_adv_icon(c,name=f'AdvPy_SplineHybrid{index}',parent=offset,
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
    for control in plan.hybrid_controls:
        offset = control.rsplit('|',1)[0]
        if ((c.listRelatives(control,parent=True,fullPath=True) or [])!=[offset]
                or (c.listRelatives(offset,parent=True,fullPath=True) or [])!=[offset.rsplit('|',1)[0]]):
            raise FitSkeletonValidationError('来源 Spline IKhybrid 父子链改变')
        shapes = c.listRelatives(control,shapes=True,fullPath=True) or []
        source = ('AdvPy_SplineHybridVisibility.output1D' if visibility_ready
                  else plan.settings+'.ikHybridVis')
        if not shapes or any(not c.isConnected(source,shape+'.visibility')
                             for shape in shapes):
            raise FitSkeletonValidationError('来源 Spline IKhybrid 显示连接改变')
