from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


DIGITS = ("Thumb", "Index", "Middle", "Ring", "Pinky")


def close(left, right, tolerance=3e-3):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def position(cmds, path):
    return tuple(float(value) for value in cmds.xform(
        path,
        query=True,
        worldSpace=True,
        translation=True,
    ))


def reflected_x(value):
    return (-value[0], value[1], value[2])


def mirrored_rotation(value):
    return (-value[0], -value[1], value[2])


def source(cmds, plug):
    values = cmds.listConnections(
        plug,
        source=True,
        destination=False,
        plugs=True,
    ) or []
    return values[0] if len(values) == 1 else None


def side_values(document, side):
    aggregates = tuple(
        (item.name, item.value)
        for item in document.aggregates
        if item.side is side
    )
    controls = tuple(
        (item.digit, item.segment, item.rotation)
        for item in document.controls
        if item.side is side
    )
    return aggregates, controls


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
            InspectBodyHandPoseRig,
            MirrorBodyHandPose,
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
            name="HandPoseMirrorSelection",
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
        end_joints = {
            side: {
                digit: joints[f"{digit}End_{side.value}"]
                for digit in DIGITS
            }
            for side in (FitBuildSide.RIGHT, FitBuildSide.LEFT)
        }

        cmds.undoInfo(stateWithoutFlush=False)
        source_driver = cmds.createNode(
            "multiplyDivide",
            name="RightHandCurlDriver",
            skipSelect=True,
        )
        source_curl_plug = f"{roots[FitBuildSide.RIGHT]}.handCurl"
        cmds.setAttr(f"{source_driver}.input1X", 24.0)
        cmds.connectAttr(f"{source_driver}.outputX", source_curl_plug)
        cmds.setAttr(
            f"{roots[FitBuildSide.RIGHT]}.handSpread",
            12.0,
        )
        rotations = {
            "Thumb": (3.0, -2.0, 4.0),
            "Index": (2.0, 3.0, 6.0),
            "Middle": (-2.0, 4.0, 8.0),
            "Ring": (1.0, -3.0, 10.0),
            "Pinky": (-3.0, 2.0, 12.0),
        }
        for digit, rotation in rotations.items():
            control = controls[f"AdvPy_{digit}1FK_R"]
            cmds.setAttr(f"{control}.rotate", *rotation)

        initial_inspection = InspectBodyHandPoseRig(host).execute()
        initial_document = body_hand_pose_document_from_snapshot(
            initial_inspection.channels
        )
        source_positions = {
            digit: position(
                cmds,
                end_joints[FitBuildSide.RIGHT][digit],
            )
            for digit in DIGITS
        }
        target_positions_before = {
            digit: position(
                cmds,
                end_joints[FitBuildSide.LEFT][digit],
            )
            for digit in DIGITS
        }
        source_connection_before = source(cmds, source_curl_plug)

        cmds.undoInfo(stateWithoutFlush=True)
        cmds.select(marker, replace=True)
        cmds.file(modified=False)
        preview = MirrorBodyHandPose(host).plan(
            source_side=FitBuildSide.RIGHT,
        )
        preview_read_only = not bool(cmds.file(query=True, modified=True))
        mirrored = MirrorBodyHandPose(host).apply(
            source_side=FitBuildSide.RIGHT,
        )
        result_inspection = InspectBodyHandPoseRig(host).execute()
        result_document = body_hand_pose_document_from_snapshot(
            result_inspection.channels
        )
        source_positions_after = {
            digit: position(
                cmds,
                end_joints[FitBuildSide.RIGHT][digit],
            )
            for digit in DIGITS
        }
        target_positions_after = {
            digit: position(
                cmds,
                end_joints[FitBuildSide.LEFT][digit],
            )
            for digit in DIGITS
        }
        source_connection_after = source(cmds, source_curl_plug)
        repeated = MirrorBodyHandPose(host).apply(
            source_side=FitBuildSide.RIGHT,
        )
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]

        cmds.undo()
        undo_inspection = InspectBodyHandPoseRig(host).execute()
        undo_document = body_hand_pose_document_from_snapshot(
            undo_inspection.channels
        )
        undo_target_positions = {
            digit: position(
                cmds,
                end_joints[FitBuildSide.LEFT][digit],
            )
            for digit in DIGITS
        }

        cmds.undoInfo(stateWithoutFlush=False)
        target_driver = cmds.createNode(
            "multiplyDivide",
            name="LeftHandUnsafeDriver",
            skipSelect=True,
        )
        unsafe_target_plug = f"{roots[FitBuildSide.LEFT]}.indexCurl"
        cmds.setAttr(f"{target_driver}.input1X", 5.0)
        cmds.connectAttr(f"{target_driver}.outputX", unsafe_target_plug)
        cmds.undoInfo(stateWithoutFlush=True)
        cmds.file(modified=False)
        unsafe_target_refused = False
        try:
            MirrorBodyHandPose(host).plan(
                source_side=FitBuildSide.RIGHT,
            )
        except ValueError:
            unsafe_target_refused = True
        unsafe_refusal_read_only = not bool(
            cmds.file(query=True, modified=True)
        )

        mirrored_positions = all(
            close(
                target_positions_after[digit],
                reflected_x(source_positions[digit]),
            )
            for digit in DIGITS
        )
        source_semantics, _ = side_values(
            result_document,
            FitBuildSide.RIGHT,
        )
        target_semantics, _ = side_values(
            result_document,
            FitBuildSide.LEFT,
        )
        source_controls = side_values(
            result_document,
            FitBuildSide.RIGHT,
        )[1]
        target_controls = side_values(
            result_document,
            FitBuildSide.LEFT,
        )[1]
        controls_follow_policy = all(
            source_item[:2] == target_item[:2]
            and close(
                target_item[2],
                mirrored_rotation(source_item[2]),
                tolerance=1e-6,
            )
            for source_item, target_item in zip(
                source_controls,
                target_controls,
            )
        )
        mirror_position_errors = {
            digit: max(
                abs(actual - expected)
                for actual, expected in zip(
                    target_positions_after[digit],
                    reflected_x(source_positions[digit]),
                )
            )
            for digit in DIGITS
        }
        checks = {
            "preview_found_seven_semantic_changes": (
                preview.changed_channel_count == 7
            ),
            "preview_did_not_modify_scene": preview_read_only,
            "mirror_applied_seven_semantic_changes": (
                mirrored.changed_channel_count == 7
            ),
            "result_matches_expected_document": (
                result_document == preview.expected_document
            ),
            "paired_semantics_follow_mirror_policy": (
                source_semantics == target_semantics
                and controls_follow_policy
            ),
            "all_five_fingertips_mirror_across_x": mirrored_positions,
            "source_pose_and_driver_are_unchanged": (
                all(
                    close(source_positions_after[digit], source_positions[digit])
                    for digit in DIGITS
                )
                and source_connection_after == source_connection_before
            ),
            "repeat_mirror_is_noop": repeated.changed_channel_count == 0,
            "selection_preserved": selection_preserved,
            "one_undo_restored_target_pose": (
                undo_document == initial_document
                and all(
                    close(
                        undo_target_positions[digit],
                        target_positions_before[digit],
                    )
                    for digit in DIGITS
                )
            ),
            "unsafe_target_refused_before_transaction": unsafe_target_refused,
            "unsafe_target_refusal_read_only": unsafe_refusal_read_only,
        }
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.file(new=True, force=True)
        checks["scene_cleanup"] = not (
            cmds.ls(
                "Root_M",
                "FitSkeleton",
                "AdvPy_*",
                marker,
                source_driver,
                target_driver,
                long=True,
            ) or []
        )

        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_hand_pose_mirror",
            **checks,
            "source_side": FitBuildSide.RIGHT.value,
            "target_side": FitBuildSide.LEFT.value,
            "changed_channel_count": mirrored.changed_channel_count,
            "max_fingertip_mirror_error": max(
                mirror_position_errors.values()
            ),
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
