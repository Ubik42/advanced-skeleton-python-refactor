"""Maya boundary for ADV's separate Game Engine Scaling operation."""
from __future__ import annotations

from adv_py.core.body_game_scaling import (
    AXES, GameScalingJointState, GameScalingNodeState, GameScalingPlan,
)


class MayaBodyGameScalingMixin:
    def _game_scaling_cmds(self):
        return self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds

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
        def incoming(plug: str) -> str | None:
            return c.connectionInfo(plug, sourceFromDestination=True) or None
        rows = []
        for path in self._game_scaling_joint_paths():
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
            fk_name = prefix + "FK" + bare
            fk_constraint = prefix + "FKParentConstraintTo" + bare
            fk_exists = bool(c.objExists(fk_name))
            constraint = (fk_constraint if c.objExists(fk_constraint)
                          else None)
            rows.append(GameScalingJointState(
                path=path, parent=parent,
                segment_scale_compensate=bool(c.getAttr(
                    path + ".segmentScaleCompensate")),
                has_marker=bool(marker),
                scale_sources=tuple(incoming(path + ".scale" + axis)
                                    for axis in AXES),
                stored_sources=tuple(incoming(path + ".GameEngineScalingS"
                                              + axis) if exists else None
                                     for axis, exists in zip(AXES, stored_attrs)),
                stored_attributes=stored_attrs,
                fk_control_exists=fk_exists,
                fk_parent_constraint=constraint,
                fk_parent_scale_sources=(tuple(incoming(
                    constraint + ".scale" + axis) for axis in AXES)
                    if constraint else (None, None, None)),
                fk_parent_compound_scale_source=(incoming(
                    constraint + ".scale") if constraint else None),
            ))
        return tuple(rows)

    def capture_game_scaling_nodes(self) -> tuple[GameScalingNodeState, ...]:
        c = self._game_scaling_cmds()
        pattern = (self.namespace + ":GameEngineScalingSSCMPD*"
                   if self.namespace else "GameEngineScalingSSCMPD*")
        names = c.ls(pattern, type="multiplyDivide") or []
        def incoming(plug: str) -> str | None:
            return c.connectionInfo(plug, sourceFromDestination=True) or None
        return tuple(GameScalingNodeState(
            name=name, node_type=c.nodeType(name),
            operation=int(c.getAttr(name + ".operation")),
            input1_sources=tuple(incoming(name + ".input1" + axis)
                                 for axis in AXES),
            input2_sources=tuple(incoming(name + ".input2" + axis)
                                 for axis in AXES),
            input1_value=tuple(float(value) for value in c.getAttr(
                name + ".input1")[0]),
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
                leaf = path.rsplit("|", 1)[-1]
                namespace, separator, bare = leaf.rpartition(":")
                prefix = namespace + ":" if separator else ""
                if not separator:
                    bare = leaf
                target = prefix + "FKParentConstraintTo" + bare + ".scale"
                if c.isConnected(joint.fk_parent_disconnect_compound, target):
                    c.disconnectAttr(joint.fk_parent_disconnect_compound,
                                     target)
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
                if axis.restore_source:
                    if not c.isConnected(axis.restore_source, scale):
                        c.connectAttr(axis.restore_source, scale, force=True)
        for node in plan.nodes:
            c.createNode("multiplyDivide", name=node.name, skipSelect=True)
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
