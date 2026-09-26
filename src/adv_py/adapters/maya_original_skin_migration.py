"""Replace an original public character rig while retaining its mesh and Skin."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adv_py.application.angle_sampler_deform import BuildAngleSamplers
from adv_py.application.angle_volume_deform import BuildAngleVolumeDeform
from adv_py.application.axial_part_deform import BuildAxialPartDeform
from adv_py.application.bend_volume_deform import BuildBendVolumeDeform
from adv_py.application.chest_volume_deform import BuildChestVolumeDeform
from adv_py.application.dense_skin_transfer import TransferDenseSkinWeights
from adv_py.application.finger_mid_deform import BuildFingerMidDeform
from adv_py.application.knee_volume_deform import BuildKneeVolumeDeform
from adv_py.application.limb_part_deform import BuildLimbPartDeform
from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
from adv_py.application.root_volume_deform import BuildRootVolumeDeform
from adv_py.application.skin_bind import BindSkin
from adv_py.application.volume_half_parent import BuildVolumeHalfParents

from .maya_angle_sampler import MayaAngleSamplerHost
from .maya_axial_part import MayaAxialPartHost
from .maya_body import MayaBodyBuildHost
from .maya_dense_skin import MayaDenseSkinHost
from .maya_finger_mid import MayaFingerMidHost
from .maya_limb_part import MayaLimbPartHost
from .maya_original_guide_capture import capture_original_guides
from .maya_root_volume import MayaRootVolumeHost
from .maya_sdk_volume import MayaSdkVolumeHost
from .maya_volume_half_parent import MayaVolumeHalfParentHost


@dataclass(frozen=True, slots=True)
class OriginalSkinMigrationResult:
    mesh: str
    skin: str
    vertices: int
    influences: int
    body_joints: int


class MayaOriginalSkinMigration:
    """One undoable replacement of the open original scene's character rig.

    The guide can be captured from the current scene before its rig is removed.
    This operation never opens another file.
    """

    def __init__(self, cmds=None):
        if cmds is None:
            from maya import cmds as maya_cmds
            cmds = maya_cmds
        self._cmds = cmds

    def apply(self, *, source_skin: str = "", volume: dict | None = None,
              angle: dict | None = None, axial: dict | None = None,
              target_mesh: str = "AdvPy_MigratedMesh",
              target_skin: str = "AdvPy_MigratedSkin",
              on_stage=None) -> OriginalSkinMigrationResult:
        c = self._cmds
        source_skin = source_skin.strip()
        if not source_skin:
            candidates = c.ls(type="skinCluster") or []
            if len(candidates) != 1:
                raise ValueError("请填写唯一的原版源 Skin 名称")
            source_skin = candidates[0]
        if volume is None and angle is None and axial is None:
            if not c.undoInfo(query=True, state=True):
                raise ValueError("迁移原版角色需要启用 Maya 撤销")
            for stem in ("Root", "Spine1", "Neck"):
                values = c.getAttr(f"FK{stem}_M.rotate")[0]
                if any(abs(value) > 1e-8 for value in values):
                    raise ValueError("采集驱动导向前须将躯干 FK 控制归零")
            c.undoInfo(openChunk=True, chunkName="只读采集原版驱动导向")
            try:
                for side in ("R", "L"):
                    c.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
                volume, angle, axial = capture_original_guides(c,
                    Path(c.file(query=True, sceneName=True)).name)
            finally:
                c.undoInfo(closeChunk=True)
                c.undo()
        elif any(guide is None for guide in (volume, angle, axial)):
            raise ValueError("须同时提供三份驱动导向，或由当前场景自动采集")
        source = MayaDenseSkinHost().capture_dense_skin(source_skin)
        if len(source.influence_names) != 121:
            raise ValueError("公开角色源 Skin 必须有 121 个影响关节")
        if not all(isinstance(guide, dict) and guide.get("source")
                   == volume.get("source") for guide in (volume, angle, axial)):
            raise ValueError("三份驱动导向必须来自同一个原版场景")
        scene_name = Path(c.file(query=True, sceneName=True)).name
        if not scene_name or scene_name != volume["source"]:
            raise ValueError("驱动导向的来源文件与当前场景不一致")
        root_paths = c.ls("Root_M", long=True, type="joint") or []
        expected_root = volume.get("root_world_matrix")
        if (len(root_paths) != 1 or not isinstance(expected_root, list)
                or len(expected_root) != 16
                or max(abs(a - b) for a, b in zip(c.xform(root_paths[0],
                    query=True, worldSpace=True, matrix=True),
                    expected_root)) > 1e-5):
            raise ValueError("当前原版骨架与驱动导向的静止姿态不一致")
        shapes = c.skinCluster(source_skin, query=True, geometry=True) or []
        if len(shapes) != 1:
            raise ValueError("源 Skin 必须只绑定一个网格")
        mesh_paths = c.ls(shapes[0], long=True, type="mesh") or []
        if len(mesh_paths) != 1:
            raise ValueError("源网格不唯一")
        source_mesh = (c.listRelatives(mesh_paths[0], parent=True,
                                      fullPath=True) or [None])[0]
        fits = c.ls("FitSkeleton", type="transform", long=True) or []
        if len(fits) != 1 or not source_mesh:
            raise ValueError("原版场景需要唯一 FitSkeleton 和源网格")
        fit_parent = (c.listRelatives(fits[0], parent=True,
                                     fullPath=True) or [None])[0]
        if not fit_parent:
            raise ValueError("FitSkeleton 没有可替换的原版角色容器")
        if any(c.objExists(name) for name in (target_mesh, target_skin)):
            raise ValueError("目标网格或 Skin 名称已被占用")
        for guide, key in ((volume, "joints"), (angle, "angles"),
                           (axial, "nodes")):
            if key not in guide:
                raise ValueError("驱动导向缺少数据：" + key)
        max_influences = int(c.getAttr(source_skin + ".maxInfluences"))
        maintain = bool(c.getAttr(source_skin + ".maintainMaxInfluences"))
        c.undoInfo(openChunk=True, chunkName="迁移原版角色与完整蒙皮")
        try:
            for side in ("R", "L"):
                plug = f"FKIKLeg_{side}.FKIKBlend"
                if c.objExists(plug):
                    c.setAttr(plug, 0.0)
            copy = c.duplicate(source_mesh, returnRootsOnly=True,
                               renameChildren=True)[0]
            if c.listRelatives(copy, parent=True):
                copy = c.parent(copy, world=True)[0]
            copy = c.rename(copy, target_mesh)
            c.delete(copy, constructionHistory=True)
            if on_stage:
                on_stage("mesh-copied")
            c.delete(tuple(path for path in (c.listRelatives(
                fit_parent, children=True, fullPath=True) or ())
                if path != fits[0]))
            built = BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
                fits[0], infer_missing_labels=True)
            BuildAxialPartDeform(MayaAxialPartHost()).apply(guide=axial)
            BuildFingerMidDeform(MayaFingerMidHost()).apply()
            BuildLimbPartDeform(MayaLimbPartHost()).apply(
                split_body_twist=True)
            BuildRootVolumeDeform(MayaRootVolumeHost()).apply(volume)
            BuildChestVolumeDeform(MayaSdkVolumeHost()).apply(volume)
            BuildKneeVolumeDeform(MayaSdkVolumeHost()).apply(volume)
            BuildVolumeHalfParents(MayaVolumeHalfParentHost()).apply(volume)
            BuildBendVolumeDeform(MayaSdkVolumeHost()).apply(volume)
            BuildAngleSamplers(MayaAngleSamplerHost()).apply(angle)
            BuildAngleVolumeDeform(MayaSdkVolumeHost()).apply(volume)
            if on_stage:
                on_stage("rig-built")
            paths = {name: c.ls(name, type="joint", long=True) or []
                     for name in source.influence_names}
            if any(len(found) != 1 for found in paths.values()):
                raise ValueError("原版影响关节未全部重建")
            BindSkin(MayaBodyBuildHost()).apply(
                (c.ls(copy, type="transform", long=True) or [])[0],
                tuple(paths[name][0] for name in source.influence_names),
                skin_name=target_skin,
                maximum_influences=max_influences,
                maintain_maximum_influences=False)
            TransferDenseSkinWeights(MayaDenseSkinHost()).apply(
                source, target_skin)
            c.setAttr(target_skin + ".maintainMaxInfluences", maintain)
            result = MayaDenseSkinHost().capture_dense_skin(target_skin)
            if result.vertex_count != source.vertex_count:
                raise RuntimeError("迁移后的顶点数变化")
            if on_stage:
                on_stage("weights-copied")
        except BaseException:
            c.undoInfo(closeChunk=True)
            c.undo()
            raise
        else:
            c.undoInfo(closeChunk=True)
        return OriginalSkinMigrationResult(copy, target_skin,
            result.vertex_count, len(result.influence_names),
            len(built.registration.body))
