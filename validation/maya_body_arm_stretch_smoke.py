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


def near(value, expected, tolerance=1e-3):
    return abs(value - expected) <= tolerance


def close(left, right, tolerance=1e-3):
    return all(near(a, b, tolerance) for a, b in zip(left, right))


def position(cmds, node):
    return tuple(float(value) for value in cmds.xform(node, query=True, worldSpace=True, translation=True))


def skeleton_matches(before, after):
    wanted = {joint.path: joint for joint in before.joints}
    current = {joint.path: joint for joint in after.joints}
    return before.root == after.root and before.provenance == after.provenance and set(wanted) == set(current) and all(
        close(wanted[path].world_position, current[path].world_position, 1e-4)
        and all(close(a, b, 1e-4) for a, b in zip(wanted[path].world_axes, current[path].world_axes))
        for path in wanted
    )


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import BuildBodyArmRig, BuildOrientedBodySkeleton, BuildSyntheticBodySourceFit, CreateFitSkeleton
        from adv_py.core import FitBuildSide

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode("transform", name="PortableArmStretchSelection", skipSelect=True)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        cmds.select(marker, replace=True)
        result = BuildBodyArmRig(host).apply(container)
        spec = next(side for side in result.plan.stretch.sides if side.side is FitBuildSide.RIGHT)
        left = next(side for side in result.plan.stretch.sides if side.side is FitBuildSide.LEFT)
        attribute = f"{result.plan.stretch.settings_path}.{spec.attribute}"
        blend_attribute = "|AdvPy_ArmSettings.armIkFk_R"
        wrist_initial = position(cmds, spec.wrist_control_path)
        direction = tuple(b - a for a, b in zip(spec.start_position, wrist_initial))
        length = sqrt(sum(value * value for value in direction))
        unit = tuple(value / length for value in direction)
        target = lambda factor: tuple(a + axis * spec.rest_length * factor for a, axis in zip(spec.start_position, unit))

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(blend_attribute, 1.0)
        cmds.xform(spec.wrist_control_path, worldSpace=True, translation=target(0.6))
        compressed_values = tuple(cmds.getAttr(f"{joint}.translateX") for joint in spec.segment_joints)
        no_compression = all(near(value, base) for value, base in zip(compressed_values, spec.base_translations))

        cmds.xform(spec.wrist_control_path, worldSpace=True, translation=target(1.35))
        full_values = tuple(cmds.getAttr(f"{joint}.translateX") for joint in spec.segment_joints)
        full_stretch = all(near(value, base * 1.35) for value, base in zip(full_values, spec.base_translations))
        reaches_target = close(position(cmds, spec.segment_joints[1]), position(cmds, spec.wrist_control_path), 2e-3)

        cmds.setAttr(attribute, 0.0)
        disabled_values = tuple(cmds.getAttr(f"{joint}.translateX") for joint in spec.segment_joints)
        disabled = all(near(value, base) for value, base in zip(disabled_values, spec.base_translations))
        cmds.setAttr(attribute, 0.5)
        half_values = tuple(cmds.getAttr(f"{joint}.translateX") for joint in spec.segment_joints)
        half_stretch = all(near(value, base * 1.175) for value, base in zip(half_values, spec.base_translations))
        left_unchanged = cmds.getAttr(f"{result.plan.stretch.settings_path}.{left.attribute}") == 1.0 and all(
            near(cmds.getAttr(f"{joint}.translateX"), base)
            for joint, base in zip(left.segment_joints, left.base_translations)
        )

        cmds.setAttr(attribute, 1.0)
        cmds.xform(spec.wrist_control_path, worldSpace=True, translation=wrist_initial)
        cmds.setAttr(blend_attribute, 0.0)
        cmds.undoInfo(stateWithoutFlush=True)
        checks = {
            "stretch_side_count": len(result.stretch.sides) == 2,
            "default_strength_one": result.stretch.sides[0].attribute_value == 1.0 and result.stretch.sides[1].attribute_value == 1.0,
            "no_compression_inside_rest_length": no_compression,
            "full_stretch_ratio": full_stretch,
            "stretched_wrist_reaches_target": reaches_target,
            "strength_zero_disables_stretch": disabled,
            "strength_half_blends_ratio": half_stretch,
            "left_side_isolated": left_unchanged,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }
        cmds.undo()
        checks["single_undo_removed_complete_arm_rig"] = all(
            not cmds.objExists(path)
            for path in ("|AdvPy_ArmMechanisms", "|AdvPy_ArmFKControls", "|AdvPy_ArmIKControls", "|AdvPy_ArmSettings")
        )
        checks["body_restored"] = skeleton_matches(body_before, host.capture_body_skeleton("Root_M"))
        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls("Root_M", "FitSkeleton", "AdvPy_Arm*", marker, long=True) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_arm_stretch",
            **checks,
            "remaining_nodes": remaining,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if passed else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if passed else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
