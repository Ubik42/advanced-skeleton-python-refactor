"""Maya boundary for ADV's separate Game Engine Scaling operation."""
from __future__ import annotations

from adv_py.core.body_game_scaling import (
    AXES, GameScalingJointState, GameScalingNodeState, GameScalingPlan,
)


class MayaBodyGameScalingMixin:
    def _game_scaling_cmds(self):
        commands = self._cmds
        # Game scaling walks the complete DeformationSystem, including every
        # Spline. Do not canonicalize another system's native node addresses
        # through whichever Spline happens to be audited at this moment.
        from .maya_spline_scope import SplineCommands
        while isinstance(commands, SplineCommands):
            commands = commands.commands
        return getattr(commands, 'raw', commands)

    def _game_scaling_incoming(self, plug):
        source = self._game_scaling_cmds().connectionInfo(plug, sourceFromDestination=True)
        if not source:
            return None
        node, attribute = source.split('.', 1)
        paths = self._game_scaling_cmds().ls(node, long=True) or []
        if len(paths) != 1:
            raise ValueError('Game Engine Scaling 缩放来源缺失或不唯一：' + source)
        return paths[0] + '.' + attribute

    def _game_scaling_joint_paths(self) -> tuple[str, ...]:
        c = self._game_scaling_cmds()
        root_name = (":" + self.namespace + ":DeformationSystem"
                     if self.namespace else "DeformationSystem")
        roots = c.ls(root_name, long=True, type="transform") or []
        if len(roots) != 1:
            raise ValueError("Game Engine Scaling 需要唯一的 DeformationSystem")
        paths = c.listRelatives(roots[0], allDescendents=True,
                                fullPath=True, type="joint") or []
        if not paths:
            raise ValueError("DeformationSystem 下没有 Body 关节")
        return tuple(paths)

    def capture_game_scaling_joints(self) -> tuple[GameScalingJointState, ...]:
        c = self._game_scaling_cmds()
        from .maya_original_control_identity import source_control_from_role, registration
        from .maya_game_scaling_state import original_scale_is_ik
        saved = registration(self)
        # A repeated native enable observes SSC already disabled. Retain the
        # first captured feature policy separately from that current state.
        authored_ssc = {}
        from .maya_game_scaling_state import MARKER
        marker_plug = 'DeformationSystem.' + MARKER
        if self._cmds.objExists(marker_plug):
            from adv_py.core.original_game_scaling_record import decode, map_addresses
            prior, prior_plan = decode(self._cmds.getAttr(marker_plug))
            prior, prior_plan = map_addresses(prior, prior_plan, self.scene_address)
            authored_ssc = {(row.path, row.uuid): (row.authored_segment_scale_compensate
                if row.authored_segment_scale_compensate is not None
                else row.segment_scale_compensate) for row in prior}
        aliases = {}
        if saved is not None:
            for node in saved.nodes:
                if node.node_type != 'transform' or not node.path.rsplit('|', 1)[-1].startswith('AdvPy_GenericFKFollow_'):
                    continue
                role = node.path + '.advPySourceFkFollowerScaleBody'
                body = None
                if self._cmds.objExists(role):
                    sources = self._cmds.listConnections(role, source=True, destination=False) or []
                    if len(sources) != 1:
                        raise ValueError('原版 FK 跟随缩放 Body 身份缺失')
                    body = self.scene_address(self._resolve_connected_node(sources[0]))
                else:
                    # Read already-built Python frames through their native
                    # point/parent target. No new rig or value is fabricated.
                    for kind, query in (('pointConstraint', self._cmds.pointConstraint),
                                        ('parentConstraint', self._cmds.parentConstraint)):
                        drivers = self._cmds.listConnections(node.path + '.translateX', source=True,
                            destination=False, type=kind) or []
                        if len(drivers) != 1:
                            continue
                        targets = query(drivers[0], query=True, targetList=True) or []
                        if len(targets) != 1:
                            continue
                        candidate = self._resolve_connected_node(targets[0])
                        if self._cmds.nodeType(candidate) == 'joint':
                            body = self.scene_address(candidate)
                        elif candidate.rsplit('|', 1)[-1] == 'AdvPy_LegLockConstrained':
                            body = self.scene_address(self._resolve_connected_node('Root_M'))
                        break
                if body:
                    aliases.setdefault(body, []).append(self.scene_address(node.path))
        def incoming(plug: str) -> str | None:
            return self._game_scaling_incoming(plug)
        rows = []
        for path in self._game_scaling_joint_paths():
            identities = c.ls(path, uuid=True) or []
            if len(identities) != 1:
                raise ValueError('Game Engine Scaling 关节身份不唯一：' + path)
            identity = identities[0]
            leaf = path.rsplit("|", 1)[-1]
            namespace, separator, bare = leaf.rpartition(":")
            prefix = namespace + ":" if separator else ""
            if not separator:
                bare = leaf
            parent = (c.listRelatives(path, parent=True, fullPath=True,
                                      type="joint") or [None])[0]
            marker = c.attributeQuery("GameEngineScalingSSC", node=path,
                                      exists=True)
            stored_attrs = tuple(c.attributeQuery(
                "GameEngineScalingS" + axis, node=path, exists=True)
                for axis in AXES)
            # Native searches FK<joint>, never the deform joint itself.
            fk_name = self.scene_address(source_control_from_role(self, 'FK' + bare))
            fk_constraint_name = prefix + "FKParentConstraintTo" + bare
            fk_constraint = None
            if c.objExists(fk_constraint_name):
                matches = c.ls(fk_constraint_name, long=True) or []
                if len(matches) != 1:
                    raise ValueError('原版 FK 跟随缩放角色不唯一：' + fk_constraint_name)
                fk_constraint = matches[0]
            fk_exists = bool(c.objExists(fk_name))
            followers = tuple(dict.fromkeys((([fk_constraint] if fk_constraint else [])
                                            + aliases.get(path, []))))
            constraint = followers[0] if followers else None
            extra = followers[1:]
            scales = tuple(incoming(path + '.scale' + axis) for axis in AXES)
            stored = tuple(incoming(path + '.GameEngineScalingS' + axis) if exists else None
                           for axis, exists in zip(AXES, stored_attrs))
            rows.append(GameScalingJointState(
                path=path, parent=parent,
                segment_scale_compensate=bool(c.getAttr(
                    path + ".segmentScaleCompensate")),
                has_marker=bool(marker),
                scale_sources=scales,
                stored_sources=stored,
                stored_attributes=stored_attrs,
                fk_control_exists=fk_exists,
                fk_parent_constraint=constraint,
                fk_parent_scale_sources=(tuple(incoming(
                    constraint + ".scale" + axis) for axis in AXES)
                    if constraint else (None, None, None)),
                fk_parent_compound_scale_source=(incoming(
                    constraint + ".scale") if constraint else None),
                scale_source_ik_roles=tuple(original_scale_is_ik(self, path,
                    stored[index] if stored_attrs[index] else scales[index], saved)
                    for index in range(3)),
                fk_parent_extra_constraints=extra,
                fk_parent_extra_scale_sources=tuple(tuple(incoming(target + '.scale' + axis)
                    for axis in AXES) for target in extra),
                fk_parent_extra_compound_sources=tuple(incoming(target + '.scale') for target in extra),
                authored_segment_scale_compensate=authored_ssc.get((path, identity)),
                uuid=identity,
                stored_values=tuple(float(c.getAttr(path + '.GameEngineScalingS' + axis))
                                    if present else 0. for axis, present in zip(AXES, stored_attrs)),
            ))
        return tuple(rows)

    def capture_game_scaling_nodes(self) -> tuple[GameScalingNodeState, ...]:
        c = self._game_scaling_cmds()
        pattern = (self.namespace + ":GameEngineScalingSSCMPD*"
                   if self.namespace else "GameEngineScalingSSCMPD*")
        names = c.ls(pattern, type="multiplyDivide") or []
        def incoming(plug: str) -> str | None:
            return self._game_scaling_incoming(plug)
        return tuple(GameScalingNodeState(
            name=name, node_type=c.nodeType(name),
            operation=int(c.getAttr(name + ".operation")),
            input1_sources=tuple(incoming(name + ".input1" + axis)
                                 for axis in AXES),
            input2_sources=tuple(incoming(name + ".input2" + axis)
                                 for axis in AXES),
            input1_value=tuple(float(value) for value in c.getAttr(
                name + ".input1")[0]),
            input2_value=tuple(float(value) for value in c.getAttr(
                name + ".input2")[0]),
        ) for name in names)

    def preflight_game_scaling(self, plan: GameScalingPlan) -> None:
        c = self._game_scaling_cmds()
        actual = set(self._game_scaling_joint_paths())
        planned = {joint.path for joint in plan.joints}
        if actual != planned or len(planned) != len(plan.joints):
            raise ValueError("Game Engine Scaling 的关节层级已变化")
        removable = set(c.ls(
            (self.namespace + ":GameEngineScalingSSCMPD*"
             if self.namespace else "GameEngineScalingSSCMPD*"),
            type="multiplyDivide") or [])
        for node in plan.nodes:
            if c.objExists(node.name) and node.name not in removable:
                raise ValueError("补偿节点名称已被占用：" + node.name)
        for joint in plan.joints:
            if c.referenceQuery(joint.path, isNodeReferenced=True):
                raise ValueError("引用关节不能修改缩放：" + joint.path)
            if c.getAttr(joint.path + ".segmentScaleCompensate", lock=True):
                raise ValueError("segmentScaleCompensate 已锁定：" + joint.path)
            for axis in joint.axes:
                scale = joint.path + ".scale" + axis.axis
                if c.getAttr(scale, lock=True):
                    raise ValueError("关节缩放已锁定：" + scale)
                stored = joint.path + ".GameEngineScalingS" + axis.axis
                if (c.objExists(stored) and c.getAttr(stored, lock=True)):
                    raise ValueError("保存的缩放驱动已锁定：" + stored)

    def apply_game_scaling(self, plan: GameScalingPlan) -> None:
        self._require_transaction()
        c = self._game_scaling_cmds()
        from .maya_game_registration import source_registration, refresh_hierarchy, scene_ids, remember_generated_nodes
        from .maya_game_scaling_state import save
        before = self.capture_game_scaling_joints()
        registration = source_registration(self)
        ids_before = scene_ids(self)
        self._transaction_changed = True
        if plan.remove_old_compensation_nodes:
            pattern = (self.namespace + ":GameEngineScalingSSCMPD*"
                       if self.namespace else "GameEngineScalingSSCMPD*")
            existing = c.ls(pattern, type="multiplyDivide") or []
            if existing:
                c.delete(existing)
        for joint in plan.joints:
            path = joint.path
            if joint.marker_required and not c.attributeQuery(
                    "GameEngineScalingSSC", node=path, exists=True):
                c.addAttr(path, longName="GameEngineScalingSSC",
                          attributeType="bool", defaultValue=True,
                          keyable=False)
            c.setAttr(path + ".segmentScaleCompensate",
                      joint.segment_scale_compensate)
            if joint.fk_parent_disconnect_compound:
                target = next(axis.fk_parent_scale_target for axis in joint.axes
                              if axis.fk_parent_scale_target).rsplit('.', 1)[0] + '.scale'
                if c.isConnected(joint.fk_parent_disconnect_compound, target):
                    c.disconnectAttr(joint.fk_parent_disconnect_compound,
                                     target)
            for source, target in joint.fk_parent_extra_disconnect_compounds:
                if c.isConnected(source, target):
                    c.disconnectAttr(source, target)
            for axis in joint.axes:
                scale = path + ".scale" + axis.axis
                stored = path + ".GameEngineScalingS" + axis.axis
                if axis.create_stored_attribute:
                    c.addAttr(path, longName="GameEngineScalingS" + axis.axis,
                              attributeType="double", keyable=False)
                if axis.reroute_source:
                    if not c.isConnected(axis.reroute_source, stored):
                        c.connectAttr(axis.reroute_source, stored, force=True)
                if axis.disconnect_scale_source:
                    if c.isConnected(axis.disconnect_scale_source, scale):
                        c.disconnectAttr(axis.disconnect_scale_source, scale)
                    c.setAttr(scale, 1.0)
                if axis.fk_parent_scale_target:
                    if not c.isConnected(stored, axis.fk_parent_scale_target):
                        c.connectAttr(stored, axis.fk_parent_scale_target,
                                      force=True)
                for target in axis.fk_parent_extra_scale_targets:
                    if not c.isConnected(stored, target):
                        c.connectAttr(stored, target, force=True)
                if axis.restore_source:
                    if not c.isConnected(axis.restore_source, scale):
                        c.connectAttr(axis.restore_source, scale, force=True)
        for node in plan.nodes:
            name = self._cmds.identity.to_local(node.name) if hasattr(self._cmds, 'identity') else node.name
            self._cmds.createNode("multiplyDivide", name=name, skipSelect=True)
            c.setAttr(node.name + ".operation", node.operation)
            if node.input1_constant is not None:
                c.setAttr(node.name + ".input1", *node.input1_constant)
            for axis, source in zip(AXES, node.input1_sources):
                if source:
                    c.connectAttr(source, node.name + ".input1" + axis)
            for axis, source in zip(AXES, node.input2_sources):
                if source:
                    c.connectAttr(source, node.name + ".input2" + axis)
        if plan.enable:
            for joint in plan.joints:
                if joint.compensation_node is None:
                    continue
                for axis in joint.axes:
                    if axis.compensation_source:
                        c.connectAttr(joint.compensation_node + ".output"
                                      + axis.axis,
                                      joint.path + ".scale" + axis.axis,
                                      force=True)
        save(self, before, plan)
        refresh_hierarchy(self, registration)
        remember_generated_nodes(self, ids_before)
        c.select(clear=True)
