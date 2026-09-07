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
        from adv_py.application import EditJointLabels
        from adv_py.core import JointLabelValidationError

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        root = cmds.createNode("joint", name="PortableLabelRoot_JNT")
        child = cmds.createNode("joint", name="PortableLabelChest_JNT", parent=root)
        not_a_joint = cmds.createNode("transform", name="PortableLabel_NOT_JOINT")
        labels = EditJointLabels(MayaFitJointHost())

        labels.apply((root,), "Hip")
        labels.apply((child,), "Chest")
        built_in_ok = (
            cmds.getAttr(f"{root}.drawLabel")
            and cmds.getAttr(f"{root}.type") == 2
            and labels.read(root).text == "Hip"
        )
        custom_ok = (
            cmds.getAttr(f"{child}.drawLabel")
            and cmds.getAttr(f"{child}.type") == 18
            and cmds.getAttr(f"{child}.otherType") == "Chest"
            and labels.read(child).text == "Chest"
        )

        before_failed_preflight = cmds.getAttr(f"{root}.type")
        preflight_blocked = False
        try:
            labels.apply((root, not_a_joint), "Root")
        except JointLabelValidationError:
            preflight_blocked = True
        no_partial_change = cmds.getAttr(f"{root}.type") == before_failed_preflight

        labels.apply((root,), "Root")
        cmds.undo()
        undo_restored = labels.read(root).text == "Hip"

        labels.clear((child,))
        clear_ok = labels.read(child) is None

        cmds.delete(root, not_a_joint)
        remaining = cmds.ls("PortableLabel*") or []
        passed = all(
            (
                built_in_ok,
                custom_ok,
                preflight_blocked,
                no_partial_change,
                undo_restored,
                clear_ok,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_joint_labels",
            "built_in_label": built_in_ok,
            "custom_label": custom_ok,
            "preflight_blocked": preflight_blocked,
            "no_partial_change": no_partial_change,
            "single_undo_restored": undo_restored,
            "clear_label": clear_ok,
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
