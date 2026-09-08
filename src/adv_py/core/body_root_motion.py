from __future__ import annotations

from dataclasses import dataclass

from .fit_container import FitUpAxis


Vector3 = tuple[float, float, float]


class BodyRootMotionValidationError(ValueError):
    """Raised before an unsafe root-motion artifact can be planned."""


@dataclass(frozen=True, slots=True)
class BodyRootMotionPlan:
    source_root_path: str
    output_name: str
    output_path: str
    point_constraint_name: str
    orient_constraint_name: str
    up_axis: FitUpAxis
    translation_axes: tuple[str, str]
    rotation_axis: str

    @property
    def node_names(self) -> tuple[str, str, str]:
        return (
            self.output_name,
            self.point_constraint_name,
            self.orient_constraint_name,
        )

    @property
    def skipped_translation_axis(self) -> str:
        return self.up_axis.value.lower()

    @property
    def skipped_rotation_axes(self) -> tuple[str, str]:
        return tuple(axis for axis in "xyz" if axis != self.rotation_axis)


@dataclass(frozen=True, slots=True)
class BodyRootMotionSnapshot:
    output_path: str
    output_parent_path: str | None
    output_type: str
    translation: Vector3
    rotation: Vector3
    scale: Vector3
    joint_orient: Vector3
    translation_sources: tuple[str | None, str | None, str | None]
    rotation_sources: tuple[str | None, str | None, str | None]
    point_targets: tuple[str, ...]
    orient_targets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BodyRootMotionIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_root_motion(
    *,
    source_root_path: str,
    up_axis: FitUpAxis,
    output_basename: str = "AdvPy_GameRootMotion",
) -> BodyRootMotionPlan:
    if (
        not isinstance(source_root_path, str)
        or not source_root_path.startswith("|")
        or source_root_path.count("|") != 1
    ):
        raise BodyRootMotionValidationError(
            "Root Motion 来源必须是场景根层的完整 DAG 路径"
        )
    if not isinstance(up_axis, FitUpAxis):
        raise BodyRootMotionValidationError("Root Motion Up Axis 无效")
    if (
        not isinstance(output_basename, str)
        or not output_basename
        or "|" in output_basename
        or ":" in output_basename
        or not output_basename.replace("_", "a").isalnum()
    ):
        raise BodyRootMotionValidationError("Root Motion 输出基名无效")

    source_name = source_root_path[1:]
    namespace = source_name.rsplit(":", 1)[0] + ":" if ":" in source_name else ""
    output_name = f"{namespace}{output_basename}"
    planar_axes = (
        ("x", "z") if up_axis is FitUpAxis.Y else ("x", "y")
    )
    rotation_axis = up_axis.value.lower()
    return BodyRootMotionPlan(
        source_root_path=source_root_path,
        output_name=output_name,
        output_path=f"|{output_name}",
        point_constraint_name=f"{output_name}_PointConstraint",
        orient_constraint_name=f"{output_name}_OrientConstraint",
        up_axis=up_axis,
        translation_axes=planar_axes,
        rotation_axis=rotation_axis,
    )


def audit_body_root_motion(
    plan: BodyRootMotionPlan,
    snapshot: BodyRootMotionSnapshot,
    *,
    tolerance: float = 1e-5,
) -> tuple[BodyRootMotionIssue, ...]:
    issues: list[BodyRootMotionIssue] = []
    if not (
        snapshot.output_path == plan.output_path
        and snapshot.output_parent_path is None
        and snapshot.output_type == "joint"
        and _close(snapshot.scale, (1.0, 1.0, 1.0), tolerance)
        and _close(snapshot.joint_orient, (0.0, 0.0, 0.0), tolerance)
    ):
        issues.append(BodyRootMotionIssue(
            "output_mismatch",
            "Root Motion 输出 joint 的路径、层级或中性属性不一致",
            plan.output_path,
        ))

    expected_translation = tuple(
        (
            f"{plan.point_constraint_name}.constraintTranslate{axis.upper()}"
            if axis in plan.translation_axes
            else None
        )
        for axis in "xyz"
    )
    expected_rotation = tuple(
        (
            f"{plan.orient_constraint_name}.constraintRotate{axis.upper()}"
            if axis == plan.rotation_axis
            else None
        )
        for axis in "xyz"
    )
    if snapshot.translation_sources != expected_translation:
        issues.append(BodyRootMotionIssue(
            "translation_wiring_mismatch",
            "Root Motion 平面位移接线不一致",
            plan.output_path,
        ))
    if snapshot.rotation_sources != expected_rotation:
        issues.append(BodyRootMotionIssue(
            "rotation_wiring_mismatch",
            "Root Motion Up 轴旋转接线不一致",
            plan.output_path,
        ))
    if snapshot.point_targets != (plan.source_root_path,):
        issues.append(BodyRootMotionIssue(
            "point_target_mismatch",
            "Root Motion 位移约束来源不一致",
            plan.point_constraint_name,
        ))
    if snapshot.orient_targets != (plan.source_root_path,):
        issues.append(BodyRootMotionIssue(
            "orient_target_mismatch",
            "Root Motion 朝向约束来源不一致",
            plan.orient_constraint_name,
        ))

    skipped_translate_index = "xyz".index(plan.skipped_translation_axis)
    skipped_rotate_indices = tuple(
        "xyz".index(axis) for axis in plan.skipped_rotation_axes
    )
    if abs(snapshot.translation[skipped_translate_index]) > tolerance:
        issues.append(BodyRootMotionIssue(
            "vertical_motion_mismatch",
            "Root Motion 输出包含了应被过滤的垂直位移",
            plan.output_path,
        ))
    if any(abs(snapshot.rotation[index]) > tolerance for index in skipped_rotate_indices):
        issues.append(BodyRootMotionIssue(
            "tilt_mismatch",
            "Root Motion 输出包含了应被过滤的倾斜旋转",
            plan.output_path,
        ))
    return tuple(issues)


def _close(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))
