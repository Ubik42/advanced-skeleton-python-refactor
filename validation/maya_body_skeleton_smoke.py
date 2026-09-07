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

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
        )
        from adv_py.core import FitBuildSide, FitSkeletonValidationError

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableBodyBuildSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        source = BuildSyntheticBodySourceFit(host).apply(container)
        source_before = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)

        use_case = BuildBodySkeleton(host)
        cmds.file(modified=False)
        preview = use_case.plan(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container)
        snapshot = result.snapshot
        by_name = {joint.name: joint for joint in snapshot.joints}
        side_counts = {
            side.value: sum(joint.side is side for joint in snapshot.joints)
            for side in FitBuildSide
        }
        topology_verified = (
            snapshot.root == "|Root_M"
            and by_name["Hip_R"].parent_path == "|Root_M"
            and by_name["Hip_L"].parent_path == "|Root_M"
            and by_name["Knee_L"].parent_path == "|Root_M|Hip_L"
            and by_name["Wrist_R"].parent_path.endswith("|Elbow_R")
        )
        positions_verified = all(
            all(
                abs(current - wanted) < 1e-5
                for current, wanted in zip(
                    by_name[spec.name].world_position,
                    spec.world_position,
                )
            )
            for spec in result.plan.specs
        )
        neutral_orientation_verified = all(
            all(abs(value) < 1e-5 for value in joint.rotation)
            and all(abs(value) < 1e-5 for value in joint.joint_orient)
            for joint in snapshot.joints
        )
        labels_verified = all(joint.label is not None for joint in snapshot.joints)
        fit_preserved = host.capture_fit_orientation(container) == source_before
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]

        duplicate_blocked = False
        try:
            use_case.apply(container)
        except FitSkeletonValidationError:
            duplicate_blocked = True
        duplicate_unchanged = len(host.capture_body_skeleton("Root_M").joints) == 30

        cmds.undo()
        body_undo_removed = not (cmds.ls("*_M", "*_R", "*_L", type="joint") or [])
        fit_survived_undo = len(host.capture_fit_orientation(container).hierarchy.joints) == 18
        container_survived = cmds.objExists(container)
        marker_survived = cmds.objExists(marker)

        cmds.delete(container, marker)
        remaining = cmds.ls("Root_M", long=True) or []
        remaining += cmds.ls("FitSkeleton", long=True) or []
        remaining += cmds.ls("PortableBodyBuildSelection", long=True) or []
        passed = all(
            (
                len(source.template.hierarchy.joints) == 18,
                preview.ready,
                preview_clean,
                len(preview.specs) == 30,
                len(snapshot.joints) == 30,
                side_counts == {"M": 6, "R": 12, "L": 12},
                topology_verified,
                positions_verified,
                neutral_orientation_verified,
                labels_verified,
                fit_preserved,
                selection_preserved,
                duplicate_blocked,
                duplicate_unchanged,
                body_undo_removed,
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
            "slice": "body_skeleton_materialization",
            "source_joint_count": len(source.template.hierarchy.joints),
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "planned_joint_count": len(preview.specs),
            "created_joint_count": len(snapshot.joints),
            "side_counts": side_counts,
            "topology_verified": topology_verified,
            "world_positions_verified": positions_verified,
            "neutral_orientation_verified": neutral_orientation_verified,
            "labels_verified": labels_verified,
            "fit_source_preserved": fit_preserved,
            "selection_preserved": selection_preserved,
            "duplicate_build_blocked": duplicate_blocked,
            "duplicate_left_body_unchanged": duplicate_unchanged,
            "single_undo_removed_body_skeleton": body_undo_removed,
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
