"""Tune the exposed Outer blink pose and verify Maya persistence and undo."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds


def main() -> None:
    source, profile, output = (Path(value).resolve()
                               for value in sys.argv[1:4])
    motion = json.loads(profile.read_text(encoding="utf-8"))
    cmds.file(str(source), open=True, force=True,
              executeScriptNodes=False)
    controls = {}
    for side in ("R", "L"):
        for arc in ("upper", "lower"):
            group = arc + "Outer" + side
            row = motion["joint_groups"][group]
            delta = row["middle_delta"]
            name = ("ctrlUpper" if arc == "upper" else "ctrlLower") + \
                   "EyeLidOuter_" + side
            controls[name] = tuple(delta)
            for axis in "XYZ":
                if not cmds.attributeQuery("blinkOffset" + axis,
                                           node=name, exists=True):
                    raise RuntimeError("Outer blink correction missing: " + name)
    upper_left = motion["joint_groups"]["upperOuterL"]
    first = "upperLidOuter" + str(upper_left["indices"][
        len(upper_left["indices"]) // 2]) + "_L"
    cmds.setAttr("ctrlEye_R.blink", 10)
    cmds.setAttr("ctrlEye_L.blink", 10)
    initial = cmds.xform(first, query=True, worldSpace=True,
                         translation=True)
    cmds.undoInfo(openChunk=True, chunkName="Tune Outer blink")
    try:
        for name, delta in controls.items():
            for axis, value in zip("XYZ", delta):
                cmds.setAttr(name + ".blinkOffset" + axis, value)
    finally:
        cmds.undoInfo(closeChunk=True)
    tuned = cmds.xform(first, query=True, worldSpace=True,
                       translation=True)
    if sum((a-b)**2 for a,b in zip(initial, tuned)) <= 1e-8:
        raise AssertionError("Outer correction did not move the joint")
    cmds.undo()
    if any(abs(cmds.getAttr(name + ".blinkOffset" + axis)) > 1e-9
           for name in controls for axis in "XYZ"):
        raise AssertionError("Outer blink tuning did not undo")
    cmds.redo()
    if any(abs(cmds.getAttr(name + ".blinkOffset" + axis) - value) > 1e-9
           for name, delta in controls.items()
           for axis, value in zip("XYZ", delta)):
        raise AssertionError("Outer blink tuning did not redo")
    output.parent.mkdir(parents=True, exist_ok=True)
    cmds.file(rename=str(output))
    cmds.file(save=True, type="mayaBinary", force=True)
    cmds.file(str(output), open=True, force=True,
              executeScriptNodes=False)
    cmds.setAttr("ctrlEye_L.blink", 10)
    reopened = cmds.xform(first, query=True, worldSpace=True,
                          translation=True)
    if max(abs(a-b) for a,b in zip(tuned, reopened)) > 1e-5:
        raise AssertionError("Outer correction changed after reopening")
    print("Outer blink tuning, Undo/Redo and reopen: OK", flush=True)


if __name__ == "__main__":
    main()
