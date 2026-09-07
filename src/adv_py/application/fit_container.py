from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_container import (
    FitContainerSpec,
    FitContainerState,
    FitUpAxis,
    audit_fit_container,
)
from adv_py.core.fit_settings import (
    FitSkeletonSetting,
    FitSkeletonSettings,
    FitSkeletonValidationError,
    audit_fit_skeleton_settings,
    default_fit_skeleton_settings,
)


class FitContainerHost(Protocol):
    def scene_up_axis(self) -> FitUpAxis: ...

    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_fit_container(self, spec: FitContainerSpec) -> str: ...

    def inspect_fit_container(self, name: str) -> FitContainerState: ...

    def add_fit_skeleton_setting(
        self,
        container: str,
        setting: FitSkeletonSetting,
    ) -> None: ...

    def read_fit_skeleton_settings(
        self, container_name: str
    ) -> FitSkeletonSettings: ...


@dataclass(frozen=True, slots=True)
class FitContainerCreatePlan:
    spec: FitContainerSpec
    settings: FitSkeletonSettings
    collisions: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.collisions


@dataclass(frozen=True, slots=True)
class FitContainerCreateResult:
    plan: FitContainerCreatePlan
    state: FitContainerState
    settings: FitSkeletonSettings


class CreateFitSkeleton:
    """Create a new, ready-to-use container without replacing scene nodes."""

    def __init__(self, host: FitContainerHost) -> None:
        self._host = host

    def plan(
        self,
        name: str = "FitSkeleton",
        *,
        display_radius: float = 3.0,
        up_axis: FitUpAxis | None = None,
        vis_gap_default: float = 0.75,
    ) -> FitContainerCreatePlan:
        spec = FitContainerSpec(
            name=name,
            display_radius=display_radius,
            up_axis=up_axis or self._host.scene_up_axis(),
        )
        settings = default_fit_skeleton_settings(
            name,
            vis_gap=vis_gap_default,
        )
        return FitContainerCreatePlan(
            spec=spec,
            settings=settings,
            collisions=self._host.find_name_collisions(name),
        )

    def apply(
        self,
        name: str = "FitSkeleton",
        *,
        display_radius: float = 3.0,
        up_axis: FitUpAxis | None = None,
        vis_gap_default: float = 0.75,
    ) -> FitContainerCreateResult:
        plan = self.plan(
            name,
            display_radius=display_radius,
            up_axis=up_axis,
            vis_gap_default=vis_gap_default,
        )
        if plan.collisions:
            raise FitSkeletonValidationError(
                "FitSkeleton 创建预检失败，同名节点未被修改："
                + "、".join(plan.collisions)
            )

        with self._host.transaction(f"创建 {plan.spec.name}"):
            path = self._host.create_fit_container(plan.spec)
            for setting in plan.settings.settings:
                self._host.add_fit_skeleton_setting(path, setting)
            state = self._host.inspect_fit_container(path)
            settings = self._host.read_fit_skeleton_settings(path)
            self._verify(plan, state, settings)
        return FitContainerCreateResult(plan=plan, state=state, settings=settings)

    @staticmethod
    def _verify(
        plan: FitContainerCreatePlan,
        state: FitContainerState,
        settings: FitSkeletonSettings,
    ) -> None:
        issues = list(audit_fit_container(state, plan.spec))
        setting_issues = audit_fit_skeleton_settings(settings, require_complete=True)
        if setting_issues:
            issues.extend(setting_issues)
        if settings.container != state.path:
            raise RuntimeError("FitSkeleton 创建后复检失败：设置不属于新建容器")
        for expected in plan.settings.settings:
            if settings.value(expected.field) != expected.value:
                raise RuntimeError(
                    "FitSkeleton 创建后复检失败：默认设置不一致："
                    f"{expected.field.value}"
                )
        if issues:
            raise RuntimeError(
                "FitSkeleton 创建后复检失败："
                + "；".join(issue.message for issue in issues)
            )
