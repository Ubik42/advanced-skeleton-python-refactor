"""Build a local replacement beside a referenced original character."""
from __future__ import annotations

from pathlib import Path
import tempfile

from adv_py.application.angle_sampler_deform import BuildAngleSamplers
from adv_py.application.angle_volume_deform import BuildAngleVolumeDeform
from adv_py.application.axial_part_deform import BuildAxialPartDeform
from adv_py.application.bend_volume_deform import BuildBendVolumeDeform
from adv_py.application.chest_volume_deform import BuildChestVolumeDeform
from adv_py.application.dense_skin_transfer import TransferDenseSkinWeights
from adv_py.application.finger_mid_deform import BuildFingerMidDeform
from adv_py.application.fit_skeleton_io import CreateAndImportFitSkeleton
from adv_py.application.knee_volume_deform import BuildKneeVolumeDeform
from adv_py.application.limb_part_deform import BuildLimbPartDeform
from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
from adv_py.application.root_volume_deform import BuildRootVolumeDeform
from adv_py.application.skin_bind import BindSkin
from adv_py.application.volume_half_parent import BuildVolumeHalfParents
from adv_py.application.external_fit_export import ExportExternalFitSkeleton
from adv_py.core.dense_skin_transfer import DenseSkinWeights

from .maya_angle_sampler import MayaAngleSamplerHost
from .maya_axial_part import MayaAxialPartHost
from .maya_body import MayaBodyBuildHost
from .maya_dense_skin import MayaDenseSkinHost
from .maya_finger_mid import MayaFingerMidHost
from .maya_limb_part import MayaLimbPartHost
from .maya_original_control_animation import (
    OriginalControlCurve, clone_original_control_animation,
    connect_original_control_animation, plan_original_control_animation)
from .maya_original_skin_migration import (
    OriginalSkinMigrationResult, _capture_guides, _skin_item,
    _without_undo_recording)
from .maya_root_volume import MayaRootVolumeHost
from .maya_sdk_volume import MayaSdkVolumeHost
from .maya_volume_half_parent import MayaVolumeHalfParentHost


def _base_name(name: str) -> str:
    return name.rsplit(":", 1)[-1]


class MayaReferencedSkinMigration:
    """Keep the source reference intact and make a local, undoable rig copy."""

    def __init__(self, cmds=None):
        if cmds is None:
            from maya import cmds as maya_cmds
            cmds = maya_cmds
        self._cmds = cmds

    def apply(self, *, source_skin: str, target_mesh: str,
              target_skin: str, on_stage=None
              ) -> OriginalSkinMigrationResult:
        c = self._cmds
        source_namespace = source_skin.rsplit(":", 1)[0] if ":" in source_skin else ""
        if not source_namespace:
            raise ValueError("引用来源需要独立的角色命名空间")
        target_namespace = source_namespace + "_AdvPy"
        target_exists = bool(c.namespace(exists=target_namespace))
        if target_exists and (c.namespaceInfo(target_namespace,
            listOnlyDependencyNodes=True, recurse=True) or
            c.namespaceInfo(target_namespace,
            listOnlyNamespaces=True, recurse=True)):
            raise ValueError("迁移目标命名空间已有内容：" + target_namespace)
        if not c.undoInfo(query=True, state=True):
            raise ValueError("迁移引用角色需要启用 Maya 撤销")
        if not c.referenceQuery(source_skin, isNodeReferenced=True):
            raise ValueError("源 Skin 不是 Maya 引用节点")
        source_reference = c.referenceQuery(source_skin, referenceNode=True)
        fits = c.ls(source_namespace + ":FitSkeleton", long=True,
                    type="transform") or []
        if len(fits) != 1:
            raise ValueError("引用角色需要唯一 FitSkeleton")
        fit_parent = (c.listRelatives(fits[0], parent=True,
                                     fullPath=True) or [None])[0]
        if (not fit_parent or not c.referenceQuery(fits[0],
            isNodeReferenced=True) or c.referenceQuery(fits[0],
            referenceNode=True) != source_reference):
            raise ValueError("Fit 与源 Skin 不属于同一角色引用")
        source_item = _skin_item(c, source_skin, target_mesh, target_skin)
        if (not c.referenceQuery(source_item.source_mesh,
            isNodeReferenced=True) or c.referenceQuery(
            source_item.source_mesh, referenceNode=True) != source_reference):
            raise ValueError("源网格与 Skin 不属于同一角色引用")
        for candidate in c.ls(type="skinCluster") or []:
            if candidate == source_skin:
                continue
            influences = c.skinCluster(candidate, query=True,
                                       influence=True) or []
            if any((c.ls(joint, long=True, type="joint") or [""])[0]
                   .startswith(fit_parent + "|") for joint in influences):
                raise ValueError("引用角色还有附加 Skin，须先完整登记：" + candidate)
        source = DenseSkinWeights(source_item.source.skin_name,
            source_item.source.vertex_count,
            tuple(_base_name(name) for name in
                  source_item.source.influence_names),
            source_item.source.values)
        if len(source.influence_names) != 121 or len(set(
                source.influence_names)) != 121:
            raise ValueError("公开角色源 Skin 必须有 121 个唯一影响关节")
        before_namespace = c.namespaceInfo(currentNamespace=True,
                                            absoluteName=True)
        before_relative = bool(c.namespace(query=True, relativeNames=True))
        try:
            with _without_undo_recording(c):
                c.namespace(setNamespace=":" + source_namespace)
                c.namespace(relativeNames=True)
            volume, angle, axial = _capture_guides(c)
            animation = plan_original_control_animation(c,
                _base_name(fit_parent))
            animation = tuple(OriginalControlCurve(
                (plan.source_curve if plan.source_curve.startswith(":")
                 else ":" + source_namespace + ":" + plan.source_curve),
                plan.clone_name, plan.target_plug) for plan in animation)
        finally:
            with _without_undo_recording(c):
                c.namespace(relativeNames=before_relative)
                c.namespace(setNamespace=before_namespace)
        root = c.ls(source_namespace + ":Root_M", long=True,
                    type="joint") or []
        expected = volume.get("root_world_matrix")
        if (len(root) != 1 or not isinstance(expected, list)
            or len(expected) != 16 or max(abs(a - b) for a, b in zip(
            c.xform(root[0], query=True, worldSpace=True, matrix=True),
            expected)) > 1e-5):
            raise ValueError("引用骨架与采集导向的静止姿态不一致")
        if not c.getAttr(fit_parent + ".visibility", settable=True):
            raise ValueError("引用角色容器的可见性不可写")
        if any(c.objExists(f"{target_namespace}:{name}") for name in
               (target_mesh, target_skin)):
            raise ValueError("迁移目标网格或 Skin 名称已被占用")

        with tempfile.TemporaryDirectory(prefix="advpy-referenced-fit-") as temp:
            fit_document = Path(temp) / "source.fit.json"
            ExportExternalFitSkeleton(MayaBodyBuildHost(
                namespace=source_namespace)).apply(fit_document)
            # Maya does not undo namespace creation. Keep the empty target
            # scope available across an ordinary Undo/Redo cycle.
            if not target_exists:
                c.namespace(add=target_namespace)
            c.undoInfo(openChunk=True,
                       chunkName="从原版引用构建本地完整蒙皮角色")
            try:
                imported = CreateAndImportFitSkeleton(MayaBodyBuildHost(
                    namespace=target_namespace)).apply(fit_document)
                copy = c.duplicate(source_item.source_mesh,
                    returnRootsOnly=True, renameChildren=True)[0]
                if c.listRelatives(copy, parent=True):
                    copy = c.parent(copy, world=True)[0]
                copy = c.rename(copy,
                    f"{target_namespace}:{target_mesh}")
                c.delete(copy, constructionHistory=True)
                c.namespace(setNamespace=":" + target_namespace)
                c.namespace(relativeNames=True)
                copy = target_mesh
                if on_stage:
                    on_stage("mesh-copied")
                animation_clones = clone_original_control_animation(c,
                                                                    animation)
                # A referenced rig may own Maya's first ikRPsolver. Give the
                # local rig its own standard solver before creating IK handles.
                if not c.objExists("ikRPsolver"):
                    c.createNode("ikRPsolver", name="ikRPsolver")
                if not c.objExists("hikSolver"):
                    c.createNode("hikSolver", name="hikSolver")
                built = BuildRegisteredBodyCharacter(
                    MayaBodyBuildHost()).apply("FitSkeleton",
                        infer_missing_labels=True)
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
                paths = {name: c.ls(name, long=True, type="joint") or []
                         for name in source.influence_names}
                if any(len(found) != 1 for found in paths.values()):
                    raise ValueError("原版 121 个影响关节未全部重建")
                BindSkin(MayaBodyBuildHost()).apply(
                    (c.ls(copy, long=True, type="transform") or [])[0],
                    tuple(paths[name][0] for name in source.influence_names),
                    skin_name=target_skin,
                    maximum_influences=source_item.maximum_influences,
                    maintain_maximum_influences=False)
                TransferDenseSkinWeights(MayaDenseSkinHost()).apply(
                    source, target_skin)
                c.setAttr(target_skin + ".maintainMaxInfluences",
                          source_item.maintain_maximum)
                result = MayaDenseSkinHost().capture_dense_skin(target_skin)
                if result.vertex_count != source.vertex_count:
                    raise RuntimeError("引用迁移后网格顶点数变化")
                connect_original_control_animation(c, animation_clones)
                c.namespace(relativeNames=before_relative)
                c.namespace(setNamespace=before_namespace)
                c.setAttr(fit_parent + ".visibility", 0)
                if on_stage:
                    on_stage("weights-copied")
            except BaseException:
                c.namespace(relativeNames=before_relative)
                c.namespace(setNamespace=before_namespace)
                c.undoInfo(closeChunk=True)
                c.undo()
                if not target_exists and not (c.namespaceInfo(target_namespace,
                    listOnlyDependencyNodes=True, recurse=True) or []):
                    c.namespace(removeNamespace=target_namespace)
                raise
            else:
                c.undoInfo(closeChunk=True)
        qualified_mesh = target_namespace + ":" + target_mesh
        qualified_skin = target_namespace + ":" + target_skin
        return OriginalSkinMigrationResult(qualified_mesh, qualified_skin,
            result.vertex_count, len(result.influence_names),
            len(built.registration.body), len(animation_clones),
            ((qualified_mesh, qualified_skin),))
