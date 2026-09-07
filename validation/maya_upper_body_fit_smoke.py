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
        from adv_py.application import (
            BuildSyntheticUpperBodyFit,
            CreateFitSkeleton,
        )
        from adv_py.core import FitSkeletonField, FitSkeletonValidationError

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableUpperBodySelection",
            skipSelect=True,
        )
        host = MayaFitJointHost()
        container = CreateFitSkeleton(host).apply(
            "FitSkeleton",
            display_radius=3.0,
        ).state.path
        cmds.select(marker, replace=True)

        use_case = BuildSyntheticUpperBodyFit(host)
        cmds.file(modified=False)
        preview = use_case.plan(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container)
        hierarchy = result.orientation.verified.hierarchy
        names = {node.short_name for node in hierarchy.joints}
        spine2 = next(
            node for node in hierarchy.joints if node.short_name == "Spine2"
        )
        branches = {
            node.short_name
            for node in hierarchy.joints
            if node.dag_parent == spine2.path
        }
        spine_change = next(
            change
            for change in result.orientation.plan.changes
            if change.joint == spine2.path
        )
        selected_branch = spine_change.child.rsplit("|", 1)[-1]
        positions_preserved = {
            node.path: node.world_position for node in hierarchy.joints
        } == {
            node.path: node.world_position
            for node in result.orientation.plan.before.hierarchy.joints
        }
        rotations_zero = all(
            all(abs(value) < 1e-5 for value in state.rotation)
            for state in result.orientation.verified.joints
        )
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]

        duplicate_blocked = False
        try:
            use_case.apply(container)
        except FitSkeletonValidationError:
            duplicate_blocked = True
        duplicate_unchanged = len(cmds.ls(type="joint") or []) == 14

        cmds.undo()
        undo_removed_tree = not (cmds.ls(type="joint") or [])
        container_survived = cmds.objExists(container)
        settings_survived = len(
            host.read_fit_skeleton_settings(container).present_fields
        ) == len(FitSkeletonField)
        marker_survived = cmds.objExists(marker)

        cmds.delete(container, marker)
        remaining = cmds.ls("FitSkeleton", long=True) or []
        remaining += cmds.ls("PortableUpperBodySelection", long=True) or []
        passed = all(
            (
                preview.ready,
                preview_clean,
                len(preview.predicted_orientation_changes) == 11,
                len(names) == 14,
                len(result.orientation.plan.changes) == 11,
                branches == {"Neck", "ClavicleLeft", "ClavicleRight"},
                selected_branch == "Neck",
                positions_preserved,
                rotations_zero,
                selection_preserved,
                duplicate_blocked,
                duplicate_unchanged,
                undo_removed_tree,
                container_survived,
                settings_survived,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "oriented_synthetic_upper_body_fit",
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "predicted_orientation_count": len(
                preview.predicted_orientation_changes
            ),
            "joint_count": len(names),
            "orientation_count": len(result.orientation.plan.changes),
            "spine2_branches_verified": branches
            == {"Neck", "ClavicleLeft", "ClavicleRight"},
            "explicit_spine2_branch": selected_branch,
            "world_positions_preserved": positions_preserved,
            "rotations_zero": rotations_zero,
            "selection_preserved": selection_preserved,
            "duplicate_build_blocked": duplicate_blocked,
            "duplicate_left_tree_unchanged": duplicate_unchanged,
            "single_undo_removed_entire_tree": undo_removed_tree,
            "container_survived_undo": container_survived,
            "settings_survived_undo": settings_survived,
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
