"""Leg PoleAim matrix chain for OPM character builds."""
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaBodyPoleAimMixin:
    def create_body_leg_pole_aim(self, spec):
        self._require_transaction()
        c = self._cmds
        for path in (spec.ik_root, spec.ankle_control,
                     spec.ankle_frame_parent, spec.pole_offset):
            if (c.ls(path, long=True, type='transform') or []) != [path]:
                raise FitSkeletonValidationError('PoleAim 输入路径无效：' + path)
        if (c.ls(spec.parent_source, long=True) or []) != [spec.parent_source] or c.nodeType(spec.parent_source) not in ('joint', 'transform'):
            raise FitSkeletonValidationError('PoleAim 父级来源无效')
        if not c.isConnected(spec.swivel_plug, spec.handle_twist,ignoreUnitConversion=True):
            raise FitSkeletonValidationError('PoleAim 接管前 swivel 输入已变化')
        if any(self.find_name_collisions(name) for name in spec.node_names):
            raise FitSkeletonValidationError('PoleAim 节点名称已占用')
        self._transaction_changed = True
        frame = c.createNode('transform', name=spec.frame_name,
                             parent=spec.ik_root, skipSelect=True)
        c.xform(frame, worldSpace=True,
                translation=c.xform(spec.parent_source, query=True,
                                    worldSpace=True, translation=True))
        c.xform(frame, worldSpace=True,
                rotation=c.xform(spec.parent_source, query=True,
                                 worldSpace=True, rotation=True))
        c.parentConstraint(spec.parent_source, frame, maintainOffset=False,
                           name=spec.frame_name + 'Constraint')
        aligned = c.createNode('transform', name=spec.aligned_name,
                               parent=spec.ankle_frame_parent, skipSelect=True)
        # MEL 80914 aligns IKFKAlignedOffset to the deformation end joint,
        # before PoleAim reads its Z reference; world-oriented IK is different.
        orientation_source=spec.aligned_orientation_source or spec.ankle_control
        if not c.objExists(orientation_source):
            raise FitSkeletonValidationError('PoleAim 对齐来源缺失')
        c.xform(aligned, worldSpace=True,
                rotation=c.xform(orientation_source, query=True,
                                 worldSpace=True, rotation=True))
        aim = c.createNode('transform', name=spec.aim_name,
                           parent=spec.ik_root, skipSelect=True)
        matrix = c.createNode('aimMatrix', name=spec.matrix_name)
        c.setAttr(matrix + '.secondaryMode', 2)
        c.setAttr(matrix + '.secondaryInputAxis', 0, 0, 1,
                  type='float3')
        c.setAttr(matrix + '.secondaryTargetVector', 0, 0, 1,
                  type='float3')
        c.connectAttr(frame + '.worldMatrix[0]', matrix + '.inputMatrix')
        c.connectAttr(spec.ankle_control + '.worldMatrix[0]',
                      matrix + '.primaryTargetMatrix')
        c.connectAttr(aligned + '.worldMatrix[0]',
                      matrix + '.secondaryTargetMatrix')
        swivel = c.createNode('composeMatrix', name=spec.swivel_name)
        local = c.createNode('multMatrix', name=spec.local_name)
        c.connectAttr(swivel + '.outputMatrix', local + '.matrixIn[0]')
        c.connectAttr(matrix + '.outputMatrix', local + '.matrixIn[1]')
        c.connectAttr(spec.ik_root + '.worldInverseMatrix[0]',
                      local + '.matrixIn[2]')
        c.connectAttr(local + '.matrixSum', aim + '.offsetParentMatrix')
        target = c.createNode('transform', name=spec.target_name,
                              parent=aim, skipSelect=True)
        c.xform(target, worldSpace=True,
                translation=c.xform(spec.pole_offset, query=True,
                                    worldSpace=True, translation=True))
        if spec.aligned_orientation_source:
            c.xform(target,worldSpace=True,rotation=c.xform(
                spec.pole_offset,query=True,worldSpace=True,rotation=True))
        c.disconnectAttr(c.connectionInfo(spec.handle_twist,sourceFromDestination=True), spec.handle_twist)
        c.connectAttr(spec.swivel_plug, swivel + '.inputRotateX')
        if spec.follow_name:
            c.parentConstraint(target, spec.pole_offset,
                               maintainOffset=True, name=spec.follow_name)
        self.capture_body_leg_pole_aim(spec)

    def capture_body_leg_pole_aim(self, spec, *, check_initial_pose=True):
        c = self._cmds
        expected = ((spec.frame_path, 'transform'),
                    (spec.aligned_path, 'transform'),
                    (spec.aim_path, 'transform'),
                    (spec.target_path, 'transform'),
                    (spec.matrix_name, 'aimMatrix'),
                    (spec.swivel_name, 'composeMatrix'),
                    (spec.local_name, 'multMatrix'))
        for path, kind in expected:
            if (c.ls(path, long=True, type=kind) or []) != [path]:
                raise FitSkeletonValidationError('PoleAim 节点缺失：' + path)
        constraint = spec.frame_name + 'Constraint'
        if not c.objExists(constraint) or c.nodeType(constraint) != 'parentConstraint':
            raise FitSkeletonValidationError('PoleAim 父级参考约束缺失')
        sources = c.parentConstraint(constraint, query=True,
                                     targetList=True) or []
        if tuple(self._resolve_connected_node(node)
                 for node in sources) != (spec.parent_source,):
            raise FitSkeletonValidationError('PoleAim 父级参考框架变化')
        if spec.follow_name:
            if (not c.objExists(spec.follow_name)
                    or c.nodeType(spec.follow_name) != 'parentConstraint'):
                raise FitSkeletonValidationError('PoleAim Pole 跟随约束缺失')
            follow_sources = c.parentConstraint(
                spec.follow_name, query=True, targetList=True) or []
            if tuple(self._resolve_connected_node(node)
                     for node in follow_sources) != (spec.target_path,):
                raise FitSkeletonValidationError('PoleAim Pole 跟随来源变化')
        edges = (
            (spec.frame_path + '.worldMatrix[0]',
             spec.matrix_name + '.inputMatrix'),
            (spec.ankle_control + '.worldMatrix[0]',
             spec.matrix_name + '.primaryTargetMatrix'),
            (spec.aligned_path + '.worldMatrix[0]',
             spec.matrix_name + '.secondaryTargetMatrix'),
            (spec.swivel_plug, spec.swivel_name + '.inputRotateX'),
            (spec.swivel_name + '.outputMatrix',
             spec.local_name + '.matrixIn[0]'),
            (spec.matrix_name + '.outputMatrix',
             spec.local_name + '.matrixIn[1]'),
            (spec.ik_root + '.worldInverseMatrix[0]',
             spec.local_name + '.matrixIn[2]'),
            (spec.local_name + '.matrixSum',
             spec.aim_path + '.offsetParentMatrix'),
        )
        if any(not c.isConnected(source, target,ignoreUnitConversion=True)
               for source, target in edges):
            raise FitSkeletonValidationError('PoleAim 矩阵或 swivel 连接不完整')
        if c.connectionInfo(spec.handle_twist,
                            sourceFromDestination=True):
            raise FitSkeletonValidationError('PoleAim 模式仍由 IK Handle twist 驱动')
        if c.getAttr(spec.matrix_name + '.secondaryMode') != 2:
            raise FitSkeletonValidationError('PoleAim 副轴求解模式变化')
        for attribute in ('secondaryInputAxis', 'secondaryTargetVector'):
            value = c.getAttr(spec.matrix_name + '.' + attribute)[0]
            if any(abs(a - b) > 1e-8
                   for a, b in zip(value, (0.0, 0.0, 1.0))):
                raise FitSkeletonValidationError('PoleAim 副轴向量变化')
        if check_initial_pose:
            position = c.xform(spec.target_path, query=True,
                               worldSpace=True, translation=True)
            if any(abs(a - b) > 1e-4
                   for a, b in zip(position, spec.pole_position)):
                raise FitSkeletonValidationError('PoleAim 中性目标位置漂移')
        return True


def audit_registered_pole_aim(host, registration):
    """Recheck the stored PoleAim graph without assuming a neutral pose."""
    from adv_py.core.body_leg_pole_aim import BodyLegPoleAimSpec
    from adv_py.core.fit_symmetry import FitBuildSide

    channels = {channel.key: channel for channel in registration.channels}
    for space in registration.spaces.spaces:
        if not space.key.startswith('foot_'):
            continue
        suffix = space.key.rsplit('_', 1)[-1]
        target = space.source('body', 1)
        short_name = target.rsplit('|', 1)[-1]
        namespace = (short_name.rsplit(':', 1)[0] + ':'
                     if ':' in short_name else '')
        expected_name = namespace + f'AdvPy_PoleAimTarget_{suffix}'
        if target.rsplit('|', 1)[-1] != expected_name:
            if space.body_target_sources and target != space.body_source:
                raise FitSkeletonValidationError('Leg PoleAim 登记来源名称不一致')
            continue
        channel = channels.get(f'foot.{suffix}.swivel')
        if channel is None or channel.attribute != 'swivel':
            raise FitSkeletonValidationError('Leg PoleAim swivel 登记缺失')
        ik_root = target.rsplit('|', 2)[0]
        ankle = channel.node
        aligned_parent = (ankle + f'|{namespace}AdvPy_LegIKSub_{suffix}'
                          if host._cmds.objExists(
                              ankle + f'|{namespace}AdvPy_LegIKSub_{suffix}')
                          else ankle)
        group = registration.body_root.split('|')[1]
        parent_source = (f'|{group}|{namespace}MotionSystem|'
                         f'{namespace}RootSystem|'
                         f'{namespace}AdvPy_LegLockConstrained')
        spec = BodyLegPoleAimSpec(
            side=FitBuildSide(suffix),
            parent_source=parent_source,
            ik_root=ik_root,
            ankle_control=ankle,
            ankle_frame_parent=aligned_parent,
            pole_offset=space.targets[1],
            pole_position=(0.0, 0.0, 0.0),
            swivel_plug=ankle + '.swivel',
            handle_twist=f'{namespace}AdvPy_LegIKHandle_{suffix}.twist',
            frame_name=f'{namespace}AdvPy_PoleParentFrame_{suffix}',
            aligned_name=f'{namespace}AdvPy_PoleAlignedOffset_{suffix}',
            aim_name=f'{namespace}AdvPy_PoleAim_{suffix}',
            target_name=expected_name,
            matrix_name=f'{namespace}AdvPy_PoleAimAM_{suffix}',
            swivel_name=f'{namespace}AdvPy_PoleAimSwivelCM_{suffix}',
            local_name=f'{namespace}AdvPy_PoleAimLocalMM_{suffix}',
        )
        host.capture_body_leg_pole_aim(spec, check_initial_pose=False)
