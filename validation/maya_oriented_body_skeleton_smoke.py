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
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
        )
        from adv_py.core import FitBuildSide, FitSkeletonValidationError

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableAtomicBodySelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        source_before = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)

        use_case = BuildOrientedBodySkeleton(host)
        cmds.file(modified=False)
        preview = use_case.plan(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container)
        snapshot = result.snapshot
        positions_preserved = all(
            _close(
                state.world_position,
                next(
                    spec.world_position
                    for spec in result.plan.build.specs
                    if spec.path == state.path
                ),
                1e-5,
            )
            for state in snapshot.joints
        )
        axes_verified = all(
            _close(
                state.world_axes[axis],
                next(
                    instance.world_axes
                    for instance in result.plan.build.symmetry.instances
                    if instance.output_path == state.path
                )[axis],
            )
            for state in snapshot.joints
            for axis in range(3)
        )
        left_right_handed = all(
            _close(_cross(state.world_axes[0], state.world_axes[1]), state.world_axes[2])
            for state in snapshot.joints
            if state.side is FitBuildSide.LEFT
        )
        fit_preserved = host.capture_fit_orientation(container) == source_before
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]

        duplicate_blocked = False
        try:
            use_case.apply(container)
        except FitSkeletonValidationError:
            duplicate_blocked = True
        duplicate_left_unchanged = len(
            host.capture_body_skeleton("Root_M").joints
        ) == 30

        cmds.undo()
        single_undo_removed_body = not (cmds.ls("Root_M", long=True) or [])
        fit_survived_undo = host.capture_fit_orientation(container) == source_before
        container_survived = cmds.objExists(container)
        marker_survived = cmds.objExists(marker)

        cmds.delete(container, marker)
        remaining = cmds.ls("Root_M", "FitSkeleton", marker, long=True) or []
        passed = all(
            (
                preview.ready,
                preview_clean,
                len(preview.build.specs) == 30,
                len(snapshot.joints) == 30,
                len(result.orientation_changes) == 30,
                positions_preserved,
                axes_verified,
                left_right_handed,
                fit_preserved,
                selection_preserved,
                duplicate_blocked,
                duplicate_left_unchanged,
                single_undo_removed_body,
                fit_survived_undo,
                container_survived,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "atomic_oriented_body_skeleton",
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "planned_joint_count": len(preview.build.specs),
            "created_joint_count": len(snapshot.joints),
            "orientation_change_count": len(result.orientation_changes),
            "world_positions_verified": positions_preserved,
            "world_axes_verified": axes_verified,
            "left_frames_right_handed": left_right_handed,
            "fit_source_preserved": fit_preserved,
            "selection_preserved": selection_preserved,
            "duplicate_build_blocked": duplicate_blocked,
            "duplicate_left_body_unchanged": duplicate_left_unchanged,
            "single_undo_removed_oriented_body": single_undo_removed_body,
            "fit_source_survived_undo": fit_survived_undo,
            "container_survived_undo": container_survived,
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
