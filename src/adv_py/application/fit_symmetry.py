from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_orientation import FitOrientationSnapshot
from adv_py.core.fit_settings import (
    FitSkeletonSettings,
    FitSkeletonValidationError,
    audit_fit_skeleton_settings,
)
from adv_py.core.fit_symmetry import FitSymmetryInstance, expand_fit_symmetry


class FitSymmetryHost(Protocol):
    def capture_fit_orientation(
        self, container_name: str
    ) -> FitOrientationSnapshot: ...

    def read_fit_skeleton_settings(
        self, container_name: str
    ) -> FitSkeletonSettings: ...


@dataclass(frozen=True, slots=True)
class FitSymmetryPlan:
    source: FitOrientationSnapshot
    settings: FitSkeletonSettings
    instances: tuple[FitSymmetryInstance, ...]


class PlanFitSymmetry:
    """Read a Maya Fit source and produce a host-independent build expansion."""

    def __init__(self, host: FitSymmetryHost) -> None:
        self._host = host

    def execute(
        self,
        container_name: str = "FitSkeleton",
        *,
        center_tolerance: float = 0.01,
    ) -> FitSymmetryPlan:
        source = self._host.capture_fit_orientation(container_name)
        settings = self._host.read_fit_skeleton_settings(
            source.hierarchy.container
        )
        setting_issues = audit_fit_skeleton_settings(settings, require_complete=True)
        if setting_issues:
            raise FitSkeletonValidationError(
                "FitSkeleton 镜像分析前设置无效："
                + "；".join(issue.message for issue in setting_issues)
            )
        instances = expand_fit_symmetry(
            source.hierarchy,
            source.metadata,
            center_tolerance=center_tolerance,
            world_axes_by_joint={
                state.joint: state.world_axes for state in source.joints
            },
        )
        return FitSymmetryPlan(source, settings, instances)
