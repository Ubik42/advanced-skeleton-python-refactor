"""Preparation Skin + All to a referenced two-mesh one-joint prop."""
from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds

from adv_py.adapters.maya_one_joint_prop import MayaOneJointPropHost
from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost
from adv_py.application.one_joint_prop import BuildOneJointProp
from adv_py.application.preparation_objects import RecordPreparationObjects
from adv_py.application.preparation_reference import ReferencePreparationModel
from adv_py.core.preparation_objects import PreparationObjectRole
from adv_py.product.maya_panel_controller import MayaPanelController


def main() -> None:
    with TemporaryDirectory(prefix="advpy-prop-") as folder:
        folder = Path(folder)
        model = folder / "prop.mb"
        rig = folder / "prop-rig.mb"
        cmds.file(new=True, force=True)
        cmds.polyCube(name="BodyMesh", width=2, height=2, depth=2)
        cmds.polySphere(name="AccessoryMesh", radius=.25)
        cmds.move(0, 1.5, 0, "AccessoryMesh")
        cmds.file(rename=str(model))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(new=True, force=True)
        ReferencePreparationModel(MayaPreparationReferenceHost()).execute(model)
        storage = MayaPreparationObjectsHost()
        cmds.select("model:BodyMesh", replace=True)
        skin = RecordPreparationObjects(storage).execute(PreparationObjectRole.SKIN)
        cmds.select("model:BodyMesh", "model:AccessoryMesh", replace=True)
        all_meshes = RecordPreparationObjects(storage).execute(
            PreparationObjectRole.ALL)
        def fault(stage):
            if stage == "skins-bound":
                raise RuntimeError("injected")
        try:
            BuildOneJointProp(MayaOneJointPropHost()).apply(
                skin, all_meshes, on_stage=fault)
        except RuntimeError as error:
            assert str(error) == "injected", error
        else:
            raise AssertionError("injected failure must roll back")
        assert not cmds.objExists("Root_M")
        assert not cmds.ls(type="skinCluster")
        assert storage.read_objects(PreparationObjectRole.SKIN) == skin
        cmds.undoInfo(state=True)
        result = MayaPanelController().preparation_one_joint_prop(":")
        assert len(result.meshes) == len(result.skins) == 2, result
        assert cmds.objExists("|FitSkeleton|Root")
        assert cmds.getAttr("FitSkeleton.objectsSkin") == "model:BodyMesh"
        assert cmds.getAttr("FitSkeleton.objectsAll") == (
            "model:BodyMesh model:AccessoryMesh")
        assert tuple(round(value) for value in cmds.getAttr(
            "Root.jointOrient")[0]) == (90, 0, 90)
        assert cmds.objExists("|Group|Rig|Root_M")
        assert cmds.objExists("|Group|Main")
        assert len(cmds.ls(type="skinCluster") or []) == 2
        assert cmds.referenceQuery("model:BodyMesh", isNodeReferenced=True)
        points = tuple(cmds.pointPosition(mesh + ".vtx[0]", world=True)
                       for mesh in ("model:BodyMesh", "model:AccessoryMesh"))
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr("Main.translateX", 2)
        moved = tuple(cmds.pointPosition(mesh + ".vtx[0]", world=True)
                      for mesh in ("model:BodyMesh", "model:AccessoryMesh"))
        assert all(abs(b[0] - a[0] - 2) < 1e-5
                   for a, b in zip(points, moved)), (points, moved)
        cmds.setAttr("Main.translateX", 0)
        cmds.undoInfo(stateWithoutFlush=True)
        cmds.undo()
        assert not cmds.objExists("Root_M")
        assert not cmds.ls(type="skinCluster")
        cmds.redo()
        assert cmds.objExists("Root_M")
        assert len(cmds.ls(type="skinCluster") or []) == 2
        cmds.file(rename=str(rig))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(rig), open=True, force=True, executeScriptNodes=False)
        assert len(cmds.ls(type="skinCluster") or []) == 2
        assert cmds.objExists("model:AccessoryMesh")
        assert cmds.objExists("Root_M")
        print("One Joint Prop Skin + All Maya smoke: OK")


if __name__ == "__main__":
    main()
