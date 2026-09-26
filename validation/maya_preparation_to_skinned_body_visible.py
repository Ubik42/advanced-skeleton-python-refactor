"""Click the Preparation Skin -> Body Build path in a real Maya window."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
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
        dialogs = QtCore.QTimer()
        dialogs.setInterval(250)

        def handle_dialogs():
            for widget in QtWidgets.QApplication.topLevelWidgets():
                if isinstance(widget, QtWidgets.QMessageBox) and widget.isVisible():
                    data["modal_error"] = widget.text()
                    widget.reject()

        dialogs.timeout.connect(handle_dialogs)
        dialogs.start()
        try:
            cmds.file(scene, open=True, force=True, executeScriptNodes=False)
            model = (output / "model.mb").resolve()
            cmds.select("|BodyMesh", "|GarmentMesh", replace=True)
            cmds.file(str(model), exportSelected=True, type="mayaBinary", force=True)
            digest = sha256(model.read_bytes()).hexdigest()
            cmds.delete("|BodyMesh", "|GarmentMesh")
            panel = create_adv_panel()
            panel.show()
            panel.section_buttons[("Preparation", None)].click()
            panel.section_buttons[("Preparation", "Rig")].click()
            panel.operation_buttons[("Preparation", "Rig", "引用模型文件")].click()
            detail = panel.detail
            detail.preparation_model_source.setText(str(model))
            reference_button = next(button for button in
                detail.findChildren(QtWidgets.QPushButton)
                if button.text() == "引用模型文件")
            reference_button.click()
            data["reference_status"] = detail.status.toPlainText()
            assert cmds.objExists("model:BodyMesh")
            panel.operation_buttons[("Preparation", "Rig", "Skin")].click()
            cmds.select("model:BodyMesh", "model:GarmentMesh", replace=True)
            record_button = detail.findChild(QtWidgets.QPushButton,
                                             "AdvPyPrepRecordSkin")
            assert record_button and record_button.isVisible()
            record_button.click()
            data["record_status"] = detail.status.toPlainText()
            data["recorded"] = detail.preparation_object_fields[
                "Skin"].text()
            assert cmds.getAttr("FitSkeleton.objectsSkin") == (
                "model:BodyMesh model:GarmentMesh")
            detail.grab().save(str(output / "preparation-skin-recorded.png"))

            panel.section_buttons[("Body", None)].click()
            panel.section_buttons[("Body", "Build")].click()
            panel.operation_buttons[("Body", "Build", "构建并登记角色")].click()
            detail.infer_missing_fit_labels.setChecked(True)
            assert not detail.build_meshes.toPlainText().strip()
            assert detail.build_use_preparation_skin.isChecked()
            assert len(detail._build_mesh_paths()) == 2
            build_button = next(button for button in
                detail.findChildren(QtWidgets.QPushButton)
                if button.text() == "构建并登记角色")
            build_button.click()
            QtWidgets.QApplication.processEvents()
            data["build_status"] = detail.status.toPlainText()
            data["skins"] = sorted(cmds.ls(type="skinCluster") or [])
            data["body_joints"] = len(ResolveBodyCharacter(
                MayaBodyBuildHost()).execute().body)
            detail.grab().save(str(output / "preparation-body-built.png"))
            data["source_unchanged"] = sha256(model.read_bytes()).hexdigest() == digest
            saved = (output / "referenced-body.mb").resolve()
            cmds.file(rename=str(saved))
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(str(saved), open=True, force=True,
                      executeScriptNodes=False)
            data["reopen_skin_count"] = len(cmds.ls(type="skinCluster") or [])
            data["reopen_model_referenced"] = bool(cmds.referenceQuery(
                "model:BodyMesh", isNodeReferenced=True))
            data["passed"] = ("已引用" in data["reference_status"]
                and "已记录 Skin" in data["record_status"]
                and "2 套 Skin" in data["build_status"]
                and len(data["skins"]) == 2
                and data["body_joints"] == 74
                and data["source_unchanged"]
                and data["reopen_skin_count"] == 2
                and data["reopen_model_referenced"]
                and "modal_error" not in data)
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            dialogs.stop()
            (output / "preparation-visible.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
