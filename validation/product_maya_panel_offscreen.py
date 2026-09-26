"""Render and exercise the Maya panel without opening a visible window."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

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

    def fit_edit_positions(self, namespace, edits, container):
        self.calls.append(("fit_edit_positions", namespace, edits, container))
        return len(edits)

    def fit_edit_metadata(self, namespace, joints, field, value, *, remove=False):
        self.calls.append(("fit_edit_metadata", namespace, joints, field,
                           value, remove))
        return len(joints)

    def fit_orient(self, namespace, joints, container, **options):
        self.calls.append(("fit_orient", namespace, joints, container, options))
        return len(joints)

    def face_build(self, namespace, specification, control_name, deformer_name):
        self.calls.append(("face_build", namespace, specification.name,
                           control_name, deformer_name))
        return 2

    def body_rebuild(self, namespace, replacement, extensions, *, progress=None):
        self.calls.append(("body_rebuild", namespace, replacement, extensions))
        if progress:
            progress("暂存替换角色并核对需保留的数据")
        return PanelCharacter(namespace, True, 30, 157)

    def spine_replace(self, namespace, replacement, skins, **options):
        self.calls.append(("spine_replace", namespace, replacement, skins, options))
        if options.get("progress"):
            options["progress"]("角色已接管原命名空间")
        return SimpleNamespace(frames=37, fk_groups=7, skin_count=len(skins))

    def control_curves_scale(self, namespace, controls, factor):
        self.calls.append(("control_curves_scale", namespace, controls, factor))
        return len(controls) if controls else 42

    def control_curves_color(self, namespace, controls, mode):
        self.calls.append(("control_curves_color", namespace, controls, mode))
        return len(controls) if controls else 42

    def control_curves_auto_scale(self, namespace, controls, mesh):
        self.calls.append(("control_curves_auto_scale", namespace, controls, mesh))
        return len(controls) if controls else 42

    def control_curves_mirror(self, namespace, controls, source_side):
        self.calls.append(("control_curves_mirror", namespace, controls,
                           source_side))
        return len(controls) if controls else 18

    def control_curves_swap(self, namespace, targets, source):
        self.calls.append(("control_curves_swap", namespace, targets, source))
        return len(targets)

    def control_orient_axis(self, namespace, controls, primary, secondary,
                            curve_unaffected=False, mirror=False,
                            mirrored_behavior=False):
        self.calls.append(("control_orient_axis", namespace, controls,
                           primary, secondary, curve_unaffected, mirror,
                           mirrored_behavior))
        return len(controls)

    def control_orient_world(self, namespace, controls,
                             curve_unaffected=False, mirror=False):
        self.calls.append(("control_orient_world", namespace, controls,
                           curve_unaffected, mirror))
        return len(controls)

    def control_orient_custom_detach(self, namespace):
        self.calls.append(("control_orient_custom_detach", namespace))
        return ("|PreviewA", "|PreviewB")

    def control_orient_custom_attach(self, namespace):
        self.calls.append(("control_orient_custom_attach", namespace))
        return 2

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
    spine_image = report.with_name("maya-panel-spine-replace.png")
    spine_narrow_image = report.with_name("maya-panel-spine-replace-narrow.png")
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
    panel.surface_mapping.setText("C:/temp/redistribution.json")
    panel.surface_mapping_mode.setCurrentIndex(1)
    skin_buttons["预检并转移权重"].click()
    redistribution_dispatch = next((call for call in controller.calls
        if isinstance(call, tuple) and call[0] == "skin_surface_transfer"
        and call[5].get("redistribution_file")), None)
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
    skin_narrow_horizontal_overflow = skin_page.horizontalScrollBar().maximum()
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
    panel.fit_position_edits.setPlainText("Spine1 0 0 8")
    panel.fit_edit_joints.setPlainText("Spine1")
    panel.fit_metadata_value.setText("2")
    panel.fit_orientation_children.setPlainText("Spine1 Chest")
    panel.fit_orientation_mode.setCurrentIndex(1)
    buttons["更新 Fit 位置"].click()
    buttons["更新 Fit 元数据"].click()
    buttons["重新定向 Fit"].click()
    buttons["构建并登记角色"].click()
    panel.control_curve_targets.setPlainText("|hero:Global")
    panel.control_curve_factor.setValue(1.25)
    buttons["缩放控制曲线"].click()
    panel.control_curve_skin.setText("|hero:Skin")
    buttons["按 Skin 自动缩放"].click()
    panel.control_curve_color_mode.setCurrentIndex(1)
    buttons["设置控制曲线颜色"].click()
    buttons["镜像控制曲线形状"].click()
    panel.control_curve_custom_source.setText("|CustomIcon")
    buttons["替换控制器图标"].click()
    panel.control_orient_targets.setPlainText("|hero:ShoulderFK_R")
    panel.control_orient_primary.setCurrentIndex(2)
    panel.control_orient_secondary.setCurrentIndex(0)
    panel.control_orient_curve_unaffected.setChecked(True)
    buttons["设置控制器局部轴"].click()
    buttons["对齐世界坐标轴"].click()
    buttons["分离全部控制器"].click()
    buttons["重新附着全部控制器"].click()
    app.processEvents()
    fit_page = panel.tabs.currentWidget()
    fit_page.verticalScrollBar().setValue(fit_page.verticalScrollBar().maximum())
    app.processEvents()
    panel.render(pixmap)
    rebuild_saved = pixmap.save(str(rebuild_image))
    panel.rebuild_extensions.setPlainText("|Head_M|AdvPy_FaceControls")
    buttons["重建并保留数据"].click()
    app.processEvents()
    panel.spine_replacement.setText("target")
    panel.spine_skins.setPlainText("hero:BodySkin\nhero:FaceSkin")
    panel.spine_meshes.setPlainText("|hero:BodyMesh\n|hero:FaceMesh")
    panel.spine_extensions.setPlainText("|hero:WristControl|hero:Prop")
    panel.spine_assets.setPlainText("|hero:FaceTarget")
    panel.spine_nodes.setPlainText("hero:FaceDriver")
    panel.spine_graph_roots.setPlainText("hero:FaceGraph")
    panel.spine_replace_substeps.setValue(4)
    panel.spine_replace_body_gate.setChecked(True)
    panel.spine_replace_body_limit.setValue(.007)
    buttons["替换脊柱角色并保留数据"].click()
    app.processEvents()
    spine_dispatch = next((call for call in controller.calls
        if isinstance(call, tuple) and call[0] == "spine_replace"), None)
    panel.spine_replace_mode.setCurrentIndex(1)
    ik_fields = (not panel.spine_replace_substeps.isEnabled()
        and panel.spine_replace_substeps.value() == 1
        and panel.spine_replace_mesh_gate.isChecked()
        and not panel.spine_replace_mesh_gate.isEnabled())
    panel.spine_replace_mode.setCurrentIndex(0)
    fit_page.verticalScrollBar().setValue(fit_page.verticalScrollBar().maximum())
    app.processEvents()
    panel.render(pixmap)
    spine_saved = pixmap.save(str(spine_image))
    panel.resize(790, 590)
    app.processEvents()
    narrow_pixmap = QtGui.QPixmap(panel.size())
    panel.render(narrow_pixmap)
    spine_narrow_saved = narrow_pixmap.save(str(spine_narrow_image))
    spine_narrow_horizontal_overflow = fit_page.horizontalScrollBar().maximum()
    panel.resize(950, 710)
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
        "surface_redistribution_dispatches": bool(redistribution_dispatch
            and redistribution_dispatch[5]["redistribution_file"]
                == Path("C:/temp/redistribution.json")
            and redistribution_dispatch[5]["mapping_file"] is None),
        "skin_narrow_no_horizontal_overflow": skin_narrow_horizontal_overflow == 0,
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
        "fit_edit_actions_dispatch": all(call in controller.calls for call in (
            ("fit_edit_positions", "hero", (("Spine1", (0., 0., 8.)),),
             "FitSkeleton"),
            ("fit_edit_metadata", "hero", ("Spine1",), "twist_joints",
             "2", False),
            ("fit_orient", "hero", ("Spine1",), "FitSkeleton",
             {"child_selections": (("Spine1", "Chest"),), "world": True}))),
        "control_curve_scale_dispatches":
            ("control_curves_scale", "hero", ("|hero:Global",), 1.25)
            in controller.calls,
        "control_curve_color_dispatches":
            ("control_curves_color", "hero", ("|hero:Global",), "type")
            in controller.calls,
        "control_curve_auto_scale_dispatches":
            ("control_curves_auto_scale", "hero", ("|hero:Global",),
             "|hero:Skin") in controller.calls,
        "control_curve_mirror_dispatches":
            ("control_curves_mirror", "hero", ("|hero:Global",), "R")
            in controller.calls,
        "control_curve_swap_dispatches":
            ("control_curves_swap", "hero", ("|hero:Global",),
             "|CustomIcon") in controller.calls,
        "control_orient_axis_dispatches":
            ("control_orient_axis", "hero", ("|hero:ShoulderFK_R",),
             "Z", "X", True, True, True) in controller.calls,
        "control_orient_world_dispatches":
            ("control_orient_world", "hero", ("|hero:ShoulderFK_R",),
             True, True) in controller.calls
            and not panel.control_orient_mirrored_behavior.isChecked(),
        "control_orient_custom_dispatches":
            ("control_orient_custom_detach", "hero") in controller.calls
            and ("control_orient_custom_attach", "hero") in controller.calls,
        "role_selection_dispatches_application_action":
            ("body_build", "hero", "FitSkeleton", None, False)
            in controller.calls,
        "rebuild_dispatches_declared_extensions":
            ("body_rebuild", "hero", "CharacterRebuildStage",
             ("|Head_M|AdvPy_FaceControls",)) in controller.calls,
        "spine_replacement_dispatches_complete_inputs": bool(spine_dispatch
            and spine_dispatch[1:4] == ("hero", "target",
                (("hero:BodySkin", "|hero:BodyMesh"),
                 ("hero:FaceSkin", "|hero:FaceMesh")))
            and spine_dispatch[4]["fk_substeps"] == 4
            and spine_dispatch[4]["max_body_error"] == .007
            and spine_dispatch[4]["extensions"]
                == ("|hero:WristControl|hero:Prop",)
            and spine_dispatch[4]["retained_graph_roots"]
                == ("hero:FaceGraph",)),
        "spine_narrow_no_horizontal_overflow":
            spine_narrow_horizontal_overflow == 0,
        "spine_mode_fields_follow_contract": ik_fields
            and panel.spine_replace_substeps.isEnabled()
            and panel.spine_replace_mesh_gate.isEnabled(),
        "result_updates_selected_role": "30 关节" in panel.current.text()
            and "157 通道" in panel.current.text(),
        "success_feedback_visible": "跨段数角色已替换" in panel.status.toPlainText(),
        "offscreen_views_rendered": fit_saved and rebuild_saved
            and spine_saved and spine_narrow_saved
            and skin_saved and skin_transfer_saved and skin_narrow_saved
            and animation_saved and animation_edit_saved and animation_narrow_saved
            and face_saved and face_library_saved and mocap_saved and publish_saved,
    }
    payload = {**checks, "status": "passed" if all(checks.values()) else "failed",
               "image_size": [panel.width(), panel.height()],
               "animation_narrow_horizontal_overflow": animation_narrow_horizontal_overflow,
               "skin_narrow_horizontal_overflow": skin_narrow_horizontal_overflow}
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    panel.close()
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
