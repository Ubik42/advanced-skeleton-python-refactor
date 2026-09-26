"""Observe how Maya keeps Skin when a referenced source model changes."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds


def state():
    mesh = "model:BodyMesh"
    shape = (cmds.listRelatives(mesh, shapes=True, noIntermediate=True,
                                fullPath=True, type="mesh") or [None])[0]
    skins = cmds.ls(type="skinCluster") or []
    return {"vertices": cmds.polyEvaluate(mesh, vertex=True),
            "faces": cmds.polyEvaluate(mesh, face=True),
            "point0": tuple(cmds.pointPosition(mesh + ".vtx[0]", world=True)),
            "skin_count": len(skins),
            "visible_shape": shape,
            "skin_geometry": cmds.skinCluster("AdvPy_BodySkin", query=True,
                                                geometry=True) or []}


def main(rig_source: Path, result_path: Path):
    with TemporaryDirectory(prefix="advpy-ref-update-") as folder:
        folder = Path(folder)
        model = folder / "model.mb"
        rig = folder / "rig.mb"
        original_model = rig_source.parent / "model.mb"
        shutil.copy2(original_model, model)
        cmds.file(str(rig_source), open=True, force=True,
                  executeScriptNodes=False)
        reference = cmds.referenceQuery("model:BodyMesh", referenceNode=True)
        cmds.file(str(model), loadReference=reference)
        cmds.file(rename=str(rig))
        cmds.file(save=True, type="mayaBinary", force=True)
        before = state()

        cmds.file(str(model), open=True, force=True,
                  executeScriptNodes=False)
        cmds.move(0, 0, 1, "BodyMesh.vtx[0]", relative=True, worldSpace=True)
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(rig), open=True, force=True,
                  executeScriptNodes=False)
        moved = state()

        cmds.file(str(model), open=True, force=True,
                  executeScriptNodes=False)
        cmds.polySubdivideFacet("BodyMesh.f[0]", divisions=1)
        cmds.delete("BodyMesh", constructionHistory=True)
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(rig), open=True, force=True,
                  executeScriptNodes=False)
        changed = state()
        result = {"before": before, "same_topology_edit": moved,
                  "changed_topology": changed}
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2)
                               + "\n", encoding="utf-8")
        print(json.dumps({label: {"vertices": row["vertices"],
                                  "skin_count": row["skin_count"]}
                          for label, row in result.items()}))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
