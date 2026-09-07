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


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyLegIkControls,
            BuildBodyLegMechanisms,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            InspectBodyRebuildSafety,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableLegIkSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)
        mechanisms = BuildBodyLegMechanisms(host).apply(container).snapshot

        use_case = BuildBodyLegIkControls(host)
        cmds.file(modified=False)
        preview = use_case.plan(container, control_radius=2.25)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container, control_radius=2.25)
        right = next(
            state for state in result.snapshot.limbs
            if state.side.value == "R"
        )
        ankle_driver = next(
            joint.path for joint in mechanisms.joints
            if joint.path.endswith("AdvPy_AnkleIKDriver_R")
        )
        body_ankle = next(
            joint.path for joint in body.joints if joint.name == "Ankle_R"
        )
        body_knee = next(
            joint.path for joint in body.joints if joint.name == "Knee_R"
        )
        body_ankle_before = position(cmds, body_ankle)
        knee_position = position(cmds, body_knee)
        target = tuple(
            ankle + (knee - ankle) * 0.25
            for ankle, knee in zip(right.ankle_position, knee_position)
        )
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.xform(
            right.ankle_control_path,
            worldSpace=True,
            translation=target,
        )
        target_reached = close(position(cmds, ankle_driver), target)
        body_isolated = close(position(cmds, body_ankle), body_ankle_before)
        cmds.xform(
            right.ankle_control_path,
            worldSpace=True,
            translation=right.ankle_position,
        )
        cmds.undoInfo(stateWithoutFlush=True)

        checks = {
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "created_bilateral_controls": len(result.snapshot.limbs) == 2,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
            "ik_target_reached": target_reached,
            "body_isolated": body_isolated,
            "pole_sources_verified": all(
                state.pole_source == state.pole_control_path
                for state in result.snapshot.limbs
            ),
            "ankle_orientation_sources_verified": all(
                state.ankle_source == state.ankle_control_path
                for state in result.snapshot.limbs
            ),
        }

        cmds.undo()
        checks["single_undo_removed_ik"] = (
            not cmds.objExists(preview.ik.root_path)
            and all(
                not cmds.objExists(spec.handle_name)
                for spec in preview.ik.limbs
            )
        )
        checks["mechanisms_survived_ik_undo"] = cmds.objExists(
            "|AdvPy_LegMechanisms"
        )
        checks["body_still_blocked_by_mechanism_links"] = not (
            InspectBodyRebuildSafety(host).execute(container).safe_to_replace
        )
        checks["body_survived"] = len(
            host.capture_body_skeleton("Root_M").joints
        ) == 30
        checks["fit_survived"] = host.capture_fit_orientation(container) == fit

        cmds.undo()
        checks["second_undo_removed_mechanisms"] = not cmds.objExists(
            "|AdvPy_LegMechanisms"
        )
        checks["body_rebuild_safe_after_mechanism_undo"] = (
            InspectBodyRebuildSafety(host).execute(container).safe_to_replace
        )
        checks["unrelated_node_survived"] = cmds.objExists(marker)

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_LegIKControls",
            "AdvPy_LegMechanisms",
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_bilateral_leg_rp_ik_controls",
            **checks,
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
