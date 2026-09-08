from __future__ import annotations

import json
import os
from pathlib import Path
import sys
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
            InspectBodyRebuildSafety,
        )
        from adv_py.application.body_rig_validation import body_bind_pose_matches
        from adv_py.core import BodyHandDigit, FitBuildSide

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="HandPoseSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodyWithHandSourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit_before = host.capture_fit_orientation(container)
        body_by_name = {joint.name: joint.path for joint in body_before.joints}
        cmds.select(marker, replace=True)

        use_case = BuildBodyCharacterRig(host)
        cmds.file(modified=False)
        preview = use_case.plan(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        rig = use_case.apply(container)
        hand = rig.hand
        if hand is None:
            raise RuntimeError("70 关节 Character 未构建 Hand")

        right_root = next(
            root.path
            for root in hand.plan.controls.roots
            if root.side is FitBuildSide.RIGHT
        )
        right_controls = {
            spec.control_name: spec
            for spec in hand.plan.controls.controls
            if spec.side is FitBuildSide.RIGHT
        }
        right_curls = {
            (spec.digit, spec.segment): spec
            for spec in hand.plan.pose.curls
            if spec.side is FitBuildSide.RIGHT
        }
        right_spreads = {
            spec.digit: spec
            for spec in hand.plan.pose.spreads
            if spec.side is FitBuildSide.RIGHT
        }
        right_index_end = body_by_name["IndexEnd_R"]
        right_pinky_end = body_by_name["PinkyEnd_R"]
        left_index_end = body_by_name["IndexEnd_L"]
        initial_index = position(cmds, right_index_end)
        initial_pinky = position(cmds, right_pinky_end)
        initial_left = position(cmds, left_index_end)

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{right_root}.handCurl", 30.0)
        aggregate_angles = tuple(
            float(cmds.getAttr(
                right_curls[(BodyHandDigit.INDEX, segment)].destination_plug
            ))
            for segment in ("1", "2", "3")
        )
        global_curl_moves_index = not close(
            position(cmds, right_index_end),
            initial_index,
        )
        global_curl_left_isolated = close(
            position(cmds, left_index_end),
            initial_left,
        )

        cmds.setAttr(f"{right_root}.indexCurl", 10.0)
        combined_angles = tuple(
            float(cmds.getAttr(
                right_curls[(BodyHandDigit.INDEX, segment)].destination_plug
            ))
            for segment in ("1", "2", "3")
        )
        aggregate_position = position(cmds, right_index_end)
        index_control = right_controls["AdvPy_Index1FK_R"].control_path
        cmds.setAttr(f"{index_control}.rotateZ", 12.0)
        manual_fk_remains_free = (
            abs(float(cmds.getAttr(f"{index_control}.rotateZ")) - 12.0)
            <= 1e-4
            and not (
                cmds.listConnections(
                    f"{index_control}.rotateZ",
                    source=True,
                    destination=False,
                ) or []
            )
        )
        manual_fk_adds_to_curl = not close(
            position(cmds, right_index_end),
            aggregate_position,
        )

        cmds.setAttr(f"{index_control}.rotateZ", 0.0)
        cmds.setAttr(f"{right_root}.indexCurl", 0.0)
        cmds.setAttr(f"{right_root}.handCurl", 0.0)
        cmds.setAttr(f"{right_root}.handSpread", 20.0)
        spread_angles = {
            digit.value: float(cmds.getAttr(spec.destination_plug))
            for digit, spec in right_spreads.items()
        }
        spread_moves_outer_digits = (
            not close(position(cmds, right_index_end), initial_index)
            and not close(position(cmds, right_pinky_end), initial_pinky)
        )
        spread_left_isolated = close(
            position(cmds, left_index_end),
            initial_left,
        )

        cmds.setAttr(f"{right_root}.handSpread", 0.0)
        neutral_pose_restored = body_bind_pose_matches(
            body_before,
            host.capture_body_skeleton("Root_M"),
        )
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        rebuild_blocked = not InspectBodyRebuildSafety(host).execute(
            container
        ).safe_to_replace
        cmds.undoInfo(stateWithoutFlush=True)

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
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "pose_layers_verified": len(hand.pose.layers) == 30,
            "pose_attributes_verified": len(hand.pose.attributes) == 14,
            "curl_nodes_verified": len(hand.pose.curls) == 30,
            "spread_nodes_verified": len(hand.pose.spreads) == 8,
            "global_curl_has_segment_weights": close(
                aggregate_angles,
                (13.5, 22.5, 30.0),
            ),
            "global_curl_moves_right_index": global_curl_moves_index,
            "global_curl_keeps_left_hand_isolated": global_curl_left_isolated,
            "digit_curl_adds_to_global_curl": close(
                combined_angles,
                (18.0, 30.0, 40.0),
            ),
            "manual_fk_channel_remains_free": manual_fk_remains_free,
            "manual_fk_adds_to_aggregate_curl": manual_fk_adds_to_curl,
            "spread_uses_signed_outer_weights": (
                abs(spread_angles["Thumb"] - 20.0) <= 1e-4
                and abs(spread_angles["Index"] - 10.0) <= 1e-4
                and abs(spread_angles["Ring"] + 10.0) <= 1e-4
                and abs(spread_angles["Pinky"] + 20.0) <= 1e-4
            ),
            "spread_moves_right_outer_digits": spread_moves_outer_digits,
            "spread_keeps_left_hand_isolated": spread_left_isolated,
            "neutral_pose_restored": neutral_pose_restored,
            "selection_preserved": selection_preserved,
            "rebuild_blocked_while_character_exists": rebuild_blocked,
            "single_undo_removed_character_and_pose_network": not remaining_rig,
            "single_undo_preserved_seventy_joint_body": body_survived,
            "single_undo_preserved_fit": fit_survived,
            "single_undo_restored_rebuild_safety": rebuild_safe_again,
            "unrelated_node_survived": marker_survived,
            "cleanup": not remaining,
        }
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_hand_aggregate_pose",
            **checks,
            "attribute_count": len(hand.pose.attributes),
            "pose_layer_count": len(hand.pose.layers),
            "curl_node_count": len(hand.pose.curls),
            "spread_node_count": len(hand.pose.spreads),
            "aggregate_angles": aggregate_angles,
            "combined_angles": combined_angles,
            "spread_angles": spread_angles,
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
