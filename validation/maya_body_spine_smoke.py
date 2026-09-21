from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import maya.standalone


def main(output, with_hand=True):
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            CreateFitSkeleton, BuildSyntheticBodySourceFit, BuildSyntheticBodyWithHandSourceFit,
            BuildOrientedBodySkeleton, BuildBodyCharacterRig, MatchBodySpine,
        )
        from adv_py.core.fit_settings import FitSkeletonValidationError
        def matrix(node):
            return tuple(cmds.xform(node, query=True, worldSpace=True, matrix=True))
        def error(before, after):
            return max(abs(a-b) for (_, old), (_, new) in zip(before, after) for a, b in zip(old, new))
        def edit(node, attr, value):
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                cmds.setAttr(node + "." + attr, value)
            finally:
                cmds.undoInfo(stateWithoutFlush=True)
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        (BuildSyntheticBodyWithHandSourceFit if with_hand else BuildSyntheticBodySourceFit)(host).apply(container)
        original = BuildOrientedBodySkeleton(host).apply(container).snapshot
        joints = {j.name: j.path for j in original.joints}
        marker = cmds.createNode("transform", name="SpineSelection", skipSelect=True)
        cmds.select(marker)
        use_case = BuildBodyCharacterRig(host)
        cmds.file(modified=False)
        planned = use_case.plan(include_torso=True, include_spine_ik=True)
        checks = {"plan_read_only": not cmds.file(query=True, modified=True)}
        result = use_case.apply(include_torso=True, include_spine_ik=True)
        spine = result.plan.torso.torso.spine
        neutral = host.capture_body_spine_pose(spine)
        MatchBodySpine(host).execute(spine, "ik")
        MatchBodySpine(host).execute(spine, "fk")
        checks["straight_bind_matches_both_directions"] = error(neutral, host.capture_body_spine_pose(spine)) < 1e-4
        checks["eight_torso_controls_and_six_drivers"] = len(result.torso.controls.controls) == 8 and len(spine.joints) == 6
        root_before = matrix(joints["Root_M"])
        hips_before = (matrix(joints["Hip_R"]), matrix(joints["Hip_L"]))
        wrist_before = matrix(joints["Wrist_R"])
        edit(spine.fk_controls[0], "rotateY", 12)
        edit(spine.fk_controls[1], "rotateZ", -24)
        edit(spine.fk_controls[1], "rotateX", 17)
        edit(spine.fk_controls[2], "rotateY", 9)
        checks["fk_spine_moves_arms_without_moving_pelvis_or_hips"] = (
            matrix(joints["Wrist_R"]) != wrist_before and matrix(joints["Root_M"]) == root_before
            and (matrix(joints["Hip_R"]), matrix(joints["Hip_L"])) == hips_before)
        before = host.capture_body_spine_pose(spine)
        matched = MatchBodySpine(host).execute(spine, "ik")
        fk_to_ik_error = error(before, matched)
        checks["fk_to_ik_preserves_all_body_matrices"] = fk_to_ik_error < 1e-4 and cmds.getAttr(spine.blend_plug) == 1
        cmds.undo()
        checks["match_undo_restores_fk"] = cmds.getAttr(spine.blend_plug) == 0 and error(before, host.capture_body_spine_pose(spine)) < 1e-4
        cmds.redo()
        checks["match_redo_restores_ik"] = cmds.getAttr(spine.blend_plug) == 1 and error(before, host.capture_body_spine_pose(spine)) < 1e-4
        edit(spine.ik_control, "translateY", cmds.getAttr(spine.ik_control + ".translateY") + 0.2)
        edit(spine.ik_control, "rotateZ", cmds.getAttr(spine.ik_control + ".rotateZ") + 14)
        edit(spine.ik_control, "waistRoll", 28)
        ik_pose = host.capture_body_spine_pose(spine)
        checks["ik_spine_moves_chest"] = error(before, ik_pose) > 0.01
        edit(spine.ik_control, "spineIkFk", 0.5)
        blend_error = 0.0
        for body, fk, ik in ((spine.body_joints[1], spine.joints[1].path, spine.waist_output),
                             (spine.body_joints[2], spine.joints[2].path, spine.joints[5].path)):
            expected = tuple((a+b)/2 for a, b in zip(matrix(fk)[12:15], matrix(ik)[12:15]))
            blend_error = max(blend_error, max(abs(a-b) for a, b in zip(expected, matrix(body)[12:15])))
        checks["half_blend_interpolates_position"] = blend_error < 1e-4
        try:
            MatchBodySpine(host).execute(spine, "fk")
            checks["matching_from_partial_blend_rejected"] = False
        except FitSkeletonValidationError:
            checks["matching_from_partial_blend_rejected"] = cmds.getAttr(spine.blend_plug) == 0.5
        edit(spine.ik_control, "spineIkFk", 1.0)
        matched = MatchBodySpine(host).execute(spine, "fk")
        ik_to_fk_error = error(ik_pose, matched)
        checks["ik_to_fk_preserves_all_body_matrices"] = ik_to_fk_error < 1e-4 and cmds.getAttr(spine.blend_plug) == 0
        edit(result.plan.global_control.control_path, "globalScale", 1.5)
        edit(result.plan.global_control.control_path, "rotateY", 22)
        edit(result.plan.global_control.control_path, "translateZ", 1)
        scaled = host.capture_body_spine_pose(spine)
        matched = MatchBodySpine(host).execute(spine, "ik")
        scaled_error = error(scaled, matched)
        checks["matching_under_global_scale"] = scaled_error < 1e-4
        cmds.setAttr(spine.fk_controls[0] + ".rotateX", lock=True)
        undo_before = cmds.undoInfo(query=True, undoName=True)
        try:
            MatchBodySpine(host).execute(spine, "fk")
            checks["locked_destination_rejected_before_mutation"] = False
        except FitSkeletonValidationError:
            checks["locked_destination_rejected_before_mutation"] = cmds.getAttr(spine.blend_plug) == 1 and cmds.undoInfo(query=True, undoName=True) == undo_before
        cmds.setAttr(spine.fk_controls[0] + ".rotateX", lock=False)
        class FailedMatchHost(MayaBodyBuildHost):
            def match_body_spine(self, plan, mode):
                super().match_body_spine(plan, mode)
                raise RuntimeError("Injected match failure")
        before_failure = host.capture_body_spine_pose(spine)
        try:
            MatchBodySpine(FailedMatchHost()).execute(spine, "fk")
            checks["failed_match_rolls_back"] = False
        except RuntimeError as exc:
            if "Injected" not in str(exc):
                raise
            checks["failed_match_rolls_back"] = cmds.getAttr(spine.blend_plug) == 1 and error(before_failure, host.capture_body_spine_pose(spine)) < 1e-4
        checks["selection_and_time_preserved"] = cmds.ls(selection=True) == [marker] and cmds.currentTime(query=True) == 1
        # A fresh build establishes the whole-character Undo boundary independently of match history.
        cmds.file(new=True, force=True)
        container = CreateFitSkeleton(host).apply().state.path
        (BuildSyntheticBodyWithHandSourceFit if with_hand else BuildSyntheticBodySourceFit)(host).apply(container)
        BuildOrientedBodySkeleton(host).apply(container)
        BuildBodyCharacterRig(host).apply(include_torso=True, include_spine_ik=True)
        original_build_pose = host.capture_body_spine_pose(spine)
        cmds.undo()
        checks["one_build_undo_preserves_body_and_removes_spine"] = cmds.objExists("Root_M") and not cmds.ls("AdvPy_Spine*", "AdvPy_Global")
        cmds.redo()
        checks["build_redo_restores_spine"] = cmds.objExists(spine.root_path) and error(original_build_pose,host.capture_body_spine_pose(spine)) < 1e-4
        cmds.file(new=True, force=True)
        report = {"host": "maya", "version": cmds.about(version=True), "body_joint_count": len(original.joints),
                  **checks, "fk_to_ik_matrix_error": fk_to_ik_error, "ik_to_fk_matrix_error": ik_to_fk_error,
                  "scaled_match_matrix_error": scaled_error, "duration_seconds": round(time.perf_counter()-started, 3),
                  "status": "passed" if all(checks.values()) else "failed"}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), with_hand="--basic" not in sys.argv[2:]))
