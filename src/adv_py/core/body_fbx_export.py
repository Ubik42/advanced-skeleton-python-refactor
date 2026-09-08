from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import re

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
from .fit_container import FitUpAxis


FBX_BINARY_MAGIC = b"Kaydara FBX Binary"
FBX_BINARY_HEADER = b"Kaydara FBX Binary  \x00\x1a\x00"


class BodyFbxFileVersion(str, Enum):
    FBX_2018 = "FBX201800"
    FBX_2020 = "FBX202000"


class BodyFbxLinearUnit(str, Enum):
    CENTIMETER = "cm"
    METER = "m"


class BodyFbxEncoding(str, Enum):
    BINARY = "binary"
    ASCII = "ascii"


@dataclass(frozen=True, slots=True)
class BodyFbxExportProfile:
    file_version: BodyFbxFileVersion
    up_axis: FitUpAxis
    linear_unit: BodyFbxLinearUnit
    encoding: BodyFbxEncoding = BodyFbxEncoding.BINARY

    def __post_init__(self) -> None:
        if (
            not isinstance(self.file_version, BodyFbxFileVersion)
            or not isinstance(self.up_axis, FitUpAxis)
            or not isinstance(self.linear_unit, BodyFbxLinearUnit)
            or not isinstance(self.encoding, BodyFbxEncoding)
        ):
            raise ValueError("FBX 导出 Profile 字段无效")

    @property
    def format_version(self) -> int:
        return {
            BodyFbxFileVersion.FBX_2018: 7500,
            BodyFbxFileVersion.FBX_2020: 7700,
        }[self.file_version]

    def scale_factor_from(self, source_unit: BodyFbxLinearUnit) -> float:
        if not isinstance(source_unit, BodyFbxLinearUnit):
            raise ValueError("FBX 导出源场景单位无效")
        centimeters_per_unit = {
            BodyFbxLinearUnit.CENTIMETER: 1.0,
            BodyFbxLinearUnit.METER: 100.0,
        }
        return (
            centimeters_per_unit[self.linear_unit]
            / centimeters_per_unit[source_unit]
        )


@dataclass(frozen=True, slots=True)
class BodyFbxAppliedProfile:
    file_version: str
    up_axis: str
    scale_factor: float
    encoding: str


@dataclass(frozen=True, slots=True)
class BodyFbxPublishedNode:
    scene_path: str
    published_name: str
    published_path: str


@dataclass(frozen=True, slots=True)
class BodyFbxExportSelection:
    root_path: str
    node_paths: tuple[str, ...]
    published_root_path: str
    published_nodes: tuple[BodyFbxPublishedNode, ...]
    start_frame: int
    end_frame: int
    sample_by: int

    @property
    def node_count(self) -> int:
        return len(self.node_paths)

    @property
    def published_paths(self) -> tuple[str, ...]:
        return tuple(node.published_path for node in self.published_nodes)


@dataclass(frozen=True, slots=True)
class BodyFbxArtifact:
    byte_count: int
    content_sha256: str
    encoding: str
    format_version: int


def plan_body_fbx_export_selection(
    bake: BodyExportSkeletonBakePlan,
    *,
    published_root_name: str = "RootMotion",
) -> BodyFbxExportSelection:
    export = bake.export_skeleton
    paths = (export.root_motion_path,) + tuple(
        joint.output_path for joint in export.joints
    )
    if len(set(paths)) != len(paths) or any(not path.startswith("|") for path in paths):
        raise ValueError("FBX 导出选择集包含重复或非完整 DAG 路径")
    if not _is_portable_node_name(published_root_name):
        raise ValueError("FBX 发布 Root Motion 名称无效")

    published_by_scene_path = {
        export.root_motion_path: f"|{published_root_name}"
    }
    nodes = [BodyFbxPublishedNode(
        scene_path=export.root_motion_path,
        published_name=published_root_name,
        published_path=f"|{published_root_name}",
    )]
    for joint in export.joints:
        published_name = joint.source_path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if not _is_portable_node_name(published_name):
            raise ValueError(
                f"FBX 发布 joint 名称无效：{published_name}"
            )
        try:
            published_parent = published_by_scene_path[joint.output_parent_path]
        except KeyError as error:
            raise ValueError("FBX 发布 joint 父级不在导出选择集") from error
        published_path = f"{published_parent}|{published_name}"
        published_by_scene_path[joint.output_path] = published_path
        nodes.append(BodyFbxPublishedNode(
            scene_path=joint.output_path,
            published_name=published_name,
            published_path=published_path,
        ))
    published_paths = tuple(node.published_path for node in nodes)
    if len(set(published_paths)) != len(published_paths):
        raise ValueError("FBX 发布名称映射产生重复 DAG 路径")
    return BodyFbxExportSelection(
        root_path=export.root_motion_path,
        node_paths=paths,
        published_root_path=f"|{published_root_name}",
        published_nodes=tuple(nodes),
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
        if not data.startswith(FBX_BINARY_HEADER) or len(data) < 27:
            raise ValueError("FBX binary 文件头不完整")
        format_version = int.from_bytes(data[23:27], "little")
    elif prefix.startswith(b"; FBX"):
        encoding = "ascii"
        match = re.search(rb"\bFBXVersion:\s*(\d+)", data[:32768])
        if match is None:
            raise ValueError("FBX ASCII 文件缺少格式版本")
        format_version = int(match.group(1))
    else:
        raise ValueError("FBX 临时文件头无效")
    if format_version < 7000:
        raise ValueError("FBX 文件格式版本过旧或无效")
    return BodyFbxArtifact(
        byte_count=len(data),
        content_sha256=sha256(data).hexdigest(),
        encoding=encoding,
        format_version=format_version,
    )


def audit_body_fbx_profile(
    profile: BodyFbxExportProfile,
    source_unit: BodyFbxLinearUnit,
    applied: BodyFbxAppliedProfile,
    artifact: BodyFbxArtifact,
    *,
    tolerance: float = 1e-9,
) -> tuple[str, ...]:
    issues = []
    if applied.file_version != profile.file_version.value:
        issues.append("FBX exporter 文件版本回读不一致")
    if applied.up_axis.casefold() != profile.up_axis.value.casefold():
        issues.append("FBX exporter Up Axis 回读不一致")
    expected_scale = profile.scale_factor_from(source_unit)
    if abs(applied.scale_factor - expected_scale) > tolerance:
        issues.append(
            "FBX exporter 单位比例回读不一致"
            f"（期望 {expected_scale:g}，实际 {applied.scale_factor:g}）"
        )
    if applied.encoding.casefold() != profile.encoding.value:
        issues.append("FBX exporter 编码回读不一致")
    if artifact.encoding != profile.encoding.value:
        issues.append("FBX 文件编码与 Profile 不一致")
    if artifact.format_version != profile.format_version:
        issues.append("FBX 文件头版本与 Profile 不一致")
    return tuple(issues)


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


def _is_portable_node_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value[0].isdigit()
        and value.replace("_", "a").isalnum()
        and value.isascii()
    )
