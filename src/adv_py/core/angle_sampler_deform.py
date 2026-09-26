"""Original locator-distance angle drivers for weighted volume joints."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

from .body_skeleton import BodySkeletonSnapshot


ANGLE_AXES = {"Hip": ("Y", "Z"), "Shoulder": ("Y",),
              "Wrist": ("Y", "Z"), "Ankle": ("Z",)}
NODE_TYPES = frozenset(("locator", "condition", "plusMinusAverage",
                        "distanceBetween", "unitConversion"))


@dataclass(frozen=True, slots=True)
class AngleSamplerSpec:
    stem: str
    side: str
    target: str
    parent: str
    source_joint_world_matrix: tuple[float, ...]
    source_parent_world_matrix: tuple[float, ...]
    ancestors: Mapping[str, Mapping[str, object]]
    graph: Mapping[str, Mapping[str, object]]
    outputs: Mapping[str, str]
    values: Mapping[str, float]


def _matrix(value: object, label: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != 16:
        raise ValueError(label + " 世界矩阵无效")
    result = tuple(float(v) for v in value)
    if not all(isfinite(v) for v in result):
        raise ValueError(label + " 世界矩阵含非有限数值")
    return result


def plan_angle_samplers(
    body: BodySkeletonSnapshot, guide: Mapping[str, object]
) -> tuple[AngleSamplerSpec, ...]:
    records = guide.get("angles")
    if not isinstance(records, dict):
        raise ValueError("原版角度导向文档缺少 angles 记录")
    by_name = {joint.name: joint for joint in body.joints}
    specs = []
    for side in ("R", "L"):
        for stem, axes in ANGLE_AXES.items():
            target_name = f"{stem}_{side}"
            target = by_name.get(target_name)
            source_parent = {"Hip": "Root_M", "Shoulder": f"Scapula_{side}",
                             "Wrist": f"ElbowPart2_{side}",
                             "Ankle": f"Knee_{side}"}[stem]
            if target is None:
                raise ValueError("角度采样器缺少 Body 目标：" + target_name)
            if source_parent in by_name:
                parent = by_name[source_parent].path
            else:
                elbow = by_name.get(f"Elbow_{side}")
                if elbow is None:
                    raise ValueError("腕角度采样器缺少 Elbow Body")
                parent = (elbow.path + f"|ElbowPart1_{side}"
                          + f"|ElbowPart2_{side}")
            graph: dict[str, Mapping[str, object]] = {}
            ancestors: dict[str, Mapping[str, object]] = {}
            outputs = {}
            values = {}
            source_joint = None
            for axis in axes:
                plug = target_name + ".angle" + axis
                row = records.get(plug)
                if not isinstance(row, dict) or not isinstance(row.get("graph"), dict):
                    raise ValueError("原版角度导向缺少节点图：" + plug)
                source_joint = _matrix(row.get("joint_world_matrix"), plug)
                for name, node in row["graph"].items():
                    if not isinstance(node, dict) or node.get("type") not in NODE_TYPES:
                        raise ValueError("原版角度图包含未知节点：" + name)
                    if name in graph and graph[name] != node:
                        raise ValueError("原版角度图共享节点不一致：" + name)
                    graph[name] = node
                    if node["type"] == "locator":
                        for ancestor in node.get("ancestor_chain", []):
                            if ancestor["name"].endswith(("AngleSamplerBaseParent",
                                                            "AngleSamplerBase",
                                                            "AngleSamplerRotate")):
                                ancestors[ancestor["name"]] = ancestor
                output = row.get("source_plug")
                if not isinstance(output, str) or output.split(".", 1)[0] not in graph:
                    raise ValueError("原版角度导向输出缺失：" + plug)
                outputs[axis] = output
                values[axis] = float(row["value"])
            base_parent = ancestors.get(target_name + "AngleSamplerBaseParent")
            base = ancestors.get(target_name + "AngleSamplerBase")
            rotate = ancestors.get(target_name + "AngleSamplerRotate")
            if not all((base_parent, base, rotate)):
                raise ValueError("原版角度采样器定位点层级缺失：" + target_name)
            def targets(item, kind):
                return [constraint["targets"] for constraint in
                        item.get("constraints", []) if constraint["type"] == kind]
            if (targets(base_parent, "pointConstraint") != [[source_parent]]
                    or targets(base_parent, "orientConstraint") != [[source_parent]]
                    or targets(base, "pointConstraint") != [[target_name]]
                    or targets(rotate, "orientConstraint") != [[target_name]]):
                raise ValueError("原版角度采样器约束来源不符：" + target_name)
            for node in graph.values():
                for destination, origin in node.get("connections", []):
                    if origin.split(".", 1)[0] not in graph:
                        raise ValueError("原版角度图包含外部连接：" + origin)
            specs.append(AngleSamplerSpec(
                stem, side, target.path, parent, source_joint,
                _matrix(base_parent.get("world_matrix"), target_name + " base"),
                ancestors, graph, outputs, values,
            ))
    return tuple(specs)
