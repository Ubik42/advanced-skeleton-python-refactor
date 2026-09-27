"""Apply the Delta Mush panel action to a public rig in an isolated scene."""
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
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        source_hash = hashlib.sha256(scene.read_bytes()).hexdigest()
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        cmds.undoInfo(state=True)
        candidates = []
        for shape in cmds.ls(type="mesh", long=True) or []:
            if cmds.getAttr(shape + ".intermediateObject"):
                continue
            parent = (cmds.listRelatives(shape, parent=True,
                                        fullPath=True) or [None])[0]
            if parent is None:
                continue
            history = cmds.listHistory(shape, pruneDagObjects=True) or []
            skins = cmds.ls(history, type="skinCluster") or []
            mush = cmds.ls(history, type="deltaMush") or []
            if len(skins) == 1 and not mush:
                candidates.append((cmds.polyEvaluate(parent, vertex=True),
                                   parent, skins[0]))
        if not candidates:
            raise RuntimeError("公开角色没有适用的单 Skin 网格")
        vertices, mesh, skin = max(candidates)
        control = next((name for name in ("FKShoulder_R.rotateX",
                                           "FKShoulder_R.rotateZ")
                        if cmds.objExists(name)
                        and cmds.getAttr(name, settable=True)), None)
        if control is None:
            raise RuntimeError("公开角色缺少可写的右肩 FK 控制")
        cmds.setAttr(control, 25.)
        def positions():
            return tuple(float(value) for value in cmds.xform(
                mesh + ".vtx[*]", query=True, worldSpace=True,
                translation=True))

        before = positions()
        cmds.select(mesh, replace=True)
        selected = tuple(cmds.ls(selection=True, long=True) or ())
        count = MayaPanelController().delta_mush_apply()
        after = positions()
        deformers = cmds.ls(cmds.listHistory(mesh) or [],
                            type="deltaMush") or []
        maximum_delta = max(abs(a - b) for a, b in zip(before, after))
        applied = (count == 1 and len(deformers) == 1
                   and maximum_delta > 1e-5
                   and selected == tuple(cmds.ls(
                       selection=True, long=True) or ()))
        cmds.undo()
        undone = (not cmds.ls(cmds.listHistory(mesh) or [],
                             type="deltaMush")
                  and max(abs(a - b) for a, b in zip(
                      before, positions())) < 1e-5)
        cmds.redo()
        redone = (len(cmds.ls(cmds.listHistory(mesh) or [],
                              type="deltaMush") or []) == 1
                  and max(abs(a - b) for a, b in zip(
                      after, positions())) < 1e-5)
        with tempfile.TemporaryDirectory(
                prefix="adv-py-public-delta-mush-",
                dir=report.parent.resolve()) as folder:
            saved = Path(folder) / "public-delta-mush.mb"
            cmds.file(rename=str(saved))
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(saved), open=True, force=True,
                      executeScriptNodes=False)
            reopened = (len(cmds.ls(cmds.listHistory(mesh) or [],
                                    type="deltaMush") or []) == 1
                and max(abs(a - b) for a, b in zip(
                    after, positions())) < 1e-5)
        unchanged_source = hashlib.sha256(scene.read_bytes()).hexdigest() == source_hash
        checks = {"public_mesh_deforms": applied,
                  "single_undo_redo": undone and redone,
                  "save_reopen": reopened,
                  "source_file_unchanged": unchanged_source}
        report.write_text(json.dumps({
            **checks, "asset": scene.name, "mesh": mesh, "skin": skin,
            "vertex_count": vertices, "posed_control": control,
            "maximum_delta_cm": maximum_delta,
            "status": "passed" if all(checks.values()) else "failed",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
