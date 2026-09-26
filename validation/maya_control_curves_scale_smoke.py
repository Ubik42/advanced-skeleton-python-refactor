"""Validate post-build control curve scaling through the product controller."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _close(left, right, tolerance=1e-6):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _same_state(left, right):
    return (
        left.control == right.control
        and _close(left.world_matrix, right.world_matrix)
        and len(left.shapes) == len(right.shapes)
        and all(
            old.path == new.path
            and old.degree == new.degree
            and old.form == new.form
            and len(old.points) == len(new.points)
            and all(_close(a, b) for a, b in zip(old.points, new.points))
            for old, new in zip(left.shapes, right.shapes)
        )
    )


def _scaled(before, after, factor):
    return (
        before.control == after.control
        and _close(before.world_matrix, after.world_matrix)
        and len(before.shapes) == len(after.shapes)
        and all(
            old.path == new.path
            and old.degree == new.degree
            and old.form == new.form
            and len(old.points) == len(new.points)
            and all(
                _close(tuple(value * factor for value in old_point), new_point)
                for old_point, new_point in zip(old.points, new.points)
            )
            for old, new in zip(before.shapes, after.shapes)
        )
    )


def main(report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildSyntheticBodySourceFit, CreateFitSkeleton, ResolveBodyCharacter,
        )
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
        character_name = resolver.discover()[0]
        registration = resolver.execute(character_name)
        candidates = tuple(dict.fromkeys(
            channel.node for channel in registration.channels))
        before_all = host.capture_control_curves(candidates, strict=False)
        target = before_all[0].control
        marker = cmds.createNode("transform", name="CurveScaleSelection",
                                 skipSelect=True)
        cmds.select(marker, replace=True)
        selection_before = tuple(cmds.ls(selection=True, long=True) or [])

        explicit_count = controller.control_curves_scale(":", (target,), 1.25)
        explicit_after = host.capture_control_curves((target,), strict=True)[0]
        explicit_scaled = _scaled(before_all[0], explicit_after, 1.25)
        selection_preserved = tuple(
            cmds.ls(selection=True, long=True) or []) == selection_before
        cmds.undo()
        explicit_undo = _same_state(
            before_all[0], host.capture_control_curves((target,), strict=True)[0])
        cmds.redo()
        explicit_redo = _scaled(
            before_all[0], host.capture_control_curves((target,), strict=True)[0], 1.25)
        cmds.undo()

        all_count = controller.control_curves_scale(":", (), 1.1)
        all_after = host.capture_control_curves(candidates, strict=False)
        all_scaled = all_count == len(before_all) and all(
            _scaled(old, new, 1.1) for old, new in zip(before_all, all_after))
        cmds.undo()
        all_undo = all(
            _same_state(old, new)
            for old, new in zip(
                before_all, host.capture_control_curves(candidates, strict=False)))
        cmds.redo()

        with tempfile.TemporaryDirectory(prefix="adv-py-curves-",
                                         dir=report.parent.resolve()) as folder:
            scene = Path(folder) / "scaled.ma"
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(scene), open=True, force=True)
            reopened = host.capture_control_curves(candidates, strict=False)
            reopen_preserved = all(
                _scaled(old, new, 1.1)
                for old, new in zip(before_all, reopened))

        checks = {
            "curves_discovered": len(before_all) > 1,
            "explicit_product_route": explicit_count == 1 and explicit_scaled,
            "selection_preserved": selection_preserved,
            "explicit_single_undo_redo": explicit_undo and explicit_redo,
            "registered_all_product_route": all_scaled,
            "registered_all_single_undo": all_undo,
            "save_reopen_preserved": reopen_preserved,
        }
        payload = {
            **checks,
            "registered_curve_controls": len(before_all),
            "status": "passed" if all(checks.values()) else "failed",
        }
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
