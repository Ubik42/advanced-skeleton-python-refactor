"""Read original eyelid aim transforms at open and closed poses."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds


def main() -> None:
    scene, output = map(Path, sys.argv[1:3])
    cmds.file(str(scene.resolve()), open=True, force=True,
              executeScriptNodes=False)
    rows = {}
    for side in ("R", "L"):
        for arc in ("upper", "lower"):
            candidates = sorted(cmds.ls(arc + "LidMain*_%s" % side,
                                             type="joint") or [],
                                key=lambda item: int(item.removeprefix(
                                    arc + "LidMain").split("_")[0]))
            if not candidates:
                continue
            name = candidates[len(candidates) // 2]
            index = name.removeprefix(arc + "LidMain").split("_")[0]
            prefix = arc + "LidMain" + index
            group = {}
            for blink in (0, 10):
                for control in ("ctrlEye_R", "ctrlEye_L"):
                    cmds.setAttr(control + ".blink", blink)
                entry = {}
                for label, node in {
                        "eye_region": "EyeRegion_" + side,
                        "lid_setup": "LidSetup_" + side,
                        "loc": arc + "LidMainLoc" + index + "_" + side,
                        "aim": prefix + "Aim_" + side,
                        "aim_end": prefix + "AimEnd_" + side,
                        "joint": name,
                }.items():
                    if not cmds.objExists(node):
                        entry[label] = None
                        continue
                    entry[label] = {
                        "world_position": cmds.xform(node, query=True,
                                                      worldSpace=True,
                                                      translation=True),
                        "world_matrix": cmds.xform(node, query=True,
                                                    worldSpace=True,
                                                    matrix=True),
                        "local_position": cmds.getAttr(node + ".translate")[0],
                    }
                group[str(blink)] = entry
            rows[name] = group
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("Read", len(rows), "eyelid aim groups", flush=True)


if __name__ == "__main__":
    main()
