from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from adv_py.core.fit_orientation import FitOrientationSnapshot
from adv_py.core.fit_hierarchy import fit_build_scale
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


def anchor_fit_symmetry(plan: FitSymmetryPlan, parent_path: str | None
                        ) -> FitSymmetryPlan:
    """Place the generated Body tree under an existing transform path."""
    if parent_path is None:
        return plan
    if (not isinstance(parent_path, str) or not parent_path.startswith("|")
            or any(not part for part in parent_path[1:].split("|"))):
        raise FitSkeletonValidationError("Body 根父级必须是完整 DAG 路径")
    roots = [item for item in plan.instances if item.parent_output_path is None]
    if len(roots) != 1 or not roots[0].output_path.startswith("|"):
        raise FitSkeletonValidationError("Fit 镜像展开必须恰有一个 Body 根关节")
    return replace(plan, instances=tuple(replace(
        item,
        output_path=parent_path + item.output_path,
        parent_output_path=(parent_path + item.parent_output_path
                            if item.parent_output_path else parent_path),
    ) for item in plan.instances))


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
        setting_issues = audit_fit_skeleton_settings(settings, require_complete=False)
        if setting_issues:
            raise FitSkeletonValidationError(
                "FitSkeleton 镜像分析前设置无效："
                + "；".join(issue.message for issue in setting_issues)
            )
        instances = expand_fit_symmetry(
            source.hierarchy,
            source.metadata,
            center_tolerance=center_tolerance * fit_build_scale(source.hierarchy),
            world_axes_by_joint={
                state.joint: state.world_axes for state in source.joints
            },
        )
        return FitSymmetryPlan(source, settings, instances)
