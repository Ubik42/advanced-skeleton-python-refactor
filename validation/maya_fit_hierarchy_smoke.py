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

        from adv_py.adapters import MayaFitJointHost
        from adv_py.application import InspectFitHierarchy

        cmds.file(new=True, force=True)
        container = cmds.createNode("transform", name="PortableFitSkeleton")
        root = cmds.createNode("joint", name="Root", parent=container)
        cmds.setAttr(f"{root}.translate", 0.0, 1.0, 0.0)
        spine = cmds.createNode("joint", name="Spine1", parent=root)
        cmds.setAttr(f"{spine}.translate", 0.0, 4.0, 0.0)

        inspector = InspectFitHierarchy(MayaFitJointHost())
        cmds.file(modified=False)
        valid_audit = inspector.execute(container)
        valid_snapshot = valid_audit.require_valid()
        capture_clean = not bool(cmds.file(query=True, modified=True))
        stable_order = tuple(item.short_name for item in valid_snapshot.joints) == (
            "Root",
            "Spine1",
        )
        full_paths = all(item.path.startswith("|") for item in valid_snapshot.joints)

        branch_a = cmds.createNode("joint", name="BranchA", parent=root)
        branch_b = cmds.createNode("joint", name="BranchB", parent=root)
        cmds.createNode("joint", name="Finger", parent=branch_a)
        cmds.createNode("joint", name="Finger", parent=branch_b)
        cmds.createNode("joint", name="Extra_Root", parent=container)
        intermediary = cmds.createNode(
            "transform", name="IntermediateGroup", parent=root
        )
        cmds.createNode("joint", name="Leaf", parent=intermediary)

        cmds.file(modified=False)
        invalid_audit = inspector.execute(container)
        invalid_codes = {issue.code for issue in invalid_audit.issues}
        expected_invalid = {
            "root_count",
            "duplicate_short_name",
            "underscore_in_name",
            "non_joint_parent",
        }
        invalid_reported = expected_invalid.issubset(invalid_codes)
        invalid_capture_clean = not bool(cmds.file(query=True, modified=True))

        cmds.delete(container)
        remaining = cmds.ls("PortableFitSkeleton", long=True) or []
        passed = all(
            (
                valid_audit.valid,
                stable_order,
                full_paths,
                capture_clean,
                invalid_reported,
                invalid_capture_clean,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_hierarchy_preflight",
            "joint_count": len(valid_snapshot.joints),
            "valid_hierarchy": valid_audit.valid,
            "stable_parent_first_order": stable_order,
            "full_dag_paths": full_paths,
            "valid_capture_did_not_modify_scene": capture_clean,
            "invalid_issue_codes": sorted(invalid_codes),
            "invalid_hierarchy_reported": invalid_reported,
            "invalid_capture_did_not_modify_scene": invalid_capture_clean,
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
