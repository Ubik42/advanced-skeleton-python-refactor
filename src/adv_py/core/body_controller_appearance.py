"""Appearance and placement rules from ADV 6.925 ``asCreateController``."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re

from .body_controller_layers import BodyControllerLayerSpec


_ORIENTED_ORDER_TYPES = frozenset((
    "FK", "IKLocal", "Bend", "BendMid", "IKhybrid"))
_ORIENTED_SHAPE_TYPES = _ORIENTED_ORDER_TYPES | {"HipSwinger"}
_OFFSET_ROTATION_TYPES = frozenset(("FK", "Bend", "BendMid"))


@dataclass(frozen=True, slots=True)
class BodyControllerAppearanceInput:
    layers: BodyControllerLayerSpec
    fit_joint: str
    main_height: float
    first_child_distance: float | None
    fit_fat: tuple[float, float, float] | None
    body_fat: tuple[float, float, float] | None
    fit_rotate_order: int
    fit_ik_local_type2: bool
    body_world_position: tuple[float, float, float]
    body_world_rotation: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class BodyControllerAppearancePlan:
    layers: BodyControllerLayerSpec
    icon_template: str
    icon_curve_scale: float
    control_local_scale: tuple[float, float, float]
    rotate_order: int | None
    world_position: tuple[float, float, float]
    offset_world_rotation: tuple[float, float, float] | None
    orient_icon_from_fit_axis: bool
    fit_joint: str
    add_extra_to_control_set: bool = True


@dataclass(frozen=True, slots=True)
class BodyControllerAppearanceState:
    icon_template: str
    icon_curve_scale: float
    control_local_scale: tuple[float, float, float]
    rotate_orders: tuple[tuple[str, int], ...]
    offset_world_position: tuple[float, float, float]
    offset_world_rotation: tuple[float, float, float]
    orient_icon_from_fit_axis: bool
    extra_in_control_set: bool


def _finite_triplet(values: tuple[float, float, float]) -> bool:
    return len(values) == 3 and all(
        type(value) in (int, float) and isfinite(value) for value in values)


def plan_body_controller_appearance(
    source: BodyControllerAppearanceInput,
) -> BodyControllerAppearancePlan:
    if not isinstance(source, BodyControllerAppearanceInput):
        raise ValueError("Body 控制器外观输入无效")
    layers = source.layers
    if (not isinstance(layers, BodyControllerLayerSpec)
            or not isinstance(source.fit_joint, str)
            or not source.fit_joint
            or type(source.main_height) not in (int, float)
            or not isfinite(source.main_height)
            or source.main_height <= 0
            or (source.first_child_distance is not None and (
                type(source.first_child_distance) not in (int, float)
                or not isfinite(source.first_child_distance)
                or source.first_child_distance < 0))
            or type(source.fit_rotate_order) is not int
            or not 0 <= source.fit_rotate_order <= 5
            or type(source.fit_ik_local_type2) is not bool
            or not _finite_triplet(source.body_world_position)
            or not _finite_triplet(source.body_world_rotation)
            or any(fat is not None and not _finite_triplet(fat)
                   for fat in (source.fit_fat, source.body_fat))):
        raise ValueError("Body 控制器外观数据无效")

    if "Scapula" in layers.name:
        icon = "Scapula_icon"
    elif layers.kind == "FK" and re.search(r"Part[0-9]", layers.name):
        icon = "Part_icon"
    else:
        icon = layers.kind + "_icon"

    default_size = source.main_height / 30.0
    if source.first_child_distance is not None:
        distance = source.first_child_distance
        default_size *= distance / 2.0 if distance > 1.0 else (
            1.0 + distance) / 2.0
    fat = source.body_fat if source.body_fat is not None else source.fit_fat
    # The MEL scales every CV by $sca[1], then by 1.5. The other two
    # components of $sca do not change this curve in 6.925.
    radius = (fat[0] * fat[1] if fat is not None else default_size) * 1.5
    if radius <= 0:
        raise ValueError("Body 控制器曲线尺寸须大于零")
    ordered = (layers.kind in _ORIENTED_ORDER_TYPES
               or source.fit_ik_local_type2)
    oriented = (layers.kind in _ORIENTED_SHAPE_TYPES
                or source.fit_ik_local_type2)
    return BodyControllerAppearancePlan(
        layers=layers, icon_template=icon, icon_curve_scale=radius,
        control_local_scale=((-1.0, -1.0, -1.0)
                             if layers.side == "_L"
                             else (1.0, 1.0, 1.0)),
        rotate_order=source.fit_rotate_order if ordered else None,
        world_position=source.body_world_position,
        offset_world_rotation=(source.body_world_rotation
                               if layers.kind in _OFFSET_ROTATION_TYPES
                               else None),
        orient_icon_from_fit_axis=oriented,
        fit_joint=source.fit_joint,
    )


def audit_body_controller_appearance(
    plan: BodyControllerAppearancePlan,
    state: BodyControllerAppearanceState,
    *, tolerance: float = 1e-4,
) -> tuple[str, ...]:
    issues = []
    if (not _finite_triplet(state.control_local_scale)
            or not _finite_triplet(state.offset_world_position)
            or not _finite_triplet(state.offset_world_rotation)
            or type(state.icon_curve_scale) not in (int, float)
            or not isfinite(state.icon_curve_scale)):
        return ("控制器外观读回数据无效",)
    if (state.icon_template != plan.icon_template
            or abs(state.icon_curve_scale - plan.icon_curve_scale) > tolerance):
        issues.append("图标模板或曲线尺寸不符")
    if any(abs(a - b) > tolerance for a, b in zip(
            state.control_local_scale, plan.control_local_scale)):
        issues.append("控制器镜像缩放不符")
    if plan.rotate_order is not None:
        wanted = {path: plan.rotate_order for path in (
            plan.layers.offset_path, plan.layers.extra_path,
            plan.layers.control_path)}
        if (len(state.rotate_orders) != len(wanted)
                or dict(state.rotate_orders) != wanted):
            issues.append("控制器旋转顺序不符")
    if any(abs(a - b) > tolerance for a, b in zip(
            state.offset_world_position, plan.world_position)):
        issues.append("控制器世界位置不符")
    if (plan.offset_world_rotation is not None and any(
            abs(a - b) > tolerance for a, b in zip(
                state.offset_world_rotation, plan.offset_world_rotation))):
        issues.append("控制器世界朝向不符")
    if state.orient_icon_from_fit_axis != plan.orient_icon_from_fit_axis:
        issues.append("控制器图标轴向处理不符")
    if state.extra_in_control_set != plan.add_extra_to_control_set:
        issues.append("Extra 控制层选择集归属不符")
    return tuple(issues)
