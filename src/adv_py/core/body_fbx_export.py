from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .body_export_skeleton import (
    BODY_EXPORT_BAKE_SCHEMA_VERSION,
    BODY_EXPORT_CHANNEL_ATTRIBUTES,
    BODY_EXPORT_KIND,
    BODY_EXPORT_OWNER,
    BODY_EXPORT_SCHEMA_VERSION,
    BodyExportSkeletonBakePlan,
    BodyExportSkeletonBakedSnapshot,
    BodyExportSkeletonIssue,
)


FBX_BINARY_MAGIC = b"Kaydara FBX Binary"


@dataclass(frozen=True, slots=True)
class BodyFbxExportSelection:
    root_path: str
    node_paths: tuple[str, ...]
    start_frame: int
    end_frame: int
    sample_by: int

    @property
    def node_count(self) -> int:
        return len(self.node_paths)


@dataclass(frozen=True, slots=True)
class BodyFbxArtifact:
    byte_count: int
    content_sha256: str
    encoding: str


def plan_body_fbx_export_selection(
    bake: BodyExportSkeletonBakePlan,
) -> BodyFbxExportSelection:
    export = bake.export_skeleton
    paths = (export.root_motion_path,) + tuple(
        joint.output_path for joint in export.joints
    )
    if len(set(paths)) != len(paths) or any(not path.startswith("|") for path in paths):
        raise ValueError("FBX 导出选择集包含重复或非完整 DAG 路径")
    return BodyFbxExportSelection(
        root_path=export.root_motion_path,
        node_paths=paths,
        start_frame=bake.root_motion.start_frame,
        end_frame=bake.root_motion.end_frame,
        sample_by=bake.root_motion.sample_by,
    )


def audit_body_fbx_export_readiness(
    bake: BodyExportSkeletonBakePlan,
    snapshot: BodyExportSkeletonBakedSnapshot,
    body_dependency_plugs: tuple[str, ...],
) -> tuple[BodyExportSkeletonIssue, ...]:
    """Audit structural bake evidence without comparing values to themselves."""
    issues: list[BodyExportSkeletonIssue] = []
    export = bake.export_skeleton
    expected_frames = bake.frames
    if (
        snapshot.root_path != export.root.output_path
        or snapshot.owner != BODY_EXPORT_OWNER
        or snapshot.artifact_kind != BODY_EXPORT_KIND
        or snapshot.schema_version != BODY_EXPORT_SCHEMA_VERSION
        or snapshot.source_body_root != export.source_body_root
        or snapshot.joint_count != len(export.joints)
        or snapshot.bake_schema_version != BODY_EXPORT_BAKE_SCHEMA_VERSION
        or snapshot.start_frame != bake.root_motion.start_frame
        or snapshot.end_frame != bake.root_motion.end_frame
        or snapshot.sample_by != bake.root_motion.sample_by
    ):
        issues.append(BodyExportSkeletonIssue(
            "fbx_bake_provenance_mismatch",
            "FBX 导出骨架的 provenance 或 bake 帧范围不一致",
            export.root.output_path,
        ))
    if snapshot.root_constraint_exists:
        issues.append(BodyExportSkeletonIssue(
            "fbx_export_constraint_remains",
            "FBX 导出骨架仍保留实时 root constraint",
            export.root.output_path,
        ))

    root_motion = snapshot.root_motion
    if (
        root_motion.output_path != export.root_motion_path
        or root_motion.point_constraint_exists
        or root_motion.orient_constraint_exists
    ):
        issues.append(BodyExportSkeletonIssue(
            "fbx_root_motion_not_independent",
            "FBX Root Motion 路径或独立性不符合要求",
            export.root_motion_path,
        ))
    _audit_channels(
        issues,
        root_motion.channels,
        bake.root_motion.channel_attributes,
        expected_frames,
        export.root_motion_path,
        "Root Motion",
    )

    actual_joints = {state.output_path: state for state in snapshot.joints}
    expected_paths = tuple(joint.output_path for joint in export.joints)
    if len(actual_joints) != len(snapshot.joints) or set(actual_joints) != set(expected_paths):
        issues.append(BodyExportSkeletonIssue(
            "fbx_joint_set_mismatch",
            "FBX 导出 joint 集合不完整或包含重复路径",
        ))
    else:
        for path in expected_paths:
            state = actual_joints[path]
            if state.source_message_exists:
                issues.append(BodyExportSkeletonIssue(
                    "fbx_source_message_remains",
                    "FBX 导出 joint 仍保留 Body source message",
                    path,
                ))
            _audit_channels(
                issues,
                state.channels,
                BODY_EXPORT_CHANNEL_ATTRIBUTES,
                expected_frames,
                path,
                "Export joint",
            )
    if body_dependency_plugs:
        issues.append(BodyExportSkeletonIssue(
            "fbx_body_dependency_remains",
            "FBX 导出层级仍与 Body 存在连接",
            "、".join(body_dependency_plugs),
        ))
    return tuple(issues)


def inspect_body_fbx_bytes(data: bytes) -> BodyFbxArtifact:
    if not isinstance(data, bytes) or len(data) < 128:
        raise ValueError("FBX 临时文件为空或过小")
    prefix = data[:256].lstrip(b"\xef\xbb\xbf\x00\t\r\n ")
    if prefix.startswith(FBX_BINARY_MAGIC):
        encoding = "binary"
    elif prefix.startswith(b"; FBX"):
        encoding = "ascii"
    else:
        raise ValueError("FBX 临时文件头无效")
    return BodyFbxArtifact(
        byte_count=len(data),
        content_sha256=sha256(data).hexdigest(),
        encoding=encoding,
    )


def _audit_channels(
    issues: list[BodyExportSkeletonIssue],
    states,
    expected_attributes: tuple[str, ...],
    expected_frames: tuple[int, ...],
    path: str,
    label: str,
) -> None:
    channels = {state.attribute: state for state in states}
    if len(channels) != len(states) or set(channels) != set(expected_attributes):
        issues.append(BodyExportSkeletonIssue(
            "fbx_baked_channel_set_mismatch",
            f"{label} bake 通道集合不一致",
            path,
        ))
        return
    for attribute in expected_attributes:
        state = channels[attribute]
        subject = f"{path}.{attribute}"
        if state.source_kind != "animation_curve":
            issues.append(BodyExportSkeletonIssue(
                "fbx_baked_channel_source_mismatch",
                f"{label} 通道不是独立动画曲线",
                subject,
            ))
        if tuple(key.frame for key in state.keys) != expected_frames:
            issues.append(BodyExportSkeletonIssue(
                "fbx_baked_key_frames_mismatch",
                f"{label} 关键帧时间不完整",
                subject,
            ))
        if any(
            key.in_tangent != "linear" or key.out_tangent != "linear"
            for key in state.keys
        ):
            issues.append(BodyExportSkeletonIssue(
                "fbx_baked_key_tangent_mismatch",
                f"{label} 关键帧切线不是 linear",
                subject,
            ))
