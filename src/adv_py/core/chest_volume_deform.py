"""Chest and scapula volume influence plans from an original rig graph."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

from .body_skeleton import BodySkeletonSnapshot


STEMS = ("ChestA", "ScapulaA")
SIDES = ("R", "L")
NODE_TYPES = frozenset(("blendWeighted", "animCurveUA", "animCurveUL",
                        "animCurveUU", "animCurveUT", "unitConversion"))


@dataclass(frozen=True, slots=True)
class ChestVolumeSpec:
    name: str
    path: str
    parent: str
    side: str
    guide: Mapping[str, object]


def plan_chest_volume_influences(
    body: BodySkeletonSnapshot, guide: Mapping[str, object]
) -> tuple[ChestVolumeSpec, ...]:
    by_name = {joint.name: joint for joint in body.joints}
    if "Chest_M" not in by_name or any(
        "Scapula_" + side not in by_name for side in SIDES
    ):
        raise ValueError("胸部体积关节需要 Chest_M 和双侧 Scapula Body 关节")
    source_frames = guide.get("body_world_matrices")
    if not isinstance(source_frames, dict):
        raise ValueError("原版导向文档缺少胸部和肩胛静止世界矩阵")
    for name in ("Chest_M", "Scapula_R", "Scapula_L"):
        source_frame = source_frames.get(name)
        if not isinstance(source_frame, (list, tuple)) or len(source_frame) != 16:
            raise ValueError("原版导向文档缺少静止世界矩阵：" + name)
        if not all(isfinite(float(value)) for value in source_frame):
            raise ValueError("原版导向文档世界矩阵含非有限数值：" + name)
        joint = by_name[name]
        current_frame = (*joint.world_axes[0], 0.0,
                         *joint.world_axes[1], 0.0,
                         *joint.world_axes[2], 0.0,
                         *joint.world_position, 1.0)
        if max(abs(float(a) - b) for a, b in zip(source_frame,
                                                 current_frame)) > 1e-3:
            raise ValueError("原版导向文档与当前 Body 静止姿态不匹配：" + name)
    records = guide.get("joints")
    if not isinstance(records, list):
        raise ValueError("原版体积关节导向文档缺少 joints 列表")
    source = {row.get("name"): row for row in records
              if isinstance(row, dict) and row.get("name") in
              {f"{stem}Joint_{side}" for stem in STEMS for side in SIDES}}
    if len(source) != 4:
        raise ValueError("原版导向文档缺少四个胸部和肩胛体积关节")
    parent = by_name["Chest_M"].path
    specs = []
    for side in SIDES:
        for stem in STEMS:
            name = f"{stem}Joint_{side}"
            row = source[name]
            chain = row.get("target_chain")
            graph = row.get("sdk_sources")
            if (row.get("parent") != "Chest_M" or not isinstance(chain, list)
                    or len(chain) < 4 or not isinstance(graph, dict)
                    or chain[1].get("name") != f"SDK{stem}_{side}"):
                raise ValueError("原版胸部体积关节驱动层级无效：" + name)
            if any(not isinstance(node, dict) or node.get("type") not in NODE_TYPES
                   for node in graph.values()):
                raise ValueError("原版胸部体积关节有未知驱动节点：" + name)
            for node in graph.values():
                for source_plug in node.get("sources", []):
                    source_node = str(source_plug).split(".", 1)[0]
                    if source_node not in graph and source_plug not in (
                            f"Scapula_{side}.rotateY", f"Scapula_{side}.rotateZ"):
                        raise ValueError("原版胸部体积关节有未知外部驱动：" + source_plug)
            specs.append(ChestVolumeSpec(name, parent + "|" + name,
                                          parent, side, row))
    return tuple(specs)
