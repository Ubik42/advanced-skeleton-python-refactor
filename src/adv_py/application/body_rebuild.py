from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from typing import Protocol

from adv_py.core.body_rebuild import (
    BodyRebuildIssue,
    BodyRebuildSceneState,
    audit_body_rebuild_safety,
)
from adv_py.core.body_skeleton import BodySkeletonSnapshot, oriented_body_provenance
from adv_py.core.fit_settings import FitSkeletonValidationError

from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry
from .oriented_body_skeleton import (
    BuildOrientedBodySkeleton,
    OrientedBodySkeletonBuildPlan,
    OrientedBodySkeletonBuildResult,
    OrientedBodySkeletonHost,
    _build_oriented_body_skeleton_in_transaction,
)


class BodyRebuildInspectionHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...

    def capture_body_rebuild_state(
        self,
        root_name: str,
    ) -> BodyRebuildSceneState: ...


@dataclass(frozen=True, slots=True)
class BodyRebuildSafetyAudit:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    scene: BodyRebuildSceneState
    issues: tuple[BodyRebuildIssue, ...]

    @property
    def safe_to_replace(self) -> bool:
        return not self.issues


class InspectBodyRebuildSafety:
    """Read the complete known replacement boundary without mutating Maya."""

    def __init__(self, host: BodyRebuildInspectionHost) -> None:
        self._host = host
        self._symmetry = PlanFitSymmetry(host)

    def execute(
        self,
        container_name: str = "FitSkeleton",
        *,
        root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyRebuildSafetyAudit:
        symmetry = self._symmetry.execute(
            container_name,
            center_tolerance=center_tolerance,
        )
        body = self._host.capture_body_skeleton(root_name)
        scene = self._host.capture_body_rebuild_state(root_name)
        provenance = oriented_body_provenance(
            symmetry.source.hierarchy.container,
            len(symmetry.instances),
        )
        return BodyRebuildSafetyAudit(
            symmetry,
            body,
            scene,
            audit_body_rebuild_safety(
                symmetry.instances,
                body,
                scene,
                provenance,
            ),
        )


class BodyReplacementHost(
    BodyRebuildInspectionHost,
    OrientedBodySkeletonHost,
    Protocol,
):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def delete_owned_body(self, root: str) -> None: ...


@dataclass(frozen=True, slots=True)
class BodyReplacementPlan:
    safety: BodyRebuildSafetyAudit
    build: OrientedBodySkeletonBuildPlan
    owned_name_collisions: tuple[str, ...]
    source_stable: bool

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers = [
            issue.message
            + (f"：{issue.subject}" if issue.subject is not None else "")
            for issue in self.safety.issues
        ]
        blockers.extend(self.build.blockers)
        if not self.source_stable:
            blockers.append("两次预检之间 Fit 输入或设置发生变化")
        return tuple(blockers)

    @property
    def ready(self) -> bool:
        return (
            self.safety.safe_to_replace
            and self.build.ready
            and self.source_stable
        )


@dataclass(frozen=True, slots=True)
class BodyReplacementResult:
    plan: BodyReplacementPlan
    previous: BodySkeletonSnapshot
    build: OrientedBodySkeletonBuildResult
    scene: BodyRebuildSceneState


class ReplaceOwnedBodySkeleton:
    """Replace one verified Python Body tree in a single transaction."""

    def __init__(self, host: BodyReplacementHost) -> None:
        self._host = host
        self._inspector = InspectBodyRebuildSafety(host)
        self._builder = BuildOrientedBodySkeleton(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyReplacementPlan:
        safety = self._inspector.execute(
            container_name,
            root_name=root_name,
            center_tolerance=center_tolerance,
        )
        raw_build = self._builder.plan(
            container_name,
            center_tolerance=center_tolerance,
        )
        owned_paths = {state.path for state in safety.body.joints}
        owned_collisions = tuple(
            sorted(
                set(raw_build.build.name_collisions) & owned_paths
            )
        )
        foreign_collisions = tuple(
            sorted(
                set(raw_build.build.name_collisions) - owned_paths
            )
        )
        prepared_build = replace(
            raw_build,
            build=replace(
                raw_build.build,
                name_collisions=foreign_collisions,
            ),
        )
        return BodyReplacementPlan(
            safety,
            prepared_build,
            owned_collisions,
            safety.symmetry == raw_build.build.symmetry,
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyReplacementResult:
        plan = self.plan(
            container_name,
            root_name=root_name,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Body ReBuild 预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        previous = plan.safety.body
        with self._host.transaction(
            f"替换 {len(plan.build.build.specs)} 个 Body skeleton joints"
        ):
            current_body = self._host.capture_body_skeleton(root_name)
            current_scene = self._host.capture_body_rebuild_state(root_name)
            current_fit = self._host.capture_fit_orientation(
                plan.build.build.symmetry.source.hierarchy.container
            )
            current_settings = self._host.read_fit_skeleton_settings(
                plan.build.build.symmetry.source.hierarchy.container
            )
            if (
                current_body != plan.safety.body
                or current_scene != plan.safety.scene
                or current_fit != plan.build.build.symmetry.source
                or current_settings != plan.build.build.symmetry.settings
            ):
                raise RuntimeError(
                    "Body ReBuild 执行前场景发生变化，旧 Body 未删除"
                )
            self._host.delete_owned_body(previous.root)
            build = _build_oriented_body_skeleton_in_transaction(
                self._host,
                plan.build,
            )
            scene = self._host.capture_body_rebuild_state(root_name)
            issues = audit_body_rebuild_safety(
                plan.build.build.symmetry.instances,
                build.snapshot,
                scene,
                plan.build.provenance,
            )
            if issues:
                raise RuntimeError(
                    "Body ReBuild 后复检失败："
                    + "；".join(issue.message for issue in issues)
                )
        return BodyReplacementResult(plan, previous, build, scene)
