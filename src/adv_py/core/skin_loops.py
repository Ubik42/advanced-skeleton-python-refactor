"""Closed edge-loop sets used by the original SkinLoops workflow."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkinLoopSpec:
    set_name: str
    parent_set: str
    mesh: str
    edge_ids: tuple[int, ...]
    control: str
    deform_joint: str


def validate_closed_loop(
    edges: tuple[tuple[int, int, int], ...],
) -> tuple[int, ...]:
    if len(edges) < 3 or len({row[0] for row in edges}) != len(edges):
        raise ValueError("SkinLoop 至少需要三条不重复的网格边")
    degrees: dict[int, int] = {}
    for _, a, b in edges:
        if a == b or min(a, b) < 0:
            raise ValueError("SkinLoop 存在无效网格边")
        degrees[a] = degrees.get(a, 0) + 1
        degrees[b] = degrees.get(b, 0) + 1
    if any(degree != 2 for degree in degrees.values()):
        raise ValueError("所选网格边没有构成完整闭环")
    return tuple(sorted(row[0] for row in edges))


def plan_skin_loops(
    parent_set: str, mesh: str, control: str, deform_joint: str,
    edges: tuple[tuple[int, int, int], ...],
    mirrored: tuple[str, str, tuple[tuple[int, int, int], ...]] | None = None,
) -> tuple[SkinLoopSpec, ...]:
    if not all((parent_set, mesh, control, deform_joint)):
        raise ValueError("SkinLoop 缺少网格或控制关节")
    suffix = deform_joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    namespace = parent_set.rsplit(":", 1)[0] + ":" if ":" in parent_set else ""
    result = [SkinLoopSpec(namespace + "SkinLoops_" + suffix, parent_set,
                           mesh, validate_closed_loop(edges), control,
                           deform_joint)]
    if mirrored is not None:
        mirror_control, mirror_joint, mirror_edges = mirrored
        if not mirror_control or not mirror_joint:
            raise ValueError("镜像 SkinLoop 缺少对侧控制器")
        mirror_suffix = mirror_joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        result.append(SkinLoopSpec(
            namespace + "SkinLoops_" + mirror_suffix, parent_set, mesh,
            validate_closed_loop(mirror_edges), mirror_control,
            mirror_joint))
    if len({item.set_name for item in result}) != len(result):
        raise ValueError("SkinLoop 两侧名称重复")
    return tuple(result)
