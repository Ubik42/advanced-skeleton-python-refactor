"""Read original angleY/Z driver graphs without editing the sam asset."""
from __future__ import annotations

import json
from pathlib import Path
import sys


ANGLES = {
    "Hip": ("angleY", "angleZ"),
    "Shoulder": ("angleY",),
    "Wrist": ("angleY", "angleZ"),
    "Ankle": ("angleZ",),
}


def main(scene: Path, report: Path) -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)

        def graph(plug):
            nodes = {}
            pending = cmds.listConnections(plug, source=True,
                destination=False, plugs=True) or []
            while pending:
                source = pending.pop()
                name = source.split(".", 1)[0]
                if name in nodes:
                    continue
                kind = cmds.nodeType(name)
                if kind in ("joint", "transform"):
                    continue
                pairs = cmds.listConnections(name, source=True,
                    destination=False, plugs=True, connections=True) or []
                connections = [pairs[i:i + 2] for i in range(0, len(pairs), 2)]
                row = {"type": kind, "connections": connections}
                if kind == "locator":
                    transform = (cmds.listRelatives(name, parent=True,
                        fullPath=False) or [None])[0]
                    row["transform"] = transform
                    row["parent"] = (cmds.listRelatives(transform, parent=True,
                        fullPath=False) or [None])[0]
                    row["translate"] = cmds.getAttr(transform + ".translate")[0]
                    row["rotate"] = cmds.getAttr(transform + ".rotate")[0]
                    row["scale"] = cmds.getAttr(transform + ".scale")[0]
                    row["local_position"] = cmds.getAttr(name + ".localPosition")[0]
                    ancestors = []
                    node = row["parent"]
                    while node and cmds.nodeType(node) == "transform" and len(ancestors) < 8:
                        parent = (cmds.listRelatives(node, parent=True,
                            fullPath=False) or [None])[0]
                        pairs = cmds.listConnections(node, source=True,
                            destination=False, plugs=True, connections=True) or []
                        ancestors.append({"name": node, "parent": parent,
                            "translate": cmds.getAttr(node + ".translate")[0],
                            "rotate": cmds.getAttr(node + ".rotate")[0],
                            "scale": cmds.getAttr(node + ".scale")[0],
                            "world_matrix": cmds.xform(node, query=True,
                                worldSpace=True, matrix=True),
                            "constraints": [{"name": constraint,
                                "type": kind,
                                "targets": (cmds.pointConstraint(constraint,
                                    query=True, targetList=True)
                                    if kind == "pointConstraint" else
                                    cmds.orientConstraint(constraint,
                                        query=True, targetList=True)) or [],
                                "offset": cmds.getAttr(constraint + ".offset")[0]}
                                for kind in ("pointConstraint", "orientConstraint")
                                for constraint in sorted(set(cmds.listConnections(
                                    node, source=True, destination=False,
                                    type=kind) or []))],
                            "connections": [pairs[i:i + 2]
                                for i in range(0, len(pairs), 2)]})
                        node = parent
                    row["ancestor_chain"] = ancestors
                elif kind == "condition":
                    row["operation"] = cmds.getAttr(name + ".operation")
                    row["first_term"] = cmds.getAttr(name + ".firstTerm")
                    row["second_term"] = cmds.getAttr(name + ".secondTerm")
                    row["true_color"] = cmds.getAttr(name + ".colorIfTrue")[0]
                    row["false_color"] = cmds.getAttr(name + ".colorIfFalse")[0]
                elif kind == "unitConversion":
                    row["conversion_factor"] = cmds.getAttr(
                        name + ".conversionFactor")
                elif kind == "plusMinusAverage":
                    row["operation"] = cmds.getAttr(name + ".operation")
                    row["input3d"] = {str(index): cmds.getAttr(
                        f"{name}.input3D[{index}]")[0]
                        for index in (cmds.getAttr(name + ".input3D",
                            multiIndices=True) or [])}
                elif kind == "distanceBetween":
                    row["point1"] = cmds.getAttr(name + ".point1")[0]
                    row["point2"] = cmds.getAttr(name + ".point2")[0]
                nodes[name] = row
                pending.extend(pair[1] for pair in connections)
                if len(nodes) > 200:
                    raise ValueError("angle graph unexpectedly large: " + plug)
            return nodes

        rows = {}
        for side in ("R", "L"):
            for stem, attrs in ANGLES.items():
                for attr in attrs:
                    plug = f"{stem}_{side}.{attr}"
                    rows[plug] = {"value": cmds.getAttr(plug),
                                  "source_plug": (cmds.listConnections(plug,
                                      source=True, destination=False,
                                      plugs=True) or [None])[0],
                                  "joint_world_matrix": cmds.xform(
                                      f"{stem}_{side}", query=True,
                                      worldSpace=True, matrix=True),
                                  "graph": graph(plug)}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"source": scene.name,
            "angles": rows}, indent=2) + "\n", encoding="utf-8")
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
