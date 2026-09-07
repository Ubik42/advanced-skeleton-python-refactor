from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def _close(left, right, tolerance=1e-4):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyArmMechanisms,
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
            name="PortableArmMechanismSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit_before = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)

        use_case = BuildBodyArmMechanisms(host)
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
            _close(state.rotation, (0.0, 0.0, 0.0))
            for state in snapshot.joints
        )
        body_preserved = host.capture_body_skeleton("Root_M") == body_before
        fit_preserved = host.capture_fit_orientation(container) == fit_before
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        rebuild_blocked_by_links = any(
            issue.code == "external_connection"
            for issue in InspectBodyRebuildSafety(host).execute(container).issues
        )

        fk_shoulder = next(
            state.path
            for state in snapshot.joints
            if state.path.endswith("AdvPy_ShoulderFKDriver_R")
        )
        fk_wrist = next(
            state.path
            for state in snapshot.joints
            if state.path.endswith("AdvPy_WristFKDriver_R")
        )
        ik_wrist = next(
            state.path
            for state in snapshot.joints
            if state.path.endswith("AdvPy_WristIKDriver_R")
        )
        body_wrist = next(
            state.path for state in body_before.joints if state.name == "Wrist_R"
        )
        fk_wrist_before = cmds.xform(
            fk_wrist, query=True, worldSpace=True, translation=True
        )
        ik_wrist_before = cmds.xform(
            ik_wrist, query=True, worldSpace=True, translation=True
        )
        body_wrist_before = cmds.xform(
            body_wrist, query=True, worldSpace=True, translation=True
        )
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{fk_shoulder}.rotateZ", 25.0)
        fk_chain_moves_independently = (
            not _close(
                cmds.xform(fk_wrist, query=True, worldSpace=True, translation=True),
                fk_wrist_before,
            )
            and _close(
                cmds.xform(ik_wrist, query=True, worldSpace=True, translation=True),
                ik_wrist_before,
            )
            and _close(
                cmds.xform(body_wrist, query=True, worldSpace=True, translation=True),
                body_wrist_before,
            )
        )
        cmds.setAttr(f"{fk_shoulder}.rotateZ", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)

        cmds.undo()
        mechanisms_removed = not (
            cmds.ls("AdvPy_ArmMechanisms", "AdvPy_*Driver_*", long=True) or []
        )
        body_survived = len(host.capture_body_skeleton("Root_M").joints) == 30
        body_safe_again = InspectBodyRebuildSafety(host).execute(
            container
        ).safe_to_replace
        fit_survived_undo = host.capture_fit_orientation(container) == fit_before
        marker_survived = cmds.objExists(marker)

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_ArmMechanisms",
            "AdvPy_*Driver_*",
            marker,
            long=True,
        ) or []
        passed = all(
            (
                preview.ready,
                preview_clean,
                len(preview.mechanisms.joints) == 12,
                len(snapshot.joints) == 12,
                sources_verified,
                zero_rotations,
                body_preserved,
                fit_preserved,
                selection_preserved,
                rebuild_blocked_by_links,
                fk_chain_moves_independently,
                mechanisms_removed,
                body_survived,
                body_safe_again,
                fit_survived_undo,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_bilateral_arm_fk_ik_mechanisms",
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "planned_joint_count": len(preview.mechanisms.joints),
            "created_joint_count": len(snapshot.joints),
            "source_links_verified": sources_verified,
            "driver_rotations_zero": zero_rotations,
            "body_bind_pose_preserved": body_preserved,
            "fit_source_preserved": fit_preserved,
            "selection_preserved": selection_preserved,
            "rebuild_blocked_while_source_links_exist": rebuild_blocked_by_links,
            "fk_chain_moves_independently": fk_chain_moves_independently,
            "single_undo_removed_mechanisms": mechanisms_removed,
            "body_survived_undo": body_survived,
            "body_rebuild_safe_after_undo": body_safe_again,
            "fit_source_survived_undo": fit_survived_undo,
            "unrelated_node_survived": marker_survived,
            "cleanup": not remaining,
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
