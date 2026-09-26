"""Assemble all rebuilt helpers and compare the 121 original Skin names."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def matrix(cmds, path):
    return tuple(cmds.xform(path, query=True, worldSpace=True, matrix=True))


def main(scene: Path, volume_file: Path, angle_file: Path, axial_file: Path,
         report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.adapters.maya_axial_part import MayaAxialPartHost
        from adv_py.adapters.maya_finger_mid import MayaFingerMidHost
        from adv_py.adapters.maya_limb_part import MayaLimbPartHost
        from adv_py.adapters.maya_root_volume import MayaRootVolumeHost
        from adv_py.adapters.maya_sdk_volume import MayaSdkVolumeHost
        from adv_py.adapters.maya_volume_half_parent import MayaVolumeHalfParentHost
        from adv_py.adapters.maya_angle_sampler import MayaAngleSamplerHost
        from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
        from adv_py.application.axial_part_deform import BuildAxialPartDeform
        from adv_py.application.finger_mid_deform import BuildFingerMidDeform
        from adv_py.application.limb_part_deform import BuildLimbPartDeform
        from adv_py.application.root_volume_deform import BuildRootVolumeDeform
        from adv_py.application.chest_volume_deform import BuildChestVolumeDeform
        from adv_py.application.knee_volume_deform import BuildKneeVolumeDeform
        from adv_py.application.volume_half_parent import BuildVolumeHalfParents
        from adv_py.application.bend_volume_deform import BuildBendVolumeDeform
        from adv_py.application.angle_sampler_deform import BuildAngleSamplers
        from adv_py.application.angle_volume_deform import BuildAngleVolumeDeform
        from adv_py.application.character_registry import ResolveBodyCharacter

        volume = json.loads(volume_file.read_text(encoding="utf-8"))
        angle = json.loads(angle_file.read_text(encoding="utf-8"))
        axial = json.loads(axial_file.read_text(encoding="utf-8"))
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        skins = cmds.ls(type="skinCluster") or []
        if len(fits) != 1 or len(skins) != 1:
            raise ValueError("原版场景需要唯一 FitSkeleton 和 skinCluster")
        names = [path.rsplit("|", 1)[-1] for path in cmds.skinCluster(
            skins[0], query=True, influence=True) or []]
        if len(names) != 121 or len(set(names)) != 121:
            raise ValueError("原版 Skin 影响关节不是 121 个唯一名称")
        original = {name: matrix(cmds, name) for name in names}
        axial_names = ("RootPart1_M", "RootPart2_M", "Spine1Part1_M",
                       "Spine1Part2_M", "NeckPart1_M", "NeckPart2_M")
        original_controls = {stem: matrix(cmds, "FK" + stem + "_M")
                             for stem in ("Root", "Spine1", "Neck")}
        axial_poses = {}
        original_control_poses = {}
        for stem in ("Root", "Spine1", "Neck"):
            control = "FK" + stem + "_M"
            cmds.setAttr(control + ".rotateY", 20.0)
            original_control_poses[stem] = matrix(cmds, control)
            axial_poses[stem] = {name: matrix(cmds, name)
                                 for name in axial_names}
            cmds.setAttr(control + ".rotateY", 0.0)
        extra_cases = {
            f"{stem}{axis}20": {f"FK{stem}_M.rotate{axis}": 20.0}
            for stem in ("Root", "Spine1", "Neck")
            for axis in ("X", "Z")
        }
        extra_cases["combined"] = {"FKRoot_M.rotateY": 12.0,
                                   "FKSpine1_M.rotateX": 10.0,
                                   "FKNeck_M.rotateZ": -8.0}
        extra_poses = {}
        for label, settings in extra_cases.items():
            for plug, value in settings.items():
                cmds.setAttr(plug, value)
            extra_poses[label] = {name: matrix(cmds, name)
                                  for name in axial_names}
            for plug in settings:
                cmds.setAttr(plug, 0.0)
        fit_parent = (cmds.listRelatives(fits[0], parent=True,
                                        fullPath=True) or [""])[0]
        cmds.delete(tuple(path for path in (cmds.listRelatives(
            fit_parent, children=True, fullPath=True) or ()) if path != fits[0]))
        BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
            fits[0], infer_missing_labels=True)
        wrong_guide = deepcopy(axial)
        wrong_guide["nodes"]["FKRoot_M"]["world_matrix"][12] += 1.0
        try:
            BuildAxialPartDeform(MayaAxialPartHost()).apply(
                guide=wrong_guide)
        except ValueError:
            axial_mismatch_rejected = not cmds.ls(
                "AdvPy_Axial*", type="transform")
        else:
            axial_mismatch_rejected = False
        if not axial_mismatch_rejected:
            raise AssertionError("轴向分段错误导向未拒绝")
        class FaultyAxialHost(MayaAxialPartHost):
            count = 0

            def create_axial_part(self, spec, guide=None):
                super().create_axial_part(spec, guide)
                self.count += 1
                if self.count == 3:
                    raise RuntimeError("injected axial fault")

        try:
            BuildAxialPartDeform(FaultyAxialHost()).apply(guide=axial)
        except RuntimeError as exc:
            fault_rolled_back = (str(exc) == "injected axial fault" and
                not cmds.ls("AdvPy_Axial*", type="transform") and
                not cmds.ls("RootPart1_M", type="joint"))
        else:
            fault_rolled_back = False
        if not fault_rolled_back:
            raise AssertionError("轴向分段故障未回滚")
        BuildAxialPartDeform(MayaAxialPartHost()).apply(guide=axial)
        cmds.undo()
        axial_undo_removed = not cmds.ls("RootPart1_M", type="joint")
        cmds.redo()
        axial_redo_restored = len(cmds.ls("RootPart1_M", type="joint") or []) == 1
        BuildFingerMidDeform(MayaFingerMidHost()).apply()
        BuildLimbPartDeform(MayaLimbPartHost()).apply()
        BuildRootVolumeDeform(MayaRootVolumeHost()).apply(volume)
        BuildChestVolumeDeform(MayaSdkVolumeHost()).apply(volume)
        BuildKneeVolumeDeform(MayaSdkVolumeHost()).apply(volume)
        BuildVolumeHalfParents(MayaVolumeHalfParentHost()).apply(volume)
        BuildBendVolumeDeform(MayaSdkVolumeHost()).apply(volume)
        BuildAngleSamplers(MayaAngleSamplerHost()).apply(angle)
        BuildAngleVolumeDeform(MayaSdkVolumeHost()).apply(volume)
        matches = {name: cmds.ls(name, type="joint", long=True) or []
                   for name in names}
        errors = {name: max(abs(a - b) for a, b in zip(
            original[name], matrix(cmds, paths[0])))
            for name, paths in matches.items() if len(paths) == 1}
        volume_names = {row["name"] for row in volume["joints"]}
        volume_errors = {name: errors[name] for name in volume_names
                         if name in errors}
        axial_differences = {name: [a - b for a, b in zip(
            original[name], matrix(cmds, matches[name][0]))]
            for name in axial_names}
        axial_pose_errors = {}
        axial_pose_differences = {}
        axial_helper_rotations = {}
        axial_anchor_pose_errors = {}
        control_rest_errors = {}
        control_pose_errors = {}
        for stem, source_pose in axial_poses.items():
            control = "AdvPy_Torso" + stem + "_MFK"
            control_rest_errors[stem] = max(abs(a - b) for a, b in zip(
                original_controls[stem], matrix(cmds, control)))
            cmds.setAttr(control + ".rotateY", 20.0)
            control_pose_errors[stem] = max(abs(a - b) for a, b in zip(
                original_control_poses[stem], matrix(cmds, control)))
            axial_pose_errors[stem] = {name: max(abs(a - b) for a, b
                in zip(source_pose[name], matrix(cmds, matches[name][0])))
                for name in axial_names}
            axial_pose_differences[stem] = {name: [a - b for a, b in zip(
                source_pose[name], matrix(cmds, matches[name][0]))]
                for name in axial_names}
            axial_helper_rotations[stem] = {name: cmds.getAttr(
                "AdvPy_AxialFKX" + name + ".rotate")[0]
                for name in axial_names}
            anchor = "AdvPy_AxialFKX" + stem + "_M"
            axial_anchor_pose_errors[stem] = max(abs(a - b) for a, b
                in zip(axial["poses"][stem]["FKX" + stem + "_M"]["world_matrix"],
                       matrix(cmds, anchor))) if "FKX" + stem + "_M" in axial["poses"][stem] else None
            cmds.setAttr(control + ".rotateY", 0.0)
        extra_pose_errors = {}
        for label, source_pose in extra_poses.items():
            settings = extra_cases[label]
            for plug, value in settings.items():
                cmds.setAttr(plug.replace("FK", "AdvPy_Torso", 1)
                             .replace("_M.rotate", "_MFK.rotate"), value)
            extra_pose_errors[label] = {name: max(abs(a - b) for a, b
                in zip(source_pose[name], matrix(cmds, matches[name][0])))
                for name in axial_names}
            for plug in settings:
                cmds.setAttr(plug.replace("FK", "AdvPy_Torso", 1)
                             .replace("_M.rotate", "_MFK.rotate"), 0.0)
        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / "guided-axial.ma"
            cmds.file(rename=str(saved))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(str(saved), open=True, force=True,
                      executeScriptNodes=False)
            axial_reopened = (all(len(cmds.ls(name, type="joint") or []) == 1
                                  for name in names) and
                max(max(abs(a - b) for a, b in zip(
                    original[name], matrix(cmds, name)))
                    for name in axial_names) < 1e-4)
        data = {"source": scene.name, "source_influence_count": len(names),
                "matched_influence_count": len(errors),
                "missing_or_ambiguous": {name: paths for name, paths in
                    matches.items() if len(paths) != 1},
                "worst_rest_matrices": sorted(errors.items(),
                    key=lambda item: item[1], reverse=True)[:20],
                "maximum_rest_matrix_error": max(errors.values()) if errors else None,
                "volume_joint_count": len(volume_errors),
                "maximum_volume_rest_matrix_error": (
                    max(volume_errors.values()) if volume_errors else None),
                "axial_rest_matrix_differences": axial_differences,
                "axial_pose_matrix_errors": axial_pose_errors,
                "axial_pose_matrix_differences": axial_pose_differences,
                "axial_helper_rotations": axial_helper_rotations,
                "axial_anchor_pose_errors": axial_anchor_pose_errors,
                "axial_extra_pose_matrix_errors": extra_pose_errors,
                "axial_control_rest_matrix_errors": control_rest_errors,
                "axial_control_pose_matrix_errors": control_pose_errors,
                "registered_body_count": len(
                    ResolveBodyCharacter(MayaBodyBuildHost()).execute().body),
                "axial_fault_rolled_back": fault_rolled_back,
                "axial_mismatch_rejected": axial_mismatch_rejected,
                "axial_undo_removed": axial_undo_removed,
                "axial_redo_restored": axial_redo_restored,
                "axial_save_reopen_retained": axial_reopened}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if (data["matched_influence_count"] != 121
                or data["volume_joint_count"] != 40
                or data["maximum_volume_rest_matrix_error"] > 1e-4
                or max(abs(value) for row in axial_differences.values()
                       for value in row[12:15]) > 1e-4
                or max(max(row.values()) for row in axial_pose_errors.values()) > 1e-4
                or max(max(row.values()) for row in extra_pose_errors.values()) > 1e-4
                or not all((axial_mismatch_rejected, fault_rolled_back,
                            axial_undo_removed,
                            axial_redo_restored, axial_reopened))
                or data["registered_body_count"] != 74):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                          Path(sys.argv[3]), Path(sys.argv[4]),
                          Path(sys.argv[5])))
