from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json

from .skin_weights import (
    SkinInfluenceWeight,
    SkinVertexWeights,
    SkinWeightInputState,
    SkinWeightIssue,
    SkinWeightValidationError,
    skin_weight_request,
)


SKIN_WEIGHT_DOCUMENT_FORMAT = "adv_py_skin_weights"
SKIN_WEIGHT_DOCUMENT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SkinWeightDocument:
    skin_name: str
    mesh_path: str
    vertex_count: int
    influence_paths: tuple[str, ...]
    maximum_influences: int
    maintain_maximum_influences: bool
    vertices: tuple[SkinVertexWeights, ...]
    content_sha256: str
    schema_version: int = SKIN_WEIGHT_DOCUMENT_SCHEMA_VERSION
    format_name: str = SKIN_WEIGHT_DOCUMENT_FORMAT


@dataclass(frozen=True, slots=True)
class SkinWeightInfluenceMapping:
    source_path: str
    target_path: str


@dataclass(frozen=True, slots=True)
class SkinWeightPathMapping:
    target_skin_name: str
    target_mesh_path: str
    influences: tuple[SkinWeightInfluenceMapping, ...]


def skin_weight_document_from_state(
    state: SkinWeightInputState,
) -> SkinWeightDocument:
    if state.skin_name is None or state.geometry_path is None:
        raise SkinWeightValidationError("无法从缺失的 skinCluster 或 mesh 导出权重")
    if state.vertex_count <= 0:
        raise SkinWeightValidationError("无法导出没有顶点的 mesh 权重")
    if not state.influence_paths or len(set(state.influence_paths)) != len(
        state.influence_paths
    ):
        raise SkinWeightValidationError("导出权重需要唯一且非空的 influence 集合")
    if any(
        not isinstance(path, str) or not path.strip()
        for path in state.influence_paths
    ):
        raise SkinWeightValidationError("导出权重包含无效 influence 路径")
    if (
        isinstance(state.maximum_influences, bool)
        or not isinstance(state.maximum_influences, int)
        or state.maximum_influences < 1
    ):
        raise SkinWeightValidationError("导出权重的最大影响数无效")
    if not isinstance(state.maintain_maximum_influences, bool):
        raise SkinWeightValidationError("导出权重的最大影响数开关无效")
    request = skin_weight_request(
        state.skin_name,
        state.geometry_path,
        state.vertices,
    )
    expected_indices = tuple(range(state.vertex_count))
    actual_indices = tuple(vertex.vertex_index for vertex in request.vertices)
    if actual_indices != expected_indices:
        raise SkinWeightValidationError("权重文档必须完整覆盖 mesh 的全部顶点")
    available = set(state.influence_paths)
    for vertex in request.vertices:
        if any(
            entry.influence_path not in available
            for entry in vertex.weights
        ):
            raise SkinWeightValidationError("顶点权重引用了 skinCluster 之外的 influence")
        if (
            state.maintain_maximum_influences
            and len(vertex.weights) > state.maximum_influences
        ):
            raise SkinWeightValidationError("顶点权重超过 skinCluster 最大影响数")
    document = SkinWeightDocument(
        request.skin_name,
        request.mesh_path,
        state.vertex_count,
        tuple(state.influence_paths),
        state.maximum_influences,
        state.maintain_maximum_influences,
        request.vertices,
        "",
    )
    return replace(document, content_sha256=_document_digest(document))


def skin_weight_document_to_json(document: SkinWeightDocument) -> str:
    if document.schema_version != SKIN_WEIGHT_DOCUMENT_SCHEMA_VERSION:
        raise SkinWeightValidationError("不支持的权重文档 schema 版本")
    if document.format_name != SKIN_WEIGHT_DOCUMENT_FORMAT:
        raise SkinWeightValidationError("不支持的权重文档格式")
    if document.content_sha256 != _document_digest(document):
        raise SkinWeightValidationError("权重文档内容摘要无效")
    data = _document_payload(document)
    data["content_sha256"] = document.content_sha256
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def skin_weight_document_from_json(text: str) -> SkinWeightDocument:
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise SkinWeightValidationError("权重文件不是有效 JSON") from error
    root_keys = {
        "format",
        "schema_version",
        "skin_name",
        "mesh_path",
        "vertex_count",
        "influence_paths",
        "maximum_influences",
        "maintain_maximum_influences",
        "vertices",
        "content_sha256",
    }
    _require_object(data, root_keys, "权重文档根对象")
    if data["format"] != SKIN_WEIGHT_DOCUMENT_FORMAT:
        raise SkinWeightValidationError("不支持的权重文档格式")
    if (
        isinstance(data["schema_version"], bool)
        or not isinstance(data["schema_version"], int)
        or data["schema_version"] != SKIN_WEIGHT_DOCUMENT_SCHEMA_VERSION
    ):
        raise SkinWeightValidationError("不支持的权重文档 schema 版本")
    if not isinstance(data["vertices"], list):
        raise SkinWeightValidationError("权重文档 vertices 必须是数组")
    vertices = []
    for item in data["vertices"]:
        _require_object(item, {"vertex_index", "weights"}, "顶点权重")
        if not isinstance(item["weights"], list):
            raise SkinWeightValidationError("顶点 weights 必须是数组")
        weights = []
        for entry in item["weights"]:
            _require_object(entry, {"influence_path", "weight"}, "Influence 权重")
            weights.append(
                SkinInfluenceWeight(entry["influence_path"], entry["weight"])
            )
        vertices.append(SkinVertexWeights(item["vertex_index"], tuple(weights)))
    if not isinstance(data["influence_paths"], list):
        raise SkinWeightValidationError("权重文档 influence_paths 必须是数组")
    if any(not isinstance(path, str) for path in data["influence_paths"]):
        raise SkinWeightValidationError("权重文档 influence_paths 必须是字符串数组")
    if not isinstance(data["maintain_maximum_influences"], bool):
        raise SkinWeightValidationError("权重文档 maintain_maximum_influences 必须是布尔值")
    if (
        isinstance(data["vertex_count"], bool)
        or not isinstance(data["vertex_count"], int)
        or data["vertex_count"] <= 0
    ):
        raise SkinWeightValidationError("权重文档 vertex_count 必须是正整数")
    if (
        isinstance(data["maximum_influences"], bool)
        or not isinstance(data["maximum_influences"], int)
        or data["maximum_influences"] < 1
    ):
        raise SkinWeightValidationError("权重文档 maximum_influences 必须是正整数")
    state = SkinWeightInputState(
        data["skin_name"],
        data["mesh_path"],
        data["vertex_count"],
        tuple(data["influence_paths"]),
        (),
        data["maximum_influences"],
        data["maintain_maximum_influences"],
        tuple(vertices),
    )
    document = skin_weight_document_from_state(state)
    if not isinstance(data["content_sha256"], str) or (
        data["content_sha256"] != document.content_sha256
    ):
        raise SkinWeightValidationError("权重文档内容摘要不匹配")
    return document


def audit_skin_weight_document_target(
    document: SkinWeightDocument,
    state: SkinWeightInputState,
) -> tuple[SkinWeightIssue, ...]:
    issues = []
    checks = (
        (
            state.skin_name == document.skin_name,
            "skin_missing",
            "目标 skinCluster 不存在、名称不唯一或类型错误",
            document.skin_name,
        ),
        (
            state.geometry_path == document.mesh_path,
            "geometry_mismatch",
            "目标 skinCluster 没有绑定到文档 mesh",
            document.mesh_path,
        ),
        (
            state.vertex_count == document.vertex_count,
            "vertex_count_mismatch",
            "目标 mesh 顶点数与权重文档不一致",
            document.mesh_path,
        ),
        (
            len(state.influence_paths) == len(document.influence_paths)
            and set(state.influence_paths) == set(document.influence_paths),
            "influence_set_mismatch",
            "目标 influence 集合与权重文档不一致",
            document.skin_name,
        ),
        (
            state.maximum_influences == document.maximum_influences
            and state.maintain_maximum_influences
            == document.maintain_maximum_influences,
            "maximum_influences_mismatch",
            "目标最大影响数设置与权重文档不一致",
            document.skin_name,
        ),
    )
    for passed, code, message, subject in checks:
        if not passed:
            issues.append(SkinWeightIssue(code, message, subject))
    locked = set(state.locked_influences) & set(document.influence_paths)
    for path in sorted(locked):
        issues.append(
            SkinWeightIssue(
                "influence_locked",
                "目标 influence 已锁定权重",
                path,
            )
        )
    return tuple(issues)


def remap_skin_weight_document(
    document: SkinWeightDocument,
    mapping: SkinWeightPathMapping,
) -> SkinWeightDocument:
    if (
        not isinstance(mapping.target_skin_name, str)
        or not mapping.target_skin_name.strip()
        or "|" in mapping.target_skin_name
    ):
        raise SkinWeightValidationError("映射目标 skinCluster 必须是有效短名")
    if (
        not isinstance(mapping.target_mesh_path, str)
        or not mapping.target_mesh_path.strip()
    ):
        raise SkinWeightValidationError("映射目标 mesh 路径不能为空")
    if not mapping.influences:
        raise SkinWeightValidationError("权重导入映射不能为空")
    pairs = []
    for entry in mapping.influences:
        if (
            not isinstance(entry.source_path, str)
            or not entry.source_path.strip()
            or not isinstance(entry.target_path, str)
            or not entry.target_path.strip()
        ):
            raise SkinWeightValidationError("Influence 映射路径不能为空")
        pairs.append((entry.source_path.strip(), entry.target_path.strip()))
    sources = tuple(source for source, _ in pairs)
    targets = tuple(target for _, target in pairs)
    if len(set(sources)) != len(sources):
        raise SkinWeightValidationError("Influence 映射包含重复源路径")
    if len(set(targets)) != len(targets):
        raise SkinWeightValidationError("Influence 映射必须是一一对应，目标路径不能重复")
    if len(sources) != len(document.influence_paths) or set(sources) != set(
        document.influence_paths
    ):
        raise SkinWeightValidationError("Influence 映射必须完整且只覆盖文档源集合")
    target_by_source = dict(pairs)
    target_influences = tuple(
        target_by_source[source]
        for source in document.influence_paths
    )
    target_vertices = tuple(
        SkinVertexWeights(
            vertex.vertex_index,
            tuple(
                SkinInfluenceWeight(
                    target_by_source[entry.influence_path],
                    entry.weight,
                )
                for entry in vertex.weights
            ),
        )
        for vertex in document.vertices
    )
    target_state = SkinWeightInputState(
        mapping.target_skin_name.strip(),
        mapping.target_mesh_path.strip(),
        document.vertex_count,
        target_influences,
        (),
        document.maximum_influences,
        document.maintain_maximum_influences,
        target_vertices,
    )
    return skin_weight_document_from_state(target_state)


def _document_payload(document: SkinWeightDocument) -> dict:
    return {
        "format": document.format_name,
        "schema_version": document.schema_version,
        "skin_name": document.skin_name,
        "mesh_path": document.mesh_path,
        "vertex_count": document.vertex_count,
        "influence_paths": list(document.influence_paths),
        "maximum_influences": document.maximum_influences,
        "maintain_maximum_influences": document.maintain_maximum_influences,
        "vertices": [
            {
                "vertex_index": vertex.vertex_index,
                "weights": [
                    {
                        "influence_path": entry.influence_path,
                        "weight": entry.weight,
                    }
                    for entry in vertex.weights
                ],
            }
            for vertex in document.vertices
        ],
    }


def _document_digest(document: SkinWeightDocument) -> str:
    encoded = json.dumps(
        _document_payload(document),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _require_object(value, expected_keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise SkinWeightValidationError(f"{label}字段集合无效")
