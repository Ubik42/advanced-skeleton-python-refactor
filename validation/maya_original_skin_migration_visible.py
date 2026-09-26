"""Drive the real Maya window through Body / Build and capture its result."""
from __future__ import annotations

from pathlib import Path
import json
import traceback

from maya import cmds
import maya.utils
from PySide2 import QtCore, QtWidgets

from adv_py.adapters.maya_body import MayaBodyBuildHost
from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
from adv_py.application.character_registry import ResolveBodyCharacter
from adv_py.product.maya_adv_layout import create_adv_panel


def _points(mesh: str):
    from maya.api import OpenMaya as om
    selection = om.MSelectionList()
    selection.add(mesh)
    dag = selection.getDagPath(0)
    if dag.apiType() == om.MFn.kTransform:
        dag.extendToShape()
    return tuple(tuple(float(value) for value in point)
                 for point in om.MFnMesh(dag).getPoints(om.MSpace.kWorld))


def schedule(scene: str, output_directory: str,
             namespace: str = ":") -> None:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    prefix = "" if namespace == ":" else namespace.strip(":") + ":"

    def run() -> None:
        data = {"scene": Path(scene).name}
        try:
            cmds.file(scene, open=True, force=True, executeScriptNodes=False)
            cmds.undoInfo(state=True)
            source_skin = (cmds.ls(type="skinCluster") or [])[0]
            source_shape = (cmds.skinCluster(source_skin, query=True,
                            geometry=True) or [])[0]
            source_mesh = (cmds.listRelatives(source_shape, parent=True,
                                              fullPath=True) or [])[0]
            cmds.setAttr(prefix + "FKRoot_M.rotateY", 20.0)
            expected = _points(source_mesh)
            cmds.setAttr(prefix + "FKRoot_M.rotateY", 0.0)

            panel = create_adv_panel()
            panel.show()
            panel.section_buttons[("Body", None)].click()
            panel.section_buttons[("Body", "Build")].click()
            button = panel.operation_buttons[(
                "Body", "Build", "迁移当前原版角色与蒙皮")]
            button.click()
            detail = panel.detail
            role = next((detail.roles.item(i) for i in
                range(detail.roles.count()) if detail.roles.item(i).data(
                    QtCore.Qt.UserRole) == namespace), None)
            if role is None:
                raise AssertionError("面板没有列出来源角色命名空间：" + namespace)
            detail.roles.setCurrentItem(role)
            QtWidgets.QApplication.processEvents()
            data["entry_visible"] = (panel.isVisible()
                and detail.isVisible() and button.isVisible())
            data["detail_title"] = detail.windowTitle()
            data["roles_before"] = [detail.roles.item(i).text()
                                    for i in range(detail.roles.count())]
            detail.grab().save(str(output / "maya-visible-migration-before.png"))

            dialogs = QtCore.QTimer()
            dialogs.setInterval(300)
            def handle_dialogs():
                for widget in QtWidgets.QApplication.topLevelWidgets():
                    if not isinstance(widget, QtWidgets.QDialog) or not widget.isVisible():
                        continue
                    labels = " ".join(label.text() for label in
                        widget.findChildren(QtWidgets.QLabel))
                    if ("skin_bulk.py" in labels
                            and "不受信任的插件加载" in widget.windowTitle()):
                        allow = next((button for button in widget.findChildren(
                            QtWidgets.QPushButton)
                            if button.text() == "允许"), None)
                        if allow:
                            data["plugin_allowed_for_this_load"] = True
                            allow.click()
                    elif isinstance(widget, QtWidgets.QMessageBox):
                        data["modal_error"] = widget.text()
                        widget.reject()
            dialogs.timeout.connect(handle_dialogs)
            dialogs.start()
            action = next(child for child in detail.findChildren(
                QtWidgets.QPushButton)
                if child.text() == "迁移当前原版角色与蒙皮")
            action.click()
            dialogs.stop()
            QtWidgets.QApplication.processEvents()
            data["status"] = detail.status.toPlainText()
            data["roles_after"] = [detail.roles.item(i).text()
                                   for i in range(detail.roles.count())]
            detail.grab().save(str(output / "maya-visible-migration-after.png"))
            panel.grab().save(str(output / "maya-visible-migration-navigation.png"))
            target_skin = prefix + "AdvPy_MigratedSkin"
            target_mesh = prefix + "AdvPy_MigratedMesh"
            if not cmds.objExists(target_skin):
                raise AssertionError("图形入口没有生成目标 Skin：" + data["status"])

            captured = MayaDenseSkinHost().capture_dense_skin(
                target_skin)
            data["vertices"] = captured.vertex_count
            data["influences"] = len(captured.influence_names)
            data["body_joints"] = len(ResolveBodyCharacter(
                MayaBodyBuildHost(namespace=None if namespace == ":"
                    else namespace)).execute().body)
            cmds.setAttr(prefix + "AdvPy_TorsoRoot_MFK.rotateY", 20.0)
            posed = _points(target_mesh)
            data["root_y20_world_point_error"] = max(abs(a - b)
                for source, target in zip(expected, posed)
                for a, b in zip(source, target))
            cmds.setAttr(prefix + "AdvPy_TorsoRoot_MFK.rotateY", 0.0)
            data["passed"] = (data["entry_visible"]
                and "已迁移" in data["status"]
                and data["vertices"] == 18151
                and data["influences"] == 121
                and data["body_joints"] == 74
                and data["root_y20_world_point_error"] <= 1e-5)
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            (output / "maya-visible-migration.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
