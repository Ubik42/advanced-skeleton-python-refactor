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
from adv_py.product.maya_panel_controller import PanelCharacter, PanelSkinSurfaceResult


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

    def body_rebuild(self, namespace, replacement, extensions, *, progress=None):
        self.calls.append(("body_rebuild", namespace, replacement, extensions))
        if progress:
            progress("暂存替换角色并核对需保留的数据")
        return PanelCharacter(namespace, True, 30, 157)

    def skin_surface_source_export(self, namespace, skin, mesh, destination):
        self.calls.append(("skin_surface_source_export", namespace, skin, mesh,
                           destination.name))
        return 4

    def skin_surface_transfer(self, namespace, target_skin, target_mesh,
                              max_distance, **options):
        self.calls.append(("skin_surface_transfer", namespace, target_skin,
                           target_mesh, max_distance, options))
        return PanelSkinSurfaceResult(9, 7, 0., 0.)

    def animation_key_current(self, namespace):
        self.calls.append(("animation_key_current", namespace))
        return 157

    def animation_enable_limb(self, namespace):
        self.calls.append(("animation_enable_limb", namespace))
        return 189

    def animation_enable_stretch(self, namespace):
        self.calls.append(("animation_enable_stretch", namespace))
        return 193

    def animation_enable_spline(self, namespace):
        self.calls.append(("animation_enable_spline", namespace))
        return 193

    def animation_enable_spaces(self, namespace):
        self.calls.append(("animation_enable_spaces", namespace))
        return 300

    def animation_bake_limb(self, namespace, start, end, limb, side, mode, step):
        self.calls.append(("animation_bake_limb", namespace, start, end,
                           limb, side, mode, step))
        return 3

    def animation_bake_spine(self, namespace, start, end, mode, step):
        self.calls.append(("animation_bake_spine", namespace, start, end,
                           mode, step))
        return 3

    def animation_switch_space(self, namespace, key, mode, frame):
        self.calls.append(("animation_switch_space", namespace, key, mode, frame))
        return mode


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
    skin_transfer_image = report.with_name("maya-panel-skin-transfer.png")
    skin_narrow_image = report.with_name("maya-panel-skin-transfer-narrow.png")
    animation_image = report.with_name("maya-panel-animation.png")
    animation_edit_image = report.with_name("maya-panel-animation-edit.png")
    animation_narrow_image = report.with_name("maya-panel-animation-edit-narrow.png")
    face_image = report.with_name("maya-panel-face.png")
    face_library_image = report.with_name("maya-panel-face-library.png")
    rebuild_image = report.with_name("maya-panel-rebuild.png")
    publish_image = report.with_name("maya-panel-publish.png")
    mocap_image = report.with_name("maya-panel-mocap.png")
    pixmap = QtGui.QPixmap(panel.size())
    panel.render(pixmap)
    fit_saved = pixmap.save(str(fit_image))
    panel.tabs.setCurrentIndex(1)
    app.processEvents()
    panel.render(pixmap)
    skin_saved = pixmap.save(str(skin_image))
    panel.roles.setCurrentRow(1)
    panel.surface_source_skin.setText("SourceSkin")
    panel.surface_source_mesh.setText("|SourceMesh")
    panel.surface_asset_out.setText("C:/temp/source-asset.json")
    skin_buttons = {button.text(): button for button in
                    panel.findChildren(QtWidgets.QPushButton)}
    skin_buttons["导出网格与权重"].click()
    panel.surface_mode.setCurrentIndex(1)
    panel.surface_asset_in.setText("C:/temp/source-asset.json")
    panel.surface_target_skin.setText("TargetSkin")
    panel.surface_target_mesh.setText("|TargetMesh")
    panel.surface_distance.setValue(.01)
    panel.surface_extra.setChecked(True)
    skin_buttons["预检并转移权重"].click()
    surface_dispatch = next((call for call in controller.calls
        if isinstance(call, tuple) and call[0] == "skin_surface_transfer"), None)
    skin_page = panel.tabs.currentWidget()
    skin_page.verticalScrollBar().setValue(skin_page.verticalScrollBar().maximum())
    app.processEvents()
    panel.render(pixmap)
    skin_transfer_saved = pixmap.save(str(skin_transfer_image))
    panel.resize(790, 590)
    app.processEvents()
    narrow_pixmap = QtGui.QPixmap(panel.size())
    panel.render(narrow_pixmap)
    skin_narrow_saved = narrow_pixmap.save(str(skin_narrow_image))
    panel.resize(950, 710)
    app.processEvents()
    panel.tabs.setCurrentIndex(2)
    app.processEvents()
    panel.render(pixmap)
    animation_saved = pixmap.save(str(animation_image))
    panel.roles.setCurrentRow(1)
    panel.start_frame.setValue(1)
    panel.end_frame.setValue(3)
    panel.frame_step.setValue(1)
    buttons = {button.text(): button for button in
               panel.findChildren(QtWidgets.QPushButton)}
    for label in ("当前帧完整写键", "启用四肢动画", "启用拉伸匹配",
                  "启用可变脊柱", "启用空间动画", "转换四肢模式", "转换脊柱模式",
                  "在指定帧切换空间"):
        buttons[label].click()
    animation_page = panel.tabs.currentWidget()
    animation_page.verticalScrollBar().setValue(animation_page.verticalScrollBar().maximum())
    app.processEvents()
    panel.render(pixmap)
    animation_edit_saved = pixmap.save(str(animation_edit_image))
    panel.resize(790, 590)
    app.processEvents()
    narrow_pixmap = QtGui.QPixmap(panel.size())
    panel.render(narrow_pixmap)
    animation_narrow_saved = narrow_pixmap.save(str(animation_narrow_image))
    animation_narrow_horizontal_overflow = animation_page.horizontalScrollBar().maximum()
    panel.resize(950, 710)
    app.processEvents()
    panel.tabs.setCurrentIndex(3)
    app.processEvents()
    panel.render(pixmap)
    face_saved = pixmap.save(str(face_image))
    face_page = panel.tabs.currentWidget()
    face_page.verticalScrollBar().setValue(face_page.verticalScrollBar().maximum())
    app.processEvents()
    panel.render(pixmap)
    face_library_saved = pixmap.save(str(face_library_image))
    panel.tabs.setCurrentIndex(4)
    app.processEvents()
    panel.render(pixmap)
    mocap_saved = pixmap.save(str(mocap_image))
    panel.tabs.setCurrentIndex(5)
    app.processEvents()
    panel.fbx_euler_filter.setChecked(True)
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
    fit_page = panel.tabs.currentWidget()
    fit_page.verticalScrollBar().setValue(fit_page.verticalScrollBar().maximum())
    app.processEvents()
    panel.render(pixmap)
    rebuild_saved = pixmap.save(str(rebuild_image))
    panel.rebuild_extensions.setPlainText("|Head_M|AdvPy_FaceControls")
    buttons["重建并保留数据"].click()
    app.processEvents()
    checks = {
        "six_chinese_workspaces": [panel.tabs.tabText(i)
            for i in range(panel.tabs.count())]
            == ["Fit 与构建", "蒙皮", "姿态与动画", "面部", "动捕", "发布"],
        "euler_filter_option_visible": panel.fbx_euler_filter.isChecked(),
        "surface_source_export_dispatches": ("skin_surface_source_export",
            "hero", "SourceSkin", "|SourceMesh", "source-asset.json") in controller.calls,
        "surface_transfer_dispatches_asset": bool(surface_dispatch
            and surface_dispatch[1:5] == ("hero", "TargetSkin", "|TargetMesh", .01)
            and surface_dispatch[5]["source_asset"] == Path("C:/temp/source-asset.json")
            and surface_dispatch[5]["allow_target_extra_influences"]),
        "animation_edit_actions_dispatch": all(call in controller.calls for call in (
            ("animation_key_current", "hero"),
            ("animation_enable_limb", "hero"),
            ("animation_enable_stretch", "hero"),
            ("animation_enable_spline", "hero"),
            ("animation_enable_spaces", "hero"),
            ("animation_bake_limb", "hero", 1, 3, "arm", "R", "ik", 1),
            ("animation_bake_spine", "hero", 1, 3, "ik", 1),
            ("animation_switch_space", "hero", "head", "body", 1))),
        "animation_narrow_no_horizontal_overflow":
            animation_narrow_horizontal_overflow == 0,
        "face_build_dispatches_application_action": face_dispatched,
        "role_selection_dispatches_application_action":
            ("body_build", "hero", "FitSkeleton", None, False)
            in controller.calls,
        "rebuild_dispatches_declared_extensions":
            ("body_rebuild", "hero", "CharacterRebuildStage",
             ("|Head_M|AdvPy_FaceControls",)) in controller.calls,
        "result_updates_selected_role": "30 关节" in panel.current.text()
            and "157 通道" in panel.current.text(),
        "success_feedback_visible": "角色已原位重建" in panel.status.toPlainText(),
        "offscreen_views_rendered": fit_saved and rebuild_saved
            and skin_saved and skin_transfer_saved and skin_narrow_saved
            and animation_saved and animation_edit_saved and animation_narrow_saved
            and face_saved and face_library_saved and mocap_saved and publish_saved,
    }
    payload = {**checks, "status": "passed" if all(checks.values()) else "failed",
               "image_size": [panel.width(), panel.height()],
               "animation_narrow_horizontal_overflow": animation_narrow_horizontal_overflow}
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    panel.close()
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
