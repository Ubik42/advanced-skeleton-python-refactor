from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .fit_container import FitUpAxis
from .matrix import multiply, matrix44


Vector3 = tuple[float, float, float]


class BodyCharacterGlobalValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyPoleArrowSpec:
    limb: str
    side: str
    middle_joint: str
    pole_control: str

    @property
    def locator_name(self) -> str:
        return f"AdvPy_PoleLoc{self.limb}_{self.side}"

    @property
    def annotation_name(self) -> str:
        return f"AdvPy_PoleAnnotation{self.limb}_{self.side}"

    @property
    def locator_path(self) -> str:
        return self.pole_control + "|" + self.locator_name

    @property
    def locator_shape_path(self) -> str:
        return self.locator_path + "|" + self.locator_name + "Shape"

    @property
    def annotation_path(self) -> str:
        return self.middle_joint + "|" + self.annotation_name

    @property
    def annotation_shape_path(self) -> str:
        return self.annotation_path + "|" + self.annotation_name + "Shape"

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.locator_name, self.locator_name + "Shape",
                self.annotation_name, self.annotation_name + "Shape")


@dataclass(frozen=True, slots=True)
class BodyHeadAimFollowSpec:
    target_offset: str
    target_control: str
    parent_joint: str
    bind_world_matrix: tuple[float, ...]
    use_offset_parent_matrix: bool

    @property
    def static_matrix_name(self) -> str:
        return "AdvPy_HeadAimFollowStaticMM"

    @property
    def parent_matrix_name(self) -> str:
        return "AdvPy_HeadAimFollowParentMM"

    @property
    def blend_name(self) -> str:
        return "AdvPy_HeadAimFollowBlend"

    @property
    def local_matrix_name(self) -> str:
        return "AdvPy_HeadAimFollowLocalMM"

    @property
    def decompose_name(self) -> str:
        return "AdvPy_HeadAimFollowDecompose"

    @property
    def scale_name(self) -> str:
        return "AdvPy_HeadAimFollowScale"

    @property
    def reverse_name(self) -> str:
        return "AdvPy_HeadAimFollowReverse"


@dataclass(frozen=True, slots=True)
class BodyCharacterGlobalPlan:
    root_name: str
    root_path: str
    offset_name: str
    offset_path: str
    control_name: str
    control_path: str
    shape_name: str
    up_axis: FitUpAxis
    radius: float
    scale_attribute: str
    scale_default: float
    scale_minimum: float
    scale_node_name: str
    driven_roots: tuple[str, ...]
    scale_destinations: tuple[str, ...]
    joint_visibility_path: str | None
    finger_visibility_paths: tuple[str, ...]
    aim_fk_control_path: str | None
    pole_arrows: tuple[BodyPoleArrowSpec, ...]
    head_aim_follow: BodyHeadAimFollowSpec | None
    root_follow_main_path: str | None = None

    @property
    def root_follow_constraint_name(self) -> str | None:
        return ("RootFollowMain_parentConstraint1"
                if self.root_follow_main_path is not None else None)

    @property
    def root_follow_scale_constraint_name(self) -> str | None:
        return ("RootFollowMain_scaleConstraint1"
                if self.root_follow_main_path is not None else None)

    @property
    def node_names(self) -> tuple[str, ...]:
        return (
            "Group", "MotionSystem", "MainSystem",
            self.root_name,
            self.offset_name,
            self.control_name,
            self.shape_name,
            self.scale_node_name,
            *((self.root_follow_constraint_name,)
              if self.root_follow_constraint_name is not None else ()),
            *((self.root_follow_scale_constraint_name,)
              if self.root_follow_scale_constraint_name is not None else ()),
            *(name for arrow in self.pole_arrows for name in arrow.node_names),
            *((self.head_aim_follow.static_matrix_name,
               self.head_aim_follow.parent_matrix_name,
               self.head_aim_follow.blend_name,
               self.head_aim_follow.local_matrix_name,
               self.head_aim_follow.scale_name,
               *((self.head_aim_follow.decompose_name,)
                 if not self.head_aim_follow.use_offset_parent_matrix else ()))
              if self.head_aim_follow is not None else ()),
        )

    @property
    def group_path(self) -> str:
        return "|Group"

    @property
    def motion_system_path(self) -> str:
        return self.group_path + "|MotionSystem"

    @property
    def main_system_path(self) -> str:
        return self.motion_system_path + "|MainSystem"

    @property
    def scale_source(self) -> str:
        return f"{self.control_path}.{self.scale_attribute}"

    @property
    def visibility_controls(self) -> tuple[tuple[str, str], ...]:
        if not any(path.startswith("|Group|MotionSystem|FKIKSystem|")
                   for path in self.driven_roots):
            return ()
        return (
            ("fkVis", "|Group|MotionSystem|FKSystem"),
            ("ikVis", "|Group|MotionSystem|IKSystem"),
            ("fkIkVis", "|Group|MotionSystem|FKIKSystem"),
            ("bendVis", "|Group|MotionSystem|BendSystem"),
            ("aimVis", "|Group|MotionSystem|AimSystem"),
        )

    @property
    def scale_system_paths(self) -> tuple[str, ...]:
        return (("|Group|MotionSystem|AimSystem",
                 "|Group|MotionSystem|DrivingSystem")
                if self.visibility_controls else ())

    @property
    def has_finger_visibility(self) -> bool:
        return (self.joint_visibility_path is not None
                or bool(self.finger_visibility_paths))

    @property
    def aim_fk_shape_path(self) -> str | None:
        if self.aim_fk_control_path is None:
            return None
        return (self.aim_fk_control_path + "|"
                + self.aim_fk_control_path.rsplit("|", 1)[-1] + "Shape")

    @property
    def reserved_visibility_attributes(self) -> tuple[str, ...]:
        # Main declares these even when the corresponding optional rig is absent.
        return ("aimLRVis", "arrowVis", "drvSysVis")

    @property
    def circle_normal(self) -> Vector3:
        return (
            (0.0, 1.0, 0.0)
            if self.up_axis is FitUpAxis.Y
            else (0.0, 0.0, 1.0)
        )


@dataclass(frozen=True, slots=True)
class BodyCharacterDrivenRootState:
    path: str
    parent_path: str | None
    translation_sources: tuple[str | None, str | None, str | None]
    rotation_sources: tuple[str | None, str | None, str | None]
    scale_sources: tuple[str | None, str | None, str | None]


@dataclass(frozen=True, slots=True)
class BodyCharacterGlobalSnapshot:
    group_path: str
    group_parent_path: str | None
    motion_system_path: str
    motion_system_parent_path: str | None
    main_system_path: str
    main_system_parent_path: str | None
    root_path: str
    root_parent_path: str | None
    root_translation: Vector3
    root_rotation: Vector3
    root_scale: Vector3
    offset_path: str
    offset_parent_path: str | None
    offset_translation: Vector3
    offset_rotation: Vector3
    offset_scale: Vector3
    control_path: str
    control_parent_path: str | None
    control_shape_type: str | None
    control_translation: Vector3
    control_rotation: Vector3
    control_scale: Vector3
    scale_attribute_plug: str
    scale_attribute_value: float
    scale_attribute_minimum: float | None
    control_scale_sources: tuple[str | None, str | None, str | None]
    driven_roots: tuple[BodyCharacterDrivenRootState, ...]
    scale_destination_sources: tuple[tuple[str, str | None], ...]
    scale_node_input_sources: tuple[str | None, str | None, str | None]
    scale_node_operation: int
    scale_node_input2: Vector3
    scale_node_output: Vector3
    visibility_controls: tuple[tuple[str, bool, str | None], ...] = ()
    scale_system_sources: tuple[tuple[str, str | None], ...] = ()
    joint_visibility: tuple[bool, str | None] | None = None
    finger_visibility: tuple[tuple[str, str | None], ...] = ()
    finger_visibility_value: bool | None = None
    aim_fk_visibility: tuple[str, bool, str | None] | None = None
    aim_fk_visibility_value: bool | None = None
    reserved_visibility_values: tuple[tuple[str, bool], ...] = ()
    driving_visibility_source: str | None = None
    pole_arrow_states: tuple[tuple[str, str, str | None, str | None,
                                   bool, bool], ...] = ()
    head_aim_follow_state: tuple | None = None
    root_follow_main_state: tuple[str, str | None, str | None,
                                  str | None, str | None] | None = None


@dataclass(frozen=True, slots=True)
class BodyCharacterGlobalIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_character_global(
    *,
    up_axis: FitUpAxis,
    body_root: str,
    driven_roots: tuple[str, ...],
    scale_destinations: tuple[str, ...],
    radius: float = 12.0,
    body_root_via_controls: bool = False,
    finger_visibility_paths: tuple[str, ...] = (),
    aim_fk_control_path: str | None = None,
    pole_arrows: tuple[BodyPoleArrowSpec, ...] = (),
    head_aim_follow: BodyHeadAimFollowSpec | None = None,
    root_follow_main_path: str | None = None,
) -> BodyCharacterGlobalPlan:
    if (
        not isinstance(up_axis, FitUpAxis)
        or not isinstance(body_root, str)
        or not body_root.startswith("|")
        or not isinstance(driven_roots, tuple)
        or not driven_roots
        or not isinstance(scale_destinations, tuple)
        or not isinstance(body_root_via_controls, bool)
        or not isinstance(finger_visibility_paths, tuple)
        or len(set(finger_visibility_paths)) != len(finger_visibility_paths)
        or any(not isinstance(path, str) or not path.startswith("|")
               for path in finger_visibility_paths)
        or (aim_fk_control_path is not None
            and (not isinstance(aim_fk_control_path, str)
                 or not aim_fk_control_path.startswith("|")))
        or not isinstance(pole_arrows, tuple)
        or any(not isinstance(arrow, BodyPoleArrowSpec)
               or arrow.limb not in ("Arm", "Leg")
               or arrow.side not in ("L", "R")
               or not arrow.middle_joint.startswith("|")
               or not arrow.pole_control.startswith("|")
               for arrow in pole_arrows)
        or len({name for arrow in pole_arrows for name in arrow.node_names})
           != 4 * len(pole_arrows)
        or (head_aim_follow is not None
            and (not isinstance(head_aim_follow, BodyHeadAimFollowSpec)
                 or not all(isinstance(path, str) and path.startswith("|")
                            for path in (head_aim_follow.target_offset,
                                         head_aim_follow.target_control,
                                         head_aim_follow.parent_joint))
                 or type(head_aim_follow.use_offset_parent_matrix) is not bool
                 or len(head_aim_follow.bind_world_matrix) != 16
                 or any(not isinstance(value, (int, float))
                        or not isfinite(float(value))
                        for value in head_aim_follow.bind_world_matrix)))
        or (root_follow_main_path is not None and (
            not body_root_via_controls
            or root_follow_main_path !=
            "|Group|MotionSystem|RootSystem|RootFollowMain"
            or any(path.startswith(root_follow_main_path + "|")
                   for path in driven_roots)))
        or (not body_root_via_controls and body_root not in driven_roots)
        or (body_root_via_controls and (
            body_root in driven_roots
            or not all(f"{body_root}.scale{axis}" in scale_destinations for axis in "XYZ")
        ))
        or len(set(driven_roots)) != len(driven_roots)
        or any(
            not isinstance(path, str)
            or not path.startswith("|")
            or (path.count("|") != 1 and not (
                (path == body_root
                 and path.startswith("|Group|DeformationSystem|")
                 and path.count("|") == 3)
                or (path.startswith("|Group|MotionSystem|RootSystem|RootFollowMain|")
                 and path.count("|") == 5)
                or (path.startswith(("|Group|MotionSystem|FKSystem|",
                                 "|Group|MotionSystem|IKSystem|",
                                 "|Group|MotionSystem|FKIKSystem|",
                                 "|Group|MotionSystem|TwistSystem|"))
                and path.count("|") == 4)))
            for path in driven_roots
        )
        or not isinstance(scale_destinations, tuple)
        or not scale_destinations
        or len(set(scale_destinations)) != len(scale_destinations)
        or any(
            not isinstance(plug, str)
            or "." not in plug
            for plug in scale_destinations
        )
        or isinstance(radius, bool)
        or not isinstance(radius, (int, float))
        or not isfinite(float(radius))
        or float(radius) <= 0.0
    ):
        raise BodyCharacterGlobalValidationError(
            "角色总控的宿主轴、根节点、缩放目标或半径无效"
        )

    root_name = "AdvPy_CharacterControls"
    root_path = f"|Group|MotionSystem|MainSystem|{root_name}"
    offset_name = "AdvPy_GlobalOffset"
    offset_path = f"{root_path}|{offset_name}"
    control_name = "AdvPy_Global"
    control_path = f"{offset_path}|{control_name}"
    names = {"Group", "MotionSystem", "MainSystem", root_name,
             offset_name, control_name, f"{control_name}Shape",
             "MainScaleMultiplyDivide"}
    if any(path.rsplit("|", 1)[-1] in names for path in driven_roots):
        raise BodyCharacterGlobalValidationError(
            "角色总控名称与被驱动根节点冲突"
        )
    return BodyCharacterGlobalPlan(
        root_name=root_name,
        root_path=root_path,
        offset_name=offset_name,
        offset_path=offset_path,
        control_name=control_name,
        control_path=control_path,
        shape_name=f"{control_name}Shape",
        up_axis=up_axis,
        radius=float(radius),
        scale_attribute="globalScale",
        scale_default=1.0,
        scale_minimum=0.0001,
        scale_node_name="MainScaleMultiplyDivide",
        driven_roots=driven_roots,
        scale_destinations=scale_destinations,
        joint_visibility_path=(
            body_root if body_root.startswith("|Group|DeformationSystem|")
            else None),
        finger_visibility_paths=finger_visibility_paths,
        aim_fk_control_path=aim_fk_control_path,
        pole_arrows=pole_arrows,
        head_aim_follow=head_aim_follow,
        root_follow_main_path=root_follow_main_path,
    )


def audit_body_character_global(
    plan: BodyCharacterGlobalPlan,
    snapshot: BodyCharacterGlobalSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyCharacterGlobalIssue, ...]:
    issues = []
    neutral = (0.0, 0.0, 0.0)
    one = (1.0, 1.0, 1.0)
    if not (
        snapshot.group_path == plan.group_path
        and snapshot.group_parent_path is None
        and snapshot.motion_system_path == plan.motion_system_path
        and snapshot.motion_system_parent_path == plan.group_path
        and snapshot.main_system_path == plan.main_system_path
        and snapshot.main_system_parent_path == plan.motion_system_path
    ):
        issues.append(BodyCharacterGlobalIssue(
            "system_hierarchy_mismatch",
            "Group、MotionSystem、MainSystem 层级不一致",
            plan.group_path,
        ))
    if not (
        snapshot.root_path == plan.root_path
        and snapshot.root_parent_path == plan.main_system_path
        and _close(snapshot.root_translation, neutral, tolerance)
        and _close(snapshot.root_rotation, neutral, tolerance)
        and _close(snapshot.root_scale, one, tolerance)
    ):
        issues.append(BodyCharacterGlobalIssue(
            "root_mismatch",
            "角色总控根层级或中性通道不一致",
            plan.root_path,
        ))
    if not (
        snapshot.offset_path == plan.offset_path
        and snapshot.offset_parent_path == plan.root_path
        and _close(snapshot.offset_translation, neutral, tolerance)
        and _close(snapshot.offset_rotation, neutral, tolerance)
        and _close(snapshot.offset_scale, one, tolerance)
    ):
        issues.append(BodyCharacterGlobalIssue(
            "offset_mismatch",
            "角色总控 offset 层级或中性通道不一致",
            plan.offset_path,
        ))
    scale_plug = plan.scale_source
    if not (
        snapshot.control_path == plan.control_path
        and snapshot.control_parent_path == plan.offset_path
        and snapshot.control_shape_type == "nurbsCurve"
        and _close(snapshot.control_translation, neutral, tolerance)
        and _close(snapshot.control_rotation, neutral, tolerance)
        and _close(snapshot.control_scale, one, tolerance)
        and snapshot.scale_attribute_plug == scale_plug
        and abs(snapshot.scale_attribute_value - plan.scale_default) <= tolerance
        and snapshot.scale_attribute_minimum is not None
        and abs(snapshot.scale_attribute_minimum - plan.scale_minimum) <= tolerance
        and snapshot.control_scale_sources == (scale_plug, scale_plug, scale_plug)
    ):
        issues.append(BodyCharacterGlobalIssue(
            "control_mismatch",
            "角色总控曲线、通道或 uniform scale 属性不一致",
            plan.control_path,
        ))

    expected_root_follow = (
        (plan.root_follow_main_path,
         plan.root_follow_constraint_name,
         plan.root_follow_scale_constraint_name,
         plan.control_path, plan.control_path)
        if plan.root_follow_main_path is not None else None)
    if snapshot.root_follow_main_state != expected_root_follow:
        issues.append(BodyCharacterGlobalIssue(
            "root_follow_main_mismatch",
            "RootFollowMain 的 Main 跟随约束不一致",
            plan.root_follow_main_path,
        ))

    actual_roots = {state.path: state for state in snapshot.driven_roots}
    if set(actual_roots) != set(plan.driven_roots):
        issues.append(BodyCharacterGlobalIssue(
            "driven_root_set_mismatch",
            "角色总控被驱动根集合不一致",
        ))
    expected_translate = tuple(
        f"{plan.control_path}.translate{axis}" for axis in "XYZ"
    )
    expected_rotate = tuple(
        f"{plan.control_path}.rotate{axis}" for axis in "XYZ"
    )
    expected_scale = (scale_plug, scale_plug, scale_plug)
    for path in plan.driven_roots:
        state = actual_roots.get(path)
        if state is None:
            continue
        if not (
            state.parent_path == (path.rsplit("|", 1)[0] or None)
            and state.translation_sources == expected_translate
            and state.rotation_sources == expected_rotate
            and state.scale_sources == expected_scale
        ):
            issues.append(BodyCharacterGlobalIssue(
                "driven_root_wiring_mismatch",
                "角色总控根节点变换接线不一致",
                path,
            ))

    expected_destinations = tuple(
        (destination, scale_plug)
        for destination in plan.scale_destinations
    )
    if snapshot.scale_destination_sources != expected_destinations:
        issues.append(BodyCharacterGlobalIssue(
            "scale_destination_mismatch",
            "Arm/Leg 全局比例补偿接线不一致",
        ))
    expected_inputs = tuple(f"{plan.control_path}.scale{axis}"
                            for axis in "XYZ")
    if (snapshot.scale_node_input_sources != expected_inputs
            or snapshot.scale_node_operation != 1
            or not _close(snapshot.scale_node_input2, one, tolerance)
            or not _close(snapshot.scale_node_output, one, tolerance)):
        issues.append(BodyCharacterGlobalIssue(
            "main_scale_node_mismatch",
            "MainScaleMultiplyDivide 比例输出或来源不一致",
            plan.scale_node_name,
        ))
    expected_visibility = tuple(
        (name, True, f"{plan.control_path}.{name}")
        for name, _ in plan.visibility_controls
    )
    if snapshot.visibility_controls != expected_visibility:
        issues.append(BodyCharacterGlobalIssue(
            "system_visibility_mismatch",
            "MotionSystem 子系统的总控可见性接线不一致",
            plan.control_path,
        ))
    expected_system_scales = tuple(
        (f"{path}.scale{axis}",
         f"{plan.scale_node_name}.output{axis}")
        for path in plan.scale_system_paths for axis in "XYZ"
    )
    if snapshot.scale_system_sources != expected_system_scales:
        issues.append(BodyCharacterGlobalIssue(
            "system_scale_mismatch",
            "AimSystem 或 DrivingSystem 的总控比例接线不一致",
            plan.control_path,
        ))
    expected_joint_visibility = (
        (True, f"{plan.control_path}.jointVis")
        if plan.joint_visibility_path is not None else None
    )
    if snapshot.joint_visibility != expected_joint_visibility:
        issues.append(BodyCharacterGlobalIssue(
            "joint_visibility_mismatch",
            "Body 根关节的总控可见性接线不一致",
            plan.joint_visibility_path,
        ))
    expected_finger_visibility = tuple(
        (path + ".visibility", f"{plan.control_path}.fingerVis")
        for path in plan.finger_visibility_paths
    )
    if snapshot.finger_visibility != expected_finger_visibility:
        issues.append(BodyCharacterGlobalIssue(
            "finger_visibility_mismatch",
            "手指 FK 根的总控可见性接线不一致",
            plan.control_path,
        ))
    if snapshot.finger_visibility_value != (
            True if plan.has_finger_visibility else None):
        issues.append(BodyCharacterGlobalIssue(
            "finger_visibility_attribute_mismatch",
            "总控 fingerVis 属性缺失或默认值不一致",
            plan.control_path,
        ))
    expected_aim_fk = (
        (plan.aim_fk_shape_path, True,
         f"{plan.control_path}.aimFKVis")
        if plan.aim_fk_shape_path is not None else None
    )
    if snapshot.aim_fk_visibility != expected_aim_fk:
        issues.append(BodyCharacterGlobalIssue(
            "aim_fk_visibility_mismatch",
            "头部 Aim 的 FK 控制曲线显示连接不一致",
            plan.aim_fk_control_path,
        ))
    if snapshot.aim_fk_visibility_value is not True:
        issues.append(BodyCharacterGlobalIssue(
            "aim_fk_visibility_attribute_mismatch",
            "总控 aimFKVis 属性缺失或默认值不一致",
            plan.control_path,
        ))
    if snapshot.reserved_visibility_values != tuple(
            (name, True) for name in plan.reserved_visibility_attributes):
        issues.append(BodyCharacterGlobalIssue(
            "reserved_visibility_attributes_mismatch",
            "总控预留显示属性缺失或默认值不一致",
            plan.control_path,
        ))
    expected_driving_source = (
        plan.control_path + ".drvSysVis"
        if plan.visibility_controls else None)
    if snapshot.driving_visibility_source != expected_driving_source:
        issues.append(BodyCharacterGlobalIssue(
            "driving_visibility_mismatch",
            "DrivingSystem 显示连接不一致",
            "|Group|MotionSystem|DrivingSystem",
        ))
    expected_arrows = tuple(
        (arrow.locator_path, arrow.annotation_path,
         arrow.locator_shape_path + ".worldMatrix[0]",
         f"{plan.control_path}.arrowVis", True, True)
        for arrow in plan.pole_arrows)
    if snapshot.pole_arrow_states != expected_arrows:
        issues.append(BodyCharacterGlobalIssue(
            "pole_arrow_mismatch",
            "Pole Vector 注释箭头层级或总控接线不一致",
            plan.control_path,
        ))
    follow = plan.head_aim_follow
    state = snapshot.head_aim_follow_state
    follow_ok = state is None if follow is None else False
    if follow is not None and state is not None and len(state) == 16:
        expected_prefix = (
            follow.target_control, 10.0, ((0.0,), (10.0,)),
            follow.use_offset_parent_matrix,
            f"{plan.control_path}.worldMatrix[0]",
            f"{follow.parent_joint}.worldMatrix[0]",
            follow.static_matrix_name + ".matrixSum",
            follow.parent_matrix_name + ".matrixSum",
            follow.target_control + ".follow", 0.1,
            follow.scale_name + ".output",
            follow.blend_name + ".outputMatrix",
            (follow.target_offset.rsplit("|", 1)[0]
             + ".worldInverseMatrix[0]"),
        )
        output = state[13]
        if not isinstance(output, tuple) or len(output) != 5:
            output = (None, (), None, None, ())
        if follow.use_offset_parent_matrix:
            expected_output = (follow.local_matrix_name + ".matrixSum",
                               (None, None, None), None, None)
            neutral_channels = output[4] == ((0.0, 0.0, 0.0),
                                             (0.0, 0.0, 0.0),
                                             (1.0, 1.0, 1.0))
        else:
            expected_output = (
                None,
                tuple(f"{follow.decompose_name}.output{kind}"
                      for kind in ("Translate", "Rotate", "Scale")),
                follow.local_matrix_name + ".matrixSum", 0)
            neutral_channels = True
        follow_ok = (state[:13] == expected_prefix
                     and output[:4] == expected_output
                     and neutral_channels
                     and _close(state[14], follow.bind_world_matrix,
                                tolerance))
        offsets = state[15]
        if len(offsets) != 4 or any(len(matrix) != 16 for matrix in offsets):
            follow_ok = False
        else:
            follow_ok = (follow_ok and _close(
                multiply(matrix44(offsets[0]), matrix44(offsets[2])),
                follow.bind_world_matrix, tolerance) and _close(
                multiply(matrix44(offsets[1]), matrix44(offsets[3])),
                follow.bind_world_matrix, tolerance))
    if not follow_ok:
        issues.append(BodyCharacterGlobalIssue(
            "head_aim_follow_mismatch",
            "Head Aim 目标的 follow 矩阵图或绑定姿态不一致",
            follow.target_control if follow is not None else None,
        ))
    return tuple(issues)


def _close(left, right, tolerance):
    return len(left) == len(right) and all(
        abs(a - b) <= tolerance for a, b in zip(left, right)
    )
