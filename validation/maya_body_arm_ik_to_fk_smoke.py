from __future__ import annotations

import json
import os
import sys
import time
from math import sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def close(left, right, tolerance=1e-3):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def pose_matches(before, after):
    names = {"Shoulder_R", "Elbow_R", "Wrist_R"}
    wanted = {joint.name: joint for joint in before.joints if joint.name in names}
    current = {joint.name: joint for joint in after.joints if joint.name in names}
    return set(wanted) == set(current) and all(
        close(wanted[name].world_position, current[name].world_position)
        and all(close(a, b) for a, b in zip(wanted[name].world_axes, current[name].world_axes))
        for name in wanted
    )


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import BuildBodyArmRig, BuildOrientedBodySkeleton, BuildSyntheticBodySourceFit, CreateFitSkeleton, MatchBodyArmIkToFk
        from adv_py.core import FitBuildSide

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode("transform", name="PortableIkToFkSelection", skipSelect=True)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        BuildOrientedBodySkeleton(host).apply(container)
        cmds.select(marker, replace=True)
        rig = BuildBodyArmRig(host).apply(container)

        limb = next(state for state in rig.ik.limbs if state.side is FitBuildSide.RIGHT)
        stretch = next(state for state in rig.plan.stretch.sides if state.side is FitBuildSide.RIGHT)
        wrist = list(cmds.xform(limb.wrist_control_path, query=True, worldSpace=True, translation=True))
        direction = tuple(value - start for value, start in zip(wrist, stretch.start_position))
        direction_length = sqrt(sum(value * value for value in direction))
        unit = tuple(value / direction_length for value in direction)
        target_ratio = 1.35
        target = tuple(
            start + axis * stretch.rest_length * target_ratio
            for start, axis in zip(stretch.start_position, unit)
        )
        pole = list(cmds.xform(limb.pole_control_path, query=True, worldSpace=True, translation=True))
        pole[2] += 2.5
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr("|AdvPy_ArmSettings.armIkFk_R", 1.0)
        cmds.xform(limb.wrist_control_path, worldSpace=True, translation=target)
        cmds.xform(limb.pole_control_path, worldSpace=True, translation=pole)
        cmds.setAttr(f"{limb.wrist_control_path}.rotateX", 19.0)
        cmds.setAttr(f"{limb.wrist_control_path}.rotateZ", -13.0)
        cmds.undoInfo(stateWithoutFlush=True)
        before = host.capture_body_skeleton("Root_M")

        use_case = MatchBodyArmIkToFk(host)
        cmds.file(modified=False)
        preview = use_case.plan(FitBuildSide.RIGHT, container)
        preview_clean = not cmds.file(query=True, modified=True)
        result = use_case.apply(FitBuildSide.RIGHT, container)
        values = {side.side: side.attribute_value for side in result.blend.sides}
        translations_zero = all(
            close(cmds.getAttr(f"{path}.translate")[0], (0.0, 0.0, 0.0), 1e-4)
            for path in result.plan.match.fk_control_paths
        )
        matched_segments = tuple(
            float(cmds.getAttr(plug)) for plug in result.plan.match.fk_segment_plugs
        )
        shoulder_fk_offset = cmds.listRelatives(result.plan.match.fk_control_paths[0], parent=True, fullPath=True)[0]
        checks = {
            "preview_ready": preview.ready,
            "preview_clean": preview_clean,
            "body_pose_preserved": pose_matches(before, result.body),
            "stretched_pose_was_tested": abs(
                sum(abs(value) for value in result.plan.match.fk_segment_translations)
                / stretch.rest_length
                - target_ratio
            ) < 2e-3,
            "fk_segment_lengths_matched": close(
                matched_segments,
                result.plan.match.fk_segment_translations,
                1e-4,
            ),
            "right_switched_to_fk": values[FitBuildSide.RIGHT] == 0.0,
            "left_blend_unchanged": values[FitBuildSide.LEFT] == 0.0,
            "fk_controls_visible": cmds.getAttr(f"{shoulder_fk_offset}.visibility") == 1,
            "fk_control_translations_remain_zero": translations_zero,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.undo()
        after_undo = host.capture_body_skeleton("Root_M")
        checks["single_undo_restored_ik_mode"] = cmds.getAttr("|AdvPy_ArmSettings.armIkFk_R") == 1.0
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
            "slice": "body_arm_ik_to_fk_match",
            **checks,
            "target_stretch_ratio": target_ratio,
            "matched_fk_segments": [round(value, 6) for value in matched_segments],
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
