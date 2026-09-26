"""Assemble all rebuilt helpers and compare the 121 original Skin names."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def matrix(cmds, path):
    return tuple(cmds.xform(path, query=True, worldSpace=True, matrix=True))


def main(scene: Path, volume_file: Path, angle_file: Path,
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
        fit_parent = (cmds.listRelatives(fits[0], parent=True,
                                        fullPath=True) or [""])[0]
        cmds.delete(tuple(path for path in (cmds.listRelatives(
            fit_parent, children=True, fullPath=True) or ()) if path != fits[0]))
        BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
            fits[0], infer_missing_labels=True)
        BuildAxialPartDeform(MayaAxialPartHost()).apply()
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
                "registered_body_count": len(
                    ResolveBodyCharacter(MayaBodyBuildHost()).execute().body)}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if (data["matched_influence_count"] != 121
                or data["volume_joint_count"] != 40
                or data["maximum_volume_rest_matrix_error"] > 1e-4
                or data["registered_body_count"] != 74):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                          Path(sys.argv[3]), Path(sys.argv[4])))
