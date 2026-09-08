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


def scene_channels(inspection):
    roots = {spec.side.value: spec.path for spec in inspection.hand.roots}
    controls = {
        spec.control_name.rsplit(":", 1)[-1]: spec.control_path
        for spec in inspection.hand.controls
    }
    joints = {joint.name: joint.path for joint in inspection.body.joints}
    return roots, controls, joints


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
        )
        from adv_py.core import body_hand_pose_document_from_snapshot

        host = MayaBodyBuildHost()
        with tempfile.TemporaryDirectory(
            prefix="adv_py_hand_namespace_"
        ) as directory:
            directory_path = Path(directory)
            asset_path = directory_path / "synthetic-hand-rig.ma"
            pose_path = directory_path / "hand-pose.json"

            cmds.file(new=True, force=True)
            cmds.undoInfo(state=True)
            cmds.upAxis(axis="z", rotateView=False)
            container = CreateFitSkeleton(host).apply().state.path
            BuildSyntheticBodyWithHandSourceFit(host).apply(container)
            BuildOrientedBodySkeleton(host).apply(container)
            character = BuildBodyCharacterRig(host).apply(container)
            if character.hand is None:
                raise RuntimeError("合成 70 关节角色未构建 Hand")
            source = InspectBodyHandPoseRig(host).execute()
            source_roots, source_controls, _source_joints = scene_channels(source)
            cmds.setAttr(f"{source_roots['R']}.handCurl", 26.0)
            cmds.setAttr(f"{source_roots['R']}.indexCurl", 8.0)
            cmds.setAttr(f"{source_roots['L']}.handSpread", -11.0)
            cmds.setAttr(f"{source_controls['AdvPy_Index1FK_R']}.rotateX", 2.0)
            cmds.setAttr(f"{source_controls['AdvPy_Index1FK_R']}.rotateY", 3.0)
            cmds.setAttr(f"{source_controls['AdvPy_Index1FK_R']}.rotateZ", 10.0)
            cmds.setAttr(f"{source_controls['AdvPy_Thumb2FK_L']}.rotateX", -4.0)
            cmds.setAttr(f"{source_controls['AdvPy_Thumb2FK_L']}.rotateY", 5.0)
            cmds.setAttr(f"{source_controls['AdvPy_Thumb2FK_L']}.rotateZ", -6.0)
            cmds.file(rename=str(asset_path))
            cmds.file(save=True, type="mayaAscii", force=True)

            cmds.file(new=True, force=True)
            cmds.file(
                str(asset_path),
                reference=True,
                namespace="RigA",
                mergeNamespacesOnClash=False,
            )
            cmds.file(
                str(asset_path),
                reference=True,
                namespace="RigB",
                mergeNamespacesOnClash=False,
            )
            marker = cmds.createNode(
                "transform",
                name="NamespacePoseSelection",
                skipSelect=True,
            )
            cmds.select(marker, replace=True)

            rig_a = InspectBodyHandPoseRig(host).execute(
                body_root_name="RigA:Root_M"
            )
            roots_a, controls_a, joints_a = scene_channels(rig_a)
            source_document = body_hand_pose_document_from_snapshot(
                rig_a.channels
            )
            source_index = position(cmds, joints_a["IndexEnd_R"])
            source_thumb = position(cmds, joints_a["ThumbEnd_L"])
            cmds.file(modified=False)
            export_result = ExportBodyHandPose(host).apply(
                pose_path,
                body_root_name="RigA:Root_M",
            )
            export_read_only = not bool(cmds.file(query=True, modified=True))
            text = pose_path.read_text(encoding="utf-8")
            namespace_free_document = (
                "RigA" not in text
                and "RigB" not in text
                and "|Root_M" not in text
            )

            rig_b = InspectBodyHandPoseRig(host).execute(
                body_root_name="RigB:Root_M"
            )
            roots_b, controls_b, joints_b = scene_channels(rig_b)
            cmds.undoInfo(stateWithoutFlush=False)
            cmds.setAttr(f"{roots_b['R']}.handCurl", -19.0)
            cmds.setAttr(f"{roots_b['R']}.indexCurl", -7.0)
            cmds.setAttr(f"{roots_b['L']}.handSpread", 9.0)
            cmds.setAttr(f"{controls_b['AdvPy_Index1FK_R']}.rotateX", -1.0)
            cmds.setAttr(f"{controls_b['AdvPy_Index1FK_R']}.rotateY", -2.0)
            cmds.setAttr(f"{controls_b['AdvPy_Index1FK_R']}.rotateZ", -3.0)
            cmds.setAttr(f"{controls_b['AdvPy_Thumb2FK_L']}.rotateX", 6.0)
            cmds.setAttr(f"{controls_b['AdvPy_Thumb2FK_L']}.rotateY", -5.0)
            cmds.setAttr(f"{controls_b['AdvPy_Thumb2FK_L']}.rotateZ", 4.0)
            mutated_b = InspectBodyHandPoseRig(host).execute(
                body_root_name="RigB:Root_M"
            )
            mutated_document = body_hand_pose_document_from_snapshot(
                mutated_b.channels
            )
            mutated_index = position(cmds, joints_b["IndexEnd_R"])
            mutated_thumb = position(cmds, joints_b["ThumbEnd_L"])
            a_before_import = body_hand_pose_document_from_snapshot(
                InspectBodyHandPoseRig(host).execute(
                    body_root_name="RigA:Root_M"
                ).channels
            )

            cmds.undoInfo(stateWithoutFlush=True)
            cmds.file(modified=False)
            preview = ImportBodyHandPose(host).plan(
                pose_path,
                body_root_name="RigB:Root_M",
            )
            preview_read_only = not bool(cmds.file(query=True, modified=True))
            imported = ImportBodyHandPose(host).apply(
                pose_path,
                body_root_name="RigB:Root_M",
            )
            restored_b = InspectBodyHandPoseRig(host).execute(
                body_root_name="RigB:Root_M"
            )
            restored_document = body_hand_pose_document_from_snapshot(
                restored_b.channels
            )
            restored_index = position(cmds, joints_b["IndexEnd_R"])
            restored_thumb = position(cmds, joints_b["ThumbEnd_L"])
            a_after_import = body_hand_pose_document_from_snapshot(
                InspectBodyHandPoseRig(host).execute(
                    body_root_name="RigA:Root_M"
                ).channels
            )
            repeated = ImportBodyHandPose(host).apply(
                pose_path,
                body_root_name="RigB:Root_M",
            )
            selection_preserved = (cmds.ls(selection=True) or []) == [marker]

            cmds.undo()
            undo_b = InspectBodyHandPoseRig(host).execute(
                body_root_name="RigB:Root_M"
            )
            undo_document = body_hand_pose_document_from_snapshot(
                undo_b.channels
            )
            undo_index = position(cmds, joints_b["IndexEnd_R"])
            undo_thumb = position(cmds, joints_b["ThumbEnd_L"])
            a_after_undo = body_hand_pose_document_from_snapshot(
                InspectBodyHandPoseRig(host).execute(
                    body_root_name="RigA:Root_M"
                ).channels
            )

            checks = {
                "two_namespaced_references_loaded": (
                    cmds.objExists("RigA:Root_M")
                    and cmds.objExists("RigB:Root_M")
                ),
                "nested_hand_paths_resolved_in_each_namespace": (
                    roots_a["R"].endswith("RigA:AdvPy_HandFKControls_R")
                    and roots_b["R"].endswith("RigB:AdvPy_HandFKControls_R")
                ),
                "namespaced_export_matches_source": (
                    export_result.plan.document == source_document
                ),
                "export_document_remains_namespace_free": namespace_free_document,
                "namespaced_export_did_not_modify_scene": export_read_only,
                "target_preview_found_five_changes": (
                    preview.changed_channel_count == 5
                ),
                "target_preview_did_not_modify_scene": preview_read_only,
                "target_import_applied_five_changes": (
                    imported.changed_channel_count == 5
                ),
                "target_pose_matches_source_instance": (
                    restored_document == source_document
                ),
                "target_real_fingers_match_source_pose": (
                    close(restored_index, source_index)
                    and close(restored_thumb, source_thumb)
                    and not close(mutated_index, source_index)
                    and not close(mutated_thumb, source_thumb)
                ),
                "source_instance_remained_isolated": (
                    a_before_import == source_document
                    and a_after_import == source_document
                    and a_after_undo == source_document
                ),
                "repeat_import_is_noop": repeated.changed_channel_count == 0,
                "selection_preserved": selection_preserved,
                "one_undo_restored_target_preimport_pose": (
                    undo_document == mutated_document
                    and close(undo_index, mutated_index)
                    and close(undo_thumb, mutated_thumb)
                ),
            }
            cmds.file(new=True, force=True)
            checks["scene_cleanup"] = not (
                cmds.ls("RigA:*", "RigB:*", marker, long=True) or []
            )
        checks["temporary_asset_and_pose_removed"] = (
            not asset_path.exists() and not pose_path.exists()
        )

        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_hand_pose_namespace_mapping",
            **checks,
            "content_sha256": source_document.content_sha256,
            "changed_channel_count": imported.changed_channel_count,
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
