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
class SkinCageBranch:
    parent: str
    child: str


@dataclass(frozen=True, slots=True)
class SkinCageBuildPlan:
    root: str
    chains: tuple[SkinCageChain, ...]
    influences: tuple[str, ...]
    branches: tuple[SkinCageBranch, ...]


@dataclass(frozen=True, slots=True)
class SkinCageBranchLayout:
    faces: tuple[tuple[tuple[str, int], ...], ...]
    reverse_faces: tuple[int, ...] = ()


def special_skin_cage_branch(parent: str,
                             children: tuple[str, ...],
                             ) -> SkinCageBranchLayout | None:
    """Original 6.925 facet connectivity for its three named branch cases.

    Curve tokens omit Profile and use ``Joint_side_start`` notation. The
    repeated Chest CV in the MEL source is collapsed to one vertex.
    """
    raw: tuple[str, ...]
    reversed_faces: tuple[int, ...] = ()
    if parent == "Root_M" and {
            "RootPart1_M", "Hip_R", "Hip_L"}.issubset(children):
        raw = (
            "Hip_R_start:3 Hip_R_start:2 Hip_L_start:0 Hip_L_start:1 Root_M_middle:3 Root_M_middle:2",
            "Hip_R_start:0 Hip_R_start:1 Hip_L_start:3 Hip_L_start:2 Root_M_middle:0 Root_M_middle:1",
            "Hip_R_start:0 Hip_R_start:3 Root_M_middle:2 Root_M_middle:1",
            "Hip_L_start:1 Hip_L_start:2 Root_M_middle:4 Root_M_middle:3",
        )
        reversed_faces = (1,)
    elif parent == "Chest_M" and {
            "Neck_M", "Shoulder_R", "Shoulder_L"}.issubset(children):
        raw = (
            "Chest_M_middle:3 Shoulder_L_start:0 Shoulder_L_start:1 Neck_M_start:3",
            "Neck_M_start:3 Neck_M_start:2 Chest_M_middle:2 Chest_M_middle:3",
            "Chest_M_middle:2 Neck_M_start:2 Shoulder_R_start:3 Shoulder_R_start:2",
            "Chest_M_middle:1 Shoulder_R_start:1 Shoulder_R_start:0 Neck_M_start:1",
            "Neck_M_start:1 Neck_M_start:0 Chest_M_middle:0 Chest_M_middle:1",
            "Chest_M_middle:0 Neck_M_start:0 Shoulder_L_start:2 Shoulder_L_start:3",
            "Shoulder_R_start:2 Shoulder_R_start:1 Chest_M_middle:1 Chest_M_middle:2",
            "Shoulder_L_start:3 Shoulder_L_start:0 Chest_M_middle:3 Chest_M_middle:0",
            "Neck_M_start:2 Neck_M_start:1 Shoulder_R_start:0 Shoulder_R_start:3",
            "Neck_M_start:0 Neck_M_start:3 Shoulder_L_start:1 Shoulder_L_start:2",
        )
    elif parent in ("Wrist_R", "Wrist_L"):
        side = parent[-2:]
        expected = {prefix + side for prefix in (
            "IndexFinger1", "MiddleFinger1", "RingFinger1",
            "PinkyFinger1", "ThumbFinger2")}
        if not expected.issubset(children):
            return None
        raw = (
            "Wrist_end:3 Wrist_end:0 MiddleFinger1_start:0 MiddleFinger1_start:3",
            "Wrist_end:1 Wrist_end:2 MiddleFinger1_start:2 MiddleFinger1_start:1",
            "Wrist_end:0 Wrist_end:1 PinkyFinger1_start:1 PinkyFinger1_start:0",
            "Wrist_end:0 MiddleFinger1_start:0 RingFinger1_start:3 RingFinger1_start:0 PinkyFinger1_start:3 PinkyFinger1_start:0",
            "Wrist_end:1 MiddleFinger1_start:1 RingFinger1_start:2 RingFinger1_start:1 PinkyFinger1_start:2 PinkyFinger1_start:1",
            "Wrist_end:2 Wrist_end:3 ThumbFinger2_start:0 ThumbFinger2_start:3",
            "Wrist_end:3 ThumbFinger2_start:0 IndexFinger1_start:3 IndexFinger1_start:0 MiddleFinger1_start:3",
            "Wrist_end:2 ThumbFinger2_start:3 ThumbFinger2_start:2",
            "IndexFinger1_start:3 IndexFinger1_start:2 ThumbFinger2_start:1 ThumbFinger2_start:0",
            "Wrist_end:2 ThumbFinger2_start:2 ThumbFinger2_start:1",
            "Wrist_end:2 IndexFinger1_start:2 IndexFinger1_start:1 MiddleFinger1_start:2",
        )
        reversed_faces = (3, 6)
        raw = tuple(" ".join(
            name.rsplit(":", 1)[0].replace("_end", side + "_end")
            .replace("_start", side + "_start") + ":" +
            name.rsplit(":", 1)[1] for name in face.split())
                    for face in raw)
    else:
        return None
    faces = tuple(tuple((token.rsplit(":", 1)[0],
                         int(token.rsplit(":", 1)[1]))
                        for token in face.split()) for face in raw)
    return SkinCageBranchLayout(faces, reversed_faces)


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
    branches: list[SkinCageBranch] = []
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
            chosen = primary(current)
            for child in kids:
                if child != chosen:
                    branches.append(SkinCageBranch(current, child))
                    walk(child)
            current = chosen
        if main:
            chains.append(SkinCageChain(tuple(main), tuple(gaps)))

    walk(root)
    if len(visited) != len(positions):
        raise ValueError("变形系统包含未连接的关节")
    return SkinCageBuildPlan(root, tuple(chains), tuple(positions),
                             tuple(branches))


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
