"""Exercise Preparation / Model Check in Maya 2024."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from adv_py.adapters.maya_model_checker import MayaModelCheckHost
from adv_py.application.model_check import CheckModel


def main():
    cmds.file(new=True, force=True)
    mesh, _ = cmds.polyCube(name="CheckMesh")
    parent = cmds.group(mesh, name="MovedParent")
    cmds.setAttr(parent + ".translateY", 3)
    cmds.setAttr(mesh + ".rotatePivotX", 0.25)
    cmds.select(mesh)
    before_nodes = set(cmds.ls(long=True))
    before_modified = cmds.file(query=True, modified=True)
    result = CheckModel(MayaModelCheckHost()).execute()
    assert result.vertex_count == 8
    assert any(i.attribute == "translateY" and i.path.endswith("MovedParent")
               for i in result.transform_issues)
    assert any(i.attribute == "rotatePivotX" for i in result.transform_issues)
    assert any(i.node_type == "polyCube" for i in result.history_issues)
    assert not result.symmetry_issues, result.symmetry_issues
    assert set(cmds.ls(long=True)) == before_nodes
    assert cmds.file(query=True, modified=True) == before_modified
    shape = cmds.listRelatives(mesh, shapes=True, fullPath=True)[0]
    cmds.xform(shape + ".vtx[0]", translation=(0.0, 0.35, 0.0), relative=True,
               worldSpace=True)
    cmds.select(mesh)
    result = CheckModel(MayaModelCheckHost()).execute()
    assert result.symmetry_issues, "asymmetric cube must be reported"
    assert cmds.ls(selection=True, flatten=True), "asymmetric vertices selected"
    assert not cmds.ls("advPyModelCheck*"), "temporary sampler leaked"
    print("Model Check Maya smoke: OK")


if __name__ == "__main__":
    main()
