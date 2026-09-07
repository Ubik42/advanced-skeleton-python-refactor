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
        from adv_py.application import EditFitJointMetadata
        from adv_py.core import FitJointPatch, FitJointValidationError

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        joint = cmds.createNode("joint", name="PortableFitEditArm_JNT")
        cmds.addAttr(
            joint,
            longName="twistJoints",
            attributeType="long",
            minValue=0,
            defaultValue=2,
            keyable=True,
        )
        cmds.addAttr(
            joint,
            longName="bendyCtrls",
            attributeType="long",
            minValue=0,
            defaultValue=1,
            keyable=True,
        )

        host = MayaFitJointHost()
        editor = EditFitJointMetadata(host)
        patch = FitJointPatch.from_values(
            twist_joints=None,
            bendy_controls=None,
            inbetween_joints=3,
            untwister=True,
            no_mirror=True,
            world_orient_up="yUp",
            ik_local_mode="localOrient",
        )

        cmds.file(modified=False)
        preview = editor.plan((joint,), patch)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = editor.apply((joint,), patch)
        verified = result.verified[0]
        values_applied = (
            not cmds.attributeQuery("twistJoints", node=joint, exists=True)
            and not cmds.attributeQuery("bendyCtrls", node=joint, exists=True)
            and cmds.getAttr(f"{joint}.inbetweenJoints") == 3
            and cmds.getAttr(f"{joint}.unTwister")
            and cmds.getAttr(f"{joint}.noMirror")
            and verified.world_orient_up == "yUp"
            and verified.ik_local_mode == "localOrient"
        )
        post_verified = verified == result.plan.after[0]

        before_invalid = host.read_fit_joint_metadata(joint)
        invalid_blocked = False
        try:
            editor.apply(
                (joint,),
                FitJointPatch.from_values(twist_joints=2),
            )
        except FitJointValidationError:
            invalid_blocked = True
        invalid_left_unchanged = host.read_fit_joint_metadata(joint) == before_invalid

        cmds.undo()
        undo_restored = (
            cmds.attributeQuery("twistJoints", node=joint, exists=True)
            and cmds.getAttr(f"{joint}.twistJoints") == 2
            and cmds.attributeQuery("bendyCtrls", node=joint, exists=True)
            and cmds.getAttr(f"{joint}.bendyCtrls") == 1
            and not cmds.attributeQuery("inbetweenJoints", node=joint, exists=True)
            and not cmds.attributeQuery("unTwister", node=joint, exists=True)
            and not cmds.attributeQuery("noMirror", node=joint, exists=True)
            and not cmds.attributeQuery("worldOrientUp", node=joint, exists=True)
            and not cmds.attributeQuery("ikLocal", node=joint, exists=True)
        )

        cmds.delete(joint)
        remaining = cmds.ls("PortableFitEdit*") or []
        passed = all(
            (
                preview_clean,
                len(preview.changes) == 7,
                values_applied,
                post_verified,
                invalid_blocked,
                invalid_left_unchanged,
                undo_restored,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_joint_metadata_edit",
            "preview_change_count": len(preview.changes),
            "preview_did_not_modify_scene": preview_clean,
            "values_applied": values_applied,
            "post_verified": post_verified,
            "invalid_patch_blocked": invalid_blocked,
            "invalid_patch_left_unchanged": invalid_left_unchanged,
            "single_undo_restored": undo_restored,
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
