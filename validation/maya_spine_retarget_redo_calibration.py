"""Cross-spine FK take keeps target animation boundaries and evaluates after Redo."""
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
        plug = "target:AdvPy_Global.translateX"
        for frame, value in ((0, 4.), (1, 0.), (10, 6.), (11, 8.)):
            cmds.setKeyframe("target:AdvPy_Global", attribute="translateX",
                             time=frame, value=value)
        curve = cmds.connectionInfo(plug, sourceFromDestination=True).split(".", 1)[0]
        cmds.rename(curve, ":target:" + curve.rsplit(":", 1)[-1])
        cmds.currentTime(1, edit=True)
        host = MayaMocapControlHost(namespace="target")
        host.read_character_registration()

        def state() -> dict[str, object]:
            current = cmds.currentTime(query=True)
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                values = {}
                for frame in (0, 1, 5, 10, 11):
                    cmds.currentTime(frame, edit=True)
                    values[frame] = float(cmds.getAttr(plug))
                driver = cmds.connectionInfo(plug, sourceFromDestination=True)
                key_times = cmds.keyframe(driver.split(".", 1)[0],
                                          query=True, timeChange=True) or []
                return dict(values=values, key_times=key_times)
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
        report = dict(source=source, target=target, before=before,
                      after=after, undone=undone, redone=redone)
        print(json.dumps(report, ensure_ascii=False), flush=True)
        (folder / f"spine-{source}-to-{target}-redo-calibration.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        def valid_take(row: dict[str, object]) -> bool:
            values = row["values"]
            return (abs(values[0] - 4.) < 1e-6 and
                    abs(values[5] - 3.) < 1e-6 and
                    abs(values[10] - 6.) < 1e-6 and
                    abs(values[11] - 8.) < 1e-6)

        return 0 if (undone == before and valid_take(after) and
                     valid_take(redone)) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve(), int(sys.argv[2]),
                          int(sys.argv[3])))
