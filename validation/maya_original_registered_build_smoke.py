"""Build the public sample through the registered product use case."""
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
        from adv_py.application.registered_body_build import (
            BuildRegisteredBodyCharacter)

        cmds.file(new=True, force=True)
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(fits) != 1:
            raise ValueError("原版场景需要唯一的 FitSkeleton")
        fit = fits[0]
        host = MayaBodyBuildHost()
        nodes = host.capture_fit_hierarchy(fit).joints
        before = tuple((node.short_name, node.world_position,
                        host.read_joint_label(node.path)) for node in nodes)
        parent = (cmds.listRelatives(fit, parent=True, fullPath=True)
                  or [""])[0]
        siblings = tuple(path for path in (cmds.listRelatives(
            parent, children=True, fullPath=True) or ()) if path != fit)
        cmds.delete(siblings)
        result = BuildRegisteredBodyCharacter(host).apply(
            fit, infer_missing_labels=True)
        built = tuple((node.short_name, node.world_position,
                       host.read_joint_label(node.path))
                      for node in host.capture_fit_hierarchy(fit).joints)
        report_data = {
            "source": scene.name,
            "inferred_labels": len(result.skeleton.plan.build.inferred_labels),
            "body_count": len(result.skeleton.snapshot.joints),
            "registered_body_count": len(result.registration.body),
            "hand_control_count": (
                len(result.rig.hand.snapshot.controls)
                if result.rig.hand is not None else 0),
            "fit_unchanged": before == built,
        }
        cmds.undo()
        report_data["single_undo_removed_character"] = (
            not (cmds.ls("Root_M", long=True, type="joint") or ())
            and not (cmds.ls("AdvPy_CharacterControls", long=True) or ()))
        cmds.redo()
        report_data["redo_restored_character"] = (
            len(cmds.ls("Root_M", long=True, type="joint") or ()) == 1
            and len(cmds.ls("AdvPy_CharacterControls", long=True) or ()) == 1)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "registered-sam.mb"
            cmds.file(rename=str(output))
            cmds.file(save=True, type="mayaBinary")
            cmds.file(str(output), open=True, force=True,
                      executeScriptNodes=False)
            report_data["reopen_body_count"] = len(
                MayaBodyBuildHost().capture_body_skeleton("Root_M").joints)
            cmds.file(new=True, force=True)
        report_data["status"] = "passed" if (
            report_data["inferred_labels"] == 30
            and report_data["body_count"] == 74
            and report_data["registered_body_count"] == 74
            and report_data["hand_control_count"] == 30
            and report_data["fit_unchanged"]
            and report_data["single_undo_removed_character"]
            and report_data["redo_restored_character"]
            and report_data["reopen_body_count"] == 74) else "failed"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(report_data, ensure_ascii=False,
                                     indent=2) + "\n", encoding="utf-8")
        return 0 if report_data["status"] == "passed" else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
