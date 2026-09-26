"""Inspect weighted AJoint-DJoint influences in the original Maya scene."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys


NAME = re.compile(r"^(Root|Chest|Scapula|Shoulder|Elbow|Wrist|Hip|Knee|Ankle)[ABCD]Joint_[RL]$")


def main(scene: Path, report: Path) -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)

        def inputs(node):
            return {attr: cmds.listConnections(node + "." + attr,
                source=True, destination=False, plugs=True) or []
                for attr in ("translate", "rotate", "scale",
                             "translateX", "translateY", "translateZ",
                             "rotateX", "rotateY", "rotateZ",
                             "scaleX", "scaleY", "scaleZ",
                             "offsetParentMatrix")}

        def chain(node):
            result = []
            while node and node not in ("Group", "Main", "DeformationSystem"):
                result.append({
                    "name": node,
                    "type": cmds.nodeType(node),
                    "parent": (cmds.listRelatives(node, parent=True,
                        fullPath=False) or [None])[0],
                    "translate": cmds.getAttr(node + ".translate")[0],
                    "rotate": cmds.getAttr(node + ".rotate")[0],
                    "scale": cmds.getAttr(node + ".scale")[0],
                    "world_matrix": cmds.xform(node, query=True,
                        worldSpace=True, matrix=True),
                    "inputs": inputs(node),
                })
                node = result[-1]["parent"]
            return result

        def source_nodes(chain_rows):
            result = {}
            pending = [plug for row in chain_rows[:3]
                       for values in row["inputs"].values() for plug in values]
            while pending:
                plug = pending.pop()
                node = plug.split(".", 1)[0]
                if node in result:
                    continue
                node_type = cmds.nodeType(node)
                if node_type not in ("blendWeighted", "animCurveUA", "animCurveUL",
                                     "animCurveUU", "animCurveUT", "unitConversion"):
                    continue
                sources = cmds.listConnections(node, source=True,
                    destination=False, plugs=True) or []
                pairs = cmds.listConnections(node, source=True,
                    destination=False, plugs=True, connections=True) or []
                record = {"type": node_type,
                          "sources": sorted(set(sources)),
                          "connections": [pairs[index:index + 2]
                                          for index in range(0, len(pairs), 2)]}
                if node_type.startswith("animCurve"):
                    record["keys"] = list(zip(
                        cmds.keyframe(node, query=True, floatChange=True) or [],
                        cmds.keyframe(node, query=True, valueChange=True) or []))
                    record["pre_infinity"] = cmds.getAttr(node + ".preInfinity")
                    record["post_infinity"] = cmds.getAttr(node + ".postInfinity")
                    record["in_tangent_types"] = cmds.keyTangent(node,
                        query=True, inTangentType=True) or []
                    record["out_tangent_types"] = cmds.keyTangent(node,
                        query=True, outTangentType=True) or []
                    record["weighted_tangents"] = bool((cmds.keyTangent(node,
                        query=True, weightedTangents=True) or [False])[0])
                elif node_type == "unitConversion":
                    record["conversion_factor"] = cmds.getAttr(
                        node + ".conversionFactor")
                elif node_type == "blendWeighted":
                    indices = cmds.getAttr(node + ".input", multiIndices=True) or []
                    record["weights"] = {str(index): cmds.getAttr(
                        f"{node}.weight[{index}]") for index in indices}
                result[node] = record
                pending.extend(sources)
            return result

        rows = []
        for name in sorted(cmds.ls(type="joint") or []):
            if not NAME.match(name):
                continue
            parent = (cmds.listRelatives(name, parent=True,
                                        fullPath=False) or [None])[0]
            constraints = cmds.listConnections(name, source=True,
                destination=False, type="parentConstraint") or []
            if len(set(constraints)) != 1:
                raise ValueError(name + " does not have one parent constraint")
            constraint = constraints[0]
            targets = cmds.parentConstraint(constraint, query=True,
                                            targetList=True) or []
            if len(targets) != 1:
                raise ValueError(name + " does not have one driver target")
            target = targets[0]
            target_parent = (cmds.listRelatives(target, parent=True,
                fullPath=False) or [None])[0]
            target_chain = chain(target)
            rows.append({
                "name": name, "parent": parent, "target": target,
                "parent_world_matrix": cmds.xform(parent, query=True,
                    worldSpace=True, matrix=True),
                "target_parent": target_parent,
                "joint_world_matrix": cmds.xform(name, query=True,
                    worldSpace=True, matrix=True),
                "target_world_matrix": cmds.xform(target, query=True,
                    worldSpace=True, matrix=True),
                "joint_local_translate": cmds.getAttr(name + ".translate")[0],
                "joint_local_rotate": cmds.getAttr(name + ".rotate")[0],
                "joint_orient": cmds.getAttr(name + ".jointOrient")[0],
                "joint_rotate_order": cmds.getAttr(name + ".rotateOrder"),
                "joint_local_scale": cmds.getAttr(name + ".scale")[0],
                "joint_inputs": inputs(name),
                "joint_scale_driver": [{"name": node,
                    "type": cmds.nodeType(node),
                    "input1": cmds.getAttr(node + ".input1")[0],
                    "input2": cmds.getAttr(node + ".input2")[0],
                    "connections": [pair[index:index + 2]
                        for index in range(0, len(pair), 2)]}
                    for node in (cmds.listConnections(name + ".scale",
                        source=True, destination=False) or [])
                    for pair in [cmds.listConnections(node, source=True,
                        destination=False, plugs=True, connections=True) or []]
                    if cmds.nodeType(node) == "multiplyDivide"],
                "target_local_translate": cmds.getAttr(target + ".translate")[0],
                "target_local_rotate": cmds.getAttr(target + ".rotate")[0],
                "target_inputs": inputs(target),
                "target_chain": target_chain,
                "sdk_sources": source_nodes(target_chain),
                "parent_inputs": inputs(parent) if parent else None,
                "parent_parent": (cmds.listRelatives(parent, parent=True,
                    fullPath=False) or [None])[0] if parent else None,
            })
        if len(rows) != 40:
            raise ValueError("expected 40 weighted volume joints, got " + str(len(rows)))
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"source": scene.name,
            "root_world_matrix": cmds.xform("Root_M", query=True,
                worldSpace=True, matrix=True),
            "body_world_matrices": {name: cmds.xform(name, query=True,
                worldSpace=True, matrix=True) for name in
                ("Chest_M", "Scapula_R", "Scapula_L",
                 "Knee_R", "Knee_L")},
            "count": len(rows), "joints": rows}, ensure_ascii=False,
            indent=2) + "\n", encoding="utf-8")
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
