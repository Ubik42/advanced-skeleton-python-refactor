"""Leg PoleAim matrix chain for OPM character builds."""
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaBodyPoleAimMixin:
    def create_body_leg_pole_aim(self, spec):
        self._require_transaction()
        c = self._cmds
        for path in (spec.parent_source, spec.ik_root, spec.ankle_control,
                     spec.ankle_frame_parent, spec.pole_offset):
            if (c.ls(path, long=True, type='transform') or []) != [path]:
                raise FitSkeletonValidationError('PoleAim 输入路径无效：' + path)
        if not c.isConnected(spec.swivel_plug, spec.handle_twist):
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
        c.xform(aligned, worldSpace=True,
                rotation=c.xform(spec.ankle_control, query=True,
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
        c.disconnectAttr(spec.swivel_plug, spec.handle_twist)
        c.connectAttr(spec.swivel_plug, swivel + '.inputRotateX')
        self.capture_body_leg_pole_aim(spec)

    def capture_body_leg_pole_aim(self, spec):
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
        if any(not c.isConnected(source, target)
               for source, target in edges):
            raise FitSkeletonValidationError('PoleAim 矩阵或 swivel 连接不完整')
        if c.connectionInfo(spec.handle_twist,
                            sourceFromDestination=True):
            raise FitSkeletonValidationError('PoleAim 模式仍由 IK Handle twist 驱动')
        if c.getAttr(spec.matrix_name + '.secondaryMode') != 2:
            raise FitSkeletonValidationError('PoleAim 副轴求解模式变化')
        position = c.xform(spec.target_path, query=True,
                           worldSpace=True, translation=True)
        if any(abs(a - b) > 1e-4
               for a, b in zip(position, spec.pole_position)):
            raise FitSkeletonValidationError('PoleAim 中性目标位置漂移')
        return True
