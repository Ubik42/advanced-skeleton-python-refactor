"""Reference two model meshes, record Skin and build one complete Body."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds

from adv_py.adapters.maya_body import MayaBodyBuildHost
from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost
from adv_py.application.preparation_objects import RecordPreparationObjects
from adv_py.application.preparation_reference import ReferencePreparationModel
from adv_py.application.registered_skinned_body_build import (
    BuildRegisteredSkinnedBodyCharacter,
)
from adv_py.core.preparation_objects import PreparationObjectRole
from adv_py.product.maya_panel_controller import MayaPanelController


def main(source: Path):
    with TemporaryDirectory(prefix="advpy-prep-body-") as folder:
        folder = Path(folder)
        model = folder / "model.mb"
        rig = folder / "rig.mb"
        cmds.file(str(source.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        cmds.select("|BodyMesh", "|GarmentMesh", replace=True)
        cmds.file(str(model), exportSelected=True, type="mayaBinary", force=True)
        model_digest = sha256(model.read_bytes()).hexdigest()
        cmds.delete("|BodyMesh", "|GarmentMesh")
        ReferencePreparationModel(MayaPreparationReferenceHost()).execute(model)
        cmds.select("model:BodyMesh", "model:GarmentMesh", replace=True)
        host = MayaPreparationObjectsHost()
        meshes = RecordPreparationObjects(host).execute(PreparationObjectRole.SKIN)
        assert len(meshes) == 2
        assert cmds.getAttr("FitSkeleton.objectsSkin") == (
            "model:BodyMesh model:GarmentMesh")
        cmds.undoInfo(state=True)

        def fault(stage):
            if stage == "skins-bound":
                raise RuntimeError("injected failure")

        try:
            BuildRegisteredSkinnedBodyCharacter(MayaBodyBuildHost()).apply(
                meshes, infer_missing_labels=True, on_stage=fault)
        except RuntimeError as error:
            assert str(error) == "injected failure", error
        else:
            raise AssertionError("injected build failure did not propagate")
        assert not cmds.objExists("Root_M")
        assert not (cmds.ls(type="skinCluster") or [])
        assert all(cmds.referenceQuery(mesh, isNodeReferenced=True)
                   for mesh in meshes)
        print("Referenced build rollback: OK", flush=True)

        built = MayaPanelController().body_build(":", meshes=meshes,
            infer_missing_labels=True)
        assert built.joint_count == 74
        skins = cmds.ls(type="skinCluster") or []
        assert len(skins) == 2, skins
        assert all(cmds.referenceQuery(mesh, isNodeReferenced=True)
                   for mesh in meshes)
        before = tuple(cmds.pointPosition(mesh + ".vtx[0]", world=True)
                       for mesh in meshes)
        cmds.setAttr("AdvPy_Global.translateX", 2)
        after = tuple(cmds.pointPosition(mesh + ".vtx[0]", world=True)
                      for mesh in meshes)
        assert all(abs(a[0] - b[0]) > 1.9 for a, b in zip(after, before))
        cmds.setAttr("AdvPy_Global.translateX", 0)
        cmds.undo()
        cmds.undo()
        cmds.undo()
        assert not cmds.objExists("Root_M")
        assert not (cmds.ls(type="skinCluster") or [])
        cmds.redo()
        assert len(cmds.ls(type="skinCluster") or []) == 2
        cmds.file(rename=str(rig))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(rig), open=True, force=True, executeScriptNodes=False)
        assert len(cmds.ls(type="skinCluster") or []) == 2
        assert len(MayaPreparationObjectsHost().read_objects(
            PreparationObjectRole.SKIN)) == 2
        cmds.setKeyframe("AdvPy_Global.translateX", time=1, value=0)
        cmds.setKeyframe("AdvPy_Global.translateX", time=5, value=2)
        fbx = folder / "rig.fbx"
        publication = MayaPanelController().publish_fbx(":", fbx,
            start=1, end=5, include_skins=True)
        assert publication.bytes_written > 0 and fbx.is_file()
        assert sha256(model.read_bytes()).hexdigest() == model_digest
        cmds.file(new=True, force=True)
        cmds.file(str(fbx), i=True, type="FBX", ignoreVersion=True,
                  executeScriptNodes=False)
        assert len(cmds.ls(type="skinCluster") or []) == 2
        assert len(cmds.ls(type="joint") or []) == 75
        print("Preparation reference to skinned Body: OK", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
