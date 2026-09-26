"""Republish edited animation and roll back a failed Maya FBX refresh."""
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(scene: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        cmds.undoInfo(state=True)
        skins = tuple(sorted(cmds.ls(type="skinCluster") or []))
        host = MayaDenseSkinHost()
        original_weights = tuple(host.capture_dense_skin(skin)
                                 for skin in skins)
        old_root = "AdvPy_GameRootMotion"
        old_uuid = cmds.ls(old_root, uuid=True)[0]
        controller = MayaPanelController()

        with tempfile.TemporaryDirectory(prefix="advpy-republish-") as temp:
            temp = Path(temp)
            cmds.setKeyframe("AdvPy_KneeFK_L", attribute="rotateX",
                             time=5, value=20.0)
            cmds.currentTime(1)
            first = temp / "updated.fbx"
            controller.publish_fbx(":", first, 1, 5,
                                   include_skins=True)
            first_uuid = cmds.ls(old_root, uuid=True)[0]
            cmds.currentTime(5)
            first_knee = cmds.getAttr("AdvPy_EXP_Knee_L.rotateX")

            cmds.currentTime(3)
            cmds.select("AdvPy_KneeFK_L", replace=True)
            original_selection = cmds.ls(selection=True, long=True)
            original_modified = cmds.file(query=True, modified=True)
            original_scene = cmds.file(query=True, sceneName=True)
            failing = temp / "failed.fbx"
            with patch("adv_py.product.maya_panel_controller.ExportBodyFbx.apply",
                       side_effect=RuntimeError("injected FBX failure")):
                try:
                    controller.publish_fbx(":", failing, 1, 5,
                                           include_skins=True)
                except RuntimeError as error:
                    failure_seen = str(error) == "injected FBX failure"
                else:
                    failure_seen = False
            cmds.currentTime(5)
            restored_knee = cmds.getAttr("AdvPy_EXP_Knee_L.rotateX")
            rollback = (failure_seen and not failing.exists()
                and cmds.ls(old_root, uuid=True) == [first_uuid]
                and abs(restored_knee - first_knee) < 1e-6
                and cmds.ls(selection=True, long=True) == original_selection
                and cmds.file(query=True, sceneName=True) == original_scene
                and cmds.file(query=True, modified=True) == original_modified
                and tuple(host.capture_dense_skin(skin) for skin in skins)
                    == original_weights)

            extra = cmds.createNode("transform", name="ForeignAttachment",
                                    parent=old_root)
            blocked = temp / "blocked.fbx"
            try:
                controller.publish_fbx(":", blocked, 1, 5,
                                       include_skins=True)
            except Exception as error:
                extra_child_rejected = "额外或缺失节点" in str(error)
            else:
                extra_child_rejected = False
            extra_child_rejected = (extra_child_rejected
                and cmds.objExists(extra) and not blocked.exists()
                and cmds.ls(old_root, uuid=True) == [first_uuid])
            cmds.delete(extra)

            reader = cmds.createNode("decomposeMatrix", name="ForeignReader")
            cmds.connectAttr(old_root + ".worldMatrix[0]",
                             reader + ".inputMatrix")
            linked = temp / "linked.fbx"
            try:
                controller.publish_fbx(":", linked, 1, 5,
                                       include_skins=True)
            except Exception as error:
                external_link_rejected = "其他节点依赖" in str(error)
            else:
                external_link_rejected = False
            external_link_rejected = (external_link_rejected
                and cmds.objExists(reader) and not linked.exists()
                and cmds.ls(old_root, uuid=True) == [first_uuid])
            cmds.delete(reader)

            cmds.setKeyframe("AdvPy_KneeFK_L", attribute="rotateX",
                             time=5, value=30.0)
            cmds.currentTime(1)
            second = temp / "updated-again.fbx"
            controller.publish_fbx(":", second, 1, 5,
                                   include_skins=True)
            second_uuid = cmds.ls(old_root, uuid=True)[0]
            cmds.undo()
            undo_uuid = cmds.ls(old_root, uuid=True)[0]
            cmds.redo()
            redo_uuid = cmds.ls(old_root, uuid=True)[0]
            single_undo_redo = (undo_uuid == first_uuid
                                and redo_uuid == second_uuid)
            cmds.currentTime(5)
            second_knee = cmds.getAttr("AdvPy_EXP_Knee_L.rotateX")
            source_intact = tuple(host.capture_dense_skin(skin)
                                  for skin in skins) == original_weights
            cmds.delete(old_root)
            fresh_failure = temp / "fresh-failed.fbx"
            with patch("adv_py.product.maya_panel_controller.ExportBodyFbx.apply",
                       side_effect=RuntimeError("injected fresh failure")):
                try:
                    controller.publish_fbx(":", fresh_failure, 1, 5,
                                           include_skins=True)
                except RuntimeError as error:
                    fresh_failure_seen = str(error) == "injected fresh failure"
                else:
                    fresh_failure_seen = False
            fresh_failure_rolled_back = (fresh_failure_seen
                and not fresh_failure.exists() and not cmds.objExists(old_root)
                and tuple(host.capture_dense_skin(skin) for skin in skins)
                    == original_weights)
            cmds.file(new=True, force=True)
            cmds.file(str(second), i=True, type="FBX",
                      ignoreVersion=True, executeScriptNodes=False)
            data = {
                "old_root_replaced": first_uuid != old_uuid,
                "first_knee_rotate_x": first_knee,
                "failure_rolled_back": rollback,
                "extra_child_rejected": extra_child_rejected,
                "external_link_rejected": external_link_rejected,
                "second_root_replaced": second_uuid != first_uuid,
                "single_undo_redo": single_undo_redo,
                "second_knee_rotate_x": second_knee,
                "source_skin_unchanged": source_intact,
                "fresh_failure_rolled_back": fresh_failure_rolled_back,
                "imported_joints": len(cmds.ls(type="joint") or []),
                "imported_skins": len(cmds.ls(type="skinCluster") or []),
                "first_fbx_bytes": first.stat().st_size,
                "second_fbx_bytes": second.stat().st_size,
            }
            report.write_text(json.dumps(data, indent=2) + "\n",
                              encoding="utf-8")
            if not (data["old_root_replaced"] and rollback
                    and extra_child_rejected
                    and external_link_rejected
                    and data["second_root_replaced"]
                    and single_undo_redo
                    and abs(first_knee - 20) < 1e-4
                    and abs(second_knee - 30) < 1e-4
                    and source_intact and fresh_failure_rolled_back
                    and data["imported_joints"] == 75
                    and data["imported_skins"] == 2):
                raise AssertionError(data)
            return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
