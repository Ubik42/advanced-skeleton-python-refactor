"""Explicit face target geometry and semantic expression/viseme channels."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from math import isfinite
import re


class FaceShapeKind(str, Enum):
    EXPRESSION = "expression"
    VISEME = "viseme"


@dataclass(frozen=True, slots=True)
class FaceTarget:
    name: str
    kind: FaceShapeKind
    mesh: str

    def __post_init__(self):
        if (not isinstance(self.name, str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", self.name)
                or not isinstance(self.kind, FaceShapeKind)
                or not isinstance(self.mesh, str) or not self.mesh.startswith("|")):
            raise ValueError("面部目标名称、类别或网格路径无效")


@dataclass(frozen=True, slots=True)
class FaceMeshSnapshot:
    path: str
    vertex_count: int
    topology_digest: str
    points: tuple[tuple[float, float, float], ...]

    def __post_init__(self):
        if (not isinstance(self.path, str) or not self.path.startswith("|")
                or self.vertex_count < 3 or len(self.points) != self.vertex_count
                or len(self.topology_digest) != 64
                or any(len(point) != 3 or any(not isfinite(v) for v in point)
                       for point in self.points)):
            raise ValueError("面部网格快照无效")

    @property
    def position_digest(self) -> str:
        payload = repr(self.points).encode("ascii")
        return sha256(payload).hexdigest()


def validate_face_targets(
    neutral: FaceMeshSnapshot,
    targets: tuple[tuple[FaceTarget, FaceMeshSnapshot], ...],
) -> None:
    if not targets or len(targets) > 128:
        raise ValueError("面部目标数量须为 1 至 128")
    names = [target.name for target, _ in targets]
    paths = [target.mesh for target, _ in targets]
    if len(set(names)) != len(names) or len(set(paths)) != len(paths):
        raise ValueError("面部目标名称或网格重复")
    if neutral.path in paths:
        raise ValueError("中性网格不能同时作为面部目标")
    for target, mesh in targets:
        if mesh.path != target.mesh or mesh.vertex_count != neutral.vertex_count:
            raise ValueError("面部目标网格路径或顶点数量不一致：" + target.name)
        if mesh.topology_digest != neutral.topology_digest:
            raise ValueError("面部目标网格拓扑不一致：" + target.name)
        if max(abs(a - b) for left, right in zip(neutral.points, mesh.points)
               for a, b in zip(left, right)) <= 1e-7:
            raise ValueError("面部目标没有有效形变：" + target.name)
