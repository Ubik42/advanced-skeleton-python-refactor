"""Native Maya boundary for NameMatcher's AutoRigConstraint pass."""
from __future__ import annotations

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.name_matcher_fit import (
    NameMatcherConstraintPlan, NameMatcherSkinMatrixLink)
from adv_py.core.name_matcher_mocap import NameMatcherMocapPlan

from .maya_source_skeleton_fit import MayaSourceSkeletonFitHost


class MayaNameMatcherHost(MayaSourceSkeletonFitHost):
    def preflight_name_matcher_mocap(self,
            plan: NameMatcherMocapPlan) -> None:
        from maya import cmds as c

        group = self.scene_address('MoCapConstraints')
        if c.objExists(group):
            raise FitSkeletonValidationError(
                'NameMatcher 动捕约束已存在，请先解除旧连接')
        if plan.poles and (not plan.root_control or not c.objExists(
                self.scene_address(plan.root_control))):
            raise FitSkeletonValidationError(
                'NameMatcher Pole Vector 缺少已登记 RootX 控制器')
        for link in plan.links:
            control = self.scene_address(link.control)
            if (len(c.ls(control, long=True, type='transform') or ()) != 1
                    or (c.ls(link.external_joint, long=True,
                             type='joint') or []) != [link.external_joint]):
                raise FitSkeletonValidationError(
                    'NameMatcher 动捕来源或控制器缺失：' + control)
            for channel, enabled in (('translate', link.point),
                                     ('rotate', link.orient)):
                if not enabled:
                    continue
                for axis in 'XYZ':
                    plug = control + '.' + channel + axis
                    if (not c.getAttr(plug, settable=True)
                            or c.connectionInfo(plug,
                                sourceFromDestination=True)):
                        raise FitSkeletonValidationError(
                            'NameMatcher 动捕控制器通道不可接线：' + plug)
            for channel in ('translate', 'rotate'):
                source = c.connectionInfo(
                    link.external_joint + '.' + channel + 'X',
                    sourceFromDestination=True)
                if source and c.nodeType(source.split('.', 1)[0]) in (
                        'pointConstraint', 'orientConstraint',
                        'parentConstraint'):
                    raise FitSkeletonValidationError(
                        'NameMatcher 动捕来源已被约束，可能形成回路：'
                        + link.external_joint)
        for pole in plan.poles:
            control = self.scene_address(pole.control)
            parents = c.listRelatives(pole.middle_joint, parent=True,
                                      fullPath=True) or []
            children = c.listRelatives(pole.middle_joint, children=True,
                                       type='joint', fullPath=True) or []
            if (len(parents) != 1 or len(children) != 1
                    or not c.objExists(control)):
                raise FitSkeletonValidationError(
                    'NameMatcher Pole Vector 缺少连续三关节或控制器：'
                    + pole.middle_joint)
            for axis in 'XYZ':
                plug = control + '.translate' + axis
                if (not c.getAttr(plug, settable=True)
                        or c.connectionInfo(plug,
                            sourceFromDestination=True)):
                    raise FitSkeletonValidationError(
                        'NameMatcher Pole Vector 通道不可接线：' + plug)

    def apply_name_matcher_mocap(self, plan: NameMatcherMocapPlan
            ) -> tuple[tuple[str, str | None, str | None], ...]:
        from maya import cmds as c

        self._require_transaction()
        self.preflight_name_matcher_mocap(plan)
        group = self.scene_address('MoCapConstraints')
        controls = tuple(link.control for link in plan.links) + tuple(
            pole.control for pole in plan.poles)
        before = tuple(tuple(float(value) for value in c.xform(
            self.scene_address(control), query=True,
            worldSpace=True, matrix=True)) for control in controls)
        self._transaction_changed = True
        c.createNode('transform', name=group, skipSelect=True)
        c.addAttr(group, longName='disableConstraints',
                  attributeType='bool', keyable=True)
        created = []
        for link in plan.links:
            control = self.scene_address(link.control)
            point = (c.pointConstraint(link.external_joint, control,
                maintainOffset=True)[0] if link.point else None)
            orient = (c.orientConstraint(link.external_joint, control,
                maintainOffset=True)[0] if link.orient else None)
            for node in (point, orient):
                if node:
                    c.connectAttr(group + '.disableConstraints',
                                  node + '.nodeState')
            created.append((control, point, orient))
        for index, pole in enumerate(plan.poles):
            parents = c.listRelatives(pole.middle_joint, parent=True,
                                      fullPath=True) or []
            children = c.listRelatives(pole.middle_joint, children=True,
                                       type='joint', fullPath=True) or []
            hip, ankle = parents[0], children[0]
            positions = [c.xform(node, query=True, worldSpace=True,
                                 translation=True)
                         for node in (hip, pole.middle_joint, ankle)]
            def distance(a, b):
                return sum((float(x)-float(y))**2
                           for x, y in zip(a, b))**0.5
            dist_a = distance(positions[0], positions[1])
            dist_b = distance(positions[1], positions[2])
            if min(dist_a, dist_b) < 1e-6:
                raise FitSkeletonValidationError(
                    'NameMatcher Pole Vector 关节段长度为零：'
                    + pole.middle_joint)
            a = c.createNode('transform', parent=group,
                             name='AdvPy_MoCapPoleA_' + str(index))
            b = c.createNode('transform', parent=a,
                             name='AdvPy_MoCapPoleB_' + str(index))
            locator = c.createNode('transform', parent=b,
                             name='AdvPy_MoCapPole_' + str(index))
            center_constraint = c.pointConstraint(
                hip, ankle, a, weight=dist_b)[0]
            weights = c.pointConstraint(center_constraint, query=True,
                                        weightAliasList=True) or []
            if len(weights) == 2:
                c.setAttr(center_constraint + '.' + weights[1], dist_a)
            else:
                raise RuntimeError('NameMatcher Pole Vector 中点权重不完整')
            c.orientConstraint(self.scene_address(plan.root_control), a)
            c.setAttr(b + '.translateZ',
                      (dist_a+dist_b) / (10.0 if pole.limb == 'arm'
                                          else -10.0))
            c.aimConstraint(pole.middle_joint, b,
                            aimVector=(1, 0, 0), upVector=(0, 1, 0),
                            worldUpType='vector', worldUpVector=(0, 1, 0))
            c.setAttr(locator + '.translateX', dist_a+dist_b)
            control = self.scene_address(pole.control)
            point = c.pointConstraint(locator, control,
                                      maintainOffset=True)[0]
            c.connectAttr(group + '.disableConstraints',
                          point + '.nodeState')
            created.append((control, point, None))
        result = tuple(created)
        self.verify_name_matcher_mocap(plan, result)
        for control_path, old in zip(controls, before):
            current = tuple(float(value) for value in c.xform(
                self.scene_address(control_path), query=True,
                worldSpace=True, matrix=True))
            if len(current) != len(old) or any(abs(a-b)>1e-4
                    for a,b in zip(old,current)):
                raise RuntimeError('NameMatcher 动捕连接改变控制器当前姿态：'
                                   +control_path)
        return result

    def verify_name_matcher_mocap(self, plan: NameMatcherMocapPlan,
            created: tuple[tuple[str, str | None, str | None], ...]) -> None:
        from maya import cmds as c

        group = self.scene_address('MoCapConstraints')
        if (len(created) != len(plan.links) + len(plan.poles)
                or not c.objExists(group)):
            raise RuntimeError('NameMatcher 动捕约束节点不完整')
        for link, (control, point, orient) in zip(plan.links, created):
            if control != self.scene_address(link.control):
                raise RuntimeError('NameMatcher 动捕约束控制器漂移')
            for node, kind in ((point, 'pointConstraint'),
                               (orient, 'orientConstraint')):
                if node is None:
                    continue
                if (c.nodeType(node) != kind
                        or c.connectionInfo(node + '.nodeState',
                            sourceFromDestination=True)
                        != group + '.disableConstraints'):
                    raise RuntimeError('NameMatcher 动捕禁用开关未接线')
                targets = getattr(c, kind)(node, query=True,
                                            targetList=True) or []
                resolved = [c.ls(item, long=True) or [] for item in targets]
                if resolved != [[link.external_joint]]:
                    raise RuntimeError('NameMatcher 动捕约束来源不一致')
        for pole, (control, point, orient) in zip(
                plan.poles, created[len(plan.links):]):
            if (control != self.scene_address(pole.control)
                    or orient is not None or not point
                    or c.nodeType(point) != 'pointConstraint'
                    or c.connectionInfo(point + '.nodeState',
                        sourceFromDestination=True)
                    != group + '.disableConstraints'):
                raise RuntimeError('NameMatcher Pole Vector 输出约束不完整')

    def capture_name_matcher_skin_links(self,
            plan: NameMatcherConstraintPlan
            ) -> tuple[NameMatcherSkinMatrixLink, ...]:
        from maya import cmds as c

        links = []
        for pair in plan.pairs:
            source = pair.external_joint + '.worldMatrix[0]'
            destinations = c.listConnections(source, source=False,
                destination=True, plugs=True, type='skinCluster') or []
            for destination in destinations:
                if '.matrix[' not in destination:
                    continue
                if c.connectionInfo(destination,
                        sourceFromDestination=True) != source:
                    continue
                if c.getAttr(destination, lock=True):
                    raise FitSkeletonValidationError(
                        'NameMatcher Skin 影响矩阵被锁定：' + destination)
                skin, suffix = destination.split('.', 1)
                if not suffix.startswith('matrix[') or not suffix.endswith(']'):
                    continue
                index = suffix[len('matrix['):-1]
                if not index.isdecimal():
                    continue
                bind_pre = skin + '.bindPreMatrix[' + index + ']'
                value = c.getAttr(bind_pre)
                if len(value) == 1 and isinstance(value[0], (tuple, list)):
                    value = value[0]
                matrix = tuple(float(item) for item in value)
                if len(matrix) != 16:
                    raise FitSkeletonValidationError(
                        'NameMatcher Skin 绑定逆矩阵不完整：' + skin)
                skin_ids = c.ls(skin, uuid=True) or []
                if len(skin_ids) != 1:
                    raise FitSkeletonValidationError(
                        'NameMatcher Skin 节点不唯一：' + skin)
                links.append(NameMatcherSkinMatrixLink(
                    pair.advanced_joint, pair.external_joint,
                    destination, source, matrix,
                    c.connectionInfo(bind_pre,
                        sourceFromDestination=True) or None,
                    skin_ids[0]))
        if not links:
            raise FitSkeletonValidationError(
                'NameMatcher 映射关节没有连接到任何 Skin 影响矩阵')
        if len({link.destination for link in links}) != len(links):
            raise FitSkeletonValidationError(
                'NameMatcher Skin 影响矩阵目标重复')
        return tuple(sorted(links, key=lambda item: item.destination))

    def apply_name_matcher_skin_links(self,
            links: tuple[NameMatcherSkinMatrixLink, ...]) -> None:
        from maya import cmds as c

        self._require_transaction()
        if not links:
            raise FitSkeletonValidationError('NameMatcher Skin 没有可转接的关节')
        for link in links:
            skin = link.destination.split('.', 1)[0]
            if (c.referenceQuery(skin, isNodeReferenced=True)
                    or any(c.lockNode(skin, query=True, lock=True) or ())
                    or (c.ls(skin, uuid=True) or [None])[0]
                    != link.skin_uuid
                    or c.connectionInfo(link.destination,
                        sourceFromDestination=True) != link.original_source):
                raise FitSkeletonValidationError(
                    'NameMatcher Skin 在转接前变化或不可写：' + skin)
            self._transaction_changed = True
            c.connectAttr(self.scene_address(link.advanced_joint)
                + '.worldMatrix[0]', link.destination, force=True)
        self.verify_name_matcher_skin_links(links)

    def verify_name_matcher_skin_links(self,
            links: tuple[NameMatcherSkinMatrixLink, ...]) -> None:
        from maya import cmds as c

        for link in links:
            skin, suffix = link.destination.split('.', 1)
            index = suffix[len('matrix['):-1]
            pre = c.getAttr(skin + '.bindPreMatrix[' + index + ']')
            if len(pre) == 1 and isinstance(pre[0], (tuple, list)):
                pre = pre[0]
            actual = c.connectionInfo(link.destination,
                sourceFromDestination=True)
            expected = self.scene_address(link.advanced_joint)
            resolved_actual = c.ls(actual.split('.', 1)[0], long=True) or []
            resolved_expected = c.ls(expected, long=True) or []
            if (not actual.endswith('.worldMatrix[0]')
                    or resolved_actual != resolved_expected
                    or tuple(float(item) for item in pre)
                    != link.bind_pre_matrix
                    or (c.connectionInfo(
                        skin + '.bindPreMatrix[' + index + ']',
                        sourceFromDestination=True) or None)
                    != link.bind_pre_source
                    or (c.ls(skin, uuid=True) or [None])[0]
                    != link.skin_uuid):
                raise RuntimeError(
                    'NameMatcher Skin 影响矩阵转接未保持原绑定：' + skin)

    def capture_name_matcher_advanced_joints(self) -> tuple[str, ...]:
        root = '|Group|DeformationSystem'
        matches = self._cmds.ls(root, long=True, type='transform') or []
        if matches != [root]:
            raise FitSkeletonValidationError(
                'NameMatcher 需要已构建的 DeformationSystem')
        joints = self._cmds.listRelatives(root,
            allDescendents=True, fullPath=True, type='joint') or []
        return tuple(sorted(set(joints)))

    def preflight_name_matcher_constraints(
            self, plan: NameMatcherConstraintPlan) -> None:
        from maya import cmds as c

        for pair in plan.pairs:
            source = self.scene_address(pair.advanced_joint)
            target = pair.external_joint
            if (len(c.ls(source, long=True, type='joint') or ()) != 1
                    or (c.ls(target, long=True, type='joint') or []) != [target]):
                raise FitSkeletonValidationError(
                    'NameMatcher 约束来源或目标已丢失：' + target)
            if (target == source or target.startswith(source + '|')
                    or source.startswith(target + '|')):
                raise FitSkeletonValidationError(
                    'NameMatcher 来源与目标骨架相互嵌套：' + target)
            if (c.referenceQuery(target, isNodeReferenced=True)
                    or any(c.lockNode(target, query=True,
                                      lock=True) or ())):
                raise FitSkeletonValidationError(
                    'NameMatcher 目标关节被引用或节点锁定：' + target)
            for channel in ('translate', 'rotate', 'scale'):
                for axis in 'XYZ':
                    plug = target + '.' + channel + axis
                    if c.connectionInfo(plug,
                            sourceFromDestination=True):
                        raise FitSkeletonValidationError(
                            'NameMatcher 目标已有通道驱动：' + plug)

    def apply_name_matcher_constraints(
            self, plan: NameMatcherConstraintPlan) -> tuple[tuple[str, ...], ...]:
        from maya import cmds as c

        self._require_transaction()
        self.preflight_name_matcher_constraints(plan)
        before_matrices = tuple(tuple(float(value) for value in c.xform(
            pair.external_joint, query=True, worldSpace=True, matrix=True))
            for pair in plan.pairs)
        created = []
        for pair in plan.pairs:
            source = self.scene_address(pair.advanced_joint)
            target = pair.external_joint
            self._transaction_changed = True
            for channel in ('translate', 'rotate', 'scale'):
                for axis in 'XYZ':
                    plug = target + '.' + channel + axis
                    if c.getAttr(plug, lock=True):
                        c.setAttr(plug, lock=False)
            c.transformLimits(target,
                enableTranslationX=(False, False),
                enableTranslationY=(False, False),
                enableTranslationZ=(False, False),
                enableRotationX=(False, False),
                enableRotationY=(False, False),
                enableRotationZ=(False, False),
                enableScaleX=(False, False),
                enableScaleY=(False, False),
                enableScaleZ=(False, False))
            nodes = (
                c.pointConstraint(source, target,
                                  maintainOffset=True)[0],
                c.orientConstraint(source, target,
                                   maintainOffset=True)[0],
                c.scaleConstraint(source, target,
                                  maintainOffset=True)[0],
            )
            created.append(nodes)
        self.verify_name_matcher_constraints(plan, tuple(created))
        for pair, before in zip(plan.pairs, before_matrices):
            after = tuple(float(value) for value in c.xform(
                pair.external_joint, query=True,
                worldSpace=True, matrix=True))
            if len(after) != len(before) or any(
                    abs(left-right) > 1e-4 for left, right in
                    zip(before, after)):
                raise RuntimeError(
                    'NameMatcher 约束没有保持外部骨架原姿态：'
                    + pair.external_joint)
        return tuple(created)

    def verify_name_matcher_constraints(self,
            plan: NameMatcherConstraintPlan,
            created: tuple[tuple[str, ...], ...]) -> None:
        from maya import cmds as c

        if len(created) != len(plan.pairs):
            raise RuntimeError('NameMatcher 约束结果数量不一致')
        for pair, nodes in zip(plan.pairs, created):
            source = (c.ls(self.scene_address(pair.advanced_joint),
                           long=True, type='joint') or [None])[0]
            target = pair.external_joint
            for node, kind, channel in zip(nodes,
                    ('pointConstraint', 'orientConstraint',
                     'scaleConstraint'),
                    ('translate', 'rotate', 'scale')):
                if c.nodeType(node) != kind:
                    raise RuntimeError('NameMatcher 约束节点无效：' + target)
                command = getattr(c, kind)
                targets = command(node, query=True, targetList=True) or []
                resolved = [c.ls(item, long=True) or [] for item in targets]
                if resolved != [[source]]:
                    raise RuntimeError('NameMatcher 约束驱动来源不一致：' + target)
                driven = c.listConnections(target + '.' + channel + 'X',
                    source=True, destination=False, type=kind) or []
                actual_nodes = {item for name in driven
                    for item in (c.ls(name, uuid=True) or ())}
                expected_id = (c.ls(node, uuid=True) or [None])[0]
                if expected_id not in actual_nodes:
                    raise RuntimeError('NameMatcher 目标通道未接线：' + target)
