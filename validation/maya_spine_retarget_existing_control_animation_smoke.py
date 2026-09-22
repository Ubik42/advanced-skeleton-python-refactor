"""Retarget a full-body FK take over existing spine and shoulder control keys."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import maya.standalone


def main(folder: Path, source: int, target: int) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaMocapControlHost
        from adv_py.application import RetargetCharacterSpineFk

        cmds.file(str(folder / f"spine-{source}-to-{target}-before.ma"),
                  open=True, force=True)
        cmds.undoInfo(state=True)
        host = MayaMocapControlHost(namespace="target")
        registration = host.read_character_registration()
        channels = {row.key: row for row in registration.channels}
        presets = {
            "torso.TorsoSpine1_MFK.rotateZ": (7., 0., 20., 25.),
            "arm.fk.ShoulderFK_R.rotateZ": (-5., 0., 30., 35.),
        }
        plugs = {}
        for key, values in presets.items():
            row = channels[key]
            node = host.scene_address(row.node)
            plug = node + "." + row.attribute
            plugs[key] = plug
            for frame, value in zip((0, 1, 10, 11), values):
                cmds.setKeyframe(node, attribute=row.attribute,
                                 time=frame, value=value)
            curve = cmds.connectionInfo(plug,
                sourceFromDestination=True).split(".", 1)[0]
            cmds.rename(curve, ":target:" + curve.rsplit(":", 1)[-1])
        cmds.currentTime(1, edit=True)
        host.read_character_registration()
        joints = tuple(host.scene_address(row.path) for row in registration.body
                       if row.path.rsplit("|", 1)[-1] in
                       ("Chest_M", "Shoulder_R", "Wrist_R"))
        if len(joints) != 3:
            raise RuntimeError("验收场景缺少胸部、右肩或右腕关节")

        def state():
            current = cmds.currentTime(query=True)
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                values = {}
                matrices = {}
                for frame in (0, 1, 5, 10, 11):
                    cmds.currentTime(frame, edit=True)
                    values[frame] = {key: float(cmds.getAttr(plug))
                                     for key, plug in plugs.items()}
                    if frame in (1, 5, 10):
                        matrices[frame] = tuple(tuple(cmds.xform(joint,
                            query=True, worldSpace=True, matrix=True))
                            for joint in joints)
                times = {key: tuple(cmds.keyframe(
                    cmds.connectionInfo(plug,
                        sourceFromDestination=True).split(".", 1)[0],
                    query=True, timeChange=True) or ())
                    for key, plug in plugs.items()}
                return values, matrices, times
            finally:
                cmds.currentTime(current, edit=True)
                cmds.undoInfo(stateWithoutFlush=True)

        before = state()
        RetargetCharacterSpineFk(host).apply("source", start_frame=1,
                                             end_frame=10, sample_by=1)
        after = state()
        cmds.undo()
        undone = state()
        cmds.redo()
        redone = state()

        def matrix_error(left, right):
            return max(abs(a-b) for frame in (1, 5, 10)
                for old, new in zip(left[frame], right[frame])
                for a,b in zip(old, new))

        checks = dict(
            undo_curves=undone[2] == before[2] and all(
                abs(undone[0][frame][key] - before[0][frame][key]) < 1e-6
                for frame in (0, 1, 5, 10, 11) for key in presets),
            undo_pose=matrix_error(undone[1], before[1]) < 1e-6,
            redo_curves=redone[2] == after[2] and all(
                abs(redone[0][frame][key] - after[0][frame][key]) < 1e-6
                for frame in (0, 1, 5, 10, 11) for key in presets),
            redo_pose=matrix_error(redone[1], after[1]) < 1e-6,
            outside_keys=all(abs(after[0][frame][key] - before[0][frame][key])
                < 1e-6 for frame in (0, 11) for key in presets),
            old_motion_replaced=all(abs(after[0][10][key]
                - before[0][10][key]) > 1. for key in presets),
        )
        report = dict(source=source, target=target, checks=checks,
                      before={str(f): before[0][f] for f in (0, 5, 10, 11)},
                      after={str(f): after[0][f] for f in (0, 5, 10, 11)},
                      redo_pose_max_error=matrix_error(redone[1], after[1]))
        (folder / f"spine-{source}-to-{target}-existing-control-animation.json"
         ).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                      encoding="utf8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve(), int(sys.argv[2]),
                          int(sys.argv[3])))
