"""Pure connection plan for ADV 6.925's separate Game Engine Scaling tool.

The Preparation gameEngine checkbox does not invoke this command. Enabling
reroutes existing joint-scale drivers through GameEngineScalingS* channels,
then supplies direct scale from multiplyDivide nodes. Disabling restores
the original scale drivers and segmentScaleCompensate.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from .original_game_hierarchy import original_part_joint


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
    scale_source_ik_roles: tuple[bool | None, bool | None, bool | None] = (None, None, None)
    fk_parent_extra_constraints: tuple[str, ...] = ()
    fk_parent_extra_scale_sources: tuple[tuple[str | None, str | None, str | None], ...] = ()
    fk_parent_extra_compound_sources: tuple[str | None, ...] = ()
    authored_segment_scale_compensate: bool | None = None
    uuid: str | None = None
    stored_values: tuple[float, float, float] = (0., 0., 0.)

    @property
    def leaf(self) -> str:
        return self.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    @property
    def is_part(self) -> bool:
        return original_part_joint(self.leaf)


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
    fk_parent_extra_scale_targets: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GameScalingJointPlan:
    path: str
    marker_required: bool
    segment_scale_compensate: bool
    axes: tuple[GameScalingAxisPlan, ...]
    compensation_node: str | None
    parent_inverse_node: str | None
    fk_parent_disconnect_compound: str | None
    fk_parent_extra_disconnect_compounds: tuple[tuple[str, str], ...] = ()


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
    input2_value: tuple[float, float, float] = (0., 0., 0.)


@dataclass(frozen=True, slots=True)
class GameScalingPlan:
    enable: bool
    joints: tuple[GameScalingJointPlan, ...]
    nodes: tuple[GameScalingNodeSpec, ...]
    # Original MEL deletes every prior GameEngineScalingSSCMPD* node first.
    remove_old_compensation_nodes: bool = True
    # A later native Unreal/Root Motion delete can remove export joints while
    # leaving their MPD nodes. This records that explicit scene operation;
    # it does not change the original scaling plan or delete its native graph.
    retired_joints: tuple[str, ...] = ()


def audit_body_game_scaling(
    plan: GameScalingPlan,
    before: tuple[GameScalingJointState, ...],
    after: tuple[GameScalingJointState, ...],
) -> tuple[str, ...]:
    before_by_path = {item.path: item for item in before}
    after_by_path = {item.path: item for item in after}
    retired = set(plan.retired_joints)
    expected = {item.path for item in plan.joints} - retired
    before_by_path = {path: row for path, row in before_by_path.items() if path not in retired}
    if (set(before_by_path) != expected or set(after_by_path) != expected
            or len(before_by_path) != len(before) - len(retired)
            or len(after_by_path) != len(after)):
        return ("Game Engine Scaling 关节集合变化",)
    issues = []
    for joint in plan.joints:
        if joint.path in retired:
            continue
        prior = before_by_path[joint.path]
        actual = after_by_path[joint.path]
        if prior.uuid is not None and actual.uuid != prior.uuid:
            issues.append(joint.path + ' 原关节身份变化')
            continue
        if (actual.fk_parent_constraint != prior.fk_parent_constraint
                or actual.fk_parent_extra_constraints != prior.fk_parent_extra_constraints
                or len(actual.fk_parent_extra_scale_sources) != len(prior.fk_parent_extra_constraints)
                or len(actual.fk_parent_extra_compound_sources) != len(prior.fk_parent_extra_constraints)):
            issues.append(joint.path + ' 原版 FK 跟随角色集合变化')
            continue
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
            if (wanted_attribute and wanted_stored is None
                    and actual.stored_values[index] != prior.stored_values[index]):
                issues.append(joint.path + ' 保留缩放常量不符：' + axis_plan.axis)
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
            wanted_fk_source = (joint.path + ".GameEngineScalingS" + axis_plan.axis
                if axis_plan.fk_parent_scale_target is not None
                else None if prior.fk_parent_compound_scale_source is not None
                    and any(axis.fk_parent_scale_target for axis in joint.axes)
                else prior.fk_parent_scale_sources[index])
            if actual.fk_parent_scale_sources[index] != wanted_fk_source:
                issues.append(joint.path + " FK 父约束缩放来源不符：" + axis_plan.axis)
            for extra_index, target in enumerate(prior.fk_parent_extra_constraints):
                expected_source = (joint.path + '.GameEngineScalingS' + axis_plan.axis
                    if target + '.scale' + axis_plan.axis in axis_plan.fk_parent_extra_scale_targets
                    else None if prior.fk_parent_extra_compound_sources[extra_index] is not None
                        and any(target + '.scale' + axis.axis in axis.fk_parent_extra_scale_targets
                                for axis in joint.axes)
                    else prior.fk_parent_extra_scale_sources[extra_index][index])
                if actual.fk_parent_extra_scale_sources[extra_index][index] != expected_source:
                    issues.append(target + ' 原版 FK 跟随缩放来源不符')
        expected_compound = (None if joint.fk_parent_disconnect_compound is not None
                             else prior.fk_parent_compound_scale_source)
        # Connecting an individual scale child replaces a compound incoming
        # connection in Maya even if MEL's explicit disconnect only applies
        # to the exact joint.scale -> FKParentConstraintTo.scale edge.
        if any(axis.fk_parent_scale_target for axis in joint.axes):
            expected_compound = None
        if actual.fk_parent_compound_scale_source != expected_compound:
            issues.append(joint.path + " FK 父约束仍连接关节复合缩放")
        for index, target in enumerate(prior.fk_parent_extra_constraints):
            expected_compound = (None if any(target + '.scale' + axis.axis
                in axis.fk_parent_extra_scale_targets for axis in joint.axes)
                else prior.fk_parent_extra_compound_sources[index])
            if actual.fk_parent_extra_compound_sources[index] != expected_compound:
                issues.append(target + ' 原版 FK 跟随复合缩放来源不符')
    return tuple(issues)


def audit_body_game_scaling_nodes(
    plan: GameScalingPlan,
    actual: tuple[GameScalingNodeState, ...],
    *, frozen_inputs=(),
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
        for target, value in frozen_inputs:
            node, _, attribute = target.partition('.')
            if node != name:
                continue
            values = state.input1_value if attribute.startswith('input1') else state.input2_value
            if values['XYZ'.index(attribute[-1])] != value:
                issues.append(target + ' 删除驱动后保留的输入常量不符')
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
                or len(joint.stored_values) != 3
                or any(type(value) not in (int, float) or not isfinite(value) for value in joint.stored_values)
                or any(type(value) is not bool
                       for value in joint.stored_attributes)
                or len(joint.fk_parent_scale_sources) != 3
                or len(joint.scale_source_ik_roles) != 3
                or any(role is not None and type(role) is not bool for role in joint.scale_source_ik_roles)
                or len(joint.fk_parent_extra_constraints) != len(joint.fk_parent_extra_scale_sources)
                or len(joint.fk_parent_extra_constraints) != len(joint.fk_parent_extra_compound_sources)
                or len(set(joint.fk_parent_extra_constraints)) != len(joint.fk_parent_extra_constraints)
                or any(len(row) != 3 for row in joint.fk_parent_extra_scale_sources)
                or type(joint.segment_scale_compensate) is not bool
                or type(joint.has_marker) is not bool
                or (joint.authored_segment_scale_compensate is not None
                    and type(joint.authored_segment_scale_compensate) is not bool)
                or (joint.uuid is not None and (not isinstance(joint.uuid, str) or not joint.uuid))
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
    in_ik = False  # MEL variable persists across native joint iterations.
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
                             or _after_compensation_delete(joint.scale_sources[0]) is not None)
                        else None)
        for index in range(3):
            source = (joint.stored_sources[index]
                      if joint.stored_attributes[index]
                      else _after_compensation_delete(joint.scale_sources[index]))
            if compensation and source is not None:
                role = joint.scale_source_ik_roles[index]
                in_ik = (role if role is not None else
                    source.rsplit("|", 1)[-1].rsplit(":", 1)[-1].startswith("ScaleBlend"))
        parent_is_part = (joint.parent in by_path
                          and by_path[joint.parent].is_part)
        ancestor = (_nearest_fk_ancestor(joint, by_path)
                    if compensation and (parent_is_part or in_ik) else None)
        inverse = (node_prefix + "GameEngineScalingSSCMPD1" + joint.leaf
                   if ancestor is not None else None)
        axes = []
        fk_parent_disconnect = None
        extra_disconnects = ()
        for index, axis in enumerate(AXES):
            current = _after_compensation_delete(joint.scale_sources[index])
            stored = joint.stored_sources[index]
            original = stored if joint.stored_attributes[index] else current
            ancestor_source = None
            if ancestor is not None:
                ancestor_source = (ancestor.stored_sources[index]
                                   if ancestor.stored_attributes[index]
                                   else _after_compensation_delete(ancestor.scale_sources[index])
                                   if (ancestor.has_marker or ancestor.segment_scale_compensate
                                       or ancestor.leaf == 'Root_M') else None)
            create_attribute = bool(enable and marker and current
                                    and not joint.stored_attributes[index])
            reroute = current if create_attribute else None
            disconnect = current if enable and marker and current else None
            fk_target = (joint.fk_parent_constraint + ".scale" + axis
                         if disconnect and joint.fk_parent_constraint else None)
            if fk_target and joint.fk_parent_compound_scale_source == joint.path + '.scale':
                fk_parent_disconnect = joint.fk_parent_compound_scale_source
            extra_targets = tuple(target + '.scale' + axis for target in
                joint.fk_parent_extra_constraints) if disconnect else ()
            if extra_targets:
                extra_disconnects = tuple((source, target + '.scale') for source, target in
                    zip(joint.fk_parent_extra_compound_sources, joint.fk_parent_extra_constraints)
                    if source == joint.path + '.scale')
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
                fk_parent_extra_scale_targets=extra_targets,
            ))
        planned.append(GameScalingJointPlan(
            path=joint.path, marker_required=marker,
            segment_scale_compensate=target_ssc,
            axes=tuple(axes), compensation_node=compensation,
            parent_inverse_node=inverse,
            fk_parent_disconnect_compound=fk_parent_disconnect,
            fk_parent_extra_disconnect_compounds=extra_disconnects))
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


def _after_compensation_delete(source):
    # Source deletes these nodes before querying any scale channels. A repeated
    # enable cannot keep their outputs as new original drivers.
    if source and source.split('.', 1)[0].rsplit('|', 1)[-1].rsplit(':', 1)[-1].startswith('GameEngineScalingSSCMPD'):
        return None
    return source



def game_scaling_result_states(before, plan):
    """Project the captured source operation for replay after Body replacement.

    This preserves the operation already performed, including FK routes kept
    by Disable. It never runs Enable against a later, different hierarchy.
    """
    prior_by_path = {row.path: row for row in before}
    result = []
    for joint in plan.joints:
        if joint.path in plan.retired_joints:
            continue
        prior = prior_by_path[joint.path]
        scale = []
        stored = []
        attributes = []
        fk = []
        extra = [[] for _ in prior.fk_parent_extra_constraints]
        fk_changed = any(axis.fk_parent_scale_target for axis in joint.axes)
        extra_changed = tuple(any(target + '.scale' + axis.axis in axis.fk_parent_extra_scale_targets
                                  for axis in joint.axes)
                              for target in prior.fk_parent_extra_constraints)
        for index, axis in enumerate(joint.axes):
            stored.append(axis.reroute_source or prior.stored_sources[index])
            attributes.append(prior.stored_attributes[index] or axis.create_stored_attribute)
            if plan.enable and joint.compensation_node is not None:
                source = joint.compensation_node + '.output' + axis.axis if axis.compensation_source else None
            elif plan.enable and axis.disconnect_scale_source is not None:
                source = None
            elif axis.restore_source is not None:
                source = axis.restore_source
            elif not plan.enable and _after_compensation_delete(prior.scale_sources[index]) is None:
                source = None
            else:
                source = prior.scale_sources[index]
            scale.append(source)
            fk.append(joint.path + '.GameEngineScalingS' + axis.axis
                      if axis.fk_parent_scale_target else None
                      if prior.fk_parent_compound_scale_source is not None and fk_changed
                      else prior.fk_parent_scale_sources[index])
            for number, target in enumerate(prior.fk_parent_extra_constraints):
                extra[number].append(joint.path + '.GameEngineScalingS' + axis.axis
                    if target + '.scale' + axis.axis in axis.fk_parent_extra_scale_targets else None
                    if prior.fk_parent_extra_compound_sources[number] is not None and extra_changed[number]
                    else prior.fk_parent_extra_scale_sources[number][index])
        result.append(replace(prior, has_marker=joint.marker_required,
            segment_scale_compensate=joint.segment_scale_compensate,
            scale_sources=tuple(scale), stored_sources=tuple(stored), stored_attributes=tuple(attributes),
            fk_parent_scale_sources=tuple(fk),
            fk_parent_compound_scale_source=None if fk_changed or joint.fk_parent_disconnect_compound else prior.fk_parent_compound_scale_source,
            fk_parent_extra_scale_sources=tuple(tuple(row) for row in extra),
            fk_parent_extra_compound_sources=tuple(None if changed else source for changed, source in
                zip(extra_changed, prior.fk_parent_extra_compound_sources))))
    return tuple(result)
