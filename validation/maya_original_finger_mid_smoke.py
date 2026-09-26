"""Build finger midpoint influences on the public sam Fit in Maya."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(scene: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.adapters.maya_finger_mid import MayaFingerMidHost
        from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
        from adv_py.application.finger_mid_deform import BuildFingerMidDeform
        from adv_py.application.character_registry import ResolveBodyCharacter

        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(fits) != 1:
            raise ValueError("原版场景需要唯一 FitSkeleton")
        original = {name: tuple(cmds.xform(name, query=True,
            worldSpace=True, translation=True)) for name in
            (f"{finger}Finger3_{side}_50" for side in ("R", "L") for finger in
             ("Thumb", "Index", "Middle", "Ring", "Pinky"))}
        original_rest_matrix = {name: tuple(cmds.xform(name, query=True,
            worldSpace=True, matrix=True)) for name in original}
        original_tip_rest_matrix = {name: tuple(cmds.xform(
            name.removesuffix("_50"), query=True, worldSpace=True,
            matrix=True)) for name in original}
        original_body_frames = {path.rsplit("|", 1)[-1]: tuple(cmds.xform(
            path, query=True, worldSpace=True, matrix=True)) for path in
            cmds.ls(type="joint", long=True) or []}
        original_posed = {}
        original_tip_posed = {}
        for name in original:
            control = "FK" + name.removesuffix("_50")
            cmds.setAttr(control + ".rotateX", 12.0)
            original_posed[name] = tuple(cmds.xform(name, query=True,
                worldSpace=True, matrix=True))
            original_tip_posed[name] = tuple(cmds.xform(
                name.removesuffix("_50"), query=True,
                worldSpace=True, matrix=True))
            cmds.setAttr(control + ".rotateX", 0.0)
        parent = (cmds.listRelatives(fits[0], parent=True, fullPath=True)
                  or [""])[0]
        cmds.delete(tuple(path for path in (cmds.listRelatives(
            parent, children=True, fullPath=True) or ()) if path != fits[0]))
        built = BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
            fits[0], infer_missing_labels=True)
        body_frame_errors = {item.path.rsplit("|", 1)[-1]: max(
            abs(a - b) for a, b in zip(
                original_body_frames[item.path.rsplit("|", 1)[-1]],
                cmds.xform(item.path, query=True, worldSpace=True,
                           matrix=True))) for item in built.registration.body
            if item.path.rsplit("|", 1)[-1] in original_body_frames}
        unmatched_body_names = sorted(item.path.rsplit("|", 1)[-1]
            for item in built.registration.body
            if item.path.rsplit("|", 1)[-1] not in original_body_frames)
        specs = BuildFingerMidDeform(MayaFingerMidHost()).apply()
        maximum_position_error = max(max(abs(a - b) for a, b in zip(
            original[spec.name], cmds.xform(spec.path, query=True,
                worldSpace=True, translation=True))) for spec in specs)
        rest_errors = {spec.name: max(abs(a - b) for a, b in zip(
            original_rest_matrix[spec.name], cmds.xform(spec.path,
                query=True, worldSpace=True, matrix=True))) for spec in specs}
        tip_rest_errors = {spec.name: max(abs(a - b) for a, b in zip(
            original_tip_rest_matrix[spec.name], cmds.xform(spec.tip,
                query=True, worldSpace=True, matrix=True))) for spec in specs}
        data = {"source": scene.name, "body_count": len(built.registration.body),
                "finger_mid_count": len(specs),
                "maximum_original_position_error": maximum_position_error,
                "body_comparison_count": len(body_frame_errors),
                "unmatched_body_names": unmatched_body_names,
                "body_frame_errors": body_frame_errors,
                "original_rest_errors": rest_errors,
                "original_tip_rest_errors": tip_rest_errors}
        cmds.undo()
        data["undo_removed_helpers"] = all(not cmds.objExists(spec.path)
                                            for spec in specs)
        cmds.redo()
        data["redo_restored_helpers"] = all(cmds.objExists(spec.path)
                                            for spec in specs)
        hand = built.rig.hand.snapshot.controls
        pose_errors = {}
        tip_pose_errors = {}
        motion_count = 0
        for spec in specs:
            control = next(item.control_path for item in hand
                           if item.driven_joint == spec.tip)
            before = tuple(cmds.xform(spec.path, query=True,
                worldSpace=True, matrix=True))
            cmds.setAttr(control + ".rotateX", 12.0)
            posed = tuple(cmds.xform(spec.path, query=True,
                worldSpace=True, matrix=True))
            if max(abs(a - b) for a, b in zip(before[:12], posed[:12])) > 1e-4:
                motion_count += 1
            pose_errors[spec.name] = max(abs(a - b) for a, b in zip(
                original_posed[spec.name], posed))
            tip_posed = tuple(cmds.xform(spec.tip, query=True,
                worldSpace=True, matrix=True))
            tip_pose_errors[spec.name] = max(abs(a - b) for a, b in zip(
                original_tip_posed[spec.name], tip_posed))
            cmds.setAttr(control + ".rotateX", 0.0)
        data["finger_mid_control_motion_count"] = motion_count
        data["original_pose_errors"] = pose_errors
        data["original_tip_pose_errors"] = tip_pose_errors
        data["maximum_original_pose_matrix_error"] = max(pose_errors.values())
        data["maximum_original_tip_pose_error"] = max(tip_pose_errors.values())
        data["maximum_original_body_frame_error"] = max(body_frame_errors.values())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "finger-mid.mb"
            cmds.file(rename=str(output))
            cmds.file(save=True, type="mayaBinary")
            cmds.file(str(output), open=True, force=True,
                      executeScriptNodes=False)
            data["reopen_helper_count"] = sum(bool(cmds.objExists(spec.path))
                                              for spec in specs)
            resolver = ResolveBodyCharacter(MayaBodyBuildHost())
            names = resolver.discover()
            data["registration_body_count"] = len(resolver.execute(names[0]).body)
        data["status"] = "passed" if (
            data["body_count"] == 74 and data["body_comparison_count"] == 68
            and data["finger_mid_count"] == 10
            and data["maximum_original_position_error"] < 0.02
            and data["finger_mid_control_motion_count"] == 10
            and data["maximum_original_body_frame_error"] < 1e-5
            and data["maximum_original_tip_pose_error"] < 1e-5
            and data["maximum_original_pose_matrix_error"] < 0.005
            and data["undo_removed_helpers"] and data["redo_restored_helpers"]
            and data["reopen_helper_count"] == 10
            and data["registration_body_count"] == 74) else "failed"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        return 0 if data["status"] == "passed" else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
