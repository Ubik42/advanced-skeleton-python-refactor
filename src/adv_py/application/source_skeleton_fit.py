"""Create an editable Fit from a named, already positioned joint hierarchy."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from math import isfinite, sqrt
import re
from typing import Protocol

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_template import FitJointSpec, FitTemplateSpec
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_orientation import FitOrientationRequest

from .fit_container import CreateFitSkeleton, FitContainerHost
from .oriented_fit_template import (BuildOrientedFitTemplate,
                                    OrientedFitTemplateHost)
from .registered_body_build import _JoinedTransactionHost
from .variable_body_fit import variable_body_source_inputs


@dataclass(frozen=True, slots=True)
class SourceSkeletonJoint:
    path: str
    name: str
    parent: str | None
    world_position: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class SourceSkeletonFitResult:
    joint_count: int
    spine_segments: int


@dataclass(frozen=True, slots=True)
class SourceSkeletonFitPlan:
    template: FitTemplateSpec
    orientation: FitOrientationRequest
    spine_segments: int


class SourceSkeletonFitHost(FitContainerHost, OrientedFitTemplateHost,
                            Protocol):
    def capture_source_skeleton(self, root: str) -> tuple[SourceSkeletonJoint, ...]: ...
    def scene_up_axis(self) -> FitUpAxis: ...
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


_FINGER = re.compile(r"^(Thumb|Index|Middle|Ring|Pinky)Finger([1-4])$")
_ALIASES = {
    "Pelvis": "Root", "Hips": "Root", "Spine": "Spine1",
    "Spine2": "Chest", "Clavicle": "Scapula", "Hand": "Wrist",
    "Foot": "Ankle", "Toe": "Toes", "Ball": "Toes",
}


def _base_name(source_name: str) -> str | None:
    name = source_name.rsplit(":", 1)[-1]
    if name.endswith("_L"):
        return None
    if name.endswith(("_R", "_M")):
        name = name[:-2]
    return name


def _fit_name(source_name: str) -> str | None:
    name = _base_name(source_name)
    if name is None:
        return None
    finger = _FINGER.fullmatch(name)
    if finger:
        return finger.group(1) + ("End" if finger.group(2) == "4"
                                  else finger.group(2))
    return _ALIASES.get(name, name)


def _axial_source_paths(source: tuple[SourceSkeletonJoint, ...],
                        root: SourceSkeletonJoint) -> tuple[str, ...]:
    by_path = {joint.path: joint for joint in source}
    if _fit_name(root.name) != "Root":
        raise FitSkeletonValidationError("来源根关节须为 Root、Pelvis 或 Hips")
    necks = [joint for joint in source if _fit_name(joint.name) == "Neck"]
    if len(necks) != 1:
        raise FitSkeletonValidationError("来源骨架须有唯一的 Neck 关节")
    paths = []
    parent = necks[0].parent
    while parent and parent in by_path and parent != root.path:
        joint = by_path[parent]
        name = _base_name(joint.name)
        if name and (name in {"Chest", "UpperChest", "Spine"}
                     or re.fullmatch(r"Spine\d+", name)):
            paths.append(parent)
        elif _fit_name(joint.name) != "Root":
            raise FitSkeletonValidationError(
                "Neck 与 Root 之间存在非脊柱关节：" + joint.name)
        parent = joint.parent
    if parent != root.path or not paths:
        raise FitSkeletonValidationError("来源骨架缺少 Root 到 Neck 的脊柱链")
    if len(paths) > 63:
        raise FitSkeletonValidationError("来源脊柱超过 63 段")
    return tuple(reversed(paths))


def _add_optional_end_markers(by_name: dict[str, SourceSkeletonJoint],
                              up_axis: str) -> None:
    """Fill Fit-only end and foot guides absent from many export skeletons."""
    def add(name: str, parent: str, position: tuple[float, float, float]):
        if name not in by_name and parent in by_name:
            by_name[name] = SourceSkeletonJoint(
                "@fit-guide:" + name, name, by_name[parent].path, position)

    if {"Neck", "Head"} <= by_name.keys():
        neck = by_name["Neck"].world_position
        head = by_name["Head"].world_position
        add("HeadEnd", "Head", tuple(h + (h - n) * 0.5
                                      for h, n in zip(head, neck)))
    for digit in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
        second, third = digit + "2", digit + "3"
        if {second, third} <= by_name.keys():
            p2 = by_name[second].world_position
            p3 = by_name[third].world_position
            add(digit + "End", third, tuple(b + (b - a) * 0.5
                                             for a, b in zip(p2, p3)))
    if not {"Root", "Hip", "Ankle", "Toes"} <= by_name.keys():
        return
    root = by_name["Root"].world_position
    hip = by_name["Hip"].world_position
    ankle = by_name["Ankle"].world_position
    toes = by_name["Toes"].world_position
    foot = tuple(t - a for t, a in zip(toes, ankle))
    add("Heel", "Ankle", tuple(a - f * 0.5 for a, f in zip(ankle, foot)))
    add("ToesEnd", "Toes", tuple(t + f * 0.5 for t, f in zip(toes, foot)))
    side = [h - r for h, r in zip(hip, root)]
    side[1 if up_axis == "y" else 2] = 0.0
    side_length = sqrt(sum(value * value for value in side))
    if side_length < 1e-5:
        side = [-1.0, 0.0, 0.0]
        side_length = 1.0
    width = max(0.25, sqrt(sum(value * value for value in foot)) * 0.2)
    offset = tuple(value * width / side_length for value in side)
    add("FootSideInner", "Toes", tuple(t - d for t, d in zip(toes, offset)))
    add("FootSideOuter", "Toes", tuple(t + d for t, d in zip(toes, offset)))


def plan_source_skeleton_fit(source: tuple[SourceSkeletonJoint, ...],
                             axis: FitUpAxis) -> SourceSkeletonFitPlan:
    """Map a captured hierarchy to Fit data without querying a DCC scene."""
    if not source:
        raise FitSkeletonValidationError("所选骨架没有关节")
    if not isinstance(axis, FitUpAxis):
        raise FitSkeletonValidationError("来源骨架场景 Up Axis 须为 Y 或 Z")
    for joint in source:
        if (not isinstance(joint.path, str) or not joint.path
                or not isinstance(joint.name, str) or not joint.name
                or (joint.parent is not None
                    and (not isinstance(joint.parent, str)
                         or not joint.parent))):
            raise FitSkeletonValidationError("来源骨架关节缺少有效路径、名称或父级")
        position = joint.world_position
        if (not isinstance(position, (tuple, list)) or len(position) != 3
                or any(isinstance(value, bool)
                       or not isinstance(value, (int, float))
                       or not isfinite(value) for value in position)):
            raise FitSkeletonValidationError(
                "来源骨架关节世界坐标无效：" + joint.name)
    by_path = {joint.path: joint for joint in source}
    if len(by_path) != len(source):
        raise FitSkeletonValidationError("来源骨架包含重复的关节路径")
    roots = [joint for joint in source if joint.parent is None]
    if len(roots) != 1:
        raise FitSkeletonValidationError("来源骨架须有唯一的根关节")
    root = roots[0]
    for joint in source:
        if joint.path != root.path and joint.parent not in by_path:
            raise FitSkeletonValidationError(
                "来源骨架关节父级不在所选层级中：" + joint.name)
        visited = {joint.path}
        parent = joint.parent
        while parent in by_path:
            if parent in visited:
                raise FitSkeletonValidationError("来源骨架包含循环父链")
            visited.add(parent)
            parent = by_path[parent].parent
        if joint.path != root.path and root.path not in visited:
            raise FitSkeletonValidationError(
                "来源骨架关节未连接到唯一根关节：" + joint.name)
    axial_paths = _axial_source_paths(source, root)
    axial_names = tuple(f"Spine{index}" for index in
                        range(1, len(axial_paths))) + ("Chest",)
    name_by_path = dict(zip(axial_paths, axial_names))

    def mapped_name(joint: SourceSkeletonJoint) -> str | None:
        return name_by_path.get(joint.path) or _fit_name(joint.name)

    by_name: dict[str, SourceSkeletonJoint] = {}
    for joint in source:
        name = mapped_name(joint)
        if name is None:
            continue
        if name in by_name:
            previous = by_name[name]
            previous_exact = _base_name(previous.name) == name
            current_exact = _base_name(joint.name) == name
            if current_exact and not previous_exact:
                by_name[name] = joint
            elif previous_exact and not current_exact:
                continue
            else:
                raise FitSkeletonValidationError("来源骨架名称映射重复：" + name)
            continue
        by_name[name] = joint

    _add_optional_end_markers(by_name, axis.value)
    body, body_request = variable_body_source_inputs(
        axis, len(axial_paths), 1.0, False)
    hand, hand_request = variable_body_source_inputs(
        axis, len(axial_paths), 1.0, True)
    if all(spec.name in by_name for spec in hand.joints):
        reference = hand
        request = hand_request
    elif all(spec.name in by_name for spec in body.joints):
        hand_names = {spec.name for spec in hand.joints}
        partial_hand = (hand_names - {spec.name for spec in body.joints})
        if partial_hand & by_name.keys():
            missing_hand = sorted(partial_hand - by_name.keys())
            raise FitSkeletonValidationError(
                "来源骨架五指链不完整：" + "、".join(missing_hand))
        reference = body
        request = body_request
    else:
        missing = [spec.name for spec in body.joints
                   if spec.name not in by_name]
        raise FitSkeletonValidationError(
            "来源骨架缺少标准身体关节：" + "、".join(missing))

    source_by_path = {joint.path: joint for joint in source}
    reference_names = {spec.name for spec in reference.joints}
    specs = []
    for reference_joint in reference.joints:
        joint = by_name[reference_joint.name]
        expected_parent = reference_joint.parent
        parent_path = joint.parent
        while parent_path and parent_path in source_by_path:
            parent_name = mapped_name(source_by_path[parent_path])
            if parent_name in reference_names and parent_name != reference_joint.name:
                break
            parent_path = source_by_path[parent_path].parent
        actual_parent = (mapped_name(source_by_path[parent_path])
                         if parent_path in source_by_path else None)
        if actual_parent != expected_parent:
            raise FitSkeletonValidationError(
                f"来源骨架层级不符：{reference_joint.name} 需要父关节 "
                f"{expected_parent or '无'}")
        parent_position = ((0.0, 0.0, 0.0) if expected_parent is None
                           else by_name[expected_parent].world_position)
        position = tuple(value - parent for value, parent in zip(
            joint.world_position, parent_position))
        specs.append(FitJointSpec(reference_joint.name, expected_parent,
                                  position, reference_joint.label))
    template = FitTemplateSpec("source_skeleton", tuple(specs))
    return SourceSkeletonFitPlan(template, request, len(axial_paths))


class BuildFitFromSourceSkeleton:
    def __init__(self, host: SourceSkeletonFitHost):
        self._host = host

    def plan(self, source_root: str) -> SourceSkeletonFitPlan:
        return plan_source_skeleton_fit(
            self._host.capture_source_skeleton(source_root),
            self._host.scene_up_axis())

    def apply(self, source_root: str,
              container: str = "FitSkeleton") -> SourceSkeletonFitResult:
        return self.apply_plan(self.plan(source_root), container)

    def apply_plan(self, plan: SourceSkeletonFitPlan,
                   container: str = "FitSkeleton") -> SourceSkeletonFitResult:
        with self._host.transaction("从标准骨架创建 Fit"):
            joined = _JoinedTransactionHost(self._host)
            if not self._host.find_name_collisions(container):
                CreateFitSkeleton(joined).apply(container)
            result = BuildOrientedFitTemplate(joined).apply(
                plan.template, plan.orientation, container,
                transaction_label="从标准骨架创建并朝向 Fit",
                error_context="标准骨架 Fit")
        return SourceSkeletonFitResult(len(result.template.joint_paths),
                                       plan.spine_segments)
