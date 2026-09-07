from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def _close(left, right, tolerance=1e-5):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


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
            EditFitJointPositions,
            InspectBodyRebuildSafety,
            ReplaceOwnedBodySkeleton,
        )
        from adv_py.core import FitJointPositionEdit, FitJointPositionPatch

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableBodyReplaceSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        initial = BuildOrientedBodySkeleton(host).apply(container).snapshot
        initial_root_uuid = cmds.ls(initial.root, uuid=True)[0]
        initial_hip = next(
            state.world_position for state in initial.joints if state.name == "Hip_R"
        )

        fit_before = host.capture_fit_hierarchy(container)
        hip_source = next(
            node for node in fit_before.joints if node.short_name == "Hip"
        )
        moved_local = (
            hip_source.local_position[0] - 0.75,
            hip_source.local_position[1],
            hip_source.local_position[2],
        )
        EditFitJointPositions(host).apply(
            FitJointPositionPatch(
                (FitJointPositionEdit(hip_source.path, moved_local),)
            ),
            container,
        )
        fit_after_edit = host.capture_fit_orientation(container)
        moved_source_world = next(
            node.world_position
            for node in fit_after_edit.hierarchy.joints
            if node.short_name == "Hip"
        )
        cmds.select(marker, replace=True)

        use_case = ReplaceOwnedBodySkeleton(host)
        cmds.file(modified=False)
        preview = use_case.plan(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container)
        replaced = result.build.snapshot
        replaced_root_uuid = cmds.ls(replaced.root, uuid=True)[0]
        replaced_hip = next(
            state.world_position for state in replaced.joints if state.name == "Hip_R"
        )
        root_recreated = replaced_root_uuid != initial_root_uuid
        fit_change_applied = (
            not _close(replaced_hip, initial_hip)
            and _close(replaced_hip, moved_source_world)
        )
        post_audit_safe = InspectBodyRebuildSafety(host).execute(
            container
        ).safe_to_replace
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        fit_preserved = host.capture_fit_orientation(container) == fit_after_edit

        cmds.undo()
        restored = host.capture_body_skeleton("Root_M")
        restored_root_uuid = cmds.ls(restored.root, uuid=True)[0]
        restored_hip = next(
            state.world_position for state in restored.joints if state.name == "Hip_R"
        )
        single_undo_restored_previous_body = (
            restored_root_uuid == initial_root_uuid
            and _close(restored_hip, initial_hip)
        )
        edited_fit_survived_undo = (
            host.capture_fit_orientation(container) == fit_after_edit
        )
        marker_survived = cmds.objExists(marker)

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            marker,
            long=True,
        ) or []
        passed = all(
            (
                preview.ready,
                preview_clean,
                len(preview.owned_name_collisions) == 30,
                not preview.build.build.name_collisions,
                root_recreated,
                fit_change_applied,
                len(replaced.joints) == 30,
                post_audit_safe,
                selection_preserved,
                fit_preserved,
                single_undo_restored_previous_body,
                edited_fit_survived_undo,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "owned_body_atomic_replace",
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "owned_name_collision_count": len(preview.owned_name_collisions),
            "foreign_name_collision_count": len(preview.build.build.name_collisions),
            "root_uuid_changed": root_recreated,
            "edited_fit_position_applied": fit_change_applied,
            "replacement_joint_count": len(replaced.joints),
            "replacement_safety_audit_passed": post_audit_safe,
            "selection_preserved": selection_preserved,
            "fit_source_preserved": fit_preserved,
            "single_undo_restored_previous_root_uuid_and_position": (
                single_undo_restored_previous_body
            ),
            "edited_fit_survived_undo": edited_fit_survived_undo,
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
