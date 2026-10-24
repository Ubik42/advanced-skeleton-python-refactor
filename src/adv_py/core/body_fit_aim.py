"""Plan ADV's per-Fit-joint Aim targets against already planned FK layers."""
from __future__ import annotations

from dataclasses import dataclass

from .body_limb_controls import BodyLimbFkControlSpec
from .body_skeleton import BodySkeletonSnapshot
from .fit_hierarchy import FitHierarchySnapshot, fit_build_scale
from .fit_metadata import FitJointField, FitJointMetadata
from .source_fit_identity import source_fit_build_name


Vector3 = tuple[float, float, float]
AIM_SYSTEM = "|Group|MotionSystem|AimSystem"
TRANSLATION = tuple("translate" + axis for axis in "XYZ")
TRANSFORM = tuple(kind + axis for kind in ("translate", "rotate", "scale") for axis in "XYZ")


@dataclass(frozen=True, slots=True)
class BodyFitAimLayout:
    stem: str
    center_attributes: tuple[str, ...]
    side_channels: tuple[tuple[str, tuple[str, ...]], ...]


def capture_body_fit_aim_layouts(channels):
    """Recover the actual saved channel order, including older TR/TRS sides."""
    centers, sides, order = {}, {}, []
    for channel in channels:
        parts = channel.key.split(".")
        if parts[:2] not in (["generic", "aim"], ["fit", "aim"]):
            continue
        stem = parts[2]
        if stem not in order:
            order.append(stem)
        if len(parts) == 4 or len(parts) == 5 and parts[3] == "center":
            centers.setdefault(stem, []).append(channel.attribute)
        elif len(parts) == 5 and parts[3] in ("R", "L"):
            sides.setdefault(stem, {}).setdefault(parts[3], []).append(channel.attribute)
        else:
            raise ValueError("保存的 Fit Aim 通道键无效：" + channel.key)
    result = []
    for stem in order:
        center = tuple(centers.get(stem, ()))
        side_rows = tuple((side, tuple(attrs)) for side, attrs in sides.get(stem, {}).items())
        for attributes, allowed in ((center, (*TRANSFORM, "follow")),
                                    *((attrs, TRANSFORM) for _, attrs in side_rows)):
            if (len(attributes) != len(set(attributes)) or not set(attributes) <= set(allowed)
                    or not set(TRANSLATION) <= set(attributes)):
                raise ValueError("保存的 Fit Aim 通道范围无效：" + stem)
        if "follow" not in center:
            raise ValueError("保存的 Fit Aim 缺少中央随动通道：" + stem)
        result.append(BodyFitAimLayout(stem, center, side_rows))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class BodyFitAimSideSpec:
    suffix: str
    target_offset: str
    target_control: str
    fk_offset: str
    fk_aim: str
    fk_control: str
    bind_position: Vector3
    channel_attributes: tuple[str, ...] = TRANSLATION
    mirrored: bool | None = None
    source_order: int | None = None

    @property
    def creation_mirrored(self) -> bool:
        return self.suffix == "L" if self.mirrored is None else self.mirrored

    @property
    def native_channels(self) -> bool:
        return self.channel_attributes == TRANSLATION

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
    center_attributes: tuple[str, ...] = TRANSFORM + ("follow",)

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
        shapes = (self.center_control.rsplit("|", 1)[-1] + "Shape",)
        shapes += tuple(side.target_control.rsplit("|", 1)[-1] + "Shape"
                        for side in self.sides if side.suffix != "M")
        matrix_nodes = tuple(name for side in self.sides for name in (
            side.aim_matrix_name, side.local_matrix_name,
            side.local_matrix_name + "DM"))
        follow_nodes = (self.follow_blend_name, self.follow_target_name,
                        self.follow_static_name, self.follow_local_name,
                        self.follow_local_name + "DM", self.follow_weight_name)
        return (tuple(path.rsplit("|", 1)[-1] for path in paths) + shapes
                + matrix_nodes + follow_nodes)


def plan_body_fit_aim(
    hierarchy: FitHierarchySnapshot,
    metadata: tuple[FitJointMetadata, ...],
    body: BodySkeletonSnapshot,
    controls: tuple[BodyLimbFkControlSpec, ...],
    *, saved_layouts: tuple[BodyFitAimLayout, ...] | None = None,
    instances: tuple = (),
    fit_joint_order: tuple[str, ...] | None = None,
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
    marked_names = {source_fit_build_name(nodes[path].short_name)
                    for path in marked if path in nodes}
    by_stem: dict[str, list[BodyLimbFkControlSpec]] = {}
    for control in controls:
        if control.aim_path is None:
            continue
        matched = {source_fit_build_name(name) for name in control.fit_joint_names} & marked_names
        if len(matched) != 1:
            raise ValueError("Fit Aim 控制必须有唯一已标记的来源关节")
        by_stem.setdefault(next(iter(matched)), []).append(control)
    scale = fit_build_scale(hierarchy)
    paths = tuple(node.path for node in hierarchy.joints) if fit_joint_order is None else fit_joint_order
    if len(paths) != len(nodes) or set(paths) != set(nodes):
        raise ValueError("Fit Aim 原版遍历顺序与来源关节不一致")
    source_order = {path: index for index, path in enumerate(paths)}
    origins = {}
    for control in controls:
        if control.aim_path is None:
            continue
        candidates = [instance for instance in instances
                      if instance.side == control.side
                      and source_fit_build_name(instance.source_joint.rsplit("|", 1)[-1])
                      in {source_fit_build_name(name) for name in control.fit_joint_names}]
        if instances and len(candidates) != 1:
            raise ValueError("Fit Aim 控制缺少唯一实际镜像来源：" + control.control_path)
        if candidates:
            origins[control.control_path] = candidates[0]
    def creation_key(control):
        origin = origins.get(control.control_path)
        return ((origin.mirrored, source_order[origin.source_joint]) if origin else
                (control.side.value == "L", len(source_order)))
    result: list[BodyFitAimSpec] = []
    covered: set[str] = set()
    # MEL 80652 creates the shared Aim center only once, then adds the
    # authored sides. NonSymmetry is a Fit suffix, not a second Aim system.
    ordered_sources = ([path for path in paths if path in marked] if fit_joint_order is not None else
                       [node.path for alternate in (False, True)
                       for node in hierarchy.joints if node.path in marked
                       and node.short_name.endswith('_NonSymmetry') == alternate])
    layouts = {layout.stem: layout for layout in saved_layouts or ()}
    if len(layouts) != len(saved_layouts or ()):
        raise ValueError("保存的 Fit Aim 布局来源重复")
    for source_path in ordered_sources:
        source = nodes.get(source_path)
        if source is None:
            raise ValueError("Fit Aim 来源关节不在当前层级：" + source_path)
        stem = source_fit_build_name(source.short_name)
        if stem in covered:
            continue
        matches = by_stem.get(stem, [])
        if not matches:
            raise ValueError("Fit Aim 缺少对应 FK 控制：" + source_path)
        if stem in covered or len({item.side.value for item in matches}) != len(matches):
            raise ValueError("Fit Aim 来源或左右 FK 控制重复：" + stem)
        covered.add(stem)
        parent = nodes.get(source.dag_parent)
        if parent is None:
            raise ValueError("Fit Aim 来源缺少父关节：" + source_path)
        parent_name = source_fit_build_name(parent.short_name)
        first_control = min(matches, key=creation_key)
        origin = origins.get(first_control.control_path)
        if origin:
            parent = nodes.get(nodes[origin.source_joint].dag_parent)
            if parent is None:
                raise ValueError("Fit Aim 实际来源缺少父关节：" + origin.source_joint)
            parent_name = source_fit_build_name(parent.short_name)
        # MEL 80641 retains the authored parent side even in the mirror pass.
        ancestors = []
        ancestor = parent
        while ancestor is not None:
            ancestors.append(ancestor)
            ancestor = nodes.get(ancestor.dag_parent)
        parent_side = "M"
        for ancestor in reversed(ancestors):
            if abs(ancestor.world_position[0]) > 0.01 * scale:
                parent_side = "L" if ancestor.world_position[0] > 0 else "R"
                break
        follow = by_name.get(parent_name + "_" + parent_side)
        if follow is None:
            raise ValueError("Fit Aim 父关节没有对应 Body 关节：" + parent_name)
        root = AIM_SYSTEM + "|AdvPy_Aim" + stem
        offset = root + "|AdvPy_AimOffset" + stem
        follow_path = offset + "|AdvPy_AimFollow" + stem
        center = follow_path + "|AdvPy_Aim" + stem + "_M"
        layout = layouts.get(stem)
        side_attributes = dict(layout.side_channels) if layout else {}
        side_order = tuple(side_attributes) if layout else ("R", "M", "L")
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
            channel_attributes=side_attributes.get(item.side.value, TRANSLATION),
            mirrored=origins[item.control_path].mirrored if item.control_path in origins else None,
            source_order=source_order[origins[item.control_path].source_joint] if item.control_path in origins else None,
        ) for item in sorted(matches, key=lambda item: side_order.index(item.side.value)
                             if item.side.value in side_order else len(side_order)))
        # The source center queries the unsuffixed Fit transform even
        # when the only active side comes from a NonSymmetry branch.
        center_source = next((node for node in hierarchy.joints
                              if node.short_name.rsplit(':', 1)[-1] == stem), source)
        result.append(BodyFitAimSpec(
            fit_joint=source_path, stem=stem, root=root,
            offset=offset, follow=follow_path,
            center_control=center,
            center_position=(0.0, center_source.world_position[1],
                             center_source.world_position[2] + 2.0 * scale),
            control_radius=scale / 3.0,
            follow_joint=follow.path,
            sides=sides,
            center_attributes=layout.center_attributes if layout else TRANSFORM + ("follow",)))
    if set(by_stem) != covered:
        raise ValueError("FK Aim 层与 Fit Aim 标记不一致")
    if saved_layouts is not None:
        order = tuple(layouts)
        result.sort(key=lambda spec: order.index(spec.stem) if spec.stem in layouts else len(order))
    return tuple(result)
