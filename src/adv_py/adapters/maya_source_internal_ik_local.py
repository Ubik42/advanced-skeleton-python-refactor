"""Create source internal IKLocal only under an existing FK parent follower."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_adv_icons import create_adv_icon


def create(host,spec):
    host._require_transaction()
    host._transaction_changed=True
    c=host._cmds
    names=(spec.control_name,spec.offset_path.rsplit('|',1)[-1],
           spec.extra_path.rsplit('|',1)[-1],spec.constraint_name)
    if any(host.find_name_collisions(name) for name in names):
        raise FitSkeletonValidationError('来源内部 IKLocal 名称冲突')
    offset=host._spine_frame(names[1],spec.offset_path.rsplit('|',1)[0],
                             spec.world_position,spec.world_axes)
    extra=host._create_body_extra_layer(spec.offset_path,names[2],spec.extra_path)
    control=create_adv_icon(c,name=spec.control_name,parent=extra,
        template='IKLocal_icon',radius=spec.radius,fallback_normal=(1.,0.,0.))
    for node in (offset,extra,control):
        c.setAttr(node+'.rotateOrder',spec.rotate_order)
    for attribute in ('scaleX','scaleY','scaleZ','visibility'):
        c.setAttr(extra+'.'+attribute,lock=True,keyable=False)
    if c.objExists(spec.old_follow_constraint):
        c.delete(spec.old_follow_constraint)
    c.parentConstraint(spec.control_path,spec.target,
                       maintainOffset=True,name=spec.constraint_name)
    c.connectAttr(spec.visibility_source,spec.offset_path+'.visibility')
