from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_arm_mechanisms import (
    BodyArmMechanismJointSpec,
    BodyArmMechanismPlan,
    BodyArmMechanismSnapshot,
    audit_body_arm_mechanisms,
    plan_body_arm_mechanisms,
)
from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.fit_settings import FitSkeletonValidationError

from .body_rebuild import (
    BodyRebuildInspectionHost,
    BodyRebuildSafetyAudit,
    InspectBodyRebuildSafety,
)


class BodyArmMechanismHost(BodyRebuildInspectionHost, Protocol):
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_body_arm_mechanism_root(self, name: str) -> str: ...

    def create_body_arm_mechanism_joint(
        self,
        spec: BodyArmMechanismJointSpec,
    ) -> str: ...

    def capture_body_arm_mechanisms(
        self,
        plan: BodyArmMechanismPlan,
    ) -> BodyArmMechanismSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyArmMechanismBuildPlan:
    safety: BodyRebuildSafetyAudit
    mechanisms: BodyArmMechanismPlan
    name_collisions: tuple[str, ...]

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers = [
            issue.message + (f"：{issue.subject}" if issue.subject else "")
            for issue in self.safety.issues
        ]
        if self.name_collisions:
            blockers.append(
                "场景中存在 Arm 机制链同名节点："
                + "、".join(self.name_collisions)
            )
        return tuple(blockers)

    @property
    def ready(self) -> bool:
        return self.safety.safe_to_replace and not self.name_collisions


@dataclass(frozen=True, slots=True)
class BodyArmMechanismBuildResult:
    plan: BodyArmMechanismBuildPlan
    snapshot: BodyArmMechanismSnapshot
    body: BodySkeletonSnapshot


class BuildBodyArmMechanisms:
    """Create bilateral FK and IK arm driver chains atomically."""

    def __init__(self, host: BodyArmMechanismHost) -> None:
        self._host = host
        self._inspector = InspectBodyRebuildSafety(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyArmMechanismBuildPlan:
        safety = self._inspector.execute(
            container_name,
            root_name=body_root_name,
            center_tolerance=center_tolerance,
        )
        mechanisms = plan_body_arm_mechanisms(safety.body)
        names = (mechanisms.root_name,) + tuple(
            spec.name for spec in mechanisms.joints
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
        return BodyArmMechanismBuildPlan(safety, mechanisms, collisions)

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyArmMechanismBuildResult:
        plan = self.plan(
            container_name,
            body_root_name=body_root_name,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Arm 机制链构建预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        with self._host.transaction("创建双臂 FK/IK 机制链"):
            root = self._host.create_body_arm_mechanism_root(
                plan.mechanisms.root_name
            )
            if root != plan.mechanisms.root_path:
                raise RuntimeError("Arm 机制链根路径发生漂移")
            for spec in plan.mechanisms.joints:
                if self._host.create_body_arm_mechanism_joint(spec) != spec.path:
                    raise RuntimeError(f"Arm 机制关节路径发生漂移：{spec.name}")
            snapshot = self._host.capture_body_arm_mechanisms(plan.mechanisms)
            issues = audit_body_arm_mechanisms(plan.mechanisms, snapshot)
            if issues:
                raise RuntimeError(
                    "Arm 机制链构建后复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            body = self._host.capture_body_skeleton(body_root_name)
            if body != plan.safety.body:
                raise RuntimeError("Arm 机制链构建后复检失败：Body 基准状态变化")
            container = plan.safety.symmetry.source.hierarchy.container
            if self._host.capture_fit_orientation(container) != plan.safety.symmetry.source:
                raise RuntimeError("Arm 机制链构建后复检失败：Fit joints 被改写")
            if self._host.read_fit_skeleton_settings(container) != plan.safety.symmetry.settings:
                raise RuntimeError("Arm 机制链构建后复检失败：容器设置被改写")
        return BodyArmMechanismBuildResult(plan, snapshot, body)
