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
        from maya.api import OpenMaya as om
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildSyntheticBodySourceFit, CreateFitSkeleton,
            ResolveBodyCharacter,
        )
        from adv_py.core import (plan_control_orientation_axis,
                                 plan_control_orientation_world,
                                 plan_control_orientation_world_axis_match,
                                 plan_control_orientation_world_match)
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
        opposite_control = next(path for path in candidates
                                if path.endswith("|AdvPy_ShoulderFK_L"))
        opposite_before = host.capture_control_orientations(
            (opposite_control,))[0]
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
        opposite_after = host.capture_control_orientations(
            (opposite_control,))[0]
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

        world_before = host.capture_control_orientations((control,))[0]
        world_expected = plan_control_orientation_world(
            (world_before,), True).changes[0].after
        world_body_before = _world_matrices(cmds, body_paths)
        world_children_before = _world_matrices(cmds, children)
        world_count = controller.control_orient_world(
            ":", (control,), True, False)
        world_after = host.capture_control_orientations((control,))[0]
        world_body_after = _world_matrices(cmds, body_paths)
        world_children_after = _world_matrices(cmds, children)
        world_registry = resolver.execute(name)
        cmds.undo()
        world_undo = host.capture_control_orientations((control,))[0]
        cmds.redo()
        world_redo = host.capture_control_orientations((control,))[0]
        with tempfile.TemporaryDirectory(
                prefix="adv-py-world-orient-",
                dir=report.parent.resolve()) as folder:
            world_scene = Path(folder) / "world.ma"
            cmds.file(rename=str(world_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(world_scene), open=True, force=True)
            world_reopen = host.capture_control_orientations((control,))[0]
            world_reopen_body = _world_matrices(cmds, body_paths)
            world_reopen_registry = resolver.execute(name)

        axis_match_controls = (control, opposite_control)
        axis_match_before = host.capture_control_orientations(
            axis_match_controls)
        axis_match_sources = host.capture_control_orientation_source_axes(
            axis_match_controls)
        axis_match_expected = plan_control_orientation_world_axis_match(
            axis_match_before, axis_match_sources, True, True)
        axis_match_body_before = _world_matrices(cmds, body_paths)
        axis_match_count = controller.control_orient_world_axis_match(
            ":", (control,), True, True)
        axis_match_after = host.capture_control_orientations(
            axis_match_controls)
        axis_match_body_after = _world_matrices(cmds, body_paths)
        cmds.undo()
        axis_match_undo = host.capture_control_orientations(
            axis_match_controls)
        cmds.redo()
        axis_match_redo = host.capture_control_orientations(
            axis_match_controls)
        with tempfile.TemporaryDirectory(
                prefix="adv-py-world-axis-match-",
                dir=report.parent.resolve()) as folder:
            axis_match_scene = Path(folder) / "match.ma"
            cmds.file(rename=str(axis_match_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(axis_match_scene), open=True, force=True)
            axis_match_reopen = host.capture_control_orientations(
                axis_match_controls)

        match_before = host.capture_control_orientations((control,))[0]
        match_targets = host.capture_control_orientation_child_targets((control,))
        match_expected = plan_control_orientation_world_match(
            (match_before,), match_targets, "X", "Y", "Y", True)
        match_body_before = _world_matrices(cmds, body_paths)
        match_children_before = _world_matrices(cmds, children)
        match_count = controller.control_orient_world_match(
            ":", (control,), "X", "Y", "Y", True, False)
        match_after = host.capture_control_orientations((control,))[0]
        match_body_after = _world_matrices(cmds, body_paths)
        match_children_after = _world_matrices(cmds, children)
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            cmds.setAttr(control + ".rotateY", 10.)
            match_body_turned = _world_matrices(cmds, body_paths)
            cmds.setAttr(control + ".rotateY", 0.)
            match_body_reset = _world_matrices(cmds, body_paths)
        finally:
            cmds.undoInfo(stateWithoutFlush=True)
        cmds.undo()
        match_undo = host.capture_control_orientations((control,))[0]
        cmds.redo()
        match_redo = host.capture_control_orientations((control,))[0]
        with tempfile.TemporaryDirectory(
                prefix="adv-py-world-match-",
                dir=report.parent.resolve()) as folder:
            match_scene = Path(folder) / "match.ma"
            cmds.file(rename=str(match_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(match_scene), open=True, force=True)
            match_reopen = host.capture_control_orientations((control,))[0]

        world_match_roles = {}
        toes_parallel_rejected = False
        for role in ("ShoulderFK", "ElbowFK", "HipFK", "KneeFK",
                     "AnkleFK", "ToesFK", "WristFK"):
            paired = next((path for path in candidates
                           if path.endswith(role + "_R")), None)
            if paired is None:
                world_match_roles[role] = "missing registered control"
                continue
            role_before = _world_matrices(cmds, body_paths)
            if role == "ToesFK":
                try:
                    controller.control_orient_world_match(
                        ":", (paired,), "X", "Y", "Y", True, True)
                except ValueError as exc:
                    toes_parallel_rejected = "方向平行" in str(exc)
            applied = False
            try:
                role_count = controller.control_orient_world_match(
                    ":", (paired,), "X", "Y",
                    "Z" if role == "ToesFK" else "Y", True, True)
                applied = True
                role_after = _world_matrices(cmds, body_paths)
                if role_count != 2 or not all(
                        _close(a, b) for a, b in zip(role_before,
                                                     role_after)):
                    raise RuntimeError("镜像数量或 Body 静止复检失败")
                cmds.undo()
                if not all(_close(a, b) for a, b in zip(
                        role_before, _world_matrices(cmds, body_paths))):
                    raise RuntimeError("撤销后 Body 姿态复检失败")
                world_match_roles[role] = "passed"
            except Exception as exc:
                if applied:
                    cmds.undo()
                unchanged = all(_close(a, b) for a, b in zip(
                    role_before, _world_matrices(cmds, body_paths)))
                world_match_roles[role] = (str(exc) if unchanged else
                                           "拒绝后 Body 姿态发生变化：" + str(exc))

        world_orient_roles = {}
        for role in ("ShoulderFK", "ElbowFK", "WristFK", "HipFK",
                     "KneeFK", "AnkleFK", "ToesFK", "ArmIK", "ArmPV",
                     "LegIK", "LegPV", "ToeIK"):
            right = next((path for path in candidates
                          if path.endswith(role + "_R")), None)
            left = next((path for path in candidates
                         if path.endswith(role + "_L")), None)
            if right is None or left is None:
                world_orient_roles[role] = "missing registered pair"
                continue
            role_controls = (right, left)
            role_states = host.capture_control_orientations(role_controls)
            role_expected = plan_control_orientation_world(
                role_states, True, True)
            role_body = _world_matrices(cmds, body_paths)
            applied = False
            try:
                role_count = controller.control_orient_world(
                    ":", (right,), True, True)
                applied = True
                role_after = host.capture_control_orientations(role_controls)
                if role_count != 2 or any(
                        actual.control != change.after.control
                        or actual.primary_axis != change.after.primary_axis
                        or actual.secondary_axis != change.after.secondary_axis
                        or not _close(actual.world_matrix,
                                      change.after.world_matrix)
                        for actual, change in zip(
                            role_after, role_expected.changes)):
                    raise RuntimeError("双侧世界轴或数量复检失败")
                if not all(_close(a, b) for a, b in zip(
                        role_body, _world_matrices(cmds, body_paths))):
                    raise RuntimeError("World Orient 改变了 Body 姿态")
                cmds.undo()
                applied = False
                if host.capture_control_orientations(
                        role_controls) != role_states:
                    raise RuntimeError("World Orient 单次撤销失败")
                world_orient_roles[role] = "passed"
            except Exception as exc:
                if applied:
                    cmds.undo()
                world_orient_roles[role] = str(exc)

        axis_match_roles = {}
        for role in ("ShoulderFK", "ElbowFK", "WristFK", "HipFK",
                     "KneeFK", "AnkleFK", "ToesFK", "ArmIK", "ArmPV",
                     "LegIK", "LegPV", "ToeIK"):
            right = next(path for path in candidates
                         if path.endswith(role + "_R"))
            left = next(path for path in candidates
                        if path.endswith(role + "_L"))
            role_controls = (right, left)
            role_states = host.capture_control_orientations(role_controls)
            role_sources = host.capture_control_orientation_source_axes(
                role_controls)
            role_expected = plan_control_orientation_world_axis_match(
                role_states, role_sources, True, True)
            role_body = _world_matrices(cmds, body_paths)
            applied = False
            try:
                role_count = controller.control_orient_world_axis_match(
                    ":", (right,), True, True)
                applied = True
                role_after = host.capture_control_orientations(role_controls)
                if role_count != 2 or any(
                        not _close(actual.world_matrix,
                                   change.after.world_matrix)
                        or actual.primary_axis.value != "X"
                        or actual.secondary_axis.value != "Z"
                        for actual, change in zip(
                            role_after, role_expected.changes)):
                    raise RuntimeError("双侧 World Match 朝向复检失败")
                if not all(_close(a, b) for a, b in zip(
                        role_body, _world_matrices(cmds, body_paths))):
                    raise RuntimeError("World Match 改变了 Body 姿态")
                cmds.undo()
                applied = False
                if host.capture_control_orientations(
                        role_controls) != role_states:
                    raise RuntimeError("World Match 单次撤销失败")
                axis_match_roles[role] = "passed"
            except Exception as exc:
                if applied:
                    cmds.undo()
                axis_match_roles[role] = str(exc)

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
        fresh_paths = tuple(joint.path for joint in hero_registration.body)
        fresh_body = _world_matrices(hero_host._cmds, fresh_paths)
        with tempfile.TemporaryDirectory(
                prefix="adv-py-orient-baseline-",
                dir=report.parent.resolve()) as folder:
            fresh_scene = Path(folder) / "baseline.ma"
            cmds.file(rename=str(fresh_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(fresh_scene), open=True, force=True)
            fresh_reopen_body = _world_matrices(hero_host._cmds, fresh_paths)
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
        hero_right = next(path for path in hero_controls
                          if "ShoulderFK_R" in path)
        hero_left = next(path for path in hero_controls
                         if "ShoulderFK_L" in path)
        mirror_before = hero_host.capture_control_orientations(
            (hero_right, hero_left))
        mirror_expected = plan_control_orientation_axis(
            mirror_before, "Z", "X", mirror=True).changes
        hero_body_paths = tuple(joint.path for joint in hero_registration.body)
        hero_body_before = _world_matrices(hero_host._cmds, hero_body_paths)
        mirror_count = controller.control_orient_axis(
            "hero", (hero_right,), "Z", "X", False, True)
        mirror_after = hero_host.capture_control_orientations(
            (hero_right, hero_left))
        mirror_body_after = _world_matrices(hero_host._cmds, hero_body_paths)
        mirror_registration = hero_host.read_character_registration()
        cmds.undo()
        mirror_undo = hero_host.capture_control_orientations(
            (hero_right, hero_left))
        cmds.redo()
        mirror_redo = hero_host.capture_control_orientations(
            (hero_right, hero_left))
        with tempfile.TemporaryDirectory(
                prefix="adv-py-mirror-orient-",
                dir=report.parent.resolve()) as folder:
            mirror_scene = Path(folder) / "mirror.ma"
            cmds.file(rename=str(mirror_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(mirror_scene), open=True, force=True)
            mirror_reopen = hero_host.capture_control_orientations(
                (hero_right, hero_left))
            mirror_reopen_registry = hero_host.read_character_registration()
            mirror_reopen_body = _world_matrices(hero_host._cmds,
                                                 hero_body_paths)

        behavior_before = hero_host.capture_control_orientations(
            (hero_right, hero_left))
        behavior_expected = plan_control_orientation_axis(
            behavior_before, "Z", "X", mirror=True,
            mirrored_behavior=True).changes
        behavior_body_before = _world_matrices(hero_host._cmds,
                                               hero_body_paths)
        behavior_count = controller.control_orient_axis(
            "hero", (hero_right,), "Z", "X", False, True, True)
        behavior_after = hero_host.capture_control_orientations(
            (hero_right, hero_left))
        behavior_body_after = _world_matrices(hero_host._cmds,
                                              hero_body_paths)
        behavior_registry = hero_host.read_character_registration()
        cmds.undo()
        behavior_undo = hero_host.capture_control_orientations(
            (hero_right, hero_left))
        behavior_undo_registry = hero_host.read_character_registration()
        cmds.redo()
        behavior_redo = hero_host.capture_control_orientations(
            (hero_right, hero_left))
        behavior_redo_registry = hero_host.read_character_registration()
        with tempfile.TemporaryDirectory(
                prefix="adv-py-mirrored-behavior-",
                dir=report.parent.resolve()) as folder:
            behavior_scene = Path(folder) / "behavior.ma"
            cmds.file(rename=str(behavior_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(behavior_scene), open=True, force=True)
            behavior_reopen = hero_host.capture_control_orientations(
                (hero_right, hero_left))
            behavior_reopen_registry = hero_host.read_character_registration()
            behavior_body_reopen = _world_matrices(hero_host._cmds,
                                                  hero_body_paths)
            elbows = tuple(next(joint.path for joint in hero_registration.body
                                if joint.path.endswith("Elbow_" + side))
                           for side in ("R", "L"))
            elbow_before = tuple(tuple(hero_host._cmds.xform(
                path, query=True, worldSpace=True, translation=True))
                for path in elbows)
            for path in (hero_right, hero_left):
                hero_host._cmds.setAttr(path + ".rotateY", 15.0)
            elbow_after = tuple(tuple(hero_host._cmds.xform(
                path, query=True, worldSpace=True, translation=True))
                for path in elbows)
            for path in (hero_right, hero_left):
                hero_host._cmds.setAttr(path + ".rotateY", 0.0)
            elbow_delta = tuple(tuple(a - b for a, b in zip(after, before))
                                for before, after in
                                zip(elbow_before, elbow_after))
            symmetric_elbow_motion = (
                max(abs(value) for value in elbow_delta[0]) > 1e-3
                and _close(elbow_delta[1], (-elbow_delta[0][0],
                                            elbow_delta[0][1],
                                            elbow_delta[0][2]), 1e-4))
            axis_samples = {}
            probe_paths = tuple(next(joint.path for joint in hero_registration.body
                                     if joint.path.endswith(name + "_" + side))
                                for side in ("R", "L")
                                for name in ("Elbow", "Wrist"))
            probe_local = []
            for path in probe_paths:
                frame = om.MMatrix(hero_host._cmds.xform(
                    path, query=True, worldSpace=True, matrix=True))
                origin = tuple(frame[index] for index in range(12, 15))
                inverse = frame.inverse()
                probe_local.append(tuple(
                    om.MPoint(origin[0] + offset[0],
                              origin[1] + offset[1],
                              origin[2] + offset[2]) * inverse
                    for offset in ((0., 0., 0.), (0., 1., 0.),
                                   (0., 0., 1.))))
            def probe_positions():
                result = []
                for path, points in zip(probe_paths, probe_local):
                    frame = om.MMatrix(hero_host._cmds.xform(
                        path, query=True, worldSpace=True, matrix=True))
                    result.extend(tuple((point * frame)[index]
                                        for index in range(3))
                                  for point in points)
                return tuple(result)
            neutral = probe_positions()
            for axis in "XYZ":
                hero_host._cmds.setAttr(hero_right + ".rotate" + axis, 15.0)
                right_pose = probe_positions()
                hero_host._cmds.setAttr(hero_right + ".rotate" + axis, 0.0)
                errors = []
                for sign in (1., -1.):
                    hero_host._cmds.setAttr(hero_left + ".rotate" + axis,
                                            sign * 15.0)
                    left_pose = probe_positions()
                    hero_host._cmds.setAttr(hero_left + ".rotate" + axis, 0.0)
                    errors.append(sum(sum(abs((left_pose[j][k]-neutral[j][k])
                        - (-1. if k == 0 else 1.) *
                        (right_pose[j-6][k]-neutral[j-6][k]))
                        for k in range(3)) for j in range(6, 12)))
                axis_samples[axis] = errors
            def mixed_pose(control):
                for axis, value in zip("XYZ", (11., -17., 7.)):
                    hero_host._cmds.setAttr(control + ".rotate" + axis, value)
                try:
                    return probe_positions()
                finally:
                    for axis in "XYZ":
                        hero_host._cmds.setAttr(control + ".rotate" + axis, 0.)
            right_mixed = mixed_pose(hero_right)
            left_mixed = mixed_pose(hero_left)
            mixed_error = sum(sum(abs(
                (left_mixed[j][k] - neutral[j][k])
                - (-1. if k == 0 else 1.) *
                (right_mixed[j-6][k] - neutral[j-6][k]))
                for k in range(3)) for j in range(6, 12))
            behavior_body_after_samples = _world_matrices(
                hero_host._cmds, hero_body_paths)

        disable_count = controller.control_orient_axis(
            "hero", (hero_right,), "Z", "X", False, True, False)
        behavior_disabled = hero_host.capture_control_orientations(
            (hero_right, hero_left))
        disable_body = _world_matrices(hero_host._cmds, hero_body_paths)
        disable_registry = hero_host.read_character_registration()
        old_driver = hero_host._cmds.objExists(
            "AdvPy_MirroredBehavior_AdvPy_ShoulderFK_L")
        cmds.undo()
        disable_undo = hero_host.capture_control_orientations(
            (hero_right, hero_left))
        disable_undo_registry = hero_host.read_character_registration()
        cmds.redo()
        disable_redo = hero_host.capture_control_orientations(
            (hero_right, hero_left))
        disable_redo_registry = hero_host.read_character_registration()
        elbow_right = next(path for path in hero_controls
                           if "ElbowFK_R" in path)
        elbow_left = next(path for path in hero_controls
                          if "ElbowFK_L" in path)
        elbow_behavior_count = controller.control_orient_axis(
            "hero", (elbow_right,), "X", "Y", False, True, True)
        elbow_behavior = hero_host.capture_control_orientations(
            (elbow_right, elbow_left))
        elbow_behavior_registry = hero_host.read_character_registration()
        from adv_py.adapters.maya_control_orient_behavior import (
            _paired_body_probes, _sample_probes, _sample_axis,
            _reflection_error)
        coverage = {}
        leg_ik_reopen = False
        scapula_pair = False
        for role in ("WristFK", "HipFK", "KneeFK", "AnkleFK", "ToesFK",
                     "ArmIK", "ArmPV", "LegIK", "LegPV", "ToeIK"):
            if role == "ArmIK":
                for side in ("R", "L"):
                    hero_host._cmds.setAttr(
                        "AdvPy_ArmSettings.armIkFk_" + side, 1.)
            if role == "LegIK":
                for side in ("R", "L"):
                    hero_host._cmds.setAttr(
                        "AdvPy_LegSettings.legIkFk_" + side, 1.)
            paired = next(path for path in hero_controls
                          if path.endswith(role + "_R"))
            role_body_before = _world_matrices(hero_host._cmds,
                                               hero_body_paths)
            try:
                controller.control_orient_axis(
                    "hero", (paired,), "X", "Y", False, True, True)
                role_body_enabled = _world_matrices(hero_host._cmds,
                                                    hero_body_paths)
                opposite = next(path for path in hero_controls
                                if path.endswith(role + "_L"))
                paired_states = hero_host.capture_control_orientations(
                    (paired, opposite))
                if not all(state.mirrored_behavior for state in paired_states):
                    raise RuntimeError("双侧镜像行为状态未写入")
                if role == "LegIK":
                    probes = _paired_body_probes(hero_host)
                    neutral_pose = _sample_probes(hero_host, probes)
                    errors = []
                    for axis in "XYZ":
                        right_pose = _sample_axis(
                            hero_host, probes, paired, axis, 15.)
                        left_pose = _sample_axis(
                            hero_host, probes, opposite, axis, 15.)
                        error, movement = _reflection_error(
                            neutral_pose, right_pose, left_pose)
                        errors.append(error <= max(1e-6, movement * .01))
                    with tempfile.TemporaryDirectory(
                            prefix="adv-py-leg-ik-orient-",
                            dir=report.parent.resolve()) as folder:
                        scene = Path(folder) / "leg_ik.ma"
                        cmds.file(rename=str(scene))
                        cmds.file(save=True, type="mayaAscii", force=True)
                        cmds.file(new=True, force=True)
                        cmds.file(str(scene), open=True, force=True)
                        leg_ik_reopen = (all(errors)
                            and hero_host.read_character_registration().body
                                == hero_registration.body
                            and all(_close(a, b) for a, b in zip(
                                role_body_before, _world_matrices(
                                    hero_host._cmds, hero_body_paths))))
                controller.control_orient_axis(
                    "hero", (paired,), "X", "Y", False, True, False)
                role_body_disabled = _world_matrices(hero_host._cmds,
                                                     hero_body_paths)
                enabled_changed = [path for path, a, b in zip(
                    hero_body_paths, role_body_before, role_body_enabled)
                    if not _close(a, b)]
                disabled_changed = [path for path, a, b in zip(
                    hero_body_paths, role_body_before, role_body_disabled)
                    if not _close(a, b)]
                if enabled_changed or disabled_changed:
                    coverage[role] = ("body_pose_changed: enabled="
                                      + str(enabled_changed[:5])
                                      + ", disabled="
                                      + str(disabled_changed[:5]))
                else:
                    coverage[role] = "passed"
            except Exception as exc:
                coverage[role] = str(exc)
        scapula_right = next(path for path in hero_controls
                             if path.endswith("TorsoScapula_RFK"))
        scapula_left = next(path for path in hero_controls
                            if path.endswith("TorsoScapula_LFK"))
        for side in ("R", "L"):
            hero_host._cmds.setAttr("AdvPy_ArmSettings.armIkFk_" + side, 0.)
            hero_host._cmds.setAttr("AdvPy_LegSettings.legIkFk_" + side, 0.)
        scapula_body_before = _world_matrices(hero_host._cmds,
                                              hero_body_paths)
        scapula_count = 0
        scapula_state = ()
        scapula_ik_errors = {}
        try:
            scapula_count = controller.control_orient_axis(
                "hero", (scapula_right,), "X", "Y", False, True, True)
            scapula_state = hero_host.capture_control_orientations(
                (scapula_right, scapula_left))
            for side in ("R", "L"):
                hero_host._cmds.setAttr(
                    "AdvPy_ArmSettings.armIkFk_" + side, 1.)
            scapula_ik_probes = _paired_body_probes(hero_host)
            scapula_ik_neutral = _sample_probes(hero_host,
                                                scapula_ik_probes)
            scapula_ik_errors = {}
            for axis in "XYZ":
                right_pose = _sample_axis(
                    hero_host, scapula_ik_probes,
                    scapula_right, axis, 10.)
                left_pose = _sample_axis(
                    hero_host, scapula_ik_probes,
                    scapula_left, axis, 10.)
                scapula_ik_errors[axis] = _reflection_error(
                    scapula_ik_neutral, right_pose, left_pose)
            for side in ("R", "L"):
                hero_host._cmds.setAttr(
                    "AdvPy_ArmSettings.armIkFk_" + side, 0.)
            controller.control_orient_axis(
                "hero", (scapula_right,), "X", "Y", False, True, False)
            scapula_pair = (scapula_count == 2
                and all(state.mirrored_behavior for state in scapula_state)
                and all(_close(a, b) for a, b in zip(
                    scapula_body_before,
                    _world_matrices(hero_host._cmds, hero_body_paths))))
        except Exception as exc:
            coverage["TorsoScapula"] = str(exc)
        arm_ik_from_fk = False
        arm_ik_from_fk_error = ""
        try:
            arm_right = next(path for path in hero_controls
                             if path.endswith("ArmIK_R"))
            arm_left = next(path for path in hero_controls
                            if path.endswith("ArmIK_L"))
            arm_body_before = _world_matrices(hero_host._cmds,
                                              hero_body_paths)
            controller.control_orient_axis(
                "hero", (arm_right,), "X", "Y", False, True, True)
            for side in ("R", "L"):
                hero_host._cmds.setAttr(
                    "AdvPy_ArmSettings.armIkFk_" + side, 1.)
            arm_probes = _paired_body_probes(hero_host)
            arm_neutral = _sample_probes(hero_host, arm_probes)
            arm_ik_errors = []
            for axis in "XYZ":
                source = _sample_axis(
                    hero_host, arm_probes, arm_right, axis, 12.)
                target = _sample_axis(
                    hero_host, arm_probes, arm_left, axis, 12.)
                error, movement = _reflection_error(
                    arm_neutral, source, target)
                arm_ik_errors.append(error <= max(1e-6, movement * .01))
            for side in ("R", "L"):
                hero_host._cmds.setAttr(
                    "AdvPy_ArmSettings.armIkFk_" + side, 0.)
            controller.control_orient_axis(
                "hero", (arm_right,), "X", "Y", False, True, False)
            arm_ik_from_fk = (all(arm_ik_errors)
                and all(_close(a, b) for a, b in zip(
                    arm_body_before,
                    _world_matrices(hero_host._cmds, hero_body_paths))))
        except Exception as exc:
            arm_ik_from_fk_error = str(exc)

        checks = {
            "fresh_character_save_reopen": all(
                _close(a, b) for a, b in zip(fresh_body,
                                              fresh_reopen_body)),
            "explicit_registered_route": count == 1,
            "target_world_axis_applied": _close(
                after.world_matrix, expected.world_matrix)
                and after.primary_axis.value == "Z"
                and after.secondary_axis.value == "X",
            "mirror_disabled_leaves_opposite_unchanged":
                opposite_after == opposite_before,
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
            "world_orient_sets_world_axes": world_count == 1
                and _close(world_after.world_matrix,
                           world_expected.world_matrix)
                and world_after.primary_axis.value == "X"
                and world_after.secondary_axis.value == "Z"
                and not world_after.mirrored_behavior,
            "world_orient_preserves_body_and_children": all(
                _close(a, b) for a, b in zip(
                    world_body_before, world_body_after))
                and all(_close(a, b) for a, b in zip(
                    world_children_before, world_children_after))
                and world_registry == registration,
            "world_orient_undo_redo": world_undo == world_before
                and world_redo == world_after,
            "world_orient_save_reopen": world_reopen == world_after
                and all(_close(a, b) for a, b in zip(
                    world_body_before, world_reopen_body))
                and world_reopen_registry == registration,
            "world_axis_match_mirrored_pair": axis_match_count == 2
                and all(_close(actual.world_matrix,
                               change.after.world_matrix)
                        and actual.primary_axis.value == "X"
                        and actual.secondary_axis.value == "Z"
                        for actual, change in zip(
                            axis_match_after, axis_match_expected.changes))
                and all(_close(a, b) for a, b in zip(
                    axis_match_body_before, axis_match_body_after))
                and axis_match_undo == axis_match_before
                and axis_match_redo == axis_match_after
                and axis_match_reopen == axis_match_after,
            "world_match_aims_at_child": match_count == 1
                and _close(match_after.world_matrix,
                           match_expected.changes[0].after.world_matrix)
                and not match_after.mirrored_behavior,
            "world_match_preserves_body_and_children": all(
                _close(a, b) for a, b in zip(
                    match_body_before, match_body_after))
                and all(_close(a, b) for a, b in zip(
                    match_children_before, match_children_after)),
            "world_match_controls_body_after_edit": any(
                not _close(a, b) for a, b in zip(
                    match_body_after, match_body_turned))
                and all(_close(a, b) for a, b in zip(
                    match_body_after, match_body_reset)),
            "world_match_undo_redo_reopen": match_undo == match_before
                and match_redo == match_after
                and match_reopen == match_after,
            "world_match_control_type_probe": world_match_roles,
            "world_match_six_fk_pairs": all(
                world_match_roles[role] == "passed"
                for role in ("ShoulderFK", "ElbowFK", "HipFK",
                             "KneeFK", "AnkleFK", "ToesFK")),
            "world_match_ambiguous_and_parallel_rejected":
                "唯一的直接子关节" in world_match_roles["WristFK"]
                and toes_parallel_rejected,
            "world_orient_control_type_probe": world_orient_roles,
            "world_orient_twelve_control_pairs": all(
                value == "passed" for value in world_orient_roles.values())
                and len(world_orient_roles) == 12,
            "world_axis_match_control_type_probe": axis_match_roles,
            "world_axis_match_twelve_control_pairs": all(
                value == "passed" for value in axis_match_roles.values())
                and len(axis_match_roles) == 12,
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
            "mirror_pair_uses_each_side_frame": mirror_count == 2
                and all(_close(actual.world_matrix, change.after.world_matrix)
                        and actual.mirror for actual, change in
                        zip(mirror_after, mirror_expected))
                and not _close(mirror_after[0].world_matrix,
                               mirror_after[1].world_matrix),
            "mirror_body_and_registry": all(
                _close(old, new) for old, new in
                zip(hero_body_before, mirror_body_after))
                and mirror_registration == hero_registration,
            "mirror_single_undo_redo": all(
                _close(actual.world_matrix, prior.world_matrix)
                and actual.mirror == prior.mirror
                for actual, prior in zip(mirror_undo, mirror_before))
                and all(_close(actual.world_matrix,
                               change.after.world_matrix)
                        and actual.mirror for actual, change in
                        zip(mirror_redo, mirror_expected)),
            "mirror_save_reopen": all(
                _close(actual.world_matrix, change.after.world_matrix)
                and actual.mirror for actual, change in
                zip(mirror_reopen, mirror_expected))
                and mirror_reopen_registry == hero_registration
                and all(_close(a, b) for a, b in zip(
                    mirror_body_after, mirror_reopen_body)),
            "mirrored_behavior_pair_orientation": behavior_count == 2
                and all(_close(actual.world_matrix,
                               change.after.world_matrix)
                        and actual.mirrored_behavior
                        for actual, change in
                        zip(behavior_after, behavior_expected)),
            "mirrored_behavior_body_and_registry": all(
                _close(old, new) for old, new in
                zip(behavior_body_before, behavior_body_after))
                and behavior_registry.body == hero_registration.body
                and behavior_registry.channels == hero_registration.channels
                and all((old.path, old.uuid, old.parent)
                        == (new.path, new.uuid, new.parent)
                        for old, new in zip(hero_registration.nodes,
                                            behavior_registry.nodes)),
            "mirrored_behavior_single_undo_redo": all(
                _close(actual.world_matrix, prior.world_matrix)
                and actual.mirrored_behavior == prior.mirrored_behavior
                for actual, prior in zip(behavior_undo, behavior_before))
                and all(_close(actual.world_matrix,
                               change.after.world_matrix)
                        and actual.mirrored_behavior
                        for actual, change in
                        zip(behavior_redo, behavior_expected))
                and behavior_undo_registry == hero_registration
                and behavior_redo_registry == behavior_registry,
            "mirrored_behavior_save_reopen": all(
                _close(actual.world_matrix, change.after.world_matrix)
                and actual.mirrored_behavior
                for actual, change in
                zip(behavior_reopen, behavior_expected))
                and behavior_reopen_registry == behavior_registry
                and all(_close(a, b) for a, b in zip(
                    behavior_body_before, behavior_body_reopen)),
            "same_local_rotation_is_symmetric": symmetric_elbow_motion
                and all(errors[0] < 1e-4 and errors[1] > 1e-2
                        for errors in axis_samples.values())
                and mixed_error < 1e-4,
            "rotation_sampling_returns_to_bind_pose": all(
                _close(a, b) for a, b in zip(
                    behavior_body_before, behavior_body_after_samples)),
            "mirrored_behavior_disable_restores": disable_count == 2
                and behavior_disabled == behavior_before
                and all(_close(a, b) for a, b in zip(
                    disable_body, behavior_body_before))
                and disable_registry == hero_registration
                and not old_driver,
            "mirrored_behavior_disable_undo_redo":
                disable_undo == behavior_reopen
                and disable_undo_registry == behavior_registry
                and disable_redo == behavior_disabled
                and disable_redo_registry == disable_registry,
            "mirrored_behavior_elbow_pair": elbow_behavior_count == 2
                and all(state.mirrored_behavior for state in elbow_behavior)
                and elbow_behavior_registry.body == hero_registration.body,
            "mirrored_behavior_coverage_pose_retained": all(
                value == "passed" for value in coverage.values())
                and leg_ik_reopen and scapula_pair,
            "arm_ik_calibrated_from_fk_mode": arm_ik_from_fk,
        }
        payload = {
            **checks,
            "control": control,
            "axis_reflection_error": {axis: values[0]
                                      for axis, values in axis_samples.items()},
            "mixed_rotation_reflection_error": mixed_error,
            "control_type_probe": coverage,
            "scapula_ik_axis_error": scapula_ik_errors,
            "arm_ik_from_fk_error": arm_ik_from_fk_error,
            "status": "passed" if all(checks.values()) else "failed",
        }
        report.write_text(json.dumps(
            payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
