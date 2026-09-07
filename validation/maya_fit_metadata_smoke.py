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
        from adv_py.application import InspectFitJoints
        from adv_py.core import FitJointValidationError

        cmds.file(new=True, force=True)
        valid_joint = cmds.createNode("joint", name="PortableFitMetaValid_JNT")
        invalid_joint = cmds.createNode("joint", name="PortableFitMetaInvalid_JNT")
        not_a_joint = cmds.createNode("transform", name="PortableFitMeta_NOT_JOINT")

        cmds.addAttr(
            valid_joint, longName="twistJoints", attributeType="long", defaultValue=2
        )
        cmds.addAttr(
            valid_joint, longName="bendyCtrls", attributeType="long", defaultValue=1
        )
        cmds.addAttr(
            valid_joint, longName="noMirror", attributeType="bool", defaultValue=True
        )
        cmds.addAttr(
            valid_joint,
            longName="noMirrorLeft",
            attributeType="bool",
            defaultValue=True,
        )
        cmds.addAttr(
            valid_joint,
            longName="worldOrientUp",
            attributeType="enum",
            enumName="xUp:yUp:zUp:xDown:yDown:zDown",
            defaultValue=1,
        )
        cmds.addAttr(
            valid_joint,
            longName="ikLocal",
            attributeType="enum",
            enumName="addCtrl:nonZero:localOrient",
            defaultValue=2,
        )
        cmds.addAttr(
            invalid_joint,
            longName="twistJoints",
            attributeType="long",
            defaultValue=2,
        )
        cmds.addAttr(
            invalid_joint,
            longName="inbetweenJoints",
            attributeType="long",
            defaultValue=2,
        )

        inspector = InspectFitJoints(MayaFitJointHost())
        cmds.file(modified=False)
        valid_audit = inspector.execute((valid_joint,))
        valid_data = valid_audit.joints[0]
        values_read = (
            valid_data.twist_joints == 2
            and valid_data.bendy_controls == 1
            and valid_data.no_mirror
            and valid_data.no_mirror_left
            and valid_data.world_orient_up == "yUp"
            and valid_data.ik_local_mode == "localOrient"
        )

        invalid_audit = inspector.execute((invalid_joint,))
        conflict_reported = {
            issue.code for issue in invalid_audit.issues
        } == {"mixed_subdivision_modes"}

        preflight_blocked = False
        try:
            inspector.execute((valid_joint, not_a_joint))
        except FitJointValidationError:
            preflight_blocked = True
        scene_mutated = bool(cmds.file(query=True, modified=True))

        cmds.delete(valid_joint, invalid_joint, not_a_joint)
        remaining = cmds.ls("PortableFitMeta*") or []
        passed = all(
            (
                valid_audit.valid,
                values_read,
                conflict_reported,
                preflight_blocked,
                not scene_mutated,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_joint_metadata",
            "valid_profile": valid_audit.valid,
            "values_read": values_read,
            "conflict_reported": conflict_reported,
            "preflight_blocked": preflight_blocked,
            "scene_mutated_by_inspection": scene_mutated,
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
