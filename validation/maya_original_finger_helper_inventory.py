"""Read-only inspection of the original finger _00 and _50 helper chain."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main(scene: Path, report: Path) -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        rows = []
        for side in ("R", "L"):
            for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
                stem = f"{finger}Finger3_{side}"
                members = {}
                for suffix in ("_00", "", "_50"):
                    name = stem + suffix
                    matches = cmds.ls(name, long=True) or []
                    if len(matches) != 1:
                        raise ValueError(f"原版手指节点缺失或重复：{name}；相近节点："
                                         f"{cmds.ls('*' + stem + '*') or []}")
                    path = matches[0]
                    members[suffix or "body"] = {
                        "path": path,
                        "type": cmds.nodeType(path),
                        "parent": (cmds.listRelatives(path, parent=True,
                            fullPath=True) or [None])[0],
                        "local_translate": cmds.getAttr(path + ".translate")[0],
                        "local_rotate": cmds.getAttr(path + ".rotate")[0],
                        "parent_world_matrix": cmds.xform(
                            (cmds.listRelatives(path, parent=True,
                                fullPath=True) or [path])[0], query=True,
                            worldSpace=True, matrix=True),
                        "world_position": cmds.xform(path, query=True,
                            worldSpace=True, translation=True),
                        "world_matrix": cmds.xform(path, query=True,
                            worldSpace=True, matrix=True),
                        "joint_orient": cmds.getAttr(path + ".jointOrient")[0]
                            if cmds.nodeType(path) == "joint" else None,
                        "inputs": {attribute: cmds.listConnections(
                            path + "." + attribute, source=True,
                            destination=False, plugs=True) or []
                            for attribute in ("translate", "rotate", "scale")},
                    }
                rows.append({"stem": stem, "members": members})
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
