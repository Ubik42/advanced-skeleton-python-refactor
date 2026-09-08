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
            BODY_HAND_POSE_PRESET_SUFFIX,
            ApplyBodyHandPosePreset,
            BuildBodyCharacterRig,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodyWithHandSourceFit,
            CreateFitSkeleton,
            InspectBodyHandPosePresetLibrary,
            InspectBodyHandPoseRig,
            SaveBodyHandPosePreset,
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
            name="HandPoseLibrarySelection",
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
        right_aggregate = f"{roots[FitBuildSide.RIGHT]}.handCurl"
        right_control = controls["AdvPy_Index1FK_R"]
        left_aggregate = f"{roots[FitBuildSide.LEFT]}.handSpread"

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(right_aggregate, 28.0)
        cmds.setAttr(f"{right_control}.rotate", 2.0, 3.0, 9.0)
        cmds.setAttr(left_aggregate, -12.0)
        desired_inspection = InspectBodyHandPoseRig(host).execute()
        desired_document = body_hand_pose_document_from_snapshot(
            desired_inspection.channels
        )
        desired_right_index = position(cmds, right_index_end)

        with tempfile.TemporaryDirectory(
            prefix="adv_py_hand_library_"
        ) as directory:
            library_path = Path(directory)
            cmds.undoInfo(stateWithoutFlush=True)
            cmds.select(marker, replace=True)
            cmds.file(modified=False)
            invalid_name_refused = False
            try:
                SaveBodyHandPosePreset(host).plan(
                    library_path,
                    "../越界",
                )
            except ValueError:
                invalid_name_refused = True
            invalid_name_read_only = not bool(
                cmds.file(query=True, modified=True)
            )
            saved = SaveBodyHandPosePreset(host).apply(
                library_path,
                "握拳Test",
            )
            save_did_not_modify_scene = not bool(
                cmds.file(query=True, modified=True)
            )
            preset_path = library_path / (
                f"握拳Test{BODY_HAND_POSE_PRESET_SUFFIX}"
            )
            saved_bytes = preset_path.read_bytes()
            library = InspectBodyHandPosePresetLibrary().execute(library_path)
            duplicate_refused = False
            try:
                SaveBodyHandPosePreset(host).apply(
                    library_path,
                    "握拳test",
                )
            except ValueError:
                duplicate_refused = True
            duplicate_preserved_file = preset_path.read_bytes() == saved_bytes

            cmds.undoInfo(stateWithoutFlush=False)
            cmds.setAttr(right_aggregate, -15.0)
            cmds.setAttr(f"{right_control}.rotate", -1.0, -2.0, -3.0)
            cmds.setAttr(left_aggregate, 6.0)
            current_inspection = InspectBodyHandPoseRig(host).execute()
            current_document = body_hand_pose_document_from_snapshot(
                current_inspection.channels
            )
            current_right_index = position(cmds, right_index_end)
            current_left_thumb = position(cmds, left_thumb_end)

            cmds.undoInfo(stateWithoutFlush=True)
            cmds.select(marker, replace=True)
            cmds.file(modified=False)
            preview = ApplyBodyHandPosePreset(host).plan(
                library_path,
                "握拳test",
                target_side=FitBuildSide.RIGHT,
            )
            preview_read_only = not bool(cmds.file(query=True, modified=True))
            applied = ApplyBodyHandPosePreset(host).apply(
                library_path,
                "握拳test",
                target_side=FitBuildSide.RIGHT,
            )
            result_inspection = InspectBodyHandPoseRig(host).execute()
            result_document = body_hand_pose_document_from_snapshot(
                result_inspection.channels
            )
            result_right_index = position(cmds, right_index_end)
            result_left_thumb = position(cmds, left_thumb_end)
            repeated = ApplyBodyHandPosePreset(host).apply(
                library_path,
                "握拳test",
                target_side=FitBuildSide.RIGHT,
            )
            selection_preserved = (cmds.ls(selection=True) or []) == [marker]

            cmds.undo()
            undo_inspection = InspectBodyHandPoseRig(host).execute()
            undo_document = body_hand_pose_document_from_snapshot(
                undo_inspection.channels
            )
            undo_right_index = position(cmds, right_index_end)
            preset_survived_maya_undo = preset_path.read_bytes() == saved_bytes

            corrupt_path = library_path / (
                f"损坏{BODY_HAND_POSE_PRESET_SUFFIX}"
            )
            corrupt_path.write_text("{}", encoding="utf-8")
            cmds.file(modified=False)
            corrupt_list_refused = False
            try:
                InspectBodyHandPosePresetLibrary().execute(library_path)
            except ValueError:
                corrupt_list_refused = True
            corrupt_apply_refused = False
            try:
                ApplyBodyHandPosePreset(host).apply(
                    library_path,
                    "损坏",
                )
            except ValueError:
                corrupt_apply_refused = True
            corrupt_refusals_read_only = not bool(
                cmds.file(query=True, modified=True)
            )

        library_removed = not library_path.exists()
        checks = {
            "invalid_name_refused_before_scene_read": invalid_name_refused,
            "invalid_name_did_not_modify_scene": invalid_name_read_only,
            "named_preset_saved_atomically": (
                saved.plan.destination == preset_path
                and saved.export_result.bytes_written == len(saved_bytes)
            ),
            "save_did_not_modify_scene": save_did_not_modify_scene,
            "library_lists_valid_chinese_name": (
                len(library.presets) == 1
                and library.presets[0].name == "握拳Test"
                and library.presets[0].document == desired_document
            ),
            "casefold_duplicate_refused_without_overwrite": (
                duplicate_refused and duplicate_preserved_file
            ),
            "apply_lookup_preserved_canonical_name": (
                preview.preset.name == "握拳Test"
            ),
            "apply_preview_found_two_right_changes": (
                preview.changed_channel_count == 2
            ),
            "apply_preview_did_not_modify_scene": preview_read_only,
            "right_only_apply_matches_expected_document": (
                applied.changed_channel_count == 2
                and result_document == preview.import_plan.expected_document
            ),
            "right_finger_restored_and_left_preserved": (
                close(result_right_index, desired_right_index)
                and not close(current_right_index, desired_right_index)
                and close(result_left_thumb, current_left_thumb)
            ),
            "repeat_preset_apply_is_noop": (
                repeated.changed_channel_count == 0
            ),
            "selection_preserved": selection_preserved,
            "one_undo_restored_scene_but_kept_preset": (
                undo_document == current_document
                and close(undo_right_index, current_right_index)
                and preset_survived_maya_undo
            ),
            "corrupt_preset_refused_for_list_and_apply": (
                corrupt_list_refused and corrupt_apply_refused
            ),
            "corrupt_refusals_did_not_modify_scene": (
                corrupt_refusals_read_only
            ),
            "temporary_library_removed": library_removed,
        }
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.file(new=True, force=True)
        checks["scene_cleanup"] = not (
            cmds.ls("Root_M", "FitSkeleton", "AdvPy_*", marker, long=True)
            or []
        )

        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_hand_pose_named_library",
            **checks,
            "preset_name": "握拳Test",
            "changed_channel_count": applied.changed_channel_count,
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
