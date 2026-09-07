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


def distance(left, right):
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


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
        from adv_py.core import (
            FitBuildSide,
            biased_stretch_factors,
            knee_pin_factors,
            volume_preservation_scale,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="LegKneePinSelection",
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
        pin = next(
            spec
            for spec in rig.plan.knee_pin.sides
            if spec.side is FitBuildSide.RIGHT
        )
        ik = next(
            spec
            for spec in rig.plan.ik.limbs
            if spec.side is FitBuildSide.RIGHT
        )
        volume = next(
            spec
            for spec in rig.plan.volume.sides
            if spec.side is FitBuildSide.RIGHT
        )
        blend_plug = f"{rig.plan.blend.settings_path}.legIkFk_R"
        bias_plug = f"{rig.plan.stretch_bias.settings_path}.{bias.attribute}"
        pin_plug = f"{rig.plan.knee_pin.settings_path}.{pin.attribute}"
        scale_plug = (
            f"{rig.plan.stretch.settings_path}."
            f"{rig.plan.stretch.global_scale_attribute}"
        )

        start = position(cmds, stretch.start_path)
        ankle_initial = position(cmds, stretch.ankle_control_path)
        direction = tuple(value - origin for value, origin in zip(ankle_initial, start))
        initial_length = sqrt(sum(value * value for value in direction))
        unit = tuple(value / initial_length for value in direction)
        target_ratio = 1.25
        ankle_target = tuple(
            origin + axis * stretch.rest_length * target_ratio
            for origin, axis in zip(start, unit)
        )
        pole_target = position(cmds, ik.pole_control_path)
        world_distances = (
            distance(start, pole_target),
            distance(pole_target, ankle_target),
        )
        bias_value = 0.75
        normal_factors = biased_stretch_factors(
            stretch.base_translations,
            target_ratio,
            bias_value,
        )
        expected_normal_segments = tuple(
            base * factor
            for base, factor in zip(stretch.base_translations, normal_factors)
        )

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(blend_plug, 1.0)
        cmds.setAttr(bias_plug, bias_value)
        cmds.xform(
            stretch.ankle_control_path,
            worldSpace=True,
            translation=ankle_target,
        )
        left_before = segment_values(cmds, left_stretch)

        default_pin = float(cmds.getAttr(pin_plug))
        normal_segments = segment_values(cmds, stretch)
        normal_knee = position(cmds, stretch.segment_joints[0])

        cmds.setAttr(pin_plug, 1.0)
        full_factors, full_ratio = knee_pin_factors(
            stretch.base_translations,
            normal_factors,
            world_distances,
            float(cmds.getAttr(scale_plug)),
            1.0,
            minimum_length=pin.minimum_length,
        )
        expected_full_segments = tuple(
            base * factor
            for base, factor in zip(stretch.base_translations, full_factors)
        )
        full_segments = segment_values(cmds, stretch)
        full_knee = position(cmds, stretch.segment_joints[0])
        full_ankle = position(cmds, stretch.segment_joints[1])
        graph_full_ratio = float(cmds.getAttr(pin.total_ratio_source))

        partial_weight = 0.5
        cmds.setAttr(pin_plug, partial_weight)
        partial_factors, partial_ratio = knee_pin_factors(
            stretch.base_translations,
            normal_factors,
            world_distances,
            float(cmds.getAttr(scale_plug)),
            partial_weight,
            minimum_length=pin.minimum_length,
        )
        expected_partial_segments = tuple(
            base * factor
            for base, factor in zip(stretch.base_translations, partial_factors)
        )
        partial_segments = segment_values(cmds, stretch)
        partial_graph_ratio = float(cmds.getAttr(pin.total_ratio_source))
        expected_volume = volume_preservation_scale(partial_ratio)
        volume_matches_total = all(
            abs(float(cmds.getAttr(f"{helper}.scale{axis}")) - expected_volume)
            < 2e-3
            for helper, axes in zip(
                volume.helper_joints,
                volume.helper_scale_axes,
            )
            for axis in axes
        )

        cmds.setAttr(pin_plug, 0.0)
        restored_normal_segments = segment_values(cmds, stretch)
        cmds.setAttr(pin_plug, 1.0)
        helpers_follow = all(
            close(
                position(cmds, helper.path),
                tuple(
                    origin + (end - origin) * helper.fraction
                    for origin, end in zip(
                        position(cmds, helper.start_joint),
                        position(cmds, helper.end_joint),
                    )
                ),
            )
            for helper in rig.plan.twist.joints
        )
        left_after = segment_values(cmds, left_stretch)
        pinned_pose = host.capture_body_skeleton("Root_M")
        cmds.undoInfo(stateWithoutFlush=True)

        match = MatchBodyLegIkToFk(host).apply(
            FitBuildSide.RIGHT,
            container,
        )
        matched_segments = tuple(
            float(cmds.getAttr(plug))
            for plug in match.plan.match.fk_segment_plugs
        )
        matched_pose = pose_matches(
            pinned_pose,
            match.body,
            {"Hip_R", "Knee_R", "Ankle_R", "Toes_R"},
        )

        checks = {
            "two_knee_pin_sides": len(rig.knee_pin.sides) == 2,
            "default_pin_is_zero": abs(default_pin) < 1e-6,
            "zero_pin_preserves_stretch_bias": (
                close(normal_segments, expected_normal_segments)
                and close(restored_normal_segments, expected_normal_segments)
            ),
            "zero_pin_does_not_force_pole_position": (
                distance(normal_knee, pole_target) > 0.1
            ),
            "full_pin_uses_two_control_distances": close(
                full_segments,
                expected_full_segments,
            ),
            "full_pin_places_knee_at_pole": close(full_knee, pole_target),
            "full_pin_keeps_ankle_on_target": close(full_ankle, ankle_target),
            "full_total_ratio_matches_graph": (
                abs(graph_full_ratio - full_ratio) < 2e-3
            ),
            "partial_pin_is_continuous": close(
                partial_segments,
                expected_partial_segments,
            ),
            "partial_total_ratio_matches_graph": (
                abs(partial_graph_ratio - partial_ratio) < 2e-3
            ),
            "volume_uses_final_pin_total_ratio": (
                volume.stretch_ratio_source == pin.total_ratio_source
                and volume_matches_total
            ),
            "left_side_isolated": close(left_before, left_after),
            "twist_helpers_follow_pinned_segments": helpers_follow,
            "pinned_ik_to_fk_preserves_pose": matched_pose,
            "pinned_ik_to_fk_transfers_lengths": close(
                matched_segments,
                expected_full_segments,
            ),
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.undo()
        after_match_undo = host.capture_body_skeleton("Root_M")
        checks["first_undo_restored_ik_mode"] = (
            abs(float(cmds.getAttr(blend_plug)) - 1.0) < 1e-4
        )
        checks["first_undo_restored_pinned_pose"] = pose_matches(
            pinned_pose,
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
            "slice": "body_leg_knee_pin",
            **checks,
            "target_stretch_ratio": target_ratio,
            "bias_value": bias_value,
            "partial_pin_weight": partial_weight,
            "world_distances": world_distances,
            "normal_segments": normal_segments,
            "full_pin_segments": full_segments,
            "partial_pin_segments": partial_segments,
            "full_total_ratio": graph_full_ratio,
            "partial_total_ratio": partial_graph_ratio,
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
