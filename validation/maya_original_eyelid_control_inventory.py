"""Read original blink-driven lid controls and face scale without edits."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds


def main() -> None:
    source, output = (Path(value).resolve() for value in sys.argv[1:3])
    cmds.file(str(source), open=True, force=True,
              executeScriptNodes=False)
    scales = {}
    for node in ("FaceFitSkeleton", "FaceMotionSystem", "LidSetup_R",
                 "LidSetup_L", "EyeRegion_R", "EyeRegion_L",
                 "FitEyeBall", "FitEyeBallLeft", "Eye_R", "Eye_L",
                 "AdvPy_Eye_R", "AdvPy_Eye_L"):
        if not cmds.objExists(node):
            continue
        scales[node] = {
            "scale": cmds.getAttr(node + ".scale")[0],
            "face_scale": (cmds.getAttr(node + ".faceScale")
                           if cmds.attributeQuery("faceScale", node=node,
                                                  exists=True) else None),
        }
    poses = {}
    for value in (0, 10):
        for eye in ("ctrlEye_R", "ctrlEye_L"):
            cmds.setAttr(eye + ".blink", value)
        rows = {}
        for side in ("R", "L"):
            for arc in ("upper", "lower"):
                for layer in ("", "Outer"):
                    control = arc + "Lid" + layer + "_" + side
                    for name in (control, "SDK" + control,
                                 control.removesuffix("_" + side) +
                                 "Follow_" + side):
                        if not cmds.objExists(name):
                            continue
                        rows[name] = {
                            "translate": cmds.getAttr(name + ".translate")[0],
                            "world_position": cmds.xform(name, query=True,
                                                          worldSpace=True,
                                                          translation=True),
                            "world_matrix": cmds.xform(name, query=True,
                                                        worldSpace=True,
                                                        matrix=True),
                            "parent": cmds.listRelatives(name, parent=True)
                                      or [],
                        }
        poses[str(value)] = rows
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"scales": scales, "poses": poses},
                                 ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("Read", len(poses["0"]), "lid controls", flush=True)


if __name__ == "__main__":
    main()
