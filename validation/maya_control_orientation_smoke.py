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
