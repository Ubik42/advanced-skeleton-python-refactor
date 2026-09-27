"""Full-weight and undo acceptance for original Body Harden weights on Sam."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(scene: Path, report: Path) -> int:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from maya.api import OpenMaya as om
        from maya.api import OpenMayaAnim as oma
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        source_hash = hashlib.sha256(scene.read_bytes()).hexdigest()
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        cmds.undoInfo(state=True)
        mesh = "|Group|Geometry|model:geo|model:body"
        if not cmds.objExists(mesh):
            raise RuntimeError("公开 Sam 主体网格不存在")
        shape = cmds.listRelatives(mesh, shapes=True,
                                   noIntermediate=True, fullPath=True)[0]
        skin = (cmds.ls(cmds.listHistory(shape) or [],
                        type="skinCluster") or [])[0]
        count = int(cmds.polyEvaluate(mesh, vertex=True))

        def weights():
            selected = om.MSelectionList()
            selected.add(skin)
            skin_fn = oma.MFnSkinCluster(selected.getDependNode(0))
            selected = om.MSelectionList()
            selected.add(shape)
            dag = selected.getDagPath(0)
            component_fn = om.MFnSingleIndexedComponent()
            component = component_fn.create(om.MFn.kMeshVertComponent)
            component_fn.addElements(range(count))
            values, width = skin_fn.getWeights(dag, component)
            return tuple(values), width

        before, width = weights()
        if len(before) != count * width:
            raise RuntimeError("公开 Sam 权重矩阵维度无效")
        cmds.select(mesh, replace=True)
        changed = MayaPanelController().delta_mush_harden_weights()
        after, after_width = weights()
        strongest_preserved = all(
            after[vertex * width + max(range(width),
                key=lambda index: before[vertex * width + index])] == 1.
            for vertex in range(count))
        binary = (changed == 1 and width == after_width
                  and strongest_preserved and
                  all(value in (0., 1.) for value in after))
        cmds.undo()
        undone = weights() == (before, width)
        cmds.redo()
        redone = weights() == (after, width)
        with tempfile.TemporaryDirectory(
                prefix="adv-py-public-harden-",
                dir=report.parent.resolve()) as directory:
            saved = Path(directory) / "sam-hardened.mb"
            cmds.file(rename=str(saved))
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(saved), open=True, force=True,
                      executeScriptNodes=False)
            reopened = weights() == (after, width)
        unchanged_source = hashlib.sha256(scene.read_bytes()).hexdigest() == source_hash
        checks = {
            "strongest_influence_per_vertex": binary,
            "single_undo_redo": undone and redone,
            "save_reopen": reopened,
            "source_file_unchanged": unchanged_source,
        }
        report.write_text(json.dumps({
            **checks, "asset": scene.name, "mesh": mesh, "skin": skin,
            "vertex_count": count, "influence_count": width,
            "status": "passed" if all(checks.values()) else "failed",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
