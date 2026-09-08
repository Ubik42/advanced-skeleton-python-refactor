from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def _close(left, right, tolerance=1e-4):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyHandFkControls,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodyWithHandSourceFit,
            CreateFitSkeleton,
            InspectBodyRebuildSafety,
        )
        from adv_py.core import BODY_HAND_DIGITS, FitSkeletonValidationError
        from adv_py.application.body_rig_validation import body_bind_pose_matches

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableHandFkSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodyWithHandSourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit_before = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)

        use_case = BuildBodyHandFkControls(host)
        cmds.file(modified=False)
        preview = use_case.plan(container, control_radius=0.35)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container, control_radius=0.35)
        snapshot = result.snapshot

        roots_verified = all(
            state.path == spec.path
            and state.parent_path == spec.parent_path
            and _close(state.local_translation, (0.0, 0.0, 0.0))
            and _close(state.local_rotation, (0.0, 0.0, 0.0))
            and _close(state.local_scale, (1.0, 1.0, 1.0))
            for state, spec in zip(snapshot.roots, preview.controls.roots)
        )
        curves_and_wiring_verified = all(
            state.shape_type == "nurbsCurve"
            and state.source_control == spec.control_path
            and state.driven_joint == spec.driven_joint
            and state.offset_parent_path == spec.parent_path
            and state.control_parent_path == spec.offset_path
            for state, spec in zip(
                snapshot.controls,
                preview.controls.controls,
            )
        )
        zero_control_channels = all(
            _close(state.local_translation, (0.0, 0.0, 0.0))
            and _close(state.local_rotation, (0.0, 0.0, 0.0))
            for state in snapshot.controls
        )
        hierarchy_verified = all(
            len(controls) == 3
            and controls[0].offset_parent_path.endswith(
                f"AdvPy_HandFKControls_{side}"
            )
            and controls[1].offset_parent_path == controls[0].control_path
            and controls[2].offset_parent_path == controls[1].control_path
            for side in ("R", "L")
            for digit in BODY_HAND_DIGITS
            for controls in [[
                state
                for state in snapshot.controls
                if state.control_path.endswith(
                    tuple(
                        f"AdvPy_{digit.value}{index}FK_{side}"
                        for index in (1, 2, 3)
                    )
                )
            ]]
        )
        body_preserved = body_bind_pose_matches(
            body_before,
            host.capture_body_skeleton("Root_M"),
        )
        fit_preserved = host.capture_fit_orientation(container) == fit_before
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        rebuild_blocked = not InspectBodyRebuildSafety(host).execute(
            container
        ).safe_to_replace

        duplicate_blocked = False
        try:
            use_case.apply(container)
        except FitSkeletonValidationError:
            duplicate_blocked = True
        duplicate_unchanged = (
            len(host.capture_body_hand_fk_controls(preview.controls).controls)
            == 30
        )

        states_by_suffix = {
            state.control_path.rsplit("|", 1)[-1]: state
            for state in snapshot.controls
        }
        body_by_name = {joint.name: joint for joint in body_before.joints}
        first_control = states_by_suffix["AdvPy_Index1FK_R"].control_path
        second_control = states_by_suffix["AdvPy_Index2FK_R"].control_path
        second_joint = body_by_name["Index2_R"].path
        third_control = states_by_suffix["AdvPy_Index3FK_R"].control_path
        third_joint = body_by_name["Index3_R"].path
        right_end = body_by_name["IndexEnd_R"].path
        left_end = body_by_name["IndexEnd_L"].path
        right_end_before = cmds.xform(
            right_end,
            query=True,
            worldSpace=True,
            translation=True,
        )
        left_end_before = cmds.xform(
            left_end,
            query=True,
            worldSpace=True,
            translation=True,
        )
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{first_control}.rotateZ", 28.0)
        cmds.setAttr(f"{second_control}.rotateZ", 17.0)
        right_end_posed = cmds.xform(
            right_end,
            query=True,
            worldSpace=True,
            translation=True,
        )
        left_end_posed = cmds.xform(
            left_end,
            query=True,
            worldSpace=True,
            translation=True,
        )
        hierarchy_tracks_joints = (
            _close(
                cmds.xform(
                    second_control,
                    query=True,
                    worldSpace=True,
                    translation=True,
                ),
                cmds.xform(
                    second_joint,
                    query=True,
                    worldSpace=True,
                    translation=True,
                ),
            )
            and _close(
                cmds.xform(
                    third_control,
                    query=True,
                    worldSpace=True,
                    translation=True,
                ),
                cmds.xform(
                    third_joint,
                    query=True,
                    worldSpace=True,
                    translation=True,
                ),
            )
        )
        right_finger_driven = not _close(right_end_posed, right_end_before)
        left_hand_isolated = _close(left_end_posed, left_end_before)
        cmds.setAttr(f"{first_control}.rotateZ", 0.0)
        cmds.setAttr(f"{second_control}.rotateZ", 0.0)
        zero_pose_restored = _close(
            cmds.xform(
                right_end,
                query=True,
                worldSpace=True,
                translation=True,
            ),
            right_end_before,
        )
        cmds.undoInfo(stateWithoutFlush=True)

        cmds.undo()
        controls_removed = all(
            not cmds.objExists(path)
            for spec in preview.controls.roots
            for path in (spec.path,)
        ) and all(
            not cmds.objExists(path)
            for spec in preview.controls.controls
            for path in (
                spec.offset_path,
                spec.control_path,
                spec.constraint_name,
            )
        )
        body_survived = len(host.capture_body_skeleton("Root_M").joints) == 70
        body_safe_again = InspectBodyRebuildSafety(host).execute(
            container
        ).safe_to_replace
        fit_survived_undo = host.capture_fit_orientation(container) == fit_before
        marker_survived = cmds.objExists(marker)

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_HandFKControls_*",
            "AdvPy_*FK*",
            marker,
            long=True,
        ) or []
        passed = all((
            preview.ready,
            preview_clean,
            not preview.input_issues,
            len(preview.controls.roots) == 2,
            len(preview.controls.controls) == 30,
            len(snapshot.roots) == 2,
            len(snapshot.controls) == 30,
            roots_verified,
            curves_and_wiring_verified,
            zero_control_channels,
            hierarchy_verified,
            body_preserved,
            fit_preserved,
            selection_preserved,
            rebuild_blocked,
            duplicate_blocked,
            duplicate_unchanged,
            right_finger_driven,
            left_hand_isolated,
            hierarchy_tracks_joints,
            zero_pose_restored,
            controls_removed,
            body_survived,
            body_safe_again,
            fit_survived_undo,
            marker_survived,
            not remaining,
        ))
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_bilateral_hand_fk_controls",
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "input_preflight_clean": not preview.input_issues,
            "root_count": len(snapshot.roots),
            "control_count": len(snapshot.controls),
            "wrist_parented_roots_verified": roots_verified,
            "nurbs_curves_and_constraints_verified": (
                curves_and_wiring_verified
            ),
            "control_channels_zero": zero_control_channels,
            "three_level_digit_hierarchy_verified": hierarchy_verified,
            "body_bind_pose_preserved": body_preserved,
            "fit_source_preserved": fit_preserved,
            "selection_preserved": selection_preserved,
            "rebuild_blocked_while_controls_exist": rebuild_blocked,
            "duplicate_build_blocked": duplicate_blocked,
            "duplicate_left_controls_unchanged": duplicate_unchanged,
            "right_index_fk_drives_body": right_finger_driven,
            "left_hand_isolated": left_hand_isolated,
            "nested_controls_track_driven_joints": hierarchy_tracks_joints,
            "zero_pose_restored": zero_pose_restored,
            "single_undo_removed_hand_controls": controls_removed,
            "body_survived_undo": body_survived,
            "body_rebuild_safe_after_undo": body_safe_again,
            "fit_source_survived_undo": fit_survived_undo,
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
