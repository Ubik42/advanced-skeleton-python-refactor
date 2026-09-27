"""Scene-independent input and parent selection for custom rig controls."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
import re


class CustomControlKind(str, Enum):
    SKIN = "skin"
    CLUSTER = "cluster"
    SOFT_MOD = "soft_mod"


@dataclass(frozen=True, slots=True)
class WeightedVertex:
    index: int
    weight: float


@dataclass(frozen=True, slots=True)
class SoftModRegion:
    deformer: str
    mesh: str
    center: tuple[float, float, float]
    vertex_count: int
    weights: tuple[WeightedVertex, ...]
    source_handle: str = ""
    falloff_radius: float = 1.0
    falloff_mode: int = 0
    falloff_curve: tuple[tuple[float, float, int], ...] = ()


@dataclass(frozen=True, slots=True)
class DeformJointCandidate:
    path: str
    center: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class CustomControllerPlan:
    kind: CustomControlKind
    region: SoftModRegion
    parent_joint: str
    offset_name: str
    control_name: str
    base_control_name: str | None
    joint_name: str | None
    deformer_name: str | None

    @property
    def created_names(self) -> tuple[str, ...]:
        names = [self.offset_name, self.control_name]
        if self.base_control_name is not None:
            names.append(self.base_control_name)
            names.extend((self.control_name + "Attach",
                          self.control_name + "BaseLocator",
                          self.control_name + "SoftModMultMatrix",
                          self.control_name + "RadiusFactor",
                          self.control_name + "RadiusScale"))
        else:
            names.append(self.control_name + "Attach")
            if self.kind is CustomControlKind.CLUSTER:
                names.append(self.control_name + "Handle")
        if self.joint_name is not None:
            names.append(self.joint_name)
        if (self.deformer_name is not None
                and self.deformer_name != self.region.deformer):
            names.append(self.deformer_name)
        return tuple(names)


def _position(value: tuple[float, float, float], label: str) -> None:
    if (not isinstance(value, tuple) or len(value) != 3
            or any(isinstance(axis, bool) or not isinstance(axis, (int, float))
                   or not isfinite(axis) for axis in value)):
        raise ValueError(label + "须为三个有限世界坐标")


def plan_custom_controller(
    kind: CustomControlKind,
    region: SoftModRegion,
    deform_joints: tuple[DeformJointCandidate, ...],
    base_name: str,
    *,
    parent_joint: str | None = None,
) -> CustomControllerPlan:
    """Use the painted SoftMod region and an explicit or nearest deform joint."""
    if not isinstance(kind, CustomControlKind):
        raise ValueError("自定义控制类型无效")
    if (not isinstance(base_name, str)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", base_name)):
        raise ValueError("自定义控制名称须为不带路径的 Maya 名称")
    if not region.deformer or not region.mesh:
        raise ValueError("SoftMod 区域须包含变形器和网格路径")
    _position(region.center, "SoftMod 中心")
    if (not isfinite(region.falloff_radius)
            or region.falloff_radius <= 0
            or region.falloff_mode not in (0, 1)):
        raise ValueError("SoftMod 衰减参数无效")
    for value, position, interpolation in region.falloff_curve:
        if (not isfinite(value) or not isfinite(position)
                or not 0 <= position <= 1 or interpolation < 0):
            raise ValueError("SoftMod 衰减曲线无效")
    if (isinstance(region.vertex_count, bool)
            or not isinstance(region.vertex_count, int)
            or region.vertex_count < 1 or not region.weights):
        raise ValueError("SoftMod 区域缺少有效顶点权重")
    seen: set[int] = set()
    active = False
    for item in region.weights:
        if (isinstance(item.index, bool) or not isinstance(item.index, int)
                or not 0 <= item.index < region.vertex_count
                or item.index in seen or isinstance(item.weight, bool)
                or not isinstance(item.weight, (int, float))
                or not isfinite(item.weight) or not 0.0 <= item.weight <= 1.0):
            raise ValueError("SoftMod 顶点索引或权重无效")
        seen.add(item.index)
        active |= item.weight > 0.0
    if not active:
        raise ValueError("SoftMod 区域没有非零影响权重")
    if not deform_joints or len({joint.path for joint in deform_joints}) != len(deform_joints):
        raise ValueError("角色缺少唯一的 DeformJoint 候选")
    for joint in deform_joints:
        if not joint.path:
            raise ValueError("DeformJoint 路径不能为空")
        _position(joint.center, "DeformJoint 位置")
    if parent_joint is not None:
        if parent_joint not in {joint.path for joint in deform_joints}:
            raise ValueError("指定父关节不属于 DeformationSystem")
        parent = parent_joint
    else:
        parent = min(deform_joints, key=lambda joint: (
            sum((a - b) ** 2 for a, b in zip(joint.center, region.center)),
            joint.path)).path
    joint_name = base_name + "Joint" if kind is CustomControlKind.SKIN else None
    deformer_name = (base_name + "SoftMod" if kind is CustomControlKind.SOFT_MOD
                     else base_name + "Cluster"
                     if kind is CustomControlKind.CLUSTER else None)
    return CustomControllerPlan(kind, region, parent,
                                base_name + "Offset",
                                base_name + "Control",
                                base_name + "BaseControl"
                                if kind is CustomControlKind.SOFT_MOD else None,
                                joint_name,
                                deformer_name)
