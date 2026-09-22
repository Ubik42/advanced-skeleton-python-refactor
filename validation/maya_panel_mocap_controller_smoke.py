"""Exercise the in-Maya MoCap controller against an external FBX fixture."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(scene: Path, source: Path, mapping: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost
        from adv_py.product.maya_panel_controller import MayaPanelController
        from adv_py.application import (load_mocap_mapping_preset,
                                        save_mocap_mapping_preset)

        cmds.file(str(scene), open=True, force=True)
        cmds.undoInfo(state=True)
        stages = []
        result = MayaPanelController().mocap_retarget(":", source, mapping,
            "PanelTake", 1, 10, mode="fk", progress=stages.append)
        character_host = MayaFaceHost()
        registration = character_host.read_character_registration()
        original_pose = character_host.capture_character_pose(registration)
        with TemporaryDirectory(prefix="adv-py-panel-mapping-",
                                dir=report.parent) as folder:
            invalid_mapping = Path(folder) / "invalid.json"
            save_mocap_mapping_preset(replace(load_mocap_mapping_preset(mapping),
                expected_body_joint_count=70), invalid_mapping)
            before_undo = cmds.undoInfo(query=True, undoName=True)
            try:
                MayaPanelController().mocap_retarget(":", source, invalid_mapping,
                    "RejectedTake", 1, 10, mode="fk", progress=stages.append)
            except ValueError:
                rollback_clean = (not cmds.namespace(exists="RejectedTake")
                    and cmds.undoInfo(query=True, undoName=True) == before_undo
                    and character_host.capture_character_pose(registration)
                        == original_pose)
            else:
                rollback_clean = False
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
            "failed_retarget_rolls_back_import": rollback_clean,
            "progress_reports_import_and_rollback": len(stages) == 5
                and "撤销" in stages[-1],
        }
        report.write_text(json.dumps({**checks,
            "status": "passed" if all(checks.values()) else "failed"},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(*(Path(item) for item in sys.argv[1:5])))
