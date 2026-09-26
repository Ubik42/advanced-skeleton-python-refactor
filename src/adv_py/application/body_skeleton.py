from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_skeleton import (
    BodyJointSpec,
    BodySkeletonSnapshot,
    audit_body_skeleton,
)
from adv_py.core.fit_orientation import FitOrientationSnapshot
from adv_py.core.fit_settings import FitSkeletonSettings, FitSkeletonValidationError
from adv_py.core.joint_labels import JointLabel

from .fit_symmetry import FitSymmetryPlan, PlanFitSymmetry


class BodySkeletonHost(Protocol):
    def capture_fit_orientation(
        self, container_name: str
    ) -> FitOrientationSnapshot: ...

    def read_fit_skeleton_settings(
        self, container_name: str
    ) -> FitSkeletonSettings: ...

    def read_joint_label(self, joint: str) -> JointLabel | None: ...

    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_body_joint(self, spec: BodyJointSpec) -> str: ...

    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodySkeletonBuildPlan:
    symmetry: FitSymmetryPlan
    specs: tuple[BodyJointSpec, ...]
    missing_labels: tuple[str, ...]
    name_collisions: tuple[str, ...]
    inferred_labels: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.missing_labels and not self.name_collisions

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.missing_labels:
            blockers.append(
                "Fit joints 缺少标签：" + "、".join(self.missing_labels)
            )
        if self.name_collisions:
            blockers.append(
                "场景中存在构建关节同名节点："
                + "、".join(self.name_collisions)
            )
        return tuple(blockers)


@dataclass(frozen=True, slots=True)
class BodySkeletonBuildResult:
    plan: BodySkeletonBuildPlan
    snapshot: BodySkeletonSnapshot


class BuildBodySkeleton:
    """Materialize a symmetry plan as a basic Maya joint hierarchy."""

    def __init__(self, host: BodySkeletonHost) -> None:
        self._host = host
        self._symmetry = PlanFitSymmetry(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        center_tolerance: float = 0.01,
        infer_missing_labels: bool = False,
    ) -> BodySkeletonBuildPlan:
        if not isinstance(infer_missing_labels, bool):
            raise FitSkeletonValidationError("推断缺失关节标签必须是布尔值")
        symmetry = self._symmetry.execute(
            container_name,
            center_tolerance=center_tolerance,
        )
        labels: dict[str, JointLabel] = {}
        missing_labels: list[str] = []
        inferred_labels: list[str] = []
        for node in symmetry.source.hierarchy.joints:
            label = self._host.read_joint_label(node.path)
            if label is None:
                if infer_missing_labels:
                    label = JointLabel.parse(node.short_name)
                    inferred_labels.append(node.path)
                else:
                    missing_labels.append(node.path)
            if label is not None:
                labels[node.path] = label
        specs = tuple(
            BodyJointSpec.from_symmetry(instance, labels[instance.source_joint])
            for instance in symmetry.instances
            if instance.source_joint in labels
        )
        collisions = tuple(
            path
            for spec in specs
            for path in self._host.find_name_collisions(spec.name)
        )
        return BodySkeletonBuildPlan(
            symmetry,
            specs,
            tuple(missing_labels),
            collisions,
            tuple(inferred_labels),
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        center_tolerance: float = 0.01,
        infer_missing_labels: bool = False,
    ) -> BodySkeletonBuildResult:
        plan = self.plan(
            container_name,
            center_tolerance=center_tolerance,
            infer_missing_labels=infer_missing_labels,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Body skeleton 构建预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        root_name = plan.specs[0].name
        with self._host.transaction(
            f"创建 {len(plan.specs)} 个 Body skeleton joints"
        ):
            snapshot = _materialize_body_skeleton(
                self._host,
                plan,
                root_name,
            )
            current_fit = self._host.capture_fit_orientation(
                plan.symmetry.source.hierarchy.container
            )
            current_settings = self._host.read_fit_skeleton_settings(
                plan.symmetry.source.hierarchy.container
            )
            if current_fit != plan.symmetry.source:
                raise RuntimeError("Body skeleton 构建后复检失败：Fit joints 被改写")
            if current_settings != plan.symmetry.settings:
                raise RuntimeError("Body skeleton 构建后复检失败：容器设置被改写")
        return BodySkeletonBuildResult(plan, snapshot)


def _materialize_body_skeleton(
    host: BodySkeletonHost,
    plan: BodySkeletonBuildPlan,
    root_name: str,
) -> BodySkeletonSnapshot:
    """Create and audit a neutral Body skeleton inside an active transaction."""

    for spec in plan.specs:
        created = host.create_body_joint(spec)
        if created != spec.path:
            raise RuntimeError(f"Body skeleton 创建路径漂移：{spec.name}")
    snapshot = host.capture_body_skeleton(root_name)
    issues = audit_body_skeleton(plan.specs, snapshot)
    if issues:
        raise RuntimeError(
            "Body skeleton 构建后复检失败："
            + "；".join(issue.message for issue in issues)
        )
    return snapshot
