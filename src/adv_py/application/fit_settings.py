from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_settings import (
    FitSkeletonField,
    FitSkeletonSetting,
    FitSkeletonSettings,
    FitSkeletonValidationError,
    audit_fit_skeleton_settings,
    default_fit_skeleton_settings,
)


class FitSkeletonSettingsHost(Protocol):
    def read_fit_skeleton_settings(
        self, container_name: str
    ) -> FitSkeletonSettings: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def add_fit_skeleton_setting(
        self,
        container: str,
        setting: FitSkeletonSetting,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class FitSkeletonEnsurePlan:
    before: FitSkeletonSettings
    additions: tuple[FitSkeletonSetting, ...]


@dataclass(frozen=True, slots=True)
class FitSkeletonEnsureResult:
    plan: FitSkeletonEnsurePlan
    verified: FitSkeletonSettings


class EnsureFitSkeletonSettings:
    """Add only missing container settings, then verify the complete snapshot."""

    def __init__(self, host: FitSkeletonSettingsHost) -> None:
        self._host = host

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        vis_gap_default: float = 0.75,
    ) -> FitSkeletonEnsurePlan:
        if not container_name.strip():
            raise FitSkeletonValidationError("FitSkeleton 容器名称不能为空")
        before = self._host.read_fit_skeleton_settings(container_name)
        issues = audit_fit_skeleton_settings(before, require_complete=False)
        if issues:
            raise FitSkeletonValidationError(
                "FitSkeleton 设置预检失败："
                + "；".join(issue.message for issue in issues)
            )
        defaults = default_fit_skeleton_settings(
            before.container,
            vis_gap=vis_gap_default,
        )
        additions = tuple(
            item
            for item in defaults.settings
            if item.field not in before.present_fields
        )
        return FitSkeletonEnsurePlan(before=before, additions=additions)

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        vis_gap_default: float = 0.75,
    ) -> FitSkeletonEnsureResult:
        plan = self.plan(container_name, vis_gap_default=vis_gap_default)
        if not plan.additions:
            self._verify(plan.before, plan.before)
            return FitSkeletonEnsureResult(plan=plan, verified=plan.before)

        with self._host.transaction(
            f"补齐 {len(plan.additions)} 项 FitSkeleton 设置"
        ):
            for setting in plan.additions:
                self._host.add_fit_skeleton_setting(
                    plan.before.container,
                    setting,
                )
            verified = self._host.read_fit_skeleton_settings(plan.before.container)
            self._verify(plan.before, verified)
        return FitSkeletonEnsureResult(plan=plan, verified=verified)

    @staticmethod
    def _verify(
        before: FitSkeletonSettings,
        verified: FitSkeletonSettings,
    ) -> None:
        issues = audit_fit_skeleton_settings(verified, require_complete=True)
        if issues:
            raise RuntimeError(
                "FitSkeleton 设置复检失败："
                + "；".join(issue.message for issue in issues)
            )
        for previous in before.settings:
            if verified.value(previous.field) != previous.value:
                raise RuntimeError(
                    "FitSkeleton 设置复检失败：已有值被意外改写："
                    f"{previous.field.value}"
                )
