"""Replay measured original eyelid joint motion on a rebuilt diagnostic scene.

The motion JSON and both Maya scenes stay outside version control. This tool
isolates a rig layer's contribution; the product never reads original data.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om


def main() -> None:
    motion_path, scene, output = (Path(value).resolve()
                                  for value in sys.argv[1:4])
    layer = sys.argv[4]
    if layer not in ("Main", "Outer"):
        raise ValueError("Layer must be Main or Outer")
    motion = json.loads(motion_path.read_text(encoding="utf-8"))
    cmds.file(str(scene), open=True, force=True,
              executeScriptNodes=False)
    count = 0
    for group, row in motion["joint_groups"].items():
        if layer not in group:
            continue
        arc, side = group[:5], group[-1]
        for index, delta, opened, closed in zip(
                row["indices"], row["deltas"],
                row["open_matrices"], row["closed_matrices"]):
            name = f"{arc}Lid{layer}{index}_{side}"
            joints = cmds.ls(name, long=True, type="joint") or []
            if not joints:
                continue
            joint = joints[0]
            offset = cmds.ls(name + "Offset", long=True,
                             type="transform")[0]
            plug = offset + ".translate"
            source = cmds.connectionInfo(plug,
                                         sourceFromDestination=True)
            if not source:
                raise RuntimeError("Missing driven joint offset: " + name)
            cmds.disconnectAttr(source, plug)
            addition = cmds.createNode("plusMinusAverage",
                                       name=name + "ReferenceMotionSum")
            cmds.connectAttr(source, addition + ".input3D[0]")
            scale = cmds.createNode("multiplyDivide",
                                    name=name + "ReferenceMotionBlink")
            extra = delta if layer == "Outer" else (delta[0], 0., 0.)
            cmds.setAttr(scale + ".input2", *[value / 10.
                         for value in extra], type="double3")
            for axis in "XYZ":
                cmds.connectAttr("ctrlEye_" + side + ".blink",
                                 scale + ".input1" + axis)
            cmds.connectAttr(scale + ".output",
                             addition + ".input3D[1]")
            cmds.connectAttr(addition + ".output3D", plug)
            if layer == "Main":
                first = om.MTransformationMatrix(om.MMatrix(opened)).rotation()
                last = om.MTransformationMatrix(om.MMatrix(closed)).rotation()
                for axis in "YZ":
                    angle = (getattr(last, axis.lower()) -
                             getattr(first, axis.lower())) * 180. / 3.141592653589793
                    node = cmds.createNode("multiplyDivide",
                                           name=name + "ReferenceRotate" + axis)
                    cmds.setAttr(node + ".input2X", angle / 10.)
                    cmds.connectAttr("ctrlEye_" + side + ".blink",
                                     node + ".input1X")
                    cmds.connectAttr(node + ".outputX",
                                     joint + ".rotate" + axis)
            count += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    cmds.file(rename=str(output))
    cmds.file(save=True, type="mayaBinary", force=True)
    print("Replayed", count, layer, "joints", flush=True)


if __name__ == "__main__":
    main()
