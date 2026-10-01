"""Original Spline CV blendMatrix, stiff and visibility graph."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.source_spline_cv import source_spline_cv_bindings
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.body_controller_layers import audit_body_extra_controller
from .maya_adv_icons import create_adv_icon
from .maya_source_parent_inverse import parent_world_inverse


def capture_control_positions(host, plan):
    """Use the original fractionMode motionPath at the DCC boundary."""
    host._require_transaction()
    if plan.system_name:
        from .maya_spline_scope import spline_scope
        from adv_py.core.spline_names import scope_spline_plan
        with spline_scope(host,plan) as local:
            result=capture_control_positions(host,local)
        return scope_spline_plan(result,plan.system_name)
    c = host._cmds
    curve = c.curve(degree=plan.curve_degree, point=plan.curve_points)
    path = None
    orientation = None
    try:
        shape = (c.listRelatives(curve, shapes=True, fullPath=True) or [])[0]
        path = c.createNode('motionPath', skipSelect=True)
        c.connectAttr(shape+'.worldSpace[0]', path+'.geometryPath')
        c.setAttr(path+'.fractionMode', True)
        c.setAttr(path+'.follow', True)
        c.setAttr(path+'.frontAxis', 0)
        c.setAttr(path+'.upAxis', 1)
        if plan.joints[0].side.value=='L':
            c.setAttr(path+'.inverseFront',True)
        c.setAttr(path+'.worldUpType', 2)
        c.setAttr(path+'.worldUpVector', 0.,1.,0., type='double3')
        c.connectAttr(plan.joints[0].source_joint+'.worldMatrix[0]',path+'.worldUpMatrix')
        orientation = c.createNode('transform',skipSelect=True)
        positions = [tuple(plan.curve_points[0])]
        axes = [plan.joints[0].world_axes]
        if plan.source_world_controls:
            axes[0]=host._spine_world_frame(plan.body_joints[0])[1]
        for index in range(1, len(plan.targets)-1):
            c.setAttr(path+'.uValue', index/(len(plan.targets)-1))
            positions.append(tuple(c.getAttr(path+'.allCoordinates')[0]))
            c.setAttr(orientation+'.rotate', *c.getAttr(path+'.rotate')[0], type='double3')
            matrix = c.xform(orientation,query=True,worldSpace=True,matrix=True)
            axes.append(tuple(tuple(matrix[start:start+3]) for start in (0,4,8)))
        positions.append(tuple(plan.curve_points[-1]))
        axes.append(plan.joints[len(plan.body_joints)-2].world_axes)
        cv_axes = []
        for index in range(len(plan.source_curve_points)):
            c.setAttr(path+'.uValue',index/(len(plan.source_curve_points)-1))
            c.setAttr(orientation+'.rotate',*c.getAttr(path+'.rotate')[0],type='double3')
            matrix = c.xform(orientation,query=True,worldSpace=True,matrix=True)
            cv_axes.append(tuple(tuple(matrix[start:start+3]) for start in (0,4,8)))
        return replace(plan, positions=tuple(positions),source_control_axes=tuple(axes),
                       source_cv_axes=tuple(cv_axes))
    finally:
        if path is not None:
            c.delete(path)
        if orientation is not None:
            c.delete(orientation)
        c.delete(curve)


def create(host, plan, shape):
    c = host._cmds
    bindings = {binding.index: binding for binding in source_spline_cv_bindings(
        plan.source_curve_points, plan.positions)}
    c.addAttr(plan.settings, longName='ikCvVis', attributeType='bool', defaultValue=False)
    c.setAttr(plan.settings+'.ikCvVis', keyable=False, channelBox=True)
    for index, point in enumerate(plan.source_curve_points):
        prefix = f'AdvPy_SplineCV{index}'
        if index in (0, len(plan.source_curve_points)-1):
            driver = plan.driver_targets[0 if index == 0 else -1]
        else:
            cv_axes = ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
            offset = host._spine_frame(prefix+'Offset', plan.cv_offsets[index-1].rsplit('|',1)[0], point, cv_axes)
            driver = plan.cv_controls[index-1]
            extra = plan.cv_extras[index-1] if plan.cv_extras else None
            if extra:
                host._create_body_extra_layer(offset,extra.rsplit('|',1)[-1],extra)
                for attribute in ('scaleX','scaleY','scaleZ','visibility'):
                    c.setAttr(extra+'.'+attribute,lock=True,keyable=False)
            create_adv_icon(c, name=prefix, parent=extra or offset, template='IKcv_icon',
                            radius=.75, fallback_normal=(1.,0.,0.))
            if plan.source_cv_axes:
                frame = host._spine_frame(prefix+'ShapeOrient',plan.root_path,
                                          (0.,0.,0.),plan.source_cv_axes[index])
                try:
                    rotation = c.xform(frame,query=True,worldSpace=True,rotation=True)
                    c.scale(.01,1.,1.,driver+'.cv[*]',relative=True,objectSpace=True)
                    c.rotate(*rotation,driver+'.cv[*]',absolute=True,worldSpace=True)
                finally:
                    c.delete(frame)
            for kind in ('rotate', 'scale'):
                for axis in 'XYZ':
                    c.setAttr(driver+'.'+kind+axis, lock=True, keyable=False)
            c.connectAttr(plan.settings+'.ikCvVis', offset+'.visibility')
            binding = bindings[index]
            follows = []
            for number, target in enumerate((binding.first, binding.second), 1):
                control = plan.source_matrix_targets[target]
                # Capture the original maintained matrix offset in control space.
                temporary = host._spine_frame(prefix+'Bind', control, point, cv_axes)
                try:
                    bind = tuple(c.getAttr(temporary+'.matrix'))
                    if len(bind) == 1 and isinstance(bind[0], (tuple, list)):
                        bind = tuple(bind[0])
                finally:
                    c.delete(temporary)
                follow = c.createNode('multMatrix', name=prefix+f'Follow{number}', skipSelect=True)
                c.setAttr(follow+'.matrixIn[0]', *bind, type='matrix')
                c.connectAttr(control+'.worldMatrix[0]', follow+'.matrixIn[1]')
                follows.append(follow)
            blend = c.createNode('blendMatrix', name=prefix+'Blend', skipSelect=True)
            c.connectAttr(follows[1]+'.matrixSum', blend+'.inputMatrix')
            c.connectAttr(follows[0]+'.matrixSum', blend+'.target[0].targetMatrix')
            c.setAttr(blend+'.target[0].weight', binding.weight)
            parent = c.createNode('multMatrix', name=prefix+'ParentMatrix', skipSelect=True)
            c.connectAttr(blend+'.outputMatrix', parent+'.matrixIn[0]')
            c.connectAttr(parent_world_inverse(host,offset), parent+'.matrixIn[1]')
            for kind, value in (('translate',0.), ('rotate',0.), ('scale',1.)):
                c.setAttr(offset+'.'+kind, value,value,value, type='double3')
            if plan.use_offset_parent_matrix:
                c.connectAttr(parent+'.matrixSum', offset+'.offsetParentMatrix')
            else:
                decompose = c.createNode('decomposeMatrix', name=prefix+'Decompose', skipSelect=True)
                c.connectAttr(parent+'.matrixSum', decompose+'.inputMatrix')
                c.connectAttr(offset+'.rotateOrder', decompose+'.inputRotateOrder')
                for kind in ('Translate','Rotate','Scale','Shear'):
                    c.connectAttr(decompose+'.output'+kind, offset+'.'+kind[0].lower()+kind[1:])
            if binding.stiffness_control is not None:
                control = plan.targets[binding.stiffness_control]
                c.addAttr(control, longName='stiff', attributeType='double',
                          minValue=0., maxValue=10., defaultValue=5., keyable=True)
                stiff = c.createNode('setRange', name=f'AdvPy_SplineStiff{binding.stiffness_control}', skipSelect=True)
                c.connectAttr(control+'.stiff', stiff+'.valueX')
                c.setAttr(stiff+'.minX', binding.weight)
                c.setAttr(stiff+'.maxX', 1.)
                c.setAttr(stiff+'.oldMaxX', 10.)
                c.connectAttr(stiff+'.outValueX', blend+'.target[0].weight')
        matrix = c.createNode('multMatrix', name=prefix+'Matrix', skipSelect=True)
        position = c.createNode('decomposeMatrix', name=prefix+'Position', skipSelect=True)
        c.connectAttr(driver+'.worldMatrix[0]', matrix+'.matrixIn[0]')
        c.connectAttr(plan.curve+'.worldInverseMatrix[0]', matrix+'.matrixIn[1]')
        c.connectAttr(matrix+'.matrixSum', position+'.inputMatrix')
        c.connectAttr(position+'.outputTranslate', shape+f'.controlPoints[{index}]')


def audit(host, plan, shape):
    c = host._cmds
    edges = []
    for index in range(len(plan.source_curve_points)):
        prefix = f'AdvPy_SplineCV{index}'
        driver = (plan.driver_targets[0 if index==0 else -1]
                  if index in (0,len(plan.source_curve_points)-1)
                  else plan.cv_controls[index-1])
        edges.extend(((driver+'.worldMatrix[0]', prefix+'Matrix.matrixIn[0]'),
                      (plan.curve+'.worldInverseMatrix[0]', prefix+'Matrix.matrixIn[1]'),
                      (prefix+'Matrix.matrixSum', prefix+'Position.inputMatrix'),
                      (prefix+'Position.outputTranslate', shape+f'.controlPoints[{index}]')))
    for binding in source_spline_cv_bindings(plan.source_curve_points, plan.positions):
        prefix = f'AdvPy_SplineCV{binding.index}'
        offset = plan.cv_offsets[binding.index-1]
        if plan.cv_extras:
            extra=plan.cv_extras[binding.index-1]
            control=plan.cv_controls[binding.index-1]
            issues=audit_body_extra_controller(offset,control,extra,
                host._capture_body_extra_layer(extra,control),extra_curve=False,
                authored_shapes=getattr(host,'_allow_authored_control_state',False))
            if issues:
                raise FitSkeletonValidationError('来源 Spline CV Extra 层改变：'+'；'.join(issues))
        edges.extend(((plan.settings+'.ikCvVis', offset+'.visibility'),
                      (plan.source_matrix_targets[binding.first]+'.worldMatrix[0]', prefix+'Follow1.matrixIn[1]'),
                      (plan.source_matrix_targets[binding.second]+'.worldMatrix[0]', prefix+'Follow2.matrixIn[1]'),
                      (prefix+'Follow2.matrixSum', prefix+'Blend.inputMatrix'),
                      (prefix+'Follow1.matrixSum', prefix+'Blend.target[0].targetMatrix'),
                      (prefix+'Blend.outputMatrix', prefix+'ParentMatrix.matrixIn[0]'),
                      (parent_world_inverse(host,offset), prefix+'ParentMatrix.matrixIn[1]')))
        if plan.use_offset_parent_matrix:
            edges.append((prefix+'ParentMatrix.matrixSum', offset+'.offsetParentMatrix'))
        else:
            edges.extend(((prefix+'ParentMatrix.matrixSum', prefix+'Decompose.inputMatrix'),
                          (offset+'.rotateOrder', prefix+'Decompose.inputRotateOrder')))
            edges.extend((prefix+'Decompose.output'+kind, offset+'.'+kind[0].lower()+kind[1:])
                         for kind in ('Translate','Rotate','Scale','Shear'))
        if binding.stiffness_control is not None:
            stiff = f'AdvPy_SplineStiff{binding.stiffness_control}'
            edges.extend(((plan.targets[binding.stiffness_control]+'.stiff', stiff+'.valueX'),
                          (stiff+'.outValueX', prefix+'Blend.target[0].weight')))
            if (abs(c.getAttr(stiff+'.minX')-binding.weight)>1e-8
                    or c.getAttr(stiff+'.maxX')!=1. or c.getAttr(stiff+'.oldMaxX')!=10.):
                raise FitSkeletonValidationError('来源 Spline stiff 权重范围改变')
        elif abs(c.getAttr(prefix+'Blend.target[0].weight')-binding.weight)>1e-8:
            raise FitSkeletonValidationError('来源 Spline CV 距离权重改变')
    if any(not c.isConnected(source,destination) for source,destination in edges):
        raise FitSkeletonValidationError('来源 Spline CV 驱动连接改变')
