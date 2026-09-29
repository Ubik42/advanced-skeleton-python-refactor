"""Create an editable Fit from a named, already positioned joint hierarchy."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from math import isfinite
import re
from typing import Protocol

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_metadata import (
    FitJointField, FitJointFieldEdit, FitJointMetadata, FitJointPatch,
    FitJointValidationError, audit_fit_joint, fit_joint_value,
    predict_fit_joint_metadata)
from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_template import FitJointSpec, FitTemplateSpec
from adv_py.core.joint_labels import JointLabel
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
    twist_joints: int | None = None
    inbetween_joints: int | None = None
    untwister: bool | None = None
    deform_profile: FitDeformProfile | None = None
    rotation_order: int | None = None
    additional_fit_edits: tuple[FitJointFieldEdit, ...] = ()
    effective_no_flip: bool | None = None
    effective_skin_enabled: bool | None = None
    label: JointLabel | None = None
    sibling_index: int = 0


@dataclass(frozen=True, slots=True)
class SourceSkeletonFitResult:
    joint_count: int
    spine_segments: int
    source_only_intermediates: tuple[str, ...] = ()
    source_only_left_branches: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceSkeletonFitPlan:
    template: FitTemplateSpec
    orientation: FitOrientationRequest
    spine_segments: int
    part_metadata: tuple[tuple[str, tuple[FitJointFieldEdit, ...]], ...] = ()
    deform_profiles: tuple[tuple[str, FitDeformProfile], ...] = ()
    rotation_orders: tuple[tuple[str, int], ...] = ()
    skin_disabled: tuple[str, ...] = ()
    source_only_intermediates: tuple[str, ...] = ()
    source_only_left_branches: tuple[str, ...] = ()


class SourceSkeletonFitHost(FitContainerHost, OrientedFitTemplateHost,
                            Protocol):
    def capture_source_skeleton(self, root: str) -> tuple[SourceSkeletonJoint, ...]: ...
    def scene_up_axis(self) -> FitUpAxis: ...
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def apply_fit_joint_edit(self, joint: str, edit: FitJointFieldEdit) -> None: ...
    def read_fit_joint_metadata(self, joint: str) -> FitJointMetadata: ...
    def write_fit_deform_profile(self, joint: str,
                                 profile: FitDeformProfile) -> None: ...
    def write_missing_fit_deform_profiles(
        self, container: str, joints: tuple[str, ...],
    ) -> None: ...
    def write_fit_rotation_order(self, joint: str, order: int) -> None: ...
    def write_fit_no_skin(self, joint: str) -> None: ...
    def read_fit_skin_enabled(self, joint: str) -> bool: ...


_FINGER = re.compile(r"^(Thumb|Index|Middle|Ring|Pinky)Finger([1-4])$")
_ALIASES = {
    "Pelvis": "Root", "Hips": "Root", "Spine": "Spine1",
    "Spine2": "Chest", "Clavicle": "Scapula", "Hand": "Wrist",
    "Foot": "Ankle", "Toe": "Toes", "Ball": "Toes",
}

# Default part switches on the 6.925 biped Fit. Keep a source skeleton's
# explicit switches authoritative, including an explicit zero count.
_STANDARD_BIPED_PARTS = {
    "Root": (FitJointField.INBETWEEN_JOINTS, 2),
    "Spine1": (FitJointField.INBETWEEN_JOINTS, 2),
    "Neck": (FitJointField.INBETWEEN_JOINTS, 2),
    "Hip": (FitJointField.TWIST_JOINTS, 2),
    "Shoulder": (FitJointField.TWIST_JOINTS, 2),
    "Elbow": (FitJointField.TWIST_JOINTS, 2),
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
        # Imported skeletons may insert helper joints between named spine
        # joints.  The canonical solver consumes only the named spine chain;
        # the helpers remain on the source and are reported by the planner.
        parent = joint.parent
    if parent != root.path or not paths:
        raise FitSkeletonValidationError("来源骨架缺少 Root 到 Neck 的脊柱链")
    if len(paths) > 63:
        raise FitSkeletonValidationError("来源脊柱超过 63 段")
    return tuple(reversed(paths))


def _add_optional_end_markers(by_name: dict[str, SourceSkeletonJoint]) -> None:
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
    if not {"Ankle", "Toes"} <= by_name.keys():
        return
    ankle = by_name["Ankle"].world_position
    toes = by_name["Toes"].world_position
    foot = tuple(t - a for t, a in zip(toes, ankle))
    add("ToesEnd", "Toes", tuple(t + f * 0.5 for t, f in zip(toes, foot)))


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
        if (type(joint.sibling_index) is not int
                or joint.sibling_index < 0):
            raise FitSkeletonValidationError(
                "来源骨架同级顺序无效：" + joint.name)
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
    def left_mirror_branch(joint: SourceSkeletonJoint) -> bool:
        current = joint.path
        while current in by_path:
            ancestor = by_path[current]
            if ancestor.name.rsplit(":", 1)[-1].endswith("_L"):
                return True
            current = ancestor.parent
        return False

    right_by_leaf: dict[str, SourceSkeletonJoint] = {}
    for joint in source:
        leaf = joint.name.rsplit(":", 1)[-1]
        if leaf.endswith("_R") and not left_mirror_branch(joint):
            if leaf in right_by_leaf:
                raise FitSkeletonValidationError(
                    "来源骨架右侧关节短名重复：" + leaf)
            right_by_leaf[leaf] = joint
    right_semantic_names = {
        _fit_name(joint.name) for joint in right_by_leaf.values()}
    unpaired_left_roots = {
        joint.path for joint in source
        if joint.name.rsplit(":", 1)[-1].endswith("_L")
        and joint.name.rsplit(":", 1)[-1][:-2] + "_R"
        not in right_by_leaf
        and _fit_name(joint.name.rsplit(":", 1)[-1][:-2] + "_R")
        not in right_semantic_names}
    left_authored_paths = set(unpaired_left_roots)
    # A left-only branch can contain children named without a side suffix.
    # They inherit their parent's left-only Body emission in the MEL build.
    # Walk the actual source parent chain so a paired _L child cannot cause
    # unrelated descendants to be claimed by this branch.
    for joint in sorted(source, key=lambda item: item.path.count("|")):
        leaf = joint.name.rsplit(":", 1)[-1]
        semantic_leaf = leaf.removesuffix("_NonSymmetry")
        if (joint.parent in left_authored_paths
                and "_" not in semantic_leaf):
            left_authored_paths.add(joint.path)
    axial_paths = _axial_source_paths(source, root)
    axial_names = tuple(f"Spine{index}" for index in
                        range(1, len(axial_paths))) + ("Chest",)
    name_by_path = dict(zip(axial_paths, axial_names))
    explicit_names = {_base_name(joint.name) for joint in source
                      if not left_mirror_branch(joint)}
    # An alias is only a substitute when the standard joint is absent.
    # A skeleton containing both Ankle and Foot must retain its actual Foot
    # branch instead of silently letting Ankle win the duplicate mapping.
    optional_aliases = {"Clavicle", "Hand", "Foot", "Toe", "Ball"}

    def mapped_name(joint: SourceSkeletonJoint) -> str | None:
        if joint.path in left_authored_paths:
            leaf = joint.name.rsplit(":", 1)[-1]
            base = leaf.removesuffix("_L").removesuffix("_NonSymmetry")
            return base
        if joint.path in name_by_path:
            return name_by_path[joint.path]
        original = _base_name(joint.name)
        mapped = _fit_name(joint.name)
        if (original == "Toe" and "Ball" in explicit_names
                and "Toes" not in explicit_names):
            ancestor = joint.parent
            while ancestor in by_path:
                if _base_name(by_path[ancestor].name) == "Ball":
                    return ("Toe" if "ToesEnd" in explicit_names
                            else "ToesEnd")
                ancestor = by_path[ancestor].parent
        if (original in optional_aliases and mapped in explicit_names):
            return original
        return mapped

    def mapped_parent_name(joint: SourceSkeletonJoint) -> str | None:
        if joint.path in left_canonical_paths:
            leaf = joint.name.rsplit(":", 1)[-1]
            return mapped_name(right_by_leaf[leaf[:-2] + "_R"])
        mapped = mapped_name(joint)
        if mapped is not None:
            return mapped
        leaf = joint.name.rsplit(":", 1)[-1]
        if leaf.endswith("_L"):
            counterpart = right_by_leaf.get(leaf[:-2] + "_R")
            if counterpart is not None:
                return mapped_name(counterpart)
            alias = _fit_name(leaf[:-2] + "_R")
            if alias in by_name:
                return alias
        return None

    by_name: dict[str, SourceSkeletonJoint] = {}
    for joint in source:
        if left_mirror_branch(joint) and joint.path not in left_authored_paths:
            continue
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

    _add_optional_end_markers(by_name)
    def fit_world_position(joint: SourceSkeletonJoint) -> tuple[float, float, float]:
        position = joint.world_position
        if joint.path not in left_authored_paths:
            return position
        ancestor_path = joint.parent
        while ancestor_path in by_path and ancestor_path in left_authored_paths:
            ancestor_path = by_path[ancestor_path].parent
        if ancestor_path in by_path:
            ancestor = by_path[ancestor_path]
            leaf = ancestor.name.rsplit(":", 1)[-1]
            if leaf.endswith("_R") or ancestor.world_position[0] < -1e-6:
                # Fit inherits its parent's right-side classification.  The
                # Body symmetry pass will flip this authored source back to
                # the requested left-side world position.
                return (-position[0], position[1], position[2])
        return position

    body, body_request = variable_body_source_inputs(
        axis, len(axial_paths), 1.0, False)
    hand, hand_request = variable_body_source_inputs(
        axis, len(axial_paths), 1.0, True)
    def has_standard(name: str) -> bool:
        return (name in by_name
                and by_name[name].path not in left_authored_paths)

    if all(has_standard(spec.name) for spec in hand.joints):
        reference = hand
        request = hand_request
    elif all(has_standard(spec.name) for spec in body.joints):
        # Incomplete or non-five-finger hands are ordinary Fit branches in
        # the MEL build. The common torso/body template stays authoritative;
        # present digits join the extra-branch path below.
        reference = body
        request = body_request
    else:
        missing = [spec.name for spec in body.joints
                   if not has_standard(spec.name)]
        raise FitSkeletonValidationError(
            "来源骨架缺少标准身体关节：" + "、".join(missing))

    optional_foot = (("Heel", "Ankle", "Foot"),
                     ("FootSideInner", "Toes", "Other"),
                     ("FootSideOuter", "Toes", "Other"),
                     ("BigToe", "Toes", "BigToe"),
                     ("PinkyToe", "Toes", "PinkyToe"))
    present_foot = tuple(FitJointSpec(
        name, parent, (0.0, 0.0, 0.0), JointLabel.parse(label))
        for name, parent, label in optional_foot if has_standard(name))
    if present_foot:
        reference = FitTemplateSpec(
            reference.name, reference.joints + present_foot)

    source_by_path = {joint.path: joint for joint in source}
    canonical_names = {spec.name for spec in reference.joints}
    for joint in source:
        mapped = mapped_name(joint)
        if (mapped is not None and mapped not in canonical_names
                and (not left_mirror_branch(joint)
                     or joint.path in left_authored_paths)
                and by_name[mapped].path != joint.path):
            raise FitSkeletonValidationError(
                "附加来源关节映射到相同 Fit 名称：" + mapped)
    canonical_paths = {by_name[name].path for name in canonical_names
                       if by_name[name].path in source_by_path}
    left_canonical_paths = {
        joint.path for joint in source
        if left_mirror_branch(joint)
        and joint.name.rsplit(":", 1)[-1].endswith("_L")
        and (counterpart := right_by_leaf.get(
            joint.name.rsplit(":", 1)[-1][:-2] + "_R")) is not None
        and mapped_name(counterpart) in canonical_names}
    source_only_intermediates = tuple(sorted(
        joint.path for name, joint in by_name.items()
        if name not in canonical_names
        and joint.path in source_by_path
        and any(path.startswith(joint.path + "|")
                for path in (left_canonical_paths if
                             joint.path in left_authored_paths else
                             canonical_paths))))
    # Keep side branches such as tails and props. A helper inserted between
    # two canonical limb/spine joints cannot be made a sibling without
    # changing the source hierarchy; the current canonical solver contracts
    # still collapse those intermediary helpers as they did before.
    extra_specs = []
    extra_rows = sorted(((name, joint) for name, joint in by_name.items()
                         if name not in canonical_names
                         and joint.path in source_by_path
                         and (not left_mirror_branch(joint)
                              or joint.path in left_authored_paths)
                         and joint.path not in left_canonical_paths
                         and joint.path not in source_only_intermediates),
                        key=lambda row: (row[1].path.count("|"),
                                         row[1].parent or "",
                                         row[1].sibling_index,
                                         row[1].path))
    available_names = set(canonical_names)
    for name, joint in extra_rows:
        parent_path = joint.parent
        parent_name = None
        while parent_path in source_by_path:
            candidate = mapped_parent_name(source_by_path[parent_path])
            if candidate in available_names:
                parent_name = candidate
                break
            parent_path = source_by_path[parent_path].parent
        if parent_name is None:
            raise FitSkeletonValidationError(
                "附加来源关节无法连接到 Fit 主链：" + joint.name)
        if (by_name[parent_name].path != parent_path
                and not left_mirror_branch(source_by_path[parent_path])):
            raise FitSkeletonValidationError(
                "附加来源关节的父关节映射不唯一：" + joint.name)
        parent_position = fit_world_position(by_name[parent_name])
        position = tuple(value - parent for value, parent in zip(
            fit_world_position(joint), parent_position))
        extra_specs.append(FitJointSpec(
            name, parent_name, position,
            joint.label or JointLabel.parse("Other")))
        available_names.add(name)
    included_left = {joint.path for _, joint in extra_rows}
    affected_left = {
        joint.path for joint in source
        if left_mirror_branch(joint)
        and any(joint.path == root_path
                or joint.path.startswith(root_path + "|")
                for root_path in unpaired_left_roots)}
    uncovered_left = (affected_left - included_left
                      - left_canonical_paths
                      - set(source_only_intermediates))
    source_only_left_branches = tuple(sorted(
        path for path in uncovered_left
        if not any(path.startswith(parent + "|")
                   for parent in uncovered_left)))
    if extra_specs:
        reference = FitTemplateSpec(
            reference.name, reference.joints + tuple(extra_specs))
        oriented_extra = tuple(
            spec.name for spec in extra_specs
            if any(child.parent == spec.name for child in extra_specs))
        if oriented_extra:
            request = replace(
                request, joints=request.joints + oriented_extra)
    reference_names = {spec.name for spec in reference.joints}
    reference_parents = {spec.name: spec.parent for spec in reference.joints}

    def source_no_flip(name: str | None) -> bool:
        if name is None:
            return False
        candidate = by_name[name]
        if candidate.effective_no_flip is not None:
            if type(candidate.effective_no_flip) is not bool:
                raise FitSkeletonValidationError(
                    "来源 noFlip 有效值无效：" + candidate.name)
            return candidate.effective_no_flip
        local = (isinstance(candidate.additional_fit_edits, tuple)
                 and any(isinstance(edit, FitJointFieldEdit)
                         and edit.field is FitJointField.NO_FLIP
                         and edit.value is True
                         for edit in candidate.additional_fit_edits))
        return local or source_no_flip(reference_parents[name])

    specs = []
    part_metadata = []
    deform_profiles = []
    rotation_orders = []
    skin_disabled = []
    for reference_joint in reference.joints:
        joint = by_name[reference_joint.name]
        source_no_flip(reference_joint.name)
        if (joint.effective_skin_enabled is not None
                and type(joint.effective_skin_enabled) is not bool):
            raise FitSkeletonValidationError(
                "来源 noSkin 有效值无效：" + joint.name)
        if (joint.rotation_order is not None and (
                type(joint.rotation_order) is not int
                or not 0 <= joint.rotation_order <= 5)):
            raise FitSkeletonValidationError(
                "来源骨架旋转顺序无效：" + joint.name)
        if (joint.deform_profile is not None
                and not isinstance(joint.deform_profile, FitDeformProfile)):
            raise FitSkeletonValidationError(
                "来源骨架体积参数无效：" + joint.name)
        if any(value is not None and (type(value) is not int
                or not 0 <= value <= 10) for value in (
                joint.twist_joints, joint.inbetween_joints)):
            raise FitSkeletonValidationError(
                "来源骨架分段关节数须为 0..10：" + joint.name)
        if (joint.twist_joints is not None
                and joint.inbetween_joints is not None):
            raise FitSkeletonValidationError(
                "来源关节不能同时使用 Twist 和 Inbetween：" + joint.name)
        if joint.untwister is not None and type(joint.untwister) is not bool:
            raise FitSkeletonValidationError("来源 UnTwister 标记无效：" + joint.name)
        default_part = _STANDARD_BIPED_PARTS.get(reference_joint.name)
        use_default_part = (default_part is not None
                            and joint.twist_joints is None
                            and joint.inbetween_joints is None)
        if (joint.untwister and not joint.inbetween_joints
                and not (use_default_part
                         and default_part[0] is FitJointField.INBETWEEN_JOINTS)):
            raise FitSkeletonValidationError(
                "来源 UnTwister 需要 Inbetween 分段：" + joint.name)
        if (not isinstance(joint.additional_fit_edits, tuple)
                or any(not isinstance(edit, FitJointFieldEdit)
                       for edit in joint.additional_fit_edits)):
            raise FitSkeletonValidationError(
                "来源 Fit 元数据格式无效：" + joint.name)
        primary_fields = {
            FitJointField.TWIST_JOINTS,
            FitJointField.INBETWEEN_JOINTS,
            FitJointField.UNTWISTER,
        }
        if any(edit.field in primary_fields
               for edit in joint.additional_fit_edits):
            raise FitSkeletonValidationError(
                "来源 Fit 元数据与分段设置重复：" + joint.name)
        expected_parent = reference_joint.parent
        if joint.path in left_authored_paths and expected_parent is not None:
            parent_source = by_name[expected_parent]
            if (parent_source.effective_skin_enabled is False
                    and joint.effective_skin_enabled is True):
                raise FitSkeletonValidationError(
                    "仅左侧分支无法覆盖父级继承的 noSkin：" + joint.name)
            if (source_no_flip(expected_parent)
                    and joint.effective_no_flip is False):
                raise FitSkeletonValidationError(
                    "仅左侧分支无法覆盖父级继承的 noFlip：" + joint.name)
        parent_path = joint.parent
        ancestry_names = (canonical_names if reference_joint.name in
                          canonical_names else reference_names)
        while parent_path and parent_path in source_by_path:
            parent_name = mapped_parent_name(source_by_path[parent_path])
            if (parent_name in ancestry_names
                    and parent_name != reference_joint.name):
                break
            parent_path = source_by_path[parent_path].parent
        actual_parent = (mapped_parent_name(source_by_path[parent_path])
                         if parent_path in source_by_path else None)
        if actual_parent != expected_parent:
            raise FitSkeletonValidationError(
                f"来源骨架层级不符：{reference_joint.name} 需要父关节 "
                f"{expected_parent or '无'}")
        parent_position = ((0.0, 0.0, 0.0) if expected_parent is None
                           else fit_world_position(by_name[expected_parent]))
        position = tuple(value - parent for value, parent in zip(
            fit_world_position(joint), parent_position))
        specs.append(FitJointSpec(reference_joint.name, expected_parent,
                                  position,
                                  joint.label or reference_joint.label))
        edits = []
        for value, field in (
                (joint.twist_joints, FitJointField.TWIST_JOINTS),
                (joint.inbetween_joints, FitJointField.INBETWEEN_JOINTS),
                (joint.untwister, FitJointField.UNTWISTER)):
            if value is not None:
                edits.append(FitJointFieldEdit(field, value))
        if use_default_part:
            field, value = default_part
            edits.append(FitJointFieldEdit(field, value))
            if (reference_joint.name == "Neck"
                    and joint.untwister is None):
                edits.append(FitJointFieldEdit(FitJointField.UNTWISTER, True))
        edits.extend(joint.additional_fit_edits)
        if joint.path in left_authored_paths:
            # The Fit source remains under its authored parent, but ADV's
            # noMirror/noMirrorLeft pair emits only the left Body branch.
            edits = [edit for edit in edits if edit.field not in (
                FitJointField.NO_MIRROR, FitJointField.NO_MIRROR_LEFT)]
            edits.extend((
                FitJointFieldEdit(FitJointField.NO_MIRROR, True),
                FitJointFieldEdit(FitJointField.NO_MIRROR_LEFT, True)))
        explicit_no_skin = next((edit.value for edit in edits
                                 if edit.field is FitJointField.NO_SKIN), None)
        if (explicit_no_skin is not None
                and joint.effective_skin_enabled is not None
                and explicit_no_skin == joint.effective_skin_enabled):
            raise FitSkeletonValidationError(
                "来源 Skin 状态与 Fit noSkin 属性冲突：" + joint.name)
        inherited_no_flip = source_no_flip(expected_parent)
        local_no_flip = next((edit.value for edit in edits
                              if edit.field is FitJointField.NO_FLIP), None)
        if (joint.effective_no_flip and not inherited_no_flip
                and local_no_flip is not True):
            edits = [edit for edit in edits
                     if edit.field is not FitJointField.NO_FLIP]
            edits.append(FitJointFieldEdit(FitJointField.NO_FLIP, True))
            local_no_flip = True
        if edits:
            try:
                patch = FitJointPatch(tuple(edits))
                metadata = predict_fit_joint_metadata(
                    FitJointMetadata(reference_joint.name), patch)
            except FitJointValidationError as error:
                raise FitSkeletonValidationError(
                    "来源 Fit 元数据无效：" + joint.name + "；" + str(error)) from error
            issues = audit_fit_joint(metadata)
            if issues:
                raise FitSkeletonValidationError(
                    "来源 Fit 元数据冲突：" + joint.name + "；"
                    + "；".join(issue.message for issue in issues))
            part_metadata.append((reference_joint.name, tuple(edits)))
        if joint.deform_profile is not None:
            deform_profiles.append((reference_joint.name,
                                    joint.deform_profile))
        if joint.rotation_order is not None:
            rotation_orders.append((reference_joint.name,
                                    joint.rotation_order))
        if (joint.effective_skin_enabled is False
                and (expected_parent is None
                     or by_name[expected_parent].effective_skin_enabled
                     is not False)):
            skin_disabled.append(reference_joint.name)
    template = FitTemplateSpec("source_skeleton", tuple(specs))
    return SourceSkeletonFitPlan(template, request, len(axial_paths),
                                 tuple(part_metadata),
                                 tuple(deform_profiles),
                                 tuple(rotation_orders),
                                 tuple(skin_disabled),
                                 source_only_intermediates,
                                 source_only_left_branches)


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
            paths = dict(zip((item.name for item in plan.template.joints),
                             result.template.joint_paths))
            for name, edits in plan.part_metadata:
                for edit in edits:
                    joined.apply_fit_joint_edit(paths[name], edit)
                actual = joined.read_fit_joint_metadata(paths[name])
                for edit in edits:
                    value = (actual.local_no_flip
                             if edit.field is FitJointField.NO_FLIP
                             else fit_joint_value(actual, edit.field))
                    if (edit.field not in actual.present_fields
                            or value != edit.value):
                        raise RuntimeError(
                            "来源 Fit 元数据写后复检失败：" + name
                            + "." + edit.field.value)
            for name, profile in plan.deform_profiles:
                joined.write_fit_deform_profile(paths[name], profile)
            for name, order in plan.rotation_orders:
                joined.write_fit_rotation_order(paths[name], order)
            for name in plan.skin_disabled:
                joined.write_fit_no_skin(paths[name])
                if joined.read_fit_skin_enabled(paths[name]):
                    raise RuntimeError("来源 noSkin 写后复检失败：" + name)
        return SourceSkeletonFitResult(len(result.template.joint_paths),
                                       plan.spine_segments,
                                       plan.source_only_intermediates,
                                       plan.source_only_left_branches)
