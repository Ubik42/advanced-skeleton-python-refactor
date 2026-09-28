"""Pure connection plan for ADV 6.925's separate Game Engine Scaling tool.

The Preparation gameEngine checkbox does not invoke this command. Enabling
reroutes existing joint-scale drivers through GameEngineScalingS* channels,
then supplies direct scale from multiplyDivide nodes. Disabling restores
the original scale drivers and segmentScaleCompensate.
"""
from __future__ import annotations

from dataclasses import dataclass


AXES = ("X", "Y", "Z")


@dataclass(frozen=True, slots=True)
class GameScalingJointState:
    path: str
    parent: str | None
    segment_scale_compensate: bool
    has_marker: bool
    scale_sources: tuple[str | None, str | None, str | None]
    stored_sources: tuple[str | None, str | None, str | None]
    stored_attributes: tuple[bool, bool, bool] = (False, False, False)
    fk_control_exists: bool = False
    fk_parent_constraint: str | None = None
    fk_parent_scale_sources: tuple[str | None, str | None, str | None] = (
        None, None, None)
    fk_parent_compound_scale_source: str | None = None

    @property
    def leaf(self) -> str:
        return self.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    @property
    def is_part(self) -> bool:
        stem = self.leaf.rsplit("_", 1)[0]
        marker = stem.rfind("Part")
        return marker >= 0 and marker + 4 < len(stem) and stem[marker + 4].isdigit()


@dataclass(frozen=True, slots=True)
class GameScalingAxisPlan:
    axis: str
    scale_source: str | None
    stored_source: str | None
    create_stored_attribute: bool
    reroute_source: str | None
    disconnect_scale_source: str | None
    restore_source: str | None
    compensation_source: str | None
    parent_inverse_source: str | None
    fk_parent_scale_target: str | None


@dataclass(frozen=True, slots=True)
class GameScalingJointPlan:
    path: str
    marker_required: bool
    segment_scale_compensate: bool
    axes: tuple[GameScalingAxisPlan, ...]
    compensation_node: str | None
    parent_inverse_node: str | None
    fk_parent_disconnect_compound: str | None


@dataclass(frozen=True, slots=True)
class GameScalingNodeSpec:
    name: str
    operation: int
    input1_sources: tuple[str | None, str | None, str | None]
    input2_sources: tuple[str | None, str | None, str | None]
    input1_constant: tuple[float, float, float] | None = None


@dataclass(frozen=True, slots=True)
class GameScalingNodeState:
    name: str
    node_type: str
    operation: int
    input1_sources: tuple[str | None, str | None, str | None]
    input2_sources: tuple[str | None, str | None, str | None]
    input1_value: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class GameScalingPlan:
    enable: bool
    joints: tuple[GameScalingJointPlan, ...]
    nodes: tuple[GameScalingNodeSpec, ...]
    # Original MEL deletes every prior GameEngineScalingSSCMPD* node first.
    remove_old_compensation_nodes: bool = True


def audit_body_game_scaling(
    plan: GameScalingPlan,
    before: tuple[GameScalingJointState, ...],
    after: tuple[GameScalingJointState, ...],
) -> tuple[str, ...]:
    before_by_path = {item.path: item for item in before}
    after_by_path = {item.path: item for item in after}
    expected = {item.path for item in plan.joints}
    if (set(before_by_path) != expected or set(after_by_path) != expected
            or len(before_by_path) != len(before)
            or len(after_by_path) != len(after)):
        return ("Game Engine Scaling 关节集合变化",)
    issues = []
    for joint in plan.joints:
        prior = before_by_path[joint.path]
        actual = after_by_path[joint.path]
        if actual.has_marker != joint.marker_required:
            issues.append(joint.path + " 标记不符")
        if actual.segment_scale_compensate != joint.segment_scale_compensate:
            issues.append(joint.path + " segmentScaleCompensate 不符")
        for index, axis_plan in enumerate(joint.axes):
            wanted_stored = (axis_plan.reroute_source
                             or prior.stored_sources[index])
            wanted_attribute = (prior.stored_attributes[index]
                                or axis_plan.create_stored_attribute)
            if actual.stored_attributes[index] != wanted_attribute:
                issues.append(joint.path + " GameEngineScalingS"
                              + axis_plan.axis + " 属性不符")
            if actual.stored_sources[index] != wanted_stored:
                issues.append(joint.path + " GameEngineScalingS"
                              + axis_plan.axis + " 驱动不符")
            if plan.enable and joint.compensation_node is not None:
                wanted_scale = (joint.compensation_node + ".output"
                                + axis_plan.axis
                                if axis_plan.compensation_source else None)
            elif plan.enable and axis_plan.disconnect_scale_source is not None:
                wanted_scale = None
            elif axis_plan.restore_source is not None:
                wanted_scale = axis_plan.restore_source
            elif (not plan.enable and prior.scale_sources[index] is not None
                  and prior.scale_sources[index].rsplit("|", 1)[-1]
                  .rsplit(":", 1)[-1].startswith(
                      "GameEngineScalingSSCMPD")):
                wanted_scale = None
            else:
                wanted_scale = prior.scale_sources[index]
            if actual.scale_sources[index] != wanted_scale:
                issues.append(joint.path + ".scale" + axis_plan.axis
                              + " 驱动不符")
            if axis_plan.fk_parent_scale_target is not None:
                wanted_fk_source = (joint.path + ".GameEngineScalingS"
                                    + axis_plan.axis)
                if actual.fk_parent_scale_sources[index] != wanted_fk_source:
                    issues.append(joint.path + " FK 父约束缩放来源不符："
                                  + axis_plan.axis)
        if (joint.fk_parent_disconnect_compound is not None
                and actual.fk_parent_compound_scale_source is not None):
            issues.append(joint.path + " FK 父约束仍连接关节复合缩放")
    return tuple(issues)


def audit_body_game_scaling_nodes(
    plan: GameScalingPlan,
    actual: tuple[GameScalingNodeState, ...],
) -> tuple[str, ...]:
    expected = {node.name: node for node in plan.nodes}
    by_name = {node.name: node for node in actual}
    if (len(expected) != len(plan.nodes) or len(by_name) != len(actual)
            or set(expected) != set(by_name)):
        return ("Game Engine Scaling 补偿节点集合不符",)
    issues = []
    for name, spec in expected.items():
        state = by_name[name]
        if (state.node_type != "multiplyDivide"
                or state.operation != spec.operation
                or state.input1_sources != spec.input1_sources
                or state.input2_sources != spec.input2_sources
                or (spec.input1_constant is not None
                    and state.input1_value != spec.input1_constant)):
            issues.append(name + " 运算或连接不符")
    return tuple(issues)


def _nearest_fk_ancestor(
    state: GameScalingJointState,
    by_path: dict[str, GameScalingJointState],
) -> GameScalingJointState | None:
    # MEL tokenizes the parent joint's full path, then starts at size-2:
    # the parent joint itself is skipped before searching for an FK control.
    parent = state.parent.rsplit("|", 1)[0] if state.parent else ""
    while parent:
        candidate = by_path.get(parent)
        parent = parent.rsplit("|", 1)[0]
        if candidate is None:
            continue
        if not candidate.is_part and candidate.fk_control_exists:
            return candidate
    return None


def plan_body_game_scaling(
    joints: tuple[GameScalingJointState, ...], *, enable: bool,
) -> GameScalingPlan:
    if type(enable) is not bool or not joints:
        raise ValueError("Game Engine Scaling 需要关节和布尔开关")
    by_path = {joint.path: joint for joint in joints}
    if len(by_path) != len(joints):
        raise ValueError("Game Engine Scaling 关节路径重复")
    for joint in joints:
        if (not joint.path.startswith("|") or joint.parent == joint.path
                or len(joint.scale_sources) != 3
                or len(joint.stored_sources) != 3
                or len(joint.stored_attributes) != 3
                or any(type(value) is not bool
                       for value in joint.stored_attributes)
                or len(joint.fk_parent_scale_sources) != 3
                or type(joint.segment_scale_compensate) is not bool
                or type(joint.has_marker) is not bool
                or (joint.fk_parent_constraint is not None
                    and not joint.fk_parent_constraint)):
            raise ValueError("Game Engine Scaling 关节快照无效：" + joint.path)
        for source in (joint.scale_sources + joint.stored_sources
                       + joint.fk_parent_scale_sources
                       + (joint.fk_parent_compound_scale_source,)):
            if source is not None and (not isinstance(source, str) or "." not in source):
                raise ValueError("Game Engine Scaling 驱动插头无效：" + joint.path)
        if any(source is not None and not exists for source, exists in zip(
                joint.stored_sources, joint.stored_attributes)):
            raise ValueError("保留驱动存在但 GameEngineScalingS 属性缺失：" + joint.path)
        if joint.fk_parent_constraint is None and (
                any(joint.fk_parent_scale_sources)
                or joint.fk_parent_compound_scale_source is not None):
            raise ValueError("FK 父约束路径缺失：" + joint.path)

    planned = []
    nodes = []
    for joint in joints:
        marker = joint.has_marker or (enable and (
            joint.segment_scale_compensate or joint.leaf == "Root_M"))
        target_ssc = False if enable and marker else (
            True if not enable and joint.has_marker
            else joint.segment_scale_compensate)
        namespace, separator, _ = joint.path.rsplit("|", 1)[-1].rpartition(":")
        node_prefix = namespace + ":" if separator else ""
        compensation = (node_prefix + "GameEngineScalingSSCMPD2" + joint.leaf
                        if enable and marker and not joint.is_part
                        and (joint.stored_attributes[0]
                             or joint.scale_sources[0] is not None)
                        else None)
        in_ik = False
        for index in range(3):
            source = (joint.stored_sources[index]
                      if joint.stored_attributes[index]
                      else joint.scale_sources[index])
            if source is not None:
                in_ik = source.rsplit("|", 1)[-1].rsplit(":", 1)[-1].startswith(
                    "ScaleBlend")
        parent_is_part = (joint.parent in by_path
                          and by_path[joint.parent].is_part)
        ancestor = (_nearest_fk_ancestor(joint, by_path)
                    if compensation and (parent_is_part or in_ik) else None)
        inverse = (node_prefix + "GameEngineScalingSSCMPD1" + joint.leaf
                   if ancestor is not None else None)
        axes = []
        fk_parent_disconnect = None
        for index, axis in enumerate(AXES):
            current = joint.scale_sources[index]
            stored = joint.stored_sources[index]
            original = stored if joint.stored_attributes[index] else current
            ancestor_source = None
            if ancestor is not None:
                ancestor_source = (ancestor.stored_sources[index]
                                   if ancestor.stored_attributes[index]
                                   else ancestor.scale_sources[index])
            create_attribute = bool(enable and marker and current
                                    and not joint.stored_attributes[index])
            reroute = current if create_attribute else None
            disconnect = current if enable and marker and current else None
            fk_target = (joint.fk_parent_constraint + ".scale" + axis
                         if disconnect and joint.fk_parent_constraint else None)
            if fk_target and joint.fk_parent_compound_scale_source:
                fk_parent_disconnect = joint.fk_parent_compound_scale_source
            axes.append(GameScalingAxisPlan(
                axis=axis,
                scale_source=current,
                stored_source=stored,
                create_stored_attribute=create_attribute,
                reroute_source=reroute,
                disconnect_scale_source=disconnect,
                restore_source=(stored if not enable and joint.has_marker
                                and stored else None),
                compensation_source=(original if compensation else None),
                parent_inverse_source=(ancestor_source if inverse else None),
                fk_parent_scale_target=fk_target,
            ))
        planned.append(GameScalingJointPlan(
            path=joint.path, marker_required=marker,
            segment_scale_compensate=target_ssc,
            axes=tuple(axes), compensation_node=compensation,
            parent_inverse_node=inverse,
            fk_parent_disconnect_compound=fk_parent_disconnect))
        if compensation is not None:
            nodes.append(GameScalingNodeSpec(
                name=compensation, operation=1,
                input1_sources=tuple(axis.compensation_source for axis in axes),
                input2_sources=tuple(
                    inverse + ".output" + axis if inverse else None
                    for axis in AXES)))
        if inverse is not None:
            nodes.append(GameScalingNodeSpec(
                name=inverse, operation=2,
                input1_sources=(None, None, None),
                input2_sources=tuple(axis.parent_inverse_source for axis in axes),
                input1_constant=(1.0, 1.0, 1.0)))
    if len({node.name for node in nodes}) != len(nodes):
        raise ValueError("Game Engine Scaling 补偿节点名称冲突")
    return GameScalingPlan(enable, tuple(planned), tuple(nodes))
