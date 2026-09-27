from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

from .body_controller_layers import (
    BodyExtraControllerState, audit_body_extra_controller,
)
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]


class BodyLimbControlValidationError(ValueError):
    """Raised when Body limb controls cannot be planned safely."""


@dataclass(frozen=True, slots=True)
class BodyLimbFkControlSpec:
    side: FitBuildSide
    driven_joint: str
    offset_path: str
    offset_name: str
    control_path: str
    control_name: str
    parent_path: str
    constraint_name: str
    world_position: Vector3
    world_axes: AxisFrame
    radius: float
    rotate_order: int = 0
    control_parent_path: str | None = None
    source_override_path: str | None = None
    sub_control_path: str | None = None
    sub_control_name: str | None = None
    extra_path: str | None = None
    extra_name: str | None = None
    extra_curve: bool = False


@dataclass(frozen=True, slots=True)
class BodyLimbFkControlPlan:
    root_path: str
    root_name: str
    controls: tuple[BodyLimbFkControlSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbFkControlState:
    offset_path: str
    offset_parent_path: str | None
    control_path: str
    control_parent_path: str | None
    constraint_name: str
    source_control: str | None
    driven_joint: str | None
    world_position: Vector3
    world_axes: AxisFrame
    local_translation: Vector3
    local_rotation: Vector3
    shape_type: str | None
    sub_control_path: str | None = None
    sub_parent_path: str | None = None
    sub_shape_type: str | None = None
    sub_visibility_source: str | None = None
    sub_color: int | None = None
    sub_shape_scale: float | None = None
    extra: BodyExtraControllerState | None = None


@dataclass(frozen=True, slots=True)
class BodyLimbFkControlSnapshot:
    root_path: str
    controls: tuple[BodyLimbFkControlState, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbControlIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_limb_fk_controls(
    body: BodySkeletonSnapshot,
    *,
    limb_label: str,
    joint_names: tuple[str, ...],
    radius: float = 1.5,
    driven_joint_by_source: Mapping[str, str] | None = None,
    sub_controllers: bool = False,
    extra_controllers: bool = False,
) -> BodyLimbFkControlPlan:
    if type(sub_controllers) is not bool or type(extra_controllers) is not bool:
        raise BodyLimbControlValidationError("FK 控制器开关必须是布尔值")
    if (
        not limb_label.isalpha()
        or len(joint_names) < 2
        or len(set(joint_names)) != len(joint_names)
        or any(not name.isalpha() for name in joint_names)
    ):
        raise BodyLimbControlValidationError("Limb FK 控制定义无效")
    if (
        isinstance(radius, bool)
        or not isinstance(radius, (int, float))
        or not isfinite(float(radius))
        or radius <= 0
    ):
        raise BodyLimbControlValidationError(
            f"{limb_label} FK 控制半径必须是正有限数值"
        )

    by_name = {state.name: state for state in body.joints}
    required_names = tuple(
        f"{joint}_{side}"
        for side in ("R", "L")
        for joint in joint_names
    )
    if len(by_name) != len(body.joints) or any(
        name not in by_name for name in required_names
    ):
        raise BodyLimbControlValidationError(
            f"Body 缺少唯一的双侧 {limb_label} FK 控制链"
        )
    if driven_joint_by_source is not None:
        source_paths = tuple(by_name[name].path for name in required_names)
        missing = tuple(
            path for path in source_paths if path not in driven_joint_by_source
        )
        targets = tuple(
            driven_joint_by_source[path]
            for path in source_paths
            if path in driven_joint_by_source
        )
        if missing:
            raise BodyLimbControlValidationError(
                f"{limb_label} FK 显式驱动映射缺少来源关节"
            )
        if any(
            not isinstance(path, str) or not path.startswith("|")
            for path in targets
        ):
            raise BodyLimbControlValidationError(
                f"{limb_label} FK 显式驱动目标必须是完整 DAG 路径"
            )
        if len(set(targets)) != len(targets):
            raise BodyLimbControlValidationError(
                f"{limb_label} FK 显式驱动目标不能重复"
            )

    root_name = f"AdvPy_{limb_label}FKControls"
    root_path = f"|{root_name}"
    controls: list[BodyLimbFkControlSpec] = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        parent_path = root_path
        previous_joint = None
        for joint_name in joint_names:
            state = by_name[f"{joint_name}_{suffix}"]
            if state.side is not side:
                raise BodyLimbControlValidationError(
                    f"{state.name} 的 Body side 与名称不一致"
                )
            if previous_joint is not None and state.parent_path != previous_joint:
                raise BodyLimbControlValidationError(
                    f"{state.name} 不在预期 {limb_label} FK 父链上"
                )
            offset_name = f"AdvPy_{joint_name}FKOffset_{suffix}"
            extra_name = f"AdvPy_{joint_name}FKExtra_{suffix}"
            control_name = f"AdvPy_{joint_name}FK_{suffix}"
            offset_path = f"{parent_path}|{offset_name}"
            extra_path = f"{offset_path}|{extra_name}"
            control_path = f"{extra_path}|{control_name}"
            controls.append(BodyLimbFkControlSpec(
                side=side,
                driven_joint=(
                    driven_joint_by_source[state.path]
                    if driven_joint_by_source is not None
                    else state.path
                ),
                offset_path=offset_path,
                offset_name=offset_name,
                control_path=control_path,
                control_name=control_name,
                parent_path=parent_path,
                constraint_name=f"AdvPy_{joint_name}FKOrient_{suffix}",
                world_position=state.world_position,
                world_axes=state.world_axes,
                radius=float(radius),
                rotate_order={"Shoulder": 5, "Elbow": 5, "Wrist": 5,
                              "Hip": 2, "Knee": 2, "Ankle": 3,
                              "Toes": 5}.get(joint_name, 0),
                sub_control_path=(
                    control_path + "|AdvPy_" + joint_name + "FKSub_" + suffix
                    if sub_controllers else None
                ),
                sub_control_name=(
                    "AdvPy_" + joint_name + "FKSub_" + suffix
                    if sub_controllers else None
                ),
                extra_path=extra_path,
                extra_name=extra_name,
                extra_curve=extra_controllers,
            ))
            parent_path = control_path
            previous_joint = state.path
    return BodyLimbFkControlPlan(root_path, root_name, tuple(controls))


def audit_body_limb_fk_controls(
    plan: BodyLimbFkControlPlan,
    snapshot: BodyLimbFkControlSnapshot,
    *,
    limb_label: str,
    tolerance: float = 1e-4,
    check_initial_pose: bool = True,
) -> tuple[BodyLimbControlIssue, ...]:
    issues: list[BodyLimbControlIssue] = []
    if snapshot.root_path != plan.root_path:
        issues.append(BodyLimbControlIssue(
            "control_root_mismatch", f"{limb_label} FK 控制根路径不一致"
        ))
    expected = {spec.control_path: spec for spec in plan.controls}
    actual = {state.control_path: state for state in snapshot.controls}
    for path in sorted(set(expected) - set(actual)):
        issues.append(BodyLimbControlIssue(
            "missing_control", f"缺少 {limb_label} FK 控制", path
        ))
    for path in sorted(set(actual) - set(expected)):
        issues.append(BodyLimbControlIssue(
            "unexpected_control", f"存在计划外 {limb_label} FK 控制", path
        ))
    for path in sorted(set(expected) & set(actual)):
        spec, state = expected[path], actual[path]
        if (
            state.offset_path != spec.offset_path
            or state.offset_parent_path != spec.parent_path
            or state.control_parent_path
            != (spec.extra_path or spec.control_parent_path or spec.offset_path)
        ):
            issues.append(BodyLimbControlIssue(
                "control_hierarchy_mismatch", "FK 控制父链不一致", path
            ))
        if state.constraint_name != spec.constraint_name:
            issues.append(BodyLimbControlIssue(
                "constraint_name_mismatch", "FK 约束名称不一致", path
            ))
        if (
            state.source_control
            != (spec.source_override_path or spec.control_path)
            or state.driven_joint != spec.driven_joint
        ):
            issues.append(BodyLimbControlIssue(
                "constraint_wiring_mismatch", "FK 约束连接不一致", path
            ))
        if state.shape_type != "nurbsCurve":
            issues.append(BodyLimbControlIssue(
                "control_shape_mismatch", "FK 控制缺少 NURBS 曲线", path
            ))
        if spec.sub_control_path is None:
            if state.sub_control_path is not None:
                issues.append(BodyLimbControlIssue(
                    "unexpected_sub_control", "存在计划外 FK Sub 控制器", path))
        elif (state.sub_control_path != spec.sub_control_path
              or state.sub_parent_path != spec.control_path
              or state.sub_shape_type != "nurbsCurve"
              or state.sub_visibility_source
              != spec.control_path + ".subControl"
              or state.sub_color != 30
              or state.sub_shape_scale is None
              or abs(state.sub_shape_scale - 0.9) > tolerance):
            issues.append(BodyLimbControlIssue(
                "sub_control_mismatch", "FK Sub 控制器与计划不一致", path))
        if spec.extra_path is not None:
            for message in audit_body_extra_controller(
                    spec.offset_path, spec.control_path, spec.extra_path,
                    state.extra, extra_curve=spec.extra_curve,
                    tolerance=tolerance):
                issues.append(BodyLimbControlIssue(
                    "extra_control_mismatch", message, path))
        if check_initial_pose:
            if not _vector_matches(
                state.world_position, spec.world_position, tolerance
            ):
                issues.append(BodyLimbControlIssue(
                    "control_position_mismatch", "FK 控制世界位置不一致", path
                ))
            if any(
                not _vector_matches(current, wanted, tolerance)
                for current, wanted in zip(state.world_axes, spec.world_axes)
            ):
                issues.append(BodyLimbControlIssue(
                    "control_axes_mismatch", "FK 控制世界轴不一致", path
                ))
            if not _vector_matches(
                state.local_translation, (0.0, 0.0, 0.0), tolerance
            ):
                issues.append(BodyLimbControlIssue(
                    "nonzero_control_translation", "FK 控制 translate 未归零", path
                ))
            if not _vector_matches(
                state.local_rotation, (0.0, 0.0, 0.0), tolerance
            ):
                issues.append(BodyLimbControlIssue(
                    "nonzero_control_rotation", "FK 控制 rotate 未归零", path
                ))
    return tuple(issues)


def _vector_matches(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))
