from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .body_arm_mechanisms import BodyArmMechanismPlan, BodyArmMechanismRole
from .body_controller_layers import (
    BodyExtraControllerState, BodySubControllerState,
    audit_body_extra_controller, audit_body_sub_controller,
)
from .body_controller_appearance import body_fk_curve_radius
from .body_limb_ik import BodyLimbIkValidationError, solve_limb_pole_position
from .body_limb_mechanisms import expanded_ik_solver_chain, body_limb_token_valid, body_limb_sides_valid
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]


BodyArmIkValidationError = BodyLimbIkValidationError


@dataclass(frozen=True, slots=True)
class BodyArmIkSpec:
    side: FitBuildSide
    chain: tuple[str, str, str]
    root_path: str
    wrist_offset_path: str
    wrist_offset_name: str
    wrist_control_path: str
    wrist_control_name: str
    pole_offset_path: str
    pole_offset_name: str
    pole_control_path: str
    pole_control_name: str
    handle_name: str
    pole_constraint_name: str
    wrist_position: Vector3
    wrist_axes: AxisFrame
    pole_position: Vector3
    radius: float
    wrist_constraint_name: str
    solver_joint_list: tuple[str, ...] | None = None
    wrist_sub_path: str | None = None
    wrist_sub_name: str | None = None
    wrist_extra_path: str | None = None
    wrist_extra_name: str | None = None
    pole_extra_path: str | None = None
    pole_extra_name: str | None = None
    wrist_extra_curve: bool = False
    wrist_align_name: str | None = None
    wrist_align_path: str | None = None
    wrist_align_parent_path: str | None = None
    source_aligned_graph: bool = False
    ik_local_mode: str | None = None
    source_middle_position: Vector3 | None = None
    source_middle_axes: AxisFrame | None = None
    source_rotation_order: int = 0
    source_foot_orientation: bool = False
    source_foot_matrix: str | None = None
    source_handle_parent: str | None = None

    @property
    def handle_parent(self):
        return self.source_handle_parent or (
            self.wrist_sub_path or self.wrist_control_path
            if self.source_aligned_graph else self.wrist_control_path)

    @property
    def source_stem(self):
        return self.wrist_control_name.removesuffix('_'+self.side.value)

    @property
    def source_aligned_offset(self):
        return (self.wrist_sub_path or self.wrist_control_path)+'|'+self.source_stem+'FKAlignedOffset_'+self.side.value

    @property
    def source_local_offset(self):
        return (self.wrist_sub_path or self.wrist_control_path)+'|'+self.source_stem+'LocalOffset_'+self.side.value

    @property
    def source_local_extra(self):
        return self.source_local_offset+'|'+self.source_stem+'LocalExtra_'+self.side.value

    @property
    def source_local_control(self):
        return self.source_local_extra+'|'+self.source_stem+'Local_'+self.side.value

    @property
    def orientation_source(self):
        if not self.source_aligned_graph:
            return self.wrist_control_path
        parent=self.source_local_control if self.ik_local_mode=='addCtrl' else self.source_aligned_offset
        return parent+'|'+self.source_stem+'FKAligned_'+self.side.value

    @property
    def source_orientation_matrix(self):
        return self.source_stem+'EndOrientMatrix_'+self.side.value

    @property
    def source_graph_names(self):
        if not self.source_aligned_graph:
            return ()
        names=(self.source_aligned_offset.rsplit('|',1)[-1],
               self.orientation_source.rsplit('|',1)[-1],self.source_orientation_matrix)
        if self.ik_local_mode=='addCtrl':
            names += (self.source_local_offset.rsplit('|',1)[-1],
                      self.source_local_extra.rsplit('|',1)[-1],
                      self.source_local_control.rsplit('|',1)[-1],
                      self.source_local_control.rsplit('|',1)[-1]+'Shape')
        return names


@dataclass(frozen=True, slots=True)
class BodyArmIkPlan:
    root_path: str
    root_name: str
    limbs: tuple[BodyArmIkSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyArmIkState:
    side: FitBuildSide
    wrist_control_path: str
    wrist_parent_path: str | None
    pole_control_path: str
    pole_parent_path: str | None
    handle_name: str
    pole_constraint_name: str
    handle_parent_path: str | None
    joint_list: tuple[str, ...]
    pole_source: str | None
    wrist_position: Vector3
    pole_position: Vector3
    wrist_shape: str | None
    pole_shape: str | None
    wrist_translation: Vector3
    wrist_rotation: Vector3
    pole_translation: Vector3
    pole_rotation: Vector3
    wrist_constraint_name: str
    wrist_source: str | None
    wrist_driven_joint: str | None
    wrist_sub: BodySubControllerState | None = None
    wrist_extra: BodyExtraControllerState | None = None
    pole_extra: BodyExtraControllerState | None = None
    wrist_align_path: str | None = None
    wrist_align_parent_path: str | None = None
    wrist_align_position: Vector3 | None = None
    wrist_align_axes: AxisFrame | None = None


@dataclass(frozen=True, slots=True)
class BodyArmIkSnapshot:
    root_path: str
    limbs: tuple[BodyArmIkState, ...]


@dataclass(frozen=True, slots=True)
class BodyArmIkIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_arm_ik(
    body: BodySkeletonSnapshot,
    mechanisms: BodyArmMechanismPlan,
    *,
    radius: float = 1.5,
    pole_distance_scale: float = 0.75,
    sub_controllers: bool = False,
    extra_controllers: bool = False,
    align_helpers: bool = True,
    joint_names: tuple[str, ...] = ("Shoulder", "Elbow", "Wrist"),
    limb_label: str = "Arm",
    sides: tuple[FitBuildSide, ...] = (FitBuildSide.RIGHT,FitBuildSide.LEFT),
) -> BodyArmIkPlan:
    if (type(sub_controllers) is not bool or type(extra_controllers) is not bool
            or type(align_helpers) is not bool):
        raise BodyArmIkValidationError("IK 控制器开关必须是布尔值")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
        or value <= 0
        for value in (radius, pole_distance_scale)
    ):
        raise BodyArmIkValidationError("IK 控制尺寸参数必须是正有限数值")
    if (not body_limb_sides_valid(sides) or len(joint_names) < 3 or len(set(joint_names)) != len(joint_names)
            or any(not body_limb_token_valid(name)
                   for name in joint_names) or not body_limb_token_valid(limb_label)):
        raise BodyArmIkValidationError("IK 关节链或系统名称无效")
    body_by_name = {joint.name: joint for joint in body.joints}
    fk_by_source = {joint.source_joint: joint.path
                    for joint in mechanisms.joints
                    if joint.role is BodyArmMechanismRole.FK}
    root_name = f"AdvPy_{limb_label}IKControls"
    root_parent = ("|Group|MotionSystem|IKSystem"
                   if body.root.startswith("|Group|DeformationSystem|")
                   else "")
    root_path = root_parent + "|" + root_name
    limbs = []
    for side in sides:
        side_name = side.value
        source_chain = tuple(body_by_name[f"{name}_{side_name}"] for name in joint_names)
        middle_index = len(source_chain) - 1 - len(source_chain) // 2
        sources = (source_chain[0], source_chain[middle_index], source_chain[-1])
        if align_helpers and sources[2].path not in fk_by_source:
            raise BodyArmIkValidationError("Wrist AlignIKTo 缺少 FK 驱动关节")
        full_drivers = tuple(
            spec.path
            for spec in mechanisms.joints
            if spec.side is side and spec.role is BodyArmMechanismRole.IK
            and spec.source_joint in {source.path for source in source_chain}
        )
        if len(full_drivers) != len(joint_names):
            raise BodyArmIkValidationError("IK mechanism 与来源关节链不一致")
        drivers = (full_drivers[0], full_drivers[middle_index], full_drivers[-1])
        solver_chain = expanded_ik_solver_chain(mechanisms, full_drivers)
        shoulder, elbow, wrist = (joint.world_position for joint in sources)
        pole = solve_arm_pole_position(
            shoulder,
            elbow,
            wrist,
            sources[1].world_axes[2],
            distance_scale=float(pole_distance_scale),
        )
        wrist_offset_name = f"AdvPy_{limb_label}IKOffset_{side_name}"
        wrist_control_name = f"AdvPy_{limb_label}IK_{side_name}"
        pole_offset_name = f"AdvPy_{limb_label}PVOffset_{side_name}"
        pole_control_name = f"AdvPy_{limb_label}PV_{side_name}"
        wrist_offset_path = f"{root_path}|{wrist_offset_name}"
        pole_offset_path = f"{root_path}|{pole_offset_name}"
        wrist_extra_name = f"AdvPy_{limb_label}IKExtra_{side_name}"
        pole_extra_name = f"AdvPy_{limb_label}PVExtra_{side_name}"
        wrist_extra_path = f"{wrist_offset_path}|{wrist_extra_name}"
        pole_extra_path = f"{pole_offset_path}|{pole_extra_name}"
        limbs.append(BodyArmIkSpec(
            side, drivers, root_path,
            wrist_offset_path, wrist_offset_name,
            f"{wrist_extra_path}|{wrist_control_name}", wrist_control_name,
            pole_offset_path, pole_offset_name,
            f"{pole_extra_path}|{pole_control_name}", pole_control_name,
            f"AdvPy_{limb_label}IKHandle_{side_name}", f"AdvPy_{limb_label}PVConstraint_{side_name}",
            wrist, sources[2].world_axes, pole,
            body_fk_curve_radius(body, sources[2], float(radius)),
            f"AdvPy_{limb_label}IKWristOrient_{side_name}",
            solver_joint_list=(solver_chain[:-1]
                               if len(solver_chain) > len(drivers) else None),
            wrist_sub_path=(
                f"{wrist_extra_path}|{wrist_control_name}|AdvPy_{limb_label}IKSub_{side_name}"
                if sub_controllers else None),
            wrist_sub_name=(f"AdvPy_{limb_label}IKSub_{side_name}"
                            if sub_controllers else None),
            wrist_extra_path=wrist_extra_path,
            wrist_extra_name=wrist_extra_name,
            pole_extra_path=pole_extra_path,
            pole_extra_name=pole_extra_name,
            wrist_extra_curve=extra_controllers,
            wrist_align_name=(f"AdvPy_AlignIKTo{joint_names[-1]}_{side_name}"
                              if align_helpers else None),
            wrist_align_path=(f"{fk_by_source[sources[2].path]}|"
                              f"AdvPy_AlignIKTo{joint_names[-1]}_{side_name}"
                              if align_helpers else None),
            wrist_align_parent_path=(fk_by_source[sources[2].path]
                                     if align_helpers else None),
        ))
    return BodyArmIkPlan(root_path, root_name, tuple(limbs))


def audit_body_arm_ik(plan: BodyArmIkPlan, snapshot: BodyArmIkSnapshot, *, tolerance: float = 1e-4, check_initial_pose: bool = True) -> tuple[BodyArmIkIssue, ...]:
    issues = []
    if snapshot.root_path != plan.root_path:
        issues.append(BodyArmIkIssue("ik_root_mismatch", "Arm IK 控制根不一致"))
    actual = {state.side: state for state in snapshot.limbs}
    for spec in plan.limbs:
        state = actual.get(spec.side)
        if state is None:
            issues.append(BodyArmIkIssue("missing_ik_limb", "缺少 Arm IK 侧", spec.side.value))
            continue
        checks = (
            (state.wrist_control_path == spec.wrist_control_path and state.wrist_parent_path == spec.wrist_extra_path, "ik_wrist_hierarchy", "Wrist IK 控制父链不一致"),
            (state.pole_control_path == spec.pole_control_path and state.pole_parent_path == spec.pole_extra_path, "ik_pole_hierarchy", "Pole Vector 控制父链不一致"),
            (state.handle_name == spec.handle_name and state.handle_parent_path == spec.handle_parent, "ik_handle_mismatch", "IK Handle 或父级不一致"),
            (state.pole_constraint_name == spec.pole_constraint_name, "ik_pole_constraint", "Pole Vector 约束名称不一致"),
            (state.wrist_constraint_name == spec.wrist_constraint_name and state.wrist_source == spec.orientation_source and state.wrist_driven_joint == spec.chain[2], "ik_wrist_orientation", "Wrist IK 朝向驱动不一致"),
            (state.joint_list == (spec.solver_joint_list or spec.chain[:2]), "ik_chain_mismatch", "RP IK 求解链不一致"),
            (state.pole_source == spec.pole_control_path, "ik_pole_wiring", "Pole Vector 连线不一致"),
            (state.wrist_shape == "nurbsCurve" and state.pole_shape == "nurbsCurve", "ik_shape_mismatch", "IK 控制缺少 NURBS 曲线"),
            (state.wrist_align_path == spec.wrist_align_path and
             state.wrist_align_parent_path == spec.wrist_align_parent_path,
             "ik_wrist_align_hierarchy", "Wrist AlignIKTo 层级不一致"),
        )
        if check_initial_pose:
            checks += (
                (_close(state.wrist_position, spec.wrist_position, tolerance) and _close(state.pole_position, spec.pole_position, tolerance), "ik_position_mismatch", "IK 控制初始位置不一致"),
                (all(_close(value, (0.0, 0.0, 0.0), tolerance) for value in
                     ((state.wrist_translation,state.pole_translation,state.pole_rotation)
                      if spec.ik_local_mode=='nonZero' else
                      (state.wrist_translation,state.wrist_rotation,state.pole_translation,state.pole_rotation))), "ik_channels_nonzero", "IK 控制本地通道未归零"),
            )
            if spec.wrist_align_path is not None and not spec.source_aligned_graph:
                checks += ((state.wrist_align_position is not None
                            and state.wrist_align_axes is not None
                            and _close(state.wrist_align_position,
                                       spec.wrist_position, tolerance)
                            and all(_close(actual, expected, tolerance)
                                    for actual, expected in zip(
                                        state.wrist_align_axes,
                                        spec.wrist_axes)),
                            "ik_wrist_align_pose",
                            "Wrist AlignIKTo 初始姿态不一致"),)
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyArmIkIssue(code, message, spec.side.value))
        for message in audit_body_sub_controller(
                spec.wrist_control_path, spec.wrist_sub_path,
                state.wrist_sub, tolerance=tolerance):
            issues.append(BodyArmIkIssue(
                "ik_sub_control_mismatch", message, spec.side.value))
        if spec.wrist_extra_path is not None:
            for message in audit_body_extra_controller(
                    spec.wrist_offset_path, spec.wrist_control_path,
                    spec.wrist_extra_path, state.wrist_extra,
                    extra_curve=spec.wrist_extra_curve, tolerance=tolerance):
                issues.append(BodyArmIkIssue(
                    "ik_extra_control_mismatch", message, spec.side.value))
        if spec.pole_extra_path is not None:
            for message in audit_body_extra_controller(
                    spec.pole_offset_path, spec.pole_control_path,
                    spec.pole_extra_path, state.pole_extra,
                    extra_curve=False, tolerance=tolerance):
                issues.append(BodyArmIkIssue(
                    "pole_extra_mismatch", message, spec.side.value))
    return tuple(issues)


def solve_arm_pole_position(
    shoulder: Vector3,
    elbow: Vector3,
    wrist: Vector3,
    fallback_axis: Vector3,
    *,
    distance_scale: float = 0.75,
) -> Vector3:
    return solve_limb_pole_position(
        shoulder,
        elbow,
        wrist,
        fallback_axis,
        limb_label="Arm",
        distance_scale=distance_scale,
    )


def _close(a, b, tolerance): return all(abs(x - y) <= tolerance for x, y in zip(a, b))
