"""Migrate a local accessory skinned to a referenced original character."""
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
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(new=True, force=True)
        cmds.file(str(scene.resolve()), reference=True, namespace="Sam",
                  executeScriptNodes=False)
        source_scene = report.with_name(report.stem + "-source.mb").resolve()
        cmds.file(rename=str(source_scene))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(source_scene), open=True, force=True,
                  executeScriptNodes=False)
        cmds.undoInfo(state=True)
        skin = (cmds.ls("Sam:*", type="skinCluster") or [])[0]
        original = MayaDenseSkinHost().capture_dense_skin(skin)
        garment = cmds.polyCube(name="GarmentMesh", width=1.0,
                                height=1.5, depth=.5)[0]
        cmds.xform(garment, worldSpace=True, translation=(.5, 7.0, 0.0))
        garment_skin = cmds.skinCluster("Sam:Root_M", "Sam:Hip_R",
            garment, name="GarmentSkin", maximumInfluences=2,
            toSelectedBones=True)[0]
        garment_before = MayaDenseSkinHost().capture_dense_skin(
            garment_skin)
        for side in ("R", "L"):
            cmds.setAttr(f"Sam:FKIKLeg_{side}.FKIKBlend", 0.0)
        cmds.setAttr("Sam:FKRoot_M.rotateY", 20.0)
        expected_pose = _points(garment)
        cmds.setAttr("Sam:FKRoot_M.rotateY", 0.0)

        def fault(stage):
            if stage == "weights-copied":
                raise RuntimeError("injected accessory fault")
        try:
            MayaOriginalSkinMigration().apply(namespace="Sam",
                source_skin=skin, on_stage=fault)
        except RuntimeError as error:
            fault_rolled_back = (str(error) == "injected accessory fault"
                and not cmds.namespace(exists="Sam_AdvPy")
                and cmds.getAttr("Sam:Group.visibility") == 1
                and cmds.getAttr(garment + ".visibility") == 1
                and MayaDenseSkinHost().capture_dense_skin(skin) == original
                and MayaDenseSkinHost().capture_dense_skin(
                    garment_skin) == garment_before)
        else:
            fault_rolled_back = False
        if not fault_rolled_back:
            raise AssertionError("双 Skin 引用迁移故障未整体回滚")

        result = MayaPanelController().original_skin_migrate("Sam")
        if len(result.migrated_skins) != 2:
            raise AssertionError("引用角色的附加 Skin 未一起迁移")
        garment_copy, garment_target_skin = result.migrated_skins[1]
        garment_after = MayaDenseSkinHost().capture_dense_skin(
            garment_target_skin)
        weights_equal = (garment_after.values == garment_before.values
            and tuple(name.rsplit(":", 1)[-1] for name in
                      garment_after.influence_names)
                == tuple(name.rsplit(":", 1)[-1] for name in
                         garment_before.influence_names))
        source_preserved = (cmds.referenceQuery(skin,
            isNodeReferenced=True) and MayaDenseSkinHost().capture_dense_skin(
            skin) == original and MayaDenseSkinHost().capture_dense_skin(
            garment_skin) == garment_before
            and cmds.getAttr("Sam:Group.visibility") == 0
            and cmds.getAttr(garment + ".visibility") == 0)
        cmds.undo()
        undo_restored = (not cmds.objExists(result.skin)
            and not cmds.objExists(garment_target_skin)
            and cmds.getAttr("Sam:Group.visibility") == 1
            and cmds.getAttr(garment + ".visibility") == 1
            and MayaDenseSkinHost().capture_dense_skin(skin) == original
            and MayaDenseSkinHost().capture_dense_skin(
                garment_skin) == garment_before)
        cmds.redo()
        redo_restored = (MayaDenseSkinHost().capture_dense_skin(
            garment_target_skin) == garment_after
            and cmds.getAttr(garment + ".visibility") == 0)
        cmds.setAttr("Sam_AdvPy:AdvPy_TorsoRoot_MFK.rotateY", 20.0)
        pose_error = max(abs(a - b) for source, target in zip(
            expected_pose, _points(garment_copy)) for a, b in zip(source,
                                                                    target))
        cmds.setAttr("Sam_AdvPy:AdvPy_TorsoRoot_MFK.rotateY", 0.0)
        saved = report.with_suffix(".mb").resolve()
        cmds.file(rename=str(saved))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(saved), open=True, force=True,
                  executeScriptNodes=False)
        reopen_restored = (MayaDenseSkinHost().capture_dense_skin(
            garment_target_skin) == garment_after
            and cmds.referenceQuery(skin, isNodeReferenced=True)
            and cmds.getAttr(garment + ".visibility") == 0)
        data = {"source": scene.name,
                "migrated_skin_count": len(result.migrated_skins),
                "garment_vertices": garment_after.vertex_count,
                "garment_influences": len(garment_after.influence_names),
                "garment_weight_equal": weights_equal,
                "garment_root_y20_world_point_error": pose_error,
                "source_preserved": source_preserved,
                "fault_rolled_back": fault_rolled_back,
                "undo_restored": undo_restored,
                "redo_restored": redo_restored,
                "reopen_restored": reopen_restored}
        report.write_text(json.dumps(data, indent=2) + "\n",
                          encoding="utf-8")
        if not (weights_equal and source_preserved and fault_rolled_back
                and undo_restored and redo_restored and reopen_restored
                and garment_after.vertex_count == 8
                and len(garment_after.influence_names) == 2
                and pose_error <= 1e-5):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
