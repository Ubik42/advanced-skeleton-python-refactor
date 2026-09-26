"""Compare rebuilt angleY/Z locator graphs against public sam.mb."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(scene: Path, guide_file: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.adapters.maya_limb_part import MayaLimbPartHost
        from adv_py.adapters.maya_angle_sampler import MayaAngleSamplerHost
        from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
        from adv_py.application.limb_part_deform import BuildLimbPartDeform
        from adv_py.application.angle_sampler_deform import BuildAngleSamplers
        from adv_py.application.character_registry import ResolveBodyCharacter

        guide = json.loads(guide_file.read_text(encoding="utf-8"))
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(fits) != 1:
            raise ValueError("原版场景需要唯一 FitSkeleton")
        original_rest = {plug: cmds.getAttr(plug)
                         for plug in guide["angles"]}
        original_pose = {}
        for plug in guide["angles"]:
            node, attr = plug.split(".", 1)
            axis = attr[-1]
            control = "FK" + node
            cmds.setAttr(control + ".rotate" + axis, 30.0)
            original_pose[plug] = cmds.getAttr(plug)
            cmds.setAttr(control + ".rotate" + axis, 0.0)
        fit_parent = (cmds.listRelatives(fits[0], parent=True,
                                        fullPath=True) or [""])[0]
        cmds.delete(tuple(path for path in (cmds.listRelatives(
            fit_parent, children=True, fullPath=True) or ()) if path != fits[0]))
        built = BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
            fits[0], infer_missing_labels=True)
        BuildLimbPartDeform(MayaLimbPartHost()).apply()
        wrong_guide = dict(guide)
        wrong_angles = dict(guide["angles"])
        wrong_row = dict(wrong_angles["Hip_R.angleZ"])
        wrong_matrix = list(wrong_row["joint_world_matrix"])
        wrong_matrix[12] += 1.0
        wrong_row["joint_world_matrix"] = wrong_matrix
        wrong_angles["Hip_R.angleZ"] = wrong_row
        wrong_guide["angles"] = wrong_angles
        mismatch_rejected = False
        try:
            BuildAngleSamplers(MayaAngleSamplerHost()).apply(wrong_guide)
        except ValueError:
            mismatch_rejected = all(not cmds.objExists(plug)
                                    for plug in guide["angles"])

        class FaultHost(MayaAngleSamplerHost):
            calls = 0

            def create_angle_sampler(self, spec):
                super().create_angle_sampler(spec)
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("injected fault")

        fault_rolled_back = False
        try:
            BuildAngleSamplers(FaultHost()).apply(guide)
        except RuntimeError as exc:
            fault_rolled_back = str(exc) == "injected fault" and all(
                not cmds.objExists(plug) for plug in guide["angles"])
        specs = BuildAngleSamplers(MayaAngleSamplerHost()).apply(guide)
        rest_errors = {plug: abs(cmds.getAttr(plug) - wanted)
                       for plug, wanted in original_rest.items()}
        cmds.undo()
        undo_removed = all(not cmds.objExists(plug)
                           for plug in guide["angles"])
        cmds.redo()
        redo_restored = all(cmds.objExists(plug)
                            for plug in guide["angles"])
        pose_errors = {}
        for plug in guide["angles"]:
            node, attr = plug.split(".", 1)
            axis = attr[-1]
            control = "AdvPy_" + node.split("_", 1)[0] + "FK_" + node[-1]
            cmds.setAttr(control + ".rotate" + axis, 30.0)
            pose_errors[plug] = abs(cmds.getAttr(plug) - original_pose[plug])
            cmds.setAttr(control + ".rotate" + axis, 0.0)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "angle_samplers.ma"
            cmds.file(rename=str(path))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(str(path), open=True, force=True,
                      executeScriptNodes=False)
            reopened = all(cmds.objExists(plug)
                           for plug in guide["angles"])
            registered = len(ResolveBodyCharacter(MayaBodyBuildHost()).execute().body)
        data = {"source": scene.name, "sampler_count": len(specs),
                "angle_attribute_count": len(guide["angles"]),
                "rest_errors": rest_errors, "pose_errors": pose_errors,
                "mismatch_rejected": mismatch_rejected,
                "fault_rolled_back": fault_rolled_back,
                "undo_removed": undo_removed, "redo_restored": redo_restored,
                "save_reopen_retained": reopened,
                "registered_body_count": registered}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if (len(specs) != 8 or len(guide["angles"]) != 12
                or max(rest_errors.values()) > 1e-3
                or max(pose_errors.values()) > 1e-3
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
