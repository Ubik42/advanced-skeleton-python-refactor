"""Source-shaped chain descriptions for AdvancedSkeleton 6.925 Bendy."""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import dist, isfinite

from .fit_metadata import FitJointMetadata
from .fit_part import FitPartJointSpec
from .body_skeleton import BodyJointSpec
from .body_limb_controls import BodyLimbFkControlSpec


@dataclass(frozen=True, slots=True)
class FitBendyChainSpec:
    source_joint: str
    start_body: str
    end_body: str
    side: str
    part_names: tuple[str, ...]
    control_count: int
    start_position: tuple[float, float, float]
    end_position: tuple[float, float, float]
    part_positions: tuple[tuple[float, float, float], ...]
    rotation_order: int = 0
    master_icon_scale: float = 1.5
    micro_icon_scales: tuple[float, ...] = ()
    child_start_control: str | None = None
    child_start_influence: str | None = None
    parent_bendy: bool = False
    child_junction_control: str | None = None
    child_source_proxy: str | None = None
    start_world_axes: tuple[tuple[float, float, float], ...] | None = None
    honor_non_symmetry_axis: bool = True
    micro_matrix_aim: bool = True
    micro_base_twist: bool = True
    micro_local_scale: bool = True
    micro_yz_scale_only: bool = True
    micro_up_twist: bool = False
    micro_blended_up: bool = False

    def __post_init__(self) -> None:
        if (type(self.control_count) is not int
                or self.control_count < 1
                or type(self.rotation_order) is not int
                or not 0 <= self.rotation_order <= 5
                or not isfinite(self.master_icon_scale)
                or self.master_icon_scale <= 0
                or (self.micro_icon_scales and (
                    len(self.micro_icon_scales) != len(self.part_names) + 1
                    or any(not isfinite(scale) or scale <= 0
                           for scale in self.micro_icon_scales)))):
            raise ValueError("Bendy 控制器朝向或图标尺寸无效")
        if bool(self.child_start_control) != bool(self.child_start_influence):
            raise ValueError("Bendy 相邻段缺少起点控制或影响关节")
        if bool(self.child_junction_control) != bool(self.child_source_proxy):
            raise ValueError("Bendy Circular 缺少相邻段控制或驱动来源")
        if (self.start_world_axes is not None
                and (len(self.start_world_axes) != 3
                     or any(len(axis) != 3 or any(not isfinite(value)
                            for value in axis)
                            for axis in self.start_world_axes))):
            raise ValueError("Bendy 起点世界朝向无效")
        if type(self.honor_non_symmetry_axis) is not bool:
            raise ValueError("Bendy 非对称瞄准策略无效")
        if type(self.micro_matrix_aim) is not bool:
            raise ValueError("Bendy 微控制矩阵瞄准策略无效")
        if type(self.micro_base_twist) is not bool:
            raise ValueError("Bendy 微控制基础扭转策略无效")
        if type(self.micro_local_scale) is not bool:
            raise ValueError("Bendy 微控制缩放策略无效")
        if type(self.micro_yz_scale_only) is not bool:
            raise ValueError("Bendy 纵向缩放策略无效")
        if type(self.micro_up_twist) is not bool:
            raise ValueError("Bendy 上行扭转策略无效")
        if type(self.micro_blended_up) is not bool:
            raise ValueError("Bendy 微控制朝向兼容策略无效")

    @property
    def control_positions(self) -> tuple[tuple[float, float, float], ...]:
        """Start control, then evenly spaced interior controls."""
        return (self.start_position, *(tuple(
            a + (b - a) * index / (self.control_count + 1)
            for a, b in zip(self.start_position, self.end_position))
            for index in range(1, self.control_count + 1)))

    @property
    def micro_radii(self) -> tuple[float, ...]:
        return (self.micro_icon_scales or
                (0.15,) * (len(self.part_names) + 1))

    @property
    def master_position(self) -> tuple[float, float, float]:
        return tuple((a + b) * 0.5 for a, b in zip(
            self.start_position, self.end_position))

    @property
    def start_icon_offset(self) -> float:
        """ADV moves only Bend0's CVs by one fifth of the segment length."""
        return (dist(self.start_position, self.end_position) / 5.0
                * self.aim_axis_sign)

    @property
    def aim_axis_sign(self) -> int:
        source = self.source_joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        return -1 if (self.side == "L"
                      or (self.honor_non_symmetry_axis
                          and source.endswith("_NonSymmetry"))) else 1

    @property
    def stem(self) -> str:
        return self.start_body.rsplit("|", 1)[-1].rsplit("_", 1)[0]

    @property
    def prefix(self) -> str:
        return f"Bend{self.stem}"

    @property
    def curve_name(self) -> str:
        return f"{self.prefix}Curve_{self.side}"

    @property
    def influence_names(self) -> tuple[str, ...]:
        middle = (("Mid",) if self.control_count == 1 else
                  tuple(f"Mid{index}" for index in
                        range(1, self.control_count + 1)))
        return tuple(f"{self.prefix}{label}_{self.side}"
                     for label in ("Start", *middle, "End"))

    @property
    def control_names(self) -> tuple[str, ...]:
        return (f"{self.prefix}_{self.side}",
                *(f"{self.prefix}{index}_{self.side}"
                  for index in range(self.control_count + 1)))

    @property
    def control_extra_names(self) -> tuple[str, ...]:
        return tuple(name + "Extra" for name in self.control_names)

    @property
    def end_proxy_name(self) -> str:
        return f"BendX{self.stem}{self.control_count + 1}_{self.side}"

    @property
    def junction_name(self) -> str:
        return f"BendMid{self.stem}_{self.side}"

    @property
    def junction_offset_name(self) -> str:
        return f"BendMidOffset{self.stem}_{self.side}"

    @property
    def junction_extra_name(self) -> str:
        return self.junction_name + "Extra"

    @property
    def junction_output_name(self) -> str:
        return f"BendMidX{self.stem}_{self.side}"

    @property
    def follow_node_names(self) -> tuple[str, ...]:
        return (f"AdvPy_{self.prefix}StartSource_{self.side}",
                f"AdvPy_{self.prefix}EndSource_{self.side}",
                f"AdvPy_{self.prefix}StartWorld_{self.side}",
                f"AdvPy_{self.prefix}EndWorld_{self.side}",
                f"AdvPy_{self.prefix}StartBlend_{self.side}",
                f"AdvPy_{self.prefix}EndBlend_{self.side}",
                *(f"AdvPy_{name}Follow" for name in self.control_names),
                *(name + "Offset" for name in self.control_names),
                *self.control_extra_names,
                *(self.end_follow_matrix_names if self.child_start_influence
                  else (f"AdvPy_{self.end_proxy_name}Follow",)),
                *((self.circular_name, *self.circular_graph_names)
                  if self.child_junction_control else ()))

    @property
    def master_follow_matrix_names(self) -> tuple[str, ...]:
        prefix = f"AdvPy_{self.prefix}MasterFollow_{self.side}"
        return (
            prefix + "Blend", prefix + "Translate",
            prefix + "Rotate", prefix + "Mix", prefix + "Aim",
            prefix + "Offset", prefix + "World", prefix + "Pick")

    @property
    def parent_untwist_names(self) -> tuple[str, str, str, str]:
        prefix = f"AdvPy_{self.prefix}ParentUntwist_{self.side}"
        return (prefix + "Negate", prefix + "Compose",
                prefix + "World", prefix + "Frame")

    @property
    def circular_name(self) -> str:
        return f"BendCircular{self.stem}_{self.side}"

    @property
    def end_follow_matrix_names(self) -> tuple[str, str, str]:
        prefix = f"AdvPy_{self.end_proxy_name}"
        return (prefix + "TranslateScale", prefix + "Rotate",
                prefix + "World")

    @property
    def circular_graph_names(self) -> tuple[str, str, str, str]:
        prefix = f"AdvPy_{self.prefix}Circular_{self.side}"
        return (prefix + "Relative", prefix + "Angle",
                prefix + "Length", prefix + "Amount")

    @property
    def skin_name(self) -> str:
        return f"{self.prefix}SC_{self.side}"

    @property
    def secondary_curve_name(self) -> str:
        return f"Bend2{self.stem}Curve_{self.side}"

    @property
    def secondary_skin_name(self) -> str:
        return f"Bend2{self.stem}SC_{self.side}"

    @property
    def secondary_influence_names(self) -> tuple[str, str, str]:
        return tuple(f"Bend2{self.stem}{label}_{self.side}"
                     for label in ("Start", "Mid", "End"))

    @property
    def secondary_motion_path_names(self) -> tuple[str, ...]:
        return tuple(f"Bendy2MP{self.stem}{index}_{self.side}"
                     for index in range(1, self.control_count + 1))

    @property
    def secondary_motion_transform_names(self) -> tuple[str, ...]:
        return tuple(f"Bend2MPX{self.stem}{index}_{self.side}"
                     for index in range(1, self.control_count + 1))

    @property
    def secondary_end_matrix_names(self) -> tuple[str, str, str]:
        prefix = f"AdvPy_Bend2{self.stem}End_{self.side}"
        return (prefix + "Translate", prefix + "Rotate",
                prefix + "World")

    @property
    def secondary_node_names(self) -> tuple[str, ...]:
        if self.control_count == 1:
            return ()
        constrained = (self.secondary_influence_names[:2]
                       if self.child_start_control
                       else self.secondary_influence_names)
        return (self.secondary_curve_name,
                self.secondary_curve_name + "Shape",
                self.secondary_skin_name,
                *self.secondary_influence_names,
                *("AdvPy_Bend2Guide" + name
                  for name in constrained),
                *(self.secondary_end_matrix_names
                  if self.child_start_control else ()),
                *self.secondary_motion_path_names,
                *self.secondary_motion_transform_names)

    @property
    def guide_node_names(self) -> tuple[str, ...]:
        return (self.curve_name, self.curve_name + "Shape",
                self.skin_name, *self.influence_names,
                *self.control_names,
                *(name + "Shape" for name in self.control_names),
                *("AdvPy_BendGuide" + name
                  for name in self.influence_names),
                self.end_proxy_name, *self.motion_path_names,
                *self.motion_transform_names,
                *((self.junction_name, self.junction_name + "Shape",
                   self.junction_offset_name, self.junction_extra_name,
                   self.junction_output_name)
                  if self.parent_bendy else ()))

    @property
    def motion_path_names(self) -> tuple[str, ...]:
        return tuple(f"BendyMP{self.stem}{index}_{self.side}"
                     for index in range(len(self.part_names) + 1))

    @property
    def motion_transform_names(self) -> tuple[str, ...]:
        return tuple(f"BendMPX{self.stem}{index}_{self.side}"
                     for index in range(len(self.part_names) + 1))

    @property
    def deform_names(self) -> tuple[str, ...]:
        return (self.start_body.rsplit("|", 1)[-1], *self.part_names)

    @property
    def micro_offset_names(self) -> tuple[str, ...]:
        return tuple("MicroOffset" + name for name in self.deform_names)

    @property
    def micro_control_names(self) -> tuple[str, ...]:
        return tuple("Micro" + name for name in self.deform_names)

    @property
    def micro_extra_names(self) -> tuple[str, ...]:
        return tuple("MicroExtra" + name for name in self.deform_names)

    @property
    def micro_output_names(self) -> tuple[str, ...]:
        return tuple("MicroX" + name for name in self.deform_names)

    @property
    def micro_node_names(self) -> tuple[str, ...]:
        return (*self.micro_offset_names, *self.micro_extra_names,
                *self.micro_control_names,
                *(name + "Shape" for name in self.micro_control_names),
                *self.micro_output_names,
                *((node for row in self.micro_aim_matrix_names
                   for node in row) if self.micro_matrix_aim else
                  (name + "Aim" for name in self.motion_transform_names)),
                *(name + "MicroFollow" for name in self.motion_transform_names),
                *(node for row in (self.micro_matrix_orientation_names
                                   if self.micro_matrix_aim else
                                   self.micro_orientation_names)
                  for node in row),
                *(node for add, mults in self.micro_twist_names
                  for node in (add, *mults)),
                *((node for row in self.micro_base_twist_names
                   for node in row) if self.micro_base_twist else ()),
                *(self.micro_up_twist_names if self.micro_up_twist else ()),
                *(node for add, deltas, weights in self.micro_scale_names
                  for node in (add, *deltas, *weights)),
                *(node for row in self.twist_projection_names
                  for node in row),
                *(self.micro_end_twist_names if self.child_start_control
                  else ()),
                *((node for row in self.micro_end_scale_names
                   for node in row) if self.child_start_control else ()))

    @property
    def deform_constraint_names(self) -> tuple[str, ...]:
        return tuple("AdvPy_BendyDeform" + name
                     for name in self.deform_names)

    @property
    def deform_scale_pick_names(self) -> tuple[str, ...]:
        return tuple("AdvPy_BendyScale" + name
                     for name in self.deform_names)

    @property
    def deform_scale_mult_names(self) -> tuple[str, ...]:
        return tuple("AdvPy_BendyDeformScale" + name
                     for name in self.deform_names)

    @property
    def deform_micro_scale_names(self) -> tuple[
        tuple[str, str, str], ...
    ]:
        return tuple(("AdvPy_BendyMicroScaleRelative" + name,
                      "AdvPy_BendyMicroScaleDecompose" + name,
                      "AdvPy_BendyMicroScaleCombine" + name)
                     for name in self.deform_names)

    def control_weights(self, sample_index: int) -> tuple[float, ...]:
        """MEL's start, master and interior distance falloffs at a bind sample."""
        if not 0 <= sample_index <= len(self.part_names):
            raise ValueError("Bendy 采样编号超出 Body／Part 链")
        total = dist(self.start_position, self.end_position)
        if total <= 1e-8:
            raise ValueError("Bendy 起止关节不能重合")
        point = (self.start_position if sample_index == 0
                 else self.part_positions[sample_index - 1])
        master = max(0.0, 1.0 - dist(point, self.master_position)
                     / (total * 0.5))
        start = 1.0 - dist(point, self.start_position) / total
        interior_interval = total / (self.control_count + 1)
        interior = tuple(max(0.0, 1.0 - dist(point, position)
                             / interior_interval)
                         for position in self.control_positions[1:])
        return (master, start, *interior)

    def twist_weights(self, sample_index: int) -> tuple[float, ...]:
        scale_weights = self.control_weights(sample_index)
        return (scale_weights[0],
                1.0 - sample_index / len(self.part_names),
                *scale_weights[2:])

    @property
    def micro_orientation_names(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(("AdvPy_" + name + "UpBlend",
                      "AdvPy_" + name + "UpDecompose",
                      "AdvPy_" + name + "Up")
                     for name in self.deform_names)

    @property
    def micro_aim_matrix_names(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(("AdvPy_" + name + "AimCompose",
                      "AdvPy_" + name + "AimMatrix",
                      "AdvPy_" + name + "AimDecompose")
                     for name in self.deform_names)

    @property
    def micro_matrix_orientation_names(self) -> tuple[
        tuple[str, ...], ...
    ]:
        return tuple((("AdvPy_" + name + "UpBlend",)
                      if self.micro_blended_up else ())
                     + ("AdvPy_" + name + "TwistCompose",
                        "AdvPy_" + name + "TwistWorld")
                     for name in self.deform_names)

    @property
    def micro_twist_names(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        return tuple(("AdvPy_" + name + "BendTwistAdd",
                      tuple("AdvPy_" + name + "BendTwist" + str(index)
                            for index in range(len(self.control_names))))
                     for name in self.deform_names)

    @property
    def micro_base_twist_names(self) -> tuple[tuple[str, str], ...]:
        return tuple(("AdvPy_" + name + "BaseTwistOffset",
                      "AdvPy_" + name + "BaseTwistMultiply")
                     for name in self.deform_names)

    @property
    def micro_up_twist_names(self) -> tuple[str, ...]:
        return tuple("AdvPy_" + name + "UpTwistMultiply"
                     for name in self.part_names)

    @property
    def twist_projection_names(self) -> tuple[
        tuple[str, str, str, str], ...
    ]:
        return tuple(("AdvPy_" + name + "TwistX",
                      "AdvPy_" + name + "TwistMatrix",
                      "AdvPy_" + name + "TwistDecompose",
                      "AdvPy_" + name + "TwistQTE")
                     for name in self.control_names)

    @property
    def micro_scale_names(self) -> tuple[
        tuple[str, tuple[str, ...], tuple[str, ...]], ...
    ]:
        return tuple((
            "AdvPy_" + name + "BendScaleAdd",
            tuple("AdvPy_" + name + "BendScaleDelta" + str(index)
                  for index in range(len(self.control_names))),
            tuple("AdvPy_" + name + "BendScaleWeight" + str(index)
                  for index in range(len(self.control_names))),
        ) for name in self.deform_names)

    @property
    def micro_end_twist_names(self) -> tuple[str, ...]:
        return tuple("AdvPy_" + name + "BendTwistEnd"
                     for name in self.deform_names)

    @property
    def micro_end_scale_names(self) -> tuple[tuple[str, str], ...]:
        return tuple(("AdvPy_" + name + "BendScaleEndDelta",
                      "AdvPy_" + name + "BendScaleEndWeight")
                     for name in self.deform_names)


def plan_fit_bendy_chains(
    parts: tuple[FitPartJointSpec, ...],
    metadata: tuple[FitJointMetadata, ...],
    body_specs: tuple[BodyJointSpec, ...],
) -> tuple[FitBendyChainSpec, ...]:
    """Resolve every positive bendyCtrls value to one complete Twist chain."""
    by_source = {item.joint: item for item in metadata}
    if len(by_source) != len(metadata):
        raise ValueError("Fit Bendy 来源关节重复")
    by_body = {item.path: item for item in body_specs}
    if len(by_body) != len(body_specs):
        raise ValueError("Fit Bendy Body 路径重复")
    by_start: dict[str, list[FitPartJointSpec]] = {}
    for part in parts:
        if part.kind == "twist":
            by_start.setdefault(part.start_body, []).append(part)
    result = []
    for chain in by_start.values():
        chain.sort(key=lambda item: item.index)
        first = chain[0]
        setting = by_source.get(first.source_joint)
        if setting is None:
            raise ValueError("Fit Bendy 缺少来源元数据：" + first.source_joint)
        requested_controls = setting.bendy_controls or 0
        if requested_controls <= 0:
            continue
        # The historical +1 block in 6.925 MEL is commented out. The stored
        # bendyCtrls value already counts the interior Bend controllers.
        count = requested_controls
        if (len(chain) != first.count
                or tuple(part.index for part in chain)
                != tuple(range(1, first.count + 1))
                or any(part.end_body != first.end_body
                       or part.side is not first.side for part in chain)):
            raise ValueError("Fit Bendy 的 Twist Part 链不完整："
                             + first.start_body_name)
        if first.start_body not in by_body or first.end_body not in by_body:
            raise ValueError("Fit Bendy 缺少两端 Body："
                             + first.start_body_name)
        result.append(FitBendyChainSpec(
            first.source_joint, first.start_body, first.end_body,
            first.side.value, tuple(part.name for part in chain), count,
            by_body[first.start_body].world_position,
            by_body[first.end_body].world_position,
            tuple(part.world_position for part in chain),
            rotation_order=by_body[first.start_body].rotation_order,
            master_icon_scale=max(
                0.1,
                1.5 * by_body[first.start_body].deform_profile.fat
                * by_body[first.start_body].deform_profile.fat_front),
            micro_icon_scales=tuple(max(
                0.1, 1.5 * profile.fat * profile.fat_front)
                for profile in (
                    by_body[first.start_body].deform_profile,
                    *(part.deform_profile for part in chain))),
            micro_up_twist=bool(first.dual_twist_child)))
    # An enabled Bendy joint without a same-side child cannot be constructed.
    planned_sources = {item.source_joint for item in result}
    missing = [item.joint for item in metadata
               if (item.bendy_controls or 0) > 0
               and item.joint not in planned_sources]
    if missing:
        raise ValueError("Fit Bendy 缺少可用 Twist 骨段："
                         + "、".join(missing))
    by_bendy_start = {item.start_body: item for item in result}
    if len(by_bendy_start) != len(result):
        raise ValueError("Fit Bendy 起点重复")
    by_bendy_end: dict[str, list[FitBendyChainSpec]] = {}
    for item in result:
        by_bendy_end.setdefault(item.end_body, []).append(item)
    if any(len(parents) > 1 for parents in by_bendy_end.values()):
        raise ValueError("Fit Bendy 交界关节有多条上游曲线")
    return tuple(replace(
        item,
        child_start_control=by_bendy_start[item.end_body].control_names[1]
        if item.end_body in by_bendy_start else None,
        child_start_influence=by_bendy_start[item.end_body].influence_names[0]
        if item.end_body in by_bendy_start else None,
        parent_bendy=item.start_body in by_bendy_end,
        child_junction_control=by_bendy_start[item.end_body].junction_name
        if item.end_body in by_bendy_start else None,
        child_source_proxy=by_bendy_start[item.end_body].follow_node_names[0]
        if item.end_body in by_bendy_start else None,
    ) for item in result)


@dataclass(frozen=True, slots=True)
class FitBendyFkScaleSpec:
    body_joint: str
    control_path: str
    bendy_scale_name: str
    multiply_name: str


def plan_fit_bendy_fk_scales(
    chains: tuple[FitBendyChainSpec, ...],
    controls: tuple[BodyLimbFkControlSpec, ...],
) -> tuple[FitBendyFkScaleSpec, ...]:
    """Compose generic FK scale with Bendy's Body scale driver."""
    by_body = {control.driven_joint: control for control in controls}
    if len(by_body) != len(controls):
        raise ValueError("Bendy FK 缩放控制的 Body 来源重复")
    result = []
    for chain in chains:
        control = by_body.get(chain.start_body)
        if control is None:
            continue
        result.append(FitBendyFkScaleSpec(
            chain.start_body, control.control_path,
            chain.deform_scale_mult_names[0],
            "AdvPy_" + chain.start_body.rsplit("|", 1)[-1]
            .rsplit(":", 1)[-1]
            + "BendyFKScale"))
    if len({item.multiply_name for item in result}) != len(result):
        raise ValueError("Bendy FK 缩放节点名称重复")
    return tuple(result)
