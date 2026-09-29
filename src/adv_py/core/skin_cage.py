"""Original SkinCage scene contracts shared by its deform operations."""
from __future__ import annotations

from dataclasses import dataclass


SKIN_CAGE_NODES = (
    "skinCage", "SkinSub", "Cages", "MeshGeometry", "MeshCurves",
    "NurbsGeometry", "SkinCage", "SkinCurves1", "SkinCurves2",
    "SkinCageCurvesSet", "skinClusterSkinCage",
)


@dataclass(frozen=True, slots=True)
class SkinCageCopyTarget:
    mesh: str
    components: tuple[str, ...] = ()


def plan_skin_cage_copy(meshes: tuple[str, ...],
                        components: tuple[str, ...] = (),
                        ) -> tuple[SkinCageCopyTarget, ...]:
    if not meshes:
        raise ValueError("请选择要复制 SkinCage 权重的网格")
    if components and len(meshes) != 1:
        raise ValueError("组件复制只能针对同一个网格")
    if len(set(meshes)) != len(meshes):
        raise ValueError("目标网格不能重复")
    return tuple(SkinCageCopyTarget(mesh, components if components else ())
                 for mesh in meshes)
