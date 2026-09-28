"""Numeric controls restored by the Python Body build-pose operation."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re


@dataclass(frozen=True, slots=True)
class BodyBuildPoseValue:
    node: str
    attribute: str
    value: float

    def __post_init__(self) -> None:
        if (not isinstance(self.node, str) or not self.node
                or not isinstance(self.attribute, str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*",
                                    self.attribute)
                or isinstance(self.value, bool)
                or not isinstance(self.value, (int, float))
                or not isfinite(self.value)):
            raise ValueError("Body 构建姿态通道无效")


@dataclass(frozen=True, slots=True)
class BodyBuildPosePlan:
    values: tuple[BodyBuildPoseValue, ...]

    def __post_init__(self) -> None:
        keys = tuple((item.node, item.attribute) for item in self.values)
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("Body 构建姿态为空或通道重复")


@dataclass(frozen=True, slots=True)
class BodyBuildPoseOverrides:
    values: tuple[BodyBuildPoseValue, ...]

    def __post_init__(self) -> None:
        keys = tuple((item.node, item.attribute) for item in self.values)
        if len(keys) != len(set(keys)):
            raise ValueError("Body 构建姿态覆盖通道重复")


def plan_body_build_pose(
    values: tuple[tuple[str, str, float], ...],
) -> BodyBuildPosePlan:
    return BodyBuildPosePlan(tuple(BodyBuildPoseValue(*item)
                                   for item in values))


def plan_body_build_pose_overrides(
    base: BodyBuildPosePlan,
    current: BodyBuildPosePlan,
    *, tolerance: float = 0.001,
) -> BodyBuildPoseOverrides:
    if tolerance < 0 or not isfinite(tolerance):
        raise ValueError("构建姿态比较容差无效")
    original = {(item.node, item.attribute): item.value
                for item in base.values}
    observed = {(item.node, item.attribute): item.value
                for item in current.values}
    if not original.keys() <= observed.keys():
        raise ValueError("当前姿态缺少初始构建通道")
    return BodyBuildPoseOverrides(tuple(item for item in current.values
        if (item.node, item.attribute) not in original
        or abs(item.value - original[item.node, item.attribute]) > tolerance))


def merge_body_build_pose(
    base: BodyBuildPosePlan,
    overrides: BodyBuildPoseOverrides,
) -> BodyBuildPosePlan:
    values = {(item.node, item.attribute): item
              for item in base.values}
    for item in overrides.values:
        values[item.node, item.attribute] = item
    return BodyBuildPosePlan(tuple(values.values()))
