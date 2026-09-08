from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_hand_controls import (
    BodyHandControlIssue,
    BodyHandFkControlPlan,
    BodyHandFkControlSnapshot,
    BodyHandFkControlSpec,
    BodyHandFkInputSnapshot,
    BodyHandFkRootSpec,
    BodyHandPosePlan,
    BodyHandPoseSnapshot,
    audit_body_hand_fk_controls,
    audit_body_hand_fk_input,
    audit_body_hand_pose_controls,
    plan_body_hand_fk_controls,
    plan_body_hand_pose_controls,
)
from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.fit_settings import FitSkeletonValidationError

from .body_rebuild import (
    BodyRebuildInspectionHost,
    BodyRebuildSafetyAudit,
    InspectBodyRebuildSafety,
)
from .body_rig_validation import body_bind_pose_matches


class BodyHandFkHost(BodyRebuildInspectionHost, Protocol):
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def capture_body_hand_fk_input(
        self,
        plan: BodyHandFkControlPlan,
    ) -> BodyHandFkInputSnapshot: ...
    def create_body_hand_fk_root(self, spec: BodyHandFkRootSpec) -> str: ...
    def create_body_hand_fk_control(self, spec: BodyHandFkControlSpec) -> None: ...
    def capture_body_hand_fk_controls(
        self,
        plan: BodyHandFkControlPlan,
    ) -> BodyHandFkControlSnapshot: ...
    def create_body_hand_pose(self, plan: BodyHandPosePlan) -> None: ...
    def capture_body_hand_pose(
        self,
        plan: BodyHandPosePlan,
    ) -> BodyHandPoseSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyHandFkBuildPlan:
    safety: BodyRebuildSafetyAudit
    controls: BodyHandFkControlPlan
    pose: BodyHandPosePlan
    input_snapshot: BodyHandFkInputSnapshot
    input_issues: tuple[BodyHandControlIssue, ...]
    name_collisions: tuple[str, ...]

    @property
    def blockers(self) -> tuple[str, ...]:
        values = [
            issue.message
            + (f"：{issue.subject}" if issue.subject is not None else "")
            for issue in self.safety.issues + self.input_issues
        ]
        if self.name_collisions:
            values.append(
                "场景中存在 Hand FK 同名节点："
                + "、".join(self.name_collisions)
            )
        return tuple(values)

    @property
    def ready(self) -> bool:
        return (
            self.safety.safe_to_replace
            and not self.input_issues
            and not self.name_collisions
        )


@dataclass(frozen=True, slots=True)
class BodyHandFkBuildResult:
    plan: BodyHandFkBuildPlan
    snapshot: BodyHandFkControlSnapshot
    pose: BodyHandPoseSnapshot
    body: BodySkeletonSnapshot


class BuildBodyHandFkControls:
    """Create bilateral hierarchical five-digit FK controls atomically."""

    def __init__(self, host: BodyHandFkHost) -> None:
        self._host = host
        self._inspector = InspectBodyRebuildSafety(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        control_radius: float = 0.3,
        center_tolerance: float = 0.01,
    ) -> BodyHandFkBuildPlan:
        safety = self._inspector.execute(
            container_name,
            root_name=body_root_name,
            center_tolerance=center_tolerance,
        )
        return self.plan_from_safety(safety, control_radius=control_radius)

    def plan_from_safety(
        self,
        safety: BodyRebuildSafetyAudit,
        *,
        control_radius: float = 0.3,
    ) -> BodyHandFkBuildPlan:
        """Plan Hand FK from an already captured shared Character input."""

        controls = plan_body_hand_fk_controls(
            safety.body,
            radius=control_radius,
        )
        pose = plan_body_hand_pose_controls(controls)
        input_snapshot = self._host.capture_body_hand_fk_input(controls)
        input_issues = audit_body_hand_fk_input(controls, input_snapshot)
        collisions = tuple(sorted({
            path
            for name in controls.node_names + pose.node_names
            for path in self._host.find_name_collisions(name)
        }))
        return BodyHandFkBuildPlan(
            safety,
            controls,
            pose,
            input_snapshot,
            input_issues,
            collisions,
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        control_radius: float = 0.3,
        center_tolerance: float = 0.01,
    ) -> BodyHandFkBuildResult:
        plan = self.plan(
            container_name,
            body_root_name=body_root_name,
            control_radius=control_radius,
            center_tolerance=center_tolerance,
        )
        return self._apply_plan(
            plan,
            body_root_name=body_root_name,
            container_name=container_name,
            center_tolerance=center_tolerance,
        )

    def _apply_plan(
        self,
        plan: BodyHandFkBuildPlan,
        *,
        body_root_name: str,
        container_name: str = "FitSkeleton",
        center_tolerance: float = 0.01,
        manage_transaction: bool = True,
        revalidate_safety: bool = True,
    ) -> BodyHandFkBuildResult:
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Hand FK 控制构建预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        transaction = (
            self._host.transaction("创建双手五指分层 FK 控制")
            if manage_transaction
            else nullcontext()
        )
        with transaction:
            current_safety = (
                self._inspector.execute(
                    container_name,
                    root_name=body_root_name,
                    center_tolerance=center_tolerance,
                )
                if revalidate_safety
                else plan.safety
            )
            current_input = self._host.capture_body_hand_fk_input(
                plan.controls
            )
            if (
                current_safety != plan.safety
                or current_input != plan.input_snapshot
                or audit_body_hand_fk_input(plan.controls, current_input)
            ):
                raise RuntimeError(
                    "Hand FK 控制执行前 Body、Fit 或目标通道发生变化"
                )
            for spec in plan.controls.roots:
                if self._host.create_body_hand_fk_root(spec) != spec.path:
                    raise RuntimeError("Hand FK 根节点路径漂移")
            for spec in plan.controls.controls:
                self._host.create_body_hand_fk_control(spec)
            self._host.create_body_hand_pose(plan.pose)
            snapshot = self._host.capture_body_hand_fk_controls(plan.controls)
            issues = audit_body_hand_fk_controls(plan.controls, snapshot)
            if issues:
                raise RuntimeError(
                    "Hand FK 控制构建后复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            pose = self._host.capture_body_hand_pose(plan.pose)
            pose_issues = audit_body_hand_pose_controls(plan.pose, pose)
            if pose_issues:
                raise RuntimeError(
                    "Hand 聚合姿态构建后复检失败："
                    + "；".join(issue.message for issue in pose_issues)
                )
            body = self._host.capture_body_skeleton(body_root_name)
            if not body_bind_pose_matches(plan.safety.body, body):
                raise RuntimeError("Hand FK 控制中性状态改变了 Body 绑定姿态")
            source = plan.safety.symmetry.source
            if (
                self._host.capture_fit_orientation(source.hierarchy.container)
                != source
                or self._host.read_fit_skeleton_settings(
                    source.hierarchy.container
                )
                != plan.safety.symmetry.settings
            ):
                raise RuntimeError("Hand FK 控制构建后 Fit 输入变化")
        return BodyHandFkBuildResult(plan, snapshot, pose, body)
