"""Maya Preparation / Rig model reference smoke."""
from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost
from adv_py.application.preparation_reference import ReferencePreparationModel
from adv_py.application.preparation_reference import ManagePreparationModelReference
from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
from adv_py.application.preparation_objects import RecordPreparationObjects
from adv_py.core.preparation_objects import PreparationObjectRole


def main():
    with TemporaryDirectory() as temp:
        source = Path(temp) / "model.ma"
        rig = Path(temp) / "rig.ma"
        empty = Path(temp) / "empty.ma"
        replacement = Path(temp) / "replacement.ma"
        cmds.file(new=True, force=True)
        cmds.polyCube(name="BodyMesh")
        cmds.file(rename=str(source))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(new=True, force=True)
        cmds.file(rename=str(empty))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(new=True, force=True)
        service = ReferencePreparationModel(MayaPreparationReferenceHost())
        try:
            service.execute(empty)
        except ValueError as error:
            assert "顶层对象" in str(error)
        else:
            raise AssertionError("empty reference must fail")
        assert not cmds.ls(type="reference") or cmds.ls(type="reference") == ["sharedReferenceNode"]
        cmds.createNode("transform", name="Hi")
        try:
            service.execute(source)
        except ValueError as error:
            assert "Hi" in str(error)
        else:
            raise AssertionError("non-layer Hi must reject reference")
        assert not cmds.objExists("model:BodyMesh")
        cmds.delete("Hi")
        result = service.execute(source)
        assert result.namespace == "model", result
        assert len(result.top_nodes) == 1, result
        assert cmds.objExists("model:BodyMesh")
        assert cmds.objExists("Hi")
        assert cmds.getAttr("Hi.displayType") == 1
        assert "model:BodyMesh" in " ".join(cmds.editDisplayLayerMembers(
            "Hi", query=True) or ())
        assert cmds.referenceQuery(result.reference_node, isLoaded=True)
        second = service.execute(source)
        assert second.namespace == "model1"
        assert cmds.objExists("model1:BodyMesh")
        cmds.file(rename=str(rig))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(new=True, force=True)
        cmds.file(str(rig), open=True, force=True, executeScriptNodes=False)
        assert cmds.objExists("model:BodyMesh")
        assert cmds.referenceQuery("model:BodyMesh", isNodeReferenced=True)
        assert cmds.objExists("model1:BodyMesh")
        assert cmds.objExists("Hi")
        assert "model:BodyMesh" in " ".join(cmds.editDisplayLayerMembers(
            "Hi", query=True) or ())
        cmds.file(str(source), open=True, force=True, executeScriptNodes=False)
        cmds.polyCube(name="AccessoryMesh")
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(rig), open=True, force=True, executeScriptNodes=False)
        assert cmds.objExists("model:AccessoryMesh")
        assert cmds.objExists("model1:AccessoryMesh")
        manager = ManagePreparationModelReference(MayaPreparationReferenceHost())
        assert manager.reload("model").namespace == "model"
        cmds.select("model:BodyMesh", "model1:BodyMesh", replace=True)
        recorded = RecordPreparationObjects(MayaPreparationObjectsHost()).execute(
            PreparationObjectRole.SKIN)
        assert len(recorded) == 2
        cmds.file(save=True, type="mayaAscii")

        cmds.file(new=True, force=True)
        cmds.polyCube(name="BodyMesh")
        cmds.polySphere(name="NewHat")
        cmds.file(rename=str(replacement))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(rig), open=True, force=True, executeScriptNodes=False)
        replaced = manager.replace("model1", replacement)
        assert replaced.source == replacement.resolve(), replaced
        assert cmds.objExists("model1:NewHat")
        assert not cmds.objExists("model1:AccessoryMesh")
        kept = MayaPreparationObjectsHost().read_objects(PreparationObjectRole.SKIN)
        assert len(kept) == 2, (kept, cmds.getAttr(
            "AdvPy_Preparation.objectsSkin"), cmds.objExists("model1:BodyMesh"))
        try:
            manager.replace("model1", empty)
        except ValueError as error:
            assert "顶层" in str(error), error
        else:
            raise AssertionError("Empty replacement must roll back")
        assert cmds.objExists("model1:BodyMesh")
        assert manager.reload("model1").source == replacement.resolve()
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(rig), open=True, force=True, executeScriptNodes=False)
        assert cmds.objExists("model1:NewHat")

        removed = manager.remove("model1")
        assert removed.namespace == "model1"
        assert not cmds.objExists("model1:BodyMesh")
        assert MayaPreparationObjectsHost().read_objects(
            PreparationObjectRole.SKIN) == ("|model:BodyMesh",)
        assert cmds.objExists("model:BodyMesh")
        cmds.select(clear=True)
        joint = cmds.joint(name="BodyJoint")
        cmds.skinCluster(joint, "model:BodyMesh", name="ProtectedSkin")
        for action in (lambda: manager.remove("model"),
                       lambda: manager.replace("model", replacement)):
            try:
                action()
            except ValueError as error:
                assert "Skin" in str(error), error
            else:
                raise AssertionError("Bound model reference must be protected")
        assert cmds.objExists("model:BodyMesh")
        assert manager.reload("model").namespace == "model"
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(rig), open=True, force=True, executeScriptNodes=False)
        assert cmds.objExists("ProtectedSkin")
        assert not cmds.objExists("model1:BodyMesh")
        print("Preparation reference Maya smoke: OK")


if __name__ == "__main__":
    main()
