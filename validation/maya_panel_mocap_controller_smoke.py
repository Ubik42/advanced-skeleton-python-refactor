"""Exercise the in-Maya MoCap controller against an external FBX fixture."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(scene: Path, source: Path, mapping: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost
        from adv_py.product.maya_panel_controller import MayaPanelController

        cmds.file(str(scene), open=True, force=True)
        cmds.undoInfo(state=True)
        result = MayaPanelController().mocap_retarget(":", source, mapping,
            "PanelTake", 1, 10, mode="fk")
        registration = MayaFaceHost().read_character_registration()
        global_x = next(channel for channel in registration.channels
                        if channel.key == "global.translateX")
        plug = global_x.node + "." + global_x.attribute
        checks = {
            "external_fbx_imported": result.source_joints == 21
                and result.frames == 10 and cmds.namespace(exists="PanelTake"),
            "control_animated": bool(cmds.keyframe(plug,
                query=True, timeChange=True)),
            "source_root_resolved": result.source_root.startswith("|PanelTake:"),
        }
        report.write_text(json.dumps({**checks,
            "status": "passed" if all(checks.values()) else "failed"},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(*(Path(item) for item in sys.argv[1:5])))
