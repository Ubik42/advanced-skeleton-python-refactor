from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]


class BodyLimbMechanismRole(str, Enum):
    FK = "fk"
    IK = "ik"


class BodyLimbMechanismValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyLimbMechanismJointSpec:
    role: BodyLimbMechanismRole
    side: FitBuildSide
    source_joint: str
    path: str
    name: str
    parent_path: str
    world_position: Vector3
    world_axes: AxisFrame


@dataclass(frozen=True, slots=True)
class BodyLimbMechanismPlan:
    limb_label: str
    root_path: str
    root_name: str
    joints: tuple[BodyLimbMechanismJointSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbMechanismJointState:
    path: str
    parent_path: str | None
    side: FitBuildSide
    source_joint: str | None
    world_position: Vector3
    world_axes: AxisFrame
    rotation: Vector3


@dataclass(frozen=True, slots=True)
class BodyLimbMechanismSnapshot:
    root_path: str
    joints: tuple[BodyLimbMechanismJointState, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbMechanismIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_limb_mechanisms(
    body: BodySkeletonSnapshot,
    *,
    limb_label: str,
    joint_names: tuple[str, str, str],
) -> BodyLimbMechanismPlan:
    if not limb_label.isalpha() or len(joint_names) != 3 or len(set(joint_names)) != 3 or any(
        not name.isalpha() for name in joint_names
    ):
        raise BodyLimbMechanismValidationError("Limb 机制定义无效")
    by_name = {state.name: state for state in body.joints}
    required = tuple(
        f"{joint}_{suffix}"
        for suffix in ("R", "L")
        for joint in joint_names
    )
    if len(by_name) != len(body.joints) or any(name not in by_name for name in required):
        raise BodyLimbMechanismValidationError(
            f"Body 缺少唯一的双侧 {limb_label} 三关节链"
        )

    root_name = f"AdvPy_{limb_label}Mechanisms"
    root_path = f"|{root_name}"
    specs = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        for role in (BodyLimbMechanismRole.FK, BodyLimbMechanismRole.IK):
            parent_path = root_path
            source_parent = None
            for joint_name in joint_names:
                source = by_name[f"{joint_name}_{suffix}"]
                if source.side is not side:
                    raise BodyLimbMechanismValidationError(
                        f"{source.name} 的 Body side 与名称不一致"
                    )
                if source_parent is not None and source.parent_path != source_parent:
                    raise BodyLimbMechanismValidationError(
                        f"{source.name} 不在预期 {limb_label} 父链上"
                    )
                name = f"AdvPy_{joint_name}{role.value.upper()}Driver_{suffix}"
                path = f"{parent_path}|{name}"
                specs.append(BodyLimbMechanismJointSpec(
                    role,
                    side,
                    source.path,
                    path,
                    name,
                    parent_path,
                    source.world_position,
                    source.world_axes,
                ))
                parent_path = path
                source_parent = source.path
    return BodyLimbMechanismPlan(limb_label, root_path, root_name, tuple(specs))


def audit_body_limb_mechanisms(
    plan: BodyLimbMechanismPlan,
    snapshot: BodyLimbMechanismSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyLimbMechanismIssue, ...]:
    issues = []
    if snapshot.root_path != plan.root_path:
        issues.append(BodyLimbMechanismIssue("mechanism_root_mismatch", f"{plan.limb_label} 机制链根路径不一致"))
    expected = {spec.path: spec for spec in plan.joints}
    actual = {state.path: state for state in snapshot.joints}
    for path in sorted(set(expected) - set(actual)):
        issues.append(BodyLimbMechanismIssue("missing_driver", f"缺少 {plan.limb_label} 驱动关节", path))
    for path in sorted(set(actual) - set(expected)):
        issues.append(BodyLimbMechanismIssue("unexpected_driver", f"存在计划外 {plan.limb_label} 驱动关节", path))
    for path in sorted(set(expected) & set(actual)):
        spec, state = expected[path], actual[path]
        checks = (
            (state.parent_path == spec.parent_path, "driver_parent_mismatch", f"{plan.limb_label} 驱动父链不一致"),
            (state.side is spec.side, "driver_side_mismatch", f"{plan.limb_label} 驱动 side 不一致"),
            (state.source_joint == spec.source_joint, "driver_source_mismatch", f"{plan.limb_label} 驱动来源不一致"),
            (_vector_matches(state.world_position, spec.world_position, tolerance), "driver_position_mismatch", f"{plan.limb_label} 驱动位置不一致"),
            (all(_vector_matches(current, wanted, tolerance) for current, wanted in zip(state.world_axes, spec.world_axes)), "driver_axes_mismatch", f"{plan.limb_label} 驱动世界轴不一致"),
            (_vector_matches(state.rotation, (0.0, 0.0, 0.0), tolerance), "driver_rotation_nonzero", f"{plan.limb_label} 驱动 rotate 未归零"),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyLimbMechanismIssue(code, message, path))
    return tuple(issues)


def _vector_matches(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))
