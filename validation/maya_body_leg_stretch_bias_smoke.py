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


def close(left, right, tolerance=2e-3):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def position(cmds, path):
    return tuple(float(value) for value in cmds.xform(
        path,
        query=True,
        worldSpace=True,
        translation=True,
    ))


def target(spec, unit, ratio):
    return tuple(
        start + axis * spec.rest_length * ratio
        for start, axis in zip(spec.start_position, unit)
    )


def segment_values(cmds, spec):
    return tuple(
        float(cmds.getAttr(f"{joint}.translate{channel}"))
        for joint, channel in zip(spec.segment_joints, spec.segment_channels)
    )


def pose_matches(before, after, names):
    wanted = {joint.name: joint for joint in before.joints if joint.name in names}
    current = {joint.name: joint for joint in after.joints if joint.name in names}
    return set(wanted) == set(current) and all(
        close(wanted[name].world_position, current[name].world_position)
        and all(
            close(actual, expected)
            for actual, expected in zip(
                wanted[name].world_axes,
                current[name].world_axes,
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
        from adv_py.core import FitBuildSide, biased_stretch_factors

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="LegStretchBiasSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        BuildOrientedBodySkeleton(host).apply(container)
        cmds.select(marker, replace=True)
        rig = BuildBodyLegRig(host).apply(container)

        stretch = next(
            spec
            for spec in rig.plan.stretch.sides
            if spec.side is FitBuildSide.RIGHT
        )
        left_stretch = next(
            spec
            for spec in rig.plan.stretch.sides
            if spec.side is FitBuildSide.LEFT
        )
        bias = next(
            spec
            for spec in rig.plan.stretch_bias.sides
            if spec.side is FitBuildSide.RIGHT
        )
        right_volume = next(
            spec
            for spec in rig.plan.volume.sides
            if spec.side is FitBuildSide.RIGHT
        )
        ankle_control = stretch.ankle_control_path
        ankle_initial = position(cmds, ankle_control)
        direction = tuple(
            value - start
            for value, start in zip(ankle_initial, stretch.start_position)
        )
        length = sqrt(sum(value * value for value in direction))
        unit = tuple(value / length for value in direction)
        target_ratio = 1.4
        bias_plug = f"{rig.plan.stretch_bias.settings_path}.{bias.attribute}"
        blend_plug = f"{rig.plan.blend.settings_path}.legIkFk_R"

        def expected_segments(share):
            factors = biased_stretch_factors(
                stretch.base_translations,
                target_ratio,
                share,
            )
            return tuple(
                base * factor
                for base, factor in zip(stretch.base_translations, factors)
            )

        def volume_scales():
            return tuple(
                tuple(
                    float(cmds.getAttr(f"{helper}.scale{axis}"))
                    for axis in axes
                )
                for helper, axes in zip(
                    right_volume.helper_joints,
                    right_volume.helper_scale_axes,
                )
            )

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(blend_plug, 1.0)
        cmds.xform(
            ankle_control,
            worldSpace=True,
            translation=target(stretch, unit, target_ratio),
        )

        default_value = float(cmds.getAttr(bias_plug))
        default_segments = segment_values(cmds, stretch)
        default_is_uniform = close(
            default_segments,
            tuple(value * target_ratio for value in stretch.base_translations),
        )

        volume_before_bias = volume_scales()
        cmds.setAttr(bias_plug, 1.0)
        upper_only_segments = segment_values(cmds, stretch)
        upper_only_reaches = close(
            position(cmds, stretch.segment_joints[1]),
            position(cmds, ankle_control),
        )

        cmds.setAttr(bias_plug, 0.0)
        lower_only_segments = segment_values(cmds, stretch)
        lower_only_reaches = close(
            position(cmds, stretch.segment_joints[1]),
            position(cmds, ankle_control),
        )

        final_share = 0.75
        cmds.setAttr(bias_plug, final_share)
        final_segments = segment_values(cmds, stretch)
        volume_after_bias = volume_scales()
        left_unchanged = close(
            segment_values(cmds, left_stretch),
            left_stretch.base_translations,
        )
        helpers_follow = all(
            close(
                position(cmds, helper.path),
                tuple(
                    start + (end - start) * helper.fraction
                    for start, end in zip(
                        position(cmds, helper.start_joint),
                        position(cmds, helper.end_joint),
                    )
                ),
            )
            for helper in rig.plan.twist.joints
        )
        biased_pose = host.capture_body_skeleton("Root_M")
        expected_fk_segments = final_segments
        cmds.undoInfo(stateWithoutFlush=True)

        match = MatchBodyLegIkToFk(host).apply(
            FitBuildSide.RIGHT,
            container,
        )
        matched_fk_segments = tuple(
            float(cmds.getAttr(plug))
            for plug in match.plan.match.fk_segment_plugs
        )
        matched_pose = pose_matches(
            biased_pose,
            match.body,
            {"Hip_R", "Knee_R", "Ankle_R", "Toes_R"},
        )

        checks = {
            "two_bias_sides": len(rig.stretch_bias.sides) == 2,
            "default_share_matches_rest_lengths": (
                abs(default_value - bias.default_value) < 1e-5
            ),
            "default_preserves_uniform_stretch": default_is_uniform,
            "upper_only_distribution": close(
                upper_only_segments,
                expected_segments(1.0),
            ),
            "lower_only_distribution": close(
                lower_only_segments,
                expected_segments(0.0),
            ),
            "partial_distribution": close(
                final_segments,
                expected_segments(final_share),
            ),
            "upper_only_still_reaches_target": upper_only_reaches,
            "lower_only_still_reaches_target": lower_only_reaches,
            "total_length_is_preserved": all(
                abs(
                    sum(abs(value) for value in values)
                    - stretch.rest_length * target_ratio
                ) < 2e-3
                for values in (
                    upper_only_segments,
                    lower_only_segments,
                    final_segments,
                )
            ),
            "volume_uses_total_ratio_only": all(
                close(before, after, 1e-4)
                for before, after in zip(
                    volume_before_bias,
                    volume_after_bias,
                )
            ),
            "left_side_isolated": left_unchanged,
            "twist_helpers_follow_redistributed_segments": helpers_follow,
            "biased_ik_to_fk_preserves_pose": matched_pose,
            "biased_ik_to_fk_transfers_lengths": close(
                matched_fk_segments,
                expected_fk_segments,
            ),
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.undo()
        after_match_undo = host.capture_body_skeleton("Root_M")
        checks["first_undo_restored_ik_mode"] = (
            abs(float(cmds.getAttr(blend_plug)) - 1.0) < 1e-4
        )
        checks["first_undo_restored_biased_pose"] = pose_matches(
            biased_pose,
            after_match_undo,
            {"Hip_R", "Knee_R", "Ankle_R", "Toes_R"},
        )
        cmds.undo()
        remaining_rig = (
            (cmds.ls("AdvPy_Leg*", long=True) or [])
            + (cmds.ls("AdvPy_Foot*", long=True) or [])
        )
        checks["second_undo_removed_complete_leg_rig"] = not remaining_rig

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
            "slice": "body_leg_stretch_bias_distribution",
            **checks,
            "target_stretch_ratio": target_ratio,
            "default_upper_extra_share": round(default_value, 6),
            "final_upper_extra_share": final_share,
            "base_translations": stretch.base_translations,
            "upper_only_segments": upper_only_segments,
            "lower_only_segments": lower_only_segments,
            "partial_segments": final_segments,
            "remaining_rig_nodes_after_undo": remaining_rig,
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
