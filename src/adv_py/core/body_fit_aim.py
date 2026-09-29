"""Plan ADV's per-Fit-joint Aim targets against already planned FK layers."""
from __future__ import annotations

from dataclasses import dataclass

from .body_limb_controls import BodyLimbFkControlSpec
from .body_skeleton import BodySkeletonSnapshot
from .fit_hierarchy import FitHierarchySnapshot
from .fit_metadata import FitJointField, FitJointMetadata


Vector3 = tuple[float, float, float]
AIM_SYSTEM = "|Group|MotionSystem|AimSystem"


@dataclass(frozen=True, slots=True)
class BodyFitAimSideSpec:
    suffix: str
    target_offset: str
    target_control: str
    fk_offset: str
    fk_aim: str
    fk_control: str
    bind_position: Vector3

    @property
    def aim_matrix_name(self) -> str:
        return "AdvPy_FKAim" + self.fk_control.rsplit("|", 1)[-1] + "AM"

    @property
    def local_matrix_name(self) -> str:
        return "AdvPy_FKAim" + self.fk_control.rsplit("|", 1)[-1] + "MM"


@dataclass(frozen=True, slots=True)
class BodyFitAimSpec:
    fit_joint: str
    stem: str
    root: str
    offset: str
    follow: str
    center_control: str
    center_position: Vector3
    control_radius: float
    follow_joint: str
    sides: tuple[BodyFitAimSideSpec, ...]

    @property
    def follow_blend_name(self) -> str:
        return "AdvPy_Aim" + self.stem + "FollowBM"

    @property
    def follow_target_name(self) -> str:
        return "AdvPy_Aim" + self.stem + "FollowTargetMM"

    @property
    def follow_static_name(self) -> str:
        return "AdvPy_Aim" + self.stem + "FollowStaticMM"

    @property
    def follow_local_name(self) -> str:
        return "AdvPy_Aim" + self.stem + "FollowLocalMM"

    @property
    def follow_weight_name(self) -> str:
        return "AdvPy_Aim" + self.stem + "FollowWeightMDL"

    @property
    def node_names(self) -> tuple[str, ...]:
        paths = (self.root, self.offset, self.follow, self.center_control)
        paths += tuple(path for side in self.sides if side.suffix != "M"
                       for path in (side.target_offset, side.target_control))
        matrix_nodes = tuple(name for side in self.sides for name in (
            side.aim_matrix_name, side.local_matrix_name,
            side.local_matrix_name + "DM"))
        follow_nodes = (self.follow_blend_name, self.follow_target_name,
                        self.follow_static_name, self.follow_local_name,
                        self.follow_local_name + "DM", self.follow_weight_name)
        return (tuple(path.rsplit("|", 1)[-1] for path in paths)
                + matrix_nodes + follow_nodes)


def plan_body_fit_aim(
    hierarchy: FitHierarchySnapshot,
    metadata: tuple[FitJointMetadata, ...],
    body: BodySkeletonSnapshot,
    controls: tuple[BodyLimbFkControlSpec, ...],
) -> tuple[BodyFitAimSpec, ...]:
    """Match each marked, non-terminal Fit joint to its mirrored FK controls."""
    nodes = {joint.path: joint for joint in hierarchy.joints}
    if len(nodes) != len(hierarchy.joints):
        raise ValueError("Fit Aim 来源层级包含重复关节路径")
    children = {joint.dag_parent for joint in hierarchy.joints}
    by_name = {joint.name: joint for joint in body.joints}
    if len(by_name) != len(body.joints):
        raise ValueError("Fit Aim Body 关节短名不唯一")
    if len({item.joint for item in metadata}) != len(metadata):
        raise ValueError("Fit Aim 元数据来源关节重复")
    marked = {
        item.joint for item in metadata
        if FitJointField.AIM in item.present_fields
        and item.joint in children
    }
    marked_names = {nodes[path].short_name.rsplit(":", 1)[-1]
                    for path in marked if path in nodes}
    by_stem: dict[str, list[BodyLimbFkControlSpec]] = {}
    for control in controls:
        if control.aim_path is None:
            continue
        matched = set(control.fit_joint_names) & marked_names
        if len(matched) != 1:
            raise ValueError("Fit Aim 控制必须有唯一已标记的来源关节")
        by_stem.setdefault(next(iter(matched)), []).append(control)
    scale = max(0.01, max((node.world_position[1]
                           for node in hierarchy.joints), default=0.0)
                / 17.176163)
    result: list[BodyFitAimSpec] = []
    covered: set[str] = set()
    for source_path in sorted(marked):
        source = nodes.get(source_path)
        if source is None:
            raise ValueError("Fit Aim 来源关节不在当前层级：" + source_path)
        stem = source.short_name.rsplit(":", 1)[-1]
        matches = by_stem.get(stem, [])
        if not matches:
            raise ValueError("Fit Aim 缺少对应 FK 控制：" + source_path)
        if stem in covered or len({item.side.value for item in matches}) != len(matches):
            raise ValueError("Fit Aim 来源或左右 FK 控制重复：" + stem)
        covered.add(stem)
        parent = nodes.get(source.dag_parent)
        if parent is None:
            raise ValueError("Fit Aim 来源缺少父关节：" + source_path)
        parent_name = parent.short_name.rsplit(":", 1)[-1]
        first_side = "R" if any(item.side.value == "R" for item in matches) else matches[0].side.value
        follow = by_name.get(parent_name + "_" + first_side) or by_name.get(parent_name + "_M")
        if follow is None:
            raise ValueError("Fit Aim 父关节没有对应 Body 关节：" + parent_name)
        root = AIM_SYSTEM + "|AdvPy_Aim" + stem
        offset = root + "|AdvPy_AimOffset" + stem
        follow_path = offset + "|AdvPy_AimFollow" + stem
        center = follow_path + "|AdvPy_Aim" + stem + "_M"
        sides = tuple(BodyFitAimSideSpec(
            suffix=item.side.value,
            target_offset=(center + "|AdvPy_AimOffset" + stem + "_" + item.side.value
                           if item.side.value != "M" else ""),
            target_control=(center + "|AdvPy_AimOffset" + stem + "_" + item.side.value
                            + "|AdvPy_Aim" + stem + "_" + item.side.value
                            if item.side.value != "M" else center),
            fk_offset=item.offset_path,
            fk_aim=item.aim_path or "",
            fk_control=item.control_path,
            bind_position=item.world_position,
        ) for item in sorted(matches, key=lambda item: item.side.value))
        result.append(BodyFitAimSpec(
            fit_joint=source_path, stem=stem, root=root,
            offset=offset, follow=follow_path,
            center_control=center,
            center_position=(0.0, source.world_position[1],
                             source.world_position[2] + 2.0 * scale),
            control_radius=scale / 3.0,
            follow_joint=follow.path,
            sides=sides))
    if set(by_stem) != covered:
        raise ValueError("FK Aim 层与 Fit Aim 标记不一致")
    return tuple(result)
