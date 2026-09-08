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


def frame_close(left, right, tolerance=1e-4):
    return all(close(a, b, tolerance) for a, b in zip(left, right))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyExportSkeleton,
            BuildBodyRootMotion,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            InspectBodyRebuildSafety,
        )
        from adv_py.core import (
            BODY_EXPORT_KIND,
            BODY_EXPORT_OWNER,
            BODY_EXPORT_SCHEMA_VERSION,
            audit_body_export_skeleton,
            audit_body_root_motion,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="ExportSkeletonSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body = BuildOrientedBodySkeleton(host).apply(container).snapshot
        body_before = host.capture_body_skeleton("Root_M")
        cmds.select(marker, replace=True)

        root_motion = BuildBodyRootMotion(host).apply(
            source_container=container
        )
        result = BuildBodyExportSkeleton(host).apply(
            source_container=container
        )
        plan = result.plan.export_skeleton
        snapshot = result.verified
        root_state = snapshot.joints[0]
        checks = {
            "thirty_export_joints": len(snapshot.joints) == len(body.joints) == 30,
            "root_parented_to_root_motion": (
                root_state.output_parent_path == root_motion.verified.output_path
            ),
            "complete_initial_audit": not audit_body_export_skeleton(
                plan,
                snapshot,
            ),
            "owned_provenance": (
                snapshot.owner == BODY_EXPORT_OWNER
                and snapshot.artifact_kind == BODY_EXPORT_KIND
                and snapshot.schema_version == BODY_EXPORT_SCHEMA_VERSION
                and snapshot.source_body_root == body.root
                and snapshot.joint_count == len(body.joints)
            ),
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
            "body_rebuild_blocked_while_export_attached": not (
                InspectBodyRebuildSafety(host).execute(container).safe_to_replace
            ),
        }

        shoulder = "|Root_M|Spine1_M|Chest_M|Scapula_R|Shoulder_R"
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            cmds.setAttr(f"{body.root}.translate", 3.0, 4.0, 5.0, type="double3")
            cmds.setAttr(f"{body.root}.rotateZ", 20.0)
            cmds.setAttr(f"{shoulder}.rotateX", 25.0)
            cmds.dgdirty(allPlugs=True)
            posed_body = host.capture_body_skeleton("Root_M")
            posed_export = host.capture_body_export_skeleton(plan)
            body_states = {state.path: state for state in posed_body.joints}
            export_follows_all_body_joints = all(
                state.source_path in body_states
                and close(
                    state.world_position,
                    body_states[state.source_path].world_position,
                )
                and frame_close(
                    state.world_axes,
                    body_states[state.source_path].world_axes,
                )
                for state in posed_export.joints
            )
            cmds.setAttr(f"{body.root}.translate", 0.0, 0.0, 0.0, type="double3")
            cmds.setAttr(f"{body.root}.rotateZ", 0.0)
            cmds.setAttr(f"{shoulder}.rotateX", 0.0)
            cmds.dgdirty(allPlugs=True)
        finally:
            cmds.undoInfo(stateWithoutFlush=True)
        checks["live_export_follows_complete_body_pose"] = (
            export_follows_all_body_joints
        )
        checks["body_restored_after_pose_check"] = (
            host.capture_body_skeleton("Root_M") == body_before
        )

        cmds.undo()
        remaining_export = cmds.ls("AdvPy_EXP_*", long=True) or []
        checks["single_undo_removed_export_skeleton"] = not remaining_export
        checks["single_undo_kept_live_root_motion"] = not audit_body_root_motion(
            root_motion.plan.root_motion,
            host.capture_body_root_motion(root_motion.plan.root_motion),
        )
        checks["single_undo_kept_body_and_fit"] = (
            bool(cmds.ls("Root_M", long=True, type="joint") or [])
            and bool(cmds.ls("FitSkeleton", long=True) or [])
        )

        cmds.undo()
        checks["second_undo_removed_root_motion"] = not any(
            cmds.ls(name, long=True) or []
            for name in root_motion.plan.root_motion.node_names
        )
        checks["body_rebuild_safe_after_export_chain_removed"] = (
            InspectBodyRebuildSafety(host).execute(container).safe_to_replace
        )

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_EXP_*",
            "AdvPy_GameRootMotion*",
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_game_export_skeleton",
            **checks,
            "source_joint_count": len(body.joints),
            "export_joint_count": len(snapshot.joints),
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
