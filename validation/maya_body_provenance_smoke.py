from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


ATTRIBUTES = (
    "advPyOwner",
    "advPyArtifactKind",
    "advPySchemaVersion",
    "advPySourceContainer",
    "advPyBodyJointCount",
)


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
            InspectBodySkeletonProvenance,
        )
        from adv_py.core import (
            BODY_PROVENANCE_KIND,
            BODY_PROVENANCE_OWNER,
            BODY_PROVENANCE_SCHEMA_VERSION,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableBodyProvenanceSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        source_before = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)

        result = BuildOrientedBodySkeleton(host).apply(container)
        root = result.snapshot.root
        state = result.snapshot.provenance
        expected_values = (
            state is not None
            and state.owner == BODY_PROVENANCE_OWNER
            and state.artifact_kind == BODY_PROVENANCE_KIND
            and state.schema_version == BODY_PROVENANCE_SCHEMA_VERSION
            and state.source_container == container
            and state.body_joint_count == 30
        )
        attributes_exist = all(
            cmds.attributeQuery(attribute, node=root, exists=True)
            for attribute in ATTRIBUTES
        )
        attributes_locked = all(
            cmds.getAttr(f"{root}.{attribute}", lock=True)
            for attribute in ATTRIBUTES
        )

        inspector = InspectBodySkeletonProvenance(host)
        cmds.file(modified=False)
        valid_audit = inspector.execute(
            source_container=container,
            expected_joint_count=30,
        )
        mismatch_audit = inspector.execute(
            source_container=container,
            expected_joint_count=31,
        )
        audit_read_only = not bool(cmds.file(query=True, modified=True))
        mismatch_detected = (
            not mismatch_audit.owned
            and any(
                issue.code == "provenance_body_joint_count_mismatch"
                for issue in mismatch_audit.issues
            )
        )
        fit_preserved = host.capture_fit_orientation(container) == source_before
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]

        cmds.undo()
        single_undo_removed_body = not (cmds.ls("Root_M", long=True) or [])
        fit_survived_undo = host.capture_fit_orientation(container) == source_before
        marker_survived = cmds.objExists(marker)

        cmds.delete(container, marker)
        remaining = cmds.ls("Root_M", "FitSkeleton", marker, long=True) or []
        passed = all(
            (
                expected_values,
                attributes_exist,
                attributes_locked,
                valid_audit.owned,
                audit_read_only,
                mismatch_detected,
                fit_preserved,
                selection_preserved,
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
            "slice": "body_provenance_contract",
            "owner": state.owner if state else None,
            "artifact_kind": state.artifact_kind if state else None,
            "schema_version": state.schema_version if state else None,
            "source_container": state.source_container if state else None,
            "body_joint_count": state.body_joint_count if state else None,
            "provenance_values_verified": expected_values,
            "attributes_exist": attributes_exist,
            "attributes_locked": attributes_locked,
            "valid_audit_owned": valid_audit.owned,
            "audit_did_not_modify_scene": audit_read_only,
            "mismatched_count_detected": mismatch_detected,
            "fit_source_preserved": fit_preserved,
            "selection_preserved": selection_preserved,
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
