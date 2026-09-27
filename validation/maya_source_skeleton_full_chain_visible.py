"""Click source skeleton build, animation and skinned FBX in Maya's UI."""
from __future__ import annotations

from pathlib import Path
import json
import os
import traceback

from maya import cmds
import maya.utils
from PySide2 import QtCore, QtWidgets

from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_template import synthetic_body_source_fit_template
from adv_py.product.maya_adv_layout import create_adv_panel


def schedule(output_directory: str, scene: str = "") -> None:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        data = {}
        try:
            source_mesh = "SourceBodyMesh" if scene else "SourceMesh"
            if scene:
                cmds.file(scene, open=True, force=True,
                          executeScriptNodes=False)
            else:
                cmds.file(new=True, force=True)
                joints = {}
                omitted = {"HeadEnd", "Heel", "FootSideInner",
                           "FootSideOuter", "ToesEnd"}
                for spec in synthetic_body_source_fit_template(FitUpAxis.Y).joints:
                    if spec.name in omitted:
                        continue
                    parent = joints.get(spec.parent)
                    joint = cmds.createNode("joint", name=spec.name,
                        **({"parent": parent} if parent else {}))
                    cmds.setAttr(joint + ".translate", *spec.local_position)
                    joints[spec.name] = joint
                cmds.polyCube(name=source_mesh, width=8,
                              height=18, depth=5)
            cmds.undoInfo(state=True)

            panel = create_adv_panel()
            panel.show()
            panel.section_buttons[("Body", None)].click()
            panel.section_buttons[("Body", "Build")].click()
            panel.operation_buttons[("Body", "Build",
                "构建并登记角色")].click()
            detail = panel.detail
            detail.build_source_root.setText("|Root")
            detail.build_meshes.setPlainText("|" + source_mesh)
            QtWidgets.QApplication.processEvents()
            data["build_entry_visible"] = (panel.isVisible()
                and detail.build_source_root.isVisible()
                and detail.build_meshes.isVisible())
            detail.grab().save(str(output / "source-build-before.png"))
            build_button = next(button for button in
                detail.findChildren(QtWidgets.QPushButton)
                if button.text() == "从来源骨架直接构建角色")
            build_button.click()
            QtWidgets.QApplication.processEvents()
            data["build_status"] = detail.status.toPlainText()
            data["selected_role"] = (detail.roles.currentItem().data(
                QtCore.Qt.UserRole) if detail.roles.currentItem() else None)
            data["source_preserved"] = (cmds.objExists("Root")
                and cmds.objExists(source_mesh))
            data["body_count"] = len(cmds.ls("AdvPy:*", type="joint") or [])
            data["skin_count"] = len(cmds.ls("AdvPy:*",
                type="skinCluster") or [])
            detail.grab().save(str(output / "source-build-after.png"))

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
            cmds.setAttr("AdvPy:AdvPy_Global.translateX", 2)
            key_button.click()
            data["key_times"] = cmds.keyframe(
                "AdvPy:AdvPy_Global.translateX", query=True,
                timeChange=True) or []

            panel.section_buttons[("Export", None)].click()
            panel.operation_buttons[("Export", None, "发布 FBX")].click()
            fbx = (output / "source-visible.fbx").resolve()
            detail.fbx_output.setText(str(fbx))
            detail.fbx_start.setValue(1)
            detail.fbx_end.setValue(5)
            detail.fbx_include_skins.setChecked(True)
            data["export_entry_visible"] = detail.fbx_output.isVisible()

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
            detail.grab().save(str(output / "source-export-after.png"))

            saved_scene = (output / "source-visible.mb").resolve()
            cmds.file(rename=str(saved_scene))
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(str(saved_scene), open=True, force=True,
                      executeScriptNodes=False)
            data["reopen_skin_count"] = len(cmds.ls("AdvPy:*",
                type="skinCluster") or [])
            data["reopen_key_times"] = cmds.keyframe(
                "AdvPy:AdvPy_Global.translateX", query=True,
                timeChange=True) or []
            data["passed"] = (data["build_entry_visible"]
                and data["export_entry_visible"]
                and data["selected_role"] == "AdvPy"
                and data["source_preserved"]
                and data["body_count"] >= 48
                and data["skin_count"] == 1
                and data["key_times"] == [1.0, 5.0]
                and data["fbx_bytes"] > 10000
                and data["reopen_skin_count"] == 1
                and data["reopen_key_times"] == [1.0, 5.0]
                and "操作失败" not in data["build_status"]
                and "操作失败" not in data["export_status"])
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            (output / "source-visible.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
