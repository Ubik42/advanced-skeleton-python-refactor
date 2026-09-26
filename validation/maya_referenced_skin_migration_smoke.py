"""Build a complete local rig from a referenced original public character."""
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
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
        from adv_py.adapters.maya_original_skin_migration import (
            MayaOriginalSkinMigration)
        from adv_py.application.character_registry import ResolveBodyCharacter
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
        source = MayaDenseSkinHost().capture_dense_skin(skin)
        mesh_shape = (cmds.skinCluster(skin, query=True,
                                      geometry=True) or [])[0]
        source_mesh = (cmds.listRelatives(mesh_shape, parent=True,
                                          fullPath=True) or [])[0]
        original_visibility = cmds.getAttr("Sam:Group.visibility")
        for side in ("R", "L"):
            cmds.setAttr(f"Sam:FKIKLeg_{side}.FKIKBlend", 0.0)
        cmds.setKeyframe("Sam:FKRoot_M.rotateY", time=1, value=0.0)
        cmds.setKeyframe("Sam:FKRoot_M.rotateY", time=5, value=20.0)
        cmds.currentTime(5)
        expected_pose = _points(source_mesh)
        cmds.currentTime(1)
        operation = MayaOriginalSkinMigration()

        def fault(stage):
            if stage == "rig-built":
                raise RuntimeError("injected reference fault")
        try:
            operation.apply(namespace="Sam", source_skin=skin,
                            on_stage=fault)
        except RuntimeError as error:
            fault_rolled_back = (str(error) == "injected reference fault"
                and not cmds.namespace(exists="Sam_AdvPy")
                and cmds.getAttr("Sam:Group.visibility")
                    == original_visibility
                and MayaDenseSkinHost().capture_dense_skin(skin) == source)
        else:
            fault_rolled_back = False
        if not fault_rolled_back:
            raise AssertionError("引用迁移故障未整体回滚")

        result = MayaPanelController().original_skin_migrate("Sam")
        target = MayaDenseSkinHost().capture_dense_skin(result.skin)
        weights_equal = (target.values == source.values and tuple(
            name.rsplit(":", 1)[-1] for name in target.influence_names)
            == tuple(name.rsplit(":", 1)[-1] for name in
                     source.influence_names))
        source_untouched = (cmds.referenceQuery(skin,
            isNodeReferenced=True) and MayaDenseSkinHost().capture_dense_skin(
            skin) == source and cmds.getAttr("Sam:Group.visibility") == 0)
        body_joints = len(ResolveBodyCharacter(MayaBodyBuildHost(
            namespace="Sam_AdvPy")).execute().body)
        target_keys = tuple(cmds.keyframe(
            "Sam_AdvPy:AdvPy_TorsoRoot_MFK.rotateY",
            query=True, timeChange=True) or [])
        cmds.undo()
        undo_restored = (not cmds.objExists(result.skin)
            and cmds.getAttr("Sam:Group.visibility") == original_visibility
            and MayaDenseSkinHost().capture_dense_skin(skin) == source)
        empty_namespace_after_undo = (cmds.namespace(exists="Sam_AdvPy")
            and not (cmds.namespaceInfo("Sam_AdvPy",
                listOnlyDependencyNodes=True, recurse=True) or []))
        cmds.redo()
        redo_restored = (MayaDenseSkinHost().capture_dense_skin(
            result.skin) == target and cmds.getAttr(
            "Sam:Group.visibility") == 0)
        cmds.currentTime(5)
        pose_error = max(abs(a - b) for original, migrated in zip(
            expected_pose, _points(result.mesh)) for a, b in zip(
            original, migrated))
        cmds.currentTime(1)
        saved = report.with_suffix(".mb").resolve()
        cmds.file(rename=str(saved))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(saved), open=True, force=True,
                  executeScriptNodes=False)
        reopen_restored = (MayaDenseSkinHost().capture_dense_skin(
            result.skin) == target and cmds.referenceQuery(skin,
            isNodeReferenced=True) and cmds.getAttr(
            "Sam:Group.visibility") == 0 and tuple(cmds.keyframe(
            "Sam_AdvPy:AdvPy_TorsoRoot_MFK.rotateY", query=True,
            timeChange=True) or []) == target_keys and len(
            ResolveBodyCharacter(MayaBodyBuildHost(
                namespace="Sam_AdvPy")).execute().body) == 74)
        data = {"source": scene.name, "target_namespace": "Sam_AdvPy",
                "vertices": target.vertex_count,
                "influences": len(target.influence_names),
                "body_joints": body_joints,
                "animation_curves": result.animation_curves,
                "root_key_times": target_keys,
                "weights_equal": weights_equal,
                "root_y20_world_point_error": pose_error,
                "source_reference_untouched": source_untouched,
                "fault_rolled_back": fault_rolled_back,
                "undo_restored": undo_restored,
                "empty_namespace_after_undo": empty_namespace_after_undo,
                "redo_restored": redo_restored,
                "reopen_restored": reopen_restored}
        report.write_text(json.dumps(data, indent=2) + "\n",
                          encoding="utf-8")
        if not (weights_equal and source_untouched and fault_rolled_back
                and undo_restored and empty_namespace_after_undo
                and redo_restored and reopen_restored
                and body_joints == 74 and target.vertex_count == 18151
                and len(target.influence_names) == 121
                and result.animation_curves == 1
                and target_keys == (1.0, 5.0)
                and pose_error <= 1e-5):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
