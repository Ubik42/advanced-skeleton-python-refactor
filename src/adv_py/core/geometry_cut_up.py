"""Partition skinned polygon faces by summed joint influence."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CutUpPiece:
    joint: str
    faces: tuple[int, ...]


@dataclass(frozen=True)
class CutUpMeshPlan:
    mesh: str
    face_count: int
    pieces: tuple[CutUpPiece, ...]


def plan_cut_up_mesh(mesh: str, influences: tuple[str, ...],
                     faces: tuple[tuple[int, ...], ...],
                     weights: tuple[tuple[float, ...], ...],
                     anchors: tuple[str, ...]) -> CutUpMeshPlan:
    if (not mesh or not influences or not faces or not weights
            or len(influences) != len(anchors)
            or len(set(influences)) != len(influences)
            or any(len(row) != len(influences) for row in weights)):
        raise ValueError("Skin Cut-Up 蒙皮输入不完整")
    grouped: dict[str, list[int]] = {}
    for face_index, vertices in enumerate(faces):
        if not vertices or any(index < 0 or index >= len(weights)
                               for index in vertices):
            raise ValueError("Skin Cut-Up 面顶点索引无效：" + mesh)
        sums = [sum(weights[index][joint_index] for index in vertices)
                for joint_index in range(len(influences))]
        if max(sums) <= 0:
            raise ValueError("Skin Cut-Up 面没有非零蒙皮权重：" + mesh)
        dominant = max(range(len(influences)),
                       key=lambda index: (sums[index], -index))
        joint = anchors[dominant]
        if not joint:
            raise ValueError("Skin Cut-Up 影响关节缺少控制来源")
        grouped.setdefault(joint, []).append(face_index)
    return CutUpMeshPlan(mesh, len(faces), tuple(
        CutUpPiece(joint, tuple(indices))
        for joint, indices in grouped.items()))
