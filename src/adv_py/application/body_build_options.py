"""Edit the original Preparation / Rig switches as one FitSkeleton change."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_build_options import (
    BODY_BUILD_OPTION_FIELDS, BodyBuildOptionPlan, BodyBuildOptions,
    plan_body_build_options,
)
from adv_py.core.fit_settings import (
    FitSkeletonSetting, FitSkeletonSettings, FitSkeletonValidationError,
)
from adv_py.core.fit_skeleton_io import FitSkeletonSettingChannelState


class BodyBuildOptionsHost(Protocol):
    def read_fit_skeleton_settings(
        self, container_name: str,
    ) -> FitSkeletonSettings: ...

    def capture_fit_skeleton_setting_channels(
        self, container: str,
    ) -> tuple[FitSkeletonSettingChannelState, ...]: ...

    def add_fit_skeleton_setting(
        self, container: str, setting: FitSkeletonSetting,
    ) -> None: ...

    def set_fit_skeleton_setting(
        self, container: str, setting: FitSkeletonSetting,
    ) -> None: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class BodyBuildOptionResult:
    plan: BodyBuildOptionPlan
    verified: FitSkeletonSettings


class SetBodyBuildOptions:
    """Write all four persisted switches and verify unrelated fields remain."""

    def __init__(self, host: BodyBuildOptionsHost) -> None:
        self._host = host

    def plan(
        self, options: BodyBuildOptions,
        container_name: str = "FitSkeleton",
    ) -> BodyBuildOptionPlan:
        if not container_name.strip():
            raise FitSkeletonValidationError("FitSkeleton 容器名称不能为空")
        before = self._host.read_fit_skeleton_settings(container_name)
        channels = self._host.capture_fit_skeleton_setting_channels(
            before.container)
        return plan_body_build_options(before, channels, options)

    def apply(
        self, options: BodyBuildOptions,
        container_name: str = "FitSkeleton",
    ) -> BodyBuildOptionResult:
        plan = self.plan(options, container_name)
        if not plan.changed:
            return BodyBuildOptionResult(plan, plan.before)
        with self._host.transaction("设置 Body 构建选项"):
            before = self._host.read_fit_skeleton_settings(
                plan.before.container)
            channels = self._host.capture_fit_skeleton_setting_channels(
                plan.before.container)
            if before != plan.before or channels != plan.channels:
                raise FitSkeletonValidationError(
                    "Body 构建选项执行前 FitSkeleton 已变化")
            for setting in plan.additions:
                self._host.add_fit_skeleton_setting(before.container, setting)
            for setting in plan.updates:
                self._host.set_fit_skeleton_setting(before.container, setting)
            verified = self._host.read_fit_skeleton_settings(before.container)
            if (verified.container != before.container
                    or verified.present_fields
                    != before.present_fields.union(BODY_BUILD_OPTION_FIELDS)
                    or BodyBuildOptions.from_fit_settings(verified)
                    != plan.desired
                    or any(verified.value(field) != before.value(field)
                           for field in before.present_fields
                           if field not in BODY_BUILD_OPTION_FIELDS)):
                raise RuntimeError("Body 构建选项写后复检失败")
        return BodyBuildOptionResult(plan, verified)
