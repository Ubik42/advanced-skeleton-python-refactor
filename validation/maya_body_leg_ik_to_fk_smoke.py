from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def close(left, right, tolerance=1e-3):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def target_pose_matches(before, after):
    names = {"Hip_R", "Knee_R", "Ankle_R", "Toes_R"}
    wanted = {joint.name: joint for joint in before.joints if joint.name in names}
    current = {joint.name: joint for joint in after.joints if joint.name in names}
    return set(wanted) == set(current) and all(
        close(wanted[name].world_position, current[name].world_position)
        and all(
            close(actual, expected)
            for actual, expected in zip(
                wanted[name].world_axes, current[name].world_axes
            )
        )
        for name in wanted
    )


def left_pose_matches(before, after):
    names = {"Hip_L", "Knee_L", "Ankle_L", "Toes_L"}
    wanted = {joint.name: joint for joint in before.joints if joint.name in names}
    current = {joint.name: joint for joint in after.joints if joint.name in names}
    return set(wanted) == set(current) and all(
        close(wanted[name].world_position, current[name].world_position)
        and all(
            close(actual, expected)
            for actual, expected in zip(
                wanted[name].world_axes, current[name].world_axes
            )
        )
        for name in wanted
    )


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyLegRig,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            MatchBodyLegIkToFk,
        )
        from adv_py.core import FitBuildSide

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform", name="PortableLegIkToFkSelection", skipSelect=True
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        BuildOrientedBodySkeleton(host).apply(container)
        cmds.select(marker, replace=True)
        rig = BuildBodyLegRig(host).apply(container)

        limb = next(
            state for state in rig.ik.limbs
            if state.side is FitBuildSide.RIGHT
        )
        body_by_name = {joint.name: joint for joint in rig.body.joints}
        ankle = body_by_name["Ankle_R"].world_position
        knee = body_by_name["Knee_R"].world_position
        target = tuple(
            end + (middle - end) * 0.25
            for end, middle in zip(ankle, knee)
        )
        pole = list(cmds.xform(
            limb.pole_control_path,
            query=True,
            worldSpace=True,
            translation=True,
        ))
        pole[2] += 2.5
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr("|AdvPy_LegSettings.legIkFk_R", 1.0)
        cmds.xform(limb.ankle_control_path, worldSpace=True, translation=target)
        cmds.xform(limb.pole_control_path, worldSpace=True, translation=pole)
        cmds.setAttr(f"{limb.ankle_control_path}.rotateX", 19.0)
        cmds.setAttr(f"{limb.ankle_control_path}.rotateZ", -13.0)
        cmds.undoInfo(stateWithoutFlush=True)
        before = host.capture_body_skeleton("Root_M")

        use_case = MatchBodyLegIkToFk(host)
        cmds.file(modified=False)
        preview = use_case.plan(FitBuildSide.RIGHT, container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(FitBuildSide.RIGHT, container)

        values = {side.side: side.attribute_value for side in result.blend.sides}
        translations_zero = all(
            close(
                cmds.getAttr(f"{path}.translate")[0],
                (0.0, 0.0, 0.0),
                1e-4,
            )
            for path in result.plan.match.fk_control_paths
        )
        fk_offset = cmds.listRelatives(
            result.plan.match.fk_control_paths[0],
            parent=True,
            fullPath=True,
        )[0]
        checks = {
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "target_pose_preserved": target_pose_matches(before, result.body),
            "left_pose_preserved": left_pose_matches(before, result.body),
            "right_switched_to_fk": values[FitBuildSide.RIGHT] == 0.0,
            "left_blend_unchanged": values[FitBuildSide.LEFT] == 0.0,
            "fk_controls_visible": cmds.getAttr(f"{fk_offset}.visibility") == 1,
            "fk_control_translations_remain_zero": translations_zero,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.undo()
        after_undo = host.capture_body_skeleton("Root_M")
        checks["single_undo_restored_ik_mode"] = (
            cmds.getAttr("|AdvPy_LegSettings.legIkFk_R") == 1.0
        )
        checks["single_undo_restored_pose"] = target_pose_matches(
            before, after_undo
        )
        cmds.undo()
        checks["second_undo_removed_complete_leg_rig"] = not (
            cmds.ls("AdvPy_Leg*", long=True) or []
        )

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M", "FitSkeleton", "AdvPy_Leg*", marker, long=True
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_leg_ik_to_fk_match",
            **checks,
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
