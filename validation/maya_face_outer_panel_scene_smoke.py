"""Verify Main/Outer panel edits on a saved eyelid rig."""
from __future__ import annotations

import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds

from adv_py.product.maya_panel_controller import MayaPanelController


def main() -> None:
    source, output = (Path(value).resolve() for value in sys.argv[1:3])
    cmds.file(str(source), open=True, force=True, executeScriptNodes=False)
    panel = MayaPanelController()
    side, arc = "Right", "upper"
    old = panel.face_outer_blink_read(":", side, arc)
    target = (old[0] + .02, old[1] - .03, old[2] + .01)
    control = "ctrlUpperEyeLidOuter_R"
    joints = sorted(cmds.ls("upperLidOuter*_R", type="joint") or [])
    assert joints
    joint = joints[len(joints) // 2]
    cmds.setAttr("ctrlEye_R.blink", 10)
    before = cmds.xform(joint, query=True, worldSpace=True,
                        translation=True)
    assert panel.face_outer_blink_apply(":", side, arc, target) == target
    after = cmds.xform(joint, query=True, worldSpace=True,
                       translation=True)
    assert max(abs(a-b) for a, b in zip(after, before)) > 1e-6
    cmds.undo()
    assert panel.face_outer_blink_read(":", side, arc) == old
    cmds.redo()
    assert panel.face_outer_blink_read(":", side, arc) == target
    main_old = panel.face_lid_blink_read(":", side, "Main", arc)
    main_joints = sorted(cmds.ls("upperLidMain*_R", type="joint") or [])
    assert main_joints
    main_joint = main_joints[len(main_joints) // 2]
    main_before = cmds.xform(main_joint, query=True, worldSpace=True,
                             translation=True)
    main_target = (main_old[0] + .01, main_old[1] + .02,
                   main_old[2] - .03)
    assert panel.face_lid_blink_apply(":", side, "Main", arc,
                                      main_target) == main_target
    main_after = cmds.xform(main_joint, query=True, worldSpace=True,
                            translation=True)
    assert max(abs(a-b) for a, b in zip(main_before, main_after)) > 1e-6
    cmds.undo()
    assert panel.face_lid_blink_read(":", side, "Main", arc) == main_old
    cmds.redo()
    assert panel.face_lid_blink_read(":", side, "Main", arc) == main_target
    try:
        panel.face_outer_blink_apply(":", side, arc,
                                     (math.nan, 0., 0.))
    except ValueError:
        pass
    else:
        raise AssertionError("NaN Outer offset was accepted")
    assert panel.face_outer_blink_read(":", side, arc) == target
    cmds.setAttr(control + ".blinkOffsetX", lock=True)
    try:
        panel.face_outer_blink_apply(":", side, arc, (1., 2., 3.))
    except ValueError:
        pass
    else:
        raise AssertionError("Locked Outer offset was accepted")
    assert panel.face_outer_blink_read(":", side, arc) == target
    cmds.setAttr(control + ".blinkOffsetX", lock=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    cmds.file(rename=str(output))
    cmds.file(save=True, type="mayaBinary", force=True)
    cmds.file(str(output), open=True, force=True, executeScriptNodes=False)
    assert panel.face_outer_blink_read(":", side, arc) == target
    assert panel.face_lid_blink_read(":", side, "Main", arc) == main_target
    print("Main/Outer blink panel controller Undo/Redo/reopen: OK",
          flush=True)


if __name__ == "__main__":
    main()
