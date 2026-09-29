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


@dataclass(frozen=True, slots=True)
class SkinLoopCopySpec:
    source_mesh: str
    source_skin: str
    target_mesh: str
    target_components: tuple[str, ...]
    target_skin: str | None
    source_influences: tuple[str, ...]
    skinning_method: int


def plan_skin_loop_copy(
    source_mesh: str, source_skin: str,
    source_influences: tuple[str, ...], skinning_method: int,
    targets: tuple[tuple[str, tuple[str, ...], str | None], ...],
) -> tuple[SkinLoopCopySpec, ...]:
    if (not source_mesh or not source_skin or not source_influences
            or len(set(source_influences)) != len(source_influences)
            or skinning_method not in (0, 1, 2)):
        raise ValueError("SkinLoop Copy 的来源蒙皮或关节集合无效")
    if not targets or len({item[0] for item in targets}) != len(targets):
        raise ValueError("SkinLoop Copy 需要不重复的目标网格")
    specs = []
    for mesh, components, skin in targets:
        if (not mesh or mesh == source_mesh
                or (skin is not None and skin == source_skin)
                or any(not component.startswith(mesh + ".")
                       for component in components)):
            raise ValueError("SkinLoop Copy 目标网格或组件无效")
        specs.append(SkinLoopCopySpec(
            source_mesh, source_skin, mesh, components, skin,
            source_influences, skinning_method))
    return tuple(specs)


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
