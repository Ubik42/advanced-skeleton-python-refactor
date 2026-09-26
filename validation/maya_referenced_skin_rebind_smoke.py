"""Rebind a referenced mesh after a same-vertex-count topology edit."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds

from adv_py.adapters.maya_face import MayaFaceHost
from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
from adv_py.application.skin_rebind import RebindSkinFromSurfaceSource
from adv_py.application.skin_weight_surface_transfer import CaptureSkinWeightSurfaceSource
from adv_py.core.skin_weights import SkinWeightValidationError


def main(rig_source: Path, result_path: Path) -> None:
    with TemporaryDirectory(prefix="advpy-rebind-") as folder:
        folder = Path(folder)
        model = folder / "model.mb"
        rig = folder / "rig.mb"
        shutil.copy2(rig_source.parent / "model.mb", model)
        cmds.file(str(rig_source), open=True, force=True,
                  executeScriptNodes=False)
        reference = cmds.referenceQuery("model:BodyMesh", referenceNode=True)
        cmds.file(str(model), loadReference=reference)
        cmds.file(rename=str(rig))
        cmds.file(save=True, type="mayaBinary", force=True)
        skin = "AdvPy_BodySkin"
        mesh = "|model:BodyMesh"
        source = CaptureSkinWeightSurfaceSource(MayaFaceHost()).execute(skin, mesh)
        before = MayaDenseSkinHost().capture_dense_skin(skin)

        cmds.file(str(model), open=True, force=True,
                  executeScriptNodes=False)
        cmds.polyTriangulate("BodyMesh.f[0]")
        cmds.delete("BodyMesh", constructionHistory=True)
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(rig), open=True, force=True,
                  executeScriptNodes=False)
        try:
            MayaDenseSkinHost().capture_dense_skin(skin)
        except ValueError as error:
            assert "拓扑" in str(error), error
        else:
            raise AssertionError("Old Skin was not rejected")

        cmds.undoInfo(state=True)
        result = RebindSkinFromSurfaceSource(MayaFaceHost()).apply(
            source, skin, mesh, max_distance=.01)
        after = MayaDenseSkinHost().capture_dense_skin(skin)
        assert result.vertices == 18151, result
        assert after.vertex_count == before.vertex_count
        assert len(after.influence_names) == len(before.influence_names)
        assert cmds.referenceQuery("model:BodyMesh", isNodeReferenced=True)
        cmds.undo()
        try:
            MayaDenseSkinHost().capture_dense_skin(skin)
        except ValueError as error:
            assert "拓扑" in str(error), error
        else:
            raise AssertionError("Undo did not restore stale Skin")
        cmds.redo()
        redone = MayaDenseSkinHost().capture_dense_skin(skin)
        assert redone == after
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(rig), open=True, force=True,
                  executeScriptNodes=False)
        reopened = MayaDenseSkinHost().capture_dense_skin(skin)
        assert reopened == after
        shutil.copy2(rig_source.parent / "model.mb", model)
        cmds.file(str(model), open=True, force=True,
                  executeScriptNodes=False)
        cmds.polySubdivideFacet("BodyMesh.f[0]", divisions=1)
        cmds.delete("BodyMesh", constructionHistory=True)
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(rig), open=True, force=True,
                  executeScriptNodes=False)
        try:
            RebindSkinFromSurfaceSource(MayaFaceHost()).apply(
                source, skin, mesh, max_distance=.01,
                max_discarded_weight=0.0)
        except SkinWeightValidationError:
            pass
        else:
            raise AssertionError("Strict transfer should have failed")
        assert len(cmds.ls(type="skinCluster") or []) == 2
        try:
            MayaDenseSkinHost().capture_dense_skin(skin)
        except ValueError as error:
            assert "拓扑" in str(error), error
        else:
            raise AssertionError("Failed transfer did not roll back")
        expanded = RebindSkinFromSurfaceSource(MayaFaceHost()).apply(
            source, skin, mesh, max_distance=.01,
            max_discarded_weight=.000001)
        expanded_weights = MayaDenseSkinHost().capture_dense_skin(skin)
        assert expanded.vertices == 18156, expanded
        assert expanded_weights.vertex_count == expanded.vertices
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(rig), open=True, force=True,
                  executeScriptNodes=False)
        assert MayaDenseSkinHost().capture_dense_skin(skin) == expanded_weights
        output = {"passed": True, "vertices": result.vertices,
                  "changed_vertices": result.changed_vertices,
                  "maximum_distance": result.maximum_distance,
                  "source_influences": len(before.influence_names),
                  "reopened_influences": len(reopened.influence_names),
                  "expanded_vertices": expanded.vertices,
                  "expanded_changed_vertices": expanded.changed_vertices,
                  "failed_transfer_rolled_back": True,
                  "undo_redo": True, "referenced": True}
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2)
                               + "\n", encoding="utf-8")
        print(json.dumps(output))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
