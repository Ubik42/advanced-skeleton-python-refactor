"""Validate registered controller local-axis editing in Maya."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _close(left, right, tolerance=1e-5):
    return len(left) == len(right) and all(
        abs(a - b) <= tolerance for a, b in zip(left, right))


def _world_points(cmds, control):
    points = []
    for shape in cmds.listRelatives(
            control, shapes=True, fullPath=True, type="nurbsCurve") or []:
        points.extend(cmds.xform(
            shape + ".cv[*]", query=True, worldSpace=True,
            translation=True) or [])
    return tuple(float(value) for value in points)


def _world_matrices(cmds, paths):
    return tuple(tuple(float(value) for value in cmds.xform(
        path, query=True, worldSpace=True, matrix=True)) for path in paths)


def main(report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildSyntheticBodySourceFit, CreateFitSkeleton,
            ResolveBodyCharacter,
        )
        from adv_py.core import plan_control_orientation_axis
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(new=True, force=True)
        cmds.upAxis(axis="z", rotateView=False)
        cmds.undoInfo(state=True)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        controller = MayaPanelController()
        controller.body_build(":")

        resolver = ResolveBodyCharacter(host)
        name = resolver.discover()[0]
        registration = resolver.execute(name)
        candidates = tuple(dict.fromkeys(
            channel.node for channel in registration.channels))
        control = next(path for path in candidates
                       if "ShoulderFK_R" in path)
        before = host.capture_control_orientations((control,))[0]
        expected = plan_control_orientation_axis(
            (before,), "Z", "X").changes[0].after
        curve_before = _world_points(cmds, control)
        children = tuple(cmds.listRelatives(
            control, children=True, fullPath=True, type="transform") or [])
        child_before = _world_matrices(cmds, children)
        body_paths = tuple(joint.path for joint in registration.body)
        body_before = _world_matrices(cmds, body_paths)
        marker = cmds.createNode("transform", name="OrientSelection",
                                 skipSelect=True)
        cmds.select(marker, replace=True)
        selection_before = tuple(cmds.ls(selection=True, long=True) or [])

        count = controller.control_orient_axis(
            ":", (control.rsplit("|", 1)[-1],), "Z", "X")
        after = host.capture_control_orientations((control,))[0]
        curve_after = _world_points(cmds, control)
        child_after = _world_matrices(cmds, children)
        body_after = _world_matrices(cmds, body_paths)
        registration_after = resolver.execute(name)
        selection_after = tuple(cmds.ls(selection=True, long=True) or [])

        cmds.undo()
        undone = host.capture_control_orientations((control,))[0]
        undo_curve = _world_points(cmds, control)
        undo_registration = resolver.execute(name)
        cmds.redo()
        redone = host.capture_control_orientations((control,))[0]
        redo_registration = resolver.execute(name)

        with tempfile.TemporaryDirectory(
                prefix="adv-py-orient-", dir=report.parent.resolve()) as folder:
            scene = Path(folder) / "oriented.ma"
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(scene), open=True, force=True)
            reopened = host.capture_control_orientations((control,))[0]
            reopen_registration = resolver.execute(name)

            curve_preserved_before = _world_points(cmds, control)
            unaffected_expected = plan_control_orientation_axis(
                (reopened,), "Y", "Z", True).changes[0].after
            unaffected_count = controller.control_orient_axis(
                ":", (control,), "Y", "Z", True)
            unaffected = host.capture_control_orientations((control,))[0]
            unaffected_curve = _world_points(cmds, control)
            unaffected_body = _world_matrices(cmds, body_paths)
            unaffected_registration = resolver.execute(name)
            cmds.undo()
            unaffected_undo = host.capture_control_orientations((control,))[0]
            unaffected_undo_curve = _world_points(cmds, control)
            cmds.redo()
            unaffected_redo = host.capture_control_orientations((control,))[0]
            unaffected_redo_curve = _world_points(cmds, control)
            unaffected_scene = Path(folder) / "curve-unaffected.ma"
            cmds.file(rename=str(unaffected_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(unaffected_scene), open=True, force=True)
            unaffected_reopen = host.capture_control_orientations((control,))[0]
            unaffected_reopen_curve = _world_points(cmds, control)

        all_controls = tuple(state.control for state in
            host.capture_control_curves(candidates, strict=False))
        custom_before = host.capture_control_orientations(all_controls)
        custom_body_before = _world_matrices(cmds, body_paths)
        custom_curve_before = _world_points(cmds, control)
        proxies = controller.control_orient_custom_detach(":")
        detached = host.capture_custom_control_orientation_previews()
        session_exists = cmds.objExists("AdvPy_ControlOrientCustomSession")
        hidden_original = all(
            cmds.getAttr(shape + ".overrideEnabled")
            and not cmds.getAttr(shape + ".overrideVisibility")
            for shape in cmds.listRelatives(
                control, shapes=True, fullPath=True, type="nurbsCurve") or [])
        cmds.undo()
        detach_undo = (not cmds.objExists("AdvPy_ControlOrientCustomSession")
                       and resolver.execute(name) == registration)
        cmds.redo()
        detach_redo = cmds.objExists("AdvPy_ControlOrientCustomSession")
        with tempfile.TemporaryDirectory(
                prefix="adv-py-detached-orient-",
                dir=report.parent.resolve()) as folder:
            detached_scene = Path(folder) / "detached.ma"
            cmds.file(rename=str(detached_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(detached_scene), open=True, force=True)
            detached_reopen = host.capture_custom_control_orientation_previews()
            detached_registration = resolver.execute(name)
        detached = host.capture_custom_control_orientation_previews()
        edit_index = next(index for index, row in enumerate(detached)
                          if row.control == control)
        proxy = proxies[edit_index]
        cmds.setAttr(proxy + ".translateX",
                     cmds.getAttr(proxy + ".translateX") + 1.0)
        try:
            controller.control_orient_custom_attach(":")
        except ValueError:
            moved_proxy_rejected = (
                cmds.objExists("AdvPy_ControlOrientCustomSession")
                and _world_matrices(cmds, body_paths) == custom_body_before)
        else:
            moved_proxy_rejected = False
        cmds.setAttr(proxy + ".translateX",
                     cmds.getAttr(proxy + ".translateX") - 1.0)
        cmds.setAttr(proxy + ".rotateY", 17.0)
        edited = host.capture_custom_control_orientation_previews()
        edit_target = edited[edit_index].preview_matrix
        custom_count = controller.control_orient_custom_attach(":")
        custom_after = host.capture_control_orientations((control,))[0]
        custom_body_after = _world_matrices(cmds, body_paths)
        custom_registry = resolver.execute(name)
        custom_curve_after = _world_points(cmds, control)
        session_removed = not cmds.objExists("AdvPy_ControlOrientCustomSession")
        original_visible = all(
            cmds.getAttr(shape + ".overrideVisibility")
            for shape in cmds.listRelatives(
                control, shapes=True, fullPath=True, type="nurbsCurve") or [])
        cmds.undo()
        attach_undo = cmds.objExists("AdvPy_ControlOrientCustomSession")
        cmds.redo()
        attach_redo = (not cmds.objExists("AdvPy_ControlOrientCustomSession")
                       and _close(host.capture_control_orientations(
                           (control,))[0].world_matrix, edit_target))
        with tempfile.TemporaryDirectory(
                prefix="adv-py-custom-orient-",
                dir=report.parent.resolve()) as folder:
            custom_scene = Path(folder) / "custom.ma"
            cmds.file(rename=str(custom_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(custom_scene), open=True, force=True)
            custom_reopen = host.capture_control_orientations((control,))[0]
            custom_reopen_registry = resolver.execute(name)

        cmds.file(new=True, force=True)
        cmds.upAxis(axis="z", rotateView=False)
        cmds.namespace(addNamespace="hero")
        hero_host = MayaBodyBuildHost(namespace="hero")
        hero_container = CreateFitSkeleton(hero_host).apply().state.path
        BuildSyntheticBodySourceFit(hero_host).apply(hero_container)
        controller.body_build("hero")
        hero_registration = hero_host.read_character_registration()
        hero_controls = tuple(state.control for state in
            hero_host.capture_control_curves(tuple(dict.fromkeys(
                channel.node for channel in hero_registration.channels)),
                strict=False))
        hero_proxies = controller.control_orient_custom_detach("hero")
        hero_previews = hero_host.capture_custom_control_orientation_previews()
        hero_host._cmds.setAttr(hero_proxies[0] + ".rotateY", 11.0)
        hero_target = hero_host.capture_custom_control_orientation_previews()[
            0].preview_matrix
        hero_attached = controller.control_orient_custom_attach("hero")
        hero_after = hero_host.capture_control_orientations(
            (hero_previews[0].control,))[0]
        namespaced_custom = (
            len(hero_proxies) == len(hero_controls)
            and hero_attached == len(hero_controls)
            and _close(hero_after.world_matrix, hero_target)
            and hero_host.read_character_registration() == hero_registration
            and not hero_host._cmds.objExists(
                "AdvPy_ControlOrientCustomSession"))

        checks = {
            "explicit_registered_route": count == 1,
            "target_world_axis_applied": _close(
                after.world_matrix, expected.world_matrix)
                and after.primary_axis.value == "Z"
                and after.secondary_axis.value == "X",
            "curve_follows_orientation": not _close(
                curve_before, curve_after),
            "direct_children_compensated": all(
                _close(old, new) for old, new in
                zip(child_before, child_after)),
            "body_bind_pose_preserved": all(
                _close(old, new) for old, new in
                zip(body_before, body_after)),
            "registration_remains_valid": registration_after == registration,
            "selection_preserved": selection_after == selection_before,
            "single_undo_restores": _close(
                undone.world_matrix, before.world_matrix)
                and undone.primary_axis.value == "X"
                and undone.secondary_axis.value == "Y"
                and _close(undo_curve, curve_before)
                and undo_registration == registration,
            "single_redo_reapplies": _close(
                redone.world_matrix, expected.world_matrix)
                and redone.primary_axis.value == "Z"
                and redone.secondary_axis.value == "X"
                and redo_registration == registration,
            "save_reopen_preserved": _close(
                reopened.world_matrix, expected.world_matrix)
                and reopened.primary_axis.value == "Z"
                and reopened.secondary_axis.value == "X"
                and reopen_registration == registration,
            "curve_unaffected_world_shape": unaffected_count == 1
                and unaffected.curve_unaffected
                and _close(unaffected.world_matrix,
                           unaffected_expected.world_matrix)
                and _close(curve_preserved_before, unaffected_curve),
            "curve_unaffected_body_and_registry": all(
                _close(old, new) for old, new in
                zip(body_before, unaffected_body))
                and unaffected_registration == registration,
            "curve_unaffected_undo_redo": _close(
                unaffected_undo.world_matrix, reopened.world_matrix)
                and not unaffected_undo.curve_unaffected
                and _close(curve_preserved_before, unaffected_undo_curve)
                and _close(unaffected_redo.world_matrix,
                           unaffected_expected.world_matrix)
                and unaffected_redo.curve_unaffected
                and _close(curve_preserved_before, unaffected_redo_curve),
            "curve_unaffected_save_reopen": _close(
                unaffected_reopen.world_matrix,
                unaffected_expected.world_matrix)
                and unaffected_reopen.curve_unaffected
                and _close(curve_preserved_before, unaffected_reopen_curve),
            "custom_all_controls_detach": len(proxies) == len(all_controls)
                and len(detached) == len(all_controls) and session_exists
                and hidden_original,
            "custom_detach_single_undo_redo": detach_undo and detach_redo,
            "custom_detached_save_reopen":
                len(detached_reopen) == len(all_controls)
                and detached_registration == registration,
            "custom_moved_proxy_rejected": moved_proxy_rejected,
            "custom_attach_orientation": custom_count == len(all_controls)
                and _close(custom_after.world_matrix, edit_target)
                and session_removed and original_visible,
            "custom_attach_body_and_registry": all(
                _close(old, new) for old, new in
                zip(custom_body_before, custom_body_after))
                and custom_registry == registration
                and _close(custom_curve_before, custom_curve_after),
            "custom_attach_single_undo_redo": attach_undo and attach_redo,
            "custom_save_reopen": _close(custom_reopen.world_matrix,
                                          edit_target)
                and custom_reopen_registry == registration,
            "custom_namespaced_character": namespaced_custom,
        }
        payload = {
            **checks,
            "control": control,
            "status": "passed" if all(checks.values()) else "failed",
        }
        report.write_text(json.dumps(
            payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
