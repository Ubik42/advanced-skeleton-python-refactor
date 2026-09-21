from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_character_global import (
    BodyCharacterGlobalPlan,
    BodyCharacterGlobalSnapshot,
    audit_body_character_global,
    plan_body_character_global,
)
from adv_py.core.body_hand_fit import body_hand_source_joint_names
from adv_py.core.body_skeleton import BodySkeletonSnapshot
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
        leg_control_radius: float = 1.75,
        hand_control_radius: float = 0.3,
        global_control_radius: float = 12.0,
        pole_distance_scale: float = 0.75,
        twist_joints_per_segment: int = 2,
        center_tolerance: float = 0.01,
        include_torso: bool = False,
        include_spine_ik: bool = False,
        include_control_spaces: bool = False,
        torso_control_radius: float = 2.0,
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
        body_names = {joint.name for joint in arm.safety.body.joints}
        present_hand_names = body_names & expected_hand_names
        hand = None
        hand_schema_blockers = ()
        if present_hand_names == expected_hand_names:
            hand = self._hand.plan_from_safety(
                arm.safety,
                control_radius=hand_control_radius,
            )
        elif present_hand_names:
            missing = sorted(expected_hand_names - present_hand_names)
            hand_schema_blockers = (
                "Body 包含不完整的双侧五指集合，Hand FK 不会静默跳过；"
                f"缺少 {len(missing)} 个关节：" + "、".join(missing),
            )
        torso = (
            self._torso.plan_from_safety(safety, arm, leg, radius=torso_control_radius, spine_ik=include_spine_ik,description=axial_description,head_aim=include_head_aim)
            if include_torso else None
        )
        driven_roots = (
            torso.torso.controls.root_path if torso else arm.safety.body.root,
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
        )
        spaces = plan_body_control_spaces(safety.body, torso.torso, arm, leg, global_control) if include_control_spaces else None
        collisions = tuple(sorted({
            path
            for name in global_control.node_names + (spaces.node_names if spaces else ())
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
        leg_control_radius: float = 1.75,
        hand_control_radius: float = 0.3,
        global_control_radius: float = 12.0,
        pole_distance_scale: float = 0.75,
        twist_joints_per_segment: int = 2,
        center_tolerance: float = 0.01,
        include_torso: bool = False,
        include_spine_ik: bool = False,
        include_control_spaces: bool = False,
        torso_control_radius: float = 2.0,
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
            self._host.create_body_character_global(plan.global_control)
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
        )
