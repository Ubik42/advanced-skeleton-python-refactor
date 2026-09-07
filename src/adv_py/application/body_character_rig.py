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
from .body_rebuild import InspectBodyRebuildSafety
from .body_rig_validation import body_bind_pose_matches


class BodyCharacterRigHost(BodyArmRigHost, BodyLegRigHost, Protocol):
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
    global_control: BodyCharacterGlobalPlan
    global_name_collisions: tuple[str, ...]
    shared_input_stable: bool

    @property
    def ready(self) -> bool:
        return (
            self.arm.ready
            and self.leg.ready
            and not self.global_name_collisions
            and self.shared_input_stable
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        values = list(self.arm.blockers)
        values.extend(
            blocker for blocker in self.leg.blockers if blocker not in values
        )
        if self.global_name_collisions:
            values.append(
                "场景中存在角色总控同名节点："
                + "、".join(self.global_name_collisions)
            )
        if not self.shared_input_stable:
            values.append("Arm/Leg 预演之间 Body 或 Fit 输入发生变化")
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyCharacterRigBuildResult:
    plan: BodyCharacterRigBuildPlan
    arm: BodyArmRigBuildResult
    leg: BodyLegRigBuildResult
    global_control: BodyCharacterGlobalSnapshot
    body: BodySkeletonSnapshot


class BuildBodyCharacterRig:
    """Build the Maya-first Arm, Leg, and character global rig atomically."""

    def __init__(self, host: BodyCharacterRigHost) -> None:
        self._host = host
        self._arm = BuildBodyArmRig(host)
        self._leg = BuildBodyLegRig(host)
        self._inspector = InspectBodyRebuildSafety(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        arm_control_radius: float = 1.5,
        leg_control_radius: float = 1.75,
        global_control_radius: float = 12.0,
        pole_distance_scale: float = 0.75,
        twist_joints_per_segment: int = 2,
        center_tolerance: float = 0.01,
    ) -> BodyCharacterRigBuildPlan:
        arm = self._arm.plan(
            container_name,
            body_root_name=body_root_name,
            control_radius=arm_control_radius,
            pole_distance_scale=pole_distance_scale,
            twist_joints_per_segment=twist_joints_per_segment,
            center_tolerance=center_tolerance,
        )
        leg = self._leg.plan(
            container_name,
            body_root_name=body_root_name,
            control_radius=leg_control_radius,
            pole_distance_scale=pole_distance_scale,
            twist_joints_per_segment=twist_joints_per_segment,
            center_tolerance=center_tolerance,
        )
        driven_roots = (
            arm.safety.body.root,
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
            ),
            radius=global_control_radius,
        )
        collisions = tuple(sorted({
            path
            for name in global_control.node_names
            for path in self._host.find_name_collisions(name)
        }))
        return BodyCharacterRigBuildPlan(
            arm=arm,
            leg=leg,
            global_control=global_control,
            global_name_collisions=collisions,
            shared_input_stable=arm.safety == leg.safety,
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        arm_control_radius: float = 1.5,
        leg_control_radius: float = 1.75,
        global_control_radius: float = 12.0,
        pole_distance_scale: float = 0.75,
        twist_joints_per_segment: int = 2,
        center_tolerance: float = 0.01,
    ) -> BodyCharacterRigBuildResult:
        plan = self.plan(
            container_name,
            body_root_name=body_root_name,
            arm_control_radius=arm_control_radius,
            leg_control_radius=leg_control_radius,
            global_control_radius=global_control_radius,
            pole_distance_scale=pole_distance_scale,
            twist_joints_per_segment=twist_joints_per_segment,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Character Rig 构建预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        self._host.prepare_body_arm_twist_runtime()
        self._host.prepare_body_leg_twist_runtime()
        with self._host.transaction("构建完整角色 Arm/Leg 与总控"):
            current = self._inspector.execute(
                container_name,
                root_name=body_root_name,
                center_tolerance=center_tolerance,
            )
            if current != plan.arm.safety:
                raise RuntimeError(
                    "Character Rig 执行前 Body 或 Fit 输入发生变化"
                )
            arm = self._arm._apply_plan(
                plan.arm,
                body_root_name=body_root_name,
                manage_transaction=False,
                prepare_runtime=False,
            )
            leg = self._leg._apply_plan(
                plan.leg,
                body_root_name=body_root_name,
                manage_transaction=False,
                prepare_runtime=False,
            )
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
            plan,
            arm,
            leg,
            global_control,
            body,
        )
