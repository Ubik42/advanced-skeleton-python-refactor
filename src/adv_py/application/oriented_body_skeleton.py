from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_skeleton import (
    BodyJointOrientationChange,
    BodySkeletonSnapshot,
    plan_body_joint_orientations,
)
from adv_py.core.fit_settings import FitSkeletonValidationError

from .body_orientation import (
    BodyOrientationHost,
    BodyOrientationPlan,
    _apply_body_orientation,
)
from .body_skeleton import (
    BodySkeletonBuildPlan,
    BodySkeletonHost,
    BuildBodySkeleton,
    _materialize_body_skeleton,
)


class OrientedBodySkeletonHost(
    BodySkeletonHost,
    BodyOrientationHost,
    Protocol,
):
    """Combined host contract for the atomic Body build path."""


@dataclass(frozen=True, slots=True)
class OrientedBodySkeletonBuildPlan:
    build: BodySkeletonBuildPlan

    @property
    def ready(self) -> bool:
        return self.build.ready

    @property
    def blockers(self) -> tuple[str, ...]:
        return self.build.blockers


@dataclass(frozen=True, slots=True)
class OrientedBodySkeletonBuildResult:
    plan: OrientedBodySkeletonBuildPlan
    neutral: BodySkeletonSnapshot
    orientation_changes: tuple[BodyJointOrientationChange, ...]
    snapshot: BodySkeletonSnapshot


class BuildOrientedBodySkeleton:
    """Create and orient the complete Body skeleton in one transaction."""

    def __init__(self, host: OrientedBodySkeletonHost) -> None:
        self._host = host
        self._builder = BuildBodySkeleton(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        center_tolerance: float = 0.01,
    ) -> OrientedBodySkeletonBuildPlan:
        return OrientedBodySkeletonBuildPlan(
            self._builder.plan(
                container_name,
                center_tolerance=center_tolerance,
            )
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        center_tolerance: float = 0.01,
    ) -> OrientedBodySkeletonBuildResult:
        plan = self.plan(
            container_name,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Body skeleton 原子构建预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        build = plan.build
        root_name = build.specs[0].name
        with self._host.transaction(
            f"创建并朝向 {len(build.specs)} 个 Body skeleton joints"
        ):
            neutral = _materialize_body_skeleton(
                self._host,
                build,
                root_name,
            )
            changes = plan_body_joint_orientations(
                build.symmetry.instances,
                neutral,
            )
            orientation = BodyOrientationPlan(
                build.symmetry,
                neutral,
                changes,
            )
            snapshot = _apply_body_orientation(
                self._host,
                orientation,
                root_name,
            )
            current_fit = self._host.capture_fit_orientation(
                build.symmetry.source.hierarchy.container
            )
            current_settings = self._host.read_fit_skeleton_settings(
                build.symmetry.source.hierarchy.container
            )
            if current_fit != build.symmetry.source:
                raise RuntimeError(
                    "Body skeleton 原子构建后复检失败：Fit joints 被改写"
                )
            if current_settings != build.symmetry.settings:
                raise RuntimeError(
                    "Body skeleton 原子构建后复检失败：容器设置被改写"
                )
        return OrientedBodySkeletonBuildResult(
            plan,
            neutral,
            changes,
            snapshot,
        )
