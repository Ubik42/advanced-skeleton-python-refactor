"""Migrate a second mesh skinned to the same original character rig."""
from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _points(mesh: str):
    from maya.api import OpenMaya as om
    selection = om.MSelectionList()
    selection.add(mesh)
    dag = selection.getDagPath(0)
    if dag.apiType() == om.MFn.kTransform:
        dag.extendToShape()
    return tuple(tuple(float(value) for value in point)
                 for point in om.MFnMesh(dag).getPoints(om.MSpace.kWorld))


def main(scene: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
        from adv_py.adapters.maya_original_skin_migration import (
            MayaOriginalSkinMigration)

        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        cmds.undoInfo(state=True)
        primary_skin = (cmds.ls(type="skinCluster") or [])[0]
        primary_before = MayaDenseSkinHost().capture_dense_skin(primary_skin)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
        garment = cmds.polyCube(name="GarmentMesh", width=1.0,
                                height=1.5, depth=.5)[0]
        cmds.xform(garment, worldSpace=True, translation=(.5, 7.0, 0.0))
        garment_skin = cmds.skinCluster("Root_M", "Hip_R",
            garment, name="GarmentSkin", maximumInfluences=2, toSelectedBones=True)[0]
        garment_before = MayaDenseSkinHost().capture_dense_skin(
            garment_skin)
        cmds.setAttr("FKRoot_M.rotateY", 20.0)
        source_pose = _points(garment)
        cmds.setAttr("FKRoot_M.rotateY", 0.0)
        operation = MayaOriginalSkinMigration()

        def fault(stage):
            if stage == "weights-copied":
                raise RuntimeError("injected second-skin fault")
        try:
            operation.apply(source_skin=primary_skin, on_stage=fault)
        except RuntimeError as error:
            fault_rolled_back = (
                str(error) == "injected second-skin fault"
                and MayaDenseSkinHost().capture_dense_skin(primary_skin)
                    == primary_before
                and MayaDenseSkinHost().capture_dense_skin(garment_skin)
                    == garment_before
                and not cmds.objExists("AdvPy_MigratedSkin")
                and not cmds.objExists("AdvPy_MigratedSkin_2"))
        else:
            fault_rolled_back = False
        if not fault_rolled_back:
            raise AssertionError("第二网格故障未整体回滚")

        result = operation.apply(source_skin=primary_skin)
        if len(result.migrated_skins) != 2:
            raise AssertionError("没有发现同 Rig 的第二个 Skin")
        garment_copy, garment_target_skin = result.migrated_skins[1]
        garment_after = MayaDenseSkinHost().capture_dense_skin(
            garment_target_skin)
        weights_equal = (garment_after.influence_names
            == garment_before.influence_names
            and garment_after.values == garment_before.values)
        target_before = MayaDenseSkinHost().capture_dense_skin(
            result.skin)
        cmds.undo()
        undo_restored = (not cmds.objExists(result.skin)
            and not cmds.objExists(garment_target_skin)
            and MayaDenseSkinHost().capture_dense_skin(primary_skin)
                == primary_before
            and MayaDenseSkinHost().capture_dense_skin(garment_skin)
                == garment_before)
        cmds.redo()
        redo_restored = (MayaDenseSkinHost().capture_dense_skin(
            result.skin) == target_before
            and MayaDenseSkinHost().capture_dense_skin(
                garment_target_skin) == garment_after)
        cmds.setAttr("AdvPy_TorsoRoot_MFK.rotateY", 20.0)
        pose_error = max(abs(a - b) for source, target in zip(
            source_pose, _points(garment_copy)) for a, b in zip(source,
                                                                 target))
        cmds.setAttr("AdvPy_TorsoRoot_MFK.rotateY", 0.0)
        report.parent.mkdir(parents=True, exist_ok=True)
        saved = report.with_suffix(".mb").resolve()
        cmds.file(rename=str(saved))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(saved), open=True, force=True,
                  executeScriptNodes=False)
        reopen_restored = (MayaDenseSkinHost().capture_dense_skin(
            result.skin) == target_before
            and MayaDenseSkinHost().capture_dense_skin(
                garment_target_skin) == garment_after)
        data = {"source": scene.name,
                "migrated_skin_count": len(result.migrated_skins),
                "garment_vertices": garment_after.vertex_count,
                "garment_influences": len(garment_after.influence_names),
                "garment_weight_equal": weights_equal,
                "garment_root_y20_world_point_error": pose_error,
                "fault_rolled_back": fault_rolled_back,
                "undo_restored": undo_restored,
                "redo_restored": redo_restored,
                "reopen_restored": reopen_restored,
                "saved_scene": saved.name}
        report.write_text(json.dumps(data, indent=2) + "\n",
                          encoding="utf-8")
        if not (weights_equal and fault_rolled_back and undo_restored
                and redo_restored and reopen_restored
                and garment_after.vertex_count == 8
                and len(garment_after.influence_names) == 2
                and pose_error <= 1e-5):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))

