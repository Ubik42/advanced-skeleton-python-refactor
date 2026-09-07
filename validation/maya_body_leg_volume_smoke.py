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
    return tuple(float(value) for value in cmds.xform(
        node,
        query=True,
        worldSpace=True,
        translation=True,
    ))


def scale_channels(cmds, node, axes):
    return tuple(
        float(cmds.getAttr(f"{node}.scale{axis}"))
        for axis in axes
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
            BuildBodyLegRig,
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
            name="LegVolumeSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        cmds.select(marker, replace=True)
        result = BuildBodyLegRig(host).apply(
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
        ankle_control = right_stretch.ankle_control_path
        ankle_initial = position(cmds, ankle_control)
        direction = tuple(
            value - start
            for value, start in zip(ankle_initial, right_stretch.start_position)
        )
        length = sqrt(sum(value * value for value in direction))
        unit = tuple(value / length for value in direction)
        target_ratio = 1.44
        far_target = tuple(
            start + axis * right_stretch.rest_length * target_ratio
            for start, axis in zip(right_stretch.start_position, unit)
        )

        def volume_scales(spec):
            return tuple(
                scale_channels(cmds, helper, axes)
                for helper, axes in zip(
                    spec.helper_joints,
                    spec.helper_scale_axes,
                )
            )

        def axial_scales(spec):
            return tuple(
                scale_channels(
                    cmds,
                    helper,
                    tuple(axis for axis in "XYZ" if axis not in axes),
                )[0]
                for helper, axes in zip(
                    spec.helper_joints,
                    spec.helper_scale_axes,
                )
            )

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.xform(ankle_control, worldSpace=True, translation=far_target)
        fk_mode_scales = volume_scales(right_volume)
        cmds.setAttr("|AdvPy_LegSettings.legIkFk_R", 1.0)
        evaluated_ratio = float(cmds.getAttr(
            f"{right_stretch.blend_name}.outputR"
        ))
        full_scales = volume_scales(right_volume)
        full_axial_scales = axial_scales(right_volume)
        left_scales = volume_scales(left_volume)

        volume_plug = (
            f"{result.plan.volume.settings_path}.{right_volume.attribute}"
        )
        cmds.setAttr(volume_plug, 0.0)
        disabled_scales = volume_scales(right_volume)
        cmds.setAttr(volume_plug, 0.5)
        half_scales = volume_scales(right_volume)
        cmds.setAttr(volume_plug, 1.0)

        before_roll_scales = volume_scales(right_volume)
        cmds.setAttr(f"{ankle_control}.footRoll", 70.0)
        after_roll_scales = volume_scales(right_volume)
        cmds.setAttr(f"{ankle_control}.footRoll", 0.0)

        expected_full = volume_preservation_scale(target_ratio, 1.0)
        expected_half = volume_preservation_scale(target_ratio, 0.5)
        checks = {
            "two_volume_sides": len(result.volume.sides) == 2,
            "four_helpers_per_side": all(
                len(spec.helper_joints) == 4
                and len(spec.helper_scale_axes) == 4
                for spec in result.plan.volume.sides
            ),
            "orthogonal_axes_are_explicit": all(
                len(axes) == 2
                and len(set(axes)) == 2
                and all(axis in "XYZ" for axis in axes)
                for spec in result.plan.volume.sides
                for axes in spec.helper_scale_axes
            ),
            "hidden_ik_does_not_change_fk_volume": all(
                close(values, (1.0, 1.0), 1e-4)
                for values in fk_mode_scales
            ),
            "stretch_ratio_reached": abs(evaluated_ratio - target_ratio) < 2e-3,
            "inverse_sqrt_scale_applied": all(
                close(values, (expected_full, expected_full), 2e-3)
                for values in full_scales
            ),
            "axial_scale_is_untouched": all(
                abs(value - 1.0) < 1e-4 for value in full_axial_scales
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
                close(values, (1.0, 1.0), 1e-4)
                for values in left_scales
            ),
            "foot_roll_does_not_change_volume": all(
                close(before, after, 1e-4)
                for before, after in zip(before_roll_scales, after_roll_scales)
            ),
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.xform(ankle_control, worldSpace=True, translation=ankle_initial)
        cmds.setAttr("|AdvPy_LegSettings.legIkFk_R", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)
        cmds.undo()
        checks["single_undo_removed_complete_leg_rig"] = all(
            not cmds.objExists(path)
            for path in (
                "|AdvPy_LegMechanisms",
                "|AdvPy_LegFKControls",
                "|AdvPy_LegIKControls",
                "|AdvPy_LegSettings",
                "|AdvPy_LegTwistJoints",
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
            "AdvPy_Leg*",
            "AdvPy_Foot*",
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_leg_principal_axis_volume_preservation",
            **checks,
            "target_stretch_ratio": target_ratio,
            "evaluated_stretch_ratio": round(evaluated_ratio, 6),
            "full_volume_scale": round(expected_full, 6),
            "half_volume_scale": round(expected_half, 6),
            "right_helper_scale_axes": right_volume.helper_scale_axes,
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
