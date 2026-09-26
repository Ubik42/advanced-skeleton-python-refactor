"""Root volume influences reconstructed from an AdvancedSkeleton rig guide."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

from .body_skeleton import BodySkeletonSnapshot


Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class RootVolumeSpec:
    name: str
    path: str
    parent: str
    translate: Vector3
    rotate: Vector3
    joint_orient: Vector3
    scale: Vector3
    rotate_order: int


def _vector(value: object, label: str) -> Vector3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(label + " 必须是三维向量")
    result = tuple(float(v) for v in value)
    if not all(isfinite(v) for v in result):
        raise ValueError(label + " 不能包含非有限数值")
    return result  # type: ignore[return-value]


def plan_root_volume_influences(
    body: BodySkeletonSnapshot, guide: Mapping[str, object]
) -> tuple[RootVolumeSpec, RootVolumeSpec]:
    root = next((joint for joint in body.joints if joint.path == body.root), None)
    if root is None or root.name != "Root_M":
        raise ValueError("Root 体积关节需要 Root_M Body 根关节")
    source_root = guide.get("root_world_matrix")
    if not isinstance(source_root, (list, tuple)) or len(source_root) != 16:
        raise ValueError("原版导向文档缺少 Root_M 世界矩阵")
    source_root = tuple(float(value) for value in source_root)
    if not all(isfinite(value) for value in source_root):
        raise ValueError("原版 Root_M 世界矩阵包含非有限数值")
    current_root = (
        *root.world_axes[0], 0.0,
        *root.world_axes[1], 0.0,
        *root.world_axes[2], 0.0,
        *root.world_position, 1.0,
    )
    if max(abs(a - b) for a, b in zip(source_root, current_root)) > 1e-3:
        raise ValueError("原版导向文档与当前 Root_M 静止世界矩阵不匹配")
    records = guide.get("joints")
    if not isinstance(records, list):
        raise ValueError("原版体积关节导向文档缺少 joints 列表")
    by_name: dict[str, Mapping[str, object]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("原版体积关节记录必须是对象")
        name = record.get("name")
        if name in ("RootAJoint_R", "RootAJoint_L"):
            if name in by_name:
                raise ValueError("原版 Root 体积关节重复：" + str(name))
            by_name[str(name)] = record
    if set(by_name) != {"RootAJoint_R", "RootAJoint_L"}:
        raise ValueError("原版导向文档需要双侧 RootAJoint")
    specs = []
    for side in ("R", "L"):
        name = "RootAJoint_" + side
        row = by_name[name]
        if row.get("parent") != "Root_M" or row.get("target_parent") != "OffsetRootA_" + side:
            raise ValueError("Root 体积关节来源层级不符：" + name)
        order = row.get("joint_rotate_order")
        if isinstance(order, bool) or not isinstance(order, int) or order not in range(6):
            raise ValueError("Root 体积关节旋转顺序无效：" + name)
        scale = _vector(row.get("joint_local_scale"), name + " scale")
        if any(v == 0.0 for v in scale):
            raise ValueError("Root 体积关节缩放不能为零：" + name)
        specs.append(RootVolumeSpec(
            name=name, path=body.root + "|" + name, parent=body.root,
            translate=_vector(row.get("joint_local_translate"), name + " translate"),
            rotate=_vector(row.get("joint_local_rotate"), name + " rotate"),
            joint_orient=_vector(row.get("joint_orient"), name + " jointOrient"),
            scale=scale, rotate_order=order,
        ))
    return specs[0], specs[1]
