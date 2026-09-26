"""Click Fit build, key animation and FBX export in the Maya window."""
from __future__ import annotations

from pathlib import Path
import json
import traceback

from maya import cmds
import maya.utils
from PySide2 import QtCore, QtWidgets

from adv_py.adapters.maya_body import MayaBodyBuildHost
from adv_py.application.character_registry import ResolveBodyCharacter
from adv_py.product.maya_adv_layout import create_adv_panel


def schedule(scene: str, output_directory: str) -> None:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        data = {"source": Path(scene).name}
        try:
            cmds.file(scene, open=True, force=True,
                      executeScriptNodes=False)
            cmds.undoInfo(state=True)
            panel = create_adv_panel()
            panel.show()
            panel.section_buttons[("Body", None)].click()
            panel.section_buttons[("Body", "Build")].click()
            panel.operation_buttons[("Body", "Build",
                "构建并登记角色")].click()
            detail = panel.detail
            role = next(detail.roles.item(i) for i in
                range(detail.roles.count()) if detail.roles.item(i).data(
                    QtCore.Qt.UserRole) == ":")
            detail.roles.setCurrentItem(role)
            detail.build_meshes.setPlainText(
                "|BodyMesh\n|GarmentMesh")
            detail.infer_missing_fit_labels.setChecked(True)
            QtWidgets.QApplication.processEvents()
            data["build_entry_visible"] = (panel.isVisible()
                and detail.isVisible() and detail.build_meshes.isVisible())
            detail.grab().save(str(output / "standard-fit-build-before.png"))
            build_button = next(button for button in
                detail.findChildren(QtWidgets.QPushButton)
                if button.text() == "构建并登记角色")
            build_button.click()
            QtWidgets.QApplication.processEvents()
            data["build_status"] = detail.status.toPlainText()
            data["skins"] = sorted(cmds.ls(type="skinCluster") or [])
            data["body_joints"] = len(ResolveBodyCharacter(
                MayaBodyBuildHost()).execute().body)
            detail.grab().save(str(output / "standard-fit-build-after.png"))

            panel.section_buttons[("Pose", None)].click()
            panel.section_buttons[("Pose", "Pose Functions")].click()
            panel.operation_buttons[("Pose", "Pose Functions",
                "当前帧完整写键")].click()
            key_button = next(button for button in
                detail.findChildren(QtWidgets.QPushButton)
                if button.text() == "当前帧完整写键")
            cmds.currentTime(1)
            key_button.click()
            cmds.currentTime(5)
            cmds.setAttr("AdvPy_Global.translateX", 2)
            key_button.click()
            data["key_times"] = cmds.keyframe(
                "AdvPy_Global.translateX", query=True,
                timeChange=True) or []
            data["key_status"] = detail.status.toPlainText()

            panel.section_buttons[("Export", None)].click()
            panel.operation_buttons[("Export", None, "发布 FBX")].click()
            fbx = (output / "standard-fit-visible.fbx").resolve()
            detail.fbx_output.setText(str(fbx))
            detail.fbx_start.setValue(1)
            detail.fbx_end.setValue(5)
            detail.fbx_include_skins.setChecked(True)
            data["export_entry_visible"] = (detail.fbx_output.isVisible()
                and any(button.text() == "发布 FBX" and button.isVisible()
                        for button in detail.findChildren(
                            QtWidgets.QPushButton)))

            dialogs = QtCore.QTimer()
            dialogs.setInterval(300)
            def handle_dialogs():
                for widget in QtWidgets.QApplication.topLevelWidgets():
                    if (not isinstance(widget, QtWidgets.QDialog)
                            or not widget.isVisible()):
                        continue
                    labels = " ".join(label.text() for label in
                                      widget.findChildren(QtWidgets.QLabel))
                    if ("不受信任的插件加载" in widget.windowTitle()
                            and "fbxmaya" in labels.lower()):
                        allow = next((button for button in
                            widget.findChildren(QtWidgets.QPushButton)
                            if button.text() == "允许"), None)
                        if allow:
                            allow.click()
                    elif isinstance(widget, QtWidgets.QMessageBox):
                        data["modal_error"] = widget.text()
                        widget.reject()
            dialogs.timeout.connect(handle_dialogs)
            dialogs.start()
            export_button = next(button for button in
                detail.findChildren(QtWidgets.QPushButton)
                if button.text() == "发布 FBX")
            export_button.click()
            dialogs.stop()
            QtWidgets.QApplication.processEvents()
            data["export_status"] = detail.status.toPlainText()
            data["fbx_bytes"] = fbx.stat().st_size if fbx.exists() else 0
            detail.grab().save(str(output / "standard-fit-export-after.png"))

            saved = (output / "standard-fit-visible.mb").resolve()
            cmds.file(rename=str(saved))
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(str(saved), open=True, force=True,
                      executeScriptNodes=False)
            data["reopen_skins"] = len(cmds.ls(type="skinCluster") or [])
            data["reopen_keys"] = cmds.keyframe(
                "AdvPy_Global.translateX", query=True,
                timeChange=True) or []
            cmds.file(new=True, force=True)
            cmds.file(str(fbx), i=True, type="FBX",
                      ignoreVersion=True, executeScriptNodes=False)
            data["fbx_joint_count"] = len(cmds.ls(type="joint") or [])
            data["fbx_skin_count"] = len(cmds.ls(type="skinCluster") or [])
            root_motion = (cmds.ls("RootMotion",
                                    type="joint") or [None])[0]
            data["fbx_root_motion"] = root_motion
            if root_motion:
                cmds.currentTime(1)
                first = cmds.xform(root_motion, query=True,
                                   worldSpace=True, translation=True)
                cmds.currentTime(5)
                last = cmds.xform(root_motion, query=True,
                                  worldSpace=True, translation=True)
                data["fbx_root_delta_x"] = last[0] - first[0]
            data["passed"] = (data["build_entry_visible"]
                and data["export_entry_visible"]
                and data["body_joints"] == 74
                and len(data["skins"]) == 2
                and data["key_times"] == [1.0, 5.0]
                and data["reopen_skins"] == 2
                and data["reopen_keys"] == [1.0, 5.0]
                and data["fbx_bytes"] > 10000
                and data["fbx_joint_count"] == 75
                and data["fbx_skin_count"] == 2
                and abs(data.get("fbx_root_delta_x", 0) - 2.0) < 1e-4)
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            (output / "standard-fit-visible.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
