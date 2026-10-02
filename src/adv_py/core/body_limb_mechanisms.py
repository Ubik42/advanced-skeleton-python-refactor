from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import re

from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide


def body_limb_token_valid(value):
    return isinstance(value,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',value) is not None


def body_limb_sides_valid(sides):
    return (isinstance(sides,tuple) and bool(sides)
            and all(isinstance(side,FitBuildSide) for side in sides)
            and len(sides)==len(set(sides)))


def body_limb_parent_matches(
    parent_path: str | None, previous_body_path: str,
    *, allow_part_parents: bool,
) -> bool:
    if parent_path == previous_body_path:
        return True
    if (not allow_part_parents or parent_path is None
            or not parent_path.startswith(previous_body_path + "|")):
        return False
    intervening = parent_path[len(previous_body_path) + 1:].split("|")
    previous_name = previous_body_path.rsplit("|", 1)[-1]
    stem, side_separator, side = previous_name.rsplit(":", 1)[-1].rpartition("_")
    if not side_separator or side not in ("R", "L", "M"):
        return False
    return bool(intervening) and all(
        item.rsplit(":", 1)[-1] == f"{stem}Part{index}_{side}"
        for index, item in enumerate(intervening, 1))


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
    rotation_order: int | None = None

    def __post_init__(self):
        if self.rotation_order is not None and (type(self.rotation_order) is not int or not 0<=self.rotation_order<=5):
            raise BodyLimbMechanismValidationError('来源四肢机制旋转顺序无效')


@dataclass(frozen=True, slots=True)
class BodyLimbMechanismPlan:
    limb_label: str
    root_path: str
    root_name: str
    joints: tuple[BodyLimbMechanismJointSpec, ...]
    auxiliary_joint_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BodyLimbMechanismJointState:
    path: str
    parent_path: str | None
    side: FitBuildSide
    source_joint: str | None
    world_position: Vector3
    world_axes: AxisFrame
    rotation: Vector3
    rotation_order: int | None = None


@dataclass(frozen=True, slots=True)
class BodyLimbMechanismSnapshot:
    root_path: str
    joints: tuple[BodyLimbMechanismJointState, ...]
    inbetween_source_parts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BodyLimbMechanismIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_limb_mechanisms(
    body: BodySkeletonSnapshot,
    *,
    limb_label: str,
    joint_names: tuple[str, ...],
    allow_part_parents: bool = False,
    sides: tuple[FitBuildSide, ...] = (FitBuildSide.RIGHT,FitBuildSide.LEFT),
) -> BodyLimbMechanismPlan:
    if type(allow_part_parents) is not bool:
        raise BodyLimbMechanismValidationError("Part 父级开关无效")
    if not body_limb_sides_valid(sides) or not body_limb_token_valid(limb_label) or len(joint_names) < 2 or len(set(joint_names)) != len(joint_names) or any(
        not body_limb_token_valid(name)
        for name in joint_names
    ):
        raise BodyLimbMechanismValidationError("Limb 机制定义无效")
    by_name = {state.name: state for state in body.joints}
    required = tuple(
        f"{joint}_{suffix}"
        for suffix in (side.value for side in sides)
        for joint in joint_names
    )
    if len(by_name) != len(body.joints) or any(name not in by_name for name in required):
        raise BodyLimbMechanismValidationError(
            f"Body 缺少唯一的双侧 {limb_label} 机制链"
        )

    root_name = f"AdvPy_{limb_label}Mechanisms"
    root_parent_path = ("|Group|MotionSystem|FKIKSystem"
                        if body.root.startswith("|Group|DeformationSystem|")
                        else "")
    root_path = f"{root_parent_path}|{root_name}"
    specs = []
    for side in sides:
        suffix = side.value
        for role in (BodyLimbMechanismRole.FK, BodyLimbMechanismRole.IK):
            parent_path = root_path
            source_parent = None
            for joint_name in joint_names:
                source = by_name[f"{joint_name}_{suffix}"]
                if source.side is not side:
                    raise BodyLimbMechanismValidationError(
                        f"{source.name} 的 Body side 与名称不一致"
                    )
                if (source_parent is not None
                        and not body_limb_parent_matches(
                            source.parent_path, source_parent,
                            allow_part_parents=allow_part_parents)):
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
    check_initial_pose: bool = True,
) -> tuple[BodyLimbMechanismIssue, ...]:
    issues = []
    if snapshot.root_path != plan.root_path:
        issues.append(BodyLimbMechanismIssue("mechanism_root_mismatch", f"{plan.limb_label} 机制链根路径不一致"))
    expected = {spec.path: spec for spec in plan.joints}
    actual = {state.path: state for state in snapshot.joints}
    auxiliary = set(plan.auxiliary_joint_paths)
    if len(auxiliary) != len(plan.auxiliary_joint_paths) or auxiliary & set(expected):
        issues.append(BodyLimbMechanismIssue(
            "invalid_auxiliary_plan", f"{plan.limb_label} IKX 辅助关节计划重复或冲突"))
    for path in sorted(set(expected) - set(actual)):
        issues.append(BodyLimbMechanismIssue("missing_driver", f"缺少 {plan.limb_label} 驱动关节", path))
    for path in sorted(auxiliary - set(actual)):
        issues.append(BodyLimbMechanismIssue(
            "missing_ikx", f"缺少 {plan.limb_label} IKX 辅助关节", path))
    for path in sorted(set(actual) - set(expected) - auxiliary):
        issues.append(BodyLimbMechanismIssue("unexpected_driver", f"存在计划外 {plan.limb_label} 驱动关节", path))
    for path in sorted(auxiliary & set(actual)):
        state = actual[path]
        if (state.parent_path != path.rsplit("|", 1)[0]
                or state.source_joint is not None):
            issues.append(BodyLimbMechanismIssue(
                "ikx_structure_mismatch", f"{plan.limb_label} IKX 辅助关节层级或来源不一致", path))
    for path in sorted(set(expected) & set(actual)):
        spec, state = expected[path], actual[path]
        checks = (
            (state.parent_path == spec.parent_path, "driver_parent_mismatch", f"{plan.limb_label} 驱动父链不一致"),
            (state.side is spec.side, "driver_side_mismatch", f"{plan.limb_label} 驱动 side 不一致"),
            (state.source_joint == spec.source_joint, "driver_source_mismatch", f"{plan.limb_label} 驱动来源不一致"),
            (spec.rotation_order is None or state.rotation_order==spec.rotation_order,
             'driver_rotation_order_mismatch',f'{plan.limb_label} 驱动旋转顺序不一致'),
        )
        if check_initial_pose:
            checks += (
                (_vector_matches(state.world_position, spec.world_position, tolerance), "driver_position_mismatch", f"{plan.limb_label} 驱动位置不一致"),
                (all(_vector_matches(current, wanted, tolerance) for current, wanted in zip(state.world_axes, spec.world_axes)), "driver_axes_mismatch", f"{plan.limb_label} 驱动世界轴不一致"),
                (_vector_matches(state.rotation, (0.0, 0.0, 0.0), tolerance), "driver_rotation_nonzero", f"{plan.limb_label} 驱动 rotate 未归零"),
            )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyLimbMechanismIssue(code, message, path))
    return tuple(issues)


def recover_body_limb_mechanisms(
    plan: BodyLimbMechanismPlan,
    body: BodySkeletonSnapshot,
    snapshot: BodyLimbMechanismSnapshot,
) -> BodyLimbMechanismPlan:
    """Recover a built limb's IK DAG paths from its owned mechanism joints.

    IKX nodes may only occupy the same ordered Body Part interval that was
    inserted between two adjacent source Body joints. FK drivers stay on the
    original chain. Unknown or detached descendants are rejected.
    """
    if snapshot.root_path != plan.root_path:
        raise BodyLimbMechanismValidationError("机制链根路径与计划不一致")
    actual = {state.path: state for state in snapshot.joints}
    if len(actual) != len(snapshot.joints):
        raise BodyLimbMechanismValidationError("机制关节路径重复")
    inbetween_parts = set(snapshot.inbetween_source_parts)
    if (len(inbetween_parts) != len(snapshot.inbetween_source_parts)
            or any(not path.startswith("|") for path in inbetween_parts)):
        raise BodyLimbMechanismValidationError("Inbetween 来源 Part 标记无效")
    by_name = {}
    for state in snapshot.joints:
        name = state.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if name in by_name:
            raise BodyLimbMechanismValidationError("机制关节名称重复：" + name)
        by_name[name] = state
    body_by_path = {state.path: state for state in body.joints}
    recovered = []
    auxiliary = []
    previous_by_chain = {}
    for spec in plan.joints:
        state = by_name.get(spec.name.rsplit(":", 1)[-1])
        if (state is None or state.side is not spec.side
                or state.source_joint != spec.source_joint
                or state.parent_path is None
                or state.path.rsplit("|", 1)[0] != state.parent_path
                or state.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                != spec.name.rsplit(":", 1)[-1]):
            raise BodyLimbMechanismValidationError(
                "机制关节身份或来源不一致：" + spec.name)
        key = (spec.role, spec.side)
        previous = previous_by_chain.get(key)
        expected_parent = previous.path if previous else (
            spec.parent_path if spec.role is BodyLimbMechanismRole.IK else plan.root_path)
        if previous is None and not (expected_parent==plan.root_path or expected_parent.startswith(plan.root_path+'|')):
            raise BodyLimbMechanismValidationError('机制起点父级不属于本系统：'+spec.name)
        if spec.role is BodyLimbMechanismRole.FK:
            if state.path != spec.path or state.parent_path != expected_parent:
                raise BodyLimbMechanismValidationError(
                    "FK 机制父链不一致：" + spec.name)
        else:
            parent = state.parent_path
            if parent == expected_parent:
                markers = ()
            elif parent.startswith(expected_parent + "|"):
                markers = tuple(parent[len(expected_parent) + 1:].split("|"))
            else:
                raise BodyLimbMechanismValidationError(
                    "IK 机制父链不一致：" + spec.name)
            if previous is None and markers:
                raise BodyLimbMechanismValidationError(
                    "IK 根关节前存在计划外节点：" + spec.name)
            if previous is not None:
                source = body_by_path.get(spec.source_joint)
                if (source is None or source.parent_path is None
                        or not source.parent_path.startswith(
                            previous.source_joint + "|")):
                    part_paths = ()
                else:
                    parent_path = previous.source_joint
                    parts = []
                    for name in source.parent_path[
                            len(parent_path) + 1:].split("|"):
                        parent_path += "|" + name
                        parts.append(parent_path)
                    part_paths = tuple(parts)
                allowed = tuple(
                    "AdvPy_" + path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                    + "_InbetweenIKX" for path in part_paths)
                normalized_markers = tuple(
                    name.rsplit(":", 1)[-1] for name in markers)
                positions = [allowed.index(name) for name in normalized_markers
                             if name in allowed]
                if (len(positions) != len(markers)
                        or positions != sorted(set(positions))):
                    raise BodyLimbMechanismValidationError(
                        "IKX 不属于有序 Body Part 父链：" + spec.name)
                required = tuple(
                    name for path, name in zip(part_paths, allowed)
                    if path in inbetween_parts)
                if normalized_markers != required:
                    raise BodyLimbMechanismValidationError(
                        "Inbetween IKX 数量或顺序与 Body Part 标记不一致："
                        + spec.name)
            marker_parent = expected_parent
            for name in markers:
                marker_path = marker_parent + "|" + name
                marker = actual.get(marker_path)
                if (marker is None or marker.parent_path != marker_parent
                        or marker.source_joint is not None):
                    raise BodyLimbMechanismValidationError(
                        "IKX 辅助关节状态不一致：" + marker_path)
                auxiliary.append(marker_path)
                marker_parent = marker_path
        recovered.append(replace(spec, path=state.path,
                                 parent_path=state.parent_path))
        previous_by_chain[key] = recovered[-1]
    if set(actual) != {spec.path for spec in recovered} | set(auxiliary):
        raise BodyLimbMechanismValidationError("机制链含有计划外关节")
    return replace(plan, joints=tuple(recovered),
                   auxiliary_joint_paths=tuple(auxiliary))


def expanded_ik_solver_chain(
    plan: BodyLimbMechanismPlan,
    drivers: tuple[str, ...],
) -> tuple[str, ...]:
    """Include owned IKX joints between ordinary driver joints."""
    if not drivers:
        raise BodyLimbMechanismValidationError("IK 求解链为空")
    auxiliary = set(plan.auxiliary_joint_paths)
    expanded = [drivers[0]]
    for start, end in zip(drivers, drivers[1:]):
        if not end.startswith(start + "|"):
            raise BodyLimbMechanismValidationError("IK 求解关节父链不连续")
        parent = start
        for name in end[len(start) + 1:].split("|")[:-1]:
            parent += "|" + name
            if parent not in auxiliary:
                raise BodyLimbMechanismValidationError(
                    "IK 求解链包含未登记的 IKX 关节：" + parent)
            expanded.append(parent)
        expanded.append(end)
    return tuple(expanded)


def _vector_matches(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))
