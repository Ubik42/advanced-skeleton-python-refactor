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


def source(cmds, plug):
    values = cmds.listConnections(
        plug,
        source=True,
        destination=False,
        plugs=True,
    ) or []
    return values[0] if len(values) == 1 else None


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
        from adv_py.core import (
            FitBuildSide,
            body_hand_pose_document_from_snapshot,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="HandPoseSideSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodyWithHandSourceFit(host).apply(container)
        BuildOrientedBodySkeleton(host).apply(container)
        character = BuildBodyCharacterRig(host).apply(container)
        if character.hand is None:
            raise RuntimeError("合成 70 关节角色未构建 Hand")

        inspection = InspectBodyHandPoseRig(host).execute()
        roots = {spec.side: spec.path for spec in inspection.hand.roots}
        controls = {
            spec.control_name.rsplit(":", 1)[-1]: spec.control_path
            for spec in inspection.hand.controls
        }
        joints = {joint.name: joint.path for joint in inspection.body.joints}
        right_index_end = joints["IndexEnd_R"]
        left_thumb_end = joints["ThumbEnd_L"]
        right_aggregate_plugs = (
            f"{roots[FitBuildSide.RIGHT]}.handCurl",
            f"{roots[FitBuildSide.RIGHT]}.indexCurl",
        )
        left_aggregate_plug = (
            f"{roots[FitBuildSide.LEFT]}.handSpread"
        )
        right_control = controls["AdvPy_Index1FK_R"]
        left_control = controls["AdvPy_Thumb2FK_L"]
        right_rotation_plugs = tuple(
            f"{right_control}.rotate{axis}" for axis in "XYZ"
        )
        left_rotation_plugs = tuple(
            f"{left_control}.rotate{axis}" for axis in "XYZ"
        )

        cmds.undoInfo(stateWithoutFlush=False)
        desired_right_values = (25.0, 8.0, 2.0, 3.0, 12.0)
        for plug, value in zip(
            right_aggregate_plugs + right_rotation_plugs,
            desired_right_values,
        ):
            cmds.setAttr(plug, value)
        cmds.setAttr(left_aggregate_plug, -14.0)
        for plug, value in zip(left_rotation_plugs, (-4.0, 5.0, -6.0)):
            cmds.setAttr(plug, value)
        desired_inspection = InspectBodyHandPoseRig(host).execute()
        desired_document = body_hand_pose_document_from_snapshot(
            desired_inspection.channels
        )
        desired_right_index = position(cmds, right_index_end)

        with tempfile.TemporaryDirectory(
            prefix="adv_py_hand_side_"
        ) as directory:
            pose_path = Path(directory) / "bilateral-pose.json"
            ExportBodyHandPose(host).apply(pose_path)

            current_right_values = (-15.0, -6.0, -1.0, -2.0, -3.0)
            for plug, value in zip(
                right_aggregate_plugs + right_rotation_plugs,
                current_right_values,
            ):
                cmds.setAttr(plug, value)
            aggregate_driver = cmds.createNode(
                "multiplyDivide",
                name="LeftHandAggregateDriver",
                skipSelect=True,
            )
            rotation_driver = cmds.createNode(
                "multiplyDivide",
                name="LeftHandRotationDriver",
                skipSelect=True,
            )
            driven_plugs = (left_aggregate_plug,) + left_rotation_plugs
            output_plugs = (
                f"{aggregate_driver}.outputX",
                *(f"{rotation_driver}.output{axis}" for axis in "XYZ"),
            )
            cmds.setAttr(f"{aggregate_driver}.input1X", 5.0)
            for axis, value in zip("XYZ", (-4.0, -5.0, -6.0)):
                cmds.setAttr(f"{rotation_driver}.input1{axis}", value)
            for driven_plug, output_plug in zip(
                driven_plugs,
                output_plugs,
            ):
                cmds.connectAttr(output_plug, driven_plug)

            current_inspection = InspectBodyHandPoseRig(host).execute()
            current_document = body_hand_pose_document_from_snapshot(
                current_inspection.channels
            )
            current_right_index = position(cmds, right_index_end)
            current_left_thumb = position(cmds, left_thumb_end)
            left_sources_before = tuple(
                source(cmds, plug) for plug in driven_plugs
            )

            cmds.undoInfo(stateWithoutFlush=True)
            cmds.select(marker, replace=True)
            cmds.file(modified=False)
            full_import_refused = False
            try:
                ImportBodyHandPose(host).plan(pose_path)
            except ValueError:
                full_import_refused = True
            full_refusal_read_only = not bool(
                cmds.file(query=True, modified=True)
            )
            left_import_refused = False
            try:
                ImportBodyHandPose(host).plan(
                    pose_path,
                    target_side=FitBuildSide.LEFT,
                )
            except ValueError:
                left_import_refused = True
            left_refusal_read_only = not bool(
                cmds.file(query=True, modified=True)
            )
            preview = ImportBodyHandPose(host).plan(
                pose_path,
                target_side=FitBuildSide.RIGHT,
            )
            preview_read_only = not bool(cmds.file(query=True, modified=True))
            imported = ImportBodyHandPose(host).apply(
                pose_path,
                target_side=FitBuildSide.RIGHT,
            )
            restored_inspection = InspectBodyHandPoseRig(host).execute()
            restored_document = body_hand_pose_document_from_snapshot(
                restored_inspection.channels
            )
            restored_right_index = position(cmds, right_index_end)
            restored_left_thumb = position(cmds, left_thumb_end)
            left_sources_preserved = (
                tuple(source(cmds, plug) for plug in driven_plugs)
                == left_sources_before
            )
            repeated = ImportBodyHandPose(host).apply(
                pose_path,
                target_side=FitBuildSide.RIGHT,
            )
            selection_preserved = (cmds.ls(selection=True) or []) == [marker]

            cmds.undo()
            undo_inspection = InspectBodyHandPoseRig(host).execute()
            undo_document = body_hand_pose_document_from_snapshot(
                undo_inspection.channels
            )
            undo_right_index = position(cmds, right_index_end)
            undo_left_thumb = position(cmds, left_thumb_end)

        temporary_file_removed = not pose_path.exists()
        expected_is_partial = (
            preview.expected_document != desired_document
            and preview.expected_document != current_document
        )
        checks = {
            "full_import_refused_non_target_drivers": full_import_refused,
            "full_refusal_did_not_modify_scene": full_refusal_read_only,
            "left_import_refused_left_drivers": left_import_refused,
            "left_refusal_did_not_modify_scene": left_refusal_read_only,
            "right_preview_found_three_changes": (
                preview.changed_channel_count == 3
            ),
            "right_preview_did_not_modify_scene": preview_read_only,
            "partial_expected_document_is_explicit": expected_is_partial,
            "right_import_applied_three_changes": (
                imported.changed_channel_count == 3
            ),
            "result_matches_partial_expected_document": (
                restored_document == preview.expected_document
            ),
            "right_finger_restored": (
                close(restored_right_index, desired_right_index)
                and not close(current_right_index, desired_right_index)
            ),
            "left_finger_and_drivers_preserved": (
                close(restored_left_thumb, current_left_thumb)
                and left_sources_preserved
            ),
            "repeat_right_import_is_noop": (
                repeated.changed_channel_count == 0
            ),
            "selection_preserved": selection_preserved,
            "one_undo_restored_complete_current_pose": (
                undo_document == current_document
                and close(undo_right_index, current_right_index)
                and close(undo_left_thumb, current_left_thumb)
            ),
            "temporary_pose_file_removed": temporary_file_removed,
        }
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.file(new=True, force=True)
        checks["scene_cleanup"] = not (
            cmds.ls(
                "Root_M",
                "FitSkeleton",
                "AdvPy_*",
                marker,
                aggregate_driver,
                rotation_driver,
                long=True,
            ) or []
        )

        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_hand_pose_target_side",
            **checks,
            "target_side": FitBuildSide.RIGHT.value,
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
