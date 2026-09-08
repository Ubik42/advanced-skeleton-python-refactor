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


def has_key(cmds, plug, frame):
    return int(cmds.keyframe(
        plug,
        query=True,
        time=(frame, frame),
        keyframeCount=True,
    ) or 0) == 1


def has_native_anim_curve(cmds, plug):
    sources = cmds.listConnections(
        plug,
        source=True,
        destination=False,
        plugs=True,
    ) or []
    return (
        len(sources) == 1
        and cmds.nodeType(sources[0].split(".", 1)[0]).startswith("animCurve")
    )


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

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="HandPoseKeyframeSelection",
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
        roots = {spec.side.value: spec.path for spec in inspection.hand.roots}
        controls = {
            spec.control_name.rsplit(":", 1)[-1]: spec.control_path
            for spec in inspection.hand.controls
        }
        joints = {joint.name: joint.path for joint in inspection.body.joints}
        right_index_end = joints["IndexEnd_R"]
        left_thumb_end = joints["ThumbEnd_L"]
        aggregate_plugs = (
            f"{roots['R']}.handCurl",
            f"{roots['R']}.indexCurl",
            f"{roots['L']}.handSpread",
        )
        index_control = controls["AdvPy_Index1FK_R"]
        thumb_control = controls["AdvPy_Thumb2FK_L"]
        rotation_plugs = tuple(
            f"{control}.rotate{axis}"
            for control in (index_control, thumb_control)
            for axis in ("X", "Y", "Z")
        )
        keyed_plugs = aggregate_plugs + rotation_plugs

        cmds.undoInfo(stateWithoutFlush=False)
        desired_values = (
            27.0,
            9.0,
            -12.0,
            2.0,
            3.0,
            11.0,
            -4.0,
            5.0,
            -6.0,
        )
        for plug, value in zip(keyed_plugs, desired_values):
            cmds.setAttr(plug, value)
        desired_inspection = InspectBodyHandPoseRig(host).execute()
        desired_document = body_hand_pose_document_from_snapshot(
            desired_inspection.channels
        )
        desired_index = position(cmds, right_index_end)
        desired_thumb = position(cmds, left_thumb_end)

        with tempfile.TemporaryDirectory(
            prefix="adv_py_hand_keyframe_"
        ) as directory:
            pose_path = Path(directory) / "desired-pose.json"
            animated_capture_path = Path(directory) / "animated-capture.json"
            ExportBodyHandPose(host).apply(pose_path)

            animated_values = (
                -18.0,
                -7.0,
                8.0,
                -1.0,
                -2.0,
                -3.0,
                6.0,
                -5.0,
                4.0,
            )
            for plug, value in zip(keyed_plugs, animated_values):
                cmds.setKeyframe(plug, time=(1.0,), value=value)
                cmds.setKeyframe(plug, time=(20.0,), value=value)
            cmds.currentTime(10.0, edit=True)
            animated_inspection = InspectBodyHandPoseRig(host).execute()
            animated_document = body_hand_pose_document_from_snapshot(
                animated_inspection.channels
            )
            animated_index = position(cmds, right_index_end)
            animated_thumb = position(cmds, left_thumb_end)
            cmds.file(modified=False)
            animated_export = ExportBodyHandPose(host).apply(
                animated_capture_path
            )
            animated_export_read_only = not bool(
                cmds.file(query=True, modified=True)
            )

            cmds.undoInfo(stateWithoutFlush=True)
            cmds.select(marker, replace=True)
            cmds.file(modified=False)
            static_import_refused = False
            try:
                ImportBodyHandPose(host).plan(pose_path)
            except ValueError:
                static_import_refused = True
            static_refusal_read_only = not bool(
                cmds.file(query=True, modified=True)
            )
            preview = ImportBodyHandPose(host).plan(
                pose_path,
                keyframe=True,
            )
            preview_read_only = not bool(cmds.file(query=True, modified=True))
            imported = ImportBodyHandPose(host).apply(
                pose_path,
                keyframe=True,
            )
            restored_inspection = InspectBodyHandPoseRig(host).execute()
            restored_document = body_hand_pose_document_from_snapshot(
                restored_inspection.channels
            )
            restored_index = position(cmds, right_index_end)
            restored_thumb = position(cmds, left_thumb_end)
            keys_at_current_frame = all(
                has_key(cmds, plug, 10.0) for plug in keyed_plugs
            )
            native_anim_sources = all(
                has_native_anim_curve(cmds, plug) for plug in keyed_plugs
            )
            repeated = ImportBodyHandPose(host).apply(
                pose_path,
                keyframe=True,
            )
            selection_preserved = (cmds.ls(selection=True) or []) == [marker]

            cmds.undo()
            undo_inspection = InspectBodyHandPoseRig(host).execute()
            undo_document = body_hand_pose_document_from_snapshot(
                undo_inspection.channels
            )
            undo_index = position(cmds, right_index_end)
            undo_thumb = position(cmds, left_thumb_end)
            current_keys_removed = all(
                not has_key(cmds, plug, 10.0) for plug in keyed_plugs
            )

            cmds.undoInfo(stateWithoutFlush=False)
            driver = cmds.createNode(
                "multiplyDivide",
                name="UnsafeHandPoseDriver",
                skipSelect=True,
            )
            cmds.setAttr(f"{driver}.input1X", 3.0)
            unsafe_plug = f"{roots['L']}.pinkyCurl"
            cmds.connectAttr(f"{driver}.outputX", unsafe_plug)
            cmds.undoInfo(stateWithoutFlush=True)
            cmds.file(modified=False)
            unknown_driver_refused = False
            try:
                ImportBodyHandPose(host).plan(
                    pose_path,
                    keyframe=True,
                )
            except ValueError:
                unknown_driver_refused = True
            unknown_refusal_read_only = not bool(
                cmds.file(query=True, modified=True)
            )
        temporary_files_removed = (
            not pose_path.exists() and not animated_capture_path.exists()
        )

        checks = {
            "animated_pose_export_is_supported": (
                animated_export.plan.document == animated_document
            ),
            "animated_export_did_not_modify_scene": animated_export_read_only,
            "static_import_refused_anim_curves": static_import_refused,
            "static_refusal_did_not_modify_scene": static_refusal_read_only,
            "keyframe_preview_found_five_changes": (
                preview.changed_channel_count == 5
            ),
            "keyframe_preview_did_not_modify_scene": preview_read_only,
            "keyframe_import_applied_five_changes": (
                imported.changed_channel_count == 5
            ),
            "keyframe_import_restored_semantic_pose": (
                restored_document == desired_document
            ),
            "keyframe_import_restored_real_fingers": (
                close(restored_index, desired_index)
                and close(restored_thumb, desired_thumb)
                and not close(animated_index, desired_index)
                and not close(animated_thumb, desired_thumb)
            ),
            "current_frame_has_nine_native_keys": (
                keys_at_current_frame and native_anim_sources
            ),
            "repeat_keyframe_import_is_noop": (
                repeated.changed_channel_count == 0
            ),
            "selection_preserved": selection_preserved,
            "one_undo_removed_current_keys": current_keys_removed,
            "one_undo_restored_interpolated_pose": (
                undo_document == animated_document
                and close(undo_index, animated_index)
                and close(undo_thumb, animated_thumb)
            ),
            "unknown_driver_refused_before_transaction": unknown_driver_refused,
            "unknown_driver_refusal_read_only": unknown_refusal_read_only,
            "temporary_pose_files_removed": temporary_files_removed,
        }
        cmds.file(new=True, force=True)
        checks["scene_cleanup"] = not (
            cmds.ls("Root_M", "FitSkeleton", "AdvPy_*", marker, long=True) or []
        )

        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_hand_pose_current_frame_keyframe",
            **checks,
            "current_frame": 10.0,
            "keyed_plug_count": len(keyed_plugs),
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
