from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .body_hand_fit import BODY_HAND_DIGITS, BODY_HAND_SEGMENTS
from .body_limb_controls import (
    BodyLimbControlIssue,
    BodyLimbFkControlPlan,
    BodyLimbFkControlSnapshot,
    BodyLimbFkControlSpec,
    BodyLimbFkControlState,
    audit_body_limb_fk_controls,
)
from .body_skeleton import BodySkeletonSnapshot
from .fit_hierarchy import TRANSLATION_AXES
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]


class BodyHandControlValidationError(ValueError):
    """Raised when bilateral five-digit controls cannot be planned safely."""


BodyHandFkControlSpec = BodyLimbFkControlSpec
BodyHandFkControlState = BodyLimbFkControlState
BodyHandControlIssue = BodyLimbControlIssue


@dataclass(frozen=True, slots=True)
class BodyHandFkRootSpec:
    side: FitBuildSide
    wrist_joint: str
    path: str
    name: str
    parent_path: str
    world_position: Vector3
    world_axes: AxisFrame


@dataclass(frozen=True, slots=True)
class BodyHandFkControlPlan:
    roots: tuple[BodyHandFkRootSpec, ...]
    controls: tuple[BodyHandFkControlSpec, ...]

    @property
    def node_names(self) -> tuple[str, ...]:
        values = [root.name for root in self.roots]
        for control in self.controls:
            values.extend((
                control.offset_name,
                control.control_name,
                control.constraint_name,
            ))
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyHandFkRootState:
    path: str
    parent_path: str | None
    world_position: Vector3
    world_axes: AxisFrame
    local_translation: Vector3
    local_rotation: Vector3
    local_scale: Vector3


@dataclass(frozen=True, slots=True)
class BodyHandFkControlSnapshot:
    roots: tuple[BodyHandFkRootState, ...]
    controls: tuple[BodyHandFkControlState, ...]


@dataclass(frozen=True, slots=True)
class BodyHandFkJointInputState:
    joint: str
    writable_rotation_axes: frozenset[str]
    rotation_sources: tuple[str | None, str | None, str | None]


@dataclass(frozen=True, slots=True)
class BodyHandFkInputSnapshot:
    joints: tuple[BodyHandFkJointInputState, ...]


def plan_body_hand_fk_controls(
    body: BodySkeletonSnapshot,
    *,
    radius: float = 0.3,
) -> BodyHandFkControlPlan:
    if (
        isinstance(radius, bool)
        or not isinstance(radius, (int, float))
        or not isfinite(float(radius))
        or float(radius) <= 0.0
    ):
        raise BodyHandControlValidationError(
            "Hand FK 控制半径必须是正有限数值"
        )
    by_name = {joint.name: joint for joint in body.joints}
    if len(by_name) != len(body.joints):
        raise BodyHandControlValidationError("Body joint 名称不唯一")

    roots = []
    controls = []
    radius_factors = (1.0, 0.82, 0.68)
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        wrist = by_name.get(f"Wrist_{suffix}")
        if wrist is None or wrist.side is not side:
            raise BodyHandControlValidationError(
                f"Body 缺少唯一的 Wrist_{suffix}"
            )
        root_name = f"AdvPy_HandFKControls_{suffix}"
        root_path = f"{wrist.path}|{root_name}"
        roots.append(BodyHandFkRootSpec(
            side=side,
            wrist_joint=wrist.path,
            path=root_path,
            name=root_name,
            parent_path=wrist.path,
            world_position=wrist.world_position,
            world_axes=wrist.world_axes,
        ))

        for digit in BODY_HAND_DIGITS:
            states = []
            previous_path = wrist.path
            for segment in BODY_HAND_SEGMENTS:
                state = by_name.get(f"{digit.value}{segment}_{suffix}")
                if state is None:
                    raise BodyHandControlValidationError(
                        f"Body 缺少 {digit.value}{segment}_{suffix}"
                    )
                if state.side is not side or state.parent_path != previous_path:
                    raise BodyHandControlValidationError(
                        f"{state.name} 不在预期 Hand 父链上"
                    )
                states.append(state)
                previous_path = state.path

            parent_path = root_path
            for index, state in enumerate(states[:-1], start=1):
                offset_name = (
                    f"AdvPy_{digit.value}{index}FKOffset_{suffix}"
                )
                control_name = f"AdvPy_{digit.value}{index}FK_{suffix}"
                offset_path = f"{parent_path}|{offset_name}"
                control_path = f"{offset_path}|{control_name}"
                controls.append(BodyHandFkControlSpec(
                    side=side,
                    driven_joint=state.path,
                    offset_path=offset_path,
                    offset_name=offset_name,
                    control_path=control_path,
                    control_name=control_name,
                    parent_path=parent_path,
                    constraint_name=(
                        f"AdvPy_{digit.value}{index}FKOrient_{suffix}"
                    ),
                    world_position=state.world_position,
                    world_axes=state.world_axes,
                    radius=float(radius) * radius_factors[index - 1],
                ))
                parent_path = control_path
    return BodyHandFkControlPlan(tuple(roots), tuple(controls))


def audit_body_hand_fk_input(
    plan: BodyHandFkControlPlan,
    snapshot: BodyHandFkInputSnapshot,
) -> tuple[BodyHandControlIssue, ...]:
    expected = {control.driven_joint for control in plan.controls}
    actual = {joint.joint: joint for joint in snapshot.joints}
    issues = []
    if len(actual) != len(snapshot.joints) or set(actual) != expected:
        issues.append(BodyHandControlIssue(
            "hand_input_joint_set_mismatch",
            "Hand FK 输入关节集合不一致",
        ))
    for path in sorted(expected & set(actual)):
        state = actual[path]
        if state.writable_rotation_axes != TRANSLATION_AXES:
            issues.append(BodyHandControlIssue(
                "hand_input_rotation_locked",
                "Hand FK 目标 rotate 不可完整写入",
                path,
            ))
        if any(source is not None for source in state.rotation_sources):
            issues.append(BodyHandControlIssue(
                "hand_input_rotation_connected",
                "Hand FK 目标 rotate 已有输入连接",
                path,
            ))
    return tuple(issues)


def audit_body_hand_fk_controls(
    plan: BodyHandFkControlPlan,
    snapshot: BodyHandFkControlSnapshot,
    *,
    tolerance: float = 1e-4,
    check_initial_pose: bool = True,
) -> tuple[BodyHandControlIssue, ...]:
    issues = []
    expected_roots = {root.path: root for root in plan.roots}
    actual_roots = {root.path: root for root in snapshot.roots}
    if (
        len(actual_roots) != len(snapshot.roots)
        or set(actual_roots) != set(expected_roots)
    ):
        issues.append(BodyHandControlIssue(
            "hand_root_set_mismatch",
            "Hand FK 根节点集合不一致",
        ))
    for path in sorted(set(expected_roots) & set(actual_roots)):
        spec = expected_roots[path]
        state = actual_roots[path]
        if state.parent_path != spec.parent_path:
            issues.append(BodyHandControlIssue(
                "hand_root_parent_mismatch",
                "Hand FK 根节点未挂在对应 Wrist 下",
                path,
            ))
        if not (
            _vector_matches(state.local_translation, (0.0, 0.0, 0.0), tolerance)
            and _vector_matches(state.local_rotation, (0.0, 0.0, 0.0), tolerance)
            and _vector_matches(state.local_scale, (1.0, 1.0, 1.0), tolerance)
        ):
            issues.append(BodyHandControlIssue(
                "hand_root_channels_mismatch",
                "Hand FK 根节点本地通道不中性",
                path,
            ))
        if check_initial_pose and not (
            _vector_matches(state.world_position, spec.world_position, tolerance)
            and _axes_match(state.world_axes, spec.world_axes, tolerance)
        ):
            issues.append(BodyHandControlIssue(
                "hand_root_pose_mismatch",
                "Hand FK 根节点世界帧与 Wrist 不一致",
                path,
            ))

    marker = "__body_hand_fk_control_set__"
    limb_issues = audit_body_limb_fk_controls(
        BodyLimbFkControlPlan(marker, marker, plan.controls),
        BodyLimbFkControlSnapshot(marker, snapshot.controls),
        limb_label="Hand",
        tolerance=tolerance,
        check_initial_pose=check_initial_pose,
    )
    issues.extend(limb_issues)
    return tuple(issues)


def _vector_matches(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _axes_match(left: AxisFrame, right: AxisFrame, tolerance: float) -> bool:
    return all(
        _vector_matches(current, wanted, tolerance)
        for current, wanted in zip(left, right)
    )
