"""Read-only weighted volume joint inventory from an original Maya scene."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(scene: Path, report: Path) -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_original_guide_capture import capture_volume

        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
        data = capture_volume(cmds, scene.name)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, ensure_ascii=False,
                          indent=2) + "\n", encoding="utf-8")
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
