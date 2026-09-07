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


def position(cmds, node):
    return tuple(
        float(value)
        for value in cmds.xform(
            node,
            query=True,
            worldSpace=True,
            translation=True,
        )
    )


def rotation(cmds, node):
    return tuple(float(value) for value in cmds.getAttr(f"{node}.rotate")[0])


def skeleton_matches(before, after):
    wanted = {joint.path: joint for joint in before.joints}
    current = {joint.path: joint for joint in after.joints}
    return (
        before.root == after.root
        and before.provenance == after.provenance
        and set(wanted) == set(current)
        and all(
            close(wanted[path].world_position, current[path].world_position, 1e-4)
            and all(
                close(a, b, 1e-4)
                for a, b in zip(
                    wanted[path].world_axes,
                    current[path].world_axes,
                )
            )
            for path in wanted
        )
    )


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyArmRig,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
        )
        from adv_py.core import BodyArmTwistSegment, FitBuildSide

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="ArmTwistDecompositionSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        cmds.select(marker, replace=True)
        result = BuildBodyArmRig(host).apply(
            container,
            twist_joints_per_segment=2,
        )

        lower_segment = next(
            spec
            for spec in result.plan.twist.segments
            if spec.side is FitBuildSide.RIGHT
            and spec.segment is BodyArmTwistSegment.LOWER
        )
        lower_helpers = tuple(
            spec
            for spec in result.plan.twist.joints
            if spec.side is FitBuildSide.RIGHT
            and spec.segment is BodyArmTwistSegment.LOWER
        )
        wrist_control = next(
            limb.wrist_control_path
            for limb in result.ik.limbs
            if limb.side is FitBuildSide.RIGHT
        )
        wrist_initial = position(cmds, wrist_control)

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr("|AdvPy_ArmSettings.armIkFk_R", 1.0)
        cmds.setAttr(f"{wrist_control}.rotateX", 72.0)
        axial_output = float(
            cmds.getAttr(f"{lower_segment.quaternion_name}.outputRotateX")
        )
        axial_rotations = tuple(rotation(cmds, spec.path) for spec in lower_helpers)

        cmds.setAttr(f"{wrist_control}.rotateX", 0.0)
        cmds.setAttr(f"{wrist_control}.rotateY", 55.0)
        swing_output = float(
            cmds.getAttr(f"{lower_segment.quaternion_name}.outputRotateX")
        )
        swing_rotations = tuple(rotation(cmds, spec.path) for spec in lower_helpers)

        cmds.setAttr(f"{wrist_control}.rotateY", 0.0)
        stretch = next(
            side
            for side in result.plan.stretch.sides
            if side.side is FitBuildSide.RIGHT
        )
        direction = tuple(
            b - a for a, b in zip(stretch.start_position, wrist_initial)
        )
        length = sqrt(sum(value * value for value in direction))
        unit = tuple(value / length for value in direction)
        far_target = tuple(
            a + axis * stretch.rest_length * 1.25
            for a, axis in zip(stretch.start_position, unit)
        )
        cmds.xform(wrist_control, worldSpace=True, translation=far_target)
        positions_follow = all(
            close(
                position(cmds, spec.path),
                tuple(
                    a + (b - a) * spec.fraction
                    for a, b in zip(
                        position(cmds, spec.start_joint),
                        position(cmds, spec.end_joint),
                    )
                ),
                2e-3,
            )
            for spec in result.plan.twist.joints
        )

        cmds.xform(wrist_control, worldSpace=True, translation=wrist_initial)
        cmds.setAttr("|AdvPy_ArmSettings.armIkFk_R", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)
        checks = {
            "quaternion_plugin_loaded": bool(
                cmds.pluginInfo("quatNodes", query=True, loaded=True)
            ),
            "four_segment_drivers": len(result.twist.segments) == 4,
            "eight_twist_helpers": len(result.twist.joints) == 8,
            "axial_projection_matches_input": abs(axial_output - 72.0) < 1e-3,
            "axial_twist_distributed": all(
                abs(values[0] - 72.0 * spec.fraction) < 1e-3
                and abs(values[1]) < 1e-4
                and abs(values[2]) < 1e-4
                for spec, values in zip(lower_helpers, axial_rotations)
            ),
            "pure_swing_has_zero_twist": abs(swing_output) < 1e-4,
            "pure_swing_does_not_rotate_helpers": all(
                close(values, (0.0, 0.0, 0.0), 1e-4)
                for values in swing_rotations
            ),
            "positions_follow_stretched_segments": positions_follow,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }
        cmds.undo()
        checks["single_undo_removed_complete_arm_rig"] = all(
            not cmds.objExists(path)
            for path in (
                "|AdvPy_ArmMechanisms",
                "|AdvPy_ArmFKControls",
                "|AdvPy_ArmIKControls",
                "|AdvPy_ArmSettings",
                "|AdvPy_ArmTwistJoints",
            )
        )
        checks["body_restored"] = skeleton_matches(
            body_before,
            host.capture_body_skeleton("Root_M"),
        )
        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_Arm*",
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_arm_axial_twist_decomposition",
            **checks,
            "axial_projection_degrees": round(axial_output, 6),
            "distributed_rotate_x_degrees": [
                round(values[0], 6) for values in axial_rotations
            ],
            "pure_swing_projection_degrees": round(swing_output, 6),
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
