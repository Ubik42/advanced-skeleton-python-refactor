from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import atan2, degrees, isfinite, sqrt

from .body_leg_ik import BodyLegIkPlan
from .body_leg_qtoes import plan_leg_qtoes_topology
from .body_controller_appearance import body_fk_curve_radius
from .body_skeleton import BodySkeletonSnapshot
from .fit_container import FitUpAxis
from .fit_metadata import FitJointMetadata
from .fit_symmetry import AxisFrame, FitBuildSide, FitSymmetryInstance


Vector3 = tuple[float, float, float]


class BodyLegFootValidationError(ValueError):
    pass


def _qtoes_roll_axes(position: Vector3, hip, side: FitBuildSide) -> AxisFrame:
    """MEL's QToes-upstream aim: local Y toward Hip, local Z from Hip Y."""
    def unit(vector):
        length = sqrt(sum(value * value for value in vector))
        if length <= 1e-8:
            raise BodyLegFootValidationError(
                "QToes Roll 朝向缺少非退化的腿根方向或上方向")
        return tuple(value / length for value in vector)

    def cross(left, right):
        return (left[1] * right[2] - left[2] * right[1],
                left[2] * right[0] - left[0] * right[2],
                left[0] * right[1] - left[1] * right[0])

    y_axis = unit(tuple(a - b for a, b in zip(hip.world_position, position)))
    world_up = hip.world_axes[1]
    projection = sum(a * b for a, b in zip(world_up, y_axis))
    sign = -1.0 if side is FitBuildSide.LEFT else 1.0
    z_axis = unit(tuple(sign * (a - projection * b)
                        for a, b in zip(world_up, y_axis)))
    x_axis = unit(cross(y_axis, z_axis))
    return (x_axis, y_axis, unit(cross(x_axis, y_axis)))


def requested_foot_pivot_sides(
    instances: tuple[FitSymmetryInstance, ...],
    metadata: tuple[FitJointMetadata, ...],
) -> tuple[FitBuildSide, ...]:
    """Find Foot Fit switches after source joints expand to both build sides."""
    source = {item.joint: item for item in metadata}
    return tuple(instance.side for instance in instances
                 if instance.output_name == f"Ankle_{instance.side.value}"
                 and source[instance.source_joint].foot_pivots)


class BodyLegFootPivotRole(str, Enum):
    HEEL = "heel"
    OUTER = "outer"
    INNER = "inner"
    TOE = "toe"
    BALL = "ball"
    QTOES = "qtoes"


@dataclass(frozen=True, slots=True)
class BodyLegFootPivotSpec:
    role: BodyLegFootPivotRole
    name: str
    path: str
    parent_path: str
    world_position: Vector3
    attribute: str
    rotation_axis: str
    source_plug: str
    target_plug: str
    multiplier_name: str | None = None
    multiplier: float = 1.0
    roll_offset_name: str = ""
    roll_offset_path: str = ""
    roll_extra_name: str = ""
    roll_extra_path: str = ""
    roll_control_name: str = ""
    roll_control_path: str = ""
    roll_radius: float = 0.0
    roll_roller_name: str = ""
    roll_roller_path: str = ""
    roll_roller_source: str = ""
    roll_world_rotation: Vector3 = (0.0, 0.0, 0.0)
    roll_world_axes: AxisFrame | None = None


@dataclass(frozen=True, slots=True)
class BodyLegFootRollNodeSpec:
    name: str
    node_type: str
    input_connections: tuple[tuple[str, str], ...]
    numeric_values: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class BodyLegFootRollSpec:
    master_attribute: str
    master_plug: str
    minimum: float
    maximum: float
    ball_break_angle: float
    nodes: tuple[BodyLegFootRollNodeSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyLegFootRockSpec:
    inner_name: str
    inner_path: str
    inner_position: Vector3
    outer_name: str
    outer_path: str
    outer_position: Vector3
    world_rotation: Vector3
    rotation_axis: str
    inner_source: str
    outer_source: str


@dataclass(frozen=True, slots=True)
class BodyLegFootManualPivotSpec:
    target_name: str
    target_path: str
    offset_name: str
    offset_path: str
    offset_parent_path: str
    control_name: str
    control_path: str
    reverse_name: str
    reverse_path: str
    matrix_name: str
    inverse_name: str
    world_position: Vector3
    world_rotation: Vector3
    radius: float
    world_axes: AxisFrame | None = None


@dataclass(frozen=True, slots=True)
class BodyLegFootHighHeelSpec:
    offset1_name: str
    offset1_path: str
    offset2_name: str
    offset2_path: str
    drive1_name: str
    drive1_path: str
    drive2_name: str
    drive2_path: str
    drive3_name: str
    drive3_path: str
    negate_name: str
    constraint_name: str
    point_constraint_name: str
    ankle_position: Vector3
    toe_position: Vector3


@dataclass(frozen=True, slots=True)
class BodyLegFootSideSpec:
    side: FitBuildSide
    legacy_roll_controls: bool
    ankle_control_path: str
    control_parent_path: str
    handle_name: str
    initial_handle_parent_path: str
    ankle_driver_path: str
    toe_driver_path: str
    ankle_constraint_name: str
    toe_offset_name: str
    toe_offset_path: str
    toe_control_name: str
    toe_control_path: str
    toe_control_position: Vector3
    toe_control_axes: AxisFrame
    toe_control_radius: float
    roll: BodyLegFootRollSpec
    pivots: tuple[BodyLegFootPivotSpec, ...]
    rock: BodyLegFootRockSpec | None = None
    manual_pivots: tuple[BodyLegFootManualPivotSpec, ...] = ()
    high_heel: BodyLegFootHighHeelSpec | None = None
    toe_extra_name: str = ""
    toe_extra_path: str = ""
    source_toe_icon: bool = False
    toe_control_rotate_order: int = 0
    toe_handle_name: str = ""
    toe_effector_name: str = ""
    toe_solver_joint_list: tuple[str, ...] | None = None
    toe_end_driver_path: str = ""
    toe_end_handle_name: str = ""
    toe_end_effector_name: str = ""
    toe_end_solver_joint_list: tuple[str, ...] | None = None
    qtoes_driver_path: str = ""
    qtoes_handle_name: str = ""
    qtoes_effector_name: str = ""
    qtoes_solver_joint_list: tuple[str, ...] | None = None

    @property
    def toe_handle_parent_path(self) -> str:
        ball = next(pivot.path for pivot in self.pivots
                    if pivot.role is BodyLegFootPivotRole.BALL)
        return next((manual.reverse_path for manual in self.manual_pivots
                     if manual.target_path == ball), ball)

    @property
    def qtoes_handle_parent_path(self) -> str:
        pivot = next(pivot.path for pivot in self.pivots
                     if pivot.role is BodyLegFootPivotRole.QTOES)
        return next((manual.reverse_path for manual in self.manual_pivots
                     if manual.target_path == pivot), pivot)

    @property
    def toe_handle_start_path(self) -> str:
        return self.qtoes_driver_path or self.ankle_driver_path

    @property
    def attributes(self) -> tuple[str, ...]:
        roll_attributes = ((self.roll.master_attribute,)
                           if self.legacy_roll_controls else
                           ("swivel", self.roll.master_attribute,
                            "rollStartAngle", "rollEndAngle"))
        return (roll_attributes + (("rock",) if self.rock else ())
                + (("footPivotsVis", "footPivotsHighHeel")
                   if self.manual_pivots else ())) + tuple(
            pivot.attribute for pivot in self.pivots if pivot.source_plug
        )

    def attribute_default(self, attribute: str) -> float:
        return {"rollStartAngle": 30.0,
                "rollEndAngle": 60.0,
                "footPivotsVis": 1.0}.get(attribute, 0.0)

    @property
    def final_handle_parent_path(self) -> str:
        if self.manual_pivots:
            return self.manual_pivots[-1].reverse_path
        return self.pivots[-1].path

    @property
    def ankle_orientation_source_path(self) -> str:
        return self.pivots[-1].path

@dataclass(frozen=True, slots=True)
class BodyLegFootPlan:
    sides: tuple[BodyLegFootSideSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyLegFootInputState:
    missing_required_paths: tuple[str, ...] = ()
    name_collisions: tuple[str, ...] = ()
    non_writable_paths: tuple[str, ...] = ()
    existing_attribute_plugs: tuple[str, ...] = ()
    occupied_rotation_plugs: tuple[str, ...] = ()
    invalid_ankle_constraints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BodyLegFootPivotState:
    role: BodyLegFootPivotRole
    path: str
    parent_path: str | None
    world_position: Vector3
    rotation_source: str | None
    multiplier_input_source: str | None = None
    multiplier_value: float | None = None
    roll_offset_path: str | None = None
    roll_offset_parent_path: str | None = None
    roll_extra_path: str | None = None
    roll_extra_parent_path: str | None = None
    roll_control_path: str | None = None
    roll_control_parent_path: str | None = None
    roll_control_position: Vector3 | None = None
    roll_control_shape: str | None = None
    roll_roller_path: str | None = None
    roll_roller_parent_path: str | None = None
    roll_roller_rotation_source: str | None = None
    roll_offset_world_rotation: Vector3 | None = None
    roll_control_rotation: Vector3 | None = None
    roll_offset_world_axes: AxisFrame | None = None


@dataclass(frozen=True, slots=True)
class BodyLegFootRollNodeState:
    name: str
    node_type: str | None
    input_connections: tuple[tuple[str, str | None], ...]
    numeric_values: tuple[tuple[str, float | None], ...]


@dataclass(frozen=True, slots=True)
class BodyLegFootRollState:
    master_plug: str
    master_value: float
    nodes: tuple[BodyLegFootRollNodeState, ...]


@dataclass(frozen=True, slots=True)
class BodyLegFootRockPivotState:
    path: str | None
    parent_path: str | None
    world_position: Vector3 | None
    world_rotation: Vector3 | None
    rotation_source: str | None
    rotate_order: int | None = None


@dataclass(frozen=True, slots=True)
class BodyLegFootManualPivotState:
    target_name: str
    offset_path: str | None
    offset_parent_path: str | None
    control_path: str | None
    control_parent_path: str | None
    reverse_path: str | None
    reverse_parent_path: str | None
    control_shape: str | None
    control_color: int | None
    visibility_source: str | None
    world_position: Vector3 | None
    world_rotation: Vector3 | None
    local_translation: Vector3 | None
    local_rotation: Vector3 | None
    graph_connections: tuple[tuple[str, str | None], ...]
    world_axes: AxisFrame | None = None


@dataclass(frozen=True, slots=True)
class BodyLegFootHighHeelState:
    paths: tuple[tuple[str, str | None, str | None], ...]
    graph_connections: tuple[tuple[str, str | None], ...]
    negate_factor: float | None
    orient_offset_y: float | None
    orient_target: str | None
    point_target: str | None


@dataclass(frozen=True, slots=True)
class BodyLegFootSideState:
    side: FitBuildSide
    attribute_values: tuple[tuple[str, float], ...]
    pivots: tuple[BodyLegFootPivotState, ...]
    handle_parent_path: str | None
    ankle_constraint_name: str | None
    ankle_orientation_source: str | None
    ankle_driven_joint: str | None
    toe_offset_path: str | None
    toe_offset_parent_path: str | None
    toe_control_path: str | None
    toe_control_parent_path: str | None
    toe_control_position: Vector3
    toe_control_axes: AxisFrame
    toe_control_translation: Vector3
    toe_control_rotation: Vector3
    toe_control_shape: str | None
    roll: BodyLegFootRollState
    toe_handle_parent_path: str | None = None
    toe_handle_joint_list: tuple[str, ...] = ()
    toe_handle_solver: str | None = None
    toe_end_handle_parent_path: str | None = None
    toe_end_handle_joint_list: tuple[str, ...] = ()
    toe_end_handle_solver: str | None = None
    toe_extra_path: str | None = None
    toe_extra_parent_path: str | None = None
    toe_control_rotate_order: int | None = None
    toe_control_color: int | None = None
    toe_ik_local: bool | None = None
    toe_extra_ik_local: bool | None = None
    swivel_source: str | None = None
    rock_pivots: tuple[BodyLegFootRockPivotState, ...] = ()
    manual_pivots: tuple[BodyLegFootManualPivotState, ...] = ()
    high_heel: BodyLegFootHighHeelState | None = None
    qtoes_handle_parent_path: str | None = None
    qtoes_handle_joint_list: tuple[str, ...] = ()
    qtoes_handle_solver: str | None = None


@dataclass(frozen=True, slots=True)
class BodyLegFootSnapshot:
    sides: tuple[BodyLegFootSideState, ...]


@dataclass(frozen=True, slots=True)
class BodyLegFootIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_leg_foot(
    body: BodySkeletonSnapshot,
    ik: BodyLegIkPlan,
    *, legacy_toe_controls: bool = False,
    legacy_roll_controls: bool = False,
    up_axis: FitUpAxis = FitUpAxis.Y,
    foot_pivots_by_side: frozenset[FitBuildSide] = frozenset(),
) -> BodyLegFootPlan:
    if type(legacy_toe_controls) is not bool:
        raise BodyLegFootValidationError("Toe 控制器版本选项无效")
    if type(legacy_roll_controls) is not bool:
        raise BodyLegFootValidationError("Roll 控制器版本选项无效")
    if not isinstance(up_axis, FitUpAxis):
        raise BodyLegFootValidationError("Foot 场景 Up Axis 无效")
    if not isinstance(foot_pivots_by_side, frozenset) or any(
            side not in (FitBuildSide.RIGHT, FitBuildSide.LEFT)
            for side in foot_pivots_by_side):
        raise BodyLegFootValidationError("Foot Pivots 侧别无效")
    if foot_pivots_by_side and legacy_roll_controls:
        raise BodyLegFootValidationError("旧版 Foot 控制层不能插入 Foot Pivots")
    if foot_pivots_by_side and up_axis is not FitUpAxis.Y:
        raise BodyLegFootValidationError(
            "6.925 Foot Pivots 的 HighHeel 驱动需要 Y-up 场景")
    body_by_name = {joint.name: joint for joint in body.joints}
    if len(body_by_name) != len(body.joints):
        raise BodyLegFootValidationError("Body 关节名称必须唯一")
    try:
        qtoes_by_suffix = {side.suffix: side for side in
                           plan_leg_qtoes_topology(body).sides}
    except ValueError as exc:
        raise BodyLegFootValidationError(str(exc)) from exc

    all_marker_roles = (
        (BodyLegFootPivotRole.HEEL, "Heel", "heelRoll", "Y", 1.0),
        (BodyLegFootPivotRole.OUTER, "FootSideOuter", "outerBank", "X", 1.0),
        (BodyLegFootPivotRole.INNER, "FootSideInner", "innerBank", "X", -1.0),
        (BodyLegFootPivotRole.TOE, "ToesEnd", "toeRoll", "Y", 1.0),
        (BodyLegFootPivotRole.BALL, "Toes", "ballRoll", "Y", 1.0),
    )
    sides = []
    for limb in ik.limbs:
        suffix = limb.side.value
        manual_enabled = limb.side in foot_pivots_by_side
        manual_pivots: list[BodyLegFootManualPivotSpec] = []
        high_heel = None
        master_attribute = "footRoll" if legacy_roll_controls else "roll"
        master_plug = f"{limb.ankle_control_path}.{master_attribute}"
        minimum, maximum, ball_break = -360.0, 360.0, 45.0
        heel_clamp = f"AdvPy_FootRollHeelClamp_{suffix}"
        ball_clamp = f"AdvPy_FootRollBallClamp_{suffix}"
        toe_subtract = f"AdvPy_FootRollToeSubtract_{suffix}"
        toe_clamp = f"AdvPy_FootRollToeClamp_{suffix}"
        sum_names = {
            BodyLegFootPivotRole.HEEL: f"AdvPy_FootRollHeelSum_{suffix}",
            BodyLegFootPivotRole.TOE: f"AdvPy_FootRollToeSum_{suffix}",
            BodyLegFootPivotRole.BALL: f"AdvPy_FootRollBallSum_{suffix}",
        }
        automatic_sources = {
            BodyLegFootPivotRole.HEEL: f"{heel_clamp}.outputR",
            BodyLegFootPivotRole.TOE: f"{toe_clamp}.outputR",
            BodyLegFootPivotRole.BALL: f"{ball_clamp}.outputR",
        }
        required = (f"ToesEnd_{suffix}", f"Toes_{suffix}")
        if any(name not in body_by_name for name in required):
            raise BodyLegFootValidationError(
                f"Body 缺少 {suffix} 侧唯一的 Toes/ToesEnd 标记"
            )
        qtoes_topology = qtoes_by_suffix[suffix]
        if qtoes_topology.hybrid:
            raise BodyLegFootValidationError(
                f"{suffix} 侧 QToes 需要 IKHybrid Roll／Sampler 和逐段 IK Handle")
        qtoes_joint = next((joint for joint in body.joints
                            if joint.path == qtoes_topology.qtoes_path), None)
        separate_qtoes = (qtoes_joint is not None
                           and qtoes_joint.path != qtoes_topology.toes_path)
        if qtoes_topology.intermediate_paths and not separate_qtoes:
            raise BodyLegFootValidationError(
                f"{suffix} 侧脚趾主链含尚未规划逐段 Foot IK 的中间关节")
        if separate_qtoes and (legacy_roll_controls or
                qtoes_topology.intermediate_paths != (qtoes_joint.path,)):
            raise BodyLegFootValidationError(
                f"{suffix} 侧 QToes 脚趾主链尚不能使用旧版 Roll 或额外中间关节")
        if separate_qtoes and (limb.toe_solver_joint_list is None or
                len(limb.toe_solver_joint_list) != 2):
            raise BodyLegFootValidationError(
                f"{suffix} 侧 QToes 缺少 Ankle→QToes IK 机制关节")
        marker_roles = tuple(row for row in all_marker_roles
                             if f"{row[1]}_{suffix}" in body_by_name)
        if separate_qtoes:
            marker_roles += ((BodyLegFootPivotRole.QTOES,
                              qtoes_joint.name.removesuffix("_" + suffix),
                              "", "Y", 1.0),)
        if manual_enabled and (
                f"Heel_{suffix}" not in body_by_name
                or f"BigToe_{suffix}" not in body_by_name
                or f"PinkyToe_{suffix}" not in body_by_name):
            raise BodyLegFootValidationError(
                f"{suffix} 侧 footPivots 需要 Heel、BigToe、PinkyToe Fit 标记")
        if legacy_roll_controls and len(marker_roles) != len(all_marker_roles):
            raise BodyLegFootValidationError(
                "旧版 Foot 场景要求完整 Heel/FootSide 标记")
        if any(body_by_name[f"{marker}_{suffix}"].side is not limb.side
               for _, marker, *_ in marker_roles):
            raise BodyLegFootValidationError(f"Foot 标记侧向与名称不一致：{suffix}")
        if qtoes_topology.qtoes_path and up_axis is not FitUpAxis.Y:
            raise BodyLegFootValidationError(
                "原版 QToes Roll 局部朝向要求 Y-up 场景")

        ankle_position = limb.ankle_position
        toes_position = body_by_name[f"Toes_{suffix}"].world_position
        dx = toes_position[0] - ankle_position[0]
        forward = (toes_position[2] - ankle_position[2]
                   if up_axis is FitUpAxis.Y
                   else toes_position[1] - ankle_position[1])
        heading_vector = (dx, forward)
        if not legacy_roll_controls and sum(v * v for v in heading_vector) <= 1e-12:
            raise BodyLegFootValidationError(
                f"Foot Roll 朝向需要非零的 Ankle→Toes 水平距离：{suffix}")
        heading = degrees(atan2(dx if up_axis is FitUpAxis.Y else -dx,
                                forward)) if not legacy_roll_controls else 0.0
        roll_world_rotation = ((0.0, heading, 0.0)
                               if up_axis is FitUpAxis.Y else
                               (0.0, 0.0, heading))

        control_parent_path = (limb.ankle_control_path
                               if legacy_roll_controls else
                               limb.ankle_sub_path or limb.ankle_control_path)
        rock = None
        if (not legacy_roll_controls
                and f"BigToe_{suffix}" in body_by_name
                and f"PinkyToe_{suffix}" in body_by_name):
            big_toe = body_by_name[f"BigToe_{suffix}"]
            pinky_toe = body_by_name[f"PinkyToe_{suffix}"]
            if big_toe.side is not limb.side or pinky_toe.side is not limb.side:
                raise BodyLegFootValidationError(
                    f"Foot Rock 脚趾标记侧向不一致：{suffix}")
            ground_axis = 1 if up_axis is FitUpAxis.Y else 2
            def ground_position(position: Vector3) -> Vector3:
                result = list(position)
                result[ground_axis] = 0.0
                return tuple(result)
            inner_name = f"AdvPy_FootRockInnerPivot_{suffix}"
            outer_name = f"AdvPy_FootRockOuterPivot_{suffix}"
            inner_position = ground_position(big_toe.world_position)
            outer_position = ground_position(pinky_toe.world_position)
            inner_parent = control_parent_path
            if manual_enabled:
                inner_offset_name = f"AdvPy_PivotOffset{inner_name}"
                inner_control_name = f"AdvPy_Pivot{inner_name}"
                inner_reverse_name = f"AdvPy_PivotReverse{inner_name}"
                inner_offset = f"{inner_parent}|{inner_offset_name}"
                inner_control = f"{inner_offset}|{inner_control_name}"
                inner_parent = inner_control
            inner_path = f"{inner_parent}|{inner_name}"
            outer_parent = inner_path
            if manual_enabled:
                inner_reverse = f"{inner_path}|{inner_reverse_name}"
                manual_pivots.append(BodyLegFootManualPivotSpec(
                    inner_name, inner_path, inner_offset_name, inner_offset,
                    control_parent_path, inner_control_name, inner_control,
                    inner_reverse_name, inner_reverse,
                    f"AdvPy_PivotReverse{inner_name}MM",
                    f"AdvPy_PivotReverse{inner_name}IM",
                    inner_position, roll_world_rotation,
                    ik.base_radius / 4.0))
                outer_parent = inner_reverse
                outer_offset_name = f"AdvPy_PivotOffset{outer_name}"
                outer_control_name = f"AdvPy_Pivot{outer_name}"
                outer_reverse_name = f"AdvPy_PivotReverse{outer_name}"
                outer_offset = f"{outer_parent}|{outer_offset_name}"
                outer_control = f"{outer_offset}|{outer_control_name}"
                outer_parent = outer_control
            outer_path = f"{outer_parent}|{outer_name}"
            if manual_enabled:
                outer_reverse = f"{outer_path}|{outer_reverse_name}"
                manual_pivots.append(BodyLegFootManualPivotSpec(
                    outer_name, outer_path, outer_offset_name, outer_offset,
                    inner_reverse, outer_control_name, outer_control,
                    outer_reverse_name, outer_reverse,
                    f"AdvPy_PivotReverse{outer_name}MM",
                    f"AdvPy_PivotReverse{outer_name}IM",
                    outer_position, roll_world_rotation,
                    ik.base_radius / 4.0))
            inner_clamp = f"AdvPy_FootRockInnerClamp_{suffix}"
            outer_clamp = f"AdvPy_FootRockOuterClamp_{suffix}"
            inner_source = f"{inner_clamp}.outputR"
            outer_source = f"{outer_clamp}.outputR"
            if limb.side is FitBuildSide.LEFT:
                inner_source = f"AdvPy_FootRockInnerSign_{suffix}.output"
                outer_source = f"AdvPy_FootRockOuterSign_{suffix}.output"
            rock = BodyLegFootRockSpec(
                inner_name, inner_path,
                inner_position,
                outer_name, outer_path,
                outer_position,
                roll_world_rotation,
                "Z" if up_axis is FitUpAxis.Y else "Y",
                inner_source, outer_source)

        parent = (manual_pivots[-1].reverse_path if manual_pivots else
                  rock.outer_path if rock else control_parent_path)
        pivots = []
        for role, marker, attribute, axis, multiplier in marker_roles:
            marker_joint = body_by_name[f"{marker}_{suffix}"]
            above_qtoes = bool(qtoes_topology.qtoes_path) and any(
                joint.path.startswith(marker_joint.path + "|")
                and "Toes" in joint.label.text
                and "ToesEnd" not in joint.label.text
                for joint in body.joints)
            roll_world_axes = (
                _qtoes_roll_axes(marker_joint.world_position,
                                 body_by_name[f"Hip_{suffix}"], limb.side)
                if above_qtoes and not legacy_roll_controls else None)
            roll_offset_name = (f"AdvPy_RollOffset{marker}_{suffix}"
                                if not legacy_roll_controls else "")
            roll_offset_path = (f"{parent}|{roll_offset_name}"
                                if roll_offset_name else "")
            roll_parent = roll_offset_path
            if manual_enabled and role is BodyLegFootPivotRole.HEEL:
                offset1_name = f"AdvPy_High{marker}Offset1_{suffix}"
                offset2_name = f"AdvPy_High{marker}Offset2_{suffix}"
                offset1_path = f"{roll_offset_path}|{offset1_name}"
                offset2_path = f"{offset1_path}|{offset2_name}"
                drive_parent = ik.root_path.rsplit("|", 1)[0] or ik.root_path
                drive1_name = f"AdvPy_High{marker}Drive1_{suffix}"
                drive2_name = f"AdvPy_High{marker}Drive2_{suffix}"
                drive3_name = f"AdvPy_High{marker}Drive3_{suffix}"
                drive1_path = f"{drive_parent}|{drive1_name}"
                drive2_path = f"{drive1_path}|{drive2_name}"
                high_heel = BodyLegFootHighHeelSpec(
                    offset1_name, offset1_path, offset2_name, offset2_path,
                    drive1_name, drive1_path, drive2_name, drive2_path,
                    drive3_name, f"{drive2_path}|{drive3_name}",
                    f"AdvPy_High{marker}OffsetNegate_{suffix}",
                    f"AdvPy_High{marker}Drive2Orient_{suffix}",
                    f"AdvPy_High{marker}Drive3Point_{suffix}",
                    ankle_position, toes_position)
                roll_parent = offset2_path
            manual_offset_name = (f"AdvPy_PivotOffsetRoll{marker}_{suffix}"
                                  if manual_enabled else "")
            manual_offset_path = (f"{roll_parent}|{manual_offset_name}"
                                  if manual_offset_name else "")
            manual_control_name = (f"AdvPy_PivotRoll{marker}_{suffix}"
                                   if manual_enabled else "")
            manual_control_path = (f"{manual_offset_path}|{manual_control_name}"
                                   if manual_control_name else "")
            roll_parent = manual_control_path or roll_parent
            roll_extra_name = (f"AdvPy_RollExtra{marker}_{suffix}"
                               if roll_offset_name else "")
            roll_extra_path = (f"{roll_parent}|{roll_extra_name}"
                               if roll_extra_name else "")
            roll_control_name = (f"AdvPy_Roll{marker}_{suffix}"
                                 if roll_extra_name else "")
            roll_control_path = (f"{roll_extra_path}|{roll_control_name}"
                                 if roll_control_name else "")
            roll_roller_name = (f"AdvPy_RollRoller{marker}_{suffix}"
                                if roll_control_name and role in (
                                    BodyLegFootPivotRole.HEEL,
                                    BodyLegFootPivotRole.TOE,
                                    BodyLegFootPivotRole.BALL) else "")
            roll_roller_path = (f"{roll_parent}|{roll_roller_name}"
                                if roll_roller_name else "")
            if roll_roller_path:
                roll_extra_path = f"{roll_roller_path}|{roll_extra_name}"
                roll_control_path = f"{roll_extra_path}|{roll_control_name}"
            name = (f"AdvPy_Foot{role.value.title()}Pivot_{suffix}"
                    if legacy_roll_controls else roll_control_name)
            path = (f"{parent}|{name}" if legacy_roll_controls
                    else roll_control_path)
            if manual_enabled:
                manual_reverse_name = f"AdvPy_PivotReverseRoll{marker}_{suffix}"
                manual_reverse_path = f"{path}|{manual_reverse_name}"
                manual_pivots.append(BodyLegFootManualPivotSpec(
                    name, path, manual_offset_name, manual_offset_path,
                    (high_heel.offset2_path if high_heel is not None
                     and role is BodyLegFootPivotRole.HEEL
                     else roll_offset_path),
                    manual_control_name, manual_control_path,
                    manual_reverse_name, manual_reverse_path,
                    f"AdvPy_PivotReverseRoll{marker}MM_{suffix}",
                    f"AdvPy_PivotReverseRoll{marker}IM_{suffix}",
                    body_by_name[f"{marker}_{suffix}"].world_position,
                    roll_world_rotation,
                    body_fk_curve_radius(
                        body, body_by_name[f"{marker}_{suffix}"],
                        ik.base_radius) / 4.0,
                    roll_world_axes))
            multiplier_name = (
                f"AdvPy_FootInnerBankSign_{suffix}"
                if legacy_roll_controls and multiplier != 1.0
                else None
            )
            manual_source = f"{limb.ankle_control_path}.{attribute}"
            source = (
                f"{sum_names[role]}.output1D"
                if legacy_roll_controls and role in sum_names
                else (
                    f"{multiplier_name}.output"
                    if multiplier_name else manual_source
                    if legacy_roll_controls else ""
                )
            )
            pivots.append(BodyLegFootPivotSpec(
                role=role,
                name=name,
                path=path,
                parent_path=(parent if legacy_roll_controls
                             else roll_extra_path),
                world_position=body_by_name[f"{marker}_{suffix}"].world_position,
                attribute=attribute,
                rotation_axis=axis,
                source_plug=source,
                target_plug=f"{path}.rotate{axis}",
                multiplier_name=multiplier_name,
                multiplier=multiplier,
                roll_offset_name=roll_offset_name,
                roll_offset_path=roll_offset_path,
                roll_extra_name=roll_extra_name,
                roll_extra_path=roll_extra_path,
                roll_control_name=roll_control_name,
                roll_control_path=roll_control_path,
                roll_radius=(body_fk_curve_radius(
                    body, body_by_name[f"{marker}_{suffix}"], ik.base_radius)
                    if roll_control_name else 0.0),
                roll_roller_name=roll_roller_name,
                roll_roller_path=roll_roller_path,
                roll_roller_source=(
                    f"AdvPy_RollHeelClamp_{suffix}.outputR"
                    if role is BodyLegFootPivotRole.HEEL else
                    f"AdvPy_RollToesEndMultiply_{suffix}.outputX"
                    if role is BodyLegFootPivotRole.TOE else
                    f"AdvPy_RollToesMultiply2_{suffix}.outputX"
                    if role is BodyLegFootPivotRole.BALL else ""
                ) if roll_roller_name else "",
                roll_world_rotation=roll_world_rotation,
                roll_world_axes=roll_world_axes,
            ))
            parent = manual_reverse_path if manual_enabled else path
        toe_pivot_path = next(
            pivot.path for pivot in pivots
            if pivot.role is BodyLegFootPivotRole.TOE
        )
        toe_offset_name = f"AdvPy_ToeIKOffset_{suffix}"
        toe_parent_path = (next(manual.reverse_path
                                for manual in manual_pivots
                                if manual.target_path == toe_pivot_path)
                           if manual_enabled else toe_pivot_path)
        toe_offset_path = f"{toe_parent_path}|{toe_offset_name}"
        toe_extra_name = (f"AdvPy_ToeIKExtra_{suffix}"
                          if not legacy_toe_controls else "")
        toe_extra_path = (f"{toe_offset_path}|{toe_extra_name}"
                          if toe_extra_name else "")
        toe_control_name = f"AdvPy_ToeIK_{suffix}"
        roll_nodes = (
            BodyLegFootRollNodeSpec(
                heel_clamp,
                "clamp",
                ((master_plug, f"{heel_clamp}.inputR"),),
                ((f"{heel_clamp}.minR", minimum), (f"{heel_clamp}.maxR", 0.0)),
            ),
            BodyLegFootRollNodeSpec(
                ball_clamp,
                "clamp",
                ((master_plug, f"{ball_clamp}.inputR"),),
                ((f"{ball_clamp}.minR", 0.0), (f"{ball_clamp}.maxR", ball_break)),
            ),
            BodyLegFootRollNodeSpec(
                toe_subtract,
                "addDoubleLinear",
                ((master_plug, f"{toe_subtract}.input1"),),
                ((f"{toe_subtract}.input2", -ball_break),),
            ),
            BodyLegFootRollNodeSpec(
                toe_clamp,
                "clamp",
                ((f"{toe_subtract}.output", f"{toe_clamp}.inputR"),),
                ((f"{toe_clamp}.minR", 0.0), (f"{toe_clamp}.maxR", maximum)),
            ),
            *(
                BodyLegFootRollNodeSpec(
                    sum_names[role],
                    "plusMinusAverage",
                    (
                        (
                            f"{limb.ankle_control_path}.{next(attribute for pivot_role, _, attribute, *_ in all_marker_roles if pivot_role is role)}",
                            f"{sum_names[role]}.input1D[0]",
                        ),
                        (
                            automatic_sources[role],
                            f"{sum_names[role]}.input1D[1]",
                        ),
                    ),
                )
                for role in (
                    BodyLegFootPivotRole.HEEL,
                    BodyLegFootPivotRole.TOE,
                    BodyLegFootPivotRole.BALL,
                )
            ),
        ) if legacy_roll_controls else ()
        if not legacy_roll_controls:
            start = f"{limb.ankle_control_path}.rollStartAngle"
            end = f"{limb.ankle_control_path}.rollEndAngle"
            heel = f"AdvPy_RollHeelClamp_{suffix}"
            toes_pma = f"AdvPy_RollToesSubtract_{suffix}"
            toes_range2 = f"AdvPy_RollToesRange2_{suffix}"
            toes_range1 = f"AdvPy_RollToesRange1_{suffix}"
            toes_multiply1 = f"AdvPy_RollToesMultiply1_{suffix}"
            toes_multiply2 = f"AdvPy_RollToesMultiply2_{suffix}"
            end_range = f"AdvPy_RollToesEndRange_{suffix}"
            end_multiply = f"AdvPy_RollToesEndMultiply_{suffix}"
            heel_nodes = ((BodyLegFootRollNodeSpec(
                heel, "clamp", ((master_plug, f"{heel}.inputR"),
                                (master_plug, f"{heel}.minR"))),)
                if any(p.role is BodyLegFootPivotRole.HEEL for p in pivots)
                else ())
            roll_nodes = (
                *heel_nodes,
                BodyLegFootRollNodeSpec(
                    toes_pma, "plusMinusAverage",
                    ((f"{toes_range2}.outValueX",
                      f"{toes_pma}.input1D[1]"),),
                    ((f"{toes_pma}.operation", 2.0),
                     (f"{toes_pma}.input1D[0]", 1.0))),
                BodyLegFootRollNodeSpec(
                    toes_range2, "setRange",
                    ((master_plug, f"{toes_range2}.valueX"),
                     (start, f"{toes_range2}.oldMinX"),
                     (end, f"{toes_range2}.oldMaxX")),
                    ((f"{toes_range2}.maxX", 1.0),)),
                BodyLegFootRollNodeSpec(
                    toes_range1, "setRange",
                    ((master_plug, f"{toes_range1}.valueX"),
                     (start, f"{toes_range1}.oldMaxX")),
                    ((f"{toes_range1}.maxX", 1.0),)),
                BodyLegFootRollNodeSpec(
                    toes_multiply1, "multiplyDivide",
                    ((f"{toes_pma}.output1D", f"{toes_multiply1}.input1X"),
                     (f"{toes_range1}.outValueX",
                      f"{toes_multiply1}.input2X"))),
                BodyLegFootRollNodeSpec(
                    toes_multiply2, "multiplyDivide",
                    ((f"{toes_multiply1}.outputX",
                      f"{toes_multiply2}.input1X"),
                     (master_plug, f"{toes_multiply2}.input2X"))),
                BodyLegFootRollNodeSpec(
                    end_range, "setRange",
                    ((master_plug, f"{end_range}.valueX"),
                     (start, f"{end_range}.oldMinX"),
                     (end, f"{end_range}.oldMaxX")),
                    ((f"{end_range}.maxX", 1.0),)),
                BodyLegFootRollNodeSpec(
                    end_multiply, "multiplyDivide",
                    ((f"{end_range}.outValueX",
                      f"{end_multiply}.input1X"),
                     (master_plug, f"{end_multiply}.input2X"))),
            )
        if rock:
            rock_plug = f"{limb.ankle_control_path}.rock"
            inner_clamp = f"AdvPy_FootRockInnerClamp_{suffix}"
            outer_clamp = f"AdvPy_FootRockOuterClamp_{suffix}"
            rock_nodes = (
                BodyLegFootRollNodeSpec(
                    inner_clamp, "clamp",
                    ((rock_plug, f"{inner_clamp}.inputR"),),
                    ((f"{inner_clamp}.minR", -200.0),)),
                BodyLegFootRollNodeSpec(
                    outer_clamp, "clamp",
                    ((rock_plug, f"{outer_clamp}.inputR"),),
                    ((f"{outer_clamp}.maxR", 200.0),)),
            )
            if limb.side is FitBuildSide.LEFT:
                rock_nodes += tuple(BodyLegFootRollNodeSpec(
                    f"AdvPy_FootRock{role}Sign_{suffix}",
                    "multDoubleLinear",
                    ((f"AdvPy_FootRock{role}Clamp_{suffix}.outputR",
                      f"AdvPy_FootRock{role}Sign_{suffix}.input1"),),
                    ((f"AdvPy_FootRock{role}Sign_{suffix}.input2", -1.0),))
                    for role in ("Inner", "Outer"))
            roll_nodes += rock_nodes
        sides.append(BodyLegFootSideSpec(
            side=limb.side,
            legacy_roll_controls=legacy_roll_controls,
            ankle_control_path=limb.ankle_control_path,
            control_parent_path=control_parent_path,
            handle_name=limb.handle_name,
            initial_handle_parent_path=limb.ankle_control_path,
            ankle_driver_path=limb.chain[2],
            toe_driver_path=limb.toe_driver_path,
            ankle_constraint_name=limb.ankle_constraint_name,
            toe_offset_name=toe_offset_name,
            toe_offset_path=toe_offset_path,
            toe_control_name=toe_control_name,
            toe_control_path=f"{toe_extra_path or toe_offset_path}|{toe_control_name}",
            toe_control_position=body_by_name[f"Toes_{suffix}"].world_position,
            toe_control_axes=body_by_name[f"Toes_{suffix}"].world_axes,
            toe_control_radius=(body_fk_curve_radius(
                body, body_by_name[f"Toes_{suffix}"], ik.base_radius)
                if not legacy_toe_controls else limb.radius * 0.65),
            roll=BodyLegFootRollSpec(
                master_attribute,
                master_plug,
                minimum,
                maximum,
                ball_break,
                roll_nodes,
            ),
            pivots=tuple(pivots),
            rock=rock,
            manual_pivots=tuple(manual_pivots),
            high_heel=high_heel,
            toe_extra_name=toe_extra_name,
            toe_extra_path=toe_extra_path,
            source_toe_icon=not legacy_toe_controls,
            toe_control_rotate_order=body_by_name[f"Toes_{suffix}"].rotation_order,
            toe_handle_name=f"AdvPy_LegIKToesHandle_{suffix}",
            toe_effector_name=f"AdvPy_LegIKToesEffector_{suffix}",
            toe_solver_joint_list=(None if separate_qtoes
                                   else limb.toe_solver_joint_list),
            toe_end_driver_path=limb.toe_end_driver_path,
            toe_end_handle_name=f"AdvPy_LegIKToesEndHandle_{suffix}",
            toe_end_effector_name=f"AdvPy_LegIKToesEndEffector_{suffix}",
            toe_end_solver_joint_list=limb.toe_end_solver_joint_list,
            qtoes_driver_path=(limb.toe_solver_joint_list[-1]
                               if separate_qtoes and limb.toe_solver_joint_list
                               else ""),
            qtoes_handle_name=(f"AdvPy_LegIKQToesHandle_{suffix}"
                               if separate_qtoes else ""),
            qtoes_effector_name=(f"AdvPy_LegIKQToesEffector_{suffix}"
                                 if separate_qtoes else ""),
            qtoes_solver_joint_list=(limb.toe_solver_joint_list
                                     if separate_qtoes else None),
        ))
    return BodyLegFootPlan(tuple(sides))


def audit_body_leg_foot_input(
    state: BodyLegFootInputState,
) -> tuple[BodyLegFootIssue, ...]:
    issues = []
    groups = (
        (state.missing_required_paths, "missing_foot_input", "Foot 必需输入缺失"),
        (state.name_collisions, "foot_name_collision", "Foot 节点名称冲突"),
        (state.non_writable_paths, "foot_input_locked", "Foot 输入不可写或被引用"),
        (state.existing_attribute_plugs, "foot_attribute_exists", "Foot 控制属性已存在"),
        (state.occupied_rotation_plugs, "foot_rotation_occupied", "Foot 旋转通道已有输入"),
        (
            state.invalid_ankle_constraints,
            "foot_ankle_constraint_invalid",
            "原 Ankle IK 朝向约束与预期不一致",
        ),
    )
    for subjects, code, message in groups:
        issues.extend(BodyLegFootIssue(code, message, subject) for subject in subjects)
    return tuple(issues)


def audit_body_leg_foot(
    plan: BodyLegFootPlan,
    snapshot: BodyLegFootSnapshot,
    *,
    tolerance: float = 1e-4,
    check_initial_pose: bool = True,
    expected_attribute_value: float | None = 0.0,
) -> tuple[BodyLegFootIssue, ...]:
    issues = []
    actual = {state.side: state for state in snapshot.sides}
    for spec in plan.sides:
        state = actual.get(spec.side)
        if state is None:
            issues.append(BodyLegFootIssue("missing_foot_side", "缺少 Foot 侧", spec.side.value))
            continue
        expected_plugs = tuple(
            f"{spec.ankle_control_path}.{attribute}"
            for attribute in spec.attributes
        )
        if (
            tuple(plug for plug, _ in state.attribute_values) != expected_plugs
            or (
                expected_attribute_value is not None
                and any(
                    abs(value - (spec.attribute_default(plug.rsplit(".", 1)[-1])
                                 if expected_attribute_value == 0.0
                                 else expected_attribute_value)) > tolerance
                    for plug, value in state.attribute_values
                )
            )
        ):
            issues.append(BodyLegFootIssue("foot_attributes", "Foot 属性或默认值不一致", spec.side.value))
        pivot_by_role = {pivot.role: pivot for pivot in state.pivots}
        manual_by_target = {manual.target_name: manual
                            for manual in spec.manual_pivots}
        if spec.rock:
            wanted_rock = (
                (spec.rock.inner_path,
                 manual_by_target[spec.rock.inner_name].control_path
                 if spec.rock.inner_name in manual_by_target
                 else spec.control_parent_path,
                 spec.rock.inner_position, spec.rock.inner_source),
                (spec.rock.outer_path,
                 manual_by_target[spec.rock.outer_name].control_path
                 if spec.rock.outer_name in manual_by_target
                 else spec.rock.inner_path,
                 spec.rock.outer_position, spec.rock.outer_source),
            )
            if len(state.rock_pivots) != 2:
                issues.append(BodyLegFootIssue(
                    "foot_rock_missing", "Foot Rock 双枢轴缺失",
                    spec.side.value))
            else:
                for actual_rock, (path, parent, position, source) in zip(
                        state.rock_pivots, wanted_rock):
                    if (actual_rock.path != path
                            or actual_rock.parent_path != parent
                            or actual_rock.rotation_source != source
                            or actual_rock.rotate_order != 5):
                        issues.append(BodyLegFootIssue(
                            "foot_rock_hierarchy", "Foot Rock 层级或驱动不一致",
                            path))
                    if check_initial_pose and (
                            actual_rock.world_position is None
                            or actual_rock.world_rotation is None
                            or not _close(actual_rock.world_position,
                                          position, tolerance)
                            or not _close_angles(actual_rock.world_rotation,
                                                 spec.rock.world_rotation,
                                                 tolerance)):
                        issues.append(BodyLegFootIssue(
                            "foot_rock_pose", "Foot Rock 初始位置或朝向不一致",
                            path))
        elif state.rock_pivots:
            issues.append(BodyLegFootIssue(
                "foot_rock_unexpected", "Foot Rock 不应存在",
                spec.side.value))
        if len(state.manual_pivots) != len(spec.manual_pivots):
            issues.append(BodyLegFootIssue(
                "foot_manual_count", "Foot Pivot 控制数量不一致",
                spec.side.value))
        for manual, found in zip(spec.manual_pivots, state.manual_pivots):
            wanted_graph = (
                (manual.matrix_name + ".matrixIn[0]",
                 manual.control_path + ".worldMatrix[0]"),
                (manual.matrix_name + ".matrixIn[1]",
                 manual.offset_path + ".worldInverseMatrix[0]"),
                (manual.inverse_name + ".inputMatrix",
                 manual.matrix_name + ".matrixSum"),
                (manual.reverse_path + ".offsetParentMatrix",
                 manual.inverse_name + ".outputMatrix"),
            )
            if (found.target_name != manual.target_name
                    or found.offset_path != manual.offset_path
                    or found.offset_parent_path != manual.offset_parent_path
                    or found.control_path != manual.control_path
                    or found.control_parent_path != manual.offset_path
                    or found.reverse_path != manual.reverse_path
                    or found.reverse_parent_path != manual.target_path
                    or found.control_shape != "nurbsCurve"
                    or found.control_color != 24
                    or found.visibility_source != (
                        spec.ankle_control_path + ".footPivotsVis")
                    or found.graph_connections != wanted_graph):
                issues.append(BodyLegFootIssue(
                    "foot_manual_graph", "Foot Pivot 层级或矩阵补偿不一致",
                    manual.control_name))
            if manual.world_axes is not None:
                manual_orientation_matches = (
                    found.world_axes is not None
                    and len(found.world_axes) == 3
                    and all(_close(actual, expected, tolerance)
                            for actual, expected in zip(
                                found.world_axes, manual.world_axes)))
            else:
                manual_orientation_matches = (
                    found.world_rotation is not None
                    and _close_angles(found.world_rotation,
                                      manual.world_rotation, tolerance))
            if check_initial_pose and (
                    found.world_position is None
                    or not manual_orientation_matches
                    or found.local_translation is None
                    or found.local_rotation is None
                    or not _close(found.world_position,
                                  manual.world_position, tolerance)
                    or not _close(found.local_translation,
                                  (0.0, 0.0, 0.0), tolerance)
                    or not _close_angles(found.local_rotation,
                                         (0.0, 0.0, 0.0), tolerance)):
                issues.append(BodyLegFootIssue(
                    "foot_manual_pose", "Foot Pivot 初始姿态不一致",
                    manual.control_name))
        if spec.high_heel is not None:
            high = spec.high_heel
            heel = next(p for p in spec.pivots
                        if p.role is BodyLegFootPivotRole.HEEL)
            wanted_paths = (
                (high.offset1_path, high.offset1_path,
                 heel.roll_offset_path),
                (high.offset2_path, high.offset2_path,
                 high.offset1_path),
                (high.drive1_path, high.drive1_path,
                 high.drive1_path.rsplit("|", 1)[0]),
                (high.drive2_path, high.drive2_path,
                 high.drive1_path),
                (high.drive3_path, high.drive3_path,
                 high.drive2_path),
            )
            source = spec.ankle_control_path + ".footPivotsHighHeel"
            wanted_connections = (
                (high.negate_name + ".input1X", source),
                (high.offset1_path + ".rotateX", source),
                (high.offset2_path + ".rotateX",
                 high.negate_name + ".outputX"),
                (high.drive1_path + ".rotateX", source),
                (spec.final_handle_parent_path + "|" + spec.handle_name
                 + ".translate", high.drive3_path + ".translate"),
            )
            if (state.high_heel is None
                    or state.high_heel.paths != wanted_paths
                    or state.high_heel.graph_connections
                    != wanted_connections
                    or state.high_heel.negate_factor != -1.0
                    or state.high_heel.orient_offset_y is None
                    or abs(state.high_heel.orient_offset_y
                           - heel.roll_world_rotation[1]) > tolerance
                    or state.high_heel.orient_target
                    != high.drive1_path.rsplit("|", 1)[0]
                    or state.high_heel.point_target
                    != high.drive1_path):
                issues.append(BodyLegFootIssue(
                    "foot_high_heel", "HighHeel 层级或驱动不一致",
                    spec.side.value))
        elif state.high_heel is not None:
            issues.append(BodyLegFootIssue(
                "foot_high_heel_unexpected", "Foot 不应有 HighHeel 驱动",
                spec.side.value))
        for pivot in spec.pivots:
            manual = manual_by_target.get(pivot.name)
            roll_parent = (manual.control_path if manual is not None
                           else pivot.roll_offset_path)
            actual_pivot = pivot_by_role.get(pivot.role)
            subject = f"{spec.side.value}:{pivot.role.value}"
            if actual_pivot is None:
                issues.append(BodyLegFootIssue("missing_foot_pivot", "缺少 Foot pivot", subject))
                continue
            if actual_pivot.path != pivot.path or actual_pivot.parent_path != pivot.parent_path:
                issues.append(BodyLegFootIssue("foot_pivot_hierarchy", "Foot pivot 层级不一致", subject))
            if pivot.roll_control_name and (
                actual_pivot.roll_offset_path != pivot.roll_offset_path
                or actual_pivot.roll_offset_parent_path != pivot.roll_offset_path.rsplit("|", 1)[0]
                or actual_pivot.roll_extra_path != pivot.roll_extra_path
                or actual_pivot.roll_extra_parent_path != (
                    pivot.roll_roller_path or roll_parent)
                or actual_pivot.roll_control_path != pivot.roll_control_path
                or actual_pivot.roll_control_parent_path != pivot.roll_extra_path
            ):
                issues.append(BodyLegFootIssue(
                    "foot_roll_control_hierarchy", "Roll 控制层级不一致", subject))
            if pivot.roll_roller_name and (
                actual_pivot.roll_roller_path != pivot.roll_roller_path
                or actual_pivot.roll_roller_parent_path != roll_parent
                or actual_pivot.roll_roller_rotation_source != pivot.roll_roller_source
            ):
                issues.append(BodyLegFootIssue(
                    "foot_roll_roller", "Roll 自动滚动层结构或驱动不一致", subject))
            if pivot.roll_control_name and actual_pivot.roll_control_shape != "nurbsCurve":
                issues.append(BodyLegFootIssue(
                    "foot_roll_control_shape", "Roll 控制缺少 NURBS 曲线", subject))
            if (pivot.roll_control_name and check_initial_pose
                    and (actual_pivot.roll_control_position is None
                         or not _close(actual_pivot.roll_control_position,
                                       pivot.world_position, tolerance))):
                issues.append(BodyLegFootIssue(
                    "foot_roll_control_position", "Roll 控制初始位置不一致", subject))
            if pivot.roll_world_axes is not None:
                heading_matches = (
                    actual_pivot.roll_offset_world_axes is not None
                    and len(actual_pivot.roll_offset_world_axes) == 3
                    and all(_close(actual, expected, tolerance)
                            for actual, expected in zip(
                                actual_pivot.roll_offset_world_axes,
                                pivot.roll_world_axes)))
            else:
                heading_matches = (
                    actual_pivot.roll_offset_world_rotation is not None
                    and _close_angles(
                        actual_pivot.roll_offset_world_rotation,
                        pivot.roll_world_rotation, tolerance))
            if pivot.roll_control_name and check_initial_pose and not heading_matches:
                issues.append(BodyLegFootIssue(
                    "foot_roll_heading", "Roll 控制朝向不一致", subject))
            if check_initial_pose and not _close(
                actual_pivot.world_position, pivot.world_position, tolerance
            ):
                issues.append(BodyLegFootIssue("foot_pivot_position", "Foot pivot 位置不一致", subject))
            if pivot.source_plug and actual_pivot.rotation_source != pivot.source_plug:
                issues.append(BodyLegFootIssue("foot_pivot_wiring", "Foot pivot 驱动不一致", subject))
            expected_input = (
                f"{spec.ankle_control_path}.{pivot.attribute}"
                if pivot.multiplier_name else None
            )
            expected_value = pivot.multiplier if pivot.multiplier_name else None
            if (
                actual_pivot.multiplier_input_source != expected_input
                or actual_pivot.multiplier_value != expected_value
            ):
                issues.append(BodyLegFootIssue("foot_multiplier", "Foot 符号节点不一致", subject))
        if state.handle_parent_path != spec.final_handle_parent_path:
            issues.append(BodyLegFootIssue("foot_handle_parent", "Leg IK Handle 未挂到 Ball pivot", spec.side.value))
        if spec.pivots[0].roll_control_name and state.swivel_source != (
                spec.ankle_control_path + ".swivel"):
            issues.append(BodyLegFootIssue(
                "foot_swivel", "Leg IK swivel 驱动来源不一致",
                spec.side.value))
        if (state.toe_handle_parent_path != spec.toe_handle_parent_path
                or state.toe_handle_joint_list != (
                    spec.toe_solver_joint_list
                    or (spec.toe_handle_start_path,))
                or state.toe_handle_solver != "ikSCsolver"):
            issues.append(BodyLegFootIssue(
                "foot_toe_ik_handle", "Toes 单链 IK 求解器结构不一致",
                spec.side.value))
        if (state.toe_end_handle_parent_path != spec.toe_control_path
                or state.toe_end_handle_joint_list != (
                    spec.toe_end_solver_joint_list
                    or (spec.toe_driver_path,))
                or state.toe_end_handle_solver != "ikSCsolver"):
            issues.append(BodyLegFootIssue(
                "foot_toe_end_ik_handle", "ToesEnd 单链 IK 求解器结构不一致",
                spec.side.value))
        if spec.qtoes_driver_path and (
                state.qtoes_handle_parent_path != spec.qtoes_handle_parent_path
                or state.qtoes_handle_joint_list != (
                    spec.qtoes_solver_joint_list
                    or (spec.ankle_driver_path,))
                or state.qtoes_handle_solver != "ikSCsolver"):
            issues.append(BodyLegFootIssue(
                "foot_qtoes_ik_handle", "QToes 单链 IK 求解器结构不一致",
                spec.side.value))
        if (
            state.ankle_constraint_name != spec.ankle_constraint_name
            or state.ankle_orientation_source != spec.ankle_orientation_source_path
            or state.ankle_driven_joint != spec.ankle_driver_path
        ):
            issues.append(BodyLegFootIssue(
                "foot_ankle_orientation",
                "Ball pivot 未正确驱动 Ankle IK 朝向",
                spec.side.value,
            ))
        master_value_mismatch = (
            expected_attribute_value is not None
            and abs(
                state.roll.master_value - expected_attribute_value
            ) > tolerance
        )
        if (
            state.roll.master_plug != spec.roll.master_plug
            or master_value_mismatch
        ):
            issues.append(BodyLegFootIssue(
                "foot_roll_master",
                "自动 footRoll 主属性不一致",
                spec.side.value,
            ))
        actual_roll_nodes = {node.name: node for node in state.roll.nodes}
        for expected_node in spec.roll.nodes:
            actual_node = actual_roll_nodes.get(expected_node.name)
            if actual_node is None:
                issues.append(BodyLegFootIssue(
                    "foot_roll_node_missing",
                    "自动 footRoll 节点缺失",
                    expected_node.name,
                ))
                continue
            if (
                actual_node.node_type != expected_node.node_type
                or actual_node.input_connections
                != tuple(
                    (target, source)
                    for source, target in expected_node.input_connections
                )
                or any(
                    actual is None or abs(actual - wanted) > tolerance
                    for (actual_plug, actual), (wanted_plug, wanted) in zip(
                        actual_node.numeric_values,
                        expected_node.numeric_values,
                    )
                    if actual_plug == wanted_plug
                )
                or tuple(plug for plug, _ in actual_node.numeric_values)
                != tuple(plug for plug, _ in expected_node.numeric_values)
            ):
                issues.append(BodyLegFootIssue(
                    "foot_roll_node",
                    "自动 footRoll 节点类型、输入或参数不一致",
                    expected_node.name,
                ))
        toe_pivot_path = next(
            pivot.path for pivot in spec.pivots
            if pivot.role is BodyLegFootPivotRole.TOE
        )
        toe_pivot_path = next(
            (manual.reverse_path for manual in spec.manual_pivots
             if manual.target_path == toe_pivot_path), toe_pivot_path)
        if (
            state.toe_offset_path != spec.toe_offset_path
            or state.toe_offset_parent_path != toe_pivot_path
            or state.toe_control_path != spec.toe_control_path
            or state.toe_control_parent_path != (
                spec.toe_extra_path or spec.toe_offset_path)
            or (spec.source_toe_icon and (
                state.toe_extra_path != spec.toe_extra_path
                or state.toe_extra_parent_path != spec.toe_offset_path))
        ):
            issues.append(BodyLegFootIssue(
                "foot_toe_control_hierarchy",
                "Toe IK 控制层级不一致",
                spec.side.value,
            ))
        if state.toe_control_shape != "nurbsCurve":
            issues.append(BodyLegFootIssue(
                "foot_toe_control_shape",
                "Toe IK 控制缺少 NURBS 曲线",
                spec.side.value,
            ))
        if spec.source_toe_icon and (
            state.toe_control_rotate_order != spec.toe_control_rotate_order
            or state.toe_control_color != 13
            or state.toe_ik_local is not True
            or state.toe_extra_ik_local is not True
        ):
            issues.append(BodyLegFootIssue(
                "foot_toe_control_appearance",
                "Toe IK 图标属性或旋转顺序不一致",
                spec.side.value,
            ))
        if check_initial_pose and (
            not _close(
                state.toe_control_position,
                spec.toe_control_position,
                tolerance,
            )
            or not all(
                _close(actual, expected, tolerance)
                for actual, expected in zip(
                    state.toe_control_axes, spec.toe_control_axes
                )
            )
            or not _close(
                state.toe_control_translation, (0.0, 0.0, 0.0), tolerance
            )
            or not _close(
                state.toe_control_rotation, (0.0, 0.0, 0.0), tolerance
            )
        ):
            issues.append(BodyLegFootIssue(
                "foot_toe_control_pose",
                "Toe IK 控制初始世界帧或本地通道不一致",
                spec.side.value,
            ))
    return tuple(issues)


def _close(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _close_angles(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs((a - b + 180.0) % 360.0 - 180.0) <= tolerance
               for a, b in zip(left, right))


def segmented_foot_roll(
    value: float,
    *,
    ball_break_angle: float = 45.0,
    minimum: float = -360.0,
    maximum: float = 360.0,
) -> tuple[float, float, float]:
    values = (value, ball_break_angle, minimum, maximum)
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not isfinite(float(item))
        for item in values
    ):
        raise BodyLegFootValidationError("footRoll 参数必须是有限数值")
    if minimum >= 0.0 or maximum <= 0.0 or not 0.0 < ball_break_angle < maximum:
        raise BodyLegFootValidationError("footRoll 范围与 Ball 分段角度无效")
    bounded = min(max(float(value), float(minimum)), float(maximum))
    heel = min(bounded, 0.0)
    positive = max(bounded, 0.0)
    ball = min(positive, float(ball_break_angle))
    toe = max(positive - float(ball_break_angle), 0.0)
    return heel, ball, toe
