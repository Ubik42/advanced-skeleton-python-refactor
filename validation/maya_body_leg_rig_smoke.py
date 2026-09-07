from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def close(left, right, tolerance=1e-3):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def position(cmds, path):
    return cmds.xform(path, query=True, worldSpace=True, translation=True)


def visible(cmds, path):
    return bool(cmds.getAttr(f"{path}.visibility"))


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
            InspectBodyRebuildSafety,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform", name="PortableCompleteLegRigSelection", skipSelect=True
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)

        use_case = BuildBodyLegRig(host)
        cmds.file(modified=False)
        preview = use_case.plan(container, control_radius=2.0)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container, control_radius=2.0)

        right_ankle = next(
            joint.path for joint in body.joints if joint.name == "Ankle_R"
        )
        left_ankle = next(
            joint.path for joint in body.joints if joint.name == "Ankle_L"
        )
        right_knee_position = next(
            joint.world_position for joint in body.joints if joint.name == "Knee_R"
        )
        bind_right = position(cmds, right_ankle)
        bind_left = position(cmds, left_ankle)
        right_fk = next(
            state.control_path
            for state in result.fk_controls.controls
            if state.control_path.endswith("AdvPy_HipFK_R")
        )
        right_ik = next(
            state.ankle_control_path
            for state in result.ik.limbs
            if state.side.value == "R"
        )
        visibility = {side.side.value: side for side in result.plan.visibility.sides}
        default_fk_only = all(
            visible(cmds, side.fk_offset_path)
            and all(not visible(cmds, path) for path in side.ik_offset_paths)
            for side in visibility.values()
        )

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{right_fk}.rotateZ", 20.0)
        fk_drives_body = not close(position(cmds, right_ankle), bind_right)
        cmds.setAttr(f"{right_fk}.rotateZ", 0.0)

        right_plug = f"{result.blend.settings_path}.legIkFk_R"
        left_plug = f"{result.blend.settings_path}.legIkFk_L"
        cmds.setAttr(right_plug, 1.0)
        target = tuple(
            ankle + (knee - ankle) * 0.25
            for ankle, knee in zip(bind_right, right_knee_position)
        )
        cmds.xform(right_ik, worldSpace=True, translation=target)
        right = visibility["R"]
        left = visibility["L"]
        ik_drives_body = close(position(cmds, right_ankle), target)
        right_ik_only = (
            not visible(cmds, right.fk_offset_path)
            and all(visible(cmds, path) for path in right.ik_offset_paths)
        )
        left_independent = (
            close(position(cmds, left_ankle), bind_left)
            and cmds.getAttr(left_plug) == 0.0
            and visible(cmds, left.fk_offset_path)
            and all(not visible(cmds, path) for path in left.ik_offset_paths)
        )
        cmds.setAttr(right_plug, 0.0)
        cmds.xform(right_ik, worldSpace=True, translation=bind_right)
        cmds.undoInfo(stateWithoutFlush=True)

        checks = {
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "mechanism_count": len(result.mechanisms.joints) == 12,
            "fk_control_count": len(result.fk_controls.controls) == 6,
            "ik_side_count": len(result.ik.limbs) == 2,
            "blend_constraint_count": sum(
                len(side.joints) for side in result.blend.sides
            ) == 6,
            "visibility_side_count": len(result.visibility.sides) == 2,
            "foot_side_count": len(result.foot.sides) == 2,
            "foot_pivot_count": sum(
                len(side.pivots) for side in result.foot.sides
            ) == 10,
            "foot_handles_parented_to_ball": all(
                side.handle_parent_path == side.pivots[-1].path
                for side in result.foot.sides
            ),
            "default_fk_only": default_fk_only,
            "fk_drives_body": fk_drives_body,
            "ik_drives_body": ik_drives_body,
            "right_ik_only": right_ik_only,
            "left_side_independent": left_independent,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.undo()
        remaining_rig = (
            (cmds.ls("AdvPy_Leg*", long=True) or [])
            + (cmds.ls("AdvPy_Foot*", long=True) or [])
        )
        checks["single_undo_removed_complete_leg_rig"] = not remaining_rig
        checks["body_restored"] = host.capture_body_skeleton("Root_M") == body
        checks["fit_preserved"] = host.capture_fit_orientation(container) == fit
        checks["body_rebuild_safe_after_undo"] = (
            InspectBodyRebuildSafety(host).execute(container).safe_to_replace
        )
        checks["unrelated_node_survived"] = cmds.objExists(marker)

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
            "slice": "complete_body_leg_rig_with_foot_atomic",
            **checks,
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
