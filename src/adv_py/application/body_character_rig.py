from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from typing import Protocol

from adv_py.core.body_character_global import (
    BodyCharacterGlobalPlan,
    BodyCharacterGlobalSnapshot,
    BodyPoleArrowSpec,
    BodyHeadAimFollowSpec,
    BodySpineRootScaleSpec,
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
from adv_py.core.fit_bendy import FitBendyFkScaleSpec
from adv_py.core.body_fk_scale_compensation import (
    BodyFkScaleCompensationSpec, plan_body_fk_scale_compensation,
)
from adv_py.core.body_no_control import plan_body_no_control
from adv_py.core.body_fk_global import (
    BodyFkGlobalSpec, BodyFkGlobalState, audit_body_fk_global,
    plan_body_fk_global,
)
from adv_py.core.body_fk_channel_locks import (
    BodyFkChannelLockSpec, plan_body_fk_channel_locks,
)
from adv_py.core.body_fit_aim import BodyFitAimSpec, plan_body_fit_aim
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_metadata import FitJointField
from adv_py.core.fit_part import FitPartFinalPaths
from adv_py.core.fit_tweaker import FitTweakerPlan, plan_fit_tweakers
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
from .body_fk_scale_compensation import BuildBodyFkScaleCompensation
from .fit_tweaker import BuildFitTweakers
from .body_torso import BodyTorsoHost, BodyTorsoBuildPlan, BuildBodyTorso
from adv_py.core.body_torso import BodyTorsoSnapshot
from adv_py.core.body_control_spaces import BodyControlSpacesPlan, plan_body_control_spaces
from adv_py.core.body_leg_pole_aim import (
    BodyLegPoleAimSpec, plan_body_leg_pole_aim,
)


class BodyCharacterRigHost(
    BodyArmRigHost,
    BodyLegRigHost,
    BodyHandFkHost,
    BodyTorsoHost,
    Protocol,
):
    def create_body_control_spaces(self, plan: BodyControlSpacesPlan) -> None: ...
    def create_body_leg_pole_aim(self, spec: BodyLegPoleAimSpec) -> None: ...
    def capture_body_leg_pole_aim(self, spec: BodyLegPoleAimSpec) -> bool: ...
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

    def preflight_body_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec) -> None: ...

    def connect_body_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec) -> None: ...

    def capture_body_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec) -> bool: ...

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
    def create_body_fit_aim(self, spec: BodyFitAimSpec, *,
                            global_control: str,
                            use_offset_parent_matrix: bool) -> None: ...
    def capture_body_fit_aim(self, spec: BodyFitAimSpec, *,
                             global_control: str,
                             use_offset_parent_matrix: bool) -> bool: ...


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
    pole_aim: tuple[BodyLegPoleAimSpec, ...] = ()
    fit_tweakers: FitTweakerPlan | None = None
    direct_fk_scales: tuple[BodyDirectFkScaleSpec, ...] = ()
    bendy_fk_scales: tuple[FitBendyFkScaleSpec, ...] = ()
    fk_scale_compensations: tuple[BodyFkScaleCompensationSpec, ...] = ()
    no_control_paths: tuple[str, ...] = ()
    fk_globals: tuple[BodyFkGlobalSpec, ...] = ()
    fk_channel_locks: tuple[BodyFkChannelLockSpec, ...] = ()
    fit_aim: tuple[BodyFitAimSpec, ...] = ()

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
        defer_fit_tweakers: bool = False,
        defer_curve_guides: bool = False,
        defer_partial_hand_to_generic: bool = False,
        part_paths: FitPartFinalPaths | None = None,
        standard_fkx_joint_names: frozenset[str] | None = None,
        standard_point_control_names: frozenset[str] | None = None,
        hand_fkx_joint_names: frozenset[str] | None = None,
        hand_point_control_names: frozenset[str] | None = None,
        standard_fk_independent_controls: frozenset[str] | None = None,
        torso_fkx_joint_names: frozenset[str] | None = None,
    ) -> BodyCharacterRigBuildPlan:
        if type(defer_fit_tweakers) is not bool:
            raise FitSkeletonValidationError("Tweaker 延后构建选项必须是布尔值")
        if type(defer_partial_hand_to_generic) is not bool:
            raise FitSkeletonValidationError("局部手指通用 FK 选项必须是布尔值")
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
            part_paths=part_paths,
        )
        curve_guides = tuple(item.joint for item in
                             safety.symmetry.source.metadata
                             if item.curve_guide is not None)
        if curve_guides and not defer_curve_guides:
            raise FitSkeletonValidationError(
                "独立 Body Rig 构建不包含 Curve Guide；请使用完整角色构建："
                + "、".join(curve_guides))
        # ADV 6.925 ignores aim on terminal Fit joints; only a joint with a
        # direct child enters the generic FKAim/AimSystem construction loop.
        fit_parents = {joint.dag_parent for joint in
                       safety.symmetry.source.hierarchy.joints}
        aim_source_names = frozenset(
            item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            for item in safety.symmetry.source.metadata
            if ((FitJointField.AIM in item.present_fields
                 and item.joint in fit_parents)
                or (defer_curve_guides and item.curve_guide is not None)))
        arm_aim = aim_source_names & frozenset(("Shoulder", "Elbow", "Wrist"))
        leg_aim = aim_source_names & frozenset(("Hip", "Knee", "Ankle",
                                                "Toes", "ToesEnd"))
        # The MEL moves an Inbetween start's FKX under FKOffset and drives it
        # with its Inbetween matrix. That final receiver is built by the
        # Inbetween stage, so the ordinary FK receiver must not compete.
        inbetween_starts = frozenset(
            item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            for item in safety.symmetry.source.metadata
            if (item.inbetween_joints or 0) > 0)
        fkx_joint_names = (standard_fkx_joint_names
                           if standard_fkx_joint_names is not None else
                           frozenset(
                               f"AdvPy_{joint}FK_{side}"
                               for joint in ("Shoulder", "Elbow", "Wrist",
                                             "Hip", "Knee", "Ankle",
                                             "Toes", "ToesEnd")
                               for side in ("R", "L")
                               if joint not in inbetween_starts))
        fresh_hand_fkx_names = frozenset(
            f"AdvPy_{digit}{index}FK_{side}"
            for digit in ("Thumb", "Index", "Middle", "Ring", "Pinky")
            for index in range(1, 5)
            for side in ("R", "L")
            if (f"{digit}Finger{index}" not in inbetween_starts
                and f"{digit}{index}" not in inbetween_starts
                and (index != 4 or f"{digit}End" not in inbetween_starts)))
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
            aim_joint_names=arm_aim,
            fkx_joint_names=fkx_joint_names,
            point_control_names=standard_point_control_names,
        )
        leg = self._leg.plan_from_safety(
            safety,
            control_radius=leg_control_radius,
            pole_distance_scale=pole_distance_scale,
            twist_joints_per_segment=twist_joints_per_segment,
            defer_pole_aim=include_control_spaces,
            aim_joint_names=leg_aim,
            fkx_joint_names=fkx_joint_names,
            point_control_names=standard_point_control_names,
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
                aim_joint_names=aim_source_names,
                fkx_joint_names=(hand_fkx_joint_names
                                 if hand_fkx_joint_names is not None
                                 else fresh_hand_fkx_names),
                point_control_names=hand_point_control_names,
            )
        elif present_hand_names or present_original_names:
            if not defer_partial_hand_to_generic:
                expected = (original_hand_names if present_original_names
                            else expected_hand_names)
                present = present_hand_names | present_original_names
                missing = sorted(expected - present)
                hand_schema_blockers = (
                    "Body 包含不完整的双侧五指集合；"
                    "局部手指需要完整角色构建中的通用 FK；"
                    f"缺少 {len(missing)} 个五指宏关节："
                    + "、".join(missing),
                )
            # MEL permits one-to-four fingers and asymmetric optional digits.
            # The full character pipeline builds them in its generic FK pass.
        torso = (
            self._torso.plan_from_safety(safety, arm, leg, radius=torso_control_radius, spine_ik=include_spine_ik,description=axial_description,head_aim=include_head_aim,aim_joint_names=aim_source_names,fkx_joint_names=torso_fkx_joint_names)
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
        root_scale_spec = None
        if torso is not None:
            if torso.torso.spine is not None:
                spine = torso.torso.spine
                root_scale_spec = BodySpineRootScaleSpec(
                    body_root=safety.body.root,
                    fk_scale_plug=spine.fk_controls[0] + ".scale",
                    ik_scale_plug=spine.joints[3].path + ".scale",
                    mode_plug=spine.blend_plug,
                )
            elif torso.torso.spline is not None:
                spline = torso.torso.spline
                root_scale_spec = BodySpineRootScaleSpec(
                    body_root=safety.body.root,
                    fk_scale_plug=spline.fk_controls[0] + ".scale",
                    ik_scale_plug=(spline.joints[len(spline.body_joints)].path
                                   + ".scale"),
                    mode_plug=spline.settings + ".spineIkFk",
                )
        global_control = plan_body_character_global(
            up_axis=self._host.scene_up_axis(),
            num_main_extras=next(
                (metadata.num_main_extras or 0
                 for metadata in safety.symmetry.source.metadata
                 if metadata.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1] == "Root"),
                0),
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
            spine_root_scale=root_scale_spec,
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
        fit_tweakers = (
            plan_fit_tweakers(
                safety.symmetry.instances,
                safety.symmetry.source.metadata, (),
                motion_system_path=(
                    global_control.root_path.rsplit("|", 2)[0]),
                global_control_path=global_control.control_path,
                body_profiles={joint.path: joint.deform_profile
                               for joint in safety.body.joints})
            if (not defer_fit_tweakers
                and BodyBuildOptions.from_fit_settings(
                    safety.symmetry.settings).use_offset_parent_matrix
                and any(item.tweaker_control
                        for item in safety.symmetry.source.metadata))
            else None)
        pole_aim = (
            plan_body_leg_pole_aim(leg.ik, torso.torso, foot=leg.foot)
            if include_control_spaces and torso is not None
            and BodyBuildOptions.from_fit_settings(
                safety.symmetry.settings).use_offset_parent_matrix
            else ())
        spaces = (plan_body_control_spaces(
            safety.body, torso.torso, arm, leg, global_control,
            pole_aim=pole_aim) if include_control_spaces else None)
        direct_controls = (
            (torso.torso.controls.controls if torso else ())
            + (hand.controls.controls if hand else ()))
        direct_fk_scales = plan_body_direct_fk_scales(
            safety.body, direct_controls)
        fk_scale_compensations = plan_body_fk_scale_compensation(
            arm.fk_controls.controls + leg.fk_controls.controls
            + (hand.controls.controls if hand else ())
            + (torso.torso.controls.controls if torso else ()),
            safety.symmetry.instances,
            safety.symmetry.source.metadata,
            use_offset_parent_matrix=BodyBuildOptions.from_fit_settings(
                safety.symmetry.settings).use_offset_parent_matrix,
            finger_control_paths=frozenset(
                control.control_path for control in hand.controls.controls)
            if hand else frozenset(),
            generated_joint_sources=tuple(
                (joint.path, joint.source_joint)
                for joint in torso.torso.spline.joints[
                    :len(torso.torso.spline.body_joints)])
            if torso and torso.torso.spline else ())
        if BodyBuildOptions.from_fit_settings(
                safety.symmetry.settings).use_offset_parent_matrix:
            fk_scale_compensations = tuple(replace(
                spec,
                independent_parent=(
                    standard_fk_independent_controls is None
                    or spec.control_path in
                    standard_fk_independent_controls),
                main_scale_source_path=(
                    global_control.control_path
                    if (standard_fk_independent_controls is None
                        or spec.control_path in
                        standard_fk_independent_controls)
                    else None)) for spec in fk_scale_compensations)
        fk_controls = (
            arm.fk_controls.controls + leg.fk_controls.controls
            + (hand.controls.controls if hand else ())
            + (torso.torso.controls.controls if torso else ()))
        fit_aim = plan_body_fit_aim(
            safety.symmetry.source.hierarchy,
            safety.symmetry.source.metadata,
            safety.body,
            fk_controls)
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
                         + tuple(name for spec in pole_aim
                                 for name in spec.node_names)
                         + ((fit_tweakers.system_path.rsplit("|", 1)[-1],)
                            + tuple(name for spec in fit_tweakers.controls
                                    for name in spec.node_names)
                            if fit_tweakers else ())
                         + tuple(name for spec in fk_globals
                                 for name in spec.node_names)
                         + tuple(name for spec in fit_aim
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
            pole_aim=pole_aim,
            fit_tweakers=fit_tweakers,
            direct_fk_scales=direct_fk_scales,
            fk_scale_compensations=fk_scale_compensations,
            no_control_paths=no_control_paths,
            fk_globals=fk_globals,
            fk_channel_locks=fk_channel_locks,
            fit_aim=fit_aim,
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
        defer_fit_tweakers: bool = False,
        defer_curve_guides: bool = False,
        defer_partial_hand_to_generic: bool = False,
        part_paths: FitPartFinalPaths | None = None,
        standard_fkx_joint_names: frozenset[str] | None = None,
        standard_point_control_names: frozenset[str] | None = None,
        hand_fkx_joint_names: frozenset[str] | None = None,
        hand_point_control_names: frozenset[str] | None = None,
        standard_fk_independent_controls: frozenset[str] | None = None,
        torso_fkx_joint_names: frozenset[str] | None = None,
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
            defer_fit_tweakers=defer_fit_tweakers,
            defer_curve_guides=defer_curve_guides,
            defer_partial_hand_to_generic=defer_partial_hand_to_generic,
            part_paths=part_paths,
            standard_fkx_joint_names=standard_fkx_joint_names,
            standard_point_control_names=standard_point_control_names,
            hand_fkx_joint_names=hand_fkx_joint_names,
            hand_point_control_names=hand_point_control_names,
            standard_fk_independent_controls=(
                standard_fk_independent_controls),
            torso_fkx_joint_names=torso_fkx_joint_names,
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
                part_paths=part_paths,
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
            self._host.create_body_character_global(plan.global_control)
            BuildBodyFkScaleCompensation(self._host).apply(
                plan.fk_scale_compensations)
            for control in plan.no_control_paths:
                self._host.hide_body_fk_control(control)
            if any(not self._host.capture_hidden_body_fk_control(control)
                   for control in plan.no_control_paths):
                raise RuntimeError("Fit noControl 曲线隐藏状态不一致")
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
            aim_use_opm = BodyBuildOptions.from_fit_settings(
                plan.arm.safety.symmetry.settings).use_offset_parent_matrix
            for spec in plan.fit_aim:
                self._host.create_body_fit_aim(
                    spec, global_control=plan.global_control.control_path,
                    use_offset_parent_matrix=aim_use_opm)
            if any(not self._host.capture_body_fit_aim(
                    spec, global_control=plan.global_control.control_path,
                    use_offset_parent_matrix=aim_use_opm)
                   for spec in plan.fit_aim):
                raise RuntimeError("通用 Fit Aim 构建后复检失败")
            for spec in plan.pole_aim:
                self._host.create_body_leg_pole_aim(spec)
            if any(not self._host.capture_body_leg_pole_aim(spec)
                   for spec in plan.pole_aim):
                raise RuntimeError("Leg PoleAim 构建后复检失败")
            if plan.control_spaces:
                self._host.create_body_control_spaces(plan.control_spaces)
            for spec in plan.fk_channel_locks:
                self._host.apply_body_fk_channel_locks(spec)
            if any(not self._host.capture_body_fk_channel_locks(spec)
                   for spec in plan.fk_channel_locks):
                raise RuntimeError("Fit FK 控制通道锁定状态不一致")
            if plan.fit_tweakers is not None:
                BuildFitTweakers(self._host).apply(plan.fit_tweakers)
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
