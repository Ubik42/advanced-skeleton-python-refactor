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


def axes(cmds, path):
    matrix = cmds.xform(path, query=True, worldSpace=True, matrix=True)
    return tuple(tuple(float(value) for value in matrix[index:index + 3]) for index in (0, 4, 8))


def axes_close(left, right, tolerance=1e-3):
    return all(close(a, b, tolerance) for a, b in zip(left, right))


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
            "transform", name="PortableLegFootSelection", skipSelect=True
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        BuildOrientedBodySkeleton(host).apply(container)
        cmds.select(marker, replace=True)
        use_case = BuildBodyLegRig(host)
        cmds.file(modified=False)
        preview = use_case.plan(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container)

        right = next(
            side for side in result.foot.sides
            if side.side is FitBuildSide.RIGHT
        )
        right_spec = next(
            side for side in result.plan.foot.sides
            if side.side is FitBuildSide.RIGHT
        )
        handle = (cmds.ls(right_spec.handle_name, long=True, type="ikHandle") or [None])[0]
        original_position = tuple(cmds.xform(
            handle, query=True, worldSpace=True, translation=True
        ))
        motion = {}
        cmds.undoInfo(stateWithoutFlush=False)
        for attribute in right_spec.attributes:
            plug = f"{right_spec.ankle_control_path}.{attribute}"
            cmds.setAttr(plug, 12.0)
            current = tuple(cmds.xform(
                handle, query=True, worldSpace=True, translation=True
            ))
            motion[attribute] = not close(current, original_position)
            cmds.setAttr(plug, 0.0)
        pivot_by_role = {pivot.role.value: pivot for pivot in right_spec.pivots}

        def roll_outputs(value, manual_ball=0.0):
            cmds.setAttr(f"{right_spec.ankle_control_path}.footRoll", value)
            cmds.setAttr(
                f"{right_spec.ankle_control_path}.ballRoll", manual_ball
            )
            result = tuple(
                float(cmds.getAttr(pivot_by_role[role].target_plug))
                for role in ("heel", "ball", "toe")
            )
            cmds.setAttr(f"{right_spec.ankle_control_path}.footRoll", 0.0)
            cmds.setAttr(f"{right_spec.ankle_control_path}.ballRoll", 0.0)
            return result

        negative_roll = roll_outputs(-30.0)
        ball_phase = roll_outputs(20.0)
        toe_phase = roll_outputs(70.0)
        additive_ball = roll_outputs(20.0, manual_ball=5.0)
        ankle_axes = axes(cmds, right_spec.ankle_driver_path)
        toe_axes = axes(cmds, right_spec.toe_driver_path)
        cmds.setAttr(f"{right_spec.ankle_control_path}.ballRoll", 12.0)
        ball_rotates_ankle = not axes_close(
            axes(cmds, right_spec.ankle_driver_path), ankle_axes
        )
        ball_keeps_toe_planted = axes_close(
            axes(cmds, right_spec.toe_driver_path), toe_axes
        )
        cmds.setAttr(f"{right_spec.ankle_control_path}.ballRoll", 0.0)
        cmds.setAttr(f"{right_spec.ankle_control_path}.toeRoll", 12.0)
        toe_rotates_ankle = not axes_close(
            axes(cmds, right_spec.ankle_driver_path), ankle_axes
        )
        toe_rotates_toes = not axes_close(
            axes(cmds, right_spec.toe_driver_path), toe_axes
        )
        cmds.setAttr(f"{right_spec.ankle_control_path}.toeRoll", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)

        match_preview = MatchBodyLegFkToIk(host).plan(
            FitBuildSide.RIGHT, container
        )
        checks = {
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "two_sides_created": len(result.foot.sides) == 2,
            "ten_pivots_created": sum(
                len(side.pivots) for side in result.foot.sides
            ) == 10,
            "handle_parented_to_ball": all(
                side.handle_parent_path == side.pivots[-1].path
                for side in result.foot.sides
            ),
            "six_channels_move_handle": all(motion.values()),
            "negative_roll_uses_heel": close(
                negative_roll, (-30.0, 0.0, 0.0)
            ),
            "positive_roll_starts_on_ball": close(
                ball_phase, (0.0, 20.0, 0.0)
            ),
            "roll_after_break_reaches_toe": close(
                toe_phase, (0.0, 45.0, 25.0)
            ),
            "manual_ball_roll_is_additive": close(
                additive_ball, (0.0, 25.0, 0.0)
            ),
            "ball_roll_rotates_ankle": ball_rotates_ankle,
            "ball_roll_keeps_toe_planted": ball_keeps_toe_planted,
            "toe_roll_rotates_ankle": toe_rotates_ankle,
            "toe_roll_rotates_toes": toe_rotates_toes,
            "inner_bank_sign_is_negative": next(
                pivot for pivot in right.pivots if pivot.multiplier_value is not None
            ).multiplier_value == -1.0,
            "fk_to_ik_match_still_preflights": match_preview.ready,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.undo()
        checks["single_undo_removed_complete_leg_rig_with_foot"] = (
            not (cmds.ls("AdvPy_Foot*", long=True) or [])
            and not (cmds.ls("AdvPy_Leg*", long=True) or [])
        )

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M", "FitSkeleton", "AdvPy_Leg*", "AdvPy_Foot*", marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_leg_segmented_foot_roll",
            **checks,
            "channel_motion": motion,
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
