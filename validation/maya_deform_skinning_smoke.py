"""Verify the original Skinning panel actions in a real Maya process."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    from maya import cmds
    from adv_py.adapters.maya_deform_skinning import (
        SMOOTH_BIND_OPTIONS, select_deform_joints, set_smooth_bind_options)

    cmds.file(new=True, force=True)
    mesh = cmds.polyCube(name="BodyMesh")[0]
    cmds.select(clear=True)
    root = cmds.joint(name="Root_M")
    body = cmds.joint(name="Spine1_M")
    cmds.select(clear=True)
    eye = cmds.joint(name="Eye_R")
    cmds.sets((root, body, eye), name="DeformSet")
    cmds.select(mesh, replace=True)
    count = select_deform_joints("", ())
    selected = set(cmds.ls(selection=True, long=True) or ())
    assert count == 2
    assert set(cmds.ls((root, body, mesh), long=True) or ()) == selected
    assert eye not in " ".join(selected)
    set_smooth_bind_options(show_dialog=False)
    for name, expected in SMOOTH_BIND_OPTIONS:
        assert cmds.optionVar(query=name) == expected, name
    print("passed: deform selection, mesh preservation, excluded eye, smooth bind preferences")


if __name__ == "__main__":
    main()
