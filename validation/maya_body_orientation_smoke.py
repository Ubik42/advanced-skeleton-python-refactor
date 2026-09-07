from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def _close(left, right, tolerance=1e-4):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _cross(left, right):
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            OrientBodySkeleton,
        )
        from adv_py.core import FitBuildSide

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableBodyOrientationSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        source_before = host.capture_fit_orientation(container)
        neutral = BuildBodySkeleton(host).apply(container).snapshot
        neutral_positions = {
            state.path: state.world_position for state in neutral.joints
        }
        cmds.select(marker, replace=True)

        use_case = OrientBodySkeleton(host)
        cmds.file(modified=False)
        preview = use_case.plan(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container)
        oriented = result.verified
        by_name = {state.name: state for state in oriented.joints}
        positions_preserved = all(
            _close(state.world_position, neutral_positions[state.path], 1e-5)
            for state in oriented.joints
        )
        rotate_zero = all(
            all(abs(value) <= 1e-5 for value in state.rotation)
            for state in oriented.joints
        )
        left_right_handed = all(
            _close(_cross(state.world_axes[0], state.world_axes[1]), state.world_axes[2])
            for state in oriented.joints
            if state.side is FitBuildSide.LEFT
        )
        right = by_name["Scapula_R"].world_axes
        left = by_name["Scapula_L"].world_axes
        scapula_behavior_mirrored = (
            _close(left[0], (-right[0][0], right[0][1], right[0][2]))
            and _close(left[1], (-right[1][0], right[1][1], right[1][2]))
            and _close(left[2], _cross(left[0], left[1]))
        )
        fit_preserved = host.capture_fit_orientation(container) == source_before
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        idempotent = not use_case.plan(container).changes

        cmds.undo()
        restored = host.capture_body_skeleton("Root_M")
        one_undo_restored_neutral = (
            len(restored.joints) == 30
            and all(
                all(abs(value) <= 1e-5 for value in state.rotation)
                and all(abs(value) <= 1e-5 for value in state.joint_orient)
                for state in restored.joints
            )
        )
        fit_survived_undo = host.capture_fit_orientation(container) == source_before
        marker_survived = cmds.objExists(marker)

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls("Root_M", "FitSkeleton", marker, long=True) or []
        passed = all(
            (
                preview_clean,
                bool(preview.changes),
                len(oriented.joints) == 30,
                positions_preserved,
                rotate_zero,
                left_right_handed,
                scapula_behavior_mirrored,
                fit_preserved,
                selection_preserved,
                idempotent,
                one_undo_restored_neutral,
                fit_survived_undo,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_mirror_behavior_orientation",
            "preview_did_not_modify_scene": preview_clean,
            "planned_orientation_changes": len(preview.changes),
            "body_joint_count": len(oriented.joints),
            "world_positions_preserved": positions_preserved,
            "rotate_channels_zero": rotate_zero,
            "left_frames_right_handed": left_right_handed,
            "scapula_behavior_mirrored": scapula_behavior_mirrored,
            "fit_source_preserved": fit_preserved,
            "selection_preserved": selection_preserved,
            "second_plan_idempotent": idempotent,
            "single_undo_restored_neutral_body": one_undo_restored_neutral,
            "fit_source_survived_undo": fit_survived_undo,
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
