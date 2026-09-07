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
        and (
            name not in {"Ankle_R", "Toes_R"}
            or all(
                close(actual, expected)
                for actual, expected in zip(
                    wanted[name].world_axes, current[name].world_axes
                )
            )
        )
        for name in wanted
    )


def left_pose_matches(before, after):
    wanted = {
        joint.name: joint.world_position
        for joint in before.joints
        if joint.name in {"Hip_L", "Knee_L", "Ankle_L", "Toes_L"}
    }
    current = {
        joint.name: joint.world_position
        for joint in after.joints
        if joint.name in wanted
    }
    return set(wanted) == set(current) and all(
        close(wanted[name], current[name]) for name in wanted
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
            MatchBodyLegFkToIk,
        )
        from adv_py.core import FitBuildSide

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform", name="PortableLegFkToIkSelection", skipSelect=True
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        BuildOrientedBodySkeleton(host).apply(container)
        cmds.select(marker, replace=True)
        rig = BuildBodyLegRig(host).apply(container)

        controls = {
            state.control_path.rsplit("AdvPy_", 1)[-1]: state.control_path
            for state in rig.fk_controls.controls
            if state.control_path.endswith("_R")
        }
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{controls['HipFK_R']}.rotateZ", 23.0)
        cmds.setAttr(f"{controls['KneeFK_R']}.rotateY", -31.0)
        cmds.setAttr(f"{controls['AnkleFK_R']}.rotateX", 17.0)
        cmds.setAttr(f"{controls['ToesFK_R']}.rotateY", 28.0)
        cmds.undoInfo(stateWithoutFlush=True)
        before = host.capture_body_skeleton("Root_M")

        use_case = MatchBodyLegFkToIk(host)
        cmds.file(modified=False)
        preview = use_case.plan(FitBuildSide.RIGHT, container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(FitBuildSide.RIGHT, container)
        target_foot_values = tuple(
            value
            for side in result.foot.sides
            if side.side is FitBuildSide.RIGHT
            for plug, value in side.attribute_values
        )

        values = {side.side: side.attribute_value for side in result.blend.sides}
        target_visibility = next(
            side for side in rig.plan.visibility.sides
            if side.side is FitBuildSide.RIGHT
        )
        left_visibility = next(
            side for side in rig.plan.visibility.sides
            if side.side is FitBuildSide.LEFT
        )
        checks = {
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "target_pose_preserved": target_pose_matches(before, result.body),
            "toe_ik_control_used": preview.match.toe_control_path.endswith(
                "AdvPy_ToeIK_R"
            ),
            "target_foot_channels_reset": all(
                abs(value) <= 1e-6 for value in target_foot_values
            ),
            "left_pose_preserved": left_pose_matches(before, result.body),
            "right_switched_to_ik": values[FitBuildSide.RIGHT] == 1.0,
            "left_blend_unchanged": values[FitBuildSide.LEFT] == 0.0,
            "right_ik_controls_visible": (
                cmds.getAttr(f"{target_visibility.fk_offset_path}.visibility") == 0
                and all(
                    cmds.getAttr(f"{path}.visibility") == 1
                    for path in target_visibility.ik_offset_paths
                )
            ),
            "left_fk_controls_remain_visible": (
                cmds.getAttr(f"{left_visibility.fk_offset_path}.visibility") == 1
                and all(
                    cmds.getAttr(f"{path}.visibility") == 0
                    for path in left_visibility.ik_offset_paths
                )
            ),
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.undo()
        after_undo = host.capture_body_skeleton("Root_M")
        checks["single_undo_restored_fk_mode"] = (
            cmds.getAttr("|AdvPy_LegSettings.legIkFk_R") == 0.0
        )
        checks["single_undo_restored_pose"] = target_pose_matches(
            before, after_undo
        )
        checks["single_undo_restored_foot_values"] = all(
            abs(cmds.getAttr(
                f"{preview.match.ankle_control_path}.{attribute}"
            )) <= 1e-6
            for attribute in ("heelRoll", "outerBank", "innerBank", "toeRoll", "ballRoll")
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
            "slice": "body_leg_fk_to_ik_foot_match",
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
