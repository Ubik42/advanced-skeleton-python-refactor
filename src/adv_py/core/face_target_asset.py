"""Portable, versioned sparse sculpt target data for one neutral mesh."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re

from .character_registry import canonical, digest, exact, safe_json
from .face_shapes import (FaceMeshSnapshot, FaceShapeKind, FaceTarget,
                          validate_face_targets)


FACE_TARGET_ASSET_FORMAT = "adv_py_face_target_asset"
FACE_TARGET_ASSET_VERSION = 1
FACE_TARGET_ASSET_MAX_BYTES = 64_000_000


@dataclass(frozen=True, slots=True)
class FaceTargetAsset:
    name: str
    kind: FaceShapeKind
    vertex_count: int
    topology_digest: str
    neutral_position_digest: str
    deltas: tuple[tuple[int, float, float, float], ...]

    def __post_init__(self):
        if (not isinstance(self.name, str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", self.name)
                or not isinstance(self.kind, FaceShapeKind)
                or type(self.vertex_count) is not int
                or not 3 <= self.vertex_count <= 1_000_000
                or any(not isinstance(value, str)
                       or not re.fullmatch(r"[0-9a-f]{64}", value)
                       for value in (self.topology_digest,
                                     self.neutral_position_digest))
                or not isinstance(self.deltas, tuple)
                or not 1 <= len(self.deltas) <= self.vertex_count):
            raise ValueError("面部目标资产的类别、拓扑或稀疏位移无效")
        previous = -1
        for row in self.deltas:
            if (not isinstance(row, tuple) or len(row) != 4
                    or type(row[0]) is not int
                    or not previous < row[0] < self.vertex_count
                    or any(isinstance(value, bool)
                           or not isinstance(value, (int, float))
                           or not isfinite(value) for value in row[1:])
                    or max(abs(value) for value in row[1:]) <= 1e-7):
                raise ValueError("面部目标资产顶点索引或位移无效")
            previous = row[0]

    def points_for(self, neutral: FaceMeshSnapshot) -> tuple[tuple[float, float, float], ...]:
        if (not isinstance(neutral, FaceMeshSnapshot)
                or neutral.vertex_count != self.vertex_count
                or neutral.topology_digest != self.topology_digest
                or neutral.position_digest != self.neutral_position_digest):
            raise ValueError("面部目标资产与中性网格拓扑或基准位置不一致")
        points = list(neutral.points)
        for index, dx, dy, dz in self.deltas:
            x, y, z = points[index]
            point = (x + dx, y + dy, z + dz)
            if not all(isfinite(value) for value in point):
                raise ValueError("面部目标资产生成了非有限顶点位置")
            points[index] = point
        return tuple(points)


def face_target_asset_from_meshes(
    neutral: FaceMeshSnapshot, target: FaceTarget,
    sculpt: FaceMeshSnapshot,
) -> FaceTargetAsset:
    validate_face_targets(neutral, ((target, sculpt),))
    deltas = tuple((index, *(float(a - b) for a, b in zip(actual, base)))
                   for index, (base, actual) in enumerate(zip(neutral.points, sculpt.points))
                   if max(abs(a - b) for a, b in zip(actual, base)) > 1e-7)
    return FaceTargetAsset(target.name, target.kind, neutral.vertex_count,
                           neutral.topology_digest, neutral.position_digest, deltas)


def face_target_asset_to_json(asset: FaceTargetAsset) -> str:
    if not isinstance(asset, FaceTargetAsset):
        raise ValueError("面部目标资产对象无效")
    payload = {"name": asset.name, "kind": asset.kind.value,
        "vertex_count": asset.vertex_count,
        "topology_digest": asset.topology_digest,
        "neutral_position_digest": asset.neutral_position_digest,
        "deltas": [list(row) for row in asset.deltas]}
    text = canonical({"format": FACE_TARGET_ASSET_FORMAT,
        "version": FACE_TARGET_ASSET_VERSION, "payload": payload,
        "digest": digest(payload)})
    if len(text.encode("utf-8")) + 1 > FACE_TARGET_ASSET_MAX_BYTES:
        raise ValueError("面部目标资产文档超过 64 MB")
    return text


def face_target_asset_from_json(source: str) -> FaceTargetAsset:
    document = exact(safe_json(source, max_bytes=FACE_TARGET_ASSET_MAX_BYTES),
                     ("format", "version", "payload", "digest"))
    if (document["format"] != FACE_TARGET_ASSET_FORMAT
            or type(document["version"]) is not int
            or document["version"] != FACE_TARGET_ASSET_VERSION):
        raise ValueError("面部目标资产格式或版本无效")
    payload = exact(document["payload"], ("name", "kind", "vertex_count",
        "topology_digest", "neutral_position_digest", "deltas"))
    if digest(payload) != document["digest"]:
        raise ValueError("面部目标资产内容摘要不匹配")
    try:
        asset = FaceTargetAsset(payload["name"], FaceShapeKind(payload["kind"]),
            payload["vertex_count"], payload["topology_digest"],
            payload["neutral_position_digest"],
            tuple(tuple(row) for row in payload["deltas"]))
        return asset
    except (TypeError, ValueError, KeyError) as error:
        raise ValueError("面部目标资产内容结构无效") from error
