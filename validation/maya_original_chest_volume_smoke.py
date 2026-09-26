"""Compare four chest/scapula SDK influences with the public sam rig."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def matrix(cmds, path):
    return tuple(cmds.xform(path, query=True, worldSpace=True, matrix=True))


def main(scene: Path, guide_file: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.adapters.maya_sdk_volume import MayaSdkVolumeHost
        from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
        from adv_py.application.chest_volume_deform import BuildChestVolumeDeform
        from adv_py.application.character_registry import ResolveBodyCharacter

        guide = json.loads(guide_file.read_text(encoding="utf-8"))
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(fits) != 1:
            raise ValueError("原版场景需要唯一 FitSkeleton")
        names = [f"{stem}Joint_{side}" for side in ("R", "L")
                 for stem in ("ChestA", "ScapulaA")]
        original_rest = {name: matrix(cmds, name) for name in names}
        original_pose = {}
        original_driver = {}
        for side in ("R", "L"):
            control = "FKScapula_" + side
            for axis in ("Y", "Z"):
                cmds.setAttr(control + ".rotate" + axis, 12.0)
                original_pose[side + axis] = {name: matrix(cmds, name)
                    for name in names if name.endswith("_" + side)}
                original_driver[side + axis] = tuple(cmds.getAttr(
                    "Scapula_" + side + ".rotate")[0])
                cmds.setAttr(control + ".rotate" + axis, 0.0)
        fit_parent = (cmds.listRelatives(fits[0], parent=True,
                                        fullPath=True) or [""])[0]
        cmds.delete(tuple(path for path in (cmds.listRelatives(
            fit_parent, children=True, fullPath=True) or ()) if path != fits[0]))
        built = BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
            fits[0], infer_missing_labels=True)
        wrong_guide = dict(guide)
        wrong_frames = dict(guide["body_world_matrices"])
        wrong_chest = list(wrong_frames["Chest_M"])
        wrong_chest[12] += 1.0
        wrong_frames["Chest_M"] = wrong_chest
        wrong_guide["body_world_matrices"] = wrong_frames
        mismatched_guide_rejected = False
        try:
            BuildChestVolumeDeform(MayaSdkVolumeHost()).apply(wrong_guide)
        except ValueError:
            mismatched_guide_rejected = all(not cmds.objExists(name)
                                            for name in names)

        class FaultHost(MayaSdkVolumeHost):
            calls = 0

            def create_sdk_volume_joint(self, spec):
                super().create_sdk_volume_joint(spec)
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("injected fault")

        fault_rolled_back = False
        try:
            BuildChestVolumeDeform(FaultHost()).apply(guide)
        except RuntimeError as exc:
            fault_rolled_back = str(exc) == "injected fault" and all(
                not cmds.objExists(name) for name in names)
        specs = BuildChestVolumeDeform(MayaSdkVolumeHost()).apply(guide)
        rest_errors = {spec.name: max(abs(a - b) for a, b in zip(
            original_rest[spec.name], matrix(cmds, spec.path))) for spec in specs}
        cmds.undo()
        undo_removed = all(not cmds.objExists(spec.path) for spec in specs)
        cmds.redo()
        redo_restored = all(cmds.objExists(spec.path) for spec in specs)
        control_names = [item.control_name for item in
                         built.rig.plan.torso.torso.controls.controls]
        pose_errors = {}
        new_driver = {}
        for side in ("R", "L"):
            control = "AdvPy_TorsoScapula_" + side + "FK"
            for axis in ("Y", "Z"):
                cmds.setAttr(control + ".rotate" + axis, 12.0)
                key = side + axis
                new_driver[key] = tuple(cmds.getAttr(
                    "Scapula_" + side + ".rotate")[0])
                pose_errors[key] = {spec.name: max(abs(a - b)
                    for a, b in zip(original_pose[key][spec.name],
                                    matrix(cmds, spec.path)))
                    for spec in specs if spec.driver_name.endswith("_" + side)}
                cmds.setAttr(control + ".rotate" + axis, 0.0)
        data = {"source": scene.name, "count": len(specs),
                "rest_errors": rest_errors,
                "mismatched_guide_rejected": mismatched_guide_rejected,
                "fault_rolled_back": fault_rolled_back,
                "undo_removed": undo_removed,
                "redo_restored": redo_restored,
                "original_driver": original_driver,
                "new_driver": new_driver,
                "pose_errors": pose_errors,
                "torso_control_names": control_names}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "chest_volume.ma"
            cmds.file(rename=str(path))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(str(path), open=True, force=True,
                      executeScriptNodes=False)
            data["save_reopen_retained"] = all(cmds.objExists(spec.path)
                                               for spec in specs)
            data["registered_body_count"] = len(
                ResolveBodyCharacter(MayaBodyBuildHost()).execute().body)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if (len(specs) != 4 or max(rest_errors.values()) > 1e-4
                or max(max(errors.values()) for errors in pose_errors.values()) > 1e-4
                or not all((mismatched_guide_rejected, fault_rolled_back,
                            undo_removed, redo_restored,
                            data["save_reopen_retained"]))
                or data["registered_body_count"] != 74):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                          Path(sys.argv[3])))
