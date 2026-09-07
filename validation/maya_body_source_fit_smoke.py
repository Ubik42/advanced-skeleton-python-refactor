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
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
        )
        from adv_py.core import FitSkeletonField, FitSkeletonValidationError

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableBodySourceSelection",
            skipSelect=True,
        )
        host = MayaFitJointHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        cmds.select(marker, replace=True)

        use_case = BuildSyntheticBodySourceFit(host)
        cmds.file(modified=False)
        preview = use_case.plan(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container)
        hierarchy = result.orientation.verified.hierarchy
        by_name = {node.short_name: node for node in hierarchy.joints}

        def children(name: str) -> set[str]:
            parent = by_name[name].path
            return {
                node.short_name
                for node in hierarchy.joints
                if node.dag_parent == parent
            }

        selections = {
            item.joint: item.child
            for item in result.plan.orientation_request.child_selections
        }
        topology_verified = (
            children("Root") == {"Spine1", "Hip"}
            and children("Ankle") == {"Heel", "Toes"}
            and children("Toes")
            == {"FootSideInner", "FootSideOuter", "ToesEnd"}
        )
        branch_policy_verified = (
            selections.get("Root") == "Spine1"
            and selections.get("Ankle") == "Toes"
            and selections.get("Toes") == "ToesEnd"
        )
        before_positions = {
            node.path: node.world_position
            for node in result.orientation.plan.before.hierarchy.joints
        }
        positions_preserved = all(
            all(
                abs(current - previous) < 1e-5
                for current, previous in zip(
                    node.world_position,
                    before_positions[node.path],
                )
            )
            for node in hierarchy.joints
        )
        labels_verified = all(
            host.read_joint_label(path) == spec.label
            for path, spec in zip(
                result.template.joint_paths,
                result.template.plan.template.joints,
            )
        )
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
        duplicate_unchanged = len(cmds.ls(type="joint") or []) == 22

        cmds.undo()
        undo_removed_tree = not (cmds.ls(type="joint") or [])
        container_survived = cmds.objExists(container)
        settings_survived = len(
            host.read_fit_skeleton_settings(container).present_fields
        ) == len(FitSkeletonField)
        marker_survived = cmds.objExists(marker)

        cmds.delete(container, marker)
        remaining = cmds.ls("FitSkeleton", long=True) or []
        remaining += cmds.ls("PortableBodySourceSelection", long=True) or []
        passed = all(
            (
                preview.ready,
                preview_clean,
                len(preview.predicted_orientation_changes) == 15,
                len(hierarchy.joints) == 22,
                len(result.orientation.plan.changes) == 15,
                topology_verified,
                branch_policy_verified,
                positions_preserved,
                labels_verified,
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
            "slice": "synthetic_body_source_fit",
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "predicted_orientation_count": len(
                preview.predicted_orientation_changes
            ),
            "joint_count": len(hierarchy.joints),
            "orientation_count": len(result.orientation.plan.changes),
            "source_leg_and_foot_topology_verified": topology_verified,
            "explicit_branch_policy_verified": branch_policy_verified,
            "world_positions_preserved": positions_preserved,
            "labels_verified": labels_verified,
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
