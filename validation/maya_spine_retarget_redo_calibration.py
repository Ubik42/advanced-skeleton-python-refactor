"""Cross-spine FK take keeps target animation boundaries and evaluates after Redo."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import maya.standalone


def main(folder: Path, source: int, target: int, multi: bool = False) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaMocapControlHost
        from adv_py.application import RetargetCharacterSpineFk

        cmds.file(str(folder / f"spine-{source}-to-{target}-before.ma"),
                  open=True, force=True)
        cmds.undoInfo(state=True)
        presets = {"translateX": (4., 0., 6., 8.)}
        if multi:
            presets.update({"translateY": (-2., 0., 1., 3.),
                            "translateZ": (1., 0., 2., 4.),
                            "rotateX": (15., 0., 5., 25.),
                            "rotateY": (-12., 0., 10., 30.),
                            "rotateZ": (8., 0., 15., 35.)})
        for attribute, values in presets.items():
            plug = "target:AdvPy_Global." + attribute
            for frame, value in zip((0, 1, 10, 11), values):
                cmds.setKeyframe("target:AdvPy_Global", attribute=attribute,
                                 time=frame, value=value)
            curve = cmds.connectionInfo(plug,
                sourceFromDestination=True).split(".", 1)[0]
            cmds.rename(curve, ":target:" + curve.rsplit(":", 1)[-1])
        cmds.currentTime(1, edit=True)
        host = MayaMocapControlHost(namespace="target")
        host.read_character_registration()

        def state() -> dict[str, object]:
            current = cmds.currentTime(query=True)
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                values = {}
                channels = {}
                for frame in (0, 1, 5, 10, 11):
                    cmds.currentTime(frame, edit=True)
                    channels[frame] = {attribute: float(cmds.getAttr(
                        "target:AdvPy_Global." + attribute))
                        for attribute in presets}
                    values[frame] = channels[frame]["translateX"]
                driver = cmds.connectionInfo(
                    "target:AdvPy_Global.translateX", sourceFromDestination=True)
                key_times = cmds.keyframe(driver.split(".", 1)[0],
                                          query=True, timeChange=True) or []
                return dict(values=values, channels=channels,
                            key_times=key_times)
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
        report = dict(source=source, target=target, multi=multi, before=before,
                      after=after, undone=undone, redone=redone)
        def valid_take(row: dict[str, object]) -> bool:
            values = row["values"]
            basic = (abs(values[0] - 4.) < 1e-6 and
                    abs(values[5] - 3.) < 1e-6 and
                    abs(values[10] - 6.) < 1e-6 and
                    abs(values[11] - 8.) < 1e-6)
            if not multi:
                return basic
            channels = row["channels"]
            return basic and all(
                abs(channels[frame][attribute] - expected) < 1e-6
                for attribute, original in presets.items()
                if attribute != "translateX"
                for frame, expected in ((0, original[0]), (5, 0.),
                                        (10, 0.), (11, original[3])))

        checks = dict(undo=undone == before, take=valid_take(after),
                      redo=valid_take(redone))
        report["checks"] = checks
        suffix = "multi-redo-calibration" if multi else "redo-calibration"
        (folder / f"spine-{source}-to-{target}-{suffix}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps(dict(source=source, target=target, multi=multi,
                              checks=checks, frame5=redone["channels"][5]),
                         ensure_ascii=False), flush=True)
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve(), int(sys.argv[2]),
                          int(sys.argv[3]), len(sys.argv) > 4 and
                          sys.argv[4] == "multi"))
