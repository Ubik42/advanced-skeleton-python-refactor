from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re

from .fit_container import FitUpAxis
from .fit_hierarchy import (
    FitHierarchyNode,
    FitHierarchySnapshot,
    audit_fit_hierarchy,
)
from .fit_settings import FitSkeletonValidationError
from .joint_labels import JointLabel


Vector3 = tuple[float, float, float]
_SAFE_FIT_JOINT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


@dataclass(frozen=True, slots=True)
class FitJointSpec:
    name: str
    parent: str | None
    local_position: Vector3
    label: JointLabel

    def __post_init__(self) -> None:
        if not _SAFE_FIT_JOINT_NAME.fullmatch(self.name):
            raise FitSkeletonValidationError(
                "Fit joint 名称必须以字母开头且只包含字母和数字"
            )
        if self.parent == self.name:
            raise FitSkeletonValidationError("Fit joint 不能以自身为父级")
        if len(self.local_position) != 3 or not all(
            isfinite(float(value)) for value in self.local_position
        ):
            raise FitSkeletonValidationError("Fit joint 本地位置必须是有限三维向量")
        if not isinstance(self.label, JointLabel):
            raise FitSkeletonValidationError("Fit joint 必须提供有效标签")


@dataclass(frozen=True, slots=True)
class FitTemplateSpec:
    name: str
    joints: tuple[FitJointSpec, ...]

    def __post_init__(self) -> None:
        validate_fit_template(self)


@dataclass(frozen=True, slots=True)
class FitTemplateIssue:
    code: str
    message: str
    joint: str | None = None


def minimal_body_fit_template(
    up_axis: FitUpAxis,
    *,
    segment_length: float = 5.0,
) -> FitTemplateSpec:
    if not isinstance(up_axis, FitUpAxis):
        raise FitSkeletonValidationError("基础 Fit 模板 Up Axis 仅支持 Y 或 Z")
    if isinstance(segment_length, bool) or not isinstance(
        segment_length, (int, float)
    ):
        raise FitSkeletonValidationError("基础 Fit 模板段长必须是数值")
    if not isfinite(float(segment_length)) or segment_length <= 0:
        raise FitSkeletonValidationError("基础 Fit 模板段长必须大于 0")

    offset = (0.0, float(segment_length), 0.0)
    if up_axis is FitUpAxis.Z:
        offset = (0.0, 0.0, float(segment_length))
    return FitTemplateSpec(
        name="minimal_body",
        joints=(
            FitJointSpec("Root", None, (0.0, 0.0, 0.0), JointLabel.parse("Root")),
            FitJointSpec("Spine1", "Root", offset, JointLabel.parse("Spine")),
            FitJointSpec("Spine2", "Spine1", offset, JointLabel.parse("Spine")),
        ),
    )


def synthetic_upper_body_fit_template(
    up_axis: FitUpAxis,
    *,
    scale: float = 1.0,
) -> FitTemplateSpec:
    """Return an independently designed T-pose torso and bilateral arm tree."""

    if not isinstance(up_axis, FitUpAxis):
        raise FitSkeletonValidationError("上半身 Fit 模板 Up Axis 仅支持 Y 或 Z")
    if (
        isinstance(scale, bool)
        or not isinstance(scale, (int, float))
        or not isfinite(float(scale))
        or scale <= 0
    ):
        raise FitSkeletonValidationError("上半身 Fit 模板缩放必须是正有限数值")

    unit = float(scale)

    def up(length: float) -> Vector3:
        if up_axis is FitUpAxis.Y:
            return (0.0, length * unit, 0.0)
        return (0.0, 0.0, length * unit)

    def side(length: float) -> Vector3:
        return (length * unit, 0.0, 0.0)

    label = JointLabel.parse
    return FitTemplateSpec(
        name="synthetic_upper_body",
        joints=(
            FitJointSpec("Root", None, (0.0, 0.0, 0.0), label("Root")),
            FitJointSpec("Spine1", "Root", up(3.0), label("Spine")),
            FitJointSpec("Spine2", "Spine1", up(3.0), label("Spine")),
            FitJointSpec("Neck", "Spine2", up(2.0), label("Neck")),
            FitJointSpec("Head", "Neck", up(2.0), label("Head")),
            FitJointSpec("HeadEnd", "Head", up(1.5), label("Head")),
            FitJointSpec(
                "ClavicleLeft", "Spine2", side(1.5), label("Collar")
            ),
            FitJointSpec(
                "ShoulderLeft", "ClavicleLeft", side(1.5), label("Shoulder")
            ),
            FitJointSpec(
                "ElbowLeft", "ShoulderLeft", side(3.0), label("Elbow")
            ),
            FitJointSpec("HandLeft", "ElbowLeft", side(2.5), label("Hand")),
            FitJointSpec(
                "ClavicleRight", "Spine2", side(-1.5), label("Collar")
            ),
            FitJointSpec(
                "ShoulderRight", "ClavicleRight", side(-1.5), label("Shoulder")
            ),
            FitJointSpec(
                "ElbowRight", "ShoulderRight", side(-3.0), label("Elbow")
            ),
            FitJointSpec("HandRight", "ElbowRight", side(-2.5), label("Hand")),
        ),
    )


def validate_fit_template(template: FitTemplateSpec) -> None:
    if not template.name.strip():
        raise FitSkeletonValidationError("Fit 模板名称不能为空")
    if not template.joints:
        raise FitSkeletonValidationError("Fit 模板至少需要一个关节")
    names = tuple(joint.name for joint in template.joints)
    if len(names) != len(set(names)):
        raise FitSkeletonValidationError("Fit 模板关节名称不能重复")

    roots = tuple(joint for joint in template.joints if joint.parent is None)
    if len(roots) != 1:
        raise FitSkeletonValidationError("Fit 模板必须有且只有一个根关节")
    if roots[0].name != "Root":
        raise FitSkeletonValidationError("Fit 模板根关节必须命名为 Root")
    if any(abs(value) > 1e-8 for value in roots[0].local_position):
        raise FitSkeletonValidationError("Fit 模板根关节必须位于容器原点")

    by_name = {joint.name: joint for joint in template.joints}
    for joint in template.joints:
        if joint.parent is not None and joint.parent not in by_name:
            raise FitSkeletonValidationError(
                f"Fit 模板父关节不存在：{joint.name} -> {joint.parent}"
            )
    ordered_fit_joints(template)


def ordered_fit_joints(template: FitTemplateSpec) -> tuple[FitJointSpec, ...]:
    by_name = {joint.name: joint for joint in template.joints}
    ordered: list[FitJointSpec] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise FitSkeletonValidationError("Fit 模板父链包含循环")
        visiting.add(name)
        parent = by_name[name].parent
        if parent in by_name:
            visit(parent)
        visiting.remove(name)
        visited.add(name)
        ordered.append(by_name[name])

    for joint in template.joints:
        visit(joint.name)
    return tuple(ordered)


def predict_fit_template_hierarchy(
    template: FitTemplateSpec,
    container_path: str,
) -> FitHierarchySnapshot:
    if not container_path.startswith("|") or container_path.endswith("|"):
        raise FitSkeletonValidationError("Fit 模板预测需要根级容器完整路径")
    paths: dict[str, str] = {}
    world_positions: dict[str, Vector3] = {}
    nodes: list[FitHierarchyNode] = []
    for spec in ordered_fit_joints(template):
        parent_path = container_path
        parent_world = (0.0, 0.0, 0.0)
        if spec.parent is not None:
            parent_path = paths[spec.parent]
            parent_world = world_positions[spec.parent]
        path = f"{parent_path}|{spec.name}"
        world: Vector3 = (
            parent_world[0] + spec.local_position[0],
            parent_world[1] + spec.local_position[1],
            parent_world[2] + spec.local_position[2],
        )
        paths[spec.name] = path
        world_positions[spec.name] = world
        nodes.append(
            FitHierarchyNode(
                path=path,
                short_name=spec.name,
                dag_parent=parent_path,
                local_position=spec.local_position,
                world_position=world,
            )
        )
    return FitHierarchySnapshot(container_path, tuple(nodes))


def audit_fit_template_snapshot(
    template: FitTemplateSpec,
    snapshot: FitHierarchySnapshot,
    *,
    tolerance: float = 1e-6,
) -> tuple[FitTemplateIssue, ...]:
    issues = [
        FitTemplateIssue(issue.code, issue.message)
        for issue in audit_fit_hierarchy(snapshot)
    ]
    actual = {node.short_name: node for node in snapshot.joints}
    expected_names = {joint.name for joint in template.joints}
    actual_names = set(actual)
    for name in sorted(expected_names - actual_names):
        issues.append(FitTemplateIssue("missing_joint", "缺少模板关节", name))
    for name in sorted(actual_names - expected_names):
        issues.append(FitTemplateIssue("unexpected_joint", "存在计划外关节", name))

    for spec in template.joints:
        node = actual.get(spec.name)
        if node is None:
            continue
        expected_parent = snapshot.container
        if spec.parent is not None and spec.parent in actual:
            expected_parent = actual[spec.parent].path
        if node.dag_parent != expected_parent:
            issues.append(
                FitTemplateIssue("unexpected_parent", "关节父级与模板不一致", spec.name)
            )
        if any(
            abs(actual_value - expected_value) > tolerance
            for actual_value, expected_value in zip(
                node.local_position,
                spec.local_position,
            )
        ):
            issues.append(
                FitTemplateIssue("unexpected_position", "关节位置与模板不一致", spec.name)
            )
    return tuple(issues)
