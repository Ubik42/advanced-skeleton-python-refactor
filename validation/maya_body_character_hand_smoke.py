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


def matrix(cmds, path):
    return tuple(float(value) for value in cmds.xform(
        path,
        query=True,
        worldSpace=True,
        matrix=True,
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
        from adv_py.core import FitBuildSide

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="CharacterHandSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodyWithHandSourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit_before = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)

        use_case = BuildBodyCharacterRig(host)
        cmds.file(modified=False)
        preview = use_case.plan(container, hand_control_radius=0.35)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        rig = use_case.apply(container, hand_control_radius=0.35)
        hand = rig.hand
        if hand is None:
            raise RuntimeError("70 关节 Body 未自动生成 Hand FK")

        right_root = next(
            spec
            for spec in hand.plan.controls.roots
            if spec.side is FitBuildSide.RIGHT
        )
        left_root = next(
            spec
            for spec in hand.plan.controls.roots
            if spec.side is FitBuildSide.LEFT
        )
        right_index = next(
            spec
            for spec in hand.plan.controls.controls
            if spec.control_name == "AdvPy_Index1FK_R"
        )
        left_index = next(
            spec
            for spec in hand.plan.controls.controls
            if spec.control_name == "AdvPy_Index1FK_L"
        )
        wrist_fk = next(
            spec.control_path
            for spec in rig.arm.plan.fk_controls.controls
            if spec.side is FitBuildSide.RIGHT
            and spec.control_name == "AdvPy_WristFK_R"
        )
        wrist_ik = next(
            spec.wrist_control_path
            for spec in rig.arm.plan.ik.limbs
            if spec.side is FitBuildSide.RIGHT
        )
        arm_blend = (
            f"{rig.arm.plan.blend.settings_path}.armIkFk_R"
        )

        right_index_before = position(cmds, right_index.control_path)
        left_index_before = position(cmds, left_index.control_path)
        ik_local_translation = tuple(
            float(cmds.getAttr(f"{wrist_ik}.translate{axis}"))
            for axis in "XYZ"
        )

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{wrist_fk}.rotateZ", 32.0)
        fk_index_position = position(cmds, right_index.control_path)
        fk_wrist_frame_followed = close(
            matrix(cmds, right_root.path),
            matrix(cmds, right_root.wrist_joint),
        )
        fk_hand_followed = not close(fk_index_position, right_index_before)
        fk_left_isolated = close(
            position(cmds, left_index.control_path),
            left_index_before,
        )

        cmds.setAttr(f"{wrist_fk}.rotateZ", 0.0)
        cmds.setAttr(arm_blend, 1.0)
        for axis, initial, delta in zip(
            "XYZ",
            ik_local_translation,
            (1.25, -0.75, 0.5),
        ):
            cmds.setAttr(f"{wrist_ik}.translate{axis}", initial + delta)
        cmds.setAttr(f"{wrist_ik}.rotateZ", -24.0)
        ik_index_position = position(cmds, right_index.control_path)
        ik_wrist_frame_followed = close(
            matrix(cmds, right_root.path),
            matrix(cmds, right_root.wrist_joint),
        )
        ik_hand_followed = not close(ik_index_position, right_index_before)
        ik_differs_from_fk = not close(ik_index_position, fk_index_position)
        ik_left_isolated = close(
            position(cmds, left_index.control_path),
            left_index_before,
        )

        for axis, initial in zip("XYZ", ik_local_translation):
            cmds.setAttr(f"{wrist_ik}.translate{axis}", initial)
        cmds.setAttr(f"{wrist_ik}.rotateZ", 0.0)
        cmds.setAttr(arm_blend, 0.0)
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
        single_undo_removed_rig = not remaining_rig
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
            "seventy_joint_body": len(body_before.joints) == 70,
            "hand_stage_auto_enabled": preview.hand is not None,
            "arm_leg_hand_built_together": (
                len(rig.arm.mechanisms.joints) == 12
                and len(rig.leg.mechanisms.joints) == 20
                and len(hand.snapshot.roots) == 2
                and len(hand.snapshot.controls) == 30
            ),
            "global_keeps_nine_root_level_targets": (
                len(rig.global_control.driven_roots) == 9
            ),
            "hand_roots_parented_to_both_wrists": (
                right_root.parent_path == right_root.wrist_joint
                and left_root.parent_path == left_root.wrist_joint
            ),
            "fk_wrist_frame_drives_hand_root": fk_wrist_frame_followed,
            "fk_wrist_moves_hand_controls": fk_hand_followed,
            "fk_right_motion_does_not_move_left_hand": fk_left_isolated,
            "ik_wrist_frame_drives_hand_root": ik_wrist_frame_followed,
            "ik_wrist_moves_hand_controls": ik_hand_followed,
            "ik_and_fk_exercise_distinct_poses": ik_differs_from_fk,
            "ik_right_motion_does_not_move_left_hand": ik_left_isolated,
            "neutral_pose_restored": neutral_pose_restored,
            "selection_preserved": selection_preserved,
            "rebuild_blocked_while_character_exists": rebuild_blocked,
            "single_undo_removed_complete_character_rig": (
                single_undo_removed_rig
            ),
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
            "slice": "body_character_optional_hand_fk",
            **checks,
            "hand_root_count": len(hand.snapshot.roots),
            "hand_control_count": len(hand.snapshot.controls),
            "global_driven_root_count": len(rig.global_control.driven_roots),
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
