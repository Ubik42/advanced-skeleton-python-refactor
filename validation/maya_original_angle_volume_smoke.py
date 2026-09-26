"""Compare 22 angle-driven weighted influences with the public sam rig."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def matrix(cmds, path):
    return tuple(cmds.xform(path, query=True, worldSpace=True, matrix=True))


CASES = {"Hip": {"Y": ("A", "B"), "Z": ("C", "D")},
         "Shoulder": {"Y": ("A",)},
         "Wrist": {"Y": ("A", "B"), "Z": ("C", "D")},
         "Ankle": {"Z": ("A", "B")}}


def main(scene: Path, volume_file: Path, angle_file: Path,
         report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.adapters.maya_limb_part import MayaLimbPartHost
        from adv_py.adapters.maya_volume_half_parent import MayaVolumeHalfParentHost
        from adv_py.adapters.maya_angle_sampler import MayaAngleSamplerHost
        from adv_py.adapters.maya_sdk_volume import MayaSdkVolumeHost
        from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
        from adv_py.application.limb_part_deform import BuildLimbPartDeform
        from adv_py.application.volume_half_parent import BuildVolumeHalfParents
        from adv_py.application.angle_sampler_deform import BuildAngleSamplers
        from adv_py.application.angle_volume_deform import BuildAngleVolumeDeform
        from adv_py.application.character_registry import ResolveBodyCharacter

        volume_guide = json.loads(volume_file.read_text(encoding="utf-8"))
        angle_guide = json.loads(angle_file.read_text(encoding="utf-8"))
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(fits) != 1:
            raise ValueError("原版场景需要唯一 FitSkeleton")
        names = [f"{stem}{letter}Joint_{side}"
                 for side in ("R", "L") for stem, axes in CASES.items()
                 for letters in axes.values() for letter in letters]
        original_rest = {name: matrix(cmds, name) for name in names}
        original_pose, original_motion = {}, {}
        for side in ("R", "L"):
            for stem, axes in CASES.items():
                for axis, letters in axes.items():
                    control = f"FK{stem}_{side}"
                    for amount in (-30.0, 30.0):
                        cmds.setAttr(control + ".rotate" + axis, amount)
                        for letter in letters:
                            name = f"{stem}{letter}Joint_{side}"
                            key = f"{name}:{axis}{amount:+g}"
                            original_pose[key] = matrix(cmds, name)
                            original_motion[key] = max(abs(a - b)
                                for a, b in zip(original_rest[name],
                                                original_pose[key]))
                    cmds.setAttr(control + ".rotate" + axis, 0.0)
        fit_parent = (cmds.listRelatives(fits[0], parent=True,
                                        fullPath=True) or [""])[0]
        cmds.delete(tuple(path for path in (cmds.listRelatives(
            fit_parent, children=True, fullPath=True) or ()) if path != fits[0]))
        built = BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
            fits[0], infer_missing_labels=True)
        BuildLimbPartDeform(MayaLimbPartHost()).apply()
        BuildVolumeHalfParents(MayaVolumeHalfParentHost()).apply(volume_guide)
        BuildAngleSamplers(MayaAngleSamplerHost()).apply(angle_guide)
        wrong_guide = dict(volume_guide)
        wrong_rows = [dict(row) for row in volume_guide["joints"]]
        wrong_row = next(row for row in wrong_rows
                         if row["name"] == "HipAJoint_R")
        wrong_parent = list(wrong_row["parent_world_matrix"])
        wrong_parent[12] += 1.0
        wrong_row["parent_world_matrix"] = wrong_parent
        wrong_guide["joints"] = wrong_rows
        mismatch_rejected = False
        try:
            BuildAngleVolumeDeform(MayaSdkVolumeHost()).apply(wrong_guide)
        except ValueError:
            mismatch_rejected = all(not cmds.objExists(name) for name in names)

        class FaultHost(MayaSdkVolumeHost):
            calls = 0

            def create_sdk_volume_joint(self, spec):
                super().create_sdk_volume_joint(spec)
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("injected fault")

        fault_rolled_back = False
        try:
            BuildAngleVolumeDeform(FaultHost()).apply(volume_guide)
        except RuntimeError as exc:
            fault_rolled_back = str(exc) == "injected fault" and all(
                not cmds.objExists(name) for name in names)
        specs = BuildAngleVolumeDeform(MayaSdkVolumeHost()).apply(volume_guide)
        by_name = {spec.name: spec for spec in specs}
        rest_errors = {name: max(abs(a - b) for a, b in zip(
            original_rest[name], matrix(cmds, by_name[name].path)))
            for name in names}
        cmds.undo()
        undo_removed = all(not cmds.objExists(spec.path) for spec in specs)
        cmds.redo()
        redo_restored = all(cmds.objExists(spec.path) for spec in specs)
        pose_errors = {}
        for side in ("R", "L"):
            for stem, axes in CASES.items():
                for axis, letters in axes.items():
                    control = f"AdvPy_{stem}FK_{side}"
                    for amount in (-30.0, 30.0):
                        cmds.setAttr(control + ".rotate" + axis, amount)
                        for letter in letters:
                            name = f"{stem}{letter}Joint_{side}"
                            key = f"{name}:{axis}{amount:+g}"
                            pose_errors[key] = max(abs(a - b) for a, b in zip(
                                original_pose[key], matrix(cmds, by_name[name].path)))
                    cmds.setAttr(control + ".rotate" + axis, 0.0)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "angle_volume.ma"
            cmds.file(rename=str(path))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(str(path), open=True, force=True,
                      executeScriptNodes=False)
            reopened = all(cmds.objExists(spec.path) for spec in specs)
            registered = len(ResolveBodyCharacter(MayaBodyBuildHost()).execute().body)
        data = {"source": scene.name, "count": len(specs),
                "rest_errors": rest_errors, "pose_errors": pose_errors,
                "original_motion": original_motion,
                "mismatch_rejected": mismatch_rejected,
                "fault_rolled_back": fault_rolled_back,
                "undo_removed": undo_removed, "redo_restored": redo_restored,
                "save_reopen_retained": reopened,
                "registered_body_count": registered}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if (len(specs) != 22 or max(rest_errors.values()) > 1e-4
                or max(pose_errors.values()) > 1e-4
                or min(original_motion.values()) < 1e-3
                or not all((mismatch_rejected, fault_rolled_back,
                            undo_removed, redo_restored, reopened))
                or registered != 74):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                          Path(sys.argv[3]), Path(sys.argv[4])))
