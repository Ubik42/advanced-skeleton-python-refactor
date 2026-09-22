"""Portable source-neutral geometry for cross-scene face asset transfer."""
from __future__ import annotations

from dataclasses import dataclass
import re

from .character_registry import canonical, digest, exact, safe_json
from .face_shapes import FaceMeshSnapshot


FACE_NEUTRAL_GEOMETRY_FORMAT = "adv_py_face_neutral_geometry"
FACE_NEUTRAL_GEOMETRY_MAX_BYTES = 128_000_000


@dataclass(frozen=True, slots=True)
class FaceNeutralGeometry:
    mesh: FaceMeshSnapshot
    triangles: tuple[tuple[int, int, int], ...]
    up_axis: str = ""
    linear_unit: str = ""

    def __post_init__(self):
        if (not isinstance(self.mesh, FaceMeshSnapshot)
                or self.mesh.vertex_count > 1_000_000
                or not isinstance(self.triangles, tuple)
                or not 1 <= len(self.triangles) <= 2_000_000):
            raise ValueError("面部中性几何的网格或三角面数量无效")
        for row in self.triangles:
            if (not isinstance(row, tuple) or len(row) != 3
                    or any(type(index) is not int
                           or not 0 <= index < self.mesh.vertex_count
                           for index in row)
                    or len(set(row)) != 3):
                raise ValueError("面部中性几何包含无效三角面")
        if (self.up_axis, self.linear_unit) != ("", "") and (
                self.up_axis not in ("y", "z")
                or self.linear_unit not in ("cm", "m")):
            raise ValueError("面部中性几何的坐标轴或长度单位无效")


def face_neutral_geometry_to_json(geometry: FaceNeutralGeometry) -> str:
    if not isinstance(geometry, FaceNeutralGeometry):
        raise ValueError("面部中性几何对象无效")
    mesh = geometry.mesh
    payload = {"path": mesh.path, "vertex_count": mesh.vertex_count,
        "topology_digest": mesh.topology_digest,
        "position_digest": mesh.position_digest,
        "points": [list(point) for point in mesh.points],
        "triangles": [list(row) for row in geometry.triangles],
        "up_axis": geometry.up_axis, "linear_unit": geometry.linear_unit}
    text = canonical({"format": FACE_NEUTRAL_GEOMETRY_FORMAT,
        "version": 2, "payload": payload, "digest": digest(payload)})
    if len(text.encode("utf-8")) + 1 > FACE_NEUTRAL_GEOMETRY_MAX_BYTES:
        raise ValueError("面部中性几何文档超过 128 MB")
    return text


def face_neutral_geometry_from_json(source: str) -> FaceNeutralGeometry:
    document = exact(safe_json(source,
        max_bytes=FACE_NEUTRAL_GEOMETRY_MAX_BYTES),
        ("format", "version", "payload", "digest"))
    if (document["format"] != FACE_NEUTRAL_GEOMETRY_FORMAT
            or type(document["version"]) is not int
            or document["version"] not in (1, 2)):
        raise ValueError("面部中性几何文档格式或版本无效")
    fields = ("path", "vertex_count", "topology_digest", "position_digest",
              "points", "triangles")
    payload = exact(document["payload"], fields + (("up_axis", "linear_unit")
        if document["version"] == 2 else ()))
    if digest(payload) != document["digest"]:
        raise ValueError("面部中性几何文档内容摘要不匹配")
    if (not isinstance(payload["topology_digest"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", payload["topology_digest"])
            or not isinstance(payload["points"], list)
            or not isinstance(payload["triangles"], list)):
        raise ValueError("面部中性几何文档结构无效")
    try:
        mesh = FaceMeshSnapshot(payload["path"], payload["vertex_count"],
            payload["topology_digest"],
            tuple(tuple(point) for point in payload["points"]))
        triangles = tuple(tuple(row) for row in payload["triangles"])
        geometry = FaceNeutralGeometry(mesh, triangles,
            payload.get("up_axis", ""), payload.get("linear_unit", ""))
    except (TypeError, ValueError, KeyError) as error:
        raise ValueError("面部中性几何文档结构无效") from error
    if mesh.position_digest != payload["position_digest"]:
        raise ValueError("面部中性几何的位置摘要不匹配")
    return geometry
