from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .fit_symmetry import FitBuildSide, FitSymmetryInstance
from .joint_labels import JointLabel


Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class BodyJointSpec:
    source_joint: str
    path: str
    name: str
    parent_path: str | None
    side: FitBuildSide
    world_position: Vector3
    label: JointLabel

    @classmethod
    def from_symmetry(
        cls,
        instance: FitSymmetryInstance,
        label: JointLabel,
    ) -> "BodyJointSpec":
        return cls(
            source_joint=instance.source_joint,
            path=instance.output_path,
            name=instance.output_name,
            parent_path=instance.parent_output_path,
            side=instance.side,
            world_position=instance.world_position,
            label=label,
        )

    def __post_init__(self) -> None:
        expected_path = (
            f"{self.parent_path}|{self.name}"
            if self.parent_path is not None
            else f"|{self.name}"
        )
        if self.path != expected_path:
            raise ValueError("构建关节路径与名称不一致")
        if len(self.world_position) != 3 or not all(
            isfinite(float(value)) for value in self.world_position
        ):
            raise ValueError("构建关节世界位置必须是有限三维向量")


@dataclass(frozen=True, slots=True)
class BodyJointState:
    path: str
    name: str
    parent_path: str | None
    side: FitBuildSide
    world_position: Vector3
    label: JointLabel | None
    joint_orient: Vector3
    rotation: Vector3


@dataclass(frozen=True, slots=True)
class BodySkeletonSnapshot:
    root: str
    joints: tuple[BodyJointState, ...]


@dataclass(frozen=True, slots=True)
class BodySkeletonIssue:
    code: str
    message: str
    joint: str | None = None


def audit_body_skeleton(
    specs: tuple[BodyJointSpec, ...],
    snapshot: BodySkeletonSnapshot,
    *,
    tolerance: float = 1e-5,
) -> tuple[BodySkeletonIssue, ...]:
    issues: list[BodySkeletonIssue] = []
    expected = {spec.path: spec for spec in specs}
    actual = {state.path: state for state in snapshot.joints}
    if len(expected) != len(specs):
        issues.append(BodySkeletonIssue("duplicate_spec_path", "构建规格路径重复"))
    if len(actual) != len(snapshot.joints):
        issues.append(BodySkeletonIssue("duplicate_state_path", "构建快照路径重复"))
    for path in sorted(set(expected) - set(actual)):
        issues.append(BodySkeletonIssue("missing_joint", "缺少构建关节", path))
    for path in sorted(set(actual) - set(expected)):
        issues.append(BodySkeletonIssue("unexpected_joint", "存在计划外构建关节", path))
    for path in sorted(set(expected) & set(actual)):
        spec = expected[path]
        state = actual[path]
        if state.name != spec.name or state.parent_path != spec.parent_path:
            issues.append(BodySkeletonIssue("topology_mismatch", "父子结构不一致", path))
        if state.side is not spec.side:
            issues.append(BodySkeletonIssue("side_mismatch", "关节侧向标签不一致", path))
        if state.label != spec.label:
            issues.append(BodySkeletonIssue("label_mismatch", "关节标签不一致", path))
        if any(
            abs(current - wanted) > tolerance
            for current, wanted in zip(state.world_position, spec.world_position)
        ):
            issues.append(BodySkeletonIssue("position_mismatch", "世界位置不一致", path))
        if any(abs(value) > tolerance for value in state.rotation):
            issues.append(BodySkeletonIssue("nonzero_rotation", "rotate 必须为零", path))
        if any(abs(value) > tolerance for value in state.joint_orient):
            issues.append(
                BodySkeletonIssue("nonzero_joint_orient", "jointOrient 必须为零", path)
            )
    return tuple(issues)
