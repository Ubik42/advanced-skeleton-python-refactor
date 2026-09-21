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
        from adv_py.application import CreateFitSkeleton, BuildSyntheticBodySourceFit, BuildSyntheticBodyWithHandSourceFit, BuildOrientedBodySkeleton, BuildBodyCharacterRig, SwitchBodyControlSpace
        from adv_py.core.body_control_spaces import control_space_pose_error
        from adv_py.core.fit_settings import FitSkeletonValidationError
        def matrix(node):
            return tuple(cmds.xform(node, query=True, worldSpace=True, matrix=True))
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
        body = BuildOrientedBodySkeleton(host).apply(container).snapshot
        marker = cmds.createNode("transform", name="SpaceSelection", skipSelect=True)
        cmds.select(marker)
        rig = BuildBodyCharacterRig(host).apply(include_torso=True, include_spine_ik=True, include_control_spaces=True)
        plan = rig.plan.control_spaces
        switch = SwitchBodyControlSpace(host)
        checks = {"five_spaces_nine_constraints": len(plan.spaces) == 5 and len(plan.node_names) == 9}
        original_pose = host.capture_control_space_pose(plan)
        cmds.undo()
        checks["one_undo_removes_complete_character"] = not cmds.ls("AdvPy_Space_*", "AdvPy_Global", "AdvPy_Spine*") and cmds.objExists("Root_M")
        cmds.redo()
        checks["redo_preserves_body_and_offsets"] = control_space_pose_error(original_pose, host.capture_control_space_pose(plan)) < 1e-4
        checks["redo_restores_spaces"] = all(host.capture_control_space_mode(s) == s.initial_mode for s in plan.spaces)
        for module in (rig.plan.arm, rig.plan.leg):
            for side in module.blend.sides:
                edit(module.blend.settings_path, side.attribute, 1)
        edit(rig.plan.torso.torso.spine.fk_controls[1], "rotateZ", 10)
        edit(rig.plan.global_control.control_path, "globalScale", 1.5)
        edit(rig.plan.global_control.control_path, "rotateY", 20)
        edit(rig.plan.global_control.control_path, "translateZ", 2)
        errors = []
        for spec in plan.spaces:
            for mode in ("body", "global"):
                before = host.capture_control_space_pose(plan)
                after = switch.execute(plan, spec.key, mode)
                errors.append(control_space_pose_error(before, after))
                if host.capture_control_space_mode(spec) != mode:
                    raise RuntimeError("space mode readback mismatch")
        checks["all_switches_preserve_body_and_offsets"] = max(errors) < 1e-4
        goals = tuple(s.targets[0] for s in plan.spaces[1:])
        before_goals = tuple(matrix(p) for p in goals)
        head_before = matrix(plan.space("head").targets[0])
        pelvis = rig.plan.torso.torso.pelvis_translation.source
        edit(pelvis, "translateX", 0.2)
        checks["global_goals_ignore_pelvis_motion"] = max(abs(a-b) for old, path in zip(before_goals, goals) for a, b in zip(old, matrix(path))) < 1e-4
        neck = next(s.control_path for s in rig.plan.torso.torso.controls.controls if s.driven_joint.endswith("|Neck_M"))
        edit(neck, "rotateZ", 15)
        head_after = matrix(plan.space("head").targets[0])
        checks["global_head_orientation_ignores_neck_rotation"] = max(abs(a-b) for a,b in zip(head_before[:12],head_after[:12])) < 1e-4
        for spec in plan.spaces:
            switch.execute(plan, spec.key, "body")
        before_goals = tuple(matrix(p) for p in goals)
        head_before = matrix(plan.space("head").targets[0])
        edit(pelvis, "translateX", 0.4)
        checks["body_goals_follow_pelvis"] = all(max(abs(a-b) for a,b in zip(old, matrix(path))) > 1e-3 for old,path in zip(before_goals,goals))
        edit(neck, "rotateZ", 25)
        checks["body_head_orientation_follows_neck"] = max(abs(a-b) for a,b in zip(head_before[:12],matrix(plan.space("head").targets[0])[:12])) > 1e-3
        before = host.capture_control_space_pose(plan)
        switch.execute(plan, "hand_R", "global")
        cmds.undo()
        checks["switch_undo"] = host.capture_control_space_mode(plan.space("hand_R")) == "body" and control_space_pose_error(before, host.capture_control_space_pose(plan)) < 1e-4
        cmds.redo()
        checks["switch_redo"] = host.capture_control_space_mode(plan.space("hand_R")) == "global"
        target = plan.space("hand_R").targets[0]
        cmds.setAttr(target + ".translateX", lock=True)
        try:
            switch.execute(plan, "hand_R", "body")
            checks["locked_target_rejected"] = False
        except FitSkeletonValidationError:
            checks["locked_target_rejected"] = host.capture_control_space_mode(plan.space("hand_R")) == "global"
        cmds.setAttr(target + ".translateX", lock=False)
        class FailedHost(MayaBodyBuildHost):
            def switch_control_space(self, spec, mode):
                super().switch_control_space(spec, mode)
                raise RuntimeError("Injected switch failure")
        before = host.capture_control_space_pose(plan)
        try:
            SwitchBodyControlSpace(FailedHost()).execute(plan, "hand_R", "body")
            checks["switch_failure_rolls_back"] = False
        except RuntimeError as exc:
            if "Injected" not in str(exc):
                raise
            checks["switch_failure_rolls_back"] = host.capture_control_space_mode(plan.space("hand_R")) == "global" and control_space_pose_error(before,host.capture_control_space_pose(plan)) < 1e-4
        checks["selection_and_time_preserved"] = cmds.ls(selection=True) == [marker] and cmds.currentTime(query=True) == 1
        cmds.file(new=True, force=True)
        report = {"host": "maya", "version": cmds.about(version=True), "body_joint_count": len(body.joints), **checks,
                  "max_switch_matrix_error": max(errors), "duration_seconds": round(time.perf_counter()-started, 3),
                  "status": "passed" if all(checks.values()) else "failed"}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), with_hand="--basic" not in sys.argv[2:]))
