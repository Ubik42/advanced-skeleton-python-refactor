"""Read the upstream Maya dependency graph of original weighted Part joints."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys


PART = re.compile(r"(?:Root|Spine\d*|Neck|Hip|Shoulder|Elbow)Part[12]_[RLM]$")


def main(scene: Path, report: Path) -> int:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        cmds.file(new=True, force=True)
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        skins = cmds.ls(type="skinCluster") or []
        if len(skins) != 1:
            raise ValueError("源场景需要唯一 skinCluster")
        influences = cmds.skinCluster(skins[0], query=True,
                                      influence=True) or []
        parts = [name for name in influences if PART.search(name)]
        graph = {}
        frontier = {plug.split(".", 1)[0] for name in parts
                    for plug in (cmds.listConnections(name,
                        source=True, destination=False, plugs=True) or [])}
        for _ in range(3):
            following = set()
            for node in sorted(frontier):
                if node in graph or not cmds.objExists(node):
                    continue
                pairs = cmds.listConnections(node, source=True,
                    destination=False, plugs=True, connections=True,
                    skipConversionNodes=False) or []
                inputs = sorted((pairs[i], pairs[i + 1])
                                for i in range(0, len(pairs), 2))
                graph[node] = {"type": cmds.nodeType(node),
                               "inputs": inputs}
                following.update(plug.split(".", 1)[0]
                                 for _, plug in inputs)
            frontier = following
        data = {"source": scene.name, "part_joints": parts,
                "nodes": graph}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, ensure_ascii=False,
                                     indent=2) + "\n", encoding="utf-8")
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
