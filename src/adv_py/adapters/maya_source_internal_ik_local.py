"""Create source internal IKLocal only under an existing FK parent follower."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_adv_icons import create_adv_icon,original_fit_icon_axis_offset
from .maya_original_transform_channels import (
    align_original_transform,lock_original_transform_channels,
)


def create(host,spec):
    host._require_transaction()
    host._transaction_changed=True
    c=host._cmds
    names=(spec.control_name,spec.offset_path.rsplit('|',1)[-1],
           spec.extra_path.rsplit('|',1)[-1],spec.constraint_name)
    if any(host.find_name_collisions(name) for name in names):
        raise FitSkeletonValidationError('来源内部 IKLocal 名称冲突')
    offset=c.createNode('transform',name=names[1],skipSelect=True)
    c.setAttr(offset+'.rotateOrder',spec.rotate_order)
    c.xform(offset,worldSpace=True,translation=spec.world_position)
    extra=c.createNode('transform',name=names[2],parent=offset,skipSelect=True)
    c.setAttr(extra+'.rotateOrder',spec.rotate_order)
    control=create_adv_icon(c,name=spec.control_name,parent=extra,
        template='IKLocal_icon',radius=spec.radius,fallback_normal=(1.,0.,0.),
        axis_offset=original_fit_icon_axis_offset(c,spec.fit_joint_names,side=spec.side)
                    if spec.fit_joint_names else (0.,0.,0.),mirror_left=spec.side=='L')
    c.setAttr(control+'.rotateOrder',spec.rotate_order)
    lock_original_transform_channels(c,extra,False,False,True,True)
    if spec.orientation_target:
        offset=align_original_transform(c,offset,spec.orientation_target,False,True)
    c.parent(offset,spec.offset_path.rsplit('|',1)[0],absolute=True)
    if c.objExists(spec.old_follow_constraint):
        c.delete(spec.old_follow_constraint)
    c.parentConstraint(spec.control_path,spec.target,
                       maintainOffset=True,name=spec.constraint_name)
    c.connectAttr(spec.visibility_source,spec.offset_path+'.visibility')
