"""Source RP IKFKAligned matrix and addCtrl/nonZero/localOrient branches."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_adv_icons import create_adv_icon,original_fit_icon_axis_offset
from .maya_original_transform_channels import (
    align_original_transform,lock_original_transform_channels,
)


def _end_orientation(c,spec,aligned):
    # MEL 80916: connect before applying any ikLocal controller transforms.
    c.setAttr(spec.chain[-1]+'.jointOrient',0.,0.,0.,type='double3')
    matrix=c.createNode('multMatrix',name=spec.source_orientation_matrix,skipSelect=True)
    decompose=c.createNode('decomposeMatrix',name=spec.wrist_constraint_name,skipSelect=True)
    c.setAttr(decompose+'.inputRotateOrder',spec.source_rotation_order)
    c.connectAttr(aligned+'.worldMatrix[0]',matrix+'.matrixIn[0]')
    c.connectAttr(spec.chain[-1]+'.parentInverseMatrix[0]',matrix+'.matrixIn[1]')
    c.connectAttr(matrix+'.matrixSum',decompose+'.inputMatrix')
    c.connectAttr(decompose+'.outputRotate',spec.chain[-1]+'.rotate')


def _end_aligned_offset(host,name,parent,spec,rotate_order=None):
    c=host._cmds
    if not spec.source_align_joint_path:
        return host._spine_frame(name,parent,spec.wrist_position,spec.wrist_axes)
    node=c.createNode('transform',name=name,parent=parent,skipSelect=True)
    if rotate_order is not None:
        c.setAttr(node+'.rotateOrder',rotate_order)
    return align_original_transform(c,node,spec.source_align_joint_path,False,True)


def create(host,spec):
    c=host._cmds
    driver=spec.wrist_sub_path or spec.wrist_control_path
    for extra in (spec.wrist_extra_path,spec.pole_extra_path):
        lock_original_transform_channels(c,extra,False,False,True,True)
    offset=_end_aligned_offset(host,spec.source_aligned_offset.rsplit('|',1)[-1],driver,spec)
    aligned=c.createNode('transform',name=spec.orientation_source.rsplit('|',1)[-1],
                         parent=offset,skipSelect=True)
    aligned=(c.ls(aligned,long=True) or [aligned])[0]
    _end_orientation(c,spec,aligned)
    if spec.ik_local_mode=='addCtrl':
        local=_end_aligned_offset(host,spec.source_local_offset.rsplit('|',1)[-1],driver,spec,
                                  rotate_order=spec.source_rotation_order)
        extra=host._create_body_extra_layer(local,spec.source_local_extra.rsplit('|',1)[-1],
                                            spec.source_local_extra)
        lock_original_transform_channels(c,extra,False,False,True,True)
        c.setAttr(extra+'.rotateOrder',spec.source_rotation_order)
        control=create_adv_icon(c,name=spec.source_local_control.rsplit('|',1)[-1],
            parent=extra,template='IKLocal_icon',radius=spec.radius,fallback_normal=(1.,0.,0.),
            axis_offset=original_fit_icon_axis_offset(c,spec.source_fit_joint_names,side=spec.side.value)
                        if spec.source_fit_joint_names else (0.,0.,0.),mirror_left=spec.side.value=='L')
        c.setAttr(control+'.rotateOrder',spec.source_rotation_order)
        lock_original_transform_channels(c,control,True,False,True,True)
        c.parent(aligned,control,absolute=True)
    elif spec.ik_local_mode=='nonZero':
        offset=c.parent(offset,world=True,absolute=True)[0]
        helper=c.createNode('transform',name='tempXform',skipSelect=True)
        try:
            if spec.source_middle_joint_path:
                helper=align_original_transform(c,helper,spec.source_middle_joint_path)
            else:
                c.xform(helper,worldSpace=True,matrix=tuple(
                    value for axis in spec.source_middle_axes for value in (*axis,0.))
                    +(*spec.source_middle_position,1.))
            aim=c.aimConstraint(helper,spec.wrist_control_path,aimVector=(1.,0.,0.),
                                upVector=(0.,1.,0.),worldUpType='object',worldUpObject=helper)
            c.delete(aim)
            if spec.source_foot_orientation:
                aim=c.aimConstraint(helper,spec.wrist_control_path,aimVector=(0.,1.,0.),
                    upVector=(0.,0.,1.),worldUpVector=(0.,1.,0.),
                    worldUpType='objectrotation',worldUpObject=helper)
                c.delete(aim)
        finally:
            c.delete(helper)
        offset=c.parent(offset,driver,absolute=True)[0]
        if spec.wrist_align_path:
            align_original_transform(c,spec.wrist_align_path,spec.wrist_control_path,False,True)
    elif spec.ik_local_mode=='localOrient':
        offset=c.parent(offset,world=True,absolute=True)[0]
        helper=c.createNode('transform',name='tempXform',skipSelect=True)
        try:
            target=spec.source_fk_orientation_path or spec.wrist_align_parent_path
            if target:
                helper=align_original_transform(c,helper,target,False,True)
            else:
                c.xform(helper,worldSpace=True,matrix=tuple(
                    value for axis in spec.wrist_axes for value in (*axis,0.))+(0.,0.,0.,1.))
            handle=c.parent(spec.handle_name,world=True,absolute=True)[0]
            align_original_transform(c,spec.wrist_offset_path,helper,False,True)
            c.parent(handle,offset,driver,absolute=True)
        finally:
            c.delete(helper)
        offset=spec.source_aligned_offset
        c.setAttr(offset+'.rotate',0.,0.,0.,type='double3')
        if spec.wrist_align_path:
            c.setAttr(spec.wrist_align_path+'.rotate',0.,0.,0.,type='double3')
        for node in (spec.wrist_control_path,spec.wrist_extra_path,
                     spec.pole_control_path,spec.pole_extra_path):
            c.addAttr(node,longName='ikLocal',attributeType='bool',defaultValue=True,keyable=False)
    parent=c.listRelatives(spec.handle_name,parent=True,fullPath=True) or []
    driver_path=(c.ls(driver,long=True) or [driver])[0]
    if parent != [driver_path]:
        c.parent(spec.handle_name,driver,absolute=True)
    if spec.ik_local_mode=='localOrient':
        for node in (spec.wrist_control_path,spec.pole_control_path):
            c.setAttr(node+'.rotateOrder',spec.source_rotation_order)


def capture_orientation(host,spec):
    c=host._cmds
    if (c.nodeType(spec.source_orientation_matrix)!='multMatrix'
            or c.nodeType(spec.wrist_constraint_name)!='decomposeMatrix'
            or c.getAttr(spec.wrist_constraint_name+'.inputRotateOrder')!=spec.source_rotation_order):
        raise FitSkeletonValidationError('来源 RP IK 末端矩阵朝向类型改变')
    edges=((spec.source_foot_matrix or spec.orientation_source+'.worldMatrix[0]',spec.source_orientation_matrix+'.matrixIn[0]'),
           (spec.chain[-1]+'.parentInverseMatrix[0]',spec.source_orientation_matrix+'.matrixIn[1]'),
           (spec.source_orientation_matrix+'.matrixSum',spec.wrist_constraint_name+'.inputMatrix'),
           (spec.wrist_constraint_name+'.outputRotate',spec.chain[-1]+'.rotate'))
    if any(not c.isConnected(source,destination) for source,destination in edges):
        raise FitSkeletonValidationError('来源 RP IK 末端朝向矩阵连接改变')
    return spec.wrist_constraint_name,spec.orientation_source,spec.chain[-1]
