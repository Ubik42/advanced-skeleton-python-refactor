"""Portable, integrity-checked geometry and weights captured from one source."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from math import isfinite

from .face_neutral_geometry import (FaceNeutralGeometry,
    face_neutral_geometry_from_json, face_neutral_geometry_to_json)
from .skin_weight_io import (SkinWeightDocument,
    skin_weight_document_from_json, skin_weight_document_to_json)
from .skin_weights import SkinWeightValidationError


SKIN_WEIGHT_SURFACE_SOURCE_FORMAT = "adv_py_skin_surface_source"
SKIN_WEIGHT_SURFACE_SOURCE_MAX_BYTES = 256_000_000


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SkinWeightValidationError("表面权重源资产包含重复字段：" + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise SkinWeightValidationError("表面权重源资产包含非有限数：" + value)


@dataclass(frozen=True, slots=True)
class SkinWeightSurfaceSource:
    weights: SkinWeightDocument
    geometry: FaceNeutralGeometry
    bind_topology: str | None = None
    blend_weights: tuple[float, ...] | None = None
    member_vertices: tuple[int, ...] | None = None

    def __post_init__(self):
        if (self.weights.mesh_path != self.geometry.mesh.path
                or self.weights.vertex_count != self.geometry.mesh.vertex_count):
            raise SkinWeightValidationError("源权重与几何不属于同一网格")
        if not self.geometry.up_axis or not self.geometry.linear_unit:
            raise SkinWeightValidationError("源几何缺少坐标轴或长度单位")
        if (self.bind_topology is not None
                and (not isinstance(self.bind_topology, str)
                     or re.fullmatch(r"[0-9a-f]{64}",
                                     self.bind_topology) is None)):
            raise SkinWeightValidationError("源 Skin 绑定拓扑摘要无效")
        if (self.blend_weights is not None
                and (not isinstance(self.blend_weights, tuple)
                     or len(self.blend_weights) != self.weights.vertex_count
                     or any(isinstance(value, bool)
                            or not isinstance(value, (int, float))
                            or not isfinite(value)
                            or not 0.0 <= value <= 1.0
                            for value in self.blend_weights))):
            raise SkinWeightValidationError("源 Skin 逐顶点混合权重无效")
        if (self.member_vertices is not None
                and (not isinstance(self.member_vertices, tuple)
                     or any(type(index) is not int
                            or index < 0 or index >= self.weights.vertex_count
                            for index in self.member_vertices)
                     or tuple(sorted(set(self.member_vertices)))
                     != self.member_vertices)):
            raise SkinWeightValidationError("源 Skin 变形集顶点成员无效")


def skin_weight_surface_source_to_json(source: SkinWeightSurfaceSource) -> str:
    if not isinstance(source, SkinWeightSurfaceSource):
        raise SkinWeightValidationError("表面权重源资产无效")
    weights = json.loads(skin_weight_document_to_json(source.weights))
    geometry = json.loads(face_neutral_geometry_to_json(source.geometry))
    payload = {"weights": weights, "geometry": geometry}
    if source.bind_topology is not None:
        payload["bind_topology"] = source.bind_topology
    if source.blend_weights is not None:
        payload["blend_weights"] = source.blend_weights
    if source.member_vertices is not None:
        payload["member_vertices"] = source.member_vertices
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    document = {"format": SKIN_WEIGHT_SURFACE_SOURCE_FORMAT,
                "version": (4 if source.member_vertices is not None else
                            3 if source.blend_weights is not None else
                            2 if source.bind_topology is not None else 1),
                "payload": payload,
                "content_sha256": sha256(canonical.encode("utf-8")).hexdigest()}
    result = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if len(result.encode("utf-8")) > SKIN_WEIGHT_SURFACE_SOURCE_MAX_BYTES:
        raise SkinWeightValidationError("表面权重源资产超过 256 MB")
    return result


def skin_weight_surface_source_from_json(text: str) -> SkinWeightSurfaceSource:
    if not isinstance(text, str) or len(text.encode("utf-8")) > SKIN_WEIGHT_SURFACE_SOURCE_MAX_BYTES:
        raise SkinWeightValidationError("表面权重源资产无效或超过 256 MB")
    try:
        document = json.loads(text, object_pairs_hook=_unique_object,
                              parse_constant=_reject_constant)
        version = document.get("version") if isinstance(document, dict) else None
        expected_payloads = {
            1: ({"weights", "geometry"},),
            2: ({"weights", "geometry", "bind_topology"},),
            3: ({"weights", "geometry", "blend_weights"},
                {"weights", "geometry", "bind_topology", "blend_weights"}),
            4: ({"weights", "geometry", "member_vertices"},
                {"weights", "geometry", "bind_topology", "member_vertices"},
                {"weights", "geometry", "blend_weights", "member_vertices"},
                {"weights", "geometry", "bind_topology", "blend_weights",
                 "member_vertices"}),
        }
        if (not isinstance(document, dict)
                or set(document) != {"format", "version", "payload", "content_sha256"}
                or document["format"] != SKIN_WEIGHT_SURFACE_SOURCE_FORMAT
                or type(document["version"]) is not int
                or version not in expected_payloads
                or not isinstance(document["payload"], dict)
                or set(document["payload"]) not in expected_payloads[version]):
            raise ValueError("结构不匹配")
        payload = document["payload"]
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False)
        if sha256(canonical.encode("utf-8")).hexdigest() != document["content_sha256"]:
            raise SkinWeightValidationError("表面权重源资产摘要不匹配")
        weights = skin_weight_document_from_json(json.dumps(payload["weights"], ensure_ascii=False))
        geometry = face_neutral_geometry_from_json(json.dumps(payload["geometry"], ensure_ascii=False))
        return SkinWeightSurfaceSource(
            weights, geometry, payload.get("bind_topology"),
            tuple(payload["blend_weights"])
            if "blend_weights" in payload and
            isinstance(payload["blend_weights"], list) else
            payload.get("blend_weights"),
            tuple(payload["member_vertices"])
            if "member_vertices" in payload and
            isinstance(payload["member_vertices"], list) else
            payload.get("member_vertices"))
    except (TypeError, ValueError, KeyError, OverflowError) as error:
        raise SkinWeightValidationError("表面权重源资产格式无效：" + str(error)) from error
