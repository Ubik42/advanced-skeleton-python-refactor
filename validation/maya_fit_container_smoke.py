from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaFitJointHost
        from adv_py.application import CreateFitSkeleton
        from adv_py.core import FitSkeletonField, FitSkeletonValidationError, FitUpAxis

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode("transform", name="PortableSelectionMarker")
        cmds.select(marker, replace=True)

        host = MayaFitJointHost()
        use_case = CreateFitSkeleton(host)
        cmds.file(modified=False)
        preview = use_case.plan(
            "PortableFitContainer",
            display_radius=2.5,
            vis_gap_default=0.6,
        )
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(
            "PortableFitContainer",
            display_radius=2.5,
            vis_gap_default=0.6,
        )
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        created_once = cmds.ls("PortableFitContainer", long=True) == [
            "|PortableFitContainer"
        ]
        settings_complete = len(result.settings.present_fields) == len(
            FitSkeletonField
        )
        defaults_verified = (
            result.settings.value(FitSkeletonField.VIS_GAP) == 0.6
            and result.settings.value(FitSkeletonField.LOCK_CENTER_JOINTS) is True
        )
        z_up_used = preview.spec.up_axis is FitUpAxis.Z

        collision_blocked = False
        try:
            use_case.apply("PortableFitContainer")
        except FitSkeletonValidationError:
            collision_blocked = True
        collision_preserved = cmds.ls("PortableFitContainer", long=True) == [
            "|PortableFitContainer"
        ]

        cmds.undo()
        undo_removed_creation = not cmds.objExists("PortableFitContainer")
        marker_survived = cmds.objExists(marker)
        cmds.delete(marker)
        remaining = cmds.ls("PortableFit*", long=True) or []

        passed = all(
            (
                preview.ready,
                preview_clean,
                selection_preserved,
                created_once,
                settings_complete,
                defaults_verified,
                z_up_used,
                collision_blocked,
                collision_preserved,
                undo_removed_creation,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_skeleton_container_create",
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "scene_up_axis_used": z_up_used,
            "selection_preserved": selection_preserved,
            "created_exactly_once": created_once,
            "settings_complete": settings_complete,
            "defaults_verified": defaults_verified,
            "collision_blocked": collision_blocked,
            "collision_left_existing_node": collision_preserved,
            "single_undo_removed_creation": undo_removed_creation,
            "unrelated_node_survived": marker_survived,
            "cleanup": not remaining,
            "remaining_nodes": remaining,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if passed else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return 0 if passed else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
