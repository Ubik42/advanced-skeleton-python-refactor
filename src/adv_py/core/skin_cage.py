"""Original SkinCage scene contracts shared by its deform operations."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
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


@dataclass(frozen=True, slots=True)
class SkinCageMirrorPair:
    source: str
    target: str


@dataclass(frozen=True, slots=True)
class SkinCageWidthInput:
    profile: str
    point_constraint: str
    scale_constraint: str
    main_point_alias: str
    other_point_alias: str
    main_scale_alias: str
    other_scale_alias: str
    edge_a: float
    edge_b: float
    target_distance: float


@dataclass(frozen=True, slots=True)
class SkinCageWidthSpec:
    source: SkinCageWidthInput
    other_weight: float


@dataclass(frozen=True, slots=True)
class SkinCageGroinLocators:
    start: tuple[float, float, float]
    side: tuple[float, float, float]


def plan_groin_locators(root: tuple[float, float, float],
                        cage_corner: tuple[float, float, float],
                        ) -> SkinCageGroinLocators:
    if len(root) != 3 or len(cage_corner) != 3 or not all(
            isfinite(value) for value in (*root, *cage_corner)):
        raise ValueError("Root 和 SkinCage 截面位置必须是有效三维坐标")
    return SkinCageGroinLocators(
        (0.0, root[1] * 0.9, root[2]),
        (cage_corner[0], cage_corner[1] * 1.03, root[2]))


@dataclass(frozen=True, slots=True)
class SkinCageGroinAdjustment:
    start_y: float
    side_y: float


@dataclass(frozen=True, slots=True)
class SkinCageProfileShape:
    name: str
    points: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True, slots=True)
class SkinCageCurveDeletePlan:
    nodes: tuple[str, ...]


def plan_skin_cage_curve_delete(
        existing: tuple[str, ...]) -> SkinCageCurveDeletePlan:
    if "MeshCurves" not in existing or "MeshGeometry" not in existing:
        raise ValueError("SkinCage 编辑曲线或管体组不存在")
    allowed = ("SkinCurves1", "SkinCurves2", "MeshGeometry",
               "MeshCurves", "NurbsGeometry")
    return SkinCageCurveDeletePlan(tuple(node for node in allowed
                                          if node in existing))


def plan_skin_cage_profile_restore(
        profiles: tuple[SkinCageProfileShape, ...],
        ) -> tuple[SkinCageProfileShape, ...]:
    if not profiles:
        raise ValueError("已有 SkinCage 缺少可恢复的截面曲线")
    names = set()
    for profile in profiles:
        if profile.name in names or not profile.name.endswith("Profile"):
            raise ValueError("SkinCage 截面名称重复或无效：" + profile.name)
        names.add(profile.name)
        if len(profile.points) < 4 or any(
                len(point) != 3 or not all(isfinite(value)
                                           for value in point)
                for point in profile.points):
            raise ValueError("SkinCage 截面控制点无效：" + profile.name)
    return profiles


def plan_groin_adjustment(start: tuple[float, float, float],
                          side: tuple[float, float, float],
                          ) -> SkinCageGroinAdjustment:
    if len(start) != 3 or len(side) != 3 or not all(
            isfinite(value) for value in (*start, *side)):
        raise ValueError("腹股沟定位器位置无效")
    return SkinCageGroinAdjustment(start[1], side[1])


def plan_skin_cage_width(rows: tuple[SkinCageWidthInput, ...]
                         ) -> tuple[SkinCageWidthSpec, ...]:
    if not rows:
        raise ValueError("没有可调整宽度的 SkinCage 起始或末端截面")
    result = []
    seen = set()
    for row in rows:
        if row.profile in seen:
            raise ValueError("SkinCage 宽度截面重复：" + row.profile)
        seen.add(row.profile)
        values = (row.edge_a, row.edge_b, row.target_distance)
        if any(not isfinite(value) or value <= 0 for value in values):
            raise ValueError("SkinCage 截面尺寸或关节距离无效：" + row.profile)
        # MEL: ((curveHeight + curveWidth) / 2 / 2) / toParentDist.
        weight = min((row.edge_a + row.edge_b) /
                     (4.0 * row.target_distance), 0.45)
        result.append(SkinCageWidthSpec(row, weight))
    return tuple(result)


def plan_skin_cage_mirror(profiles: tuple[str, ...],
                          source_side: str,
                          ) -> tuple[SkinCageMirrorPair, ...]:
    if source_side not in ("L", "R"):
        raise ValueError("SkinCage 镜像来源侧必须是 L 或 R")
    source_marker = "_" + source_side + "_"
    target_marker = "_" + ("R" if source_side == "L" else "L") + "_"
    available = set(profiles)
    pairs = []
    for profile in profiles:
        leaf = profile.rsplit("|", 1)[-1]
        if source_marker not in leaf:
            continue
        target_leaf = leaf.replace(source_marker, target_marker, 1)
        target = profile[:-len(leaf)] + target_leaf
        if target in available:
            pairs.append(SkinCageMirrorPair(profile, target))
    if not pairs:
        raise ValueError("SkinCage 曲线集合没有可镜像的左右截面")
    return tuple(pairs)


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
