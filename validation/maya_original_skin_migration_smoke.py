"""Exercise the reusable original-scene migration, including whole-chain rollback."""
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


def main(scene: Path, volume_file: Path, angle_file: Path,
         axial_file: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
        from adv_py.adapters.maya_original_skin_migration import (
            MayaOriginalSkinMigration)

        volume = json.loads(volume_file.read_text(encoding="utf-8"))
        angle = json.loads(angle_file.read_text(encoding="utf-8"))
        axial = json.loads(axial_file.read_text(encoding="utf-8"))
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        source_skin = (cmds.ls(type="skinCluster") or [])[0]
        original = MayaDenseSkinHost().capture_dense_skin(source_skin)
        source_shape = (cmds.skinCluster(source_skin, query=True,
                                        geometry=True) or [])[0]
        source_mesh = (cmds.listRelatives(source_shape, parent=True,
                                         fullPath=True) or [])[0]
        source_points = _points(source_mesh)
        operation = MayaOriginalSkinMigration()
        mismatched = dict(volume)
        mismatched["source"] = "another-character.mb"
        try:
            operation.apply(source_skin=source_skin, volume=mismatched,
                            angle=angle, axial=axial)
        except ValueError:
            wrong_guide_rejected = (cmds.objExists(source_skin)
                and not cmds.objExists("AdvPy_MigratedMesh"))
        else:
            wrong_guide_rejected = False
        if not wrong_guide_rejected:
            raise AssertionError("错误场景导向未在修改前拒绝")
        fault_results = {}
        for stage in ("mesh-copied", "rig-built"):
            def fault(current, expected=stage):
                if current == expected:
                    raise RuntimeError("injected " + expected)
            try:
                operation.apply(source_skin=source_skin, volume=volume,
                    angle=angle, axial=axial, on_stage=fault)
            except RuntimeError as error:
                fault_results[stage] = (str(error) == "injected " + stage
                    and not cmds.objExists("AdvPy_MigratedMesh")
                    and not cmds.objExists("AdvPy_MigratedSkin")
                    and cmds.objExists("FitSkeleton")
                    and MayaDenseSkinHost().capture_dense_skin(source_skin)
                        == original)
            else:
                fault_results[stage] = False
            if not fault_results[stage]:
                raise AssertionError("整链故障回滚失败：" + stage)
        result = operation.apply(source_skin=source_skin, volume=volume,
                                 angle=angle, axial=axial)
        migrated = MayaDenseSkinHost().capture_dense_skin(result.skin)
        rest_error = max(abs(a - b) for source, target in zip(
            source_points, _points(result.mesh)) for a, b in zip(source,
                                                                  target))
        names_equal = set(migrated.influence_names) == set(original.influence_names)
        cmds.undo()
        undo_restored = (not cmds.objExists(result.mesh)
            and MayaDenseSkinHost().capture_dense_skin(source_skin) == original)
        cmds.redo()
        redo_restored = (MayaDenseSkinHost().capture_dense_skin(result.skin)
            == migrated)
        report.parent.mkdir(parents=True, exist_ok=True)
        saved = report.with_suffix(".mb")
        cmds.file(rename=str(saved.resolve()))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(saved.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        reopen_restored = (MayaDenseSkinHost().capture_dense_skin(result.skin)
            == migrated)
        data = {"source": scene.name, "fault_rolled_back": fault_results,
                "wrong_guide_rejected": wrong_guide_rejected,
                "rest_world_point_error": rest_error,
                "vertex_count": result.vertices,
                "influence_count": result.influences,
                "body_joints": result.body_joints,
                "influence_names_equal": names_equal,
                "undo_restored": undo_restored,
                "redo_restored": redo_restored,
                "reopen_restored": reopen_restored,
                "saved_scene": saved.name}
        report.write_text(json.dumps(data, ensure_ascii=False, indent=2)
                          + "\n", encoding="utf-8")
        if (result.vertices != 18151 or result.influences != 121
                or result.body_joints != 74 or not names_equal
                or not undo_restored or not redo_restored
                or not reopen_restored or rest_error > 1e-5):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(*(Path(value) for value in sys.argv[1:6])))
