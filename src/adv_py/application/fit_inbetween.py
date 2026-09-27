"""Prepare the temporary Fit guides required by Inbetween Body builds."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_inbetween import (
    FitInbetweenGuide, FitInbetweenGuideState, FitInbetweenPlan,
    FitInbetweenReparent, audit_fit_inbetween, plan_fit_inbetween,
)
from adv_py.core.fit_orientation import FitOrientationSnapshot


class FitInbetweenHost(Protocol):
    def capture_fit_orientation(
        self, container_name: str
    ) -> FitOrientationSnapshot: ...

    def read_fit_deform_profile(self, joint: str) -> FitDeformProfile: ...

    def read_fit_rotation_order(self, joint: str) -> int: ...

    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def preflight_fit_inbetween(self, plan: FitInbetweenPlan) -> None: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_fit_inbetween_guide(self, guide: FitInbetweenGuide) -> None: ...

    def reparent_fit_inbetween_child(
        self, step: FitInbetweenReparent
    ) -> None: ...

    def capture_fit_inbetween_guides(
        self, names: tuple[str, ...]
    ) -> tuple[FitInbetweenGuideState, ...]: ...

    def restore_fit_inbetween(
        self, plan: FitInbetweenPlan, original: FitOrientationSnapshot
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class FitInbetweenPreparation:
    original: FitOrientationSnapshot
    plan: FitInbetweenPlan
    guides: tuple[FitInbetweenGuideState, ...]


class PrepareFitInbetween:
    def __init__(self, host: FitInbetweenHost) -> None:
        self._host = host

    def plan(self, container_name: str = "FitSkeleton",
             *, center_tolerance: float = 0.01
             ) -> tuple[FitOrientationSnapshot, FitInbetweenPlan]:
        source = self._host.capture_fit_orientation(container_name)
        paths = tuple(node.path for node in source.hierarchy.joints)
        profiles = {path: self._host.read_fit_deform_profile(path)
                    for path in paths}
        orders = {path: self._host.read_fit_rotation_order(path)
                  for path in paths}
        plan = plan_fit_inbetween(
            source.hierarchy, source.metadata, profiles, orders,
            center_tolerance=center_tolerance)
        for guide in plan.guides:
            if self._host.find_name_collisions(guide.name):
                raise ValueError("Inbetween 临时导向名称已占用：" + guide.name)
        self._host.preflight_fit_inbetween(plan)
        return source, plan

    def apply(self, original: FitOrientationSnapshot,
              plan: FitInbetweenPlan) -> FitInbetweenPreparation:
        if self._host.capture_fit_orientation(
                original.hierarchy.container) != original:
            raise ValueError("Inbetween 构建前 Fit 来源已变化")
        for guide in plan.guides:
            if self._host.find_name_collisions(guide.name):
                raise ValueError("Inbetween 临时导向名称已占用：" + guide.name)
        self._host.preflight_fit_inbetween(plan)
        with self._host.transaction("创建临时 Inbetween Fit 导向"):
            for guide in plan.guides:
                self._host.create_fit_inbetween_guide(guide)
            for step in plan.reparents:
                self._host.reparent_fit_inbetween_child(step)
            guides = self._host.capture_fit_inbetween_guides(
                tuple(guide.name for guide in plan.guides))
            issues = audit_fit_inbetween(plan, guides)
            if issues:
                raise RuntimeError("Inbetween 导向写后复检失败："
                                   + "；".join(issues))
        return FitInbetweenPreparation(original, plan, guides)

    def restore(self, preparation: FitInbetweenPreparation) -> None:
        with self._host.transaction("移除临时 Inbetween Fit 导向"):
            self._host.restore_fit_inbetween(
                preparation.plan, preparation.original)
            if self._host.capture_fit_orientation(
                    preparation.original.hierarchy.container
                    ) != preparation.original:
                raise RuntimeError("Inbetween 临时导向移除后 Fit 未恢复")
