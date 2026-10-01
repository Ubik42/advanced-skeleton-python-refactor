"""Source RP IKFKAligned matrix and addCtrl/nonZero/localOrient branches."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_adv_icons import create_adv_icon


def create(host,spec):
    c=host._cmds
    driver=spec.wrist_sub_path or spec.wrist_control_path
    for extra in (spec.wrist_extra_path,spec.pole_extra_path):
        for attribute in ('scaleX','scaleY','scaleZ','visibility'):
            c.setAttr(extra+'.'+attribute,lock=True,keyable=False)
    offset=host._spine_frame(spec.source_aligned_offset.rsplit('|',1)[-1],driver,
                             spec.wrist_position,spec.wrist_axes)
    aligned=c.createNode('transform',name=spec.orientation_source.rsplit('|',1)[-1],
                          parent=offset,skipSelect=True)
    aligned=(c.ls(aligned,long=True) or [aligned])[0]
    if spec.ik_local_mode=='addCtrl':
        local=host._spine_frame(spec.source_local_offset.rsplit('|',1)[-1],driver,
                                spec.wrist_position,spec.wrist_axes)
        extra=host._create_body_extra_layer(local,spec.source_local_extra.rsplit('|',1)[-1],
                                            spec.source_local_extra)
        for attribute in ('scaleX','scaleY','scaleZ','visibility'):
            c.setAttr(extra+'.'+attribute,lock=True,keyable=False)
        control=create_adv_icon(c,name=spec.source_local_control.rsplit('|',1)[-1],
            parent=extra,template='IKLocal_icon',radius=spec.radius,fallback_normal=(1.,0.,0.))
        c.setAttr(control+'.rotateOrder',spec.source_rotation_order)
        for kind in ('translate','scale'):
            for axis in 'XYZ':
                c.setAttr(control+'.'+kind+axis,lock=True,keyable=False)
        c.setAttr(control+'.visibility',lock=True,keyable=False)
        c.parent(aligned,control,absolute=True)
    elif spec.ik_local_mode=='nonZero':
        # Preserve the oriented end receiver and handle while the main
        # controller receives the original aim-generated nonzero rotation.
        aligned_world=c.xform(offset,query=True,worldSpace=True,matrix=True)
        handle_world=c.xform(spec.handle_name,query=True,worldSpace=True,matrix=True)
        detached=c.parent(offset,world=True,absolute=True)[0]
        offset=(c.ls(detached,long=True) or [detached])[0]
        helper=host._spine_frame(spec.source_stem+'LocalAim_'+spec.side.value,spec.root_path,
                                spec.source_middle_position,spec.source_middle_axes)
        try:
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
            c.parent(offset,driver,absolute=True)
            c.xform(spec.source_aligned_offset,worldSpace=True,matrix=aligned_world)
            c.xform(spec.handle_name,worldSpace=True,matrix=handle_world)
        if spec.wrist_align_path:
            rotation=c.xform(spec.wrist_control_path,query=True,worldSpace=True,rotation=True)
            c.xform(spec.wrist_align_path,worldSpace=True,rotation=rotation)
    elif spec.ik_local_mode=='localOrient':
        c.setAttr(offset+'.rotate',0.,0.,0.,type='double3')
        if spec.wrist_align_path:
            c.setAttr(spec.wrist_align_path+'.rotate',0.,0.,0.,type='double3')
        for node in (spec.wrist_control_path,spec.wrist_extra_path,
                     spec.pole_control_path,spec.pole_extra_path):
            c.addAttr(node,longName='ikLocal',attributeType='bool',defaultValue=True)
    # The RP creator already parents the ordinary handle to this driver.
    # Maya treats parenting it to its existing parent as a command error.
    parent=c.listRelatives(spec.handle_name,parent=True,fullPath=True) or []
    driver_path=(c.ls(driver,long=True) or [driver])[0]
    if parent != [driver_path]:
        c.parent(spec.handle_name,driver,absolute=True)
    c.setAttr(spec.chain[-1]+'.jointOrient',0.,0.,0.,type='double3')
    c.setAttr(spec.chain[-1]+'.rotateOrder',spec.source_rotation_order)
    if spec.ik_local_mode=='localOrient':
        for node in (spec.wrist_control_path,spec.pole_control_path):
            c.setAttr(node+'.rotateOrder',spec.source_rotation_order)
    matrix=c.createNode('multMatrix',name=spec.source_orientation_matrix,skipSelect=True)
    decompose=c.createNode('decomposeMatrix',name=spec.wrist_constraint_name,skipSelect=True)
    c.connectAttr(spec.orientation_source+'.worldMatrix[0]',matrix+'.matrixIn[0]')
    c.connectAttr(spec.chain[-1]+'.parentInverseMatrix[0]',matrix+'.matrixIn[1]')
    c.connectAttr(matrix+'.matrixSum',decompose+'.inputMatrix')
    c.setAttr(decompose+'.inputRotateOrder',spec.source_rotation_order)
    c.connectAttr(decompose+'.outputRotate',spec.chain[-1]+'.rotate')


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
