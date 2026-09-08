from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

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


@dataclass(frozen=True, slots=True)
class BodyRootMotionSample:
    frame: int
    translation: Vector3
    rotation: Vector3

    def __post_init__(self) -> None:
        if (
            isinstance(self.frame, bool)
            or not isinstance(self.frame, int)
            or len(self.translation) != 3
            or len(self.rotation) != 3
            or not all(
                isfinite(float(value))
                for value in self.translation + self.rotation
            )
        ):
            raise BodyRootMotionValidationError(
                "Root Motion 采样必须包含整数帧和有限 TR 值"
            )


@dataclass(frozen=True, slots=True)
class BodyRootMotionBakePlan:
    root_motion: BodyRootMotionPlan
    start_frame: int
    end_frame: int
    sample_by: int
    frames: tuple[int, ...]

    @property
    def channel_attributes(self) -> tuple[str, str, str]:
        return tuple(
            f"translate{axis.upper()}" for axis in self.root_motion.translation_axes
        ) + (f"rotate{self.root_motion.rotation_axis.upper()}",)


@dataclass(frozen=True, slots=True)
class BodyRootMotionKeyState:
    frame: int
    value: float
    in_tangent: str
    out_tangent: str


@dataclass(frozen=True, slots=True)
class BodyRootMotionBakedChannelState:
    attribute: str
    source_kind: str | None
    keys: tuple[BodyRootMotionKeyState, ...]


@dataclass(frozen=True, slots=True)
class BodyRootMotionBakedSnapshot:
    output_path: str
    point_constraint_exists: bool
    orient_constraint_exists: bool
    channels: tuple[BodyRootMotionBakedChannelState, ...]


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


def plan_body_root_motion_bake(
    root_motion: BodyRootMotionPlan,
    *,
    start_frame: int,
    end_frame: int,
    sample_by: int = 1,
) -> BodyRootMotionBakePlan:
    values = (start_frame, end_frame, sample_by)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise BodyRootMotionValidationError(
            "Root Motion bake 帧范围与采样步长必须是整数"
        )
    if start_frame > end_frame or sample_by < 1:
        raise BodyRootMotionValidationError(
            "Root Motion bake 帧范围或采样步长无效"
        )
    if (end_frame - start_frame) % sample_by:
        raise BodyRootMotionValidationError(
            "Root Motion bake 结束帧必须落在采样步长上"
        )
    frames = tuple(range(start_frame, end_frame + 1, sample_by))
    return BodyRootMotionBakePlan(
        root_motion=root_motion,
        start_frame=start_frame,
        end_frame=end_frame,
        sample_by=sample_by,
        frames=frames,
    )


def audit_body_root_motion_samples(
    plan: BodyRootMotionBakePlan,
    samples: tuple[BodyRootMotionSample, ...],
    *,
    tolerance: float = 1e-5,
) -> tuple[BodyRootMotionIssue, ...]:
    issues: list[BodyRootMotionIssue] = []
    if tuple(sample.frame for sample in samples) != plan.frames:
        issues.append(BodyRootMotionIssue(
            "sample_frames_mismatch",
            "Root Motion 采样帧与 bake 计划不一致",
        ))
        return tuple(issues)
    vertical = "xyz".index(plan.root_motion.skipped_translation_axis)
    tilt = tuple(
        "xyz".index(axis) for axis in plan.root_motion.skipped_rotation_axes
    )
    for sample in samples:
        if abs(sample.translation[vertical]) > tolerance:
            issues.append(BodyRootMotionIssue(
                "sample_vertical_motion_mismatch",
                "Root Motion bake 样本包含垂直位移",
                str(sample.frame),
            ))
        if any(abs(sample.rotation[index]) > tolerance for index in tilt):
            issues.append(BodyRootMotionIssue(
                "sample_tilt_mismatch",
                "Root Motion bake 样本包含倾斜旋转",
                str(sample.frame),
            ))
    return tuple(issues)


def audit_baked_body_root_motion(
    plan: BodyRootMotionBakePlan,
    samples: tuple[BodyRootMotionSample, ...],
    snapshot: BodyRootMotionBakedSnapshot,
    *,
    tolerance: float = 1e-5,
) -> tuple[BodyRootMotionIssue, ...]:
    issues = list(audit_body_root_motion_samples(plan, samples, tolerance=tolerance))
    if snapshot.output_path != plan.root_motion.output_path:
        issues.append(BodyRootMotionIssue(
            "baked_output_mismatch",
            "Root Motion bake 输出路径不一致",
            plan.root_motion.output_path,
        ))
    if snapshot.point_constraint_exists or snapshot.orient_constraint_exists:
        issues.append(BodyRootMotionIssue(
            "baked_constraint_remains",
            "Root Motion bake 后仍有实时约束",
            plan.root_motion.output_path,
        ))
    actual_channels = {state.attribute: state for state in snapshot.channels}
    if (
        len(actual_channels) != len(snapshot.channels)
        or set(actual_channels) != set(plan.channel_attributes)
    ):
        issues.append(BodyRootMotionIssue(
            "baked_channel_set_mismatch",
            "Root Motion bake 通道集合不一致",
            plan.root_motion.output_path,
        ))
        return tuple(issues)

    translate_indices = {
        f"translate{axis.upper()}": "xyz".index(axis)
        for axis in plan.root_motion.translation_axes
    }
    for attribute in plan.channel_attributes:
        state = actual_channels[attribute]
        if state.source_kind != "animation_curve":
            issues.append(BodyRootMotionIssue(
                "baked_channel_source_mismatch",
                "Root Motion bake 通道不是独立动画曲线",
                attribute,
            ))
        expected_values = tuple(
            (
                sample.translation[translate_indices[attribute]]
                if attribute in translate_indices
                else sample.rotation[
                    "xyz".index(plan.root_motion.rotation_axis)
                ]
            )
            for sample in samples
        )
        if (
            tuple(key.frame for key in state.keys) != plan.frames
            or len(state.keys) != len(expected_values)
            or any(
                abs(key.value - value) > tolerance
                for key, value in zip(state.keys, expected_values)
            )
        ):
            issues.append(BodyRootMotionIssue(
                "baked_key_values_mismatch",
                "Root Motion bake 关键帧时间或数值不一致",
                attribute,
            ))
        if any(
            key.in_tangent != "linear" or key.out_tangent != "linear"
            for key in state.keys
        ):
            issues.append(BodyRootMotionIssue(
                "baked_key_tangent_mismatch",
                "Root Motion bake 关键帧切线不是 linear",
                attribute,
            ))
    return tuple(issues)


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
