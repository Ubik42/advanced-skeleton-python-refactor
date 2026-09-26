"""Compare in-process product guide capture with prior read-only inventories."""
from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(scene: Path, volume_file: Path, angle_file: Path,
         axial_file: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_original_guide_capture import (
            capture_original_guides)

        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
        actual = capture_original_guides(cmds, scene.name)
        expected = tuple(json.loads(path.read_text(encoding="utf-8"))
                         for path in (volume_file, angle_file, axial_file))
        equal = tuple(json.loads(json.dumps(result)) == baseline
                      for result, baseline in zip(
            actual, expected))
        data = {"source": scene.name, "guide_equal": equal,
                "volume_joints": len(actual[0]["joints"]),
                "angle_inputs": len(actual[1]["angles"]),
                "axial_nodes": len(actual[2]["nodes"])}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, indent=2) + "\n",
                          encoding="utf-8")
        if equal != (True, True, True):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(*(Path(value) for value in sys.argv[1:6])))
