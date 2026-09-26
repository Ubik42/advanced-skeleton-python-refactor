"""Preparation model records on referenced meshes and FitSkeleton."""
from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds

from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost
from adv_py.application.preparation_objects import (
    RecordPreparationObjects, ReselectPreparationObjects,
)
from adv_py.application.preparation_reference import ReferencePreparationModel
from adv_py.core.preparation_objects import PreparationObjectRole as Role


def main():
    with TemporaryDirectory() as folder:
        source = Path(folder) / "model.ma"
        rig = Path(folder) / "rig.ma"
        cmds.file(new=True, force=True)
        for name in ("BodyMesh", "GarmentMesh", "RightEyeMesh", "LeftEyeMesh"):
            cmds.polyCube(name=name)
        cmds.file(rename=str(source))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(new=True, force=True)
        ReferencePreparationModel(MayaPreparationReferenceHost()).execute(source)
        host = MayaPreparationObjectsHost()
        recorder = RecordPreparationObjects(host)
        meshes = ("model:BodyMesh", "model:GarmentMesh")
        cmds.select(list(meshes), replace=True)
        skin = recorder.execute(Role.SKIN)
        assert len(skin) == 2, skin
        cmds.setAttr("AdvPy_Preparation.objectsSkin", lock=True)
        cmds.select("model:GarmentMesh", replace=True)
        try:
            recorder.execute(Role.SKIN)
        except ValueError as error:
            assert "不可写" in str(error)
        else:
            raise AssertionError("locked preparation record was overwritten")
        assert host.read_objects(Role.SKIN) == skin
        cmds.setAttr("AdvPy_Preparation.objectsSkin", lock=False)
        cmds.select("model:RightEyeMesh", "model:LeftEyeMesh", replace=True)
        try:
            recorder.execute(Role.RIGHT_EYE)
        except ValueError as error:
            assert "一个" in str(error)
        else:
            raise AssertionError("two eyes accepted as Right Eye")
        assert host.read_objects(Role.RIGHT_EYE) == ()
        for role, names in (
            (Role.ALL, ("model:BodyMesh", "model:GarmentMesh",
                        "model:RightEyeMesh", "model:LeftEyeMesh")),
            (Role.RIGHT_EYE, ("model:RightEyeMesh",)),
            (Role.LEFT_EYE, ("model:LeftEyeMesh",)),
        ):
            cmds.select(list(names), replace=True)
            assert len(recorder.execute(role)) == len(names)
        cmds.file(rename=str(rig))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(rig), open=True, force=True, executeScriptNodes=False)
        host = MayaPreparationObjectsHost()
        assert len(host.read_objects(Role.SKIN)) == 2
        assert len(host.read_objects(Role.ALL)) == 4
        ReselectPreparationObjects(host).execute(Role.RIGHT_EYE)
        assert cmds.ls(selection=True)[0] == "model:RightEyeMesh"
        cmds.createNode("transform", name="FitSkeleton")
        for role, names, attribute in (
            (Role.ALL, ("model:BodyMesh", "model:GarmentMesh",
                        "model:RightEyeMesh", "model:LeftEyeMesh"), "objectsAll"),
            (Role.RIGHT_EYE, ("model:RightEyeMesh",), "objectsRightEye"),
            (Role.LEFT_EYE, ("model:LeftEyeMesh",), "objectsLeftEye"),
        ):
            cmds.select(list(names), replace=True)
            RecordPreparationObjects(host).execute(role)
            assert cmds.getAttr("FitSkeleton." + attribute) == " ".join(names)
        cmds.select(list(meshes), replace=True)
        RecordPreparationObjects(host).execute(Role.SKIN)
        assert cmds.getAttr("FitSkeleton.objectsSkin") == " ".join(meshes)
        cmds.undo()
        assert not cmds.attributeQuery("objectsSkin", node="FitSkeleton", exists=True)
        cmds.redo()
        assert cmds.getAttr("FitSkeleton.objectsSkin") == " ".join(meshes)
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(rig), open=True, force=True, executeScriptNodes=False)
        assert len(MayaPreparationObjectsHost().read_objects(Role.SKIN)) == 2
        print("Preparation object records Maya smoke: OK")


if __name__ == "__main__":
    main()
