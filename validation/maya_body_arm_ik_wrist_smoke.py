from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def axes(cmds, node):
    matrix = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    return tuple(tuple(float(value) for value in matrix[index : index + 3]) for index in (0, 4, 8))


def close(left, right, tolerance=1e-4):
    return all(abs(a - b) <= tolerance for row_a, row_b in zip(left, right) for a, b in zip(row_a, row_b))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import BuildBodyArmRig, BuildOrientedBodySkeleton, BuildSyntheticBodySourceFit, CreateFitSkeleton

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode("transform", name="PortableArmWristOrientationSelection", skipSelect=True)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        BuildOrientedBodySkeleton(host).apply(container)
        cmds.select(marker, replace=True)

        result = BuildBodyArmRig(host).apply(container)
        limb = next(state for state in result.ik.limbs if state.side.value == "R")
        settings = result.blend.settings_path
        body_wrist = next(joint.body_joint for side in result.plan.blend.sides if side.side.value == "R" for joint in side.joints if "Wrist" in joint.constraint_name)

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{settings}.armIkFk_R", 1)
        before = axes(cmds, body_wrist)
        cmds.setAttr(f"{limb.wrist_control_path}.rotateX", 27.0)
        control_axes = axes(cmds, limb.wrist_control_path)
        driver_axes = axes(cmds, limb.wrist_driven_joint)
        body_axes = axes(cmds, body_wrist)
        cmds.setAttr(f"{limb.wrist_control_path}.rotateX", 0.0)
        cmds.setAttr(f"{settings}.armIkFk_R", 0)
        cmds.undoInfo(stateWithoutFlush=True)

        checks = {
            "wrist_constraint_captured": limb.wrist_source == limb.wrist_control_path and limb.wrist_driven_joint is not None,
            "wrist_control_changes_orientation": not close(before, control_axes),
            "wrist_control_drives_ik_driver": close(control_axes, driver_axes),
            "ik_driver_drives_body_wrist": close(driver_axes, body_axes),
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }
        cmds.undo()
        checks["single_undo_removed_complete_arm_rig"] = all(
            not cmds.objExists(path)
            for path in ("|AdvPy_ArmMechanisms", "|AdvPy_ArmFKControls", "|AdvPy_ArmIKControls", "|AdvPy_ArmSettings")
        )
        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls("Root_M", "FitSkeleton", "AdvPy_Arm*", marker, long=True) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_arm_ik_wrist_orientation",
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
