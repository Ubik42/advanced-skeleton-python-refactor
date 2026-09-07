from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
import re

from .fit_settings import FitSkeletonValidationError


Vector3 = tuple[float, float, float]
LOCKED_FIT_CHANNELS = frozenset({"tx", "ty", "tz", "rx", "ry", "rz"})
_SAFE_NODE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class FitUpAxis(str, Enum):
    Y = "y"
    Z = "z"


class FitContainerShape(str, Enum):
    RING = "ring"


class FitContainerDisplayStyle(str, Enum):
    FIT = "fit"


@dataclass(frozen=True, slots=True)
class FitContainerSpec:
    name: str = "FitSkeleton"
    display_radius: float = 3.0
    up_axis: FitUpAxis = FitUpAxis.Y
    shape: FitContainerShape = FitContainerShape.RING
    display_style: FitContainerDisplayStyle = FitContainerDisplayStyle.FIT

    def __post_init__(self) -> None:
        if not _SAFE_NODE_NAME.fullmatch(self.name):
            raise FitSkeletonValidationError(
                "FitSkeleton 名称必须是安全的根级节点短名"
            )
        if isinstance(self.display_radius, bool) or not isinstance(
            self.display_radius, (int, float)
        ):
            raise FitSkeletonValidationError("FitSkeleton 显示半径必须是数值")
        if not isfinite(float(self.display_radius)) or self.display_radius <= 0:
            raise FitSkeletonValidationError("FitSkeleton 显示半径必须大于 0")
        if not isinstance(self.up_axis, FitUpAxis):
            raise FitSkeletonValidationError("FitSkeleton Up Axis 仅支持 Y 或 Z")
        if not isinstance(self.shape, FitContainerShape):
            raise FitSkeletonValidationError("不支持的 FitSkeleton 显示形状")
        if not isinstance(self.display_style, FitContainerDisplayStyle):
            raise FitSkeletonValidationError("不支持的 FitSkeleton 显示样式")


@dataclass(frozen=True, slots=True)
class FitContainerState:
    path: str
    short_name: str
    shape: FitContainerShape | None
    display_style: FitContainerDisplayStyle | None
    locked_channels: frozenset[str]
    local_translation: Vector3
    local_rotation: Vector3
    bounding_size: Vector3


@dataclass(frozen=True, slots=True)
class FitContainerIssue:
    code: str
    message: str


def audit_fit_container(
    state: FitContainerState,
    spec: FitContainerSpec,
    *,
    tolerance: float = 1e-4,
) -> tuple[FitContainerIssue, ...]:
    issues: list[FitContainerIssue] = []
    if state.path != f"|{spec.name}":
        issues.append(FitContainerIssue("unexpected_path", "容器必须位于场景根级"))
    if state.short_name != spec.name:
        issues.append(FitContainerIssue("unexpected_name", "容器名称与创建计划不一致"))
    if state.shape is not spec.shape:
        issues.append(FitContainerIssue("unexpected_shape", "容器显示形状不完整"))
    if state.display_style is not spec.display_style:
        issues.append(FitContainerIssue("unexpected_style", "容器显示样式不完整"))

    missing_locks = LOCKED_FIT_CHANNELS - state.locked_channels
    if missing_locks:
        issues.append(
            FitContainerIssue(
                "unlocked_channels",
                "容器缺少锁定通道：" + "、".join(sorted(missing_locks)),
            )
        )
    if any(abs(value) > tolerance for value in state.local_translation):
        issues.append(FitContainerIssue("nonzero_translation", "容器平移必须为零"))
    if any(abs(value) > tolerance for value in state.local_rotation):
        issues.append(FitContainerIssue("nonzero_rotation", "容器旋转必须为零"))

    expected_diameter = float(spec.display_radius) * 2.0
    flat_axis = 1 if spec.up_axis is FitUpAxis.Y else 2
    radial_axes = (0, 2) if spec.up_axis is FitUpAxis.Y else (0, 1)
    if abs(state.bounding_size[flat_axis]) > tolerance:
        issues.append(
            FitContainerIssue("unexpected_plane", "容器圆环平面与 Up Axis 不一致")
        )
    if any(
        abs(state.bounding_size[index] - expected_diameter) > tolerance
        for index in radial_axes
    ):
        issues.append(
            FitContainerIssue("unexpected_radius", "容器圆环尺寸与创建计划不一致")
        )
    return tuple(issues)
