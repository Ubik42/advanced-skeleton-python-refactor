"""KneeC/D weighted influences driven by the rebuilt knee and hip Part chain."""
from __future__ import annotations

from math import isfinite
from typing import Mapping

from .body_skeleton import BodySkeletonSnapshot
from .chest_volume_deform import NODE_TYPES
from .sdk_volume_deform import SdkVolumeSpec


def plan_knee_volume_influences(
    body: BodySkeletonSnapshot, guide: Mapping[str, object]
) -> tuple[SdkVolumeSpec, ...]:
    by_name = {joint.name: joint for joint in body.joints}
    source_frames = guide.get("body_world_matrices")
    records = guide.get("joints")
    if not isinstance(source_frames, dict) or not isinstance(records, list):
        raise ValueError("膝部体积导向文档缺少原版 Body 矩阵或关节记录")
    specs = []
    for side in ("R", "L"):
        hip_name, knee_name = "Hip_" + side, "Knee_" + side
        hip, knee = by_name.get(hip_name), by_name.get(knee_name)
        if hip is None or knee is None or knee.parent_path != hip.path:
            raise ValueError("KneeC 需要 Hip → Knee Body 直接父子链：" + side)
        source_frame = source_frames.get(knee_name)
        if not isinstance(source_frame, (list, tuple)) or len(source_frame) != 16:
            raise ValueError("原版导向文档缺少膝关节静止矩阵：" + side)
        current_frame = (*knee.world_axes[0], 0.0,
                         *knee.world_axes[1], 0.0,
                         *knee.world_axes[2], 0.0,
                         *knee.world_position, 1.0)
        if (not all(isfinite(float(value)) for value in source_frame)
                or max(abs(float(a) - b) for a, b in zip(
                    source_frame, current_frame)) > 1e-3):
            raise ValueError("原版和当前膝关节静止姿态不匹配：" + side)
        for letter in ("C", "D"):
            name = f"Knee{letter}Joint_{side}"
            matches = [row for row in records if isinstance(row, dict)
                       and row.get("name") == name]
            if len(matches) != 1:
                raise ValueError("原版导向文档需要唯一膝体积关节：" + name)
            row = matches[0]
            chain = row.get("target_chain")
            graph = row.get("sdk_sources")
            expected_parent = ("HipPart2_" + side if letter == "C"
                               else knee_name)
            if (row.get("parent") != expected_parent
                    or not isinstance(chain, list) or len(chain) < 4
                    or chain[1].get("name") != f"SDKKnee{letter}_{side}"
                    or not isinstance(graph, dict)):
                raise ValueError("原版膝体积驱动层级无效：" + name)
            if any(not isinstance(node, dict) or node.get("type") not in NODE_TYPES
                   for node in graph.values()):
                raise ValueError("膝体积驱动图包含未知节点：" + name)
            for node in graph.values():
                for source_plug in node.get("sources", []):
                    source_node = str(source_plug).split(".", 1)[0]
                    if source_node not in graph and source_plug != knee_name + ".rotateZ":
                        raise ValueError("膝体积驱动图包含未知外部输入：" + source_plug)
            parent = (hip.path + "|HipPart1_" + side + "|HipPart2_" + side
                      if letter == "C" else knee.path)
            specs.append(SdkVolumeSpec(name, parent + "|" + name,
                                        parent, knee_name, row))
    return tuple(specs)
