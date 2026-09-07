from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def close(left, right, tolerance=1e-3):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def pose_matches(before, after):
    wanted = {joint.name: joint for joint in before.joints if joint.name in {"Shoulder_R", "Elbow_R", "Wrist_R"}}
    current = {joint.name: joint for joint in after.joints if joint.name in wanted}
    return set(wanted) == set(current) and all(
        close(wanted[name].world_position, current[name].world_position)
        and (name != "Wrist_R" or all(close(a, b) for a, b in zip(wanted[name].world_axes, current[name].world_axes)))
        for name in wanted
    )


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import BuildBodyArmRig, BuildOrientedBodySkeleton, BuildSyntheticBodySourceFit, CreateFitSkeleton, MatchBodyArmFkToIk
        from adv_py.core import FitBuildSide

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode("transform", name="PortableFkToIkSelection", skipSelect=True)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        BuildOrientedBodySkeleton(host).apply(container)
        cmds.select(marker, replace=True)
        rig = BuildBodyArmRig(host).apply(container)

        fk = {state.control_path.rsplit("AdvPy_", 1)[-1]: state.control_path for state in rig.fk_controls.controls if state.control_path.endswith("_R")}
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{fk['ShoulderFK_R']}.rotateZ", 23.0)
        cmds.setAttr(f"{fk['ElbowFK_R']}.rotateY", -31.0)
        cmds.setAttr(f"{fk['WristFK_R']}.rotateX", 17.0)
        cmds.undoInfo(stateWithoutFlush=True)
        before = host.capture_body_skeleton("Root_M")

        use_case = MatchBodyArmFkToIk(host)
        cmds.file(modified=False)
        preview = use_case.plan(FitBuildSide.RIGHT, container)
        preview_clean = not cmds.file(query=True, modified=True)
        result = use_case.apply(FitBuildSide.RIGHT, container)
        values = {side.side: side.attribute_value for side in result.blend.sides}
        wrist_offset = cmds.listRelatives(result.plan.match.wrist_control_path, parent=True, fullPath=True)[0]
        pole_offset = cmds.listRelatives(result.plan.match.pole_control_path, parent=True, fullPath=True)[0]
        wrist_value = cmds.getAttr(f"{wrist_offset}.visibility")
        pole_value = cmds.getAttr(f"{pole_offset}.visibility")
        checks = {
            "preview_ready": preview.ready,
            "preview_clean": preview_clean,
            "body_pose_preserved": pose_matches(before, result.body),
            "right_switched_to_ik": values[FitBuildSide.RIGHT] == 1.0,
            "left_blend_unchanged": values[FitBuildSide.LEFT] == 0.0,
            "ik_controls_visible": wrist_value == 1 and pole_value == 1,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.undo()
        after_undo = host.capture_body_skeleton("Root_M")
        checks["single_undo_restored_fk_mode"] = cmds.getAttr("|AdvPy_ArmSettings.armIkFk_R") == 0.0
        checks["single_undo_restored_pose"] = pose_matches(before, after_undo)
        cmds.undo()
        checks["second_undo_removed_complete_arm_rig"] = all(
            not cmds.objExists(path)
            for path in ("|AdvPy_ArmMechanisms", "|AdvPy_ArmFKControls", "|AdvPy_ArmIKControls", "|AdvPy_ArmSettings")
        )

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls("Root_M", "FitSkeleton", "AdvPy_Arm*", marker, long=True) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_arm_fk_to_ik_match",
            **checks,
            "remaining_nodes": remaining,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if passed else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if passed else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
