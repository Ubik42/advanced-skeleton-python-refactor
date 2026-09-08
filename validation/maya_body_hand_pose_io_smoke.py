from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def close(left, right, tolerance=2e-3):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def position(cmds, path):
    return tuple(float(value) for value in cmds.xform(
        path,
        query=True,
        worldSpace=True,
        translation=True,
    ))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyCharacterRig,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodyWithHandSourceFit,
            CreateFitSkeleton,
            ExportBodyHandPose,
            ImportBodyHandPose,
            InspectBodyHandPoseRig,
            InspectBodyRebuildSafety,
        )
        from adv_py.application.body_rig_validation import body_bind_pose_matches
        from adv_py.core import (
            BodyHandDigit,
            FitBuildSide,
            body_hand_pose_document_from_snapshot,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="HandPoseIoSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodyWithHandSourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit_before = host.capture_fit_orientation(container)
        body_by_name = {joint.name: joint.path for joint in body_before.joints}
        cmds.select(marker, replace=True)

        rig = BuildBodyCharacterRig(host).apply(container)
        hand = rig.hand
        if hand is None:
            raise RuntimeError("70 关节 Character 未构建 Hand")
        roots = {spec.side: spec.path for spec in hand.plan.controls.roots}
        controls = {
            spec.control_name: spec.control_path
            for spec in hand.plan.controls.controls
        }
        right_index_end = body_by_name["IndexEnd_R"]
        left_thumb_end = body_by_name["ThumbEnd_L"]

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{roots[FitBuildSide.RIGHT]}.handCurl", 28.0)
        cmds.setAttr(f"{roots[FitBuildSide.RIGHT]}.indexCurl", 9.0)
        cmds.setAttr(f"{roots[FitBuildSide.LEFT]}.handSpread", -12.0)
        cmds.setAttr(f"{controls['AdvPy_Index1FK_R']}.rotateX", 2.0)
        cmds.setAttr(f"{controls['AdvPy_Index1FK_R']}.rotateY", 3.0)
        cmds.setAttr(f"{controls['AdvPy_Index1FK_R']}.rotateZ", 11.0)
        cmds.setAttr(f"{controls['AdvPy_Thumb2FK_L']}.rotateX", -4.0)
        cmds.setAttr(f"{controls['AdvPy_Thumb2FK_L']}.rotateY", 5.0)
        cmds.setAttr(f"{controls['AdvPy_Thumb2FK_L']}.rotateZ", -6.0)
        source_inspection = InspectBodyHandPoseRig(host).execute()
        source_document = body_hand_pose_document_from_snapshot(
            source_inspection.channels
        )
        source_index_position = position(cmds, right_index_end)
        source_thumb_position = position(cmds, left_thumb_end)

        with tempfile.TemporaryDirectory(prefix="adv_py_hand_pose_") as directory:
            pose_path = Path(directory) / "gesture.json"
            cmds.file(modified=False)
            export_result = ExportBodyHandPose(host).apply(pose_path)
            export_did_not_modify_scene = not bool(
                cmds.file(query=True, modified=True)
            )
            selection_after_export = cmds.ls(selection=True) or []
            text = pose_path.read_text(encoding="utf-8")
            semantic_document_has_no_maya_paths = (
                "|Root_M" not in text
                and "AdvPy_" not in text
                and '"side": "R"' in text
                and '"digit": "Index"' in text
            )
            overwrite_refused = False
            try:
                ExportBodyHandPose(host).apply(pose_path)
            except ValueError:
                overwrite_refused = True

            cmds.setAttr(f"{roots[FitBuildSide.RIGHT]}.handCurl", -20.0)
            cmds.setAttr(f"{roots[FitBuildSide.RIGHT]}.indexCurl", -7.0)
            cmds.setAttr(f"{roots[FitBuildSide.LEFT]}.handSpread", 8.0)
            cmds.setAttr(f"{controls['AdvPy_Index1FK_R']}.rotateX", -1.0)
            cmds.setAttr(f"{controls['AdvPy_Index1FK_R']}.rotateY", -2.0)
            cmds.setAttr(f"{controls['AdvPy_Index1FK_R']}.rotateZ", -3.0)
            cmds.setAttr(f"{controls['AdvPy_Thumb2FK_L']}.rotateX", 6.0)
            cmds.setAttr(f"{controls['AdvPy_Thumb2FK_L']}.rotateY", -5.0)
            cmds.setAttr(f"{controls['AdvPy_Thumb2FK_L']}.rotateZ", 4.0)
            mutated_inspection = InspectBodyHandPoseRig(host).execute()
            mutated_document = body_hand_pose_document_from_snapshot(
                mutated_inspection.channels
            )
            mutated_index_position = position(cmds, right_index_end)
            mutated_thumb_position = position(cmds, left_thumb_end)

            cmds.undoInfo(stateWithoutFlush=True)
            cmds.file(modified=False)
            preview = ImportBodyHandPose(host).plan(pose_path)
            import_preview_did_not_modify_scene = not bool(
                cmds.file(query=True, modified=True)
            )
            import_result = ImportBodyHandPose(host).apply(pose_path)
            restored_inspection = InspectBodyHandPoseRig(host).execute()
            restored_document = body_hand_pose_document_from_snapshot(
                restored_inspection.channels
            )
            restored_index_position = position(cmds, right_index_end)
            restored_thumb_position = position(cmds, left_thumb_end)
            repeated = ImportBodyHandPose(host).apply(pose_path)
            selection_after_import = cmds.ls(selection=True) or []

            cmds.undo()
            undo_inspection = InspectBodyHandPoseRig(host).execute()
            undo_document = body_hand_pose_document_from_snapshot(
                undo_inspection.channels
            )
            undo_index_position = position(cmds, right_index_end)
            undo_thumb_position = position(cmds, left_thumb_end)
        temporary_pose_removed = not pose_path.exists()

        rebuild_blocked = not InspectBodyRebuildSafety(host).execute(
            container
        ).safe_to_replace
        cmds.undo()
        remaining_rig = (
            (cmds.ls("AdvPy_Arm*", long=True) or [])
            + (cmds.ls("AdvPy_Leg*", long=True) or [])
            + (cmds.ls("AdvPy_Foot*", long=True) or [])
            + (cmds.ls("AdvPy_Hand*", long=True) or [])
            + (cmds.ls("AdvPy_Thumb*", long=True) or [])
            + (cmds.ls("AdvPy_Index*", long=True) or [])
            + (cmds.ls("AdvPy_Middle*", long=True) or [])
            + (cmds.ls("AdvPy_Ring*", long=True) or [])
            + (cmds.ls("AdvPy_Pinky*", long=True) or [])
            + (cmds.ls("AdvPy_Character*", long=True) or [])
            + (cmds.ls("AdvPy_Global*", long=True) or [])
        )
        body_after_undo = host.capture_body_skeleton("Root_M")
        body_survived = (
            len(body_after_undo.joints) == 70
            and body_bind_pose_matches(body_before, body_after_undo)
        )
        fit_survived = host.capture_fit_orientation(container) == fit_before
        rebuild_safe_again = InspectBodyRebuildSafety(host).execute(
            container
        ).safe_to_replace
        marker_survived = cmds.objExists(marker)

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_*",
            marker,
            long=True,
        ) or []
        checks = {
            "semantic_schema_has_fourteen_aggregate_values": (
                len(source_document.aggregates) == 14
            ),
            "semantic_schema_has_thirty_fk_rotations": (
                len(source_document.controls) == 30
            ),
            "semantic_document_has_no_maya_paths": (
                semantic_document_has_no_maya_paths
            ),
            "export_matches_scene_pose": export_result.plan.document == source_document,
            "export_did_not_modify_scene": export_did_not_modify_scene,
            "export_preserved_selection": selection_after_export == [marker],
            "export_refused_overwrite": overwrite_refused,
            "import_preview_found_five_changes": preview.changed_channel_count == 5,
            "import_preview_did_not_modify_scene": import_preview_did_not_modify_scene,
            "import_applied_five_changes": import_result.changed_channel_count == 5,
            "import_restored_exact_semantic_pose": restored_document == source_document,
            "import_restored_real_finger_positions": (
                close(restored_index_position, source_index_position)
                and close(restored_thumb_position, source_thumb_position)
                and not close(mutated_index_position, source_index_position)
                and not close(mutated_thumb_position, source_thumb_position)
            ),
            "repeat_import_is_noop": repeated.changed_channel_count == 0,
            "import_preserved_selection": selection_after_import == [marker],
            "one_undo_restored_preimport_pose": (
                undo_document == mutated_document
                and close(undo_index_position, mutated_index_position)
                and close(undo_thumb_position, mutated_thumb_position)
            ),
            "temporary_pose_file_removed": temporary_pose_removed,
            "rebuild_blocked_while_character_exists": rebuild_blocked,
            "next_undo_removed_complete_character": not remaining_rig,
            "character_undo_preserved_seventy_joint_body": body_survived,
            "character_undo_preserved_fit": fit_survived,
            "character_undo_restored_rebuild_safety": rebuild_safe_again,
            "unrelated_node_survived": marker_survived,
            "cleanup": not remaining,
        }
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_hand_pose_document_io",
            **checks,
            "content_sha256": source_document.content_sha256,
            "exported_bytes": export_result.bytes_written,
            "changed_channel_count": import_result.changed_channel_count,
            "remaining_rig_nodes_after_undo": remaining_rig,
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
