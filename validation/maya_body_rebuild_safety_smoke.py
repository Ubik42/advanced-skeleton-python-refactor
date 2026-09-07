from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


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
            name="PortableRebuildSafetySelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        source_before = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)
        body_result = BuildOrientedBodySkeleton(host).apply(container)
        chest = next(
            state.path
            for state in body_result.snapshot.joints
            if state.name == "Chest_M"
        )

        inspector = InspectBodyRebuildSafety(host)
        cmds.file(modified=False)
        clean_audit = inspector.execute(container)
        clean_audit_read_only = not bool(cmds.file(query=True, modified=True))
        clean_dependency_count = len(clean_audit.scene.external_dependencies)

        cmds.undoInfo(stateWithoutFlush=False)
        attachment = cmds.createNode(
            "transform",
            name="UserBodyAttachment",
            parent=chest,
            skipSelect=True,
        )
        consumer = cmds.createNode(
            "network",
            name="ExternalBodyConsumer",
            skipSelect=True,
        )
        cmds.addAttr(consumer, longName="bodyLink", attributeType="message")
        cmds.connectAttr("|Root_M.message", f"{consumer}.bodyLink")
        cmds.undoInfo(stateWithoutFlush=True)

        blocked_audit = inspector.execute(container)
        blocked_codes = {issue.code for issue in blocked_audit.issues}
        dag_attachment_blocked = "unexpected_dag_descendant" in blocked_codes
        external_connection_blocked = "external_connection" in blocked_codes

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.delete(attachment, consumer)
        cmds.undoInfo(stateWithoutFlush=True)
        restored_audit = inspector.execute(container)
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        fit_preserved = host.capture_fit_orientation(container) == source_before

        cmds.undo()
        single_undo_removed_body = not (cmds.ls("Root_M", long=True) or [])
        fit_survived_undo = host.capture_fit_orientation(container) == source_before
        marker_survived = cmds.objExists(marker)

        cmds.delete(container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "UserBodyAttachment",
            "ExternalBodyConsumer",
            marker,
            long=True,
        ) or []
        passed = all(
            (
                clean_audit.safe_to_replace,
                clean_audit_read_only,
                clean_dependency_count == 0,
                not blocked_audit.safe_to_replace,
                dag_attachment_blocked,
                external_connection_blocked,
                restored_audit.safe_to_replace,
                selection_preserved,
                fit_preserved,
                single_undo_removed_body,
                fit_survived_undo,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_rebuild_safety_inspection",
            "clean_body_safe_to_replace": clean_audit.safe_to_replace,
            "clean_audit_did_not_modify_scene": clean_audit_read_only,
            "clean_external_dependency_count": clean_dependency_count,
            "attached_body_blocked": not blocked_audit.safe_to_replace,
            "unexpected_dag_descendant_detected": dag_attachment_blocked,
            "external_connection_detected": external_connection_blocked,
            "restored_body_safe_to_replace": restored_audit.safe_to_replace,
            "selection_preserved": selection_preserved,
            "fit_source_preserved": fit_preserved,
            "single_undo_removed_owned_body": single_undo_removed_body,
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
