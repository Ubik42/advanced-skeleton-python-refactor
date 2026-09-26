"""Export original Fit to a new scene, then build a registered character."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


def main(scene: Path, report: Path) -> int:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.application.external_fit_export import ExportExternalFitSkeleton
        from adv_py.application.fit_skeleton_io import (
            CreateAndImportFitSkeleton, ExportFitSkeleton)
        from adv_py.application.registered_body_build import (
            BuildRegisteredBodyCharacter)
        from adv_py.core.fit_skeleton_io import fit_skeleton_documents_match

        cmds.file(new=True, force=True)
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(fits) != 1:
            raise ValueError("原版场景需要唯一 FitSkeleton")
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "sam.fit.json"
            exported = ExportExternalFitSkeleton(
                MayaBodyBuildHost()).apply(document, fits[0])
            cmds.file(new=True, force=True)
            cmds.upAxis(axis=exported.document.up_axis.value,
                        rotateView=False)
            host = MayaBodyBuildHost()
            imported = CreateAndImportFitSkeleton(host).apply(document)
            roundtrip = ExportFitSkeleton(host).plan(
                Path(directory) / "roundtrip.fit.json")
            source_root = next(joint for joint in exported.document.joints
                               if joint.name == "Root")
            target_root = next(joint for joint in roundtrip.document.joints
                               if joint.name == "Root")
            result = BuildRegisteredBodyCharacter(host).apply(
                imported.verified.container.path)
            data = {
                "source": scene.name,
                "export_joint_count": len(exported.document.joints),
                "inferred_label_count": len(exported.inferred_labels),
                "import_joint_count": len(imported.joint_paths),
                "document_matches": fit_skeleton_documents_match(
                    exported.document, roundtrip.document),
                "root_offset_matches": all(abs(a - b) < 1e-6
                    for a, b in zip(source_root.local_position,
                                    target_root.local_position)),
                "registered_body_count": len(result.registration.body),
                "hand_control_count": len(
                    result.rig.hand.snapshot.controls)
                    if result.rig.hand is not None else 0,
            }
            cmds.undo()
            data["single_undo_removed_character"] = not (
                cmds.ls("Root_M", type="joint", long=True) or ())
            data["imported_fit_survives_undo"] = len(
                host.capture_fit_hierarchy("FitSkeleton").joints) == 41
            cmds.redo()
            output = Path(directory) / "roundtrip.mb"
            cmds.file(rename=str(output))
            cmds.file(save=True, type="mayaBinary")
            cmds.file(str(output), open=True, force=True,
                      executeScriptNodes=False)
            data["reopen_body_count"] = len(
                MayaBodyBuildHost().capture_body_skeleton("Root_M").joints)
            cmds.file(new=True, force=True)
        data["status"] = "passed" if (
            data["export_joint_count"] == 41
            and data["inferred_label_count"] == 30
            and data["import_joint_count"] == 41
            and data["document_matches"]
            and data["root_offset_matches"]
            and data["registered_body_count"] == 74
            and data["hand_control_count"] == 30
            and data["single_undo_removed_character"]
            and data["imported_fit_survives_undo"]
            and data["reopen_body_count"] == 74) else "failed"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, ensure_ascii=False,
                                     indent=2) + "\n", encoding="utf-8")
        return 0 if data["status"] == "passed" else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
