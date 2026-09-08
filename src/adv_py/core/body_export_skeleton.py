from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .body_root_motion import (
    BodyRootMotionBakePlan,
    BodyRootMotionBakedChannelState,
    BodyRootMotionBakedSnapshot,
    BodyRootMotionPlan,
    BodyRootMotionSample,
    audit_baked_body_root_motion,
    audit_body_root_motion_samples,
    plan_body_root_motion_bake,
)
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide
from .joint_labels import JointLabel


Vector3 = tuple[float, float, float]
BODY_EXPORT_OWNER = "advanced-skeleton-python-refactor"
BODY_EXPORT_KIND = "body_export_skeleton"
BODY_EXPORT_SCHEMA_VERSION = 1
BODY_EXPORT_BAKE_SCHEMA_VERSION = 1
BODY_EXPORT_CHANNEL_ATTRIBUTES = tuple(
    f"{kind}{axis}" for kind in ("translate", "rotate", "scale") for axis in "XYZ"
)


class BodyExportSkeletonValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyExportJointSpec:
    source_path: str
    source_parent_path: str | None
    output_name: str
    output_path: str
    output_parent_path: str
    side: FitBuildSide
    label: JointLabel | None
    joint_orient: Vector3
    world_position: Vector3
    world_axes: AxisFrame
    root_constraint_name: str | None = None

    @property
    def is_root(self) -> bool:
        return self.source_parent_path is None


@dataclass(frozen=True, slots=True)
class BodyExportSkeletonPlan:
    source_body_root: str
    root_motion_path: str
    output_prefix: str
    joints: tuple[BodyExportJointSpec, ...]

    @property
    def root(self) -> BodyExportJointSpec:
        return self.joints[0]

    @property
    def node_names(self) -> tuple[str, ...]:
        names = [joint.output_name for joint in self.joints]
        if self.root.root_constraint_name is not None:
            names.append(self.root.root_constraint_name)
        return tuple(names)


@dataclass(frozen=True, slots=True)
class BodyExportJointState:
    source_path: str | None
    output_name: str
    output_path: str
    output_parent_path: str | None
    side: FitBuildSide
    label: JointLabel | None
    joint_orient: Vector3
    world_position: Vector3
    world_axes: AxisFrame
    translation_sources: tuple[str | None, str | None, str | None]
    rotation_sources: tuple[str | None, str | None, str | None]
    scale_sources: tuple[str | None, str | None, str | None]


@dataclass(frozen=True, slots=True)
class BodyExportSkeletonSnapshot:
    root_path: str
    joints: tuple[BodyExportJointState, ...]
    owner: str | None
    artifact_kind: str | None
    schema_version: int | None
    source_body_root: str | None
    joint_count: int | None


@dataclass(frozen=True, slots=True)
class BodyExportSkeletonIssue:
    code: str
    message: str
    subject: str | None = None


@dataclass(frozen=True, slots=True)
class BodyExportJointSample:
    output_path: str
    translation: Vector3
    rotation: Vector3
    scale: Vector3

    def __post_init__(self) -> None:
        values = self.translation + self.rotation + self.scale
        if (
            not isinstance(self.output_path, str)
            or not self.output_path.startswith("|")
            or any(len(vector) != 3 for vector in (
                self.translation,
                self.rotation,
                self.scale,
            ))
            or not all(isfinite(float(value)) for value in values)
        ):
            raise BodyExportSkeletonValidationError(
                "Export Skeleton joint 样本无效"
            )


@dataclass(frozen=True, slots=True)
class BodyExportSkeletonSample:
    frame: int
    root_motion: BodyRootMotionSample
    joints: tuple[BodyExportJointSample, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.frame, bool)
            or not isinstance(self.frame, int)
            or self.root_motion.frame != self.frame
            or not self.joints
            or len({joint.output_path for joint in self.joints}) != len(self.joints)
        ):
            raise BodyExportSkeletonValidationError(
                "Export Skeleton 帧样本结构无效"
            )


@dataclass(frozen=True, slots=True)
class BodyExportSkeletonBakePlan:
    export_skeleton: BodyExportSkeletonPlan
    root_motion: BodyRootMotionBakePlan

    @property
    def frames(self) -> tuple[int, ...]:
        return self.root_motion.frames


@dataclass(frozen=True, slots=True)
class BodyExportBakedJointState:
    output_path: str
    source_message_exists: bool
    channels: tuple[BodyRootMotionBakedChannelState, ...]


@dataclass(frozen=True, slots=True)
class BodyExportSkeletonBakedSnapshot:
    root_path: str
    owner: str | None
    artifact_kind: str | None
    schema_version: int | None
    source_body_root: str | None
    joint_count: int | None
    bake_schema_version: int | None
    start_frame: int | None
    end_frame: int | None
    sample_by: int | None
    root_constraint_exists: bool
    root_motion: BodyRootMotionBakedSnapshot
    joints: tuple[BodyExportBakedJointState, ...]


def plan_body_export_skeleton(
    body: BodySkeletonSnapshot,
    root_motion: BodyRootMotionPlan,
    *,
    output_prefix: str = "AdvPy_EXP_",
) -> BodyExportSkeletonPlan:
    if body.root != root_motion.source_root_path or not body.joints:
        raise BodyExportSkeletonValidationError(
            "Export Skeleton 的 Body 与 Root Motion 来源不一致"
        )
    if (
        not isinstance(output_prefix, str)
        or not output_prefix
        or "|" in output_prefix
        or ":" in output_prefix
        or not output_prefix.replace("_", "a").isalnum()
    ):
        raise BodyExportSkeletonValidationError(
            "Export Skeleton 输出前缀无效"
        )
    states = sorted(body.joints, key=lambda item: (item.path.count("|"), item.path))
    if states[0].path != body.root or states[0].parent_path is not None:
        raise BodyExportSkeletonValidationError("Body root 拓扑无效")
    if len({state.path for state in states}) != len(states):
        raise BodyExportSkeletonValidationError("Body joint 路径重复")
    if len({state.name for state in states}) != len(states):
        raise BodyExportSkeletonValidationError(
            "Export Skeleton 当前要求 Body joint 短名唯一"
        )

    source_name = body.root[1:]
    namespace = source_name.rsplit(":", 1)[0] + ":" if ":" in source_name else ""
    output_paths: dict[str, str] = {}
    specs = []
    for state in states:
        if state.parent_path is None:
            output_parent = root_motion.output_path
        else:
            try:
                output_parent = output_paths[state.parent_path]
            except KeyError as error:
                raise BodyExportSkeletonValidationError(
                    f"Body joint 父级不在同一骨架：{state.path}"
                ) from error
        output_name = f"{namespace}{output_prefix}{state.name}"
        output_path = f"{output_parent}|{output_name}"
        output_paths[state.path] = output_path
        specs.append(BodyExportJointSpec(
            source_path=state.path,
            source_parent_path=state.parent_path,
            output_name=output_name,
            output_path=output_path,
            output_parent_path=output_parent,
            side=state.side,
            label=state.label,
            joint_orient=state.joint_orient,
            world_position=state.world_position,
            world_axes=state.world_axes,
            root_constraint_name=(
                f"{output_name}_ParentConstraint"
                if state.parent_path is None
                else None
            ),
        ))
    return BodyExportSkeletonPlan(
        source_body_root=body.root,
        root_motion_path=root_motion.output_path,
        output_prefix=output_prefix,
        joints=tuple(specs),
    )


def plan_body_export_skeleton_bake(
    export_skeleton: BodyExportSkeletonPlan,
    root_motion: BodyRootMotionPlan,
    *,
    start_frame: int,
    end_frame: int,
    sample_by: int = 1,
) -> BodyExportSkeletonBakePlan:
    if (
        export_skeleton.root_motion_path != root_motion.output_path
        or export_skeleton.source_body_root != root_motion.source_root_path
    ):
        raise BodyExportSkeletonValidationError(
            "Export Skeleton 与 Root Motion bake 输入不一致"
        )
    return BodyExportSkeletonBakePlan(
        export_skeleton=export_skeleton,
        root_motion=plan_body_root_motion_bake(
            root_motion,
            start_frame=start_frame,
            end_frame=end_frame,
            sample_by=sample_by,
        ),
    )


def audit_body_export_skeleton_samples(
    plan: BodyExportSkeletonBakePlan,
    samples: tuple[BodyExportSkeletonSample, ...],
) -> tuple[BodyExportSkeletonIssue, ...]:
    issues: list[BodyExportSkeletonIssue] = []
    if tuple(sample.frame for sample in samples) != plan.frames:
        return (
            BodyExportSkeletonIssue(
                "sample_frames_mismatch",
                "Export Skeleton 采样帧与 bake 计划不一致",
            ),
        )
    expected_paths = tuple(
        joint.output_path for joint in plan.export_skeleton.joints
    )
    root_samples = tuple(sample.root_motion for sample in samples)
    if audit_body_root_motion_samples(plan.root_motion, root_samples):
        issues.append(BodyExportSkeletonIssue(
            "root_motion_samples_mismatch",
            "Export Skeleton 的 Root Motion 样本无效",
        ))
    for sample in samples:
        if tuple(joint.output_path for joint in sample.joints) != expected_paths:
            issues.append(BodyExportSkeletonIssue(
                "joint_sample_set_mismatch",
                "Export Skeleton joint 样本集合或顺序不一致",
                str(sample.frame),
            ))
    return tuple(issues)


def audit_baked_body_export_skeleton(
    plan: BodyExportSkeletonBakePlan,
    samples: tuple[BodyExportSkeletonSample, ...],
    snapshot: BodyExportSkeletonBakedSnapshot,
    *,
    tolerance: float = 1e-5,
) -> tuple[BodyExportSkeletonIssue, ...]:
    issues = list(audit_body_export_skeleton_samples(plan, samples))
    if any(issue.code in {
        "sample_frames_mismatch",
        "joint_sample_set_mismatch",
    } for issue in issues):
        return tuple(issues)
    export = plan.export_skeleton
    if (
        snapshot.root_path != export.root.output_path
        or snapshot.owner != BODY_EXPORT_OWNER
        or snapshot.artifact_kind != BODY_EXPORT_KIND
        or snapshot.schema_version != BODY_EXPORT_SCHEMA_VERSION
        or snapshot.source_body_root != export.source_body_root
        or snapshot.joint_count != len(export.joints)
        or snapshot.bake_schema_version != BODY_EXPORT_BAKE_SCHEMA_VERSION
        or snapshot.start_frame != plan.root_motion.start_frame
        or snapshot.end_frame != plan.root_motion.end_frame
        or snapshot.sample_by != plan.root_motion.sample_by
    ):
        issues.append(BodyExportSkeletonIssue(
            "bake_provenance_mismatch",
            "Export Skeleton bake provenance 或帧范围不一致",
            export.root.output_path,
        ))
    if snapshot.root_constraint_exists:
        issues.append(BodyExportSkeletonIssue(
            "root_constraint_remains",
            "Export Skeleton bake 后 root constraint 仍存在",
            export.root.output_path,
        ))
    root_samples = tuple(sample.root_motion for sample in samples)
    if audit_baked_body_root_motion(
        plan.root_motion,
        root_samples,
        snapshot.root_motion,
        tolerance=tolerance,
    ):
        issues.append(BodyExportSkeletonIssue(
            "root_motion_bake_mismatch",
            "Export Skeleton 的 Root Motion bake 结果不一致",
            export.root_motion_path,
        ))

    actual = {state.output_path: state for state in snapshot.joints}
    expected_paths = {joint.output_path for joint in export.joints}
    if len(actual) != len(snapshot.joints) or set(actual) != expected_paths:
        issues.append(BodyExportSkeletonIssue(
            "baked_joint_set_mismatch",
            "Export Skeleton bake joint 集合不一致",
        ))
        return tuple(issues)

    samples_by_path = {
        joint.output_path: tuple(
            next(item for item in sample.joints if item.output_path == joint.output_path)
            for sample in samples
        )
        for joint in export.joints
    }
    for spec in export.joints:
        state = actual[spec.output_path]
        if state.source_message_exists:
            issues.append(BodyExportSkeletonIssue(
                "source_message_remains",
                "Export Skeleton bake 后仍有 Body source message",
                spec.output_path,
            ))
        channels = {channel.attribute: channel for channel in state.channels}
        if (
            len(channels) != len(state.channels)
            or set(channels) != set(BODY_EXPORT_CHANNEL_ATTRIBUTES)
        ):
            issues.append(BodyExportSkeletonIssue(
                "baked_channel_set_mismatch",
                "Export Skeleton bake 通道集合不一致",
                spec.output_path,
            ))
            continue
        joint_samples = samples_by_path[spec.output_path]
        values_by_attribute = {
            **{
                f"translate{axis}": tuple(
                    sample.translation[index] for sample in joint_samples
                )
                for index, axis in enumerate("XYZ")
            },
            **{
                f"rotate{axis}": tuple(
                    sample.rotation[index] for sample in joint_samples
                )
                for index, axis in enumerate("XYZ")
            },
            **{
                f"scale{axis}": tuple(
                    sample.scale[index] for sample in joint_samples
                )
                for index, axis in enumerate("XYZ")
            },
        }
        for attribute in BODY_EXPORT_CHANNEL_ATTRIBUTES:
            channel = channels[attribute]
            wanted = values_by_attribute[attribute]
            if channel.source_kind != "animation_curve":
                issues.append(BodyExportSkeletonIssue(
                    "baked_channel_source_mismatch",
                    "Export Skeleton bake 通道不是独立动画曲线",
                    f"{spec.output_path}.{attribute}",
                ))
            if (
                tuple(key.frame for key in channel.keys) != plan.frames
                or len(channel.keys) != len(wanted)
                or any(
                    abs(key.value - value) > tolerance
                    for key, value in zip(channel.keys, wanted)
                )
            ):
                issues.append(BodyExportSkeletonIssue(
                    "baked_key_values_mismatch",
                    "Export Skeleton bake key 时间或数值不一致",
                    f"{spec.output_path}.{attribute}",
                ))
            if any(
                key.in_tangent != "linear" or key.out_tangent != "linear"
                for key in channel.keys
            ):
                issues.append(BodyExportSkeletonIssue(
                    "baked_key_tangent_mismatch",
                    "Export Skeleton bake key 切线不是 linear",
                    f"{spec.output_path}.{attribute}",
                ))
    return tuple(issues)


def audit_body_export_skeleton(
    plan: BodyExportSkeletonPlan,
    snapshot: BodyExportSkeletonSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyExportSkeletonIssue, ...]:
    issues: list[BodyExportSkeletonIssue] = []
    if (
        snapshot.root_path != plan.root.output_path
        or snapshot.owner != BODY_EXPORT_OWNER
        or snapshot.artifact_kind != BODY_EXPORT_KIND
        or snapshot.schema_version != BODY_EXPORT_SCHEMA_VERSION
        or snapshot.source_body_root != plan.source_body_root
        or snapshot.joint_count != len(plan.joints)
    ):
        issues.append(BodyExportSkeletonIssue(
            "provenance_mismatch",
            "Export Skeleton 根路径或 provenance 不一致",
            plan.root.output_path,
        ))

    actual = {state.output_path: state for state in snapshot.joints}
    if len(actual) != len(snapshot.joints) or set(actual) != {
        spec.output_path for spec in plan.joints
    }:
        issues.append(BodyExportSkeletonIssue(
            "joint_set_mismatch",
            "Export Skeleton joint 集合不一致",
        ))
        return tuple(issues)

    for spec in plan.joints:
        state = actual[spec.output_path]
        if spec.is_root:
            constraint = f"{spec.output_path}|{spec.root_constraint_name}"
            expected_translate = tuple(
                f"{constraint}.constraintTranslate{axis}" for axis in "XYZ"
            )
            expected_rotate = tuple(
                f"{constraint}.constraintRotate{axis}" for axis in "XYZ"
            )
        else:
            expected_translate = tuple(
                f"{spec.source_path}.translate{axis}" for axis in "XYZ"
            )
            expected_rotate = tuple(
                f"{spec.source_path}.rotate{axis}" for axis in "XYZ"
            )
        expected_scale = tuple(
            f"{spec.source_path}.scale{axis}" for axis in "XYZ"
        )
        if not (
            state.source_path == spec.source_path
            and state.output_name == spec.output_name
            and state.output_parent_path == spec.output_parent_path
            and state.side is spec.side
            and state.label == spec.label
            and _close(state.joint_orient, spec.joint_orient, tolerance)
        ):
            issues.append(BodyExportSkeletonIssue(
                "joint_structure_mismatch",
                "Export Skeleton joint 结构、标签或来源不一致",
                spec.output_path,
            ))
        if not (
            _close(state.world_position, spec.world_position, tolerance)
            and _frame_close(state.world_axes, spec.world_axes, tolerance)
        ):
            issues.append(BodyExportSkeletonIssue(
                "joint_world_pose_mismatch",
                "Export Skeleton joint 世界姿态与 Body 不一致",
                spec.output_path,
            ))
        if (
            state.translation_sources != expected_translate
            or state.rotation_sources != expected_rotate
            or state.scale_sources != expected_scale
        ):
            issues.append(BodyExportSkeletonIssue(
                "joint_wiring_mismatch",
                "Export Skeleton joint 实时接线不一致",
                spec.output_path,
            ))
    return tuple(issues)


def _close(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _frame_close(left: AxisFrame, right: AxisFrame, tolerance: float) -> bool:
    return all(_close(a, b, tolerance) for a, b in zip(left, right))
