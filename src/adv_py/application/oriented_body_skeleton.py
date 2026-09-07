from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_skeleton import (
    BodyJointOrientationChange,
    BodySkeletonProvenance,
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
    plan_body_joint_orientations,
)
from adv_py.core.fit_settings import FitSkeletonValidationError

from .body_orientation import (
    BodyOrientationHost,
    BodyOrientationPlan,
    _apply_body_orientation,
    _verify_body_orientation,
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

    def write_body_provenance(
        self,
        root: str,
        provenance: BodySkeletonProvenance,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class OrientedBodySkeletonBuildPlan:
    build: BodySkeletonBuildPlan
    provenance: BodySkeletonProvenance

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
        build = self._builder.plan(
            container_name,
            center_tolerance=center_tolerance,
        )
        return OrientedBodySkeletonBuildPlan(
            build,
            oriented_body_provenance(
                build.symmetry.source.hierarchy.container,
                len(build.symmetry.instances),
            ),
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
        with self._host.transaction(
            f"创建并朝向 {len(build.specs)} 个 Body skeleton joints"
        ):
            result = _build_oriented_body_skeleton_in_transaction(
                self._host,
                plan,
            )
        return result


def _build_oriented_body_skeleton_in_transaction(
    host: OrientedBodySkeletonHost,
    plan: OrientedBodySkeletonBuildPlan,
) -> OrientedBodySkeletonBuildResult:
    """Build, orient, mark and verify Body inside an active transaction."""

    build = plan.build
    root_name = build.specs[0].name
    neutral = _materialize_body_skeleton(host, build, root_name)
    changes = plan_body_joint_orientations(
        build.symmetry.instances,
        neutral,
    )
    orientation = BodyOrientationPlan(
        build.symmetry,
        neutral,
        changes,
    )
    _apply_body_orientation(host, orientation, root_name)
    host.write_body_provenance(neutral.root, plan.provenance)
    snapshot = host.capture_body_skeleton(root_name)
    _verify_body_orientation(orientation, snapshot)
    provenance_issues = audit_body_provenance(
        plan.provenance,
        snapshot.provenance,
    )
    if provenance_issues:
        raise RuntimeError(
            "Body skeleton 原子构建后复检失败："
            + "；".join(issue.message for issue in provenance_issues)
        )
    current_fit = host.capture_fit_orientation(
        build.symmetry.source.hierarchy.container
    )
    current_settings = host.read_fit_skeleton_settings(
        build.symmetry.source.hierarchy.container
    )
    if current_fit != build.symmetry.source:
        raise RuntimeError("Body skeleton 原子构建后复检失败：Fit joints 被改写")
    if current_settings != build.symmetry.settings:
        raise RuntimeError("Body skeleton 原子构建后复检失败：容器设置被改写")
    return OrientedBodySkeletonBuildResult(
        plan,
        neutral,
        changes,
        snapshot,
    )
