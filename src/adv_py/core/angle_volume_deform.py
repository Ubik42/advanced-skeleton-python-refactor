"""Twenty-two weighted hip, shoulder, wrist, and ankle SDK joints."""
from __future__ import annotations

from typing import Mapping

from .body_skeleton import BodySkeletonSnapshot
from .chest_volume_deform import NODE_TYPES
from .sdk_volume_deform import SdkVolumeSpec
from .volume_half_parent import plan_volume_half_parents


FAMILIES = {
    "Hip": (("A", "Y"), ("B", "Y"), ("C", "Z"), ("D", "Z")),
    "Shoulder": (("A", "Y"),),
    "Wrist": (("A", "Y"), ("B", "Y"), ("C", "Z"), ("D", "Z")),
    "Ankle": (("A", "Z"), ("B", "Z")),
}


def plan_angle_volume_influences(
    body: BodySkeletonSnapshot, guide: Mapping[str, object]
) -> tuple[SdkVolumeSpec, ...]:
    records = guide.get("joints")
    if not isinstance(records, list):
        raise ValueError("角度体积导向文档缺少关节记录")
    by_name = {joint.name: joint for joint in body.joints}
    helpers = {spec.name: spec for spec in plan_volume_half_parents(body, guide)}
    specs = []
    for side in ("R", "L"):
        for stem, variants in FAMILIES.items():
            driver = f"{stem}_{side}"
            if driver not in by_name:
                raise ValueError("角度体积关节缺少 Body 驱动：" + driver)
            for letter, axis in variants:
                name = f"{stem}{letter}Joint_{side}"
                matches = [row for row in records if isinstance(row, dict)
                           and row.get("name") == name]
                if len(matches) != 1:
                    raise ValueError("原版导向文档需要唯一角度体积关节：" + name)
                row = matches[0]
                chain = row.get("target_chain")
                graph = row.get("sdk_sources")
                if stem == "Hip" and letter == "C":
                    parent = by_name[driver].path + f"|HipPart1_{side}"
                    parent_name = f"HipPart1_{side}"
                else:
                    helper = helpers[f"{stem}_{side}_50"]
                    parent, parent_name = helper.path, helper.name
                if (row.get("parent") != parent_name
                        or not isinstance(chain, list) or len(chain) < 4
                        or chain[1].get("name") != f"SDK{stem}{letter}_{side}"
                        or not isinstance(graph, dict)):
                    raise ValueError("原版角度体积驱动层级无效：" + name)
                if any(not isinstance(node, dict) or node.get("type") not in NODE_TYPES
                       for node in graph.values()):
                    raise ValueError("角度体积驱动图含未知节点：" + name)
                for node in graph.values():
                    for source_plug in node.get("sources", []):
                        source_node = str(source_plug).split(".", 1)[0]
                        if (source_node not in graph
                                and source_plug != driver + ".angle" + axis):
                            raise ValueError("角度体积驱动图含未知输入：" + source_plug)
                specs.append(SdkVolumeSpec(name, parent + "|" + name,
                                            parent, driver, row))
    return tuple(specs)
