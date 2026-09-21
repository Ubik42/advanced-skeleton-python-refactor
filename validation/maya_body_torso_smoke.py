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
            CreateFitSkeleton, BuildSyntheticBodyWithHandSourceFit, BuildSyntheticBodySourceFit,
            BuildOrientedBodySkeleton, BuildBodyCharacterRig,
        )
        from adv_py.core.fit_settings import FitSkeletonValidationError

        def position(node):
            return tuple(cmds.xform(node, query=True, worldSpace=True, translation=True))

        def matrix(node):
            return tuple(cmds.xform(node, query=True, worldSpace=True, matrix=True))

        def close(a, b):
            return len(a) == len(b) and max(abs(x-y) for x, y in zip(a, b)) < 2e-3

        def input_edit(node, attr, value):
            cmds.setAttr(f"{node}.{attr}", value)

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        source_builder = BuildSyntheticBodyWithHandSourceFit if with_hand else BuildSyntheticBodySourceFit
        source_builder(host).apply(container)
        body = BuildOrientedBodySkeleton(host).apply(container).snapshot
        joints = {j.name: j.path for j in body.joints}
        baseline = {j.name: matrix(j.path) for j in body.joints}
        marker = cmds.createNode("transform", name="SelectionMarker", skipSelect=True)
        cmds.select(marker)
        selection = cmds.ls(selection=True, long=True)
        use_case = BuildBodyCharacterRig(host)
        cmds.file(modified=False)
        plan = use_case.plan(include_torso=True)
        checks = {"plan_read_only": not cmds.file(query=True, modified=True)}
        cmds.setAttr(joints["Chest_M"] + ".rotateX", lock=True)
        try:
            use_case.apply(include_torso=True)
            checks["locked_channel_rejected"] = False
        except FitSkeletonValidationError:
            checks["locked_channel_rejected"] = not cmds.ls("AdvPy_ArmMechanisms")
        cmds.setAttr(joints["Chest_M"] + ".rotateX", lock=False)

        class FailingHost(MayaBodyBuildHost):
            def capture_body_torso(self, plan):
                super().capture_body_torso(plan)
                raise RuntimeError("Injected torso postcheck failure")

        before_nodes = set(cmds.ls(long=True))
        try:
            BuildBodyCharacterRig(FailingHost()).apply(include_torso=True)
            checks["failure_rolls_back_whole_character"] = False
        except RuntimeError as error:
            if "Injected torso" not in str(error):
                raise
            after_nodes = set(cmds.ls(long=True))
            # Maya initializes shared IK solver nodes lazily; they are not rig products.
            solvers = set(cmds.ls(type="ikSolver", long=True) or [])
            checks["failure_rolls_back_whole_character"] = (
                not (before_nodes - after_nodes) and (after_nodes - before_nodes) <= solvers
                and all(close(matrix(joints[name]), value) for name, value in baseline.items()))

        result = use_case.apply(include_torso=True)
        checks["neutral_body_preserved"] = all(close(matrix(joints[name]), value) for name, value in baseline.items())
        checks["seven_torso_controls"] = len(result.torso.controls.controls) == 7
        checks["selection_preserved"] = cmds.ls(selection=True, long=True) == selection
        controls = {spec.driven_joint.rsplit("|", 1)[-1]: spec.control_path for spec in plan.torso.torso.controls.controls}
        # Exercise motion without adding animator edits to the build's Undo entry.
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            for blend in (plan.arm.blend, plan.leg.blend):
                for side in blend.sides:
                    input_edit(blend.settings_path, side.attribute, 0.0)
            chest_before = position(joints["Head_M"])
            head_matrix_before = matrix(joints["Head_M"])
            wrist_before = position(joints["Wrist_R"])
            leg_before = position(joints["Ankle_R"])
            input_edit(controls["Chest_M"], "rotateZ", 15)
            input_edit(controls["Chest_M"], "rotateY", 8)
            checks["chest_moves_head_and_fk_arms"] = (
                not close(matrix(joints["Head_M"]), head_matrix_before)
                and not close(position(joints["Wrist_R"]), wrist_before))
            checks["chest_does_not_move_legs"] = close(position(joints["Ankle_R"]), leg_before)
            checks["fk_shoulders_follow_scapula"] = all(
                close(position(spec.path), position(spec.source_joint))
                for spec in plan.arm.mechanisms.joints if "Shoulder" in spec.name)
            input_edit(controls["Chest_M"], "rotateZ", 0)
            input_edit(controls["Chest_M"], "rotateY", 0)
            input_edit(controls["Neck_M"], "rotateZ", 12)
            checks["neck_moves_head"] = not close(position(joints["Head_M"]), chest_before)
            input_edit(controls["Neck_M"], "rotateZ", 0)
            head_before = matrix(joints["Head_M"])
            input_edit(controls["Head_M"], "rotateX", 20)
            checks["head_rotates_independently"] = not close(matrix(joints["Head_M"]), head_before) and close(position(joints["Wrist_R"]), wrist_before)
            input_edit(controls["Head_M"], "rotateX", 0)
            left_before = position(joints["Wrist_L"])
            input_edit(controls["Scapula_R"], "rotateZ", 15)
            checks["scapula_moves_only_own_arm"] = not close(position(joints["Wrist_R"]), wrist_before) and close(position(joints["Wrist_L"]), left_before)
            input_edit(controls["Scapula_R"], "rotateZ", 0)
            root_before = position(joints["Root_M"])
            input_edit(controls["Root_M"], "translateX", 1)
            checks["pelvis_moves_body_and_fk_limbs"] = all(
                not close(position(joints[name]), before)
                for name, before in (("Root_M", root_before), ("Wrist_R", wrist_before), ("Ankle_R", leg_before)))
            input_edit(controls["Root_M"], "translateX", 0)
            # IK goals retain global space as torso and limb origins move.
            for blend in (plan.arm.blend, plan.leg.blend):
                for side in blend.sides:
                    input_edit(blend.settings_path, side.attribute, 1.0)
            targets = tuple(spec.wrist_control_path for spec in plan.arm.ik.limbs) + tuple(spec.ankle_control_path for spec in plan.leg.ik.limbs)
            target_before = {path: position(path) for path in targets}
            input_edit(controls["Root_M"], "translateX", 0.3)
            input_edit(controls["Chest_M"], "rotateZ", 5)
            checks["ik_targets_stay_in_global_space"] = all(close(position(path), value) for path, value in target_before.items())
            checks["ik_limbs_reach_goals"] = all(close(position(joints[f"{name}_{side}"]), position(target))
                for name, side, target in (
                    ("Wrist", "R", plan.arm.ik.limbs[0].wrist_control_path),
                    ("Wrist", "L", plan.arm.ik.limbs[1].wrist_control_path),
                    ("Ankle", "R", plan.leg.ik.limbs[0].ankle_control_path),
                    ("Ankle", "L", plan.leg.ik.limbs[1].ankle_control_path)))
            checks["stretch_origins_follow_body"] = all(close(position(spec.start_path), position(joints[f"{name}_{spec.side.value}"]))
                for module, name in ((plan.arm, "Shoulder"), (plan.leg, "Hip")) for spec in module.stretch.sides)
            input_edit(controls["Root_M"], "translateX", 0)
            input_edit(controls["Chest_M"], "rotateZ", 0)
            input_edit(controls["Chest_M"], "rotateY", 0)
            for blend in (plan.arm.blend, plan.leg.blend):
                for side in blend.sides:
                    input_edit(blend.settings_path, side.attribute, 0.0)
            before_scale = {name: position(path) for name, path in joints.items()}
            input_edit(plan.global_control.control_path, "globalScale", 1.5)
            checks["global_scale_once"] = all(close(position(joints[name]), tuple(v * 1.5 for v in value)) for name, value in before_scale.items())
            input_edit(plan.global_control.control_path, "globalScale", 1.0)
            checks["neutral_restored"] = all(close(matrix(joints[name]), value) for name, value in baseline.items())
        finally:
            cmds.undoInfo(stateWithoutFlush=True)
        cmds.undo()
        checks["one_undo_removes_all_controls"] = not cmds.ls("AdvPy_Torso*", "AdvPy_ArmMechanisms", "AdvPy_LegMechanisms", "AdvPy_Global")
        checks["undo_preserves_body_fit"] = cmds.objExists("Root_M") and cmds.objExists("FitSkeleton")
        cmds.redo()
        checks["redo_restores_torso"] = cmds.objExists(plan.torso.torso.controls.root_path)
        cmds.file(new=True, force=True)
        result_json = {"host": "maya", "version": cmds.about(version=True), "body_joint_count": len(body.joints), **checks,
                       "duration_seconds": round(time.perf_counter()-started, 3),
                       "status": "passed" if all(checks.values()) else "failed"}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result_json, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result_json, indent=2))
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), with_hand="--basic" not in sys.argv[2:]))
