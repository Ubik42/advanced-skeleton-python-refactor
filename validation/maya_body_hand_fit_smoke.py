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
            BuildOrientedBodySkeleton,
            BuildSyntheticBodyWithHandSourceFit,
            CreateFitSkeleton,
        )
        from adv_py.core import (
            BODY_HAND_DIGITS,
            BODY_HAND_SEGMENTS,
            FitBuildSide,
            FitSkeletonValidationError,
            body_hand_source_joint_names,
            body_orientation_matches,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableHandFitSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        cmds.select(marker, replace=True)

        fit_use_case = BuildSyntheticBodyWithHandSourceFit(host)
        cmds.file(modified=False)
        fit_preview = fit_use_case.plan(container)
        fit_preview_clean = not bool(cmds.file(query=True, modified=True))
        fit_result = fit_use_case.apply(container)
        fit_snapshot = fit_result.orientation.verified
        fit_by_name = {
            node.short_name: node for node in fit_snapshot.hierarchy.joints
        }
        wrist = fit_by_name["Wrist"]
        wrist_branches = {
            node.short_name
            for node in fit_snapshot.hierarchy.joints
            if node.dag_parent == wrist.path
        }
        expected_branches = {
            f"{digit.value}1" for digit in BODY_HAND_DIGITS
        }
        hand_source_names = set(body_hand_source_joint_names())
        hand_source_paths = {
            node.path
            for node in fit_snapshot.hierarchy.joints
            if node.short_name in hand_source_names
        }
        source_labels_verified = all(
            host.read_joint_label(path).text == "Finger"
            for path in hand_source_paths
        )
        source_positions_before = {
            node.path: node.world_position
            for node in fit_result.orientation.plan.before.hierarchy.joints
        }
        source_positions_after = {
            node.path: node.world_position
            for node in fit_snapshot.hierarchy.joints
        }
        max_source_position_drift = max(
            abs(after - before)
            for path, position in source_positions_after.items()
            for after, before in zip(position, source_positions_before[path])
        )
        source_positions_preserved = max_source_position_drift < 1e-5
        source_rotations_zero = all(
            all(abs(value) < 1e-5 for value in state.rotation)
            for state in fit_snapshot.joints
        )

        duplicate_fit_blocked = False
        try:
            fit_use_case.apply(container)
        except FitSkeletonValidationError:
            duplicate_fit_blocked = True
        duplicate_fit_unchanged = len(
            host.capture_fit_orientation(container).hierarchy.joints
        ) == 38

        body_use_case = BuildOrientedBodySkeleton(host)
        cmds.file(modified=False)
        body_preview = body_use_case.plan(container)
        body_preview_clean = not bool(cmds.file(query=True, modified=True))
        body_result = body_use_case.apply(container)
        body_snapshot = body_result.snapshot
        body_by_name = {joint.name: joint for joint in body_snapshot.joints}
        side_counts = {
            side.value: sum(joint.side is side for joint in body_snapshot.joints)
            for side in FitBuildSide
        }
        hand_body_names = {
            f"{name}_{side}"
            for name in hand_source_names
            for side in ("R", "L")
        }
        hand_topology_verified = all(
            body_by_name[f"{digit.value}1_{side}"].parent_path
            == body_by_name[f"Wrist_{side}"].path
            and body_by_name[f"{digit.value}2_{side}"].parent_path
            == body_by_name[f"{digit.value}1_{side}"].path
            and body_by_name[f"{digit.value}3_{side}"].parent_path
            == body_by_name[f"{digit.value}2_{side}"].path
            and body_by_name[f"{digit.value}End_{side}"].parent_path
            == body_by_name[f"{digit.value}3_{side}"].path
            for digit in BODY_HAND_DIGITS
            for side in ("R", "L")
        )
        hand_labels_verified = all(
            body_by_name[name].label is not None
            and body_by_name[name].label.text == "Finger"
            for name in hand_body_names
        )
        hand_positions_mirrored = all(
            abs(body_by_name[f"{name}_R"].world_position[0]
                + body_by_name[f"{name}_L"].world_position[0]) < 1e-5
            and all(
                abs(body_by_name[f"{name}_R"].world_position[index]
                    - body_by_name[f"{name}_L"].world_position[index]) < 1e-5
                for index in (1, 2)
            )
            for name in hand_source_names
        )
        desired_by_path = {
            instance.output_path: instance.world_axes
            for instance in body_result.plan.build.symmetry.instances
        }
        hand_orientations_verified = all(
            body_orientation_matches(
                desired_by_path[body_by_name[name].path],
                body_by_name[name],
            )
            for name in hand_body_names
        )
        fit_preserved = host.capture_fit_orientation(container) == fit_snapshot
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]

        duplicate_body_blocked = False
        try:
            body_use_case.apply(container)
        except FitSkeletonValidationError:
            duplicate_body_blocked = True
        duplicate_body_unchanged = len(
            host.capture_body_skeleton("Root_M").joints
        ) == 70

        cmds.undo()
        body_undo_removed = not (
            cmds.ls("*_M", "*_R", "*_L", type="joint") or []
        )
        fit_survived_body_undo = len(
            host.capture_fit_orientation(container).hierarchy.joints
        ) == 38
        cmds.undo()
        fit_undo_removed = not (cmds.ls(type="joint") or [])
        container_survived = cmds.objExists(container)
        marker_survived = cmds.objExists(marker)

        cmds.delete(container, marker)
        remaining = cmds.ls("FitSkeleton", long=True) or []
        remaining += cmds.ls("Root_M", long=True) or []
        remaining += cmds.ls("PortableHandFitSelection", long=True) or []
        passed = all((
            fit_preview.ready,
            fit_preview_clean,
            len(fit_preview.template_plan.template.joints) == 38,
            len(fit_preview.predicted_orientation_changes) == 28,
            len(fit_snapshot.hierarchy.joints) == 38,
            wrist_branches == expected_branches,
            len(hand_source_paths) == 20,
            source_labels_verified,
            source_positions_preserved,
            source_rotations_zero,
            duplicate_fit_blocked,
            duplicate_fit_unchanged,
            body_preview.ready,
            body_preview_clean,
            len(body_preview.build.specs) == 70,
            len(body_snapshot.joints) == 70,
            side_counts == {"M": 6, "R": 32, "L": 32},
            len(hand_body_names) == 40,
            hand_topology_verified,
            hand_labels_verified,
            hand_positions_mirrored,
            hand_orientations_verified,
            fit_preserved,
            selection_preserved,
            duplicate_body_blocked,
            duplicate_body_unchanged,
            body_undo_removed,
            fit_survived_body_undo,
            fit_undo_removed,
            container_survived,
            marker_survived,
            not remaining,
        ))
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_hand_fit_and_oriented_skeleton",
            "fit_preview_ready": fit_preview.ready,
            "fit_preview_did_not_modify_scene": fit_preview_clean,
            "source_joint_count": len(fit_snapshot.hierarchy.joints),
            "source_orientation_count": len(
                fit_result.orientation.plan.changes
            ),
            "digit_count": len(BODY_HAND_DIGITS),
            "segments_per_digit": len(BODY_HAND_SEGMENTS),
            "hand_source_joint_count": len(hand_source_paths),
            "wrist_has_five_digit_branches": wrist_branches
            == expected_branches,
            "source_labels_verified": source_labels_verified,
            "source_world_positions_preserved": source_positions_preserved,
            "max_source_position_drift": max_source_position_drift,
            "source_rotations_zero": source_rotations_zero,
            "duplicate_fit_build_blocked": duplicate_fit_blocked,
            "duplicate_fit_left_source_unchanged": duplicate_fit_unchanged,
            "body_preview_ready": body_preview.ready,
            "body_preview_did_not_modify_scene": body_preview_clean,
            "body_joint_count": len(body_snapshot.joints),
            "body_side_counts": side_counts,
            "hand_body_joint_count": len(hand_body_names),
            "hand_topology_verified": hand_topology_verified,
            "hand_labels_verified": hand_labels_verified,
            "hand_positions_mirrored": hand_positions_mirrored,
            "hand_orientations_verified": hand_orientations_verified,
            "fit_source_preserved": fit_preserved,
            "selection_preserved": selection_preserved,
            "duplicate_body_build_blocked": duplicate_body_blocked,
            "duplicate_body_left_skeleton_unchanged": duplicate_body_unchanged,
            "single_undo_removed_body_skeleton": body_undo_removed,
            "fit_survived_body_undo": fit_survived_body_undo,
            "second_undo_removed_fit_tree": fit_undo_removed,
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
