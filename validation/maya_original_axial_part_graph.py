"""Read-only axial Part and intermediate FK/IK driver inventory."""
from __future__ import annotations

import json
from pathlib import Path
import sys


PARTS = ("RootPart1_M", "RootPart2_M", "Spine1Part1_M",
         "Spine1Part2_M", "NeckPart1_M", "NeckPart2_M")


def main(scene: Path, report: Path) -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        rows = {}
        names = set(PARTS)
        for part in PARTS:
            names.add("FKX" + part)
            names.add("IKX" + part)
            names.add("FK" + part)
            names.add("FKExtra" + part)
        names.update(("FKRoot_M", "FKSpine1_M", "FKNeck_M"))
        for stem in ("Root", "Spine1", "Neck"):
            names.update((f"InbetweenBase{stem}_M",
                          f"InbetweenTarget{stem}_M"))
        for part in PARTS:
            paths = cmds.ls("FKX" + part, long=True) or []
            if len(paths) == 1:
                for ancestor in paths[0].split("|")[1:-1]:
                    if ancestor.startswith("FK"):
                        names.add(ancestor)
        for name in sorted(names):
            paths = cmds.ls(name, long=True) or []
            if len(paths) != 1:
                continue
            path = paths[0]
            inputs = {}
            for attr in ("translate", "rotate", "scale", "jointOrient"):
                if not cmds.attributeQuery(attr, node=path, exists=True):
                    continue
                plugs = []
                for plug in (path + "." + attr,
                             *(path + "." + child for child in
                               (cmds.attributeQuery(attr, node=path,
                                                    listChildren=True) or []))):
                    plugs.extend(cmds.listConnections(
                        plug, source=True, destination=False, plugs=True,
                        skipConversionNodes=False) or [])
                if plugs:
                    inputs[attr] = sorted(set(plugs))
            constraints = []
            for node in sorted({plug.split(".", 1)[0]
                                for plugs in inputs.values() for plug in plugs}):
                kind = cmds.nodeType(node)
                query = {"pointConstraint": cmds.pointConstraint,
                         "orientConstraint": cmds.orientConstraint,
                         "parentConstraint": cmds.parentConstraint}.get(kind)
                if query:
                    aliases = query(node, query=True, weightAliasList=True) or []
                    constraints.append({"name": node, "type": kind,
                        "targets": query(node, query=True, targetList=True) or [],
                        "weights": [cmds.getAttr(node + "." + alias)
                                    for alias in aliases]})
            rows[name] = {
                "type": cmds.nodeType(path), "path": path,
                "parent": (cmds.listRelatives(path, parent=True,
                                               fullPath=True) or [None])[0],
                "world_matrix": cmds.xform(path, query=True,
                                            worldSpace=True, matrix=True),
                "translate": cmds.getAttr(path + ".translate")[0],
                "rotate": cmds.getAttr(path + ".rotate")[0],
                "scale": cmds.getAttr(path + ".scale")[0],
                "joint_orient": (cmds.getAttr(path + ".jointOrient")[0]
                                 if cmds.nodeType(path) == "joint" else None),
                "rotate_order": cmds.getAttr(path + ".rotateOrder"),
                "inputs": inputs, "constraints": constraints,
            }
        drivers = {}
        for part in PARTS:
            for suffix in ("InbetweenDM_M", "InbetweenMM_M",
                           "InbetweenBM_M", "HSMM_M"):
                name = part.replace("_M", suffix)
                if not cmds.objExists(name):
                    continue
                plugs = cmds.listConnections(name, source=True,
                    destination=False, connections=True, plugs=True) or []
                drivers[name] = {"type": cmds.nodeType(name),
                    "connections": list(zip(plugs[::2], plugs[1::2])),
                }
        for stem in ("Root", "Spine1", "Neck"):
            for position in ("Mid", "End"):
                name = f"FK{stem}{position}BiasRV_M"
                plugs = cmds.listConnections(name, source=True,
                    destination=False, connections=True, plugs=True) or []
                drivers[name] = {"type": cmds.nodeType(name),
                    "connections": list(zip(plugs[::2], plugs[1::2])),
                    "out_value": cmds.getAttr(name + ".outValue")}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"source": scene.name, "nodes": rows,
                                      "drivers": drivers},
                                     indent=2) + "\n", encoding="utf-8")
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
