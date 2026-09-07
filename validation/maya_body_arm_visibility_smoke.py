from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


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

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode("transform", name="PortableArmVisibilitySelection", skipSelect=True)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        BuildOrientedBodySkeleton(host).apply(container)
        cmds.select(marker, replace=True)

        result = BuildBodyArmRig(host).apply(container)
        settings = result.blend.settings_path
        right = next(side for side in result.plan.visibility.sides if side.side.value == "R")
        left = next(side for side in result.plan.visibility.sides if side.side.value == "L")

        default_visibility = (
            cmds.getAttr(f"{right.fk_offset_path}.visibility") == 1
            and all(cmds.getAttr(f"{path}.visibility") == 0 for path in right.ik_offset_paths)
        )
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{settings}.armIkFk_R", 1)
        right_ik_visibility = (
            cmds.getAttr(f"{right.fk_offset_path}.visibility") == 0
            and all(cmds.getAttr(f"{path}.visibility") == 1 for path in right.ik_offset_paths)
        )
        left_isolated = (
            cmds.getAttr(f"{left.fk_offset_path}.visibility") == 1
            and all(cmds.getAttr(f"{path}.visibility") == 0 for path in left.ik_offset_paths)
        )
        cmds.setAttr(f"{settings}.armIkFk_R", 0)
        cmds.undoInfo(stateWithoutFlush=True)

        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        wiring_audited = len(result.visibility.sides) == 2
        cmds.undo()
        roots_removed = all(
            not cmds.objExists(path)
            for path in (
                "|AdvPy_ArmMechanisms",
                "|AdvPy_ArmFKControls",
                "|AdvPy_ArmIKControls",
                "|AdvPy_ArmSettings",
            )
        )

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls("Root_M", "FitSkeleton", "AdvPy_Arm*", marker, long=True) or []
        checks = {
            "default_fk_visible_ik_hidden": default_visibility,
            "right_ik_mode_visibility": right_ik_visibility,
            "left_side_isolated": left_isolated,
            "visibility_wiring_audited": wiring_audited,
            "selection_preserved": selection_preserved,
            "single_undo_removed_complete_arm_rig": roots_removed,
            "cleanup": not remaining,
        }
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_arm_control_visibility",
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
