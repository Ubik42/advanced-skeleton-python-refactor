"""Validate explicit World Match child selection on a five-digit Body."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _matrix(cmds, path):
    return tuple(float(value) for value in cmds.xform(
        path, query=True, worldSpace=True, matrix=True))


def _close(left, right, tolerance=1e-5):
    return len(left) == len(right) and all(
        abs(a - b) <= tolerance for a, b in zip(left, right))


def main(report: Path) -> int:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildSyntheticBodyWithHandSourceFit, CreateFitSkeleton,
            ResolveBodyCharacter)
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(new=True, force=True)
        cmds.upAxis(axis="z", rotateView=False)
        cmds.undoInfo(state=True)
        cmds.namespace(addNamespace="hero")
        host = MayaBodyBuildHost(namespace="hero")
        c = host._cmds
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodyWithHandSourceFit(host).apply(container)
        controller = MayaPanelController()
        controller.body_build("hero")
        resolver = ResolveBodyCharacter(host)
        name = resolver.discover()[0]
        registration = resolver.execute(name)
        controls = tuple(dict.fromkeys(
            channel.node for channel in registration.channels))
        right = next((path for path in controls
                      if path.endswith("|AdvPy_WristFK_R")), None)
        left = next((path for path in controls
                     if path.endswith("|AdvPy_WristFK_L")), None)
        if right is None or left is None:
            raise RuntimeError("五指角色缺少双侧 WristFK 控制器")
        right_children = host._control_orientation_child_joints(right)
        left_children = host._control_orientation_child_joints(left)
        right_child = next(path for path in right_children
                           if path.endswith("|Index1_R"))
        left_child = next(path for path in left_children
                          if path.endswith("|Index1_L"))
        selections = ((right, "Index1_R"), (left, "Index1_L"))
        body_paths = tuple(joint.path for joint in registration.body)
        before_body = tuple(_matrix(c, path) for path in body_paths)
        before = host.capture_control_orientations((right, left))
        selection_before = tuple(c.ls(selection=True, long=True) or ())

        missing_rejected = False
        try:
            controller.control_orient_world_match(
                "hero", (right,), "X", "Y", "Z", True, True)
        except ValueError as exc:
            missing_rejected = "唯一的直接子关节" in str(exc)
        wrong_rejected = False
        try:
            controller.control_orient_world_match(
                "hero", (right,), "X", "Y", "Z", True, True,
                ((right, body_paths[0]), (left, left_child)))
        except ValueError as exc:
            wrong_rejected = "不是唯一直接子关节" in str(exc)
        rejected_body = tuple(_matrix(c, path) for path in body_paths)

        count = controller.control_orient_world_match(
            "hero", (right,), "X", "Y", "Z", True, True, selections)
        after = host.capture_control_orientations((right, left))
        after_body = tuple(_matrix(c, path) for path in body_paths)
        selection_after = tuple(c.ls(selection=True, long=True) or ())
        targets = host.capture_control_orientation_child_targets(
            (right, left), selections)
        aims = []
        for state, (_, child) in zip(after, targets):
            row = state.world_matrix[:3]
            origin = state.world_matrix[12:15]
            delta = tuple(a - b for a, b in zip(child, origin))
            dot = sum(a * b for a, b in zip(row, delta))
            length = (sum(a * a for a in row)
                      * sum(a * a for a in delta)) ** .5
            aims.append(dot / length > .99999)
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            c.setAttr(right + ".rotateY", 10.)
            posed_body = tuple(_matrix(c, path) for path in body_paths)
            c.setAttr(right + ".rotateY", 0.)
            reset_body = tuple(_matrix(c, path) for path in body_paths)
        finally:
            cmds.undoInfo(stateWithoutFlush=True)
        cmds.undo()
        undone = host.capture_control_orientations((right, left))
        cmds.redo()
        redone = host.capture_control_orientations((right, left))
        with tempfile.TemporaryDirectory(
                prefix="adv-py-world-match-hand-",
                dir=report.parent.resolve()) as folder:
            scene = Path(folder) / "hand.ma"
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(scene), open=True, force=True)
            reopened = host.capture_control_orientations((right, left))
            reopened_registration = resolver.execute(name)

        finger_right = next(path for path in controls
                            if path.endswith("|AdvPy_Index1FK_R"))
        finger_left = next(path for path in controls
                           if path.endswith("|AdvPy_Index1FK_L"))
        finger_before = host.capture_control_orientations(
            (finger_right, finger_left))
        finger_body_before = tuple(_matrix(c, path) for path in body_paths)
        finger_count = controller.control_orient_world(
            "hero", (finger_right,), True, True)
        finger_after = host.capture_control_orientations(
            (finger_right, finger_left))
        finger_body_after = tuple(_matrix(c, path) for path in body_paths)
        cmds.undo()
        finger_undo = host.capture_control_orientations(
            (finger_right, finger_left))
        cmds.redo()
        finger_redo = host.capture_control_orientations(
            (finger_right, finger_left))
        with tempfile.TemporaryDirectory(
                prefix="adv-py-world-orient-finger-",
                dir=report.parent.resolve()) as folder:
            scene = Path(folder) / "finger.ma"
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(scene), open=True, force=True)
            finger_reopen = host.capture_control_orientations(
                (finger_right, finger_left))

        original_match_before = host.capture_control_orientations(
            (finger_right, finger_left))
        original_match_body_before = tuple(_matrix(c, path)
                                           for path in body_paths)
        original_match_count = controller.control_orient_world_axis_match(
            "hero", (finger_right,), True, True)
        original_match_after = host.capture_control_orientations(
            (finger_right, finger_left))
        original_match_body_after = tuple(_matrix(c, path)
                                          for path in body_paths)
        cmds.undo()
        original_match_undo = host.capture_control_orientations(
            (finger_right, finger_left))
        cmds.redo()
        original_match_redo = host.capture_control_orientations(
            (finger_right, finger_left))
        with tempfile.TemporaryDirectory(
                prefix="adv-py-original-world-match-finger-",
                dir=report.parent.resolve()) as folder:
            scene = Path(folder) / "finger-match.ma"
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(scene), open=True, force=True)
            original_match_reopen = host.capture_control_orientations(
                (finger_right, finger_left))
        checks = {
            "five_direct_body_children_each_side":
                len(right_children) == len(left_children) == 5
                and cmds.objExists("hero:Wrist_R")
                and not cmds.objExists("Wrist_R"),
            "ambiguous_and_invalid_targets_rejected":
                missing_rejected and wrong_rejected
                and all(_close(a, b) for a, b in zip(
                    before_body, rejected_body)),
            "both_wrist_controls_aim_at_selected_children":
                count == 2 and all(aims),
            "body_bind_pose_and_selection_preserved":
                all(_close(a, b) for a, b in zip(before_body, after_body))
                and selection_before == selection_after,
            "control_still_drives_body":
                any(not _close(a, b) for a, b in zip(
                    after_body, posed_body))
                and all(_close(a, b) for a, b in zip(
                    after_body, reset_body)),
            "single_undo_redo_and_save_reopen":
                undone == before and redone == after
                and reopened == after
                and reopened_registration == registration,
            "world_orient_namespaced_finger_pair":
                finger_count == 2
                and all(state.primary_axis.value == "X"
                        and state.secondary_axis.value == "Z"
                        and not state.mirrored_behavior
                        and all(abs(state.world_matrix[index]) <= 1e-5
                                for index in (1, 2, 4, 6, 8, 9))
                        for state in finger_after)
                and all(_close(a, b) for a, b in zip(
                    finger_body_before, finger_body_after))
                and finger_undo == finger_before
                and finger_redo == finger_after
                and finger_reopen == finger_after,
            "original_world_match_namespaced_finger_pair":
                original_match_count == 2
                and all(state.primary_axis.value == "X"
                        and state.secondary_axis.value == "Z"
                        for state in original_match_after)
                and all(_close(a, b) for a, b in zip(
                    original_match_body_before, original_match_body_after))
                and original_match_undo == original_match_before
                and original_match_redo == original_match_after
                and original_match_reopen == original_match_after,
        }
        payload = {**checks, "status": "passed" if all(
            checks.values()) else "failed"}
        report.write_text(json.dumps(
            payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
