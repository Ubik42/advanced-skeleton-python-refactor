from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_hierarchy import FitHierarchySnapshot
from adv_py.core.fit_settings import (
    FitSkeletonSettings,
    FitSkeletonValidationError,
    audit_fit_skeleton_settings,
)
from adv_py.core.fit_template import (
    FitJointSpec,
    FitTemplateSpec,
    audit_fit_template_snapshot,
    minimal_body_fit_template,
    ordered_fit_joints,
)
from adv_py.core.joint_labels import JointLabel


class FitTemplateHost(Protocol):
    def scene_up_axis(self) -> FitUpAxis: ...

    def capture_fit_hierarchy(self, container_name: str) -> FitHierarchySnapshot: ...

    def read_fit_skeleton_settings(
        self, container_name: str
    ) -> FitSkeletonSettings: ...

    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_fit_joint(
        self,
        parent: str,
        spec: FitJointSpec,
    ) -> str: ...

    def set_joint_label(self, joint: str, label: JointLabel) -> None: ...

    def read_joint_label(self, joint: str) -> JointLabel | None: ...


@dataclass(frozen=True, slots=True)
class FitTemplateCreatePlan:
    template: FitTemplateSpec
    before_hierarchy: FitHierarchySnapshot
    before_settings: FitSkeletonSettings
    name_collisions: tuple[str, ...]
    setting_errors: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not (
            self.before_hierarchy.joints
            or self.name_collisions
            or self.setting_errors
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        messages: list[str] = []
        if self.before_hierarchy.joints:
            messages.append("FitSkeleton 已包含关节")
        if self.name_collisions:
            messages.append("场景中存在同名关节：" + "、".join(self.name_collisions))
        messages.extend(self.setting_errors)
        return tuple(messages)


@dataclass(frozen=True, slots=True)
class FitTemplateCreateResult:
    plan: FitTemplateCreatePlan
    hierarchy: FitHierarchySnapshot
    joint_paths: tuple[str, ...]


class CreateMinimalFitTemplate:
    """Create an independent Root/Spine baseline inside an empty container."""

    def __init__(self, host: FitTemplateHost) -> None:
        self._host = host

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        template: FitTemplateSpec | None = None,
        segment_length: float = 5.0,
    ) -> FitTemplateCreatePlan:
        active_template = template or minimal_body_fit_template(
            self._host.scene_up_axis(),
            segment_length=segment_length,
        )
        hierarchy = self._host.capture_fit_hierarchy(container_name)
        settings = self._host.read_fit_skeleton_settings(hierarchy.container)
        setting_errors = tuple(
            issue.message
            for issue in audit_fit_skeleton_settings(settings, require_complete=True)
        )
        collisions = tuple(
            path
            for joint in active_template.joints
            for path in self._host.find_name_collisions(joint.name)
        )
        return FitTemplateCreatePlan(
            template=active_template,
            before_hierarchy=hierarchy,
            before_settings=settings,
            name_collisions=collisions,
            setting_errors=setting_errors,
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        template: FitTemplateSpec | None = None,
        segment_length: float = 5.0,
    ) -> FitTemplateCreateResult:
        plan = self.plan(
            container_name,
            template=template,
            segment_length=segment_length,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "基础 Fit 模板创建预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        paths: dict[str, str] = {}
        with self._host.transaction("创建基础 Fit 关节模板"):
            for spec in ordered_fit_joints(plan.template):
                parent = plan.before_hierarchy.container
                if spec.parent is not None:
                    parent = paths[spec.parent]
                path = self._host.create_fit_joint(parent, spec)
                self._host.set_joint_label(path, spec.label)
                paths[spec.name] = path

            hierarchy = self._host.capture_fit_hierarchy(
                plan.before_hierarchy.container
            )
            settings = self._host.read_fit_skeleton_settings(
                plan.before_hierarchy.container
            )
            self._verify(plan, hierarchy, settings, paths)
        return FitTemplateCreateResult(
            plan=plan,
            hierarchy=hierarchy,
            joint_paths=tuple(paths[joint.name] for joint in plan.template.joints),
        )

    def _verify(
        self,
        plan: FitTemplateCreatePlan,
        hierarchy: FitHierarchySnapshot,
        settings: FitSkeletonSettings,
        paths: dict[str, str],
    ) -> None:
        issues = audit_fit_template_snapshot(plan.template, hierarchy)
        if issues:
            raise RuntimeError(
                "基础 Fit 模板创建后复检失败："
                + "；".join(issue.message for issue in issues)
            )
        if settings != plan.before_settings:
            raise RuntimeError("基础 Fit 模板创建后复检失败：容器设置被意外改写")
        for spec in plan.template.joints:
            if self._host.read_joint_label(paths[spec.name]) != spec.label:
                raise RuntimeError(
                    f"基础 Fit 模板创建后复检失败：{spec.name} 标签不一致"
                )
