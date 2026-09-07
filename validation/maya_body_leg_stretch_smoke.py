from __future__ import annotations

import json
from math import sqrt
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def close(left, right, tolerance=2e-3):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def position(cmds, path):
    return tuple(float(value) for value in cmds.xform(
        path, query=True, worldSpace=True, translation=True
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
            "transform", name="PortableLegStretchSelection", skipSelect=True
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
        rig = use_case.apply(container)

        spec = next(
            side for side in rig.plan.stretch.sides
            if side.side is FitBuildSide.RIGHT
        )
        left = next(
            side for side in rig.plan.stretch.sides
            if side.side is FitBuildSide.LEFT
        )
        direction = tuple(
            value - start
            for value, start in zip(
                position(cmds, spec.target_control_path), spec.start_position
            )
        )
        direction_length = sqrt(sum(value * value for value in direction))
        unit = tuple(value / direction_length for value in direction)
        strength_plug = f"{rig.plan.stretch.settings_path}.{spec.attribute}"
        left_strength_plug = (
            f"{rig.plan.stretch.settings_path}.{left.attribute}"
        )
        scale_plug = (
            f"{rig.plan.stretch.settings_path}."
            f"{rig.plan.stretch.global_scale_attribute}"
        )
        blend_plug = f"{rig.plan.blend.settings_path}.legIkFk_R"
        foot_plug = f"{spec.target_control_path}.footRoll"
        handle_path = (cmds.ls(
            next(
                limb.handle_name for limb in rig.plan.ik.limbs
                if limb.side is FitBuildSide.RIGHT
            ),
            long=True,
        ) or [None])[0]
        axis_wiring = all(
            (cmds.listConnections(
                f"{joint}.translate{channel}",
                source=True,
                destination=False,
                plugs=True,
            ) or []) == [f"{spec.segment_name}.output{output}"]
            for joint, channel, output in zip(
                spec.segment_joints, spec.segment_channels, "XY"
            )
        )

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(blend_plug, 1.0)

        cmds.xform(
            spec.target_control_path,
            worldSpace=True,
            translation=target(spec, unit, 0.65),
        )
        short_values = segment_values(cmds, spec)
        no_compression = close(short_values, spec.base_translations)

        cmds.xform(
            spec.target_control_path,
            worldSpace=True,
            translation=target(spec, unit, 1.35),
        )
        full_values = segment_values(cmds, spec)
        full_stretch = close(
            full_values,
            tuple(value * 1.35 for value in spec.base_translations),
        )
        reaches_target = close(
            position(cmds, spec.segment_joints[1]),
            position(cmds, spec.target_control_path),
        )

        cmds.setAttr(strength_plug, 0.0)
        disabled_values = segment_values(cmds, spec)
        disabled = close(disabled_values, spec.base_translations)
        cmds.setAttr(strength_plug, 0.5)
        half_values = segment_values(cmds, spec)
        half_stretch = close(
            half_values,
            tuple(value * 1.175 for value in spec.base_translations),
        )
        left_unchanged = (
            cmds.getAttr(left_strength_plug) == 1.0
            and close(segment_values(cmds, left), left.base_translations)
        )

        cmds.setAttr(strength_plug, 1.0)
        cmds.xform(
            spec.target_control_path,
            worldSpace=True,
            translation=target(spec, unit, 1.25),
        )
        before_foot_values = segment_values(cmds, spec)
        before_foot_handle = position(cmds, handle_path)
        cmds.setAttr(foot_plug, 70.0)
        foot_decoupled = close(
            segment_values(cmds, spec), before_foot_values
        )
        foot_still_moves_handle = not close(
            position(cmds, handle_path), before_foot_handle
        )
        cmds.setAttr(foot_plug, 0.0)

        cmds.setAttr(scale_plug, 2.0)
        cmds.xform(
            spec.target_control_path,
            worldSpace=True,
            translation=target(spec, unit, 2.0),
        )
        scaled_rest_values = segment_values(cmds, spec)
        global_scale_compensated = close(
            scaled_rest_values, spec.base_translations
        )
        cmds.xform(
            spec.target_control_path,
            worldSpace=True,
            translation=target(spec, unit, 2.5),
        )
        scaled_stretch_values = segment_values(cmds, spec)
        scaled_stretch = close(
            scaled_stretch_values,
            tuple(value * 1.25 for value in spec.base_translations),
        )

        cmds.setAttr(scale_plug, 1.0)
        cmds.xform(
            spec.target_control_path,
            worldSpace=True,
            translation=target(spec, unit, 1.25),
        )
        stretched_pose = host.capture_body_skeleton("Root_M")
        expected_fk_segments = segment_values(cmds, spec)
        cmds.undoInfo(stateWithoutFlush=True)

        cmds.file(modified=False)
        match_use_case = MatchBodyLegIkToFk(host)
        match_preview = match_use_case.plan(FitBuildSide.RIGHT, container)
        match_preview_clean = not bool(cmds.file(query=True, modified=True))
        match = match_use_case.apply(FitBuildSide.RIGHT, container)
        matched_fk_segments = tuple(
            float(cmds.getAttr(plug))
            for plug in match.plan.match.fk_segment_plugs
        )
        matched_pose = pose_matches(
            stretched_pose,
            match.body,
            {"Hip_R", "Knee_R", "Ankle_R", "Toes_R"},
        )

        checks = {
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "stretch_side_count": len(rig.stretch.sides) == 2,
            "leg_uses_explicit_local_axes": axis_wiring,
            "default_strength_one": (
                rig.stretch.sides[0].attribute_value == 1.0
                and rig.stretch.sides[1].attribute_value == 1.0
            ),
            "short_target_does_not_compress": no_compression,
            "full_stretch_ratio": full_stretch,
            "stretched_ankle_reaches_target": reaches_target,
            "strength_zero_disables_stretch": disabled,
            "strength_half_blends_ratio": half_stretch,
            "left_side_unchanged": left_unchanged,
            "foot_roll_does_not_change_leg_length": foot_decoupled,
            "foot_roll_still_moves_handle": foot_still_moves_handle,
            "global_scale_avoids_false_stretch": global_scale_compensated,
            "scaled_character_can_still_stretch": scaled_stretch,
            "match_preview_ready": match_preview.ready,
            "match_preview_did_not_modify_scene": match_preview_clean,
            "stretched_ik_to_fk_preserves_pose": matched_pose,
            "stretched_ik_to_fk_transfers_lengths": close(
                matched_fk_segments, expected_fk_segments
            ),
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.undo()
        after_match_undo = host.capture_body_skeleton("Root_M")
        checks["single_undo_restored_ik_mode"] = (
            cmds.getAttr(blend_plug) == 1.0
        )
        checks["single_undo_restored_stretched_pose"] = pose_matches(
            stretched_pose,
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
            "Root_M", "FitSkeleton", "AdvPy_Leg*", "AdvPy_Foot*", marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_leg_stretch_and_stretched_match",
            **checks,
            "rest_length": round(spec.rest_length, 6),
            "base_translations": spec.base_translations,
            "segment_channels": spec.segment_channels,
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
