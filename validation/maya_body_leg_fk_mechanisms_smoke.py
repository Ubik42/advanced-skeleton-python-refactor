from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def close(left, right, tolerance=1e-4):
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
            BuildBodyLegFkMechanismControls,
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
            name="PortableLegFkSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit_before = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)
        mechanisms_before = BuildBodyLegMechanisms(host).apply(container).snapshot

        use_case = BuildBodyLegFkMechanismControls(host)
        cmds.file(modified=False)
        preview = use_case.plan(container, control_radius=2.25)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container, control_radius=2.25)
        snapshot = result.snapshot
        fk_targets_verified = all(
            state.driven_joint == spec.driven_joint
            and "FKDriver" in (state.driven_joint or "")
            for state, spec in zip(snapshot.controls, preview.controls.controls)
        )
        body_paths = {joint.path for joint in body_before.joints}
        body_not_directly_driven = all(
            state.driven_joint not in body_paths for state in snapshot.controls
        )
        zero_channels = all(
            close(state.local_translation, (0.0, 0.0, 0.0))
            and close(state.local_rotation, (0.0, 0.0, 0.0))
            for state in snapshot.controls
        )
        mechanism_bind_pose_preserved = host.capture_body_leg_mechanisms(
            BuildBodyLegMechanisms(host).plan(container).mechanisms
        ) == mechanisms_before

        hip_control = next(
            state.control_path for state in snapshot.controls
            if state.control_path.endswith("AdvPy_HipFK_R")
        )
        fk_ankle = next(
            state.driven_joint for state in snapshot.controls
            if state.control_path.endswith("AdvPy_AnkleFK_R")
        )
        ik_ankle = next(
            state.path for state in mechanisms_before.joints
            if state.path.endswith("AdvPy_AnkleIKDriver_R")
        )
        body_ankle = next(
            state.path for state in body_before.joints if state.name == "Ankle_R"
        )
        fk_before = position(cmds, fk_ankle)
        ik_before = position(cmds, ik_ankle)
        body_ankle_before = position(cmds, body_ankle)
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{hip_control}.rotateZ", 25.0)
        control_drives_only_fk_chain = (
            not close(position(cmds, fk_ankle), fk_before)
            and close(position(cmds, ik_ankle), ik_before)
            and close(position(cmds, body_ankle), body_ankle_before)
        )
        cmds.setAttr(f"{hip_control}.rotateZ", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)

        checks = {
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "created_eight_controls": len(snapshot.controls) == 8,
            "fk_driver_targets_verified": fk_targets_verified,
            "body_not_directly_driven": body_not_directly_driven,
            "zero_control_channels": zero_channels,
            "body_bind_pose_preserved": host.capture_body_skeleton("Root_M") == body_before,
            "mechanism_bind_pose_preserved": mechanism_bind_pose_preserved,
            "fit_source_preserved": host.capture_fit_orientation(container) == fit_before,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
            "control_drives_only_fk_chain": control_drives_only_fk_chain,
        }

        cmds.undo()
        checks["single_undo_removed_controls"] = (
            not cmds.objExists(preview.controls.root_path)
            and all(
                not cmds.objExists(name)
                for spec in preview.controls.controls
                for name in (spec.offset_path, spec.control_path, spec.constraint_name)
            )
        )
        checks["mechanisms_survived_control_undo"] = len(
            host.capture_body_leg_mechanisms(
                BuildBodyLegMechanisms(host).plan(container).mechanisms
            ).joints
        ) == 20
        checks["body_still_blocked_by_mechanism_links"] = not (
            InspectBodyRebuildSafety(host).execute(container).safe_to_replace
        )

        cmds.undo()
        checks["second_undo_removed_mechanisms"] = not cmds.objExists(
            "|AdvPy_LegMechanisms"
        )
        checks["body_rebuild_safe_after_mechanism_undo"] = (
            InspectBodyRebuildSafety(host).execute(container).safe_to_replace
        )
        checks["body_survived"] = len(
            host.capture_body_skeleton("Root_M").joints
        ) == 30
        checks["fit_source_survived"] = (
            host.capture_fit_orientation(container) == fit_before
        )
        checks["unrelated_node_survived"] = cmds.objExists(marker)

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_LegMechanisms",
            "AdvPy_LegFKControls",
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_leg_fk_controls_to_mechanisms",
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
