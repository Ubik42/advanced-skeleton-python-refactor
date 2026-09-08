from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite

from .fit_container import FitUpAxis
from .fit_hierarchy import audit_fit_hierarchy
from .fit_metadata import (
    FitJointField,
    FitJointMetadata,
    FitJointValue,
    audit_fit_joint,
    fit_joint_value,
    validate_fit_joint_value,
)
from .fit_orientation import (
    FitLocalDirection,
    FitOrientationAxisConfiguration,
    FitOrientationSnapshot,
)
from .fit_settings import (
    FitSkeletonField,
    FitSkeletonSetting,
    FitSkeletonSettings,
    FitSkeletonValue,
    audit_fit_skeleton_settings,
)
from .fit_template import FitJointSpec, FitTemplateSpec, ordered_fit_joints
from .joint_labels import JointLabel


Vector3 = tuple[float, float, float]
AxisFrame = tuple[Vector3, Vector3, Vector3]

FIT_SKELETON_DOCUMENT_FORMAT = "adv_py_fit_skeleton"
FIT_SKELETON_DOCUMENT_SCHEMA_VERSION = 1
FIT_SKELETON_DOCUMENT_SUFFIX = ".fit.json"

FIT_SKELETON_NONPORTABLE_SETTING_FIELDS = (
    FitSkeletonField.OBJECTS_SKIN,
    FitSkeletonField.OBJECTS_ALL,
    FitSkeletonField.OBJECTS_RIGHT_EYE,
    FitSkeletonField.OBJECTS_LEFT_EYE,
    FitSkeletonField.PRE_REBUILD_SCRIPT,
    FitSkeletonField.POST_REBUILD_SCRIPT,
)
FIT_SKELETON_PORTABLE_SETTING_FIELDS = tuple(
    field
    for field in FitSkeletonField
    if field not in FIT_SKELETON_NONPORTABLE_SETTING_FIELDS
)


class FitSkeletonDocumentValidationError(ValueError):
    """Raised when a portable FitSkeleton document is unsafe to use."""


@dataclass(frozen=True, slots=True)
class FitSkeletonSettingChannelState:
    field: FitSkeletonField
    value: FitSkeletonValue
    writable: bool
    incoming_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FitSkeletonJointMetadataValue:
    field: FitJointField
    value: FitJointValue

    def __post_init__(self) -> None:
        if not isinstance(self.field, FitJointField):
            raise FitSkeletonDocumentValidationError(
                "FitSkeleton 文档包含未知关节元数据字段"
            )
        if self.value is None:
            raise FitSkeletonDocumentValidationError(
                "FitSkeleton 文档不能保存空的关节元数据值"
            )
        try:
            validate_fit_joint_value(self.field, self.value)
        except ValueError as error:
            raise FitSkeletonDocumentValidationError(str(error)) from error


@dataclass(frozen=True, slots=True)
class FitSkeletonJointDocument:
    name: str
    parent: str | None
    local_position: Vector3
    world_axes: AxisFrame
    label: JointLabel
    metadata: tuple[FitSkeletonJointMetadataValue, ...] = ()


@dataclass(frozen=True, slots=True)
class FitSkeletonDocument:
    up_axis: FitUpAxis
    axis_configuration: FitOrientationAxisConfiguration
    settings: tuple[FitSkeletonSetting, ...]
    joints: tuple[FitSkeletonJointDocument, ...]
    content_sha256: str
    schema_version: int = FIT_SKELETON_DOCUMENT_SCHEMA_VERSION
    format_name: str = FIT_SKELETON_DOCUMENT_FORMAT


def fit_skeleton_document_from_snapshot(
    snapshot: FitOrientationSnapshot,
    settings: FitSkeletonSettings,
    labels: tuple[tuple[str, JointLabel], ...],
) -> FitSkeletonDocument:
    hierarchy_issues = audit_fit_hierarchy(snapshot.hierarchy)
    if hierarchy_issues:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 层级不能导出："
            + "；".join(issue.message for issue in hierarchy_issues)
        )
    hierarchy = {node.path: node for node in snapshot.hierarchy.joints}
    orientations = {item.joint: item for item in snapshot.joints}
    metadata = {item.joint: item for item in snapshot.metadata}
    label_map = dict(labels)
    if (
        len(orientations) != len(snapshot.joints)
        or set(orientations) != set(hierarchy)
    ):
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 朝向快照与层级不一致"
        )
    if (
        len(metadata) != len(snapshot.metadata)
        or set(metadata) != set(hierarchy)
    ):
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 导出需要每个关节的完整元数据"
        )
    if len(label_map) != len(labels) or set(label_map) != set(hierarchy):
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 导出需要每个关节的唯一标签"
        )
    if settings.container != snapshot.hierarchy.container:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 设置与层级不属于同一容器"
        )
    setting_issues = audit_fit_skeleton_settings(settings, require_complete=True)
    if setting_issues:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 设置不能导出："
            + "；".join(issue.message for issue in setting_issues)
        )
    _reject_nonportable_setting_values(settings)

    records = []
    for node in snapshot.hierarchy.joints:
        orientation = orientations[node.path]
        if any(abs(float(value)) > 1e-5 for value in orientation.rotation):
            raise FitSkeletonDocumentValidationError(
                f"Fit joint rotate 必须先归零：{node.short_name}"
            )
        parent = None
        if node.dag_parent != snapshot.hierarchy.container:
            parent_node = hierarchy.get(node.dag_parent)
            if parent_node is None:
                raise FitSkeletonDocumentValidationError(
                    f"Fit joint 父级不在导出层级：{node.short_name}"
                )
            parent = parent_node.short_name
        values = tuple(
            FitSkeletonJointMetadataValue(
                field,
                fit_joint_value(metadata[node.path], field),
            )
            for field in FitJointField
            if field in metadata[node.path].present_fields
        )
        records.append(
            FitSkeletonJointDocument(
                node.short_name,
                parent,
                tuple(float(value) for value in node.local_position),
                tuple(
                    tuple(float(value) for value in axis)
                    for axis in orientation.world_axes
                ),
                label_map[node.path],
                values,
            )
        )
    portable_settings = tuple(
        FitSkeletonSetting(field, settings.value(field))
        for field in FIT_SKELETON_PORTABLE_SETTING_FIELDS
    )
    return _make_document(
        snapshot.up_axis,
        snapshot.axis_configuration,
        portable_settings,
        tuple(records),
    )


def fit_skeleton_document_to_json(document: FitSkeletonDocument) -> str:
    _validate_document(document)
    return json.dumps(
        {
            **_document_payload(document),
            "content_sha256": document.content_sha256,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def fit_skeleton_document_from_json(text: str) -> FitSkeletonDocument:
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文件不是有效 JSON"
        ) from error
    _require_object(
        data,
        {
            "format",
            "schema_version",
            "up_axis",
            "axis_configuration",
            "settings",
            "joints",
            "content_sha256",
        },
        "FitSkeleton 文档根对象",
    )
    if data["format"] != FIT_SKELETON_DOCUMENT_FORMAT:
        raise FitSkeletonDocumentValidationError(
            "不支持的 FitSkeleton 文档格式"
        )
    if (
        isinstance(data["schema_version"], bool)
        or not isinstance(data["schema_version"], int)
        or data["schema_version"] != FIT_SKELETON_DOCUMENT_SCHEMA_VERSION
    ):
        raise FitSkeletonDocumentValidationError(
            "不支持的 FitSkeleton schema 版本"
        )
    try:
        up_axis = FitUpAxis(data["up_axis"])
    except (TypeError, ValueError) as error:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton up_axis 仅支持 y 或 z"
        ) from error

    axis_data = data["axis_configuration"]
    _require_object(
        axis_data,
        {"primary", "secondary", "world_match"},
        "FitSkeleton axis_configuration",
    )
    if type(axis_data["world_match"]) is not bool:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton world_match 必须是布尔值"
        )
    try:
        axis_configuration = FitOrientationAxisConfiguration(
            FitLocalDirection(axis_data["primary"]),
            FitLocalDirection(axis_data["secondary"]),
            axis_data["world_match"],
        )
    except (TypeError, ValueError) as error:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 轴配置无效"
        ) from error

    if not isinstance(data["settings"], list):
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton settings 必须是数组"
        )
    settings = []
    for item in data["settings"]:
        _require_object(item, {"field", "value"}, "FitSkeleton setting")
        try:
            field = FitSkeletonField(item["field"])
            settings.append(FitSkeletonSetting(field, item["value"]))
        except (TypeError, ValueError) as error:
            raise FitSkeletonDocumentValidationError(
                "FitSkeleton setting 值无效"
            ) from error

    if not isinstance(data["joints"], list):
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton joints 必须是数组"
        )
    joints = []
    for item in data["joints"]:
        _require_object(
            item,
            {
                "name",
                "parent",
                "local_position",
                "world_axes",
                "label",
                "metadata",
            },
            "FitSkeleton joint",
        )
        name = _require_string(item["name"], "FitSkeleton joint name")
        parent = item["parent"]
        if parent is not None:
            parent = _require_string(parent, "FitSkeleton joint parent")
        label = JointLabel.parse(
            _require_string(item["label"], "FitSkeleton joint label")
        )
        position = _vector3(
            item["local_position"],
            "FitSkeleton joint local_position",
        )
        axes_value = item["world_axes"]
        if not isinstance(axes_value, list) or len(axes_value) != 3:
            raise FitSkeletonDocumentValidationError(
                "FitSkeleton joint world_axes 必须包含三条轴"
            )
        axes = tuple(
            _vector3(axis, "FitSkeleton joint world axis")
            for axis in axes_value
        )
        metadata_value = item["metadata"]
        if not isinstance(metadata_value, list):
            raise FitSkeletonDocumentValidationError(
                "FitSkeleton joint metadata 必须是数组"
            )
        values = []
        for metadata_item in metadata_value:
            _require_object(
                metadata_item,
                {"field", "value"},
                "FitSkeleton joint metadata",
            )
            try:
                field = FitJointField(metadata_item["field"])
                values.append(
                    FitSkeletonJointMetadataValue(
                        field,
                        metadata_item["value"],
                    )
                )
            except (TypeError, ValueError) as error:
                raise FitSkeletonDocumentValidationError(
                    "FitSkeleton joint metadata 值无效"
                ) from error
        joints.append(
            FitSkeletonJointDocument(
                name,
                parent,
                position,
                axes,
                label,
                tuple(values),
            )
        )

    document = _make_document(
        up_axis,
        axis_configuration,
        tuple(settings),
        tuple(joints),
    )
    if (
        not isinstance(data["content_sha256"], str)
        or data["content_sha256"] != document.content_sha256
    ):
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文档内容摘要不匹配"
        )
    return document


def fit_skeleton_documents_match(
    left: FitSkeletonDocument,
    right: FitSkeletonDocument,
    *,
    tolerance: float = 1e-5,
) -> bool:
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not isfinite(float(tolerance))
        or tolerance <= 0
    ):
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文档比较容差必须是正有限数值"
        )
    _validate_document(left)
    _validate_document(right)
    if (
        left.up_axis is not right.up_axis
        or left.axis_configuration != right.axis_configuration
        or len(left.settings) != len(right.settings)
        or len(left.joints) != len(right.joints)
    ):
        return False
    for first, second in zip(left.settings, right.settings):
        if first.field is not second.field or not _values_match(
            first.value,
            second.value,
            tolerance,
        ):
            return False
    for first, second in zip(left.joints, right.joints):
        if (
            first.name != second.name
            or first.parent != second.parent
            or first.label != second.label
            or len(first.metadata) != len(second.metadata)
            or not _vectors_match(
                first.local_position,
                second.local_position,
                tolerance,
            )
            or any(
                not _vectors_match(a, b, tolerance)
                for a, b in zip(first.world_axes, second.world_axes)
            )
        ):
            return False
        for first_value, second_value in zip(first.metadata, second.metadata):
            if (
                first_value.field is not second_value.field
                or not _values_match(
                    first_value.value,
                    second_value.value,
                    tolerance,
                )
            ):
                return False
    return True


def fit_skeleton_document_template(
    document: FitSkeletonDocument,
) -> FitTemplateSpec:
    _validate_document(document)
    return FitTemplateSpec(
        "fit_skeleton_document",
        tuple(
            FitJointSpec(
                joint.name,
                joint.parent,
                joint.local_position,
                joint.label,
            )
            for joint in document.joints
        ),
    )


def _make_document(
    up_axis: FitUpAxis,
    axis_configuration: FitOrientationAxisConfiguration,
    settings: tuple[FitSkeletonSetting, ...],
    joints: tuple[FitSkeletonJointDocument, ...],
) -> FitSkeletonDocument:
    if not isinstance(up_axis, FitUpAxis):
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文档 Up Axis 无效"
        )
    if not isinstance(axis_configuration, FitOrientationAxisConfiguration):
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文档轴配置无效"
        )
    fields = tuple(item.field for item in settings)
    if fields != FIT_SKELETON_PORTABLE_SETTING_FIELDS:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文档需要完整且有序的可移植设置"
        )
    setting_snapshot = FitSkeletonSettings("<document>", settings)
    setting_issues = audit_fit_skeleton_settings(
        setting_snapshot,
        require_complete=False,
    )
    if setting_issues:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文档设置无效："
            + "；".join(issue.message for issue in setting_issues)
        )
    if not joints:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文档至少需要一个关节"
        )
    if len({joint.name for joint in joints}) != len(joints):
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文档包含重复关节名称"
        )
    try:
        template = FitTemplateSpec(
            "fit_skeleton_document",
            tuple(
                FitJointSpec(
                    joint.name,
                    joint.parent,
                    joint.local_position,
                    joint.label,
                )
                for joint in joints
            ),
        )
    except ValueError as error:
        raise FitSkeletonDocumentValidationError(str(error)) from error
    ordered_names = tuple(
        joint.name for joint in ordered_fit_joints(template)
    )
    if tuple(joint.name for joint in joints) != ordered_names:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文档关节必须按父级优先顺序排列"
        )
    for joint in joints:
        _validate_axis_frame(joint.world_axes, joint.name)
        fields = tuple(value.field for value in joint.metadata)
        if len(fields) != len(set(fields)) or fields != tuple(
            field for field in FitJointField if field in set(fields)
        ):
            raise FitSkeletonDocumentValidationError(
                f"Fit joint 元数据必须唯一且有序：{joint.name}"
            )
        item = _metadata_from_values(joint.name, joint.metadata)
        issues = audit_fit_joint(item)
        if issues:
            raise FitSkeletonDocumentValidationError(
                f"Fit joint 元数据无效：{joint.name}："
                + "；".join(issue.message for issue in issues)
            )
    provisional = FitSkeletonDocument(
        up_axis,
        axis_configuration,
        settings,
        joints,
        "",
    )
    digest = sha256(_canonical_payload(provisional)).hexdigest()
    return FitSkeletonDocument(
        up_axis,
        axis_configuration,
        settings,
        joints,
        digest,
    )


def _validate_document(document: FitSkeletonDocument) -> None:
    if (
        document.format_name != FIT_SKELETON_DOCUMENT_FORMAT
        or document.schema_version != FIT_SKELETON_DOCUMENT_SCHEMA_VERSION
    ):
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文档格式或 schema 版本无效"
        )
    expected = _make_document(
        document.up_axis,
        document.axis_configuration,
        document.settings,
        document.joints,
    )
    if document.content_sha256 != expected.content_sha256:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 文档内容摘要不匹配"
        )


def _metadata_from_values(
    joint: str,
    values: tuple[FitSkeletonJointMetadataValue, ...],
) -> FitJointMetadata:
    keywords = {value.field.value: value.value for value in values}
    return FitJointMetadata(
        joint=joint,
        present_fields=frozenset(value.field for value in values),
        **keywords,
    )


def _reject_nonportable_setting_values(settings: FitSkeletonSettings) -> None:
    populated = tuple(
        field.value
        for field in FIT_SKELETON_NONPORTABLE_SETTING_FIELDS
        if settings.value(field) != ""
    )
    if populated:
        raise FitSkeletonDocumentValidationError(
            "FitSkeleton 包含场景路径或脚本文本，当前安全文档拒绝导出："
            + "、".join(populated)
        )


def _validate_axis_frame(frame: AxisFrame, joint: str) -> None:
    if len(frame) != 3:
        raise FitSkeletonDocumentValidationError(
            f"Fit joint 世界轴数量无效：{joint}"
        )
    axes = tuple(_finite_vector(axis, f"Fit joint 世界轴无效：{joint}") for axis in frame)
    tolerance = 1e-4
    for axis in axes:
        if abs(_dot(axis, axis) - 1.0) > tolerance:
            raise FitSkeletonDocumentValidationError(
                f"Fit joint 世界轴必须归一化：{joint}"
            )
    if any(
        abs(_dot(axes[first], axes[second])) > tolerance
        for first, second in ((0, 1), (0, 2), (1, 2))
    ):
        raise FitSkeletonDocumentValidationError(
            f"Fit joint 世界轴必须互相正交：{joint}"
        )
    if _dot(_cross(axes[0], axes[1]), axes[2]) < 1.0 - tolerance:
        raise FitSkeletonDocumentValidationError(
            f"Fit joint 世界轴必须组成右手坐标系：{joint}"
        )


def _document_payload(document: FitSkeletonDocument) -> dict[str, object]:
    return {
        "format": FIT_SKELETON_DOCUMENT_FORMAT,
        "schema_version": FIT_SKELETON_DOCUMENT_SCHEMA_VERSION,
        "up_axis": document.up_axis.value,
        "axis_configuration": {
            "primary": document.axis_configuration.primary.value,
            "secondary": document.axis_configuration.secondary.value,
            "world_match": document.axis_configuration.world_match,
        },
        "settings": [
            {"field": setting.field.value, "value": setting.value}
            for setting in document.settings
        ],
        "joints": [
            {
                "name": joint.name,
                "parent": joint.parent,
                "local_position": list(joint.local_position),
                "world_axes": [list(axis) for axis in joint.world_axes],
                "label": joint.label.text,
                "metadata": [
                    {"field": value.field.value, "value": value.value}
                    for value in joint.metadata
                ],
            }
            for joint in document.joints
        ],
    }


def _canonical_payload(document: FitSkeletonDocument) -> bytes:
    return json.dumps(
        _document_payload(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _require_object(
    value: object,
    fields: set[str],
    context: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise FitSkeletonDocumentValidationError(
            f"{context} 字段不完整或包含未知字段"
        )
    return value


def _require_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise FitSkeletonDocumentValidationError(f"{context} 必须是非空字符串")
    return value


def _vector3(value: object, context: str) -> Vector3:
    if not isinstance(value, list) or len(value) != 3:
        raise FitSkeletonDocumentValidationError(
            f"{context} 必须是三个有限数值"
        )
    return _finite_vector(tuple(value), context)


def _finite_vector(value: tuple[object, ...], context: str) -> Vector3:
    if len(value) != 3 or any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not isfinite(float(item))
        for item in value
    ):
        raise FitSkeletonDocumentValidationError(
            f"{context} 必须是三个有限数值"
        )
    return tuple(float(item) for item in value)


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right))


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _values_match(left: object, right: object, tolerance: float) -> bool:
    if type(left) is bool or type(right) is bool:
        return type(left) is bool and type(right) is bool and left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tolerance
    return left == right


def _vectors_match(
    left: Vector3,
    right: Vector3,
    tolerance: float,
) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))
