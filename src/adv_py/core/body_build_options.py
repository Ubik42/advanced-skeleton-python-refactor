"""Preparation / Rig switches stored on the FitSkeleton container."""
from __future__ import annotations

from dataclasses import dataclass

from .body_game_engine import BodyGameEnginePolicy
from .fit_settings import (
    FitSkeletonField, FitSkeletonSetting, FitSkeletonSettings,
    FitSkeletonValidationError, audit_fit_skeleton_settings,
)
from .fit_skeleton_io import FitSkeletonSettingChannelState


BODY_BUILD_OPTION_FIELDS = (
    FitSkeletonField.GAME_ENGINE,
    FitSkeletonField.USE_OFFSET_PARENT_MATRIX,
    FitSkeletonField.SUB_CONTROLLERS,
    FitSkeletonField.EXTRA_CONTROLLERS,
)


@dataclass(frozen=True, slots=True)
class BodyBuildOptions:
    game_engine: bool = False
    use_offset_parent_matrix: bool = False
    sub_controllers: bool = False
    extra_controllers: bool = False

    def __post_init__(self) -> None:
        if any(type(value) is not bool for value in (
                self.game_engine, self.use_offset_parent_matrix,
                self.sub_controllers, self.extra_controllers)):
            raise FitSkeletonValidationError("Body 构建选项必须为布尔值")

    def settings(self) -> tuple[FitSkeletonSetting, ...]:
        return tuple(FitSkeletonSetting(field, getattr(self, field.value))
                     for field in BODY_BUILD_OPTION_FIELDS)

    @property
    def game_engine_policy(self) -> BodyGameEnginePolicy:
        return BodyGameEnginePolicy(self.game_engine)

    @classmethod
    def from_fit_settings(cls, settings: FitSkeletonSettings) -> "BodyBuildOptions":
        values = {field.value: settings.value(field)
                  for field in BODY_BUILD_OPTION_FIELDS}
        if any(type(value) is not bool for value in values.values()):
            raise FitSkeletonValidationError("FitSkeleton 缺少 Body 构建选项")
        return cls(**values)


@dataclass(frozen=True, slots=True)
class BodyBuildOptionPlan:
    before: FitSkeletonSettings
    channels: tuple[FitSkeletonSettingChannelState, ...]
    desired: BodyBuildOptions
    additions: tuple[FitSkeletonSetting, ...]
    updates: tuple[FitSkeletonSetting, ...]

    @property
    def changed(self) -> bool:
        return bool(self.additions or self.updates)


def plan_body_build_options(
    before: FitSkeletonSettings,
    channels: tuple[FitSkeletonSettingChannelState, ...],
    desired: BodyBuildOptions,
) -> BodyBuildOptionPlan:
    if not isinstance(desired, BodyBuildOptions):
        raise FitSkeletonValidationError("Body 构建选项类型无效")
    issues = audit_fit_skeleton_settings(before, require_complete=False)
    if issues:
        raise FitSkeletonValidationError("FitSkeleton 设置无效："
                                         + "；".join(item.message for item in issues))
    by_field = {channel.field: channel for channel in channels}
    if (len(by_field) != len(channels)
            or set(by_field) != before.present_fields
            or any(channel.value != before.value(channel.field)
                   for channel in channels)):
        raise FitSkeletonValidationError("FitSkeleton 设置通道与当前值不一致")
    additions = []
    updates = []
    for setting in desired.settings():
        channel = by_field.get(setting.field)
        if channel is None:
            additions.append(setting)
        elif channel.value != setting.value:
            if not channel.writable or channel.incoming_sources:
                raise FitSkeletonValidationError(
                    "Body 构建选项被锁定或连接：" + setting.field.value)
            updates.append(setting)
    return BodyBuildOptionPlan(before, channels, desired,
                               tuple(additions), tuple(updates))
