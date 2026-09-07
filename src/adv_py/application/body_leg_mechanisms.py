from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_leg_mechanisms import (
    BodyLegMechanismJointSpec,
    BodyLegMechanismPlan,
    BodyLegMechanismSnapshot,
    audit_body_leg_mechanisms,
    plan_body_leg_mechanisms,
)
from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.fit_settings import FitSkeletonValidationError

from .body_rebuild import (
    BodyRebuildInspectionHost,
    BodyRebuildSafetyAudit,
    InspectBodyRebuildSafety,
)


class BodyLegMechanismHost(BodyRebuildInspectionHost, Protocol):
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_body_leg_mechanism_root(self, name: str) -> str: ...
    def create_body_leg_mechanism_joint(self, spec: BodyLegMechanismJointSpec) -> str: ...
    def capture_body_leg_mechanisms(self, plan: BodyLegMechanismPlan) -> BodyLegMechanismSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyLegMechanismBuildPlan:
    safety: BodyRebuildSafetyAudit
    mechanisms: BodyLegMechanismPlan
    name_collisions: tuple[str, ...]

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers = [
            issue.message + (f"：{issue.subject}" if issue.subject else "")
            for issue in self.safety.issues
        ]
        if self.name_collisions:
            blockers.append("场景中存在 Leg 机制链同名节点：" + "、".join(self.name_collisions))
        return tuple(blockers)

    @property
    def ready(self) -> bool:
        return self.safety.safe_to_replace and not self.name_collisions


@dataclass(frozen=True, slots=True)
class BodyLegMechanismBuildResult:
    plan: BodyLegMechanismBuildPlan
    snapshot: BodyLegMechanismSnapshot
    body: BodySkeletonSnapshot


class BuildBodyLegMechanisms:
    """Create bilateral FK and IK leg driver chains atomically."""

    def __init__(self, host: BodyLegMechanismHost) -> None:
        self._host = host
        self._inspector = InspectBodyRebuildSafety(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyLegMechanismBuildPlan:
        safety = self._inspector.execute(
            container_name,
            root_name=body_root_name,
            center_tolerance=center_tolerance,
        )
        mechanisms = plan_body_leg_mechanisms(safety.body)
        names = (mechanisms.root_name,) + tuple(spec.name for spec in mechanisms.joints)
        collisions = tuple(sorted({
            path
            for name in names
            for path in self._host.find_name_collisions(name)
        }))
        return BodyLegMechanismBuildPlan(safety, mechanisms, collisions)

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyLegMechanismBuildResult:
        plan = self.plan(
            container_name,
            body_root_name=body_root_name,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Leg 机制链构建预检失败，场景未修改：" + "；".join(plan.blockers)
            )
        with self._host.transaction("创建双腿 FK/IK 机制链"):
            root = self._host.create_body_leg_mechanism_root(plan.mechanisms.root_name)
            if root != plan.mechanisms.root_path:
                raise RuntimeError("Leg 机制链根路径发生漂移")
            for spec in plan.mechanisms.joints:
                if self._host.create_body_leg_mechanism_joint(spec) != spec.path:
                    raise RuntimeError(f"Leg 机制关节路径发生漂移：{spec.name}")
            snapshot = self._host.capture_body_leg_mechanisms(plan.mechanisms)
            issues = audit_body_leg_mechanisms(plan.mechanisms, snapshot)
            if issues:
                raise RuntimeError(
                    "Leg 机制链构建后复检失败：" + "；".join(issue.message for issue in issues)
                )
            body = self._host.capture_body_skeleton(body_root_name)
            if body != plan.safety.body:
                raise RuntimeError("Leg 机制链构建后复检失败：Body 基准状态变化")
            container = plan.safety.symmetry.source.hierarchy.container
            if self._host.capture_fit_orientation(container) != plan.safety.symmetry.source:
                raise RuntimeError("Leg 机制链构建后复检失败：Fit joints 被改写")
            if self._host.read_fit_skeleton_settings(container) != plan.safety.symmetry.settings:
                raise RuntimeError("Leg 机制链构建后复检失败：容器设置被改写")
        return BodyLegMechanismBuildResult(plan, snapshot, body)
