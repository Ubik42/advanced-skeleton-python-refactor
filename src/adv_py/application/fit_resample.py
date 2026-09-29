"""Resample a Fit joint chain as one reversible Maya operation."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_hierarchy import FitHierarchySnapshot
from adv_py.core.fit_orientation import FitOrientationRequest
from adv_py.core.fit_resample import FitResamplePlan, plan_fit_resample

from .fit_orientation import OrientSimpleFitChain


class FitResampleHost(Protocol):
    def capture_fit_hierarchy(self, container: str) -> FitHierarchySnapshot: ...
    def preflight_fit_resample(self, plan: FitResamplePlan) -> None: ...
    def resample_fit_chain(self, plan: FitResamplePlan) -> tuple[str, ...]: ...
    def finalize_fit_resample(self, plan: FitResamplePlan,
                              created: tuple[str, ...]) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class FitResampleResult:
    plan: FitResamplePlan
    created: tuple[str, ...]
    verified: FitHierarchySnapshot


class ResampleFitChain:
    def __init__(self, host: FitResampleHost) -> None:
        self._host = host

    def plan(self, start: str, end: str, joint_count: int,
             container: str = "FitSkeleton") -> FitResamplePlan:
        source = self._host.capture_fit_hierarchy(container)
        planned = plan_fit_resample(source, start, end, joint_count)
        self._host.preflight_fit_resample(planned)
        return planned

    def apply(self, start: str, end: str, joint_count: int,
              container: str = "FitSkeleton") -> FitResampleResult:
        plan = self.plan(start, end, joint_count, container)
        with self._host.transaction("重采样 Fit 关节链"):
            if plan != plan_fit_resample(
                    self._host.capture_fit_hierarchy(container),
                    start, end, joint_count):
                raise ValueError("Fit 重采样前层级已变化")
            self._host.preflight_fit_resample(plan)
            created = self._host.resample_fit_chain(plan)
            if created:
                orient = OrientSimpleFitChain(self._host)
                orientation = orient.plan(FitOrientationRequest(created),
                                          container)
                orient.apply_plan_in_transaction(orientation)
            self._host.finalize_fit_resample(plan, created)
            verified = self._host.capture_fit_hierarchy(container)
            paths = {node.path: node for node in verified.joints}
            end_name = plan.end.rsplit("|", 1)[-1]
            end_path = (created[-1] if created else plan.start) + "|" + end_name
            if (len(created) != joint_count - 2
                    or tuple(path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                             for path in created) != plan.new_names
                    or any(path not in paths for path in created)
                    or any(paths[path].dag_parent != parent
                           for path, parent in zip(
                               created, (plan.start, *created[:-1])))
                    or end_path not in paths
                    or paths[end_path].dag_parent != (created[-1]
                                                      if created else plan.start)):
                raise RuntimeError("Fit 关节重采样结果与计划不一致")
            return FitResampleResult(plan, created, verified)
