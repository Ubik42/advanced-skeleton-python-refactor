"""Advanced Root/COG and original two-stage LegLock rotation matrices."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_adv_icons import create_adv_icon


def _matrix(value):
    return tuple(value[0]) if len(value)==1 and isinstance(value[0],(tuple,list)) else tuple(value)


def create_controls(host,plan):
    host._require_transaction()
    host._transaction_changed=True
    c=host._cmds
    for spec in (*plan.cogs,plan.root_x):
        if any(host.find_name_collisions(name) for name in
               (spec.offset_name,spec.extra_name,spec.control_name)):
            raise FitSkeletonValidationError('来源 Root／COG 控制名称冲突')
        offset=c.createNode('transform',name=spec.offset_name,
                            parent=spec.offset_path.rsplit('|',1)[0],skipSelect=True)
        c.xform(offset,worldSpace=True,translation=spec.world_position)
        extra=host._create_body_extra_layer(spec.offset_path,spec.extra_name,spec.extra_path)
        control=create_adv_icon(c,name=spec.control_name,parent=extra,
            template='Root_icon' if spec is plan.root_x else 'COG_icon',radius=spec.radius,
            fallback_normal=(0.,1.,0.))
        if spec is plan.root_x:
            c.setAttr(control+'.rotateOrder',3)
        for attribute in ('scaleX','scaleY','scaleZ','visibility'):
            c.setAttr(extra+'.'+attribute,lock=True,keyable=False)
        for axis in 'XYZ':
            c.setAttr(control+'.scale'+axis,lock=True,keyable=False)
    host._spine_frame('AdvPy_LegLockConstrained',plan.leg_lock_path.rsplit('|',1)[0],
                      plan.position,plan.axes)


def connect_fk_root(host,plan):
    from maya.api import OpenMaya as om
    c=host._cmds
    world=om.MMatrix(c.xform(plan.fk_offset,query=True,worldSpace=True,matrix=True))
    source=om.MMatrix(c.xform(plan.root_x.control_path,query=True,worldSpace=True,matrix=True))
    matrix=c.createNode('multMatrix',name='AdvPy_SourceRootFollowMM',skipSelect=True)
    c.setAttr(matrix+'.matrixIn[0]',*tuple(world*source.inverse()),type='matrix')
    c.connectAttr(plan.root_x.control_path+'.worldMatrix[0]',matrix+'.matrixIn[1]')
    c.connectAttr(plan.fk_offset+'.parentInverseMatrix[0]',matrix+'.matrixIn[2]')
    for kind,value in (('translate',0.),('rotate',0.),('scale',1.),('shear',0.)):
        c.setAttr(plan.fk_offset+'.'+kind,value,value,value,type='double3')
    if plan.use_offset_parent_matrix:
        c.connectAttr(matrix+'.matrixSum',plan.fk_offset+'.offsetParentMatrix')
    else:
        dm=c.createNode('decomposeMatrix',name='AdvPy_SourceRootFollowDM',skipSelect=True)
        c.connectAttr(matrix+'.matrixSum',dm+'.inputMatrix')
        c.connectAttr(plan.fk_offset+'.rotateOrder',dm+'.inputRotateOrder')
        for kind in ('Translate','Rotate','Scale','Shear'):
            c.connectAttr(dm+'.output'+kind,plan.fk_offset+'.'+kind.lower())
    if not plan.hip_swing_no_parts:
        c.createNode('transform',name='AdvPy_SourceRootHS_M',parent=plan.fk_control,skipSelect=True)


def connect_outputs(host,plan,body,fk,splines,generated_sources):
    host._require_transaction()
    host._transaction_changed=True
    from .maya_source_spline_start import create
    current_sources=dict(generated_sources)
    current_sources.update((joint.path,joint.source_joint) for spline in splines for joint in spline.joints)
    for spline in splines:
        create(host,spline,fk,tuple(current_sources.items()))
    connect_leg_lock(host,plan)
    connect_branch_offsets(host,plan)


def connect_branch_offsets(host,plan):
    """Cancel the Root FK parent rotation in non-first Root branches."""
    from maya.api import OpenMaya as om
    c=host._cmds
    source=plan.leg_lock_path+'.worldMatrix[0]'
    source_bind=om.MMatrix(_matrix(c.getAttr(source)))
    for offset in plan.branch_offsets:
        bind=om.MMatrix(c.xform(offset,query=True,worldSpace=True,matrix=True))
        name=offset.rsplit('|',1)[-1]+'LegLock'
        matrix=c.createNode('multMatrix',name=name+'MM',skipSelect=True)
        c.setAttr(matrix+'.matrixIn[0]',*tuple(bind*source_bind.inverse()),type='matrix')
        c.connectAttr(source,matrix+'.matrixIn[1]')
        c.connectAttr(offset+'.parentInverseMatrix[0]',matrix+'.matrixIn[2]')
        # Offsets are owned by the source planner. Part follow graphs are
        # excluded from this list and keep their existing matrix input.
        for kind,value in (('translate',0.),('rotate',0.),('scale',1.),('shear',0.)):
            c.setAttr(offset+'.'+kind,value,value,value,type='double3')
        if plan.use_offset_parent_matrix:
            c.connectAttr(matrix+'.matrixSum',offset+'.offsetParentMatrix')
        else:
            dm=c.createNode('decomposeMatrix',name=name+'DM',skipSelect=True)
            c.connectAttr(matrix+'.matrixSum',dm+'.inputMatrix')
            c.connectAttr(offset+'.rotateOrder',dm+'.inputRotateOrder')
            for kind in ('Translate','Rotate','Scale','Shear'):
                c.connectAttr(dm+'.output'+kind,offset+'.'+kind.lower())


def connect_leg_lock(host,plan):
    c=host._cmds
    source=plan.body_root+'.worldMatrix[0]'
    if plan.leg_lock_enabled:
        c.addAttr(plan.fk_control,longName='legLock',attributeType='double',defaultValue=10.,
                  softMinValue=0.,softMaxValue=10.,keyable=True)
        unit=c.createNode('unitConversion',name='AdvPy_SourceRootLegLockUnit',skipSelect=True)
        c.setAttr(unit+'.conversionFactor',.1)
        c.connectAttr(plan.fk_control+'.legLock',unit+'.input')
    if plan.leg_lock_enabled and not plan.hip_swing_no_parts:
        relative=c.createNode('multMatrix',name='AdvPy_SourceRootRelativeMM',skipSelect=True)
        c.connectAttr(plan.relative_source or plan.hs_path+'.worldMatrix[0]',relative+'.matrixIn[0]')
        c.connectAttr(plan.fk_offset+'.worldInverseMatrix[0]',relative+'.matrixIn[1]')
        rotation=c.createNode('blendMatrix',name='AdvPy_SourceRootRemoveRotBM',skipSelect=True)
        c.connectAttr(relative+'.matrixSum',rotation+'.target[0].targetMatrix')
        c.connectAttr(unit+'.output',rotation+'.target[0].weight')
        pick=c.createNode('pickMatrix',name='AdvPy_SourceRootRemoveRotPM',skipSelect=True)
        c.connectAttr(rotation+'.outputMatrix',pick+'.inputMatrix')
        for kind in ('Translate','Scale','Shear'):
            c.setAttr(pick+'.use'+kind,False)
        inverse=c.createNode('inverseMatrix',name='AdvPy_SourceRootRemoveRotIM',skipSelect=True)
        c.connectAttr(pick+'.outputMatrix',inverse+'.inputMatrix')
        fk_only=c.createNode('blendMatrix',name='AdvPy_SourceRootRemoveRotBM2',skipSelect=True)
        c.connectAttr(inverse+'.outputMatrix',fk_only+'.target[0].targetMatrix')
        if plan.spline_reverse:
            c.connectAttr(plan.spline_reverse,fk_only+'.target[0].weight')
        else:
            c.setAttr(fk_only+'.target[0].weight',1.)
    if plan.leg_lock_enabled or plan.hip_swing_no_parts:
        world=c.createNode('multMatrix',name='AdvPy_SourceRootRemoveRotMM',skipSelect=True)
        if not plan.hip_swing_no_parts:
            c.connectAttr(fk_only+'.outputMatrix',world+'.matrixIn[0]')
        c.connectAttr(plan.fk_receiver+'.worldMatrix[0]',world+'.matrixIn[1]')
        source=world+'.matrixSum'
        if plan.spline_ik_source:
            blend=c.createNode('blendMatrix',name='AdvPy_SourceLegLockSplineBM',skipSelect=True)
            c.connectAttr(source,blend+'.inputMatrix')
            c.connectAttr(plan.spline_ik_source+'.worldMatrix[0]',blend+'.target[0].targetMatrix')
            c.connectAttr(plan.spline_mode,blend+'.target[0].weight')
            source=blend+'.outputMatrix'
    local=c.createNode('multMatrix',name='AdvPy_SourceLegLockOutputMM',skipSelect=True)
    c.connectAttr(source,local+'.matrixIn[0]')
    c.connectAttr(plan.leg_lock_path+'.parentInverseMatrix[0]',local+'.matrixIn[1]')
    dm=c.createNode('decomposeMatrix',name='AdvPy_SourceLegLockDM',skipSelect=True)
    c.connectAttr(local+'.matrixSum',dm+'.inputMatrix')
    c.connectAttr(plan.leg_lock_path+'.rotateOrder',dm+'.inputRotateOrder')
    for kind in ('Translate','Rotate','Scale','Shear'):
        c.connectAttr(dm+'.output'+kind,plan.leg_lock_path+'.'+kind.lower())
