from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]


class BodyArmMechanismRole(str, Enum):
    FK = "fk"
    IK = "ik"


class BodyArmMechanismValidationError(ValueError):
    """Raised when bilateral arm driver chains cannot be planned safely."""


@dataclass(frozen=True, slots=True)
class BodyArmMechanismJointSpec:
    role: BodyArmMechanismRole
    side: FitBuildSide
    source_joint: str
    path: str
    name: str
    parent_path: str
    world_position: Vector3
    world_axes: AxisFrame


@dataclass(frozen=True, slots=True)
class BodyArmMechanismPlan:
    root_path: str
    root_name: str
    joints: tuple[BodyArmMechanismJointSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyArmMechanismJointState:
    path: str
    parent_path: str | None
    side: FitBuildSide
    source_joint: str | None
    world_position: Vector3
    world_axes: AxisFrame
    rotation: Vector3


@dataclass(frozen=True, slots=True)
class BodyArmMechanismSnapshot:
    root_path: str
    joints: tuple[BodyArmMechanismJointState, ...]


@dataclass(frozen=True, slots=True)
class BodyArmMechanismIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_arm_mechanisms(
    body: BodySkeletonSnapshot,
) -> BodyArmMechanismPlan:
    by_name = {state.name: state for state in body.joints}
    required = tuple(
        f"{joint}_{side}"
        for side in ("R", "L")
        for joint in ("Shoulder", "Elbow", "Wrist")
    )
    if len(by_name) != len(body.joints) or any(name not in by_name for name in required):
        raise BodyArmMechanismValidationError(
            "Body 缺少唯一的双臂 Shoulder/Elbow/Wrist"
        )

    root_name = "AdvPy_ArmMechanisms"
    root_path = f"|{root_name}"
    specs: list[BodyArmMechanismJointSpec] = []
    for side_name, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        source_parent = None
        for role in (BodyArmMechanismRole.FK, BodyArmMechanismRole.IK):
            parent_path = root_path
            source_parent = None
            for joint_name in ("Shoulder", "Elbow", "Wrist"):
                source = by_name[f"{joint_name}_{side_name}"]
                if source.side is not side:
                    raise BodyArmMechanismValidationError(
                        f"{source.name} 的 Body side 与名称不一致"
                    )
                if source_parent is not None and source.parent_path != source_parent:
                    raise BodyArmMechanismValidationError(
                        f"{source.name} 不在预期手臂父链上"
                    )
                role_name = role.value.upper()
                name = f"AdvPy_{joint_name}{role_name}Driver_{side_name}"
                path = f"{parent_path}|{name}"
                specs.append(
                    BodyArmMechanismJointSpec(
                        role=role,
                        side=side,
                        source_joint=source.path,
                        path=path,
                        name=name,
                        parent_path=parent_path,
                        world_position=source.world_position,
                        world_axes=source.world_axes,
                    )
                )
                parent_path = path
                source_parent = source.path
    return BodyArmMechanismPlan(root_path, root_name, tuple(specs))


def audit_body_arm_mechanisms(
    plan: BodyArmMechanismPlan,
    snapshot: BodyArmMechanismSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyArmMechanismIssue, ...]:
    issues: list[BodyArmMechanismIssue] = []
    if snapshot.root_path != plan.root_path:
        issues.append(
            BodyArmMechanismIssue(
                "mechanism_root_mismatch",
                "Arm 机制链根路径不一致",
            )
        )
    expected = {spec.path: spec for spec in plan.joints}
    actual = {state.path: state for state in snapshot.joints}
    for path in sorted(set(expected) - set(actual)):
        issues.append(BodyArmMechanismIssue("missing_driver", "缺少 Arm 驱动关节", path))
    for path in sorted(set(actual) - set(expected)):
        issues.append(
            BodyArmMechanismIssue("unexpected_driver", "存在计划外 Arm 驱动关节", path)
        )
    for path in sorted(set(expected) & set(actual)):
        spec = expected[path]
        state = actual[path]
        if state.parent_path != spec.parent_path:
            issues.append(
                BodyArmMechanismIssue("driver_parent_mismatch", "Arm 驱动父链不一致", path)
            )
        if state.side is not spec.side:
            issues.append(
                BodyArmMechanismIssue("driver_side_mismatch", "Arm 驱动 side 不一致", path)
            )
        if state.source_joint != spec.source_joint:
            issues.append(
                BodyArmMechanismIssue("driver_source_mismatch", "Arm 驱动来源不一致", path)
            )
        if not _vector_matches(state.world_position, spec.world_position, tolerance):
            issues.append(
                BodyArmMechanismIssue("driver_position_mismatch", "Arm 驱动位置不一致", path)
            )
        if any(
            not _vector_matches(current, wanted, tolerance)
            for current, wanted in zip(state.world_axes, spec.world_axes)
        ):
            issues.append(
                BodyArmMechanismIssue("driver_axes_mismatch", "Arm 驱动世界轴不一致", path)
            )
        if not _vector_matches(state.rotation, (0.0, 0.0, 0.0), tolerance):
            issues.append(
                BodyArmMechanismIssue("driver_rotation_nonzero", "Arm 驱动 rotate 未归零", path)
            )
    return tuple(issues)


def _vector_matches(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))
