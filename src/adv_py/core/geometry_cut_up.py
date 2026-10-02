"""Source ControlMeshes partition: face eligibility, last vertex and controls."""
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
                     anchors: tuple[str | None, ...],
                     eligible: tuple[tuple[int,...],...] | None = None) -> CutUpMeshPlan:
    if (not mesh or not influences or not faces or not weights
            or len(influences) != len(anchors)
            or len(set(influences)) != len(influences)
            or any(len(row) != len(influences) for row in weights)):
        raise ValueError("Skin Cut-Up 蒙皮输入不完整")
    if eligible is not None and len(eligible)!=len(faces):
        raise ValueError('Skin Cut-Up 面影响查询数量不符')
    grouped: dict[str, list[int]] = {control:[] for control in dict.fromkeys(anchors) if control}
    for face_index, vertices in enumerate(faces):
        if not vertices or any(index < 0 or index >= len(weights)
                               for index in vertices):
            raise ValueError("Skin Cut-Up 面顶点索引无效：" + mesh)
        candidates=(eligible[face_index] if eligible is not None else tuple(
            index for index in range(len(influences))
            if sum(weights[vertex][index] for vertex in vertices)/len(vertices)>.001))
        if not candidates:continue
        # 8865 clears jointWeights on z==0 inside EACH vertex iteration.
        # Preserve the source's last selected vertex, rather than summing all
        # face weights as the previous reconstruction did.
        last=vertices[-1]
        dominant=max(candidates,key=lambda index:weights[last][index])
        if weights[last][dominant]<=0:continue
        joint = anchors[dominant]
        if not joint:
            raise ValueError("Skin Cut-Up 影响关节缺少控制来源")
        grouped[joint].append(face_index)
    return CutUpMeshPlan(mesh, len(faces), tuple(
        CutUpPiece(joint, tuple(indices))
        for joint, indices in grouped.items() if indices))
