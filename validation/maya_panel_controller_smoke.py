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
        from adv_py.core import (FacePerformance, FaceShapeKind,
                                 face_performance_to_json)

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
            presets = controller.presets(":", folder)
            applied_preset = controller.preset_apply(":", folder, animation.name)
            cmds.polyPlane(name="FaceNeutral", width=2, height=2,
                           subdivisionsX=1, subdivisionsY=1)
            landmarks = folder / "face-landmarks.json"
            landmarks.write_text(json.dumps({"landmarks": [{"vertex": 0,
                "displacement": [0.5, 0.0, 0.2], "radius": 3.0}]}),
                encoding="utf-8")
            face_vertices = controller.face_generate(":", "|FaceNeutral",
                "smile_R", "expression", "|SmileTarget", landmarks)
            asset = folder / "smile.asset.json"
            exported_deltas = controller.face_asset_export(":", "|FaceNeutral",
                "smile_R", "expression", "|SmileTarget", asset)
            library = folder / "face-library"
            for release in ("1.0.0", "1.1.0", "1.2.0"):
                controller.face_library_add(library, asset, release)
            merged = controller.face_library_merge(library, "smile_R",
                "1.0.0", "1.1.0", "1.2.0", "1.3.0")
            library_export = folder / "smile-merged.json"
            controller.face_library_export(library, "smile_R", "1.3.0",
                                           library_export)
            library_entries = controller.face_library_list(library)
            imported_deltas = controller.face_asset_import(":", "|FaceNeutral",
                asset, "|ImportedSmile")
            specification = folder / "face-build.json"
            specification.write_text(json.dumps({"neutral": "|FaceNeutral",
                "targets": [{"name": "smile_R", "kind": "expression",
                             "mesh": "|SmileTarget"}]}), encoding="utf-8")
            face_channels = controller.face_build(":", specification)
            head = next(joint for joint in cmds.ls(type="joint", long=True)
                        if joint.rsplit("|", 1)[-1] == "Head_M")
            performance = FacePerformance((("smile_R", FaceShapeKind.EXPRESSION),),
                cmds.currentUnit(query=True, time=True),
                ((1, (0.0,)), (3, (1.0,))))
            face_clip = folder / "face-performance.json"
            face_clip.write_text(face_performance_to_json(performance),
                                 encoding="utf-8")
            face_frames = controller.face_performance_apply(":",
                head + "|AdvPy_FaceControls", face_clip)
            stages = []
            rebuilt = controller.body_rebuild(":", "PanelRebuildStage",
                (head + "|AdvPy_FaceControls",), progress=stages.append)
            rebuild_stage_removed = not cmds.namespace(exists="PanelRebuildStage")
            published = controller.publish_fbx(":", folder / "panel.fbx", 1, 3,
                euler_filter=True, progress=stages.append)
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
                "presets_apply": any(entry.filename == animation.name and entry.applicable
                    for entry in presets) and applied_preset == frame_count,
                "face_target_asset_roundtrip": face_vertices == 4
                    and exported_deltas > 0 and imported_deltas == exported_deltas
                    and cmds.objExists("ImportedSmile"),
                "face_library_versions": merged.valid
                    and len(library_entries) == 4
                    and all(entry.valid for entry in library_entries)
                    and library_export.is_file(),
                "face_control_and_animation": face_channels == 1
                    and face_frames == 2
                    and cmds.objExists(head + "|AdvPy_FaceControls"),
                "rebuild_preserves_character": rebuilt.joint_count == character.joint_count
                    and rebuilt.channel_count == character.channel_count
                    and rebuild_stage_removed,
                "fbx_published": published.joints == character.joint_count
                    and published.frames == 3
                    and published.bytes_written > 64
                    and published.euler_filtered_curves == 90
                    and (folder / "panel.fbx").is_file(),
                "long_operation_progress": len(stages) == 6
                    and "Root Motion" in stages[2]
                    and "FBX" in stages[-1],
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
