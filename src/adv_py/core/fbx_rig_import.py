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
class FBXRigControlLink:
    control_name: str
    source_joint: str
    side: str


@dataclass(frozen=True, slots=True)
class FBXRigResolvedControlLink:
    control_name: str
    source_joint: str
    deform_driver_name: str


@dataclass(frozen=True, slots=True)
class FBXRigControlTransferPlan:
    links: tuple[FBXRigResolvedControlLink, ...]

    @property
    def bake_control_names(self) -> tuple[str, ...]:
        return tuple(link.control_name for link in self.links)


@dataclass(frozen=True, slots=True)
class FBXRigImportPlan:
    top_joint: str
    root_joint: str
    game_root_joint: str | None
    scale: float
    side_threshold_cm: float
    fit_guides: tuple[FBXRigFitGuide, ...]
    mirror_pairs: tuple[FBXRigMirrorPair, ...]
    candidate_control_links: tuple[FBXRigControlLink, ...]
    inferred_labels: tuple[tuple[str, str], ...]
    first_bake_frame: int | None
    last_bake_frame: int | None
    names_requiring_underscore_removal: tuple[str, ...]
    collapsed_fit_source_joints: tuple[str, ...] = ()
    bind_pose_joints: tuple[FBXRigSourceJoint, ...] = ()


def plan_fbx_control_transfer(
    plan: FBXRigImportPlan,
    control_names: tuple[str, ...],
    deform_joint_names: tuple[str, ...],
) -> FBXRigControlTransferPlan:
    """Resolve the controls actually built before making either constraint set."""
    if (len(set(control_names)) != len(control_names)
            or len(set(deform_joint_names)) != len(deform_joint_names)):
        raise ValueError("FBX rig 构建结果包含重复控制器或变形关节")
    controls = set(control_names)
    deform = set(deform_joint_names)
    if "FKRoot_M" not in controls:
        raise ValueError("FBX rig 缺少 Root FK 控制器")
    links = []
    for candidate in plan.candidate_control_links:
        if candidate.control_name not in controls:
            continue
        driver = ("FKRoot_M" if candidate.control_name == "FKRoot_M"
                  else candidate.control_name.removeprefix("FK"))
        if candidate.control_name != "FKRoot_M" and driver not in deform:
            raise ValueError("FBX rig 控制器缺少同名变形关节：" + driver)
        links.append(FBXRigResolvedControlLink(
            candidate.control_name, candidate.source_joint, driver))
    if len({link.source_joint for link in links}) != len(links):
        raise ValueError("FBX rig 多个控制器指向同一来源关节")
    return FBXRigControlTransferPlan(tuple(links))


def fbx_bind_pose_matches(
    expected: tuple[FBXRigSourceJoint, ...],
    actual: tuple[FBXRigSourceJoint, ...],
    *,
    tolerance: float = 1e-4,
) -> bool:
    """Require the prepared scene to match the read-only bind-pose capture."""
    if not isfinite(tolerance) or tolerance < 0:
        raise ValueError("FBX rig 绑定姿态容差无效")
    by_path = {joint.path: joint for joint in actual}
    if len(by_path) != len(actual) or len(expected) != len(actual):
        return False
    return all(
        (candidate := by_path.get(joint.path)) is not None
        and candidate.name == joint.name
        and candidate.parent == joint.parent
        and len(candidate.world_position) == 3
        and all(abs(before - after) <= tolerance
                for before, after in zip(joint.world_position,
                                         candidate.world_position))
        for joint in expected
    )


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
    # 6.925 removes direct Fit Root children shorter than the side threshold,
    # then reparents their children to Root. The source skeleton stays intact.
    collapsed = frozenset(
        joint.path for joint in kept
        if joint.parent == root.path
        and dist(joint.world_position, root.world_position) < threshold
    )
    names = {}
    guides = [FBXRigFitGuide("Root", None, root.path,
                             root.world_position, False)]
    for joint in kept:
        if joint.path in collapsed:
            continue
        name = joint.name.rsplit(":", 1)[-1].replace("_", "")
        if not name or name in names or name == "Root":
            raise ValueError("FBX rig 关节映射到重复 Fit 名称：" + name)
        names[joint.path] = name
        parent = joint.parent
        while parent not in names and parent != root.path:
            if parent not in by_path:
                raise ValueError("FBX rig Fit 父级无法解析：" + name)
            parent = by_path[parent].parent
        parent_name = "Root" if parent == root.path else names[parent]
        guides.append(FBXRigFitGuide(
            name, parent_name, joint.path, joint.world_position,
            not children[joint.path]))
    pairs = []
    if not left and any(joint.world_position[0] < -threshold for joint in kept):
        raise ValueError("FBX rig 右侧骨架缺少左侧镜像关节")
    for joint in kept:
        if joint.path in collapsed:
            continue
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
    pair_by_right = {pair.right_joint: pair.left_joint for pair in pairs}
    control_links = [FBXRigControlLink("FKRoot_M", root.path, "M")]
    for joint in kept:
        if joint.path in collapsed:
            continue
        name = names[joint.path]
        right_side = joint.world_position[0] < -threshold
        side = "R" if right_side else "M"
        control_links.append(FBXRigControlLink(
            "FK" + name + "_" + side, joint.path, side))
        if right_side:
            left_path = pair_by_right.get(joint.path)
            if left_path is None:
                raise ValueError("FBX rig 右侧关节缺少镜像目标：" + name)
            control_links.append(FBXRigControlLink(
                "FK" + name + "_L", left_path, "L"))
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
        tuple(guides), tuple(pairs), tuple(control_links), tuple(labels),
        -1 if last_frame is not None else None, last_frame,
        tuple(joint.path for joint in joints if "_" in joint.name),
        tuple(joint.path for joint in kept if joint.path in collapsed),
        joints)
