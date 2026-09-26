"""Elbow and knee A/B weighted influences driven by joint bend."""
from __future__ import annotations

from typing import Mapping

from .body_skeleton import BodySkeletonSnapshot
from .chest_volume_deform import NODE_TYPES
from .sdk_volume_deform import SdkVolumeSpec
from .volume_half_parent import plan_volume_half_parents


def plan_bend_volume_influences(
    body: BodySkeletonSnapshot, guide: Mapping[str, object]
) -> tuple[SdkVolumeSpec, ...]:
    records = guide.get("joints")
    if not isinstance(records, list):
        raise ValueError("肘膝体积导向文档缺少关节记录")
    helpers = {spec.name: spec for spec in plan_volume_half_parents(body, guide)}
    specs = []
    for side in ("R", "L"):
        for stem in ("Elbow", "Knee"):
            helper = helpers[f"{stem}_{side}_50"]
            driver = f"{stem}_{side}"
            for letter in ("A", "B"):
                name = f"{stem}{letter}Joint_{side}"
                matches = [row for row in records if isinstance(row, dict)
                           and row.get("name") == name]
                if len(matches) != 1:
                    raise ValueError("原版导向文档需要唯一肘膝体积关节：" + name)
                row = matches[0]
                chain = row.get("target_chain")
                graph = row.get("sdk_sources")
                if (row.get("parent") != helper.name
                        or not isinstance(chain, list) or len(chain) < 4
                        or chain[1].get("name") != f"SDK{stem}{letter}_{side}"
                        or not isinstance(graph, dict)):
                    raise ValueError("原版肘膝体积驱动层级无效：" + name)
                if any(not isinstance(node, dict) or node.get("type") not in NODE_TYPES
                       for node in graph.values()):
                    raise ValueError("肘膝体积驱动图含未知节点：" + name)
                for node in graph.values():
                    for source_plug in node.get("sources", []):
                        source_node = str(source_plug).split(".", 1)[0]
                        if (source_node not in graph
                                and source_plug != driver + ".rotateZ"):
                            raise ValueError("肘膝体积驱动图含未知外部输入：" + source_plug)
                specs.append(SdkVolumeSpec(name, helper.path + "|" + name,
                                            helper.path, driver, row))
    return tuple(specs)
