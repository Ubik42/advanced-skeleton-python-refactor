from __future__ import annotations

from dataclasses import dataclass

from .body_root_motion import BodyRootMotionPlan
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide
from .joint_labels import JointLabel


Vector3 = tuple[float, float, float]
BODY_EXPORT_OWNER = "advanced-skeleton-python-refactor"
BODY_EXPORT_KIND = "body_export_skeleton"
BODY_EXPORT_SCHEMA_VERSION = 1


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
