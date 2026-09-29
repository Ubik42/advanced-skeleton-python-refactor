"""Original SkinCage scene contracts shared by its deform operations."""
from __future__ import annotations

from dataclasses import dataclass
import re


SKIN_CAGE_NODES = (
    "skinCage", "SkinSub", "Cages", "MeshGeometry", "MeshCurves",
    "NurbsGeometry", "SkinCage", "SkinCurves1", "SkinCurves2",
    "SkinCageCurvesSet", "skinClusterSkinCage",
)


@dataclass(frozen=True, slots=True)
class SkinCageCopyTarget:
    mesh: str
    components: tuple[str, ...] = ()


_PART = re.compile(r"Part\d+_[RLM]$")


@dataclass(frozen=True, slots=True)
class SkinCageChain:
    joints: tuple[str, ...]
    parts: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class SkinCageBuildPlan:
    root: str
    chains: tuple[SkinCageChain, ...]
    influences: tuple[str, ...]
    branch_joints: tuple[str, ...]


def plan_skin_cage_build(root: str, children: dict[str, tuple[str, ...]],
                         positions: dict[str, tuple[float, float, float]],
                         ) -> SkinCageBuildPlan:
    """Partition the deformation tree like asCreateMainBox/asRlaChild.

    Part joints stay between adjacent main profiles and receive twist profiles.
    Branches get their own chain and are identified for bridge generation.
    """
    if root not in positions:
        raise ValueError("DeformationSystem 没有根关节")
    if set(children) != set(positions):
        raise ValueError("变形关节的子节点与位置数据不完整")
    for parent, kids in children.items():
        if any(child not in positions for child in kids):
            raise ValueError("变形关节引用了未知子关节：" + parent)

    def primary(joint: str) -> str | None:
        kids = children[joint]
        if not kids:
            return None
        leaf = joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        preferences = (("Root", "Spine"), ("Head", "Head"),
                       ("Ankle", "Toes"), ("Toes", "Toes"))
        for prefix, preferred in preferences:
            if leaf.startswith(prefix):
                match = next((kid for kid in kids if kid.rsplit("|", 1)[-1]
                              .rsplit(":", 1)[-1].startswith(preferred)), None)
                if match:
                    return match
        center = abs(positions[joint][0]) < 0.01
        same_side = [kid for kid in kids
                     if (abs(positions[kid][0]) < 0.01) == center]
        return (same_side or list(kids))[0]

    chains: list[SkinCageChain] = []
    branch_joints: list[str] = []
    visited: set[str] = set()

    def walk(start: str) -> None:
        current = start
        main: list[str] = []
        gaps: list[tuple[str, ...]] = []
        pending_parts: list[str] = []
        while current:
            if current in visited:
                raise ValueError("变形关节树出现环或重复分支")
            visited.add(current)
            if _PART.search(current.rsplit("|", 1)[-1]):
                pending_parts.append(current)
            else:
                if main:
                    gaps.append(tuple(pending_parts))
                pending_parts.clear()
                main.append(current)
            kids = children[current]
            if len(kids) > 1:
                branch_joints.append(current)
            chosen = primary(current)
            for child in kids:
                if child != chosen:
                    walk(child)
            current = chosen
        if main:
            chains.append(SkinCageChain(tuple(main), tuple(gaps)))

    walk(root)
    if len(visited) != len(positions):
        raise ValueError("变形系统包含未连接的关节")
    return SkinCageBuildPlan(root, tuple(chains), tuple(positions),
                             tuple(branch_joints))


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
