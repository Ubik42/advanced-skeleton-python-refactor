from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .body_leg_ik import BodyLegIkPlan
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import FitBuildSide


Vector3 = tuple[float, float, float]


class BodyLegFootValidationError(ValueError):
    pass


class BodyLegFootPivotRole(str, Enum):
    HEEL = "heel"
    OUTER = "outer"
    INNER = "inner"
    TOE = "toe"
    BALL = "ball"


@dataclass(frozen=True, slots=True)
class BodyLegFootPivotSpec:
    role: BodyLegFootPivotRole
    name: str
    path: str
    parent_path: str
    world_position: Vector3
    attribute: str
    rotation_axis: str
    source_plug: str
    target_plug: str
    multiplier_name: str | None = None
    multiplier: float = 1.0


@dataclass(frozen=True, slots=True)
class BodyLegFootSideSpec:
    side: FitBuildSide
    ankle_control_path: str
    handle_name: str
    initial_handle_parent_path: str
    pivots: tuple[BodyLegFootPivotSpec, ...]

    @property
    def attributes(self) -> tuple[str, ...]:
        return tuple(pivot.attribute for pivot in self.pivots)

    @property
    def final_handle_parent_path(self) -> str:
        return self.pivots[-1].path


@dataclass(frozen=True, slots=True)
class BodyLegFootPlan:
    sides: tuple[BodyLegFootSideSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyLegFootInputState:
    missing_required_paths: tuple[str, ...] = ()
    name_collisions: tuple[str, ...] = ()
    non_writable_paths: tuple[str, ...] = ()
    existing_attribute_plugs: tuple[str, ...] = ()
    occupied_rotation_plugs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BodyLegFootPivotState:
    role: BodyLegFootPivotRole
    path: str
    parent_path: str | None
    world_position: Vector3
    rotation_source: str | None
    multiplier_input_source: str | None = None
    multiplier_value: float | None = None


@dataclass(frozen=True, slots=True)
class BodyLegFootSideState:
    side: FitBuildSide
    attribute_values: tuple[tuple[str, float], ...]
    pivots: tuple[BodyLegFootPivotState, ...]
    handle_parent_path: str | None


@dataclass(frozen=True, slots=True)
class BodyLegFootSnapshot:
    sides: tuple[BodyLegFootSideState, ...]


@dataclass(frozen=True, slots=True)
class BodyLegFootIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_leg_foot(
    body: BodySkeletonSnapshot,
    ik: BodyLegIkPlan,
) -> BodyLegFootPlan:
    body_by_name = {joint.name: joint for joint in body.joints}
    if len(body_by_name) != len(body.joints):
        raise BodyLegFootValidationError("Body 关节名称必须唯一")

    marker_roles = (
        (BodyLegFootPivotRole.HEEL, "Heel", "heelRoll", "Y", 1.0),
        (BodyLegFootPivotRole.OUTER, "FootSideOuter", "outerBank", "X", 1.0),
        (BodyLegFootPivotRole.INNER, "FootSideInner", "innerBank", "X", -1.0),
        (BodyLegFootPivotRole.TOE, "ToesEnd", "toeRoll", "Y", 1.0),
        (BodyLegFootPivotRole.BALL, "Toes", "ballRoll", "Y", 1.0),
    )
    sides = []
    for limb in ik.limbs:
        suffix = limb.side.value
        required = tuple(f"{marker}_{suffix}" for _, marker, *_ in marker_roles)
        if any(name not in body_by_name for name in required):
            raise BodyLegFootValidationError(
                f"Body 缺少 {suffix} 侧唯一的 Heel/FootSide/Toes 标记"
            )
        if any(body_by_name[name].side is not limb.side for name in required):
            raise BodyLegFootValidationError(f"Foot 标记侧向与名称不一致：{suffix}")

        parent = limb.ankle_control_path
        pivots = []
        for role, marker, attribute, axis, multiplier in marker_roles:
            name = f"AdvPy_Foot{role.value.title()}Pivot_{suffix}"
            path = f"{parent}|{name}"
            multiplier_name = (
                f"AdvPy_FootInnerBankSign_{suffix}"
                if multiplier != 1.0
                else None
            )
            source = (
                f"{multiplier_name}.output"
                if multiplier_name
                else f"{limb.ankle_control_path}.{attribute}"
            )
            pivots.append(BodyLegFootPivotSpec(
                role=role,
                name=name,
                path=path,
                parent_path=parent,
                world_position=body_by_name[f"{marker}_{suffix}"].world_position,
                attribute=attribute,
                rotation_axis=axis,
                source_plug=source,
                target_plug=f"{path}.rotate{axis}",
                multiplier_name=multiplier_name,
                multiplier=multiplier,
            ))
            parent = path
        sides.append(BodyLegFootSideSpec(
            side=limb.side,
            ankle_control_path=limb.ankle_control_path,
            handle_name=limb.handle_name,
            initial_handle_parent_path=limb.ankle_control_path,
            pivots=tuple(pivots),
        ))
    return BodyLegFootPlan(tuple(sides))


def audit_body_leg_foot_input(
    state: BodyLegFootInputState,
) -> tuple[BodyLegFootIssue, ...]:
    issues = []
    groups = (
        (state.missing_required_paths, "missing_foot_input", "Foot 必需输入缺失"),
        (state.name_collisions, "foot_name_collision", "Foot 节点名称冲突"),
        (state.non_writable_paths, "foot_input_locked", "Foot 输入不可写或被引用"),
        (state.existing_attribute_plugs, "foot_attribute_exists", "Foot 控制属性已存在"),
        (state.occupied_rotation_plugs, "foot_rotation_occupied", "Foot 旋转通道已有输入"),
    )
    for subjects, code, message in groups:
        issues.extend(BodyLegFootIssue(code, message, subject) for subject in subjects)
    return tuple(issues)


def audit_body_leg_foot(
    plan: BodyLegFootPlan,
    snapshot: BodyLegFootSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyLegFootIssue, ...]:
    issues = []
    actual = {state.side: state for state in snapshot.sides}
    for spec in plan.sides:
        state = actual.get(spec.side)
        if state is None:
            issues.append(BodyLegFootIssue("missing_foot_side", "缺少 Foot 侧", spec.side.value))
            continue
        expected_attributes = tuple(
            (f"{spec.ankle_control_path}.{attribute}", 0.0)
            for attribute in spec.attributes
        )
        if state.attribute_values != expected_attributes:
            issues.append(BodyLegFootIssue("foot_attributes", "Foot 属性或默认值不一致", spec.side.value))
        pivot_by_role = {pivot.role: pivot for pivot in state.pivots}
        for pivot in spec.pivots:
            actual_pivot = pivot_by_role.get(pivot.role)
            subject = f"{spec.side.value}:{pivot.role.value}"
            if actual_pivot is None:
                issues.append(BodyLegFootIssue("missing_foot_pivot", "缺少 Foot pivot", subject))
                continue
            if actual_pivot.path != pivot.path or actual_pivot.parent_path != pivot.parent_path:
                issues.append(BodyLegFootIssue("foot_pivot_hierarchy", "Foot pivot 层级不一致", subject))
            if not _close(actual_pivot.world_position, pivot.world_position, tolerance):
                issues.append(BodyLegFootIssue("foot_pivot_position", "Foot pivot 位置不一致", subject))
            if actual_pivot.rotation_source != pivot.source_plug:
                issues.append(BodyLegFootIssue("foot_pivot_wiring", "Foot pivot 驱动不一致", subject))
            expected_input = (
                f"{spec.ankle_control_path}.{pivot.attribute}"
                if pivot.multiplier_name else None
            )
            expected_value = pivot.multiplier if pivot.multiplier_name else None
            if (
                actual_pivot.multiplier_input_source != expected_input
                or actual_pivot.multiplier_value != expected_value
            ):
                issues.append(BodyLegFootIssue("foot_multiplier", "Foot 符号节点不一致", subject))
        if state.handle_parent_path != spec.final_handle_parent_path:
            issues.append(BodyLegFootIssue("foot_handle_parent", "Leg IK Handle 未挂到 Ball pivot", spec.side.value))
    return tuple(issues)


def _close(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))
