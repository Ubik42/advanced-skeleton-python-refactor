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


def scale_yz(cmds, node):
    return (
        float(cmds.getAttr(f"{node}.scaleY")),
        float(cmds.getAttr(f"{node}.scaleZ")),
    )


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
                for a, b in zip(wanted[path].world_axes, current[path].world_axes)
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
        from adv_py.core import FitBuildSide, volume_preservation_scale

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="ArmVolumeSelection",
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

        right_volume = next(
            spec
            for spec in result.plan.volume.sides
            if spec.side is FitBuildSide.RIGHT
        )
        left_volume = next(
            spec
            for spec in result.plan.volume.sides
            if spec.side is FitBuildSide.LEFT
        )
        right_stretch = next(
            spec
            for spec in result.plan.stretch.sides
            if spec.side is FitBuildSide.RIGHT
        )
        wrist_control = right_stretch.wrist_control_path
        wrist_initial = position(cmds, wrist_control)
        direction = tuple(
            b - a
            for a, b in zip(right_stretch.start_position, wrist_initial)
        )
        length = sqrt(sum(value * value for value in direction))
        unit = tuple(value / length for value in direction)
        target_ratio = 1.44
        far_target = tuple(
            a + axis * right_stretch.rest_length * target_ratio
            for a, axis in zip(right_stretch.start_position, unit)
        )

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.xform(wrist_control, worldSpace=True, translation=far_target)
        fk_mode_scales = tuple(
            scale_yz(cmds, helper) for helper in right_volume.helper_joints
        )
        cmds.setAttr("|AdvPy_ArmSettings.armIkFk_R", 1.0)
        evaluated_ratio = float(
            cmds.getAttr(f"{right_stretch.blend_name}.outputR")
        )
        full_scales = tuple(
            scale_yz(cmds, helper) for helper in right_volume.helper_joints
        )
        left_scales = tuple(
            scale_yz(cmds, helper) for helper in left_volume.helper_joints
        )

        volume_plug = f"{result.plan.volume.settings_path}.{right_volume.attribute}"
        cmds.setAttr(volume_plug, 0.0)
        disabled_scales = tuple(
            scale_yz(cmds, helper) for helper in right_volume.helper_joints
        )
        cmds.setAttr(volume_plug, 0.5)
        half_scales = tuple(
            scale_yz(cmds, helper) for helper in right_volume.helper_joints
        )
        cmds.setAttr(volume_plug, 1.0)
        cmds.setAttr(f"{wrist_control}.rotateX", 72.0)
        twist_values = tuple(
            float(cmds.getAttr(f"{helper}.rotateX"))
            for helper in right_volume.helper_joints
        )

        expected_full = volume_preservation_scale(target_ratio, 1.0)
        expected_half = volume_preservation_scale(target_ratio, 0.5)
        checks = {
            "two_volume_sides": len(result.volume.sides) == 2,
            "hidden_ik_does_not_change_fk_volume": all(
                close(values, (1.0, 1.0), 1e-4) for values in fk_mode_scales
            ),
            "stretch_ratio_reached": abs(evaluated_ratio - target_ratio) < 2e-3,
            "inverse_sqrt_scale_applied": all(
                close(values, (expected_full, expected_full), 2e-3)
                for values in full_scales
            ),
            "volume_can_be_disabled": all(
                close(values, (1.0, 1.0), 1e-4)
                for values in disabled_scales
            ),
            "volume_strength_blends": all(
                close(values, (expected_half, expected_half), 2e-3)
                for values in half_scales
            ),
            "left_side_isolated": all(
                close(values, (1.0, 1.0), 1e-4) for values in left_scales
            ),
            "axial_twist_remains_driven": max(abs(value) for value in twist_values) > 20.0,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.setAttr(f"{wrist_control}.rotateX", 0.0)
        cmds.xform(wrist_control, worldSpace=True, translation=wrist_initial)
        cmds.setAttr("|AdvPy_ArmSettings.armIkFk_R", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)
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
            "slice": "body_arm_volume_preservation",
            **checks,
            "target_stretch_ratio": target_ratio,
            "evaluated_stretch_ratio": round(evaluated_ratio, 6),
            "full_volume_scale": round(expected_full, 6),
            "half_volume_scale": round(expected_half, 6),
            "right_helper_count": len(right_volume.helper_joints),
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
