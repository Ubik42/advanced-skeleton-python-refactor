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


def transformed_point(matrix_values, point):
    from maya.api import OpenMaya as om

    result = om.MPoint(*point) * om.MMatrix(matrix_values)
    return (float(result.x), float(result.y), float(result.z))


def target_point(start, end, rest_length, ratio):
    direction = tuple(value - origin for value, origin in zip(end, start))
    length = sqrt(sum(value * value for value in direction))
    unit = tuple(value / length for value in direction)
    return tuple(
        origin + axis * rest_length * ratio
        for origin, axis in zip(start, unit)
    )


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyCharacterRig,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            InspectBodyRebuildSafety,
        )
        from adv_py.application.body_rig_validation import body_bind_pose_matches
        from adv_py.core import FitBuildSide, knee_pin_factors

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="CharacterGlobalSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        pre_body = BuildOrientedBodySkeleton(host).apply(container).snapshot
        cmds.select(marker, replace=True)
        rig = BuildBodyCharacterRig(host).apply(container)

        global_plan = rig.plan.global_control
        control = global_plan.control_path
        arm_stretch = next(
            spec
            for spec in rig.arm.plan.stretch.sides
            if spec.side is FitBuildSide.RIGHT
        )
        leg_stretch = next(
            spec
            for spec in rig.leg.plan.stretch.sides
            if spec.side is FitBuildSide.RIGHT
        )
        leg_pin = next(
            spec
            for spec in rig.leg.plan.knee_pin.sides
            if spec.side is FitBuildSide.RIGHT
        )
        arm_blend = f"{rig.arm.plan.blend.settings_path}.armIkFk_R"
        leg_blend = f"{rig.leg.plan.blend.settings_path}.legIkFk_R"
        leg_pin_plug = (
            f"{rig.leg.plan.knee_pin.settings_path}.{leg_pin.attribute}"
        )
        arm_scale_plug, leg_scale_plug = global_plan.scale_destinations
        initial_positions = {
            joint.name: joint.world_position
            for joint in pre_body.joints
            if joint.name in {
                "Root_M",
                "Wrist_R",
                "Ankle_R",
                "Toes_R",
            }
        }
        arm_control_initial = position(cmds, arm_stretch.target_control_path)
        leg_control_initial = position(cmds, leg_stretch.target_control_path)

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{control}.translateX", 3.0)
        cmds.setAttr(f"{control}.translateY", -2.0)
        cmds.setAttr(f"{control}.translateZ", 5.0)
        cmds.setAttr(f"{control}.rotateZ", 25.0)
        cmds.setAttr(global_plan.scale_source, 1.5)
        global_matrix = cmds.xform(
            control,
            query=True,
            worldSpace=True,
            matrix=True,
        )
        transformed_body = host.capture_body_skeleton("Root_M")
        transformed_by_name = {
            joint.name: joint.world_position for joint in transformed_body.joints
        }
        body_follows_global = all(
            close(
                transformed_by_name[name],
                transformed_point(global_matrix, point),
            )
            for name, point in initial_positions.items()
        )
        driven_roots_follow = all(
            close(
                tuple(
                    float(cmds.getAttr(f"{path}.translate{axis}"))
                    for axis in "XYZ"
                ),
                (3.0, -2.0, 5.0),
            )
            and close(
                tuple(
                    float(cmds.getAttr(f"{path}.rotate{axis}"))
                    for axis in "XYZ"
                ),
                (0.0, 0.0, 25.0),
            )
            and close(
                tuple(
                    float(cmds.getAttr(f"{path}.scale{axis}"))
                    for axis in "XYZ"
                ),
                (1.5, 1.5, 1.5),
            )
            for path in global_plan.driven_roots
        )

        target_ratio = 1.25
        arm_local_target = target_point(
            arm_stretch.start_position,
            arm_control_initial,
            arm_stretch.rest_length,
            target_ratio,
        )
        leg_local_target = target_point(
            leg_stretch.start_position,
            leg_control_initial,
            leg_stretch.rest_length,
            target_ratio,
        )
        arm_world_target = transformed_point(global_matrix, arm_local_target)
        leg_world_target = transformed_point(global_matrix, leg_local_target)
        cmds.setAttr(arm_blend, 1.0)
        cmds.setAttr(leg_blend, 1.0)
        cmds.xform(
            arm_stretch.ankle_control_path,
            worldSpace=True,
            translation=arm_world_target,
        )
        cmds.xform(
            leg_stretch.ankle_control_path,
            worldSpace=True,
            translation=leg_world_target,
        )
        arm_segments = segment_values(cmds, arm_stretch)
        leg_segments = segment_values(cmds, leg_stretch)
        expected_arm_segments = tuple(
            value * target_ratio for value in arm_stretch.base_translations
        )
        expected_leg_segments = tuple(
            value * target_ratio for value in leg_stretch.base_translations
        )

        pole_world = position(cmds, leg_pin.pole_matrix_source.split(".", 1)[0])
        leg_start_world = position(
            cmds,
            leg_pin.start_matrix_source.split(".", 1)[0],
        )
        world_distances = (
            distance(leg_start_world, pole_world),
            distance(pole_world, leg_world_target),
        )
        cmds.setAttr(leg_pin_plug, 1.0)
        expected_pin_factors, _ = knee_pin_factors(
            leg_stretch.base_translations,
            (target_ratio, target_ratio),
            world_distances,
            1.5,
            1.0,
            minimum_length=leg_pin.minimum_length,
        )
        expected_pin_segments = tuple(
            base * factor
            for base, factor in zip(
                leg_stretch.base_translations,
                expected_pin_factors,
            )
        )
        pin_segments = segment_values(cmds, leg_stretch)
        pinned_knee = position(cmds, leg_stretch.segment_joints[0])
        pinned_ankle = position(cmds, leg_stretch.segment_joints[1])

        checks = {
            "arm_and_leg_built_together": (
                len(rig.arm.mechanisms.joints) == 12
                and len(rig.leg.mechanisms.joints) == 20
            ),
            "global_hierarchy_and_shape": (
                rig.global_control.control_shape_type == "nurbsCurve"
                and rig.global_control.root_parent_path is None
                and rig.global_control.control_parent_path
                == global_plan.offset_path
            ),
            "nine_owned_roots_are_driven": (
                len(rig.global_control.driven_roots) == 9
                and driven_roots_follow
            ),
            "body_follows_global_trs": body_follows_global,
            "arm_and_leg_scale_compensation_are_wired": (
                abs(float(cmds.getAttr(arm_scale_plug)) - 1.5) < 1e-4
                and abs(float(cmds.getAttr(leg_scale_plug)) - 1.5) < 1e-4
            ),
            "arm_stretch_is_scale_invariant": close(
                arm_segments,
                expected_arm_segments,
            ),
            "leg_stretch_is_scale_invariant": close(
                leg_segments,
                expected_leg_segments,
            ),
            "arm_wrist_reaches_scaled_target": close(
                position(cmds, arm_stretch.segment_joints[1]),
                arm_world_target,
            ),
            "leg_ankle_reaches_scaled_target": close(
                position(cmds, leg_stretch.segment_joints[1]),
                leg_world_target,
            ),
            "leg_pin_divides_world_distance_by_global_scale": close(
                pin_segments,
                expected_pin_segments,
            ),
            "leg_pin_reaches_scaled_pole_and_ankle": (
                close(pinned_knee, pole_world)
                and close(pinned_ankle, leg_world_target)
            ),
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.undoInfo(stateWithoutFlush=True)
        cmds.undo()
        remaining_rig = (
            (cmds.ls("AdvPy_Arm*", long=True) or [])
            + (cmds.ls("AdvPy_Leg*", long=True) or [])
            + (cmds.ls("AdvPy_Foot*", long=True) or [])
            + (cmds.ls("AdvPy_Character*", long=True) or [])
            + (cmds.ls("AdvPy_Global*", long=True) or [])
        )
        restored_body = host.capture_body_skeleton("Root_M")
        checks["single_undo_removed_complete_character_rig"] = not remaining_rig
        checks["single_undo_restored_body_bind_pose"] = body_bind_pose_matches(
            pre_body,
            restored_body,
        )
        checks["single_undo_restored_rebuild_safety"] = (
            InspectBodyRebuildSafety(host).execute(container).safe_to_replace
        )

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_Arm*",
            "AdvPy_Leg*",
            "AdvPy_Foot*",
            "AdvPy_Character*",
            "AdvPy_Global*",
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_character_global_control",
            **checks,
            "driven_root_count": len(global_plan.driven_roots),
            "global_translate": [3.0, -2.0, 5.0],
            "global_rotate_z": 25.0,
            "global_scale": 1.5,
            "target_stretch_ratio": target_ratio,
            "arm_segments": arm_segments,
            "leg_segments": leg_segments,
            "leg_pin_segments": pin_segments,
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
