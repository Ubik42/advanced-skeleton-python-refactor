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


def main():
    with TemporaryDirectory() as temp:
        source = Path(temp) / "model.ma"
        rig = Path(temp) / "rig.ma"
        empty = Path(temp) / "empty.ma"
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
        print("Preparation reference Maya smoke: OK")


if __name__ == "__main__":
    main()
