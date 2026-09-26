"""Migrate the original public character after importing it into a namespace."""
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

        cmds.file(new=True, force=True)
        cmds.file(str(scene.resolve()), i=True, namespace="Sam",
                  executeScriptNodes=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        source_copy = report.with_name(report.stem + "-source.mb").resolve()
        cmds.file(rename=str(source_copy))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(source_copy), open=True, force=True,
                  executeScriptNodes=False)
        cmds.undoInfo(state=True)
        skin = (cmds.ls("Sam:*", type="skinCluster") or [])[0]
        original = MayaDenseSkinHost().capture_dense_skin(skin)
        mesh_shape = (cmds.skinCluster(skin, query=True,
                                      geometry=True) or [])[0]
        source_mesh = (cmds.listRelatives(mesh_shape, parent=True,
                                          fullPath=True) or [])[0]
        for side in ("R", "L"):
            cmds.setAttr(f"Sam:FKIKLeg_{side}.FKIKBlend", 0.0)
        cmds.setAttr("Sam:FKRoot_M.rotateY", 20.0)
        source_pose = _points(source_mesh)
        cmds.setAttr("Sam:FKRoot_M.rotateY", 0.0)
        operation = MayaOriginalSkinMigration()

        def fault(stage):
            if stage == "rig-built":
                raise RuntimeError("injected namespace fault")
        try:
            operation.apply(source_skin=skin, on_stage=fault)
        except RuntimeError as error:
            fault_rolled_back = (str(error) == "injected namespace fault"
                and MayaDenseSkinHost().capture_dense_skin(skin) == original
                and not cmds.objExists("Sam:AdvPy_MigratedSkin"))
        else:
            fault_rolled_back = False
        if not fault_rolled_back:
            raise AssertionError("命名空间迁移故障未整体回滚")

        result = operation.apply(source_skin=skin)
        target = MayaDenseSkinHost().capture_dense_skin(result.skin)
        scoped_names = all(name.startswith("Sam:") for name in
            (result.mesh, result.skin))
        namespace_restored = (cmds.namespaceInfo(currentNamespace=True,
            absoluteName=True) == ":" and not cmds.namespace(query=True,
                                                        relativeNames=True))
        weights_equal = (target.influence_names == original.influence_names
                         and target.values == original.values)
        cmds.undo()
        undo_target_gone = not cmds.objExists(result.skin)
        undo_weights_equal = (cmds.objExists(skin) and
            MayaDenseSkinHost().capture_dense_skin(skin) == original)
        undo_restored = undo_target_gone and undo_weights_equal
        cmds.redo()
        redo_restored = (MayaDenseSkinHost().capture_dense_skin(
            result.skin) == target)
        cmds.setAttr("Sam:AdvPy_TorsoRoot_MFK.rotateY", 20.0)
        pose_error = max(abs(a - b) for source, dest in zip(
            source_pose, _points(result.mesh)) for a, b in zip(source,
                                                                dest))
        cmds.setAttr("Sam:AdvPy_TorsoRoot_MFK.rotateY", 0.0)
        saved = report.with_suffix(".mb").resolve()
        cmds.file(rename=str(saved))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(saved), open=True, force=True,
                  executeScriptNodes=False)
        reopen_restored = (MayaDenseSkinHost().capture_dense_skin(
            result.skin) == target)
        data = {"source": scene.name, "namespace": "Sam",
                "vertices": target.vertex_count,
                "influences": len(target.influence_names),
                "scoped_names": scoped_names,
                "namespace_restored": namespace_restored,
                "weights_equal": weights_equal,
                "root_y20_world_point_error": pose_error,
                "fault_rolled_back": fault_rolled_back,
                "undo_restored": undo_restored,
                "undo_target_gone": undo_target_gone,
                "undo_weights_equal": undo_weights_equal,
                "redo_restored": redo_restored,
                "reopen_restored": reopen_restored}
        report.write_text(json.dumps(data, indent=2) + "\n",
                          encoding="utf-8")
        if not (scoped_names and namespace_restored and weights_equal
                and fault_rolled_back and undo_restored and redo_restored
                and reopen_restored and target.vertex_count == 18151
                and len(target.influence_names) == 121
                and pose_error <= 1e-5):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
