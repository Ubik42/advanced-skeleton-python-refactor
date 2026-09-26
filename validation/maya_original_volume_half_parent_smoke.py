"""Compare rebuilt _00/_50 volume-parent helpers against public sam."""
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
        from adv_py.adapters.maya_limb_part import MayaLimbPartHost
        from adv_py.adapters.maya_volume_half_parent import MayaVolumeHalfParentHost
        from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
        from adv_py.application.limb_part_deform import BuildLimbPartDeform
        from adv_py.application.volume_half_parent import BuildVolumeHalfParents
        from adv_py.application.character_registry import ResolveBodyCharacter

        guide = json.loads(guide_file.read_text(encoding="utf-8"))
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(fits) != 1:
            raise ValueError("原版场景需要唯一 FitSkeleton")
        names = [f"{stem}_{side}_50" for side in ("R", "L")
                 for stem in ("Shoulder", "Elbow", "Wrist", "Hip",
                              "Knee", "Ankle")]
        original_rest = {name: matrix(cmds, name) for name in names}
        cases = (("Shoulder", "Y", 12.0), ("Elbow", "Z", 12.0),
                 ("Wrist", "Y", 12.0), ("Hip", "Y", 12.0),
                 ("Knee", "Z", -110.0), ("Ankle", "Z", 12.0))
        original_pose, original_motion = {}, {}
        for side in ("R", "L"):
            for stem, axis, value in cases:
                name = f"{stem}_{side}_50"
                control = f"FK{stem}_{side}"
                cmds.setAttr(control + ".rotate" + axis, value)
                original_pose[name] = matrix(cmds, name)
                original_motion[name] = max(abs(a - b) for a, b in zip(
                    original_rest[name], original_pose[name]))
                cmds.setAttr(control + ".rotate" + axis, 0.0)
        fit_parent = (cmds.listRelatives(fits[0], parent=True,
                                        fullPath=True) or [""])[0]
        cmds.delete(tuple(path for path in (cmds.listRelatives(
            fit_parent, children=True, fullPath=True) or ()) if path != fits[0]))
        built = BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
            fits[0], infer_missing_labels=True)
        BuildLimbPartDeform(MayaLimbPartHost()).apply()
        wrong_guide = dict(guide)
        wrong_rows = [dict(row) for row in guide["joints"]]
        wrong_row = next(row for row in wrong_rows
                         if row["parent"] == "Shoulder_R_50")
        wrong_helper = dict(wrong_row["parent_node"])
        wrong_parent = list(wrong_helper["parent_world_matrix"])
        wrong_parent[12] += 1.0
        wrong_helper["parent_world_matrix"] = wrong_parent
        wrong_row["parent_node"] = wrong_helper
        wrong_guide["joints"] = wrong_rows
        mismatch_rejected = False
        try:
            BuildVolumeHalfParents(MayaVolumeHalfParentHost()).apply(wrong_guide)
        except ValueError:
            mismatch_rejected = all(not cmds.objExists(name) for name in names)

        class FaultHost(MayaVolumeHalfParentHost):
            calls = 0

            def create_volume_half_parent(self, spec):
                super().create_volume_half_parent(spec)
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("injected fault")

        fault_rolled_back = False
        try:
            BuildVolumeHalfParents(FaultHost()).apply(guide)
        except RuntimeError as exc:
            fault_rolled_back = str(exc) == "injected fault" and all(
                not cmds.objExists(name) for name in names)
        specs = BuildVolumeHalfParents(MayaVolumeHalfParentHost()).apply(guide)
        rest_errors = {spec.name: max(abs(a - b) for a, b in zip(
            original_rest[spec.name], matrix(cmds, spec.path))) for spec in specs}
        cmds.undo()
        undo_removed = all(not cmds.objExists(spec.path) for spec in specs)
        cmds.redo()
        redo_restored = all(cmds.objExists(spec.path) for spec in specs)
        pose_errors = {}
        for side in ("R", "L"):
            for stem, axis, value in cases:
                name = f"{stem}_{side}_50"
                spec = next(item for item in specs if item.name == name)
                control = f"AdvPy_{stem}FK_{side}"
                cmds.setAttr(control + ".rotate" + axis, value)
                pose_errors[name] = max(abs(a - b) for a, b in zip(
                    original_pose[name], matrix(cmds, spec.path)))
                cmds.setAttr(control + ".rotate" + axis, 0.0)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "volume_half_parents.ma"
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
        if (len(specs) != 12 or max(rest_errors.values()) > 1e-4
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
                          Path(sys.argv[3])))
