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

        from adv_py.adapters import MayaMocapSourceReader
        from adv_py.application import InspectMocapSource

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.namespace(add="TakeA")
        root = cmds.createNode("joint", name="TakeA:Hips", skipSelect=True)
        spine = cmds.createNode("joint", name="TakeA:Spine", parent=root, skipSelect=True)
        chest = cmds.createNode("joint", name="TakeA:Chest", parent=spine, skipSelect=True)
        neck = cmds.createNode("joint", name="TakeA:Neck", parent=chest, skipSelect=True)
        head = cmds.createNode("joint", name="TakeA:Head", parent=neck, skipSelect=True)
        marker = cmds.createNode("transform", name="MocapInspectionSelection", skipSelect=True)
        for frame, hips_x, hips_yaw, spine_pitch in (
            (1, 0.0, 0.0, 0.0),
            (10, 5.0, 35.0, 12.0),
            (20, 12.0, 80.0, -8.0),
        ):
            cmds.setKeyframe(root, attribute="translateX", time=frame, value=hips_x)
            cmds.setKeyframe(root, attribute="rotateY", time=frame, value=hips_yaw)
            cmds.setKeyframe(spine, attribute="rotateX", time=frame, value=spine_pitch)
        cmds.currentTime(10, edit=True, update=True)
        cmds.select(marker, replace=True)

        host = MayaMocapSourceReader()
        use_case = InspectMocapSource(host)
        before_nodes = tuple(cmds.ls(long=True) or [])
        before_selection = tuple(cmds.ls(selection=True, long=True) or [])
        before_time = float(cmds.currentTime(query=True))
        before_modified = bool(cmds.file(query=True, modified=True))
        before_undo = str(cmds.undoInfo(query=True, undoName=True) or "")

        inspection = use_case.execute("|TakeA:Hips")
        summary = inspection.require_valid()

        after_nodes = tuple(cmds.ls(long=True) or [])
        read_only_preserved = (
            after_nodes == before_nodes
            and tuple(cmds.ls(selection=True, long=True) or []) == before_selection
            and abs(float(cmds.currentTime(query=True)) - before_time) < 1e-9
            and bool(cmds.file(query=True, modified=True)) == before_modified
            and str(cmds.undoInfo(query=True, undoName=True) or "") == before_undo
        )

        driver = cmds.createNode("multiplyDivide", name="UnsafeMocapDriver")
        cmds.connectAttr(f"{driver}.outputX", f"{head}.rotateZ", force=True)
        unsafe = use_case.execute("|TakeA:Hips")
        unsafe_codes = {issue.code for issue in unsafe.issues}
        checks = {
            "valid_source_accepted": inspection.valid,
            "namespace_detected": summary.namespace == "TakeA",
            "five_joint_hierarchy": summary.joint_count == 5,
            "portable_names_are_path_free": summary.portable_joint_names == (
                "Hips", "Spine", "Chest", "Neck", "Head"
            ),
            "three_direct_animation_channels": summary.channel_count == 3,
            "two_animated_joints": summary.animated_joint_count == 2,
            "clip_range_detected": (
                summary.start_time == 1.0 and summary.end_time == 20.0
            ),
            "non_curve_driver_detected": "unsupported_driver" in unsafe_codes,
            "inspection_is_read_only": read_only_preserved,
        }

        cmds.file(new=True, force=True)
        checks["scene_cleanup"] = not (cmds.ls("TakeA:*", long=True) or [])
        passed = all(checks.values())
        result = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "mocap_source_inspection",
            **checks,
            "joint_count": summary.joint_count,
            "channel_count": summary.channel_count,
            "start_time": summary.start_time,
            "end_time": summary.end_time,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if passed else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if passed else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
