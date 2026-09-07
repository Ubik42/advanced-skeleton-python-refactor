from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def close(left, right, tolerance=1e-3):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def position(cmds, node):
    return tuple(float(value) for value in cmds.xform(node, query=True, worldSpace=True, translation=True))


def skeleton_matches(before, after):
    wanted = {joint.path: joint for joint in before.joints}
    current = {joint.path: joint for joint in after.joints}
    return before.root == after.root and before.provenance == after.provenance and set(wanted) == set(current) and all(
        wanted[path].parent_path == current[path].parent_path
        and close(wanted[path].world_position, current[path].world_position, 1e-4)
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
        marker = cmds.createNode("transform", name="PortableArmTranslationBlendSelection", skipSelect=True)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        cmds.select(marker, replace=True)
        result = BuildBodyArmRig(host).apply(container)

        right = next(side for side in result.plan.blend.sides if side.side is FitBuildSide.RIGHT)
        elbow = right.joints[1]
        wrist = right.joints[2]
        translation_states = tuple(
            joint
            for side in result.blend.sides
            for joint in side.joints
            if joint.translation_constraint_name is not None
        )
        bind_unchanged = skeleton_matches(body_before, host.capture_body_skeleton("Root_M"))

        cmds.undoInfo(stateWithoutFlush=False)
        fk_value = cmds.getAttr(f"{elbow.fk_driver}.translateX")
        cmds.setAttr(f"{elbow.fk_driver}.translateX", fk_value * 1.12)
        fk_position_follows = close(position(cmds, elbow.body_joint), position(cmds, elbow.fk_driver))
        cmds.setAttr(f"{elbow.fk_driver}.translateX", fk_value)

        cmds.setAttr("|AdvPy_ArmSettings.armIkFk_R", 1.0)
        ik_elbow_value = cmds.getAttr(f"{elbow.ik_driver}.translateX")
        ik_wrist_value = cmds.getAttr(f"{wrist.ik_driver}.translateX")
        cmds.setAttr(f"{elbow.ik_driver}.translateX", ik_elbow_value * 1.1)
        cmds.setAttr(f"{wrist.ik_driver}.translateX", ik_wrist_value * 1.15)
        ik_positions_follow = (
            close(position(cmds, elbow.body_joint), position(cmds, elbow.ik_driver))
            and close(position(cmds, wrist.body_joint), position(cmds, wrist.ik_driver))
        )
        cmds.setAttr(f"{elbow.ik_driver}.translateX", ik_elbow_value)
        cmds.setAttr(f"{wrist.ik_driver}.translateX", ik_wrist_value)
        cmds.setAttr("|AdvPy_ArmSettings.armIkFk_R", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)

        checks = {
            "translation_constraint_count": len(translation_states) == 4,
            "translation_wiring_audited": all(
                state.translation_fk_weight_source and state.translation_fk_weight_source.endswith(".outputX")
                and state.translation_ik_weight_source and state.translation_ik_weight_source.startswith("|AdvPy_ArmSettings.armIkFk_")
                for state in translation_states
            ),
            "bind_pose_unchanged": bind_unchanged,
            "fk_translation_reaches_body": fk_position_follows,
            "ik_translation_reaches_body": ik_positions_follow,
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
            "slice": "body_arm_translation_blend",
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
