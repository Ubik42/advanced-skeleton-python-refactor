from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_character_global import (
    BodyCharacterGlobalPlan,
    BodyCharacterGlobalSnapshot,
    BodyPoleArrowSpec,
    BodyHeadAimFollowSpec,
    audit_body_character_global,
    fit_character_height,
    plan_body_character_global,
)
from adv_py.core.body_hand_fit import (
    advanced_skeleton_hand_source_joint_names, body_hand_source_joint_names,
)
from adv_py.core.body_build_options import BodyBuildOptions
from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.body_direct_fk_scale import (
    BodyDirectFkScaleSpec, plan_body_direct_fk_scales,
)
from adv_py.core.body_no_control import plan_body_no_control
from adv_py.core.body_fk_global import (
    BodyFkGlobalSpec, BodyFkGlobalState, audit_body_fk_global,
    plan_body_fk_global,
)
from adv_py.core.body_fk_channel_locks import (
    BodyFkChannelLockSpec, plan_body_fk_channel_locks,
)
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_settings import FitSkeletonValidationError

from .body_arm_rig import (
    BodyArmRigBuildPlan,
    BodyArmRigBuildResult,
    BodyArmRigHost,
    BuildBodyArmRig,
)
from .body_leg_rig import (
    BodyLegRigBuildPlan,
    BodyLegRigBuildResult,
    BodyLegRigHost,
    BuildBodyLegRig,
)
from .body_hand_controls import (
    BodyHandFkBuildPlan,
    BodyHandFkBuildResult,
    BodyHandFkHost,
    BuildBodyHandFkControls,
)
from .body_rebuild import InspectBodyRebuildSafety
from .body_rig_validation import body_bind_pose_matches
from .body_torso import BodyTorsoHost, BodyTorsoBuildPlan, BuildBodyTorso
from adv_py.core.body_torso import BodyTorsoSnapshot
from adv_py.core.body_control_spaces import BodyControlSpacesPlan, plan_body_control_spaces


class BodyCharacterRigHost(
    BodyArmRigHost,
    BodyLegRigHost,
    BodyHandFkHost,
    BodyTorsoHost,
    Protocol,
):
    def create_body_control_spaces(self, plan: BodyControlSpacesPlan) -> None: ...
    def scene_up_axis(self) -> FitUpAxis: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_body_character_global(self, plan: BodyCharacterGlobalPlan) -> None: ...
    def capture_body_character_global(
        self,
        plan: BodyCharacterGlobalPlan,
    ) -> BodyCharacterGlobalSnapshot: ...

    def preflight_body_direct_fk_scale(
        self, spec: BodyDirectFkScaleSpec) -> None: ...

    def connect_body_direct_fk_scale(
        self, spec: BodyDirectFkScaleSpec) -> None: ...

    def capture_body_direct_fk_scale(
        self, spec: BodyDirectFkScaleSpec) -> bool: ...

    def hide_body_fk_control(self, control: str) -> None: ...
    def capture_hidden_body_fk_control(self, control: str) -> bool: ...
    def create_body_fk_global(self, spec: BodyFkGlobalSpec) -> None: ...
    def capture_body_fk_global(
        self, spec: BodyFkGlobalSpec,
    ) -> BodyFkGlobalState: ...
    def read_fit_fk_lock_channels(self, joint: str) -> tuple[str, ...]: ...
    def apply_body_fk_channel_locks(
        self, spec: BodyFkChannelLockSpec,
    ) -> None: ...
    def capture_body_fk_channel_locks(
        self, spec: BodyFkChannelLockSpec,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class BodyCharacterRigBuildPlan:
    arm: BodyArmRigBuildPlan
    leg: BodyLegRigBuildPlan
    hand: BodyHandFkBuildPlan | None
    hand_schema_blockers: tuple[str, ...]
    global_control: BodyCharacterGlobalPlan
    global_name_collisions: tuple[str, ...]
    shared_input_stable: bool
    torso: BodyTorsoBuildPlan | None = None
    control_spaces: BodyControlSpacesPlan | None = None
    direct_fk_scales: tuple[BodyDirectFkScaleSpec, ...] = ()
    no_control_paths: tuple[str, ...] = ()
    fk_globals: tuple[BodyFkGlobalSpec, ...] = ()
    fk_channel_locks: tuple[BodyFkChannelLockSpec, ...] = ()

    @property
    def ready(self) -> bool:
        return (
            self.arm.ready
            and self.leg.ready
            and (self.hand is None or self.hand.ready)
            and not self.hand_schema_blockers
            and not self.global_name_collisions
            and self.shared_input_stable
            and (self.torso is None or self.torso.ready)
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        values = list(self.arm.blockers)
        values.extend(
            blocker for blocker in self.leg.blockers if blocker not in values
        )
        if self.torso is not None:
            values.extend(self.torso.blockers)
        if self.hand is not None:
            values.extend(
                blocker for blocker in self.hand.blockers if blocker not in values
            )
        values.extend(
            blocker for blocker in self.hand_schema_blockers if blocker not in values
        )
        if self.global_name_collisions:
            values.append(
                "场景中存在角色总控同名节点："
                + "、".join(self.global_name_collisions)
            )
        if not self.shared_input_stable:
            values.append("Arm/Leg/Hand 预演之间 Body 或 Fit 输入发生变化")
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyCharacterRigBuildResult:
    plan: BodyCharacterRigBuildPlan
    arm: BodyArmRigBuildResult
    leg: BodyLegRigBuildResult
    hand: BodyHandFkBuildResult | None
    global_control: BodyCharacterGlobalSnapshot
    body: BodySkeletonSnapshot
    torso: BodyTorsoSnapshot | None = None
    fk_globals: tuple[BodyFkGlobalState, ...] = ()


class BuildBodyCharacterRig:
    """Build Maya-first limbs, optional complete hands, and global atomically."""

    def __init__(self, host: BodyCharacterRigHost) -> None:
        self._host = host
        self._arm = BuildBodyArmRig(host)
        self._leg = BuildBodyLegRig(host)
        self._hand = BuildBodyHandFkControls(host)
        self._torso = BuildBodyTorso(host)
        self._inspector = InspectBodyRebuildSafety(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        arm_control_radius: float = 1.5,
        leg_control_radius: float = 1.5,
        hand_control_radius: float = 1.5,
        global_control_radius: float = 12.0,
        pole_distance_scale: float = 0.75,
        twist_joints_per_segment: int = 2,
        center_tolerance: float = 0.01,
        include_torso: bool = False,
        include_spine_ik: bool = False,
        include_control_spaces: bool = False,
        torso_control_radius: float = 1.5,
        axial_description=None,
        include_head_aim: bool = False,
    ) -> BodyCharacterRigBuildPlan:
        if not isinstance(include_head_aim,bool) or (include_head_aim and not include_torso):
            raise FitSkeletonValidationError('头部瞄准需要显式启用 Torso')
        if axial_description is not None and not include_torso:
            raise FitSkeletonValidationError('身体描述需要启用 Torso')
        if not isinstance(include_control_spaces, bool) or (include_control_spaces and not include_torso):
            raise FitSkeletonValidationError("控制空间需要显式包含 Torso")
        if not isinstance(include_spine_ik, bool) or (include_spine_ik and not include_torso):
            raise FitSkeletonValidationError("Spine IK 必须以布尔参数显式启用，并包含 Torso")
        if not isinstance(include_torso, bool):
            raise FitSkeletonValidationError("include_torso 必须是布尔值")
        safety = self._inspector.execute(
            container_name, root_name=body_root_name, center_tolerance=center_tolerance,
        )
        if (BodyBuildOptions.from_fit_settings(
                safety.symmetry.settings).use_offset_parent_matrix
                and any(item.tweaker_control
                        for item in safety.symmetry.source.metadata)):
            raise FitSkeletonValidationError(
                "Fit tweakerControl 的 OPM 关节驱动尚未接入 Body 主构建")
        fit_height = fit_character_height(tuple(
            node.world_position for node in
            safety.symmetry.source.hierarchy.joints))
        if (safety.body.fit_height is not None and
                abs(safety.body.fit_height - fit_height) > 1e-5):
            raise FitSkeletonValidationError(
                "Body 来源 Fit 高度与当前 Fit 输入不一致")
        arm = self._arm.plan_from_safety(
            safety,
            control_radius=arm_control_radius,
            pole_distance_scale=pole_distance_scale,
            twist_joints_per_segment=twist_joints_per_segment,
        )
        leg = self._leg.plan_from_safety(
            safety,
            control_radius=leg_control_radius,
            pole_distance_scale=pole_distance_scale,
            twist_joints_per_segment=twist_joints_per_segment,
        )
        expected_hand_names = {
            f"{source_name}_{suffix}"
            for source_name in body_hand_source_joint_names()
            for suffix in ("R", "L")
        }
        original_hand_names = {
            f"{source_name}_{suffix}"
            for source_name in advanced_skeleton_hand_source_joint_names()
            for suffix in ("R", "L")
        }
        body_names = {joint.name for joint in arm.safety.body.joints}
        present_hand_names = body_names & expected_hand_names
        present_original_names = body_names & original_hand_names
        hand = None
        hand_schema_blockers = ()
        if ((present_hand_names == expected_hand_names and not present_original_names)
                or (present_original_names == original_hand_names
                    and not present_hand_names)):
            hand = self._hand.plan_from_safety(
                arm.safety,
                control_radius=hand_control_radius,
            )
        elif present_hand_names or present_original_names:
            expected = (original_hand_names if present_original_names
                        else expected_hand_names)
            present = present_hand_names | present_original_names
            missing = sorted(expected - present)
            hand_schema_blockers = (
                "Body 包含不完整的双侧五指集合，Hand FK 不会静默跳过；"
                f"缺少 {len(missing)} 个关节：" + "、".join(missing),
            )
        torso = (
            self._torso.plan_from_safety(safety, arm, leg, radius=torso_control_radius, spine_ik=include_spine_ik,description=axial_description,head_aim=include_head_aim)
            if include_torso else None
        )
        root_follow_main_path = (
            "|Group|MotionSystem|RootSystem|RootFollowMain"
            if (torso is not None and torso.torso.controls.root_path.startswith(
                "|Group|MotionSystem|RootSystem|RootFollowMain|"))
            else None)
        follow_use_opm = (
            BodyBuildOptions.from_fit_settings(
                safety.symmetry.settings).use_offset_parent_matrix
            if root_follow_main_path is not None else False)
        global_follow_path = (
            "|Group|MotionSystem|GlobalSystem|GlobalFollowMain"
            if safety.body.root.startswith("|Group|DeformationSystem|")
            else None)
        global_follow_use_opm = (
            BodyBuildOptions.from_fit_settings(
                safety.symmetry.settings).use_offset_parent_matrix
            if global_follow_path is not None else False)
        primary_driven = (
            arm.safety.body.root if torso is None else
            torso.torso.controls.root_path
            if root_follow_main_path is None else None)
        driven_roots = (() if primary_driven is None else
                        (primary_driven,)) + (
            arm.mechanisms.root_path,
            arm.fk_controls.root_path,
            arm.ik.root_path,
            arm.twist.root_path,
            leg.mechanisms.root_path,
            leg.fk_controls.root_path,
            leg.ik.root_path,
            leg.twist.root_path,
        )
        global_control = plan_body_character_global(
            up_axis=self._host.scene_up_axis(),
            fit_height=fit_height,
            body_root=arm.safety.body.root,
            driven_roots=driven_roots,
            scale_destinations=(
                f"{arm.stretch.settings_path}."
                f"{arm.stretch.global_scale_attribute}",
                f"{leg.stretch.settings_path}."
                f"{leg.stretch.global_scale_attribute}",
                *(tuple(f"{safety.body.root}.scale{axis}" for axis in "XYZ") if torso else ()),
            ),
            radius=global_control_radius,
            body_root_via_controls=include_torso,
            root_follow_main_path=root_follow_main_path,
            root_follow_use_opm=follow_use_opm,
            global_follow_main_path=global_follow_path,
            global_follow_use_opm=global_follow_use_opm,
            finger_visibility_paths=(
                tuple(root.path for root in hand.controls.roots)
                if hand is not None else ()),
            aim_fk_control_path=(
                torso.torso.head_aim.head_control
                if torso is not None and torso.torso.head_aim is not None
                else None),
            pole_arrows=tuple(
                BodyPoleArrowSpec("Arm", spec.side.value,
                                  spec.chain[1], spec.pole_control_path)
                for spec in arm.ik.limbs) + tuple(
                BodyPoleArrowSpec("Leg", spec.side.value,
                                  spec.chain[1], spec.pole_control_path)
                for spec in leg.ik.limbs),
            head_aim_follow=(
                BodyHeadAimFollowSpec(
                    torso.torso.head_aim.target_offset,
                    torso.torso.head_aim.target,
                    torso.torso.head_aim.follow_parent_joint,
                    tuple(value for axis in torso.torso.head_aim.axes
                          for value in (*axis, 0.0))
                    + (*torso.torso.head_aim.position, 1.0),
                    BodyBuildOptions.from_fit_settings(
                        safety.symmetry.settings).use_offset_parent_matrix)
                if torso is not None and torso.torso.head_aim is not None
                else None),
        )
        spaces = plan_body_control_spaces(safety.body, torso.torso, arm, leg, global_control) if include_control_spaces else None
        direct_controls = (
            (torso.torso.controls.controls if torso else ())
            + (hand.controls.controls if hand else ()))
        direct_fk_scales = plan_body_direct_fk_scales(
            safety.body, direct_controls)
        fk_controls = (
            arm.fk_controls.controls + leg.fk_controls.controls
            + (hand.controls.controls if hand else ())
            + (torso.torso.controls.controls if torso else ()))
        no_control_paths = plan_body_no_control(
            safety.symmetry.source.metadata,
            fk_controls)
        fk_globals = plan_body_fk_global(
            safety.symmetry.source.metadata, fk_controls)
        fk_channel_locks = plan_body_fk_channel_locks(
            safety.symmetry.source.hierarchy, fk_controls,
            tuple((joint.path, self._host.read_fit_fk_lock_channels(
                joint.path)) for joint in
                safety.symmetry.source.hierarchy.joints))
        if fk_globals and global_follow_path is None:
            raise FitSkeletonValidationError(
                "Fit Global 控制需要标准 Body 的 GlobalSystem 层级")
        collisions = tuple(sorted({
            path
            for name in (global_control.node_names
                         + (spaces.node_names if spaces else ())
                         + tuple(name for spec in fk_globals
                                 for name in spec.node_names))
            if not (name in ("Group", "MotionSystem") and safety.body.root.startswith(
                "|Group|DeformationSystem|"))
            for path in self._host.find_name_collisions(name)
        }))
        return BodyCharacterRigBuildPlan(
            arm=arm,
            leg=leg,
            hand=hand,
            hand_schema_blockers=hand_schema_blockers,
            global_control=global_control,
            global_name_collisions=collisions,
            torso=torso,
            control_spaces=spaces,
            direct_fk_scales=direct_fk_scales,
            no_control_paths=no_control_paths,
            fk_globals=fk_globals,
            fk_channel_locks=fk_channel_locks,
            shared_input_stable=(
                arm.safety == leg.safety
                and (hand is None or hand.safety == arm.safety)
            ),
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        arm_control_radius: float = 1.5,
        leg_control_radius: float = 1.5,
        hand_control_radius: float = 1.5,
        global_control_radius: float = 12.0,
        pole_distance_scale: float = 0.75,
        twist_joints_per_segment: int = 2,
        center_tolerance: float = 0.01,
        include_torso: bool = False,
        include_spine_ik: bool = False,
        include_control_spaces: bool = False,
        torso_control_radius: float = 1.5,
        axial_description=None,
        include_head_aim: bool = False,
    ) -> BodyCharacterRigBuildResult:
        plan = self.plan(
            container_name,
            body_root_name=body_root_name,
            arm_control_radius=arm_control_radius,
            leg_control_radius=leg_control_radius,
            hand_control_radius=hand_control_radius,
            global_control_radius=global_control_radius,
            include_torso=include_torso,
            include_spine_ik=include_spine_ik,
            include_control_spaces=include_control_spaces,
            torso_control_radius=torso_control_radius,
            axial_description=axial_description,
            include_head_aim=include_head_aim,
            pole_distance_scale=pole_distance_scale,
            twist_joints_per_segment=twist_joints_per_segment,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Character Rig 构建预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        self._arm.prepare_runtime()
        self._leg.prepare_runtime()
        with self._host.transaction("构建完整角色 Arm/Leg/Hand 与总控"):
            current = self._inspector.execute(
                container_name,
                root_name=body_root_name,
                center_tolerance=center_tolerance,
            )
            if current != plan.arm.safety:
                raise RuntimeError(
                    "Character Rig 执行前 Body 或 Fit 输入发生变化"
                )
            arm = self._arm.build_in_transaction(plan.arm)
            leg = self._leg.build_in_transaction(plan.leg)
            hand = (
                self._hand.build_in_transaction(plan.hand)
                if plan.hand is not None else None
            )
            torso = self._torso.build_in_transaction(plan.torso) if plan.torso else None
            for control in plan.no_control_paths:
                self._host.hide_body_fk_control(control)
            if any(not self._host.capture_hidden_body_fk_control(control)
                   for control in plan.no_control_paths):
                raise RuntimeError("Fit noControl 曲线隐藏状态不一致")
            self._host.create_body_character_global(plan.global_control)
            for spec in plan.fk_globals:
                self._host.create_body_fk_global(spec)
            fk_global_states = tuple(
                self._host.capture_body_fk_global(spec)
                for spec in plan.fk_globals)
            if any(audit_body_fk_global(spec, state)
                   for spec, state in zip(plan.fk_globals,
                                          fk_global_states)):
                raise RuntimeError("FK Global 矩阵层构建后复检失败")
            for spec in plan.direct_fk_scales:
                self._host.preflight_body_direct_fk_scale(spec)
            for spec in plan.direct_fk_scales:
                self._host.connect_body_direct_fk_scale(spec)
            if any(not self._host.capture_body_direct_fk_scale(spec)
                   for spec in plan.direct_fk_scales):
                raise RuntimeError("Body FK 缩放连接不一致")
            global_control = self._host.capture_body_character_global(
                plan.global_control
            )
            issues = audit_body_character_global(
                plan.global_control,
                global_control,
            )
            if issues:
                raise RuntimeError(
                    "角色总控阶段复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            if plan.control_spaces:
                self._host.create_body_control_spaces(plan.control_spaces)
            for spec in plan.fk_channel_locks:
                self._host.apply_body_fk_channel_locks(spec)
            if any(not self._host.capture_body_fk_channel_locks(spec)
                   for spec in plan.fk_channel_locks):
                raise RuntimeError("Fit FK 控制通道锁定状态不一致")
            body = self._host.capture_body_skeleton(body_root_name)
            if not body_bind_pose_matches(plan.arm.safety.body, body):
                raise RuntimeError("角色总控中性状态改变了 Body 绑定姿态")
            container = plan.arm.safety.symmetry.source.hierarchy.container
            if (
                self._host.capture_fit_orientation(container)
                != plan.arm.safety.symmetry.source
                or self._host.read_fit_skeleton_settings(container)
                != plan.arm.safety.symmetry.settings
            ):
                raise RuntimeError("Character Rig 构建后 Fit 输入变化")
        return BodyCharacterRigBuildResult(
            plan=plan,
            arm=arm,
            leg=leg,
            hand=hand,
            global_control=global_control,
            body=body,
            torso=torso,
            fk_globals=fk_global_states,
        )
