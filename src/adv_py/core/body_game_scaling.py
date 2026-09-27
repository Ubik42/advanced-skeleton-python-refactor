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
    fk_control_exists: bool = False

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
    reroute_source: str | None
    restore_source: str | None
    compensation_source: str | None
    parent_inverse_source: str | None


@dataclass(frozen=True, slots=True)
class GameScalingJointPlan:
    path: str
    marker_required: bool
    segment_scale_compensate: bool
    axes: tuple[GameScalingAxisPlan, ...]
    compensation_node: str | None
    parent_inverse_node: str | None


@dataclass(frozen=True, slots=True)
class GameScalingPlan:
    enable: bool
    joints: tuple[GameScalingJointPlan, ...]
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
            if actual.stored_sources[index] != wanted_stored:
                issues.append(joint.path + " GameEngineScalingS"
                              + axis_plan.axis + " 驱动不符")
            if plan.enable and joint.compensation_node is not None:
                wanted_scale = (joint.compensation_node + ".output"
                                + axis_plan.axis
                                if axis_plan.compensation_source else None)
            elif plan.enable and axis_plan.reroute_source is not None:
                wanted_scale = None
            elif axis_plan.restore_source is not None:
                wanted_scale = axis_plan.restore_source
            elif (not plan.enable and prior.scale_sources[index] is not None
                  and prior.scale_sources[index].rsplit("|", 1)[-1].startswith(
                      "GameEngineScalingSSCMPD")):
                wanted_scale = None
            else:
                wanted_scale = prior.scale_sources[index]
            if actual.scale_sources[index] != wanted_scale:
                issues.append(joint.path + ".scale" + axis_plan.axis
                              + " 驱动不符")
    return tuple(issues)


def _nearest_fk_ancestor(
    state: GameScalingJointState,
    by_path: dict[str, GameScalingJointState],
) -> GameScalingJointState | None:
    parent = state.parent
    visited: set[str] = set()
    while parent is not None:
        if parent in visited:
            raise ValueError("Game Engine Scaling 关节父链存在环")
        visited.add(parent)
        candidate = by_path.get(parent)
        if candidate is None:
            return None
        if not candidate.is_part and candidate.fk_control_exists:
            return candidate
        parent = candidate.parent
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
                or type(joint.segment_scale_compensate) is not bool
                or type(joint.has_marker) is not bool):
            raise ValueError("Game Engine Scaling 关节快照无效：" + joint.path)
        for source in joint.scale_sources + joint.stored_sources:
            if source is not None and (not isinstance(source, str) or "." not in source):
                raise ValueError("Game Engine Scaling 驱动插头无效：" + joint.path)

    planned = []
    for joint in joints:
        marker = joint.has_marker or (enable and (
            joint.segment_scale_compensate or joint.leaf == "Root_M"))
        target_ssc = False if enable and marker else (
            True if not enable and joint.has_marker
            else joint.segment_scale_compensate)
        compensation = ("GameEngineScalingSSCMPD2" + joint.leaf
                        if enable and marker and not joint.is_part
                        and (joint.stored_sources[0] or joint.scale_sources[0])
                        else None)
        in_ik = any(source is not None and source.rsplit("|", 1)[-1].startswith(
            "ScaleBlend") for source in joint.scale_sources + joint.stored_sources)
        parent_is_part = (joint.parent in by_path
                          and by_path[joint.parent].is_part)
        ancestor = (_nearest_fk_ancestor(joint, by_path)
                    if compensation and (parent_is_part or in_ik) else None)
        inverse = ("GameEngineScalingSSCMPD1" + joint.leaf
                   if ancestor is not None else None)
        axes = []
        for index, axis in enumerate(AXES):
            current = joint.scale_sources[index]
            stored = joint.stored_sources[index]
            original = stored or current
            ancestor_source = (ancestor.stored_sources[index]
                               or ancestor.scale_sources[index]
                               if ancestor is not None else None)
            axes.append(GameScalingAxisPlan(
                axis=axis,
                scale_source=current,
                stored_source=stored,
                reroute_source=(current if enable and marker and current
                                and not stored else None),
                restore_source=(stored if not enable and joint.has_marker
                                and stored else None),
                compensation_source=(original if compensation else None),
                parent_inverse_source=(ancestor_source if inverse else None),
            ))
        planned.append(GameScalingJointPlan(
            path=joint.path, marker_required=marker,
            segment_scale_compensate=target_ssc,
            axes=tuple(axes), compensation_node=compensation,
            parent_inverse_node=inverse))
    return GameScalingPlan(enable, tuple(planned))
