"""Exercise panel controller against a generated Maya character without UI."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import CreateFitSkeleton, BuildSyntheticBodySourceFit
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(new=True, force=True)
        cmds.upAxis(axis="z", rotateView=False)
        cmds.undoInfo(state=True)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        controller = MayaPanelController()
        with tempfile.TemporaryDirectory(prefix="adv-py-panel-",
                                         dir=report.parent.resolve()) as folder:
            folder = Path(folder)
            fit = folder / "panel.fit.json"
            pose = folder / "panel.pose.json"
            animation = folder / "panel.animation.json"
            fit_count = controller.fit_export(":", fit)
            character = controller.body_build(":")
            roles = controller.characters()
            pose_count = controller.pose_capture(":", pose)
            applied_pose_count = controller.pose_apply(":", pose)
            frame_count = controller.animation_capture(":", animation, 1, 3)
            applied_frames = controller.animation_apply(":", animation)
            checks = {
                "fit_document_written": fit_count == 18 and fit.is_file(),
                "registered_character_discovered": character.registered
                    and character.joint_count == 30
                    and any(entry.namespace == ":" and entry.registered
                            and entry.joint_count == 30 for entry in roles),
                "pose_roundtrip": pose_count == character.channel_count
                    and applied_pose_count == pose_count and pose.is_file(),
                "animation_roundtrip": frame_count == 3
                    and applied_frames == 3 and animation.is_file(),
            }
            payload = {**checks, "status": "passed" if all(checks.values())
                       else "failed"}
            report.write_text(json.dumps(payload, ensure_ascii=False, indent=2)
                              + "\n", encoding="utf-8")
            return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
