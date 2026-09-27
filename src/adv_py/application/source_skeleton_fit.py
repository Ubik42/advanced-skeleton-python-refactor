"""Create an editable Fit from a named, already positioned joint hierarchy."""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
import re
from typing import Protocol

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_template import (
    FitJointSpec, FitTemplateSpec, synthetic_body_source_fit_template)
from adv_py.core.body_hand_fit import synthetic_body_with_hand_source_fit_template

from .body_hand_fit import body_with_hand_orientation_request
from .fit_container import CreateFitSkeleton
from .oriented_fit_template import BuildOrientedFitTemplate
from .registered_body_build import _JoinedTransactionHost
from .upper_body_fit import body_source_orientation_request


@dataclass(frozen=True, slots=True)
class SourceSkeletonJoint:
    path: str
    name: str
    parent: str | None
    world_position: tuple[float, float, float]


class SourceSkeletonFitHost(Protocol):
    def capture_source_skeleton(self, root: str) -> tuple[SourceSkeletonJoint, ...]: ...
    def scene_up_axis(self): ...
    def find_name_collisions(self, name: str): ...
    def transaction(self, label: str): ...


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


class BuildFitFromSourceSkeleton:
    def __init__(self, host: SourceSkeletonFitHost):
        self._host = host

    def apply(self, source_root: str, container: str = "FitSkeleton") -> int:
        source = self._host.capture_source_skeleton(source_root)
        if not source:
            raise FitSkeletonValidationError("所选骨架没有关节")
        by_name: dict[str, SourceSkeletonJoint] = {}
        for joint in source:
            name = _fit_name(joint.name)
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

        axis = self._host.scene_up_axis()
        _add_optional_end_markers(by_name, axis.value)
        body = synthetic_body_source_fit_template(axis)
        hand = synthetic_body_with_hand_source_fit_template(axis)
        if all(spec.name in by_name for spec in hand.joints):
            reference = hand
            request = body_with_hand_orientation_request()
        elif all(spec.name in by_name for spec in body.joints):
            hand_names = {spec.name for spec in hand.joints}
            partial_hand = (hand_names - {spec.name for spec in body.joints})
            if partial_hand & by_name.keys():
                missing_hand = sorted(partial_hand - by_name.keys())
                raise FitSkeletonValidationError(
                    "来源骨架五指链不完整：" + "、".join(missing_hand))
            reference = body
            request = body_source_orientation_request()
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
                parent_name = _fit_name(source_by_path[parent_path].name)
                if parent_name in reference_names and parent_name != reference_joint.name:
                    break
                parent_path = source_by_path[parent_path].parent
            actual_parent = (_fit_name(source_by_path[parent_path].name)
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

        with self._host.transaction("从标准骨架创建 Fit"):
            joined = _JoinedTransactionHost(self._host)
            if not self._host.find_name_collisions(container):
                CreateFitSkeleton(joined).apply(container)
            result = BuildOrientedFitTemplate(joined).apply(
                template, request, container,
                transaction_label="从标准骨架创建并朝向 Fit",
                error_context="标准骨架 Fit")
        return len(result.template.joint_paths)
