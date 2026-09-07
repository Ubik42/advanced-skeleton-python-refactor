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
    return tuple(float(value) for value in cmds.xform(
        path,
        query=True,
        worldSpace=True,
        translation=True,
    ))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyLegMechanisms,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            InspectBodyRebuildSafety,
        )
        from adv_py.core import BodyLegMechanismRole, FitBuildSide

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableLegMechanismSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit_before = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)

        use_case = BuildBodyLegMechanisms(host)
        cmds.file(modified=False)
        preview = use_case.plan(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container)
        snapshot = result.snapshot
        source_by_path = {
            state.path: state.source_joint for state in snapshot.joints
        }
        sources_verified = all(
            source_by_path.get(spec.path) == spec.source_joint
            for spec in preview.mechanisms.joints
        )
        zero_rotations = all(
            close(state.rotation, (0.0, 0.0, 0.0))
            for state in snapshot.joints
        )
        side_counts = {
            side.value: sum(state.side is side for state in snapshot.joints)
            for side in (FitBuildSide.RIGHT, FitBuildSide.LEFT)
        }
        role_counts = {
            role.value: sum(spec.role is role for spec in preview.mechanisms.joints)
            for role in (BodyLegMechanismRole.FK, BodyLegMechanismRole.IK)
        }
        rebuild_blocked = any(
            issue.code == "external_connection"
            for issue in InspectBodyRebuildSafety(host).execute(container).issues
        )

        fk_hip = next(
            state.path
            for state in snapshot.joints
            if state.path.endswith("AdvPy_HipFKDriver_R")
        )
        fk_ankle = next(
            state.path
            for state in snapshot.joints
            if state.path.endswith("AdvPy_AnkleFKDriver_R")
        )
        ik_ankle = next(
            state.path
            for state in snapshot.joints
            if state.path.endswith("AdvPy_AnkleIKDriver_R")
        )
        body_ankle = next(
            state.path for state in body_before.joints if state.name == "Ankle_R"
        )
        fk_before = position(cmds, fk_ankle)
        ik_before = position(cmds, ik_ankle)
        body_ankle_before = position(cmds, body_ankle)
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{fk_hip}.rotateZ", 25.0)
        fk_independent = (
            not close(position(cmds, fk_ankle), fk_before)
            and close(position(cmds, ik_ankle), ik_before)
            and close(position(cmds, body_ankle), body_ankle_before)
        )
        cmds.setAttr(f"{fk_hip}.rotateZ", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)

        checks = {
            "preview_ready": preview.ready,
            "preview_clean": preview_clean,
            "planned_twelve_joints": len(preview.mechanisms.joints) == 12,
            "created_twelve_joints": len(snapshot.joints) == 12,
            "bilateral_six_per_side": side_counts == {"R": 6, "L": 6},
            "six_fk_and_six_ik": role_counts == {"fk": 6, "ik": 6},
            "source_links_verified": sources_verified,
            "driver_rotations_zero": zero_rotations,
            "body_preserved": host.capture_body_skeleton("Root_M") == body_before,
            "fit_preserved": host.capture_fit_orientation(container) == fit_before,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
            "rebuild_blocked_while_source_links_exist": rebuild_blocked,
            "fk_and_ik_chains_are_independent": fk_independent,
        }

        cmds.undo()
        checks["single_undo_removed_leg_mechanisms"] = not (
            cmds.ls("AdvPy_LegMechanisms", "AdvPy_Hip*Driver_*", "AdvPy_Knee*Driver_*", "AdvPy_Ankle*Driver_*", long=True)
            or []
        )
        checks["body_survived_undo"] = len(host.capture_body_skeleton("Root_M").joints) == 30
        checks["body_rebuild_safe_after_undo"] = InspectBodyRebuildSafety(host).execute(container).safe_to_replace
        checks["fit_survived_undo"] = host.capture_fit_orientation(container) == fit_before
        checks["unrelated_node_survived"] = cmds.objExists(marker)

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_LegMechanisms",
            "AdvPy_Hip*Driver_*",
            "AdvPy_Knee*Driver_*",
            "AdvPy_Ankle*Driver_*",
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_bilateral_leg_fk_ik_mechanisms",
            **checks,
            "side_counts": side_counts,
            "role_counts": role_counts,
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
