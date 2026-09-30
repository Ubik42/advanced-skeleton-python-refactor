"""Native Maya boundary for NameMatcher's AutoRigConstraint pass."""
from __future__ import annotations

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.name_matcher_fit import (
    NameMatcherConstraintPlan, NameMatcherSkinMatrixLink,
    NameMatcherSourceHandoffPlan, plan_name_matcher_source_handoff)
from adv_py.core.name_matcher_mocap import NameMatcherMocapPlan
from adv_py.core.name_matcher_mocap_session import (
    NameMatcherMocapConstraint, NameMatcherMocapSession)

from .maya_source_skeleton_fit import MayaSourceSkeletonFitHost


class MayaNameMatcherHost(MayaSourceSkeletonFitHost):
    def preflight_name_matcher_zero_out(
            self, plan: NameMatcherConstraintPlan) -> None:
        from maya import cmds as c

        for pair in plan.pairs:
            joint = pair.external_joint
            if (c.ls(joint, long=True, type='joint') or []) != [joint]:
                raise FitSkeletonValidationError(
                    'NameMatcher Zero Out 来源关节丢失：' + joint)
            if (c.referenceQuery(joint, isNodeReferenced=True)
                    or any(c.lockNode(joint, query=True,
                                      lock=True) or ())):
                raise FitSkeletonValidationError(
                    'NameMatcher Zero Out 来源关节不可编辑：' + joint)
            for axis in 'XYZ':
                plug = joint + '.rotate' + axis
                if not c.getAttr(plug, settable=True):
                    raise FitSkeletonValidationError(
                        'NameMatcher Zero Out 旋转通道不可写：' + plug)

    def zero_out_name_matcher_joints(
            self, plan: NameMatcherConstraintPlan) -> None:
        from maya import cmds as c

        self._require_transaction()
        self.preflight_name_matcher_zero_out(plan)
        for pair in plan.pairs:
            self._transaction_changed = True
            c.setAttr(pair.external_joint + '.rotate', 0, 0, 0,
                      type='double3')
        for pair in plan.pairs:
            if any(abs(float(c.getAttr(
                    pair.external_joint + '.rotate' + axis))) > 1e-7
                    for axis in 'XYZ'):
                raise RuntimeError(
                    'NameMatcher Zero Out 来源旋转未归零：'
                    + pair.external_joint)

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
        if (plan.spine_control and any(link.control == plan.spine_control
                for link in plan.links)):
            spine = self.scene_address(plan.spine_control)
            for attribute in ('followRoot', 'ikHybridVis'):
                if (c.attributeQuery(attribute, node=spine, exists=True)
                        and not c.getAttr(spine + '.' + attribute,
                                          settable=True)):
                    raise FitSkeletonValidationError(
                        'NameMatcher 脊柱动捕属性不可写：'
                        + spine + '.' + attribute)
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
        c.addAttr(group, longName='advPyNameMatcher',
                  attributeType='bool', defaultValue=True)
        c.setAttr(group + '.advPyNameMatcher', lock=True)
        c.addAttr(group, longName='disableConstraints',
                  attributeType='bool', keyable=True)
        if (plan.spine_control and any(link.control == plan.spine_control
                for link in plan.links)):
            spine = self.scene_address(plan.spine_control)
            for attribute in ('followRoot', 'ikHybridVis'):
                if c.attributeQuery(attribute, node=spine, exists=True):
                    c.setAttr(spine + '.' + attribute, 0)
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

    def capture_name_matcher_mocap_session(self) -> NameMatcherMocapSession:
        """Resolve only this tool's output constraints, never arbitrary rig nodes."""
        from maya import cmds as c

        group = self.scene_address('MoCapConstraints')
        if (not c.objExists(group)
                or not c.attributeQuery('advPyNameMatcher',
                                        node=group, exists=True)
                or not c.getAttr(group + '.advPyNameMatcher')
                or not c.attributeQuery('disableConstraints',
                                        node=group, exists=True)):
            raise FitSkeletonValidationError(
                'NameMatcher 动捕会话不存在或不是本工具创建')
        group_ids = c.ls(group, uuid=True) or []
        if len(group_ids) != 1:
            raise FitSkeletonValidationError('NameMatcher 动捕会话身份不唯一')
        output = group + '.disableConstraints'
        nodes = c.listConnections(output, source=False,
                                  destination=True) or []
        constraints = []
        for name in sorted(set(nodes)):
            matches = c.ls(name, long=True) or []
            if len(matches) != 1:
                raise FitSkeletonValidationError(
                    'NameMatcher 动捕约束名称不唯一：' + name)
            node = matches[0]
            kind = c.nodeType(node)
            if (kind not in ('pointConstraint', 'orientConstraint')
                    or c.connectionInfo(node + '.nodeState',
                        sourceFromDestination=True) != output):
                raise FitSkeletonValidationError(
                    'NameMatcher 动捕禁用连接被其他节点占用：' + node)
            parents = c.listConnections(
                node + '.constraintParentInverseMatrix',
                source=True, destination=False, plugs=True) or []
            if len(parents) != 1:
                raise FitSkeletonValidationError(
                    'NameMatcher 动捕约束没有唯一控制器：' + node)
            control = parents[0].split('.', 1)[0]
            controls = c.ls(control, long=True, type='transform') or []
            node_ids = c.ls(node, uuid=True) or []
            control_ids = c.ls(control, uuid=True) or []
            if (len(controls) != 1 or len(node_ids) != 1
                    or len(control_ids) != 1):
                raise FitSkeletonValidationError(
                    'NameMatcher 动捕控制器身份不唯一：' + control)
            constraints.append(NameMatcherMocapConstraint(
                node, node_ids[0], controls[0], control_ids[0], kind))
        if not constraints:
            raise FitSkeletonValidationError('NameMatcher 动捕没有输出约束')
        return NameMatcherMocapSession(group, group_ids[0],
                                      tuple(constraints))

    def bake_name_matcher_mocap(self,
            session: NameMatcherMocapSession) -> tuple[float, float]:
        from maya import cmds as c

        self._require_transaction()
        if self.capture_name_matcher_mocap_session() != session:
            raise FitSkeletonValidationError(
                'NameMatcher 动捕约束在烘焙前变化')
        if c.getAttr(session.group + '.disableConstraints'):
            raise FitSkeletonValidationError(
                'NameMatcher 动捕约束已禁用，不能烘焙')
        first = float(c.playbackOptions(query=True, minTime=True))
        last = float(c.playbackOptions(query=True, maxTime=True))
        if first > last:
            raise FitSkeletonValidationError('NameMatcher 播放范围无效')
        previous_selection = c.ls(selection=True, long=True) or []
        previous_time = c.currentTime(query=True)
        previous_auto_key = bool(c.autoKeyframe(query=True, state=True))
        controls = session.controls
        try:
            self._transaction_changed = True
            c.autoKeyframe(state=False)
            c.bakeResults(controls, simulation=True,
                time=(first, last), sampleBy=1,
                disableImplicitControl=True, preserveOutsideKeys=False,
                sparseAnimCurveBake=False,
                removeBakedAttributeFromLayer=False,
                bakeOnOverrideLayer=False, controlPoints=False,
                shape=False)
            if not any((c.keyframe(control, query=True,
                    keyframeCount=True, time=(first, last)) or 0) > 0
                    for control in controls):
                raise RuntimeError('NameMatcher 动捕烘焙未生成控制器关键帧')
            c.delete(controls, staticChannels=True,
                     unitlessAnimationCurves=False, hierarchy='none',
                     controlPoints=False, shape=True)
        finally:
            c.currentTime(previous_time)
            c.autoKeyframe(state=previous_auto_key)
            if previous_selection:
                c.select([node for node in previous_selection
                          if c.objExists(node)], replace=True)
            else:
                c.select(clear=True)
        if self.capture_name_matcher_mocap_session() != session:
            raise RuntimeError('NameMatcher 烘焙改变了动捕约束身份')
        return first, last

    def disconnect_name_matcher_mocap(self,
            session: NameMatcherMocapSession) -> None:
        from maya import cmds as c

        self._require_transaction()
        if self.capture_name_matcher_mocap_session() != session:
            raise FitSkeletonValidationError(
                'NameMatcher 动捕约束在断开前变化')
        descendants = c.listRelatives(session.group,
            allDescendents=True, fullPath=True) or []
        if any(c.nodeType(node) not in ('transform', 'pointConstraint',
                                       'orientConstraint', 'aimConstraint')
               or (c.nodeType(node) == 'transform'
                   and not node.rsplit('|', 1)[-1].startswith(
                       'AdvPy_MoCapPole'))
               for node in descendants):
            raise FitSkeletonValidationError(
                'NameMatcher 动捕组包含非本工具节点，拒绝删除')
        self._transaction_changed = True
        c.delete(tuple(item.node for item in session.constraints))
        c.delete(session.group)
        if (c.objExists(session.group)
                or any(c.ls(item.uuid) for item in session.constraints)):
            raise RuntimeError('NameMatcher 动捕约束未全部断开')

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
                body_inverse = c.getAttr(self.scene_address(
                    pair.advanced_joint) + '.worldInverseMatrix[0]')
                if (len(body_inverse) == 1
                        and isinstance(body_inverse[0], (tuple, list))):
                    body_inverse = body_inverse[0]
                body_inverse = tuple(float(item) for item in body_inverse)
                if len(body_inverse) != 16:
                    raise FitSkeletonValidationError(
                        'NameMatcher Body 绑定逆矩阵不完整：'
                        + pair.advanced_joint)
                skin_ids = c.ls(skin, uuid=True) or []
                if len(skin_ids) != 1:
                    raise FitSkeletonValidationError(
                        'NameMatcher Skin 节点不唯一：' + skin)
                links.append(NameMatcherSkinMatrixLink(
                    pair.advanced_joint, pair.external_joint,
                    destination, source, matrix, body_inverse,
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

    def capture_name_matcher_source_handoff(self, source,
            mapping: NameMatcherConstraintPlan,
            links: tuple[NameMatcherSkinMatrixLink, ...]
            ) -> NameMatcherSourceHandoffPlan:
        from maya import cmds as c

        source_paths = {joint.path for joint in source}
        mapped = {pair.external_joint for pair in mapping.pairs}
        def canonical(plug):
            node, attribute = plug.split('.', 1)
            resolved = c.ls(node, long=True) or []
            return (resolved[0] if len(resolved) == 1 else node) + '.' + attribute
        transferred = {(canonical(link.original_source),
                        canonical(link.destination))
                       for link in links}
        for link in links:
            if link.bind_pre_source:
                transferred.add((canonical(link.bind_pre_source),
                    canonical(link.destination.replace('.matrix[',
                                             '.bindPreMatrix['))))
        observed_live = []
        geometry_roots = []
        for joint in source:
            path = joint.path
            if (c.referenceQuery(path, isNodeReferenced=True)
                    or any(c.lockNode(path, query=True,
                                      lock=True) or ())):
                raise FitSkeletonValidationError(
                    'NameMatcher 来源关节不可迁移或删除：' + path)
            children = c.listRelatives(path, children=True,
                                       fullPath=True) or []
            for child in children:
                if c.nodeType(child) == 'transform':
                    shapes = c.listRelatives(child,
                        allDescendents=True, fullPath=True,
                        type='mesh') or []
                    if any(candidate.startswith(child + '|')
                           for candidate in source_paths):
                        if shapes:
                            raise FitSkeletonValidationError(
                                'NameMatcher 来源骨架中间变换同时含模型和关节：'
                                + child)
                        continue
                    if not shapes:
                        raise FitSkeletonValidationError(
                            'NameMatcher 来源骨架挂有非模型层级，'
                            '不能随骨架删除：' + child)
                    geometry_roots.append(child)
                elif c.nodeType(child) not in ('joint',):
                    # A joint's own shape is normal; external mesh shapes
                    # directly below a joint cannot be moved as a DAG root.
                    if c.nodeType(child) == 'mesh':
                        raise FitSkeletonValidationError(
                            'NameMatcher 来源网格 shape 直接挂在关节下：'
                            + child)
            destinations = []
            for attribute in ('worldMatrix[0]', 'worldInverseMatrix[0]',
                    *(kind + axis for kind in ('translate', 'rotate', 'scale')
                      for axis in 'XYZ')):
                plug = path + '.' + attribute
                destinations.extend((canonical(plug), canonical(destination))
                    for destination in (c.listConnections(plug,
                        source=False, destination=True, plugs=True) or []))
            external = tuple((plug, destination)
                for plug, destination in destinations
                if (c.ls(destination.split('.', 1)[0], long=True) or [None])[0]
                   not in source_paths)
            if path in mapped:
                unexpected = [(plug, destination)
                    for plug, destination in external
                    if (plug, destination) not in transferred]
                if unexpected:
                    raise FitSkeletonValidationError(
                        'NameMatcher 已映射关节仍驱动来源外部节点：'
                        + path + ' → ' + unexpected[0][1])
            elif external:
                observed_live.append(path)
        for transform in geometry_roots:
            if (c.referenceQuery(transform, isNodeReferenced=True)
                    or any(c.lockNode(transform, query=True,
                                      lock=True) or ())):
                raise FitSkeletonValidationError(
                    'NameMatcher 来源模型层级不可迁移：' + transform)
        return plan_name_matcher_source_handoff(
            tuple((joint.path, joint.parent) for joint in source),
            mapping, tuple(observed_live), tuple(geometry_roots))

    def capture_name_matcher_skin_payload(self,
            links: tuple[NameMatcherSkinMatrixLink, ...]) -> tuple:
        """The matrix source and bind pre may change; weights may not."""
        from maya import cmds as c

        rows = []
        for skin in sorted({link.destination.split('.', 1)[0]
                            for link in links}):
            geometries = tuple(sorted((c.ls(shape, uuid=True) or [None])[0]
                for shape in (c.skinCluster(skin, query=True,
                                             geometry=True) or [])))
            settings = tuple((attribute, c.getAttr(skin + '.' + attribute))
                for attribute in ('envelope', 'skinningMethod',
                    'normalizeWeights', 'maxInfluences',
                    'maintainMaxInfluences', 'weightDistribution',
                    'bindMethod', 'useComponents')
                if c.objExists(skin + '.' + attribute))
            weights = []
            for vertex in c.getAttr(skin + '.weightList',
                                    multiIndices=True) or []:
                plug = skin + '.weightList[' + str(vertex) + '].weights'
                weights.append((vertex, tuple((index,
                    float(c.getAttr(plug + '[' + str(index) + ']')))
                    for index in (c.getAttr(plug,
                        multiIndices=True) or []))))
            blend = tuple((index, float(c.getAttr(skin
                + '.blendWeights[' + str(index) + ']')))
                for index in (c.getAttr(skin + '.blendWeights',
                                        multiIndices=True) or []))
            rows.append(((c.ls(skin, uuid=True) or [None])[0],
                         geometries, settings, tuple(weights), blend))
        return tuple(rows)

    def normalize_name_matcher_skins(
            self, links: tuple[NameMatcherSkinMatrixLink, ...]) -> None:
        """Mirror MEL's final skinPercent normalization on affected meshes."""
        from maya import cmds as c

        self._require_transaction()
        self._transaction_changed = True
        for skin in sorted({link.destination.split('.', 1)[0]
                            for link in links}):
            for mesh in c.skinCluster(skin, query=True, geometry=True) or []:
                c.skinPercent(skin, mesh, normalize=True)

    def verify_name_matcher_skin_payload(self, before: tuple,
            after: tuple) -> None:
        """Allow MEL's normalization, but keep each vertex's weight ratios."""
        if len(before) != len(after):
            raise RuntimeError('NameMatcher Skin 数量变化')
        for old, new in zip(before, after):
            old_id, old_geo, old_settings, old_weights, old_blend = old
            new_id, new_geo, new_settings, new_weights, new_blend = new
            if ((old_id, old_geo, old_settings, old_blend)
                    != (new_id, new_geo, new_settings, new_blend)):
                raise RuntimeError(
                    'NameMatcher Skin 几何、参数或 Blend Weight 变化')
            normalize_mode = dict(old_settings).get('normalizeWeights', 0)
            old_by_vertex = dict(old_weights)
            new_by_vertex = dict(new_weights)
            for vertex in set(old_by_vertex) | set(new_by_vertex):
                original = dict(old_by_vertex.get(vertex, ()))
                changed = dict(new_by_vertex.get(vertex, ()))
                total_before = sum(original.values())
                total_after = sum(changed.values())
                if total_before <= 1e-12:
                    if total_after > 1e-8:
                        raise RuntimeError(
                            'NameMatcher Skin 零权重顶点被改写')
                    continue
                expected_total = 1.0 if normalize_mode else total_before
                if abs(total_after - expected_total) > 1e-5:
                    raise RuntimeError(
                        'NameMatcher Skin 顶点权重总量不符')
                for index in set(original) | set(changed):
                    fraction_before = original.get(index, 0.0) / total_before
                    fraction_after = changed.get(index, 0.0) / total_after
                    if abs(fraction_before-fraction_after) > 1e-5:
                        raise RuntimeError(
                            'NameMatcher Skin 顶点影响比例被改写')

    def apply_name_matcher_source_handoff(self,
            handoff: NameMatcherSourceHandoffPlan) -> tuple[int, int]:
        from maya import cmds as c

        self._require_transaction()
        geometry = self.scene_address('|Group|Geometry')
        if not c.objExists(geometry):
            raise FitSkeletonValidationError(
                'NameMatcher 缺少可接收原模型的 Geometry 容器')
        move_paths = (tuple(path for path, _ in handoff.retained_branches)
                      + handoff.preserved_transforms)
        ids = {}
        matrices = {}
        for path in move_paths:
            if (c.ls(path, long=True) or []) != [path]:
                raise FitSkeletonValidationError(
                    'NameMatcher 来源保留节点不唯一：' + path)
            uuids = c.ls(path, uuid=True) or []
            if len(uuids) != 1:
                raise FitSkeletonValidationError(
                    'NameMatcher 来源保留节点身份不唯一：' + path)
            ids[path] = uuids[0]
            matrices[path] = tuple(float(value) for value in c.xform(
                path, query=True, worldSpace=True, matrix=True))
        root_ids = c.ls(handoff.source_root, uuid=True) or []
        if len(root_ids) != 1:
            raise FitSkeletonValidationError('NameMatcher 来源根身份不唯一')
        self._transaction_changed = True
        for path in handoff.preserved_transforms:
            c.parent(path, geometry, absolute=True)
        for path, advanced in handoff.retained_branches:
            resolved = c.ls(ids[path], long=True) or []
            if len(resolved) != 1:
                raise RuntimeError('NameMatcher 未映射关节迁移前丢失：' + path)
            c.parent(resolved[0], self.scene_address(advanced),
                     absolute=True)
        for path, uuid in ids.items():
            resolved = c.ls(uuid, long=True) or []
            if (len(resolved) != 1
                    or any(abs(float(actual)-expected) > 1e-4
                           for actual, expected in zip(c.xform(resolved[0],
                               query=True, worldSpace=True, matrix=True),
                               matrices[path]))):
                raise RuntimeError(
                    'NameMatcher 来源保留节点世界矩阵变化：' + path)
        c.delete(handoff.source_root)
        if c.ls(root_ids[0]):
            raise RuntimeError('NameMatcher 已映射来源骨架未移除')
        for path, uuid in ids.items():
            if len(c.ls(uuid, long=True) or []) != 1:
                raise RuntimeError(
                    'NameMatcher 来源保留节点在清理后丢失：' + path)
        return len(handoff.retained_branches), len(handoff.preserved_transforms)

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
            index = link.destination.split('matrix[', 1)[1][:-1]
            bind_pre = skin + '.bindPreMatrix[' + index + ']'
            if ((c.connectionInfo(bind_pre,
                    sourceFromDestination=True) or None)
                    != link.bind_pre_source):
                raise FitSkeletonValidationError(
                    'NameMatcher Skin 绑定逆矩阵来源变化：' + bind_pre)
            if (link.bind_pre_source is not None
                    and (not link.bind_pre_source.endswith(
                        '.worldInverseMatrix[0]')
                    or (c.ls(link.bind_pre_source.split('.', 1)[0],
                             long=True) or []) != [link.external_joint])):
                raise FitSkeletonValidationError(
                    'NameMatcher Skin 绑定逆矩阵存在不支持的外部驱动：'
                    + bind_pre)
            if c.getAttr(bind_pre, lock=True):
                raise FitSkeletonValidationError(
                    'NameMatcher Skin 绑定逆矩阵被锁定：'
                    + bind_pre)
            self._transaction_changed = True
            body = self.scene_address(link.advanced_joint)
            c.connectAttr(body + '.worldMatrix[0]',
                          link.destination, force=True)
            if link.bind_pre_source:
                c.connectAttr(body + '.worldInverseMatrix[0]',
                              bind_pre, force=True)
            else:
                c.setAttr(bind_pre, *link.target_bind_pre_matrix,
                          type='matrix')
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
            pre_source = c.connectionInfo(
                skin + '.bindPreMatrix[' + index + ']',
                sourceFromDestination=True) or None
            pre_source_correct = (pre_source is None
                if link.bind_pre_source is None else
                bool(pre_source and pre_source.endswith(
                    '.worldInverseMatrix[0]')
                    and (c.ls(pre_source.split('.', 1)[0],
                              long=True) or []) == resolved_expected))
            if (not actual.endswith('.worldMatrix[0]')
                    or resolved_actual != resolved_expected
                    or len(pre) != 16
                    or any(abs(float(actual_value)-expected_value) > 1e-8
                           for actual_value, expected_value in zip(
                               pre, link.target_bind_pre_matrix))
                    or not pre_source_correct
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
