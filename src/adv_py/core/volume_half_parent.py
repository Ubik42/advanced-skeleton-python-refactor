"""The twelve original _00/_50 parent helpers used by volume joints."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

from .body_skeleton import BodySkeletonSnapshot


@dataclass(frozen=True, slots=True)
class VolumeHalfParentSpec:
    name: str
    path: str
    zero_name: str
    zero_path: str
    parent: str
    target: str
    world_matrix: tuple[float, ...]
    parent_world_matrix: tuple[float, ...]
    joint_orient: tuple[float, float, float]
    rotate_order: int
    point_offset: tuple[float, float, float]
    orient_offset: tuple[float, float, float]
    orient_interp_type: int


def _values(value: object, count: int, label: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError(label + " 数据长度无效")
    result = tuple(float(number) for number in value)
    if not all(isfinite(number) for number in result):
        raise ValueError(label + " 包含非有限数值")
    return result


def plan_volume_half_parents(
    body: BodySkeletonSnapshot, guide: Mapping[str, object]
) -> tuple[VolumeHalfParentSpec, ...]:
    by_name = {joint.name: joint for joint in body.joints}
    if len(by_name) != len(body.joints):
        raise ValueError("Body 关节名称不唯一")
    records = guide.get("joints")
    if not isinstance(records, list):
        raise ValueError("原版导向文档缺少体积关节记录")
    specs = []
    for side in ("R", "L"):
        for stem, source_parent in (
            ("Shoulder", "Scapula_" + side),
            ("Elbow", "ShoulderPart2_" + side),
            ("Wrist", "ElbowPart2_" + side),
            ("Hip", "Root_M"),
            ("Knee", "HipPart2_" + side),
            ("Ankle", "Knee_" + side),
        ):
            target = by_name.get(stem + "_" + side)
            if target is None:
                raise ValueError("体积中间关节缺少 Body 目标：" + stem + side)
            helper_name = f"{stem}_{side}_50"
            rows = [row for row in records if isinstance(row, dict)
                    and row.get("parent") == helper_name]
            if not rows:
                raise ValueError("原版导向缺少中间关节：" + helper_name)
            row = rows[0]
            helper = row.get("parent_node")
            zero = row.get("parent_zero")
            if (row.get("parent_parent") != source_parent
                    or not isinstance(helper, dict) or helper.get("type") != "joint"
                    or not isinstance(zero, dict)
                    or zero.get("name") != f"{stem}_{side}_00"
                    or zero.get("parent") != source_parent
                    or any(abs(v) > 1e-8 for v in _values(
                        zero.get("translate"), 3, helper_name + " zero translate"))
                    or any(abs(v) > 1e-8 for v in _values(
                        zero.get("rotate"), 3, helper_name + " zero rotate"))):
                raise ValueError("原版体积中间关节层级不符：" + helper_name)
            constraints = {item["type"]: item for item in helper.get("constraints", [])}
            point = constraints.get("pointConstraint", {})
            orient = constraints.get("orientConstraint", {})
            if (point.get("targets") != [stem + "_" + side]
                    or orient.get("targets") != [zero["name"], stem + "_" + side]
                    or point.get("weight_values") != [1.0]
                    or orient.get("weight_values") != [1.0, 1.0]):
                raise ValueError("原版体积中间关节约束不符：" + helper_name)
            if source_parent in by_name:
                parent = by_name[source_parent].path
            else:
                source_stem = {"ShoulderPart2": "Shoulder",
                               "ElbowPart2": "Elbow",
                               "HipPart2": "Hip"}[source_parent.split("_", 1)[0]]
                start = by_name[source_stem + "_" + side]
                parent = (start.path + f"|{source_stem}Part1_{side}"
                          + "|" + source_parent)
            order = helper.get("rotate_order")
            if isinstance(order, bool) or not isinstance(order, int) or order not in range(6):
                raise ValueError("体积中间关节旋转顺序无效：" + helper_name)
            orient_values = _values(helper.get("joint_orient"), 3,
                                    helper_name + " jointOrient")
            point_offset = _values(point.get("offset"), 3,
                                   helper_name + " point offset")
            orient_offset = _values(orient.get("offset"), 3,
                                    helper_name + " orient offset")
            interp_type = orient.get("interp_type")
            if isinstance(interp_type, bool) or not isinstance(interp_type, int):
                raise ValueError("体积中间关节约束插值类型无效：" + helper_name)
            specs.append(VolumeHalfParentSpec(
                helper_name, parent + "|" + helper_name,
                zero["name"], parent + "|" + zero["name"],
                parent, target.path,
                _values(helper.get("world_matrix"), 16,
                        helper_name + " world matrix"),
                _values(helper.get("parent_world_matrix"), 16,
                        helper_name + " parent matrix"),
                (orient_values[0], orient_values[1], orient_values[2]),
                order,
                (point_offset[0], point_offset[1], point_offset[2]),
                (orient_offset[0], orient_offset[1], orient_offset[2]),
                interp_type,
            ))
    return tuple(specs)
