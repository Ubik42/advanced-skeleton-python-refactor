from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_controls import (
    BodyArmFkControlPlan,
    BodyArmFkControlSnapshot,
    BodyArmFkControlSpec,
    audit_body_arm_fk_controls,
    plan_body_arm_fk_controls,
)
from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.fit_settings import FitSkeletonValidationError

from .body_rebuild import (
    BodyRebuildInspectionHost,
    BodyRebuildSafetyAudit,
    InspectBodyRebuildSafety,
)


class BodyArmFkHost(BodyRebuildInspectionHost, Protocol):
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_body_control_root(self, name: str) -> str: ...

    def create_body_arm_fk_control(self, spec: BodyArmFkControlSpec) -> None: ...

    def capture_body_arm_fk_controls(
        self,
        plan: BodyArmFkControlPlan,
    ) -> BodyArmFkControlSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyArmFkBuildPlan:
    safety: BodyRebuildSafetyAudit
    controls: BodyArmFkControlPlan
    name_collisions: tuple[str, ...]

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers = [
            issue.message
            + (f"：{issue.subject}" if issue.subject is not None else "")
            for issue in self.safety.issues
        ]
        if self.name_collisions:
            blockers.append(
                "场景中存在 Arm FK 同名节点："
                + "、".join(self.name_collisions)
            )
        return tuple(blockers)

    @property
    def ready(self) -> bool:
        return self.safety.safe_to_replace and not self.name_collisions


@dataclass(frozen=True, slots=True)
class BodyArmFkBuildResult:
    plan: BodyArmFkBuildPlan
    snapshot: BodyArmFkControlSnapshot
    body: BodySkeletonSnapshot


class BuildBodyArmFkControls:
    """Create bilateral Shoulder/Elbow/Wrist FK controls atomically."""

    def __init__(self, host: BodyArmFkHost) -> None:
        self._host = host
        self._inspector = InspectBodyRebuildSafety(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        control_radius: float = 1.5,
        center_tolerance: float = 0.01,
    ) -> BodyArmFkBuildPlan:
        safety = self._inspector.execute(
            container_name,
            root_name=body_root_name,
            center_tolerance=center_tolerance,
        )
        controls = plan_body_arm_fk_controls(
            safety.body,
            radius=control_radius,
        )
        names = [controls.root_name]
        for spec in controls.controls:
            names.extend(
                (spec.offset_name, spec.control_name, spec.constraint_name)
            )
        collisions = tuple(
            sorted(
                {
                    path
                    for name in names
                    for path in self._host.find_name_collisions(name)
                }
            )
        )
        return BodyArmFkBuildPlan(safety, controls, collisions)

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        control_radius: float = 1.5,
        center_tolerance: float = 0.01,
    ) -> BodyArmFkBuildResult:
        plan = self.plan(
            container_name,
            body_root_name=body_root_name,
            control_radius=control_radius,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Arm FK 控制构建预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        with self._host.transaction("创建双臂 FK 控制"):
            root = self._host.create_body_control_root(
                plan.controls.root_name
            )
            if root != plan.controls.root_path:
                raise RuntimeError("Arm FK 控制根路径发生漂移")
            for spec in plan.controls.controls:
                self._host.create_body_arm_fk_control(spec)
            snapshot = self._host.capture_body_arm_fk_controls(plan.controls)
            issues = audit_body_arm_fk_controls(plan.controls, snapshot)
            if issues:
                raise RuntimeError(
                    "Arm FK 控制构建后复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            body = self._host.capture_body_skeleton(body_root_name)
            if body != plan.safety.body:
                raise RuntimeError("Arm FK 控制构建后复检失败：Body 基准状态变化")
            current_fit = self._host.capture_fit_orientation(
                plan.safety.symmetry.source.hierarchy.container
            )
            current_settings = self._host.read_fit_skeleton_settings(
                plan.safety.symmetry.source.hierarchy.container
            )
            if current_fit != plan.safety.symmetry.source:
                raise RuntimeError("Arm FK 控制构建后复检失败：Fit joints 被改写")
            if current_settings != plan.safety.symmetry.settings:
                raise RuntimeError("Arm FK 控制构建后复检失败：容器设置被改写")
        return BodyArmFkBuildResult(plan, snapshot, body)
