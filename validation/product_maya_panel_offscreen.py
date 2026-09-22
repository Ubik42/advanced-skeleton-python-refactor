"""Render and exercise the Maya panel without opening a visible window."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide2 import QtCore, QtGui, QtWidgets
from adv_py.product.maya_panel import create_panel
from adv_py.product.maya_panel_controller import PanelCharacter


class FakeController:
    def __init__(self):
        self.built = False
        self.calls = []

    def characters(self):
        self.calls.append("characters")
        return (PanelCharacter(":", False),
                PanelCharacter("hero", self.built,
                    30 if self.built else 0, 157 if self.built else 0))

    def body_build(self, namespace, container, *, spine_segments, head_aim):
        self.calls.append(("body_build", namespace, container,
                           spine_segments, head_aim))
        self.built = True
        return PanelCharacter(namespace, True, 30, 157)

    def face_build(self, namespace, specification, control_name, deformer_name):
        self.calls.append(("face_build", namespace, specification.name,
                           control_name, deformer_name))
        return 2


def main(report: Path) -> int:
    report.parent.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication([])
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.is_file():
        QtGui.QFontDatabase.addApplicationFont(str(font))
    controller = FakeController()
    panel = create_panel(controller)
    panel.show()
    app.processEvents()
    fit_image = report.with_name("maya-panel-fit.png")
    skin_image = report.with_name("maya-panel-skin.png")
    animation_image = report.with_name("maya-panel-animation.png")
    face_image = report.with_name("maya-panel-face.png")
    publish_image = report.with_name("maya-panel-publish.png")
    mocap_image = report.with_name("maya-panel-mocap.png")
    pixmap = QtGui.QPixmap(panel.size())
    panel.render(pixmap)
    fit_saved = pixmap.save(str(fit_image))
    panel.tabs.setCurrentIndex(1)
    app.processEvents()
    panel.render(pixmap)
    skin_saved = pixmap.save(str(skin_image))
    panel.tabs.setCurrentIndex(2)
    app.processEvents()
    panel.render(pixmap)
    animation_saved = pixmap.save(str(animation_image))
    panel.tabs.setCurrentIndex(3)
    app.processEvents()
    panel.render(pixmap)
    face_saved = pixmap.save(str(face_image))
    panel.tabs.setCurrentIndex(4)
    app.processEvents()
    panel.render(pixmap)
    mocap_saved = pixmap.save(str(mocap_image))
    panel.tabs.setCurrentIndex(5)
    app.processEvents()
    panel.render(pixmap)
    publish_saved = pixmap.save(str(publish_image))
    panel.face_build_document.setText("C:/temp/face-build.json")
    buttons = {button.text(): button for button in
               panel.findChildren(QtWidgets.QPushButton)}
    panel.roles.setCurrentRow(1)
    buttons["构建面部控制"].click()
    face_dispatched = ("face_build", "hero", "face-build.json",
                       "AdvPy_FaceControls", "AdvPy_FaceBlendShape") in controller.calls
    panel.tabs.setCurrentIndex(0)
    panel.roles.setCurrentRow(1)
    buttons = {button.text(): button for button in
               panel.findChildren(QtWidgets.QPushButton)}
    buttons["构建并登记角色"].click()
    app.processEvents()
    checks = {
        "six_chinese_workspaces": [panel.tabs.tabText(i)
            for i in range(panel.tabs.count())]
            == ["Fit 与构建", "蒙皮", "姿态与动画", "面部", "动捕", "发布"],
        "face_build_dispatches_application_action": face_dispatched,
        "role_selection_dispatches_application_action":
            ("body_build", "hero", "FitSkeleton", None, False)
            in controller.calls,
        "result_updates_selected_role": "30 关节" in panel.current.text()
            and "157 通道" in panel.current.text(),
        "success_feedback_visible": "角色已登记" in panel.status.toPlainText(),
        "offscreen_views_rendered": fit_saved and skin_saved and animation_saved
            and face_saved and mocap_saved and publish_saved,
    }
    payload = {**checks, "status": "passed" if all(checks.values()) else "failed",
               "image_size": [panel.width(), panel.height()]}
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    panel.close()
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
