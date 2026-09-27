"""Plan the 6.925 Preparation / FBX rig skeleton interpretation."""
from __future__ import annotations

from dataclasses import dataclass
from math import dist, isfinite


Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class FBXRigSourceJoint:
    path: str
    name: str
    parent: str | None
    world_position: Vector3


@dataclass(frozen=True, slots=True)
class FBXRigFitGuide:
    name: str
    parent: str | None
    source_joint: str
    world_position: Vector3
    end_control: bool


@dataclass(frozen=True, slots=True)
class FBXRigMirrorPair:
    right_joint: str
    left_joint: str
    mirror_distance_cm: float


@dataclass(frozen=True, slots=True)
class FBXRigImportPlan:
    top_joint: str
    root_joint: str
    game_root_joint: str | None
    scale: float
    side_threshold_cm: float
    fit_guides: tuple[FBXRigFitGuide, ...]
    mirror_pairs: tuple[FBXRigMirrorPair, ...]
    inferred_labels: tuple[tuple[str, str], ...]
    first_bake_frame: int | None
    last_bake_frame: int | None
    names_requiring_underscore_removal: tuple[str, ...]


def plan_fbx_rig_import(
    joints: tuple[FBXRigSourceJoint, ...],
    *,
    animation_key_times: tuple[float, ...] = (),
    highest_descendant_y: float | None = None,
) -> FBXRigImportPlan:
    """Interpret a bound source skeleton before any scene renaming or bake."""
    if not joints:
        raise ValueError("FBX rig 没有来源关节")
    by_path = {joint.path: joint for joint in joints}
    if len(by_path) != len(joints):
        raise ValueError("FBX rig 来源关节路径重复")
    roots = [joint for joint in joints if joint.parent is None]
    if len(roots) != 1:
        raise ValueError("FBX rig 需要唯一顶层关节")
    for joint in joints:
        if (not joint.path or not joint.name
                or (joint.parent is not None and joint.parent not in by_path)
                or len(joint.world_position) != 3
                or any(isinstance(value, bool)
                       or not isinstance(value, (int, float))
                       or not isfinite(value)
                       for value in joint.world_position)):
            raise ValueError("FBX rig 关节名称、父级或世界坐标无效")
        seen = {joint.path}
        parent = joint.parent
        while parent is not None:
            if parent in seen:
                raise ValueError("FBX rig 来源关节父链成环")
            seen.add(parent)
            parent = by_path[parent].parent
        if roots[0].path not in seen:
            raise ValueError("FBX rig 来源关节未连接顶层关节")
    if any(isinstance(value, bool)
           or not isinstance(value, (int, float))
           or not isfinite(value) for value in animation_key_times):
        raise ValueError("FBX rig 动画时间含非有限值")
    top = roots[0]
    max_y = (max(joint.world_position[1] for joint in joints)
             if highest_descendant_y is None else highest_descendant_y)
    if (isinstance(max_y, bool) or not isinstance(max_y, (int, float))
            or not isfinite(max_y) or max_y <= 0):
        raise ValueError("FBX rig 来源高度无效")
    scale = max_y / 17.176163
    threshold = scale * .01
    children = {joint.path: tuple(child for child in joints
                if child.parent == joint.path) for joint in joints}
    game_root = None
    root = top
    if all(abs(value) <= 1e-9 for value in top.world_position):
        direct = children[top.path]
        if len(direct) != 1:
            raise ValueError("FBX rig 原点游戏根需要唯一直接子关节")
        game_root, root = top.path, direct[0]
    if not children[root.path]:
        raise ValueError("FBX rig 根关节没有可构建的后代")
    descendants = []
    def visit(parent: str) -> None:
        for child in children[parent]:
            descendants.append(child)
            visit(child.path)
    visit(root.path)
    left = tuple(joint for joint in descendants
                 if joint.world_position[0] > threshold)
    kept = tuple(joint for joint in descendants
                 if joint.world_position[0] <= threshold)
    names = {}
    guides = [FBXRigFitGuide("Root", None, root.path,
                             root.world_position, False)]
    for joint in kept:
        name = joint.name.rsplit(":", 1)[-1].replace("_", "")
        if not name or name in names or name == "Root":
            raise ValueError("FBX rig 关节映射到重复 Fit 名称：" + name)
        names[joint.path] = name
        parent = joint.parent
        while parent not in names and parent != root.path:
            if parent not in by_path:
                raise ValueError("FBX rig Fit 父级无法解析：" + name)
            parent = by_path[parent].parent
        guides.append(FBXRigFitGuide(
            name, "Root" if parent == root.path else names[parent],
            joint.path, joint.world_position, not children[joint.path]))
    pairs = []
    if not left and any(joint.world_position[0] < -threshold for joint in kept):
        raise ValueError("FBX rig 右侧骨架缺少左侧镜像关节")
    for joint in kept:
        x, y, z = joint.world_position
        if x >= -threshold:
            continue
        if not left:
            raise ValueError("FBX rig 缺少左侧关节")
        mirror = (-x, y, z)
        partner = min(left, key=lambda item: (
            dist(mirror, item.world_position), item.path))
        pairs.append(FBXRigMirrorPair(
            joint.path, partner.path,
            dist(mirror, partner.world_position)))
    labels = []
    def unique_match(*tokens: str) -> str | None:
        matches = [name for name in names.values()
                   if any(token in name for token in tokens)]
        return matches[0] if len(matches) == 1 else None
    hip = unique_match("Thigh", "Hip")
    ankle = unique_match("Foot", "Ankle")
    shoulder = unique_match("UpperArm", "Shoulder")
    wrist = unique_match("Hand", "Wrist")
    chest = unique_match("Chest")
    if hip and ankle:
        labels.extend(((hip, "Hip"), (ankle, "Foot")))
    if shoulder and wrist:
        labels.extend(((shoulder, "Shoulder"), (wrist, "Hand")))
    if chest:
        labels.extend(((chest, "Chest"), ("Root", "Root")))
    last_frame = int(max(animation_key_times)) if animation_key_times else None
    if last_frame is not None and last_frame < -1:
        raise ValueError("FBX rig 动画最后一帧早于绑定姿态帧 -1")
    return FBXRigImportPlan(
        top.path, root.path, game_root, scale, threshold,
        tuple(guides), tuple(pairs), tuple(labels),
        -1 if last_frame is not None else None, last_frame,
        tuple(joint.path for joint in joints if "_" in joint.name))
