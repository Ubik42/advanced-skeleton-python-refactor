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
            BuildBodyArmFkMechanismControls,
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
            name="PortableFkMechanismSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit_before = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)
        mechanisms_before = BuildBodyArmMechanisms(host).apply(container).snapshot

        use_case = BuildBodyArmFkMechanismControls(host)
        cmds.file(modified=False)
        preview = use_case.plan(container, control_radius=2.0)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container, control_radius=2.0)
        snapshot = result.snapshot
        fk_targets_verified = all(
            state.driven_joint == spec.driven_joint
            and "FKDriver" in (state.driven_joint or "")
            for state, spec in zip(snapshot.controls, preview.controls.controls)
        )
        body_not_directly_driven = all(
            state.driven_joint not in {joint.path for joint in body_before.joints}
            for state in snapshot.controls
        )
        body_preserved = host.capture_body_skeleton("Root_M") == body_before
        mechanism_bind_pose_preserved = host.capture_body_arm_mechanisms(
            BuildBodyArmMechanisms(host).plan(container).mechanisms
        ) == mechanisms_before
        fit_preserved = host.capture_fit_orientation(container) == fit_before
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]

        shoulder_control = next(
            state.control_path
            for state in snapshot.controls
            if state.control_path.endswith("AdvPy_ShoulderFK_R")
        )
        fk_wrist = next(
            state.driven_joint
            for state in snapshot.controls
            if state.control_path.endswith("AdvPy_WristFK_R")
        )
        ik_wrist = next(
            state.path
            for state in mechanisms_before.joints
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
        cmds.setAttr(f"{shoulder_control}.rotateZ", 25.0)
        control_drives_only_fk_chain = (
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
        cmds.setAttr(f"{shoulder_control}.rotateZ", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)

        cmds.undo()
        controls_removed = all(
            not cmds.objExists(name)
            for spec in preview.controls.controls
            for name in (spec.offset_path, spec.control_path, spec.constraint_name)
        ) and not cmds.objExists(preview.controls.root_path)
        mechanisms_survived_control_undo = len(
            host.capture_body_arm_mechanisms(
                BuildBodyArmMechanisms(host).plan(container).mechanisms
            ).joints
        ) == 12
        body_still_blocked = not InspectBodyRebuildSafety(host).execute(
            container
        ).safe_to_replace

        cmds.undo()
        mechanisms_removed = not cmds.objExists("|AdvPy_ArmMechanisms")
        body_safe_again = InspectBodyRebuildSafety(host).execute(
            container
        ).safe_to_replace
        body_survived = len(host.capture_body_skeleton("Root_M").joints) == 30
        fit_survived = host.capture_fit_orientation(container) == fit_before
        marker_survived = cmds.objExists(marker)

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_ArmMechanisms",
            "AdvPy_ArmFKControls",
            marker,
            long=True,
        ) or []
        passed = all(
            (
                preview.ready,
                preview_clean,
                len(snapshot.controls) == 6,
                fk_targets_verified,
                body_not_directly_driven,
                body_preserved,
                mechanism_bind_pose_preserved,
                fit_preserved,
                selection_preserved,
                control_drives_only_fk_chain,
                controls_removed,
                mechanisms_survived_control_undo,
                body_still_blocked,
                mechanisms_removed,
                body_safe_again,
                body_survived,
                fit_survived,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_arm_fk_controls_to_mechanisms",
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "created_control_count": len(snapshot.controls),
            "fk_driver_targets_verified": fk_targets_verified,
            "body_not_directly_driven": body_not_directly_driven,
            "body_bind_pose_preserved": body_preserved,
            "mechanism_bind_pose_preserved": mechanism_bind_pose_preserved,
            "fit_source_preserved": fit_preserved,
            "selection_preserved": selection_preserved,
            "control_drives_only_fk_chain": control_drives_only_fk_chain,
            "single_undo_removed_controls": controls_removed,
            "mechanisms_survived_control_undo": mechanisms_survived_control_undo,
            "body_still_blocked_by_mechanism_links": body_still_blocked,
            "second_undo_removed_mechanisms": mechanisms_removed,
            "body_rebuild_safe_after_mechanism_undo": body_safe_again,
            "body_survived": body_survived,
            "fit_source_survived": fit_survived,
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
