from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .body_leg_ik import BodyLegIkPlan
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]


class BodyLegFootValidationError(ValueError):
    pass


class BodyLegFootPivotRole(str, Enum):
    HEEL = "heel"
    OUTER = "outer"
    INNER = "inner"
    TOE = "toe"
    BALL = "ball"


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
class BodyLegFootSideSpec:
    side: FitBuildSide
    ankle_control_path: str
    handle_name: str
    initial_handle_parent_path: str
    ankle_driver_path: str
    toe_driver_path: str
    ankle_constraint_name: str
    toe_constraint_name: str
    toe_offset_name: str
    toe_offset_path: str
    toe_control_name: str
    toe_control_path: str
    toe_control_position: Vector3
    toe_control_axes: AxisFrame
    toe_control_radius: float
    roll: BodyLegFootRollSpec
    pivots: tuple[BodyLegFootPivotSpec, ...]

    @property
    def attributes(self) -> tuple[str, ...]:
        return (self.roll.master_attribute,) + tuple(
            pivot.attribute for pivot in self.pivots
        )

    @property
    def final_handle_parent_path(self) -> str:
        return self.pivots[-1].path

    @property
    def ankle_orientation_source_path(self) -> str:
        return self.pivots[-1].path

    @property
    def toe_orientation_source_path(self) -> str:
        return self.toe_control_path


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
class BodyLegFootSideState:
    side: FitBuildSide
    attribute_values: tuple[tuple[str, float], ...]
    pivots: tuple[BodyLegFootPivotState, ...]
    handle_parent_path: str | None
    ankle_constraint_name: str | None
    ankle_orientation_source: str | None
    ankle_driven_joint: str | None
    toe_constraint_name: str | None
    toe_orientation_source: str | None
    toe_driven_joint: str | None
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
) -> BodyLegFootPlan:
    body_by_name = {joint.name: joint for joint in body.joints}
    if len(body_by_name) != len(body.joints):
        raise BodyLegFootValidationError("Body 关节名称必须唯一")

    marker_roles = (
        (BodyLegFootPivotRole.HEEL, "Heel", "heelRoll", "Y", 1.0),
        (BodyLegFootPivotRole.OUTER, "FootSideOuter", "outerBank", "X", 1.0),
        (BodyLegFootPivotRole.INNER, "FootSideInner", "innerBank", "X", -1.0),
        (BodyLegFootPivotRole.TOE, "ToesEnd", "toeRoll", "Y", 1.0),
        (BodyLegFootPivotRole.BALL, "Toes", "ballRoll", "Y", 1.0),
    )
    sides = []
    for limb in ik.limbs:
        suffix = limb.side.value
        master_attribute = "footRoll"
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
        required = tuple(f"{marker}_{suffix}" for _, marker, *_ in marker_roles)
        if any(name not in body_by_name for name in required):
            raise BodyLegFootValidationError(
                f"Body 缺少 {suffix} 侧唯一的 Heel/FootSide/Toes 标记"
            )
        if any(body_by_name[name].side is not limb.side for name in required):
            raise BodyLegFootValidationError(f"Foot 标记侧向与名称不一致：{suffix}")

        parent = limb.ankle_control_path
        pivots = []
        for role, marker, attribute, axis, multiplier in marker_roles:
            name = f"AdvPy_Foot{role.value.title()}Pivot_{suffix}"
            path = f"{parent}|{name}"
            multiplier_name = (
                f"AdvPy_FootInnerBankSign_{suffix}"
                if multiplier != 1.0
                else None
            )
            manual_source = f"{limb.ankle_control_path}.{attribute}"
            source = (
                f"{sum_names[role]}.output1D"
                if role in sum_names
                else (
                    f"{multiplier_name}.output"
                    if multiplier_name else manual_source
                )
            )
            pivots.append(BodyLegFootPivotSpec(
                role=role,
                name=name,
                path=path,
                parent_path=parent,
                world_position=body_by_name[f"{marker}_{suffix}"].world_position,
                attribute=attribute,
                rotation_axis=axis,
                source_plug=source,
                target_plug=f"{path}.rotate{axis}",
                multiplier_name=multiplier_name,
                multiplier=multiplier,
            ))
            parent = path
        toe_pivot_path = next(
            pivot.path for pivot in pivots
            if pivot.role is BodyLegFootPivotRole.TOE
        )
        toe_offset_name = f"AdvPy_ToeIKOffset_{suffix}"
        toe_offset_path = f"{toe_pivot_path}|{toe_offset_name}"
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
                            f"{limb.ankle_control_path}.{next(p.attribute for p in pivots if p.role is role)}",
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
        )
        sides.append(BodyLegFootSideSpec(
            side=limb.side,
            ankle_control_path=limb.ankle_control_path,
            handle_name=limb.handle_name,
            initial_handle_parent_path=limb.ankle_control_path,
            ankle_driver_path=limb.chain[2],
            toe_driver_path=limb.toe_driver_path,
            ankle_constraint_name=limb.ankle_constraint_name,
            toe_constraint_name=f"AdvPy_LegIKToesOrient_{suffix}",
            toe_offset_name=toe_offset_name,
            toe_offset_path=toe_offset_path,
            toe_control_name=toe_control_name,
            toe_control_path=f"{toe_offset_path}|{toe_control_name}",
            toe_control_position=body_by_name[f"Toes_{suffix}"].world_position,
            toe_control_axes=body_by_name[f"Toes_{suffix}"].world_axes,
            toe_control_radius=limb.radius * 0.65,
            roll=BodyLegFootRollSpec(
                master_attribute,
                master_plug,
                minimum,
                maximum,
                ball_break,
                roll_nodes,
            ),
            pivots=tuple(pivots),
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
                    abs(value - expected_attribute_value) > tolerance
                    for _, value in state.attribute_values
                )
            )
        ):
            issues.append(BodyLegFootIssue("foot_attributes", "Foot 属性或默认值不一致", spec.side.value))
        pivot_by_role = {pivot.role: pivot for pivot in state.pivots}
        for pivot in spec.pivots:
            actual_pivot = pivot_by_role.get(pivot.role)
            subject = f"{spec.side.value}:{pivot.role.value}"
            if actual_pivot is None:
                issues.append(BodyLegFootIssue("missing_foot_pivot", "缺少 Foot pivot", subject))
                continue
            if actual_pivot.path != pivot.path or actual_pivot.parent_path != pivot.parent_path:
                issues.append(BodyLegFootIssue("foot_pivot_hierarchy", "Foot pivot 层级不一致", subject))
            if check_initial_pose and not _close(
                actual_pivot.world_position, pivot.world_position, tolerance
            ):
                issues.append(BodyLegFootIssue("foot_pivot_position", "Foot pivot 位置不一致", subject))
            if actual_pivot.rotation_source != pivot.source_plug:
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
        if (
            state.toe_offset_path != spec.toe_offset_path
            or state.toe_offset_parent_path != toe_pivot_path
            or state.toe_control_path != spec.toe_control_path
            or state.toe_control_parent_path != spec.toe_offset_path
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
        if (
            state.toe_constraint_name != spec.toe_constraint_name
            or state.toe_orientation_source != spec.toe_orientation_source_path
            or state.toe_driven_joint != spec.toe_driver_path
        ):
            issues.append(BodyLegFootIssue(
                "foot_toe_orientation",
                "Toe IK 控制未正确驱动 Toes IK 朝向",
                spec.side.value,
            ))
    return tuple(issues)


def _close(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


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
