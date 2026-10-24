"""In-process Maya panel actions; scene changes go through application cases."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable

from adv_py.adapters import MayaFaceHost, MayaOriginalSkinSpineMigrationHost
from adv_py.application import (ApplyBodyCharacterAnimation,
    ApplyBodyCharacterPose, ApplyFacePerformance, BindSkin,
    BakeBodyExportSkeleton, BuildBodyExportSkeleton, BuildBodyRootMotion,
    BuildFaceBlendShapes,
    CaptureBodyCharacterAnimation, CaptureBodyCharacterPose,
    CaptureAnimatedBodyCharacterPose, KeyBodyCharacterPose,
    EnableBodyCharacterLimbAnimation, EnableBodyCharacterStretchMatching,
    EnableBodyCharacterSplineAnimation, EnableBodyCharacterSpaceAnimation,
    BakeBodyCharacterLimbMode, BakeBodyCharacterSpineMode,
    SwitchBodyCharacterSpace,
    AutoScaleControlCurves, ColorControlCurves, MirrorControlCurves,
    ScaleControlCurves, SwapControlCurves,
    CreateAndImportFitSkeleton, EditFitJointMetadata,
    EditAndOrientFitJointPositions,
    ExportFitSkeleton, ExportExternalFitSkeleton, ExportSkinWeights,
    OrientFitJoints,
    OrientWorldFitJoints,
    ExportBodyFbx, ExportFaceTargetAsset, GenerateFaceTarget, ImportFaceTargetAsset,
    FaceAssetLibrary, ImportSkinWeights, InspectBodyCharacterPresets,
    CaptureSkinWeightSurfaceSource, TransferSkinWeightsBySurface,
    load_skin_weight_surface_source, save_skin_weight_surface_source,
    RebuildBodyCharacter, ReplaceRegisteredSpineCharacter, ResolveBodyCharacter,
    ImportMocapFbx, RetargetMocapFullFkToCharacter,
    RetargetMocapFullLimbIkToCharacter, RetargetMocapFullIkToCharacter,
    load_mocap_mapping_preset,
    load_character_animation, load_character_pose, load_face_target_asset,
    save_character_animation, save_character_pose, save_face_target_asset)
from adv_py.core import (BodyFbxCurvePolicy, BodyFbxEncoding,
    BodyFbxExportProfile, BodyFbxFileVersion, FaceShapeKind, FaceTarget,
    FitJointField, FitJointFieldEdit, FitJointPatch,
    FitJointPositionEdit, FitJointPositionPatch, FitOrientationChildSelection,
    FitOrientationRequest,
    face_performance_from_json)

from .input_documents import (load_face_build_spec, load_face_landmarks,
                              load_skin_path_mapping, load_skin_redistribution,
                              load_surface_alignment)


@dataclass(frozen=True, slots=True)
class PanelCharacter:
    namespace: str
    registered: bool
    joint_count: int = 0
    channel_count: int = 0
    issue: str = ""
    segment_joint_count: int = 0
    mode: str = ""


@dataclass(frozen=True, slots=True)
class PanelFbxPublication:
    joints: int
    frames: int
    bytes_written: int
    sha256: str
    euler_filtered_curves: int = 0


@dataclass(frozen=True, slots=True)
class PanelMocapResult:
    source_joints: int
    frames: int
    source_root: str


@dataclass(frozen=True, slots=True)
class PanelSkinSurfaceResult:
    vertices: int
    changed_vertices: int
    max_surface_distance: float
    max_discarded_weight: float


def _ensure_body_build_centimeters() -> None:
    """Mirror asReBuildAdvancedSkeleton's public cm scene-unit gate."""
    from maya import cmds

    current = str(cmds.currentUnit(query=True, linear=True))
    if current in ("cm", "centimeter"):
        return
    answer = cmds.confirmDialog(
        title="确认场景单位",
        message=(f"当前线性单位为 {current}。AdvancedSkeleton 构建要求厘米。"
                 "\n切换到厘米并继续吗？"),
        button=("切换并继续", "取消"),
        defaultButton="切换并继续", cancelButton="取消",
        dismissString="取消")
    if answer != "切换并继续":
        raise ValueError("已取消：角色构建需要厘米场景单位")
    cmds.currentUnit(linear="cm")
    if str(cmds.currentUnit(query=True, linear=True)) not in (
            "cm", "centimeter"):
        raise RuntimeError("场景线性单位切换到厘米失败")


def _target_for_source_skeleton(cmds, namespace: str,
                                source_root: str) -> tuple[str, str | None]:
    matches = cmds.ls(source_root, long=True, type="joint") or []
    if len(matches) != 1:
        raise ValueError("请选择唯一的来源根关节")
    leaf = matches[0].rsplit("|", 1)[-1]
    source_namespace = leaf.rsplit(":", 1)[0] if ":" in leaf else ":"
    if source_namespace != namespace:
        return namespace, None
    index = 1
    while cmds.namespace(exists="AdvPy" if index == 1 else f"AdvPy{index}"):
        index += 1
    target = "AdvPy" if index == 1 else f"AdvPy{index}"
    cmds.namespace(addNamespace=":" + target)
    return target, target


def _remove_empty_source_target(cmds, namespace: str | None) -> None:
    if namespace and cmds.namespace(exists=namespace):
        if not (cmds.namespaceInfo(namespace,
                listOnlyDependencyNodes=True, recurse=True) or []):
            cmds.namespace(removeNamespace=namespace)


_FIT_INTEGER_FIELDS = frozenset({
    FitJointField.TWIST_JOINTS,
    FitJointField.BENDY_CONTROLS,
    FitJointField.INBETWEEN_JOINTS,
    FitJointField.CHILD_OF_PART,
    FitJointField.NUM_MAIN_EXTRAS,
})
_FIT_BOOLEAN_FIELDS = frozenset({
    FitJointField.UNTWISTER,
    FitJointField.CONTROL,
    FitJointField.TWEAKER_CONTROL,
    FitJointField.NO_CONTROL,
    FitJointField.NO_SKIN,
    FitJointField.SEG_SCALE_COMP,
    FitJointField.HIP_SWINGER,
    FitJointField.COG,
    FitJointField.AIM,
    FitJointField.FOOT_PIVOTS,
    FitJointField.WHEEL,
    FitJointField.ROLLING_BALL,
    FitJointField.FREE_ORIENT,
    FitJointField.FLIP_ORIENT,
    FitJointField.NO_MIRROR,
    FitJointField.NO_MIRROR_LEFT,
    FitJointField.NO_FLIP,
    FitJointField.GLOBAL_TRANSLATE,
    FitJointField.ORIENT_CONSTRAINT_MAINTAIN_OFFSET,
    FitJointField.FOLLOW_LEFT_RIGHT,
    FitJointField.FOLLOW_WORLD,
    FitJointField.FOLLOW_SPACES,
    FitJointField.LEG_LOCK,
    FitJointField.CENTER_BETWEEN_FEET,
})


def parse_fit_metadata_value(field: str, text: str, *, remove: bool = False):
    """Parse one panel field without weakening the core validation contract."""
    try:
        key = FitJointField(field)
    except ValueError as error:
        raise ValueError(f"未知 Fit 元数据字段：{field}") from error
    if remove:
        return key, None
    value = text.strip()
    if not value:
        raise ValueError("请填写 Fit 元数据值，或选择删除字段")
    if key is FitJointField.FOLLOW_BY_NAME:
        from adv_py.core.fit_metadata import validate_follow_by_name
        entries = []
        for pair in value.split(","):
            name, separator, weight_text = pair.strip().partition("=")
            if not separator:
                raise ValueError("Follow* 格式应为 目标=权重,目标=权重")
            try:
                weight = float(weight_text)
            except ValueError as error:
                raise ValueError("Follow* 权重必须是数值") from error
            entries.append((name.strip(), weight))
        result = tuple(entries)
        validate_follow_by_name(result)
        return key, result
    if key in _FIT_INTEGER_FIELDS:
        try:
            return key, int(value)
        except ValueError as error:
            raise ValueError(f"{field} 必须是整数") from error
    if key in _FIT_BOOLEAN_FIELDS:
        normalized = value.lower()
        if normalized not in {"true", "false", "1", "0"}:
            raise ValueError(f"{field} 必须是 true、false、1 或 0")
        return key, normalized in {"true", "1"}
    if key is FitJointField.GLOBAL_WEIGHT:
        try:
            return key, float(value)
        except ValueError as error:
            raise ValueError("global_weight 必须是数值") from error
    return key, value


class MayaPanelController:
    """Connect one selected namespace to application use cases."""

    def __init__(self, host_factory=MayaFaceHost):
        self._host_factory = host_factory

    def hide_help_buttons(self) -> bool:
        from maya import cmds

        key = "asSettingsHideHelpButtons"
        return (bool(cmds.optionVar(query=key))
                if cmds.optionVar(exists=key) else False)

    def set_hide_help_buttons(self, hidden: bool) -> bool:
        from maya import cmds

        if type(hidden) is not bool:
            raise ValueError("隐藏帮助按钮开关无效")
        cmds.optionVar(intValue=("asSettingsHideHelpButtons", int(hidden)))
        actual = self.hide_help_buttons()
        if actual != hidden:
            raise RuntimeError("隐藏帮助按钮开关保存失败")
        return actual

    def panel_palette(self):
        from maya import cmds
        from adv_py.core.panel_preferences import (
            PANEL_COLOR_DEFAULTS, PanelPalette, panel_rgb)

        enabled = (bool(cmds.optionVar(query="asSettingsUseCustomColors"))
                   if cmds.optionVar(exists="asSettingsUseCustomColors")
                   else False)
        colors = []
        for kind, fallback in PANEL_COLOR_DEFAULTS:
            key = "asSettingsUseCustomColors" + kind
            value = (cmds.optionVar(query=key)
                     if cmds.optionVar(exists=key) else fallback)
            try:
                color = panel_rgb(value)
            except ValueError:
                color = fallback
            colors.append((kind, color))
        return PanelPalette(enabled, tuple(colors))

    def set_panel_palette_enabled(self, enabled: bool):
        from maya import cmds

        if type(enabled) is not bool:
            raise ValueError("自定义颜色开关无效")
        cmds.optionVar(intValue=("asSettingsUseCustomColors", int(enabled)))
        result = self.panel_palette()
        if result.enabled != enabled:
            raise RuntimeError("自定义颜色开关保存失败")
        return result

    def set_panel_color(self, kind: str, rgb):
        from maya import cmds
        from adv_py.core.panel_preferences import PANEL_COLOR_KINDS, panel_rgb

        if kind not in PANEL_COLOR_KINDS:
            raise ValueError("面板颜色栏目无效")
        color = panel_rgb(rgb)
        key = "asSettingsUseCustomColors" + kind
        if cmds.optionVar(exists=key):
            cmds.optionVar(remove=key)
        for value in color:
            cmds.optionVar(floatValueAppend=(key, value))
        result = self.panel_palette()
        if any(abs(a - b) > 1e-6 for a, b in zip(result.color(kind), color)):
            raise RuntimeError("面板颜色保存失败")
        return result

    def reset_panel_colors(self):
        from maya import cmds
        from adv_py.core.panel_preferences import PANEL_COLOR_DEFAULTS

        keys = ("asSettingsUseCustomColors",) + tuple(
            "asSettingsUseCustomColors" + kind + suffix
            for kind, _ in PANEL_COLOR_DEFAULTS for suffix in ("", "Fade"))
        for key in keys:
            if cmds.optionVar(exists=key):
                cmds.optionVar(remove=key)
        result = self.panel_palette()
        if result.enabled or result.colors != PANEL_COLOR_DEFAULTS:
            raise RuntimeError("面板颜色未恢复默认值")
        return result

    def _host(self, namespace: str):
        if not isinstance(namespace, str) or not namespace.strip():
            raise ValueError("请选择角色命名空间")
        return self._host_factory(namespace=None if namespace == ":" else namespace)

    def body_build_options(self, namespace: str,
                           container: str = "FitSkeleton"):
        from adv_py.core.body_build_options import BodyBuildOptions
        from adv_py.core.fit_settings import FitSkeletonField

        settings = self._host(namespace).read_fit_skeleton_settings(container)
        return BodyBuildOptions(
            game_engine=settings.value(FitSkeletonField.GAME_ENGINE) is True,
            use_offset_parent_matrix=settings.value(
                FitSkeletonField.USE_OFFSET_PARENT_MATRIX) is True,
            sub_controllers=settings.value(
                FitSkeletonField.SUB_CONTROLLERS) is True,
            extra_controllers=settings.value(
                FitSkeletonField.EXTRA_CONTROLLERS) is True,
        )

    def set_body_build_options(self, namespace: str, options,
                               container: str = "FitSkeleton"):
        from adv_py.application.body_build_options import SetBodyBuildOptions

        result = SetBodyBuildOptions(self._host(namespace)).apply(
            options, container)
        return result.plan.desired

    def model_check(self, *, interactive: bool = False,
                    skip_symmetry: bool = False):
        from adv_py.adapters.maya_model_checker import MayaModelCheckHost
        from adv_py.application.model_check import CheckModel, ReviewModelCheck

        host = MayaModelCheckHost()
        if interactive:
            return ReviewModelCheck(host).execute(skip_symmetry=skip_symmetry)
        return CheckModel(host).execute(skip_symmetry=skip_symmetry)

    def model_create_geo_group(self) -> tuple[str, ...]:
        from adv_py.adapters.maya_model_geo_group import MayaModelGeoGroupHost
        from adv_py.application.model_geo_group import CreateModelGeoGroup

        return CreateModelGeoGroup(MayaModelGeoGroupHost()).execute()

    def model_clean(self):
        from adv_py.adapters.maya_model_clean import MayaModelCleanHost
        from adv_py.application.model_clean import CleanModel

        return CleanModel(MayaModelCleanHost()).execute()

    def preparation_new_scene(self) -> None:
        from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost

        MayaPreparationReferenceHost().new_scene()

    def preparation_scene_modified(self) -> bool:
        from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost

        return MayaPreparationReferenceHost().scene_modified()

    def preparation_scene_name(self) -> str:
        from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost

        return MayaPreparationReferenceHost().scene_name()

    def preparation_save_scene(self, destination: Path | None = None) -> None:
        from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost

        MayaPreparationReferenceHost().save_scene(destination)

    def preparation_reference_model(self, source: Path):
        from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost
        from adv_py.application.preparation_reference import ReferencePreparationModel

        return ReferencePreparationModel(MayaPreparationReferenceHost()).execute(source)

    def preparation_reload_model(self, namespace: str):
        from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost
        from adv_py.application.preparation_reference import ManagePreparationModelReference

        return ManagePreparationModelReference(MayaPreparationReferenceHost()).reload(namespace)

    def preparation_replace_model(self, namespace: str, source: Path):
        from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost
        from adv_py.application.preparation_reference import ManagePreparationModelReference

        return ManagePreparationModelReference(MayaPreparationReferenceHost()).replace(
            namespace, source)

    def preparation_remove_model(self, namespace: str):
        from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost
        from adv_py.application.preparation_reference import ManagePreparationModelReference

        return ManagePreparationModelReference(MayaPreparationReferenceHost()).remove(namespace)

    def preparation_record_objects(self, namespace: str, role: str) -> tuple[str, ...]:
        from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
        from adv_py.application.preparation_objects import RecordPreparationObjects
        from adv_py.core.preparation_objects import PreparationObjectRole

        return RecordPreparationObjects(MayaPreparationObjectsHost(namespace)).execute(
            PreparationObjectRole(role))

    def preparation_read_objects(self, namespace: str, role: str) -> tuple[str, ...]:
        from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
        from adv_py.core.preparation_objects import PreparationObjectRole

        return MayaPreparationObjectsHost(namespace).read_objects(
            PreparationObjectRole(role))

    def preparation_reselect_objects(self, namespace: str, role: str) -> tuple[str, ...]:
        from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
        from adv_py.application.preparation_objects import ReselectPreparationObjects
        from adv_py.core.preparation_objects import PreparationObjectRole

        return ReselectPreparationObjects(MayaPreparationObjectsHost(namespace)).execute(
            PreparationObjectRole(role))

    def preparation_one_joint_prop(self, namespace: str, *, build_options=None):
        from adv_py.adapters.maya_one_joint_prop import MayaOneJointPropHost
        from adv_py.application.one_joint_prop import BuildOneJointProp

        skins = self.preparation_read_objects(namespace, "Skin")
        all_meshes = self.preparation_read_objects(namespace, "All")
        return BuildOneJointProp(MayaOneJointPropHost(
            namespace=None if namespace == ":" else namespace)).apply(
            skins, all_meshes, build_options=build_options)

    def preparation_fbx_rig(self):
        from adv_py.adapters.maya_fbx_rig_source import MayaFBXRigPreparationHost
        from adv_py.application.fbx_rig_import import BuildFBXRig

        return BuildFBXRig(MayaFBXRigPreparationHost()).execute()

    def preparation_name_matcher_fit(self, namespace: str,
            rows: tuple[tuple[str, str], ...], *,
            right: str = 'R', left: str = 'L', middle: str = '',
            side_before_name: bool = False,
            side_underscore: bool = True, template_name=None, preparation=None):
        from maya import cmds
        from adv_py.adapters.maya_source_skeleton_fit import (
            MayaSourceSkeletonFitHost)
        from adv_py.application.name_matcher_fit import BuildNameMatchedFit
        from adv_py.core.name_matcher_fit import NameMatcherRow, NameMatcherRules

        selection = cmds.ls(selection=True, long=True, type='joint') or []
        if len(selection) != 1:
            raise ValueError('NameMatcher 请只选中来源骨架根关节')
        target_namespace, created = _target_for_source_skeleton(
            cmds, namespace, selection[0])
        matcher_namespace_existed = cmds.namespace(exists=':NameMatcher')
        try:
            host = MayaSourceSkeletonFitHost(
                namespace=None if target_namespace == ':' else target_namespace)
            result = BuildNameMatchedFit(host).apply(selection[0],
                tuple(NameMatcherRow(*row) for row in rows),
                NameMatcherRules(right, left, middle,
                                 side_before_name, side_underscore),
                template_name=template_name,preparation=preparation)
        except Exception:
            _remove_empty_source_target(cmds, created)
            if (not matcher_namespace_existed
                    and cmds.namespace(exists=':NameMatcher')
                    and not (cmds.namespaceInfo(':NameMatcher',
                        listOnlyDependencyNodes=True, recurse=True) or [])):
                cmds.namespace(removeNamespace=':NameMatcher')
            raise
        return result, target_namespace

    def preparation_source_name_matcher_catalog(self, *,mocap=False):
        from adv_py.adapters.maya_source_name_matcher import source_name_matcher_catalog
        return source_name_matcher_catalog(mocap=mocap)

    def preparation_source_name_matcher_template(self, name, *,mocap=False):
        from adv_py.adapters.maya_source_name_matcher import source_name_matcher_template_path
        from adv_py.core.source_name_matcher import read_source_name_matcher_template
        path = source_name_matcher_template_path(name,mocap=mocap)
        return read_source_name_matcher_template(path.read_text(encoding='utf-8-sig'))

    def preparation_name_matcher_check(self, namespace: str, source_root: str):
        host = self._host(namespace)
        with host.transaction('原版 NameMatcher Check'):
            return host.check_source_name_matcher(source_root)

    def preparation_source_name_matcher_export(self, destination: Path, rows, *,
            right='Right',left='Left',middle='',side_before_name=True,side_underscore=False):
        from adv_py.core.source_name_matcher import export_source_name_matcher_template
        from adv_py.core.name_matcher_fit import NameMatcherRow, NameMatcherRules
        destination = Path(destination).resolve()
        if destination.suffix.lower()!='.txt' or not destination.parent.is_dir():
            raise ValueError('NameMatcher 导出需要现有目录中的 .txt 配置文件')
        destination.write_text(export_source_name_matcher_template(
            tuple(NameMatcherRow(*row) for row in rows),
            NameMatcherRules(right,left,middle,side_before_name,side_underscore)),encoding='utf-8')
        return destination

    def preparation_name_matcher_character(self, namespace: str,
            rows: tuple[tuple[str, str], ...], *,
            right: str = 'R', left: str = 'L', middle: str = '',
            side_before_name: bool = False,
            side_underscore: bool = True, template_name=None, preparation=None):
        from maya import cmds
        from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost
        from adv_py.application.name_matcher_character import (
            BuildNameMatchedCharacter)
        from adv_py.core.name_matcher_fit import NameMatcherRow, NameMatcherRules

        selection = cmds.ls(selection=True, long=True, type='joint') or []
        if len(selection) != 1:
            raise ValueError('NameMatcher 请只选中来源骨架根关节')
        target_namespace, created = _target_for_source_skeleton(
            cmds, namespace, selection[0])
        matcher_namespace_existed = cmds.namespace(exists=':NameMatcher')
        animation_namespace_existed = cmds.namespace(
            exists=':NameMatcherKeepAnimation')
        try:
            host = MayaNameMatcherHost(
                namespace=None if target_namespace == ':'
                else target_namespace)
            result = BuildNameMatchedCharacter(host).apply(
                selection[0], tuple(NameMatcherRow(*row) for row in rows),
                NameMatcherRules(right, left, middle,
                                 side_before_name, side_underscore),
                template_name=template_name,preparation=preparation)
        except Exception:
            _remove_empty_source_target(cmds, created)
            if (not matcher_namespace_existed
                    and cmds.namespace(exists=':NameMatcher')
                    and not (cmds.namespaceInfo(':NameMatcher',
                        listOnlyDependencyNodes=True, recurse=True) or [])):
                cmds.namespace(removeNamespace=':NameMatcher')
            if (not animation_namespace_existed
                    and cmds.namespace(exists=':NameMatcherKeepAnimation')
                    and not (cmds.namespaceInfo(
                        ':NameMatcherKeepAnimation',
                        listOnlyDependencyNodes=True, recurse=True) or [])):
                cmds.namespace(removeNamespace=':NameMatcherKeepAnimation')
            raise
        return result, target_namespace

    def tools_name_matcher_connect(self, namespace: str,
            source_root: str, rows: tuple[tuple[str, str], ...], *,
            right: str = 'R', left: str = 'L', middle: str = '',
            side_before_name: bool = False,
            side_underscore: bool = True):
        from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost
        from adv_py.application.name_matcher_constraints import (
            ConnectNameMatchedSkeleton)
        from adv_py.core.name_matcher_fit import NameMatcherRow, NameMatcherRules

        host = MayaNameMatcherHost(
            namespace=None if namespace == ':' else namespace)
        return ConnectNameMatchedSkeleton(host).apply(source_root,
            tuple(NameMatcherRow(*row) for row in rows),
            NameMatcherRules(right, left, middle,
                             side_before_name, side_underscore))

    def tools_name_matcher_transfer_skin(self, namespace: str,
            source_root: str, rows: tuple[tuple[str, str], ...], *,
            right: str = 'R', left: str = 'L', middle: str = '',
            side_before_name: bool = False,
            side_underscore: bool = True):
        from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost
        from adv_py.application.name_matcher_constraints import (
            TransferNameMatchedSkinInfluences)
        from adv_py.core.name_matcher_fit import NameMatcherRow, NameMatcherRules

        host = MayaNameMatcherHost(
            namespace=None if namespace == ':' else namespace)
        return TransferNameMatchedSkinInfluences(host).apply(source_root,
            tuple(NameMatcherRow(*row) for row in rows),
            NameMatcherRules(right, left, middle,
                             side_before_name, side_underscore))

    def tools_name_matcher_mocap(self, namespace: str,
            source_root: str, rows: tuple[tuple[str, str], ...], *,
            right: str = 'R', left: str = 'L', middle: str = '',
            side_before_name: bool = False,
            side_underscore: bool = True,
            use_extra: bool = False,source_namespace=None):
        from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost
        from adv_py.application.name_matcher_mocap import ConnectNameMatchedMocap
        from adv_py.core.name_matcher_fit import NameMatcherRow, NameMatcherRules

        host = MayaNameMatcherHost(
            namespace=None if namespace == ':' else namespace)
        return ConnectNameMatchedMocap(host).apply(source_root,
            tuple(NameMatcherRow(*row) for row in rows),
            NameMatcherRules(right, left, middle,
                             side_before_name, side_underscore),
            use_extra=use_extra,source_namespace=source_namespace)

    def tools_name_matcher_keep_animation(self, namespace: str,
            source_root: str):
        from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost
        from adv_py.application.name_matcher_animation import (
            KeepNameMatchedAnimation)

        host = MayaNameMatcherHost(
            namespace=None if namespace == ':' else namespace)
        return KeepNameMatchedAnimation(host).apply(source_root)

    def tools_name_matcher_bake_kept_animation(self, namespace: str,
            source_root: str, rows: tuple[tuple[str, str], ...], *,
            right: str = 'R', left: str = 'L', middle: str = '',
            side_before_name: bool = False,
            side_underscore: bool = True):
        from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost
        from adv_py.application.name_matcher_animation import (
            BakeNameMatchedAnimation)
        from adv_py.core.name_matcher_fit import NameMatcherRow, NameMatcherRules

        host = MayaNameMatcherHost(
            namespace=None if namespace == ':' else namespace)
        return BakeNameMatchedAnimation(host).apply(source_root,
            tuple(NameMatcherRow(*row) for row in rows),
            NameMatcherRules(right, left, middle,
                             side_before_name, side_underscore))

    def tools_name_matcher_zero_out(self, namespace: str,
            source_root: str, rows: tuple[tuple[str, str], ...], *,
            right: str = 'R', left: str = 'L', middle: str = '',
            side_before_name: bool = False,
            side_underscore: bool = True,template_name=None,source_namespace=None):
        from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost
        from adv_py.application.name_matcher_mocap_operations import (
            ZeroOutNameMatchedMocap)
        from adv_py.core.name_matcher_fit import NameMatcherRow, NameMatcherRules

        host = MayaNameMatcherHost(
            namespace=None if namespace == ':' else namespace)
        return ZeroOutNameMatchedMocap(host).apply(source_root,
            tuple(NameMatcherRow(*row) for row in rows),
            NameMatcherRules(right, left, middle,
                             side_before_name, side_underscore),template_name=template_name,
            source_namespace=source_namespace)

    def tools_source_mocap_matcher(self,namespace: str):
        from .maya_source_mocap_mapping_ui import show_mocap_matcher
        return show_mocap_matcher(self,namespace)

    def tools_name_matcher_bake(self, namespace: str):
        from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost
        from adv_py.application.name_matcher_mocap_operations import (
            BakeNameMatchedMocap)

        host = MayaNameMatcherHost(
            namespace=None if namespace == ':' else namespace)
        return BakeNameMatchedMocap(host).apply()

    def tools_name_matcher_disconnect(self, namespace: str):
        from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost
        from adv_py.application.name_matcher_mocap_operations import (
            DisconnectNameMatchedMocap)

        host = MayaNameMatcherHost(
            namespace=None if namespace == ':' else namespace)
        return DisconnectNameMatchedMocap(host).apply()

    def characters(self) -> tuple[PanelCharacter, ...]:
        from adv_py.adapters.maya_scene_gateway import MayaSceneGateway
        from maya import cmds

        entries = []
        for namespace in MayaSceneGateway().namespaces():
            label = namespace or ":"
            host = self._host(label)
            resolver = ResolveBodyCharacter(host)
            names = resolver.discover()
            if not names:
                marker = "|Group.advPyFbxRigMode"
                if (label == ":" and cmds.objExists(marker)
                        and cmds.getAttr(marker) == "generic_fk_v1"):
                    body = "|Group|DeformationSystem"
                    count = len(cmds.listRelatives(body,
                        allDescendents=True, type="joint",
                        fullPath=True) or ())
                    entries.append(PanelCharacter(label, False,
                                                  joint_count=count,
                                                  mode="generic_fk"))
                else:
                    entries.append(PanelCharacter(label, False))
                continue
            try:
                registration = resolver.execute(names[0])
                entries.append(PanelCharacter(label, True,
                    len(registration.body), len(registration.channels)))
            except ValueError as error:
                entries.append(PanelCharacter(label, False, issue=str(error)))
        return tuple(entries)

    def fit_export(self, namespace: str, destination: Path,
                   container: str = "FitSkeleton", *,
                   external_compatibility: bool = False) -> int:
        if external_compatibility:
            result = ExportExternalFitSkeleton(self._host(namespace)).apply(
                destination, container)
            return len(result.document.joints)
        result = ExportFitSkeleton(self._host(namespace)).apply(
            destination, container)
        return len(result.plan.document.joints)

    def fit_import(self, namespace: str, source: Path,
                   container: str = "FitSkeleton") -> int:
        result = CreateAndImportFitSkeleton(self._host(namespace)).apply(
            source, container)
        return len(result.joint_paths)

    def fit_source_asset_catalog(self, *, limbs=False):
        from adv_py.adapters.maya_source_fit_import import source_fit_asset_catalog
        return source_fit_asset_catalog(limbs=limbs)

    def fit_source_import_has_joints(self, namespace: str):
        c = self._host(namespace)._cmds
        return bool(c.objExists('FitSkeleton') and c.listRelatives(
            'FitSkeleton',allDescendents=True,type='joint'))

    def fit_source_import(self, namespace: str, source: Path, *, merge=False, policy='existing',
                          preparation=None):
        host = self._host(namespace)
        with host.transaction('导入原版 Fit 模板'):
            joints = host.import_source_fit_scene(source,merge=merge,policy=policy)
            if preparation is not None:
                host.save_source_fit_preparation(preparation)
            return joints

    def fit_source_limb_import(self, namespace: str, source: Path):
        host = self._host(namespace)
        with host.transaction('导入原版 Fit 部件'):
            return host.import_source_fit_limb(source)

    def fit_source_export_is_limb(self, namespace: str):
        return self._host(namespace).source_fit_export_selection_is_limb()

    def fit_source_export(self, namespace: str, destination: Path):
        return self._host(namespace).export_source_fit_scene(destination)

    def fit_source_matcher_detect(self, namespace: str):
        return self._host(namespace).detect_source_import_matcher()

    def fit_source_matcher_prepare(self, namespace: str, detection):
        host = self._host(namespace)
        with host.transaction('导入模板后准备原版 NameMatcher'):
            return host.prepare_source_import_matcher(detection)

    def fit_source_matcher_align(self, namespace: str, detection, rows, *, template_name=None,
            preparation=None,right='Right',left='Left',middle='',side_before_name=True,side_underscore=False):
        from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost
        from adv_py.core.name_matcher_fit import NameMatcherRow,NameMatcherRules
        host = MayaNameMatcherHost(namespace=None if namespace==':' else namespace)
        with host.transaction('原版 ImportMatcher 对齐 Fit'):
            result = host.create_source_name_matched_fit(detection.source_root,
                tuple(NameMatcherRow(*row) for row in rows),
                NameMatcherRules(right,left,middle,side_before_name,side_underscore),
                template_name=template_name,preparation=preparation)
            host.mark_source_import_matcher_alignment(detection.joint)
            return result

    def fit_source_matcher_attach(self, namespace: str, source_root, rows, *,
            right='Right',left='Left',middle='',side_before_name=True,side_underscore=False):
        from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost
        from adv_py.application.source_name_matcher_attach import AttachSourceNameMatchedFit
        from adv_py.core.name_matcher_fit import NameMatcherRow,NameMatcherRules
        _ensure_body_build_centimeters()
        host = MayaNameMatcherHost(namespace=None if namespace==':' else namespace)
        return AttachSourceNameMatchedFit(host).apply(source_root,
            tuple(NameMatcherRow(*row) for row in rows),
            NameMatcherRules(right,left,middle,side_before_name,side_underscore))

    def fit_auto_scale(self, namespace: str, container: str = 'FitSkeleton', *,
                       interactive: bool = True):
        from adv_py.application.fit_auto_scale import AutoScaleFit
        from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
        from adv_py.core.preparation_objects import PreparationObjectRole
        records=MayaPreparationObjectsHost(namespace)
        from maya import cmds
        host=self._host(namespace)
        if cmds.objExists(host.scene_address('AutoPlacing')):
            from adv_py.application.fit_auto_place import FinishFitAutoPlace
            return FinishFitAutoPlace(host).apply(container,
                skin=records.existing_objects(PreparationObjectRole.SKIN),
                all_objects=records.existing_objects(PreparationObjectRole.ALL))
        host._fit_auto_place_interactive=interactive
        identity=getattr(host._cmds,'identity',None)
        def objects(role):
            names=records.read_objects(role)
            return tuple(identity.to_local(name) for name in names) if identity else names
        return AutoScaleFit(host).apply(container,
            skin=objects(PreparationObjectRole.SKIN),
            all_objects=objects(PreparationObjectRole.ALL),
            right_eye=objects(PreparationObjectRole.RIGHT_EYE))

    def fit_auto_place(self,namespace: str,container: str='FitSkeleton',*,interactive: bool=True):
        from maya import cmds
        from adv_py.application.fit_auto_place import AutoPlaceFit
        from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
        from adv_py.core.preparation_objects import PreparationObjectRole
        records=MayaPreparationObjectsHost(namespace);host=self._host(namespace)
        if cmds.objExists(host.scene_address('AutoPlacing')):
            from adv_py.application.fit_auto_place import FinishFitAutoPlace
            return FinishFitAutoPlace(host).apply(container,
                skin=records.existing_objects(PreparationObjectRole.SKIN),
                all_objects=records.existing_objects(PreparationObjectRole.ALL))
        skin=records.read_objects(PreparationObjectRole.SKIN)
        all_objects=records.read_objects(PreparationObjectRole.ALL)
        eye=records.read_objects(PreparationObjectRole.RIGHT_EYE)
        host._fit_auto_place_interactive=interactive
        identity=getattr(host._cmds,'identity',None)
        def local(nodes):return tuple(identity.to_local(node) for node in nodes) if identity else nodes
        return AutoPlaceFit(host).apply(container,skin=local(skin),all_objects=local(all_objects),right_eye=local(eye))

    def fit_create_template(self, namespace: str,
                            container: str = "FitSkeleton", *,
                            with_fingers: bool = True,
                            scale: float = 1.0) -> int:
        from adv_py.application.body_hand_fit import (
            BuildSyntheticBodyWithHandSourceFit)
        from adv_py.application.fit_container import CreateFitSkeleton
        from adv_py.application.registered_body_build import _JoinedTransactionHost
        from adv_py.application.upper_body_fit import BuildSyntheticBodySourceFit

        builder = (BuildSyntheticBodyWithHandSourceFit if with_fingers
                   else BuildSyntheticBodySourceFit)
        host = self._host(namespace)
        if host.find_name_collisions(container):
            result = builder(host).apply(container, scale=scale)
        else:
            with host.transaction("创建 Fit 容器和身体模板"):
                joined = _JoinedTransactionHost(host)
                CreateFitSkeleton(joined).apply(container)
                result = builder(joined).apply(container, scale=scale)
        return len(result.template.joint_paths)

    def selected_meshes(self) -> tuple[str, ...]:
        from maya import cmds

        meshes = []
        for node in cmds.ls(selection=True, long=True) or ():
            kind = cmds.nodeType(node)
            transform = ((cmds.listRelatives(node, parent=True,
                fullPath=True) or [None])[0] if kind == "mesh" else node)
            if (transform and cmds.nodeType(transform) == "transform"
                    and cmds.listRelatives(transform, shapes=True,
                        noIntermediate=True, type="mesh", fullPath=True)):
                meshes.append(transform)
        return tuple(dict.fromkeys(meshes))

    def fit_from_selected_skeleton(self, namespace: str,
                                   container: str = "FitSkeleton") -> tuple[int, str]:
        from maya import cmds
        from adv_py.adapters.maya_source_skeleton_fit import (
            MayaSourceSkeletonFitHost)
        from adv_py.application.source_skeleton_fit import (
            BuildFitFromSourceSkeleton)

        selection = cmds.ls(selection=True, long=True, type="joint") or []
        if len(selection) != 1:
            raise ValueError("请只选中来源骨架的根关节")
        target_namespace, created = _target_for_source_skeleton(
            cmds, namespace, selection[0])
        try:
            host = MayaSourceSkeletonFitHost(
                namespace=None if target_namespace == ":" else target_namespace)
            fit = BuildFitFromSourceSkeleton(host).apply(selection[0], container)
        except Exception:
            _remove_empty_source_target(cmds, created)
            raise
        return fit.joint_count, target_namespace

    def fit_edit_positions(self, namespace: str,
                           edits: tuple[tuple[str, tuple[float, float, float]], ...],
                           container: str = "FitSkeleton") -> int:
        patch = FitJointPositionPatch(tuple(
            FitJointPositionEdit(joint, position) for joint, position in edits))
        result = EditAndOrientFitJointPositions(
            self._host(namespace)).apply(patch, container)
        return len(result.plan.changes)

    def fit_edit_metadata(self, namespace: str, joints: tuple[str, ...],
                          field: str, value: str, *, remove: bool = False) -> int:
        key, parsed = parse_fit_metadata_value(field, value, remove=remove)
        patch = FitJointPatch((FitJointFieldEdit(key, parsed),))
        result = EditFitJointMetadata(self._host(namespace)).apply(joints, patch)
        return len(result.plan.changes)

    def fit_source_attributes(self, namespace: str, attribute: str, *,
                              remove: bool = False) -> int:
        host = self._host(namespace)
        method = (host.remove_source_fit_attributes if remove
                  else host.add_source_fit_attributes)
        return len(method(attribute))

    def fit_source_labels(self, namespace: str, label: str, *, remove=False) -> int:
        return len(self._host(namespace).edit_source_fit_labels(label, remove=remove))

    def fit_joint_display_scale(self, value=None) -> float:
        """Original Edit / joint display control; native Maya display only."""
        from maya import cmds
        if value is not None:
            cmds.jointDisplayScale(float(value))
        return float(cmds.jointDisplayScale(query=True))

    def fit_orient(self, namespace: str, joints: tuple[str, ...],
                   container: str = "FitSkeleton", *,
                   child_selections: tuple[tuple[str, str], ...] = (),
                   world: bool = False) -> int:
        request = FitOrientationRequest(joints, tuple(
            FitOrientationChildSelection(joint, child)
            for joint, child in child_selections))
        host=self._host(namespace)
        native=getattr(host,'update_source_fit_orientations',None)
        if callable(native) and not world and not child_selections:
            from adv_py.core.fit_orientation import select_fit_orientation_child,FitOrientationValidationError
            snapshot=host.capture_fit_orientation(container)
            nodes={node.path:node for node in snapshot.hierarchy.joints}
            names={node.short_name:node for node in snapshot.hierarchy.joints}
            children=[]
            for name in request.joints:
                node=nodes.get(name) or names.get(name)
                if node is None:
                    raise FitOrientationValidationError('朝向目标不在 FitSkeleton 中：'+name)
                child=select_fit_orientation_child(snapshot,node.path)
                if child is not None:children.append(child)
            with host.transaction('按原版规则更新 Fit 朝向'):
                return len(native(tuple(children),container=container) or ())
        use_case = OrientWorldFitJoints if world else OrientFitJoints
        result = use_case(host).apply(request, container)
        return len(result.plan.changes)

    def fit_resample(self, namespace: str, start: str, end: str,
                     joint_count: int, container: str = "FitSkeleton") -> int:
        from adv_py.adapters.maya_fit_resample import MayaFitResampleHost
        from adv_py.application.fit_resample import ResampleFitChain

        host = MayaFitResampleHost(
            namespace=None if namespace == ":" else namespace)
        result = ResampleFitChain(host).apply(
            start, end, joint_count, container)
        return len(result.created)

    def fit_manual_update(self, namespace: str, container: str = 'FitSkeleton'):
        host = self._host(namespace)
        with host.transaction('立即更新 Fit'):
            host.manual_update_fit(container)

    def fit_placement_snap(self, namespace: str):
        host = self._host(namespace)
        with host.transaction('吸附 Fit 到所选组件中心'):
            return host.snap_source_fit_placement()

    def fit_placement_copy(self, namespace: str):
        return self._host(namespace).copy_source_fit_placement()

    def fit_placement_paste(self, namespace: str, position):
        host = self._host(namespace)
        with host.transaction('粘贴 Fit 位置'):
            return host.paste_source_fit_placement(position)

    def fit_toggle_center_locks(self, namespace: str, container: str = 'FitSkeleton'):
        host = self._host(namespace)
        with host.transaction('切换 Fit 中心关节锁定'):
            return host.toggle_fit_center_joint_locks(container)

    def fit_toggle_mode(self, namespace: str):
        return self._host(namespace).toggle_source_fit_mode()

    def fit_pole_vector_display(self, namespace: str, enabled: bool):
        host = self._host(namespace)
        with host.transaction('切换 Fit PoleVector 显示'):
            return host.display_fit_pole_vectors(enabled)

    def fit_toggle_joint_display(self, namespace: str, kind: str):
        if kind not in ('axis','orient'):
            raise ValueError('Fit 显示需要 axis 或 orient')
        host = self._host(namespace)
        plug = 'FitSkeleton.'+('visJointAxis' if kind == 'axis' else 'visJointOrient')
        enabled = not (host._cmds.objExists(plug) and bool(host._cmds.getAttr(plug)))
        with host.transaction('切换 Fit 关节显示'):
            if kind == 'axis':host.display_fit_joint_axes(enabled)
            else:host.display_fit_joint_orient(enabled)
        return enabled

    def fit_straighten_pole_vector(self, namespace: str, limb: str):
        host = self._host(namespace)
        with host.transaction('拉直 Fit PoleVector'):
            return host.straighten_fit_pole_vector(limb)

    def fit_finger_up_display(self, namespace: str, enabled: bool):
        host = self._host(namespace)
        with host.transaction('切换 Fit Finger-up 显示'):
            return host.display_fit_finger_up(enabled)

    def fit_sdk_capture(self, namespace: str):
        return self._host(namespace).capture_source_fit_sdk()

    def fit_sdk_create_attribute(self, namespace: str, plan, options):
        host = self._host(namespace)
        with host.transaction('创建 Fit SDK 属性'):
            return host.create_source_fit_sdk_attribute(plan, options)

    def body_build(self, namespace: str, container: str = "FitSkeleton", *,
                   spine_segments: int | None = None,
                   head_aim: bool = False,
                   meshes: tuple[str, ...] = (),
                   maximum_influences: int | None = None,
                   segment_influences: bool = True,
                   fit_parts: bool = True) -> PanelCharacter:
        from adv_py.application.character_from_fit import BuildCharacterFromFit

        host = self._host(namespace)
        _ensure_body_build_centimeters()

        def build(build_host):
            return BuildCharacterFromFit(build_host).apply(
                container, meshes=meshes, spine_segments=spine_segments,
                maximum_influences=maximum_influences,
                include_head_aim=head_aim,
                include_segment_influences=segment_influences,
                use_fit_part_hierarchy=fit_parts)

        if not host.find_name_collisions(container):
            from maya import cmds
            from adv_py.application.fit_container import CreateFitSkeleton
            from adv_py.application.registered_body_build import (
                _JoinedTransactionHost)

            selected = cmds.ls(selection=True, long=True,
                               type="joint") or ()
            if not selected:
                raise ValueError("未找到 FitSkeleton，也没有选中的来源关节")
            # The original Build adopts the first selected chain directly.
            # The separate source-conversion action remains an explicit tool.
            with host.transaction("将选中骨架转为 Fit 并构建 Body"):
                joined = _JoinedTransactionHost(host)
                fit = CreateFitSkeleton(joined).apply(container)
                joined.parent_selected_joint_under_fit(selected[0], fit.state.path)
                result = build(joined)
        else:
            result = build(host)
        character = result.body
        return PanelCharacter(namespace, True, len(character.registration.body),
                              len(character.registration.channels),
                              segment_joint_count=len(character.segment_influences))

    def body_toggle_fit_advanced(self, namespace: str) -> bool:
        return self._host(namespace).toggle_fit_advanced_visibility()

    def body_toggle_fit_non_symmetry(self, namespace: str) -> tuple[str, ...]:
        return self._host(namespace).toggle_fit_non_symmetry_joints()

    def body_delete_advanced(self, namespace: str) -> bool:
        from adv_py.application.body_delete import DeleteBodyAdvanced

        return DeleteBodyAdvanced(self._host(namespace)).apply()

    def body_build_from_source(self, namespace: str, source_root: str,
                               container: str = "FitSkeleton", *,
                               meshes: tuple[str, ...] = (),
                               maximum_influences: int | None = None,
                               head_aim: bool = False,
                               spine_segments: int | None = None,
                               segment_influences: bool = True,
                               fit_parts: bool = True) -> PanelCharacter:
        from adv_py.adapters.maya_source_skeleton_fit import (
            MayaSourceSkeletonFitHost)
        from adv_py.application.character_from_source import (
            BuildCharacterFromSourceSkeleton)
        from maya import cmds

        if not source_root.strip():
            raise ValueError("请填写来源骨架根关节路径")
        _ensure_body_build_centimeters()
        target_namespace, created_namespace = _target_for_source_skeleton(
            cmds, namespace, source_root)
        try:
            host = MayaSourceSkeletonFitHost(
                namespace=None if target_namespace == ":" else target_namespace)
            built = BuildCharacterFromSourceSkeleton(host).apply(
                source_root, container, meshes=meshes,
                maximum_influences=maximum_influences,
                include_head_aim=head_aim,
                spine_segments=spine_segments,
                include_segment_influences=segment_influences,
                use_fit_part_hierarchy=fit_parts)
        except Exception:
            _remove_empty_source_target(cmds, created_namespace)
            raise
        character = built.character.body
        omitted = built.fit.source_only_intermediates
        names = "、".join(path.rsplit("|", 1)[-1]
                         for path in omitted[:3])
        issue = (f"来源骨架有 {len(omitted)} 个主链中间关节未进入新角色："
                 f"{names}{'等' if len(omitted) > 3 else ''}"
                 if omitted else "")
        left_only = built.fit.source_only_left_branches
        if left_only:
            left_names = "、".join(path.rsplit("|", 1)[-1]
                                  for path in left_only[:3])
            issue += ("；" if issue else "") + (
                f"{len(left_only)} 个仅左侧来源分支未按原层级映射："
                f"{left_names}{'等' if len(left_only) > 3 else ''}")
        return PanelCharacter(target_namespace, True, len(character.registration.body),
                              len(character.registration.channels),
                              issue=issue,
                              segment_joint_count=len(character.segment_influences))

    def original_skin_migrate(self, namespace: str,
                              source_skin: str = ""):
        """Rebuild the open original character and retain its complete Skin."""
        from adv_py.adapters.maya_original_skin_migration import (
            MayaOriginalSkinMigration)

        return MayaOriginalSkinMigration().apply(
            namespace=namespace, source_skin=source_skin)

    def body_rebuild(self, namespace: str, replacement: str,
                     extensions: tuple[str, ...] = (), *,
                     spline_counts: tuple[tuple[str,int], ...] = (),
                     progress: Callable[[str], None] | None = None) -> PanelCharacter:
        if not isinstance(replacement, str) or not replacement.strip():
            raise ValueError("请填写尚未占用的重建暂存命名空间")
        _ensure_body_build_centimeters()
        host = self._host_factory(namespace="" if namespace == ":" else namespace)
        if progress:
            progress("暂存替换角色并核对需保留的数据")
        result = RebuildBodyCharacter(host).apply(replacement.strip(),
            extensions=extensions,spline_counts=spline_counts)
        if progress:
            progress("替换完成，原角色与保留数据已复核")
        return PanelCharacter(namespace, True, len(result.registration.body),
                              len(result.registration.channels),
                              segment_joint_count=len(result.segment_influences))

    def spine_replace(self, namespace: str, replacement: str,
                      skins: tuple[tuple[str, str], ...], *, start: int,
                      end: int, step: int = 1, mode: str = "fk",
                      fk_substeps: int = 1, max_mesh_error: float | None = None,
                      max_body_error: float | None = None,
                      extensions: tuple[str, ...] = (),
                      retained_assets: tuple[str, ...] = (),
                      retained_nodes: tuple[str, ...] = (),
                      retained_graph_roots: tuple[str, ...] = (),
                      progress: Callable[[str], None] | None = None):
        source = "" if namespace == ":" else namespace.strip()
        target = replacement.strip()
        if not source:
            raise ValueError("跨段数替换要求来源角色位于独立命名空间")
        if not target or target == ":" or target == source:
            raise ValueError("请选择不同于来源角色的已登记目标命名空间")
        if (not skins or any(not skin or not mesh for skin, mesh in skins)
                or len({skin for skin, _ in skins}) != len(skins)
                or len({mesh for _, mesh in skins}) != len(skins)):
            raise ValueError("每行 Skin 和网格路径须一一对应且不重复")
        if progress:
            progress("核对新旧角色、Skin、动画与需保留的用户数据")
        result = ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace=target)).apply_many(
                source, target, skins, start_frame=start, end_frame=end,
                sample_by=step, spine_mode=mode, fk_substeps=fk_substeps,
                max_mesh_error=max_mesh_error, max_body_error=max_body_error,
                extensions=extensions, retained_assets=retained_assets,
                retained_nodes=retained_nodes,
                retained_graph_roots=retained_graph_roots)
        if progress:
            progress("角色已接管原命名空间，Skin、动画与保留数据已复检")
        return result

    def control_curves_scale(self, namespace: str, controls: tuple[str, ...],
                             factor: float) -> int:
        host = self._host(namespace)
        strict = bool(controls)
        if not controls:
            c=host._cmds
            sets=tuple(name for name in ('ControlSet','FaceControlSet') if c.objExists(name))
            if not sets:raise ValueError('当前角色没有 ControlSet 或 FaceControlSet')
            selected=c.ls(selection=True,long=True) or []
            controls=tuple(node for node in selected if any(c.sets(node,isMember=name) for name in sets))
            if not controls:
                controls=tuple(dict.fromkeys(node for name in sets for node in c.sets(name,query=True) or []))
        raw=getattr(host._cmds,'raw',host._cmds)
        if (raw.getModifiers()//4)%2:
            if factor==0:raise ValueError('Ctrl 反向缩放不能使用零倍率')
            factor=1./factor
        result = ScaleControlCurves(host).apply(controls, factor, strict=strict)
        return len(result.verified)

    def control_curves_color(self, namespace: str, controls: tuple[str, ...],
                             mode: str) -> int:
        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        registration = resolver.execute(names[0]) if len(names) == 1 else None
        semantic_map: dict[str, list[str]] = {}
        if registration:
            for channel in registration.channels:
                semantic_map.setdefault(channel.node, []).append(channel.key)
        strict = bool(controls)
        if not controls:
            if registration is None:
                raise ValueError("当前命名空间必须恰好包含一个已登记角色")
            controls = tuple(semantic_map)
        semantics = tuple(
            (control, tuple(semantic_map.get(control, ()))) for control in controls)
        result = ColorControlCurves(host).apply(
            controls, mode, semantics, strict=strict)
        return len(result.verified)

    def control_curves_auto_scale(self, namespace: str,
                                  controls: tuple[str, ...], mesh: str) -> int:
        host = self._host(namespace)
        strict = bool(controls)
        if not controls:
            controls=tuple(host._cmds.ls(selection=True,long=True) or [])
        result = AutoScaleControlCurves(host).apply(
            controls, mesh.strip(), strict=strict)
        return len(result.verified)

    def control_curves_palette(self,namespace,controls,index,*,rgb=None):
        from adv_py.application.control_curve_style import SetControlCurvePalette
        host=self._host(namespace)
        controls=tuple(controls) or tuple(host._cmds.ls(selection=True,long=True) or [])
        return SetControlCurvePalette(host).apply(controls,index,rgb=rgb)

    def control_curve_palette_colors(self):
        from maya import cmds
        return ((0.,0.,0.),)+tuple(tuple(cmds.colorIndex(index,query=True)) for index in range(1,32))

    def select_control_curves(self,namespace,controller_type,side):
        from adv_py.application.control_curve_selection import SelectControlCurves
        return SelectControlCurves(self._host(namespace)).apply(controller_type,side)

    def control_curves_width(self,namespace,controls,width):
        from adv_py.application.control_curve_style import SetControlCurveWidth
        host=self._host(namespace)
        controls=tuple(controls) or tuple(host._cmds.ls(selection=True,long=True) or [])
        return SetControlCurveWidth(host).apply(controls,width)

    def control_curves_snap_rotate(self,namespace,controls,axis):
        from adv_py.application.control_curve_style import SnapRotateControlCurves
        host=self._host(namespace)
        controls=tuple(controls) or tuple(host._cmds.ls(selection=True,long=True) or [])
        return SnapRotateControlCurves(host).apply(controls,axis)

    def control_curves_mirror(self, namespace: str, controls: tuple[str, ...],
                              source_side: str) -> int:
        if source_side not in ('R', 'L'):
            raise ValueError('镜像来源侧必须是 R 或 L')
        from adv_py.adapters.maya_source_control_curve_mirror import mirror_source_control_curves
        host = self._host(namespace)
        with host.transaction('原版控制曲线镜像'):
            return len(mirror_source_control_curves(host,source_side=='L',
                'ControlSet',controls=controls or None))

    def control_curves_swap(self, namespace: str, targets: tuple[str, ...],
                            source: str) -> int:
        if not targets or not source.strip():
            raise ValueError("曲线替换需要至少一个目标控制器和一个自定义曲线")
        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        if len(names) != 1:
            raise ValueError("当前命名空间必须恰好包含一个已登记角色")
        registration = resolver.execute(names[0])
        registered = tuple(dict.fromkeys(
            channel.node for channel in registration.channels))
        resolved = []
        for target in targets:
            matches = [path for path in registered
                       if path == target or path.rsplit("|", 1)[-1] == target]
            if len(matches) != 1:
                raise ValueError(f"替换目标未登记或名称不唯一：{target}")
            resolved.append(matches[0])
        result = SwapControlCurves(host).apply(
            source.strip(), tuple(dict.fromkeys(resolved)))
        return len(result.verified)

    def create_control_mesh(self, namespace: str, *, mirror: bool = True
                            ) -> int:
        from adv_py.adapters.maya_control_mesh import MayaControlMeshHost
        from adv_py.application.control_mesh import CreateControlMesh

        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        if len(names) != 1:
            raise ValueError("当前命名空间必须恰好包含一个已登记角色")
        registration = resolver.execute(names[0])
        globals_ = {channel.node for channel in registration.channels
                    if channel.key.startswith("global.")}
        if len(globals_) != 1:
            raise ValueError("角色总控登记无效")
        items = CreateControlMesh(MayaControlMeshHost()).execute(
            globals_.pop(), mirror=mirror)
        return len(items)

    def create_control_meshes(self, namespace: str) -> int:
        from adv_py.adapters.maya_control_mesh import MayaControlMeshHost
        from adv_py.application.control_mesh import CreateControlMeshes

        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        if len(names) != 1:
            raise ValueError("当前命名空间必须恰好包含一个已登记角色")
        registration = resolver.execute(names[0])
        global_controls = {channel.node for channel in registration.channels
                           if channel.key.startswith("global.")}
        if len(global_controls) != 1:
            raise ValueError("角色总控登记无效")
        pose = host.read_body_build_pose()
        current = host.capture_current_body_build_pose(pose)
        observed = {(item.node, item.attribute): item.value
                    for item in current.values}
        if any(abs(observed.get((item.node, item.attribute),
                                float("inf")) - item.value) > 1e-3
               for item in pose.values):
            raise ValueError("批量 Control Mesh 须先返回 Body 构建姿态")
        controls = tuple(dict.fromkeys(channel.node
                          for channel in registration.channels))
        items = CreateControlMeshes(MayaControlMeshHost()).execute(
            global_controls.pop(), controls)
        return len(items)

    def colorize_control_meshes(self, namespace: str) -> int:
        from adv_py.adapters.maya_control_mesh import MayaControlMeshHost
        from adv_py.application.control_mesh_color import ColorizeControlMeshes

        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        if len(names) != 1:
            raise ValueError("当前命名空间必须恰好包含一个已登记角色")
        registration = resolver.execute(names[0])
        controls = tuple(dict.fromkeys(channel.node
                          for channel in registration.channels))
        items = ColorizeControlMeshes(MayaControlMeshHost()).execute(controls)
        return len(items)

    def create_ik_control_meshes(self, namespace: str) -> int:
        from adv_py.adapters.maya_control_mesh import MayaControlMeshHost
        from adv_py.application.ik_control_mesh import CreateIKControlMeshes

        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        if len(names) != 1:
            raise ValueError("当前命名空间必须恰好包含一个已登记角色")
        registration = resolver.execute(names[0])
        globals_ = {channel.node for channel in registration.channels
                    if channel.key.startswith("global.")}
        if len(globals_) != 1:
            raise ValueError("角色总控登记无效")
        items = CreateIKControlMeshes(MayaControlMeshHost()).execute(
            globals_.pop())
        return len(items)

    def delete_control_meshes(self, namespace: str, *,
                              selected_only: bool) -> int:
        from adv_py.adapters.maya_control_mesh import MayaControlMeshHost
        from adv_py.application.control_mesh_delete import DeleteControlMeshes

        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        if len(names) != 1:
            raise ValueError("当前命名空间必须恰好包含一个已登记角色")
        registration = resolver.execute(names[0])
        globals_ = {channel.node for channel in registration.channels
                    if channel.key.startswith("global.")}
        if len(globals_) != 1:
            raise ValueError("角色总控登记无效")
        items = DeleteControlMeshes(MayaControlMeshHost()).execute(
            globals_.pop(), selected_only=selected_only)
        return sum(len(item.shapes) for item in items)

    def control_curves_copy_to_variant(
            self, namespace: str, controls: tuple[str, ...],
            variant: str) -> int:
        from adv_py.application.control_curve_variants import (
            CopyControlCurvesToVariants)

        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        if len(names) != 1:
            raise ValueError("当前命名空间必须恰好包含一个已登记角色")
        registration = resolver.execute(names[0])
        registered = tuple(dict.fromkeys(
            channel.node for channel in registration.channels))
        if controls:
            resolved = []
            for requested in controls:
                matches = [path for path in registered if (
                    path == requested
                    or path.rsplit("|", 1)[-1] == requested)]
                if len(matches) != 1:
                    raise ValueError("控制器未登记或名称不唯一：" + requested)
                resolved.append(matches[0])
            controls = tuple(dict.fromkeys(resolved))
        else:
            controls = registered
        return CopyControlCurvesToVariants(host).apply(controls, variant)

    def control_orient_axis(self, namespace: str, controls: tuple[str, ...],
                            primary: str, secondary: str,
                            curve_unaffected: bool = False,
                            mirror: bool = False,
                            mirrored_behavior: bool = False,
                            mirrored_translate: bool = False) -> int:
        from adv_py.core.original_control_orientation import OriginalControlOrientOptions
        return self._original_control_orient(namespace, controls,
            OriginalControlOrientOptions(primary, secondary,
                curve_unaffected=curve_unaffected, mirror=mirror,
                mirrored_behaviour=mirrored_behavior, mirrored_translate=mirrored_translate))

    def _original_control_orient(self, namespace, controls, options):
        from adv_py.application.original_control_orientation import SetOriginalControlOrientations
        host, resolved = self._control_orient_targets(
            namespace, controls, False)
        return len(SetOriginalControlOrientations(host).apply(resolved, options))

    def control_orient_world(self, namespace: str, controls: tuple[str, ...],
                             curve_unaffected: bool = False,
                             mirror: bool = False,
                             mirrored_behavior: bool = False,
                             mirrored_translate: bool = False,
                             primary: str = 'X', secondary: str = 'Y') -> int:
        from adv_py.core.original_control_orientation import OriginalControlOrientOptions
        return self._original_control_orient(namespace, controls,
            OriginalControlOrientOptions(primary, secondary, world_orient=True,
                curve_unaffected=curve_unaffected, mirror=mirror,
                mirrored_behaviour=mirrored_behavior, mirrored_translate=mirrored_translate))

    def control_orient_world_axis_match(
            self, namespace: str, controls: tuple[str, ...],
            curve_unaffected: bool = False,
            mirror: bool = False,
            mirrored_behavior: bool = False,
            mirrored_translate: bool = False,
            primary: str = 'X', secondary: str = 'Y') -> int:
        from adv_py.core.original_control_orientation import OriginalControlOrientOptions
        return self._original_control_orient(namespace, controls,
            OriginalControlOrientOptions(primary, secondary, world_match=True,
                curve_unaffected=curve_unaffected, mirror=mirror,
                mirrored_behaviour=mirrored_behavior, mirrored_translate=mirrored_translate))

    def _control_orient_targets(self, namespace, controls, mirror):
        host = self._host(namespace)
        if not controls:
            controls = tuple(host._cmds.ls(selection=True, long=True) or [])
        if not controls:
            raise ValueError("请先选择控制器")
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        if len(names) != 1:
            raise ValueError("当前命名空间必须恰好包含一个已登记角色")
        registration = resolver.execute(names[0])
        registered = tuple(dict.fromkeys(
            channel.node for channel in registration.channels))
        resolved = []
        for control in controls:
            matches = [path for path in registered
                       if path == control or path.rsplit("|", 1)[-1] == control]
            if len(matches) != 1:
                raise ValueError(f"控制器未登记或名称不唯一：{control}")
            resolved.append(matches[0])
        if mirror:
            registered_set = set(registered)
            for source in tuple(resolved):
                for marker, opposite in (("_R", "_L"), ("_L", "_R")):
                    if re.search(re.escape(marker) + r"(?=(?:FK|IK|PV|Offset)?(?:\||$))", source):
                        target = re.sub(re.escape(marker) + r"(?=(?:FK|IK|PV|Offset)?(?:\||$))",
                                        opposite, source)
                        if target in registered_set:
                            resolved.append(target)
                        break
        return host, tuple(dict.fromkeys(resolved))

    def control_orient_custom_detach(self, namespace: str) -> tuple[str, ...]:
        from adv_py.application.original_control_orientation import DetachOriginalControlOrientations
        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        if len(names) != 1:
            raise ValueError("当前命名空间必须恰好包含一个已登记角色")
        resolver.execute(names[0])
        return DetachOriginalControlOrientations(host).apply()

    def control_orient_custom_attach(self, namespace: str, mirror: bool = True) -> int:
        from adv_py.application.original_control_orientation import AttachOriginalControlOrientations
        host = self._host(namespace)
        return AttachOriginalControlOrientations(host).apply(mirror=mirror)

    def custom_orient_joints(self, namespace: str, action: str,
                            primary: str = 'X', secondary: str = 'Y'):
        from adv_py.adapters import maya_original_game_skeleton as source
        operations = {'create': source.create, 'delete': source.delete,
                      'show_axis': source.show_axis, 'connect': source.connect,
                      'disconnect': source.disconnect, 'transfer_skin': source.transfer_skin}
        if action not in operations:
            raise ValueError('Custom Orient Joints 操作无效')
        host = self._host(namespace)
        with host.transaction('Original Custom Orient Joints ' + action):
            return (source.create(host, primary, secondary) if action == 'create'
                    else operations[action](host))

    def custom_softmod_create(self, namespace: str, deformer: str,
                              base_name: str, parent_joint: str = "",
                              *, face: bool = False, middle: bool = False,
                              local: bool = True, mirror: bool = True):
        from adv_py.adapters.maya_custom_controller import MayaCustomControllerHost
        from adv_py.application.custom_controller import BuildCustomController
        from adv_py.core.custom_controller import CustomControlKind

        host = MayaCustomControllerHost(
            namespace=None if namespace == ":" else namespace, face=face)
        return BuildCustomController(host).apply(
            deformer, CustomControlKind.SOFT_MOD, base_name,
            parent_joint=parent_joint or None,
            middle=middle, local=local, mirror=mirror).state

    def custom_softmod_tool(self) -> None:
        from maya import mel

        mel.eval("SoftModTool;")

    def custom_cluster_create(self, namespace: str, deformer: str,
                              base_name: str, parent_joint: str = "",
                              *, face: bool = False, middle: bool = False,
                              local: bool = True, mirror: bool = True):
        from adv_py.adapters.maya_custom_controller import MayaCustomControllerHost
        from adv_py.application.custom_controller import BuildCustomController
        from adv_py.core.custom_controller import CustomControlKind

        host = MayaCustomControllerHost(
            namespace=None if namespace == ":" else namespace, face=face)
        return BuildCustomController(host).apply(
            deformer, CustomControlKind.CLUSTER, base_name,
            parent_joint=parent_joint or None,
            middle=middle, local=local, mirror=mirror).state

    def custom_skin_create(self, namespace: str, deformer: str,
                           base_name: str, parent_joint: str = "",
                           *, face: bool = False, middle: bool = False,
                           local: bool = True,
                           partial_parent: bool = False,
                           skin_cluster: str | None = None,
                           mirror: bool = True):
        from adv_py.adapters.maya_custom_controller import MayaCustomControllerHost
        from adv_py.application.custom_controller import BuildCustomController
        from adv_py.core.custom_controller import CustomControlKind

        host = MayaCustomControllerHost(
            namespace=None if namespace == ":" else namespace, face=face)
        return BuildCustomController(host).apply(
            deformer, CustomControlKind.SKIN, base_name,
            parent_joint=parent_joint or None,
            middle=middle, local=local,
            partial_parent=partial_parent,
            skin_cluster=skin_cluster, mirror=mirror).state

    def custom_softmod_add_mesh(self, namespace: str, control: str,
                                mesh: str, *, face: bool = False):
        from adv_py.adapters.maya_custom_controller import MayaCustomControllerHost
        from adv_py.application.custom_controller import ExtendSoftModController

        host = MayaCustomControllerHost(
            namespace=None if namespace == ":" else namespace, face=face)
        return ExtendSoftModController(host).apply(control, mesh)

    def custom_cluster_paint(self, namespace: str, control: str,
                             *, face: bool = False):
        from adv_py.adapters.maya_custom_controller import MayaCustomControllerHost
        from adv_py.application.custom_controller import PaintClusterControlWeights

        host = MayaCustomControllerHost(
            namespace=None if namespace == ":" else namespace, face=face)
        return PaintClusterControlWeights(host).apply(control)

    def custom_cluster_mirror(self, namespace: str, control: str,
                              *, face: bool = False):
        from adv_py.adapters.maya_custom_controller import MayaCustomControllerHost
        from adv_py.application.custom_controller import MirrorClusterControlWeights

        host = MayaCustomControllerHost(
            namespace=None if namespace == ":" else namespace, face=face)
        return MirrorClusterControlWeights(host).apply(control)

    def custom_control_delete(self, namespace: str, control: str,
                              *, face: bool = False):
        from adv_py.adapters.maya_custom_controller import MayaCustomControllerHost
        from adv_py.application.custom_controller import DeleteCustomController

        host = MayaCustomControllerHost(
            namespace=None if namespace == ":" else namespace, face=face)
        return DeleteCustomController(host).apply(control)

    def partial_joints_create(self, namespace: str, *, count: int = 1,
                              include_controller: bool = False,
                              auto_bind: bool = False):
        from adv_py.adapters.maya_partial_joints import MayaPartialJointsHost
        from adv_py.application.partial_joints import CreatePartialJoints

        host = MayaPartialJointsHost(
            namespace=None if namespace == ":" else namespace)
        return CreatePartialJoints(host).apply(
            count=count, include_controller=include_controller,
            auto_bind=auto_bind)

    def partial_joints_delete(self, namespace: str):
        from adv_py.adapters.maya_partial_joints import MayaPartialJointsHost
        from adv_py.application.partial_joints import DeletePartialJoints

        host = MayaPartialJointsHost(
            namespace=None if namespace == ":" else namespace)
        return DeletePartialJoints(host).apply()

    def unreal_joints_create(self, namespace: str):
        from adv_py.adapters.maya_unreal_joints import MayaUnrealJointsHost
        from adv_py.application.unreal_joints import CreateUnrealJoints

        host = MayaUnrealJointsHost(
            namespace=None if namespace == ":" else namespace)
        return CreateUnrealJoints(host).apply()

    def unreal_joints_delete(self, namespace: str) -> None:
        from adv_py.adapters.maya_unreal_joints import MayaUnrealJointsHost
        from adv_py.application.unreal_joints import DeleteUnrealJoints

        host = MayaUnrealJointsHost(
            namespace=None if namespace == ":" else namespace)
        DeleteUnrealJoints(host).apply()

    def unreal_mannequin_create(self, namespace: str, template_path: str,
                                template: str, scale_to_match: bool,
                                match_pose: bool, *, ctrl_button=None):
        from adv_py.adapters.maya_unreal_mannequin import MayaMannequinHost
        from adv_py.application.unreal_mannequin import CreateMannequin
        from adv_py.adapters.maya_unreal_asset import unreal_asset

        host = MayaMannequinHost(
            namespace=None if namespace == ":" else namespace,
            ctrl_button=ctrl_button)
        return CreateMannequin(host).apply(
            str(unreal_asset(template_path)), template=template,
            scale_adv_to_template=scale_to_match,
            match_template_pose=match_pose)

    def unreal_mannequin_transfer_skin(self, namespace: str) -> int:
        from adv_py.adapters.maya_unreal_mannequin import MayaMannequinHost
        from adv_py.application.unreal_mannequin import TransferMannequinSkin

        host = MayaMannequinHost(
            namespace=None if namespace == ":" else namespace)
        return TransferMannequinSkin(host).apply()

    def unreal_mannequin_delete(self, namespace: str) -> None:
        from adv_py.adapters.maya_unreal_mannequin import MayaMannequinHost
        from adv_py.application.unreal_mannequin import DeleteMannequin

        host = MayaMannequinHost(
            namespace=None if namespace == ":" else namespace)
        DeleteMannequin(host).apply()

    def unreal_mannequin_export(self, namespace: str, destination,
                                template_path: str, options, *, ctrl_button=None):
        from adv_py.adapters.maya_unreal_mannequin import MayaMannequinHost
        from adv_py.application.unreal_mannequin_export import ExportMannequin
        from adv_py.adapters.maya_unreal_asset import unreal_asset

        host = MayaMannequinHost(
            namespace=None if namespace == ":" else namespace,
            ctrl_button=ctrl_button)
        return ExportMannequin(host).apply(destination, str(unreal_asset(template_path)),
                                           options=options)

    def unreal_face_solver_export(self, namespace: str, destination):
        from adv_py.adapters.maya_unreal_face_solver import MayaUnrealFaceSolverHost
        from adv_py.application.unreal_face_solver import ExportUnrealFaceSolver

        host = MayaUnrealFaceSolverHost(
            namespace=None if namespace == ":" else namespace)
        return ExportUnrealFaceSolver(host).apply(destination)

    def original_fbx_export(self, namespace: str, destination=None):
        from adv_py.adapters.maya_original_fbx_export import MayaOriginalFbxExportHost
        from adv_py.application.original_fbx_export import ExportOriginalFbx

        host = MayaOriginalFbxExportHost(
            namespace=None if namespace == ':' else namespace)
        return ExportOriginalFbx(host).apply(destination)

    def original_body_rig_export(self, namespace: str, destination):
        from adv_py.adapters.maya_original_body_rig import MayaOriginalBodyRigHost
        from adv_py.application.original_body_rig import ExportOriginalBodyRig

        host = MayaOriginalBodyRigHost(
            namespace=None if namespace == ':' else namespace)
        return ExportOriginalBodyRig(host).apply(destination)

    def original_export_preparation(self, namespace: str, operation: str):
        from adv_py.adapters.maya_original_export_preparation import MayaOriginalExportPreparationHost
        from adv_py.application.original_export_preparation import PrepareOriginalExport

        host = MayaOriginalExportPreparationHost(
            namespace=None if namespace == ':' else namespace)
        return PrepareOriginalExport(host).apply(operation)

    def roblox_dynamic_head_export(self, namespace: str, geometry: str):
        from adv_py.adapters.maya_original_export_preparation import MayaOriginalExportPreparationHost
        from adv_py.application.original_export_preparation import PrepareRobloxDynamicHead

        host = MayaOriginalExportPreparationHost(
            namespace=None if namespace == ':' else namespace)
        return PrepareRobloxDynamicHead(host).apply(geometry)

    def unreal_twist_hierarchy(self, namespace: str, enable: bool) -> int:
        from adv_py.adapters.maya_unreal_twist import MayaUnrealTwistHost
        from adv_py.application.unreal_twist import SetUnrealTwistHierarchy

        host = MayaUnrealTwistHost(
            namespace=None if namespace == ":" else namespace)
        return SetUnrealTwistHierarchy(host).apply(enable)

    def game_engine_scaling(self, namespace: str, enable: bool) -> int:
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.application.body_game_scaling import SwitchBodyGameScaling

        host = MayaBodyBuildHost(
            namespace=None if namespace == ":" else namespace)
        plan = SwitchBodyGameScaling(host).apply(enable=enable)
        return len(plan.joints)

    def game_engine_root_motion(self, namespace: str, create: bool):
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.application.body_game_root_motion import SwitchGameRootMotion

        host = MayaBodyBuildHost(
            namespace=None if namespace == ":" else namespace)
        return SwitchGameRootMotion(host).apply(create=create)

    def rig_display(self, namespace: str, operation: str,
                    value: bool | float):
        from adv_py.adapters.maya_rig_display import MayaRigDisplayHost
        from adv_py.application.rig_display import SetRigDisplay

        host = MayaRigDisplayHost(
            namespace=None if namespace == ":" else namespace)
        return SetRigDisplay(host).apply(operation, value)

    def remove_unused_skin_influences(self, namespace: str) -> tuple[int, int]:
        from adv_py.adapters.maya_skin_optimize import MayaSkinOptimizeHost
        from adv_py.application.skin_optimize import RemoveUnusedSkinInfluences

        host = MayaSkinOptimizeHost(
            namespace=None if namespace == ":" else namespace)
        return RemoveUnusedSkinInfluences(host).apply()

    def prune_small_skin_weights(self, namespace: str) -> int:
        from adv_py.adapters.maya_skin_optimize import MayaSkinOptimizeHost
        from adv_py.application.skin_optimize import PruneSmallSkinWeights

        host = MayaSkinOptimizeHost(
            namespace=None if namespace == ":" else namespace)
        return PruneSmallSkinWeights(host).apply()

    def original_optimize(self, namespace: str, operation: str):
        from adv_py.adapters.maya_original_optimize import MayaOriginalOptimizeHost
        from adv_py.application.original_optimize import OptimizeOriginalRig
        host = MayaOriginalOptimizeHost(namespace=None if namespace == ':' else namespace)
        return OptimizeOriginalRig(host).apply(operation)

    def decompose_original_opm(self, namespace: str):
        from adv_py.adapters.maya_original_opm_decomposition import MayaOriginalOpmDecompositionHost
        from adv_py.application.original_opm_decomposition import DecomposeOriginalOffsetParentMatrices
        host = MayaOriginalOpmDecompositionHost(namespace=None if namespace == ':' else namespace)
        return DecomposeOriginalOffsetParentMatrices(host).apply()

    def original_publish(self, namespace: str):
        from adv_py.adapters.maya_original_publish import MayaOriginalPublishHost
        from adv_py.application.original_publish import PublishOriginalScene
        from maya import mel
        # This callback executes only the user's explicitly configured custom
        # extension. Built-in ADV templates are dispatched to Python first.
        host = MayaOriginalPublishHost(namespace=None if namespace == ':' else namespace,
                                       script_runner=mel.eval)
        return PublishOriginalScene(host).apply()

    def original_model_update(self, namespace: str, operation: str):
        if operation == 'face_fitting_update':
            from adv_py.adapters.maya_original_face_fitting_update import MayaOriginalFaceFittingUpdateHost
            from adv_py.application.original_face_fitting_update import UpdateOriginalFaceFitting
            return UpdateOriginalFaceFitting(MayaOriginalFaceFittingUpdateHost(
                namespace=None if namespace == ':' else namespace)).apply()
        from adv_py.adapters.maya_original_model_updates import MayaOriginalModelUpdatesHost
        from adv_py.application.original_model_updates import UpdateOriginalModel
        host = MayaOriginalModelUpdatesHost(namespace=None if namespace == ':' else namespace)
        return UpdateOriginalModel(host).apply(operation)

    def original_publish_reference_layers(self, namespace: str):
        from adv_py.adapters.maya_original_publish import MayaOriginalPublishHost
        host = MayaOriginalPublishHost(namespace=None if namespace == ':' else namespace)
        with host.transaction('Set DisplayLayers to R'):
            return host.set_original_display_layers_to_reference()

    def original_publish_build_pose(self, namespace: str):
        from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
        host = MayaOriginalFaceBuildHost(namespace=None if namespace == ':' else namespace)
        body = host.read_body_build_pose()
        host.preflight_body_build_pose(body)
        face = host.read_face_build_pose() if host._cmds.objExists('FaceControlSet') else None
        if face is not None:
            host.preflight_face_build_pose(face)
        with host.transaction('Go to Build Pose'):
            host.apply_body_build_pose(body)
            if face is not None:
                host.apply_face_build_pose(face)
        return len(body.values) + (len(face.values) if face is not None else 0)

    def original_publish_entries(self, namespace: str):
        from adv_py.adapters.maya_original_publish import MayaOriginalPublishHost
        from adv_py.core.original_publish import original_publish_entries
        host = MayaOriginalPublishHost(namespace=None if namespace == ':' else namespace)
        return original_publish_entries(host.original_publish_options())

    def original_publish_save_entry(self, namespace: str, name: str, script: str):
        from adv_py.adapters.maya_original_publish import MayaOriginalPublishHost
        host = MayaOriginalPublishHost(namespace=None if namespace == ':' else namespace)
        return host.set_original_publish_option(name, script)

    def original_publish_delete_entry(self, namespace: str, index: int):
        from adv_py.adapters.maya_original_publish import MayaOriginalPublishHost
        host = MayaOriginalPublishHost(namespace=None if namespace == ':' else namespace)
        host.remove_original_publish_option(index)

    def face_joint_reduction(self, namespace: str, kind: str, count: int):
        from adv_py.adapters.maya_original_face_reduction import MayaOriginalFaceReductionHost
        from adv_py.application.original_face_reduction import (
            ReduceOriginalEyeLidJoints, ReduceOriginalLipJoints,
        )
        host = MayaOriginalFaceReductionHost(namespace=None if namespace == ':' else namespace)
        if kind == 'EyeLid':
            return ReduceOriginalEyeLidJoints(host).apply(count)
        if kind == 'Lip':
            return ReduceOriginalLipJoints(host).apply(count)
        raise ValueError('未知面部关节缩减对象')

    def custom_face_joint_reduction(self, namespace: str, kind: str, every: int,
                                   *, preview: bool = False):
        from adv_py.adapters.maya_original_face_reduction import MayaOriginalFaceReductionHost
        from adv_py.application.original_face_reduction import CustomReduceOriginalFace
        host = MayaOriginalFaceReductionHost(namespace=None if namespace == ':' else namespace)
        return CustomReduceOriginalFace(host).apply(kind, every, preview=preview)

    def custom_face_joint_reduction_counts(self, namespace: str, kind: str, every: int):
        from adv_py.adapters.maya_original_face_reduction import MayaOriginalFaceReductionHost
        host = MayaOriginalFaceReductionHost(namespace=None if namespace == ':' else namespace)
        return host.original_custom_face_reduction_counts(kind, every)

    def unreal_rename(self, namespace: str):
        from adv_py.adapters.maya_unreal_rename import MayaUnrealRenameHost
        from adv_py.application.unreal_rename import RenameToUnreal

        host = MayaUnrealRenameHost(
            namespace=None if namespace == ":" else namespace)
        return RenameToUnreal(host).apply()

    def unreal_restore_names(self, namespace: str) -> None:
        from adv_py.adapters.maya_unreal_rename import MayaUnrealRenameHost
        from adv_py.application.unreal_rename import RestoreAdvNames

        host = MayaUnrealRenameHost(
            namespace=None if namespace == ":" else namespace)
        RestoreAdvNames(host).apply()

    def squash_controller_create(self, namespace: str, *, mirror: bool = True):
        from adv_py.adapters.maya_squash_controller import MayaSquashControllerHost
        from adv_py.application.squash_controller import CreateSquashController

        host = MayaSquashControllerHost(
            namespace=None if namespace == ":" else namespace)
        return CreateSquashController(host).apply(mirror=mirror)

    def squash_controller_delete(self, namespace: str):
        from maya import cmds
        from adv_py.adapters.maya_squash_controller import MayaSquashControllerHost
        from adv_py.application.squash_controller import DeleteSquashController

        selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []
        if len(selected) != 1:
            raise ValueError("须选择一个 Squash Controller")
        host = MayaSquashControllerHost(
            namespace=None if namespace == ":" else namespace)
        return DeleteSquashController(host).apply(selected[0])

    def human_ik_create(self, namespace: str, *,
                        create_control_rig: bool = True):
        from adv_py.adapters.maya_human_ik import MayaHumanIkHost
        from adv_py.application.human_ik import CreateHumanIk

        host = MayaHumanIkHost(
            namespace=None if namespace == ":" else namespace)
        return CreateHumanIk(host).apply(create_control_rig=create_control_rig)

    def human_ik_delete(self, namespace: str) -> None:
        from adv_py.adapters.maya_human_ik import MayaHumanIkHost
        from adv_py.application.human_ik import DeleteHumanIk

        host = MayaHumanIkHost(
            namespace=None if namespace == ":" else namespace)
        DeleteHumanIk(host).apply()

    def human_ik_bake(self, namespace: str):
        from adv_py.adapters.maya_human_ik import MayaHumanIkHost
        from adv_py.application.human_ik import BakeHumanIk

        host = MayaHumanIkHost(
            namespace=None if namespace == ":" else namespace)
        return BakeHumanIk(host).apply()

    def skin_bind(self, namespace: str, mesh: str,
                  influences: tuple[str, ...], skin: str) -> int:
        from adv_py.application.skin_bind import smooth_bind_arguments

        host = self._host(namespace)
        options = host.read_body_smooth_bind_options()
        result = BindSkin(host).apply(mesh, influences,
            skin_name=skin, **smooth_bind_arguments(options))
        return result.plan.input_state.vertex_count

    def skinning_select_deform_joints(self, namespace: str) -> int:
        from adv_py.adapters.maya_deform_skinning import select_deform_joints

        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        registration = resolver.execute(names[0]) if len(names) == 1 else None
        joints = tuple(item.path for item in registration.body) if registration else ()
        return select_deform_joints("" if namespace == ":" else namespace, joints)

    def skinning_set_smooth_bind_options(self) -> None:
        from adv_py.adapters.maya_deform_skinning import set_smooth_bind_options

        set_smooth_bind_options()

    def skin_copy_for_selected_vertices(self) -> int:
        from adv_py.adapters.maya_original_skin_operations import copy_skin_for_selected_vertices
        return copy_skin_for_selected_vertices()

    def detach_motion_system(self, namespace: str = "") -> int:
        from adv_py.adapters.maya_original_skin_operations import detach_motion_system
        return detach_motion_system(namespace)

    def attach_motion_system(self, namespace: str = "") -> int:
        from adv_py.adapters.maya_original_skin_operations import attach_motion_system
        return attach_motion_system(namespace)

    def skin_cage_create(self, namespace: str, *,
                         include_controller: bool = False) -> int:
        from adv_py.adapters.maya_skin_cage import MayaSkinCageHost
        from adv_py.application.skin_cage import CreateSkinCage

        return CreateSkinCage(MayaSkinCageHost(
            namespace, slider_include_controller=include_controller)).execute()

    def skin_cage_delete(self, namespace: str) -> int:
        from adv_py.adapters.maya_skin_cage import MayaSkinCageHost
        from adv_py.application.skin_cage import DeleteSkinCage

        return DeleteSkinCage(MayaSkinCageHost(namespace)).execute()

    def skin_cage_copy_weights(self, namespace: str) -> int:
        from adv_py.adapters.maya_skin_cage import MayaSkinCageHost
        from adv_py.application.skin_cage import CopySkinCageWeights

        return CopySkinCageWeights(MayaSkinCageHost(namespace)).execute()

    def skin_cage_mirror(self, namespace: str,
                         source_side: str, *, include_controller: bool = False) -> int:
        from adv_py.adapters.maya_skin_cage import MayaSkinCageHost
        from adv_py.application.skin_cage import MirrorSkinCage

        return MirrorSkinCage(MayaSkinCageHost(
            namespace, slider_include_controller=include_controller)).execute(
            source_side)

    def skin_cage_deformation_width(self, namespace: str) -> int:
        from adv_py.adapters.maya_skin_cage import MayaSkinCageHost
        from adv_py.application.skin_cage import SetSkinCageDeformationWidth

        return SetSkinCageDeformationWidth(
            MayaSkinCageHost(namespace)).execute()

    def skin_cage_groin_locators(self, namespace: str) -> None:
        from adv_py.adapters.maya_skin_cage import MayaSkinCageHost
        from adv_py.application.skin_cage import CreateSkinCageGroinLocators

        CreateSkinCageGroinLocators(MayaSkinCageHost(namespace)).execute()

    def skin_cage_adjust_groin(self, namespace: str, *,
                               include_controller: bool = False) -> int:
        from adv_py.adapters.maya_skin_cage import MayaSkinCageHost
        from adv_py.application.skin_cage import AdjustSkinCageGroin

        return AdjustSkinCageGroin(MayaSkinCageHost(
            namespace, slider_include_controller=include_controller)).execute()

    def skin_cage_groin_joint(self, namespace: str) -> None:
        from adv_py.adapters.maya_skin_cage import MayaSkinCageHost
        from adv_py.application.skin_cage import CreateSkinCageGroinJoint

        CreateSkinCageGroinJoint(MayaSkinCageHost(namespace)).execute()

    def skin_cage_delete_curves(self, namespace: str) -> int:
        from adv_py.adapters.maya_skin_cage import MayaSkinCageHost
        from adv_py.application.skin_cage import DeleteSkinCageCurves

        return DeleteSkinCageCurves(MayaSkinCageHost(namespace)).execute()

    def skin_cage_create_sliders(self, namespace: str, *,
                                 include_controller: bool) -> int:
        from adv_py.adapters.maya_skin_cage_sliders import MayaSkinCageSliderHost
        from adv_py.application.skin_cage_sliders import CreateSkinCageSliders

        return CreateSkinCageSliders(MayaSkinCageSliderHost(namespace)).execute(
            include_controller=include_controller)

    def skin_cage_delete_sliders(self, namespace: str) -> int:
        from adv_py.adapters.maya_skin_cage_sliders import MayaSkinCageSliderHost
        from adv_py.application.skin_cage_sliders import DeleteSkinCageSliders

        return DeleteSkinCageSliders(MayaSkinCageSliderHost(namespace)).execute()

    def sub_wrap_create_cage(self, namespace: str) -> None:
        from adv_py.adapters.maya_sub_wrap import MayaSubWrapHost
        from adv_py.application.sub_wrap import SubWrapOperations
        SubWrapOperations(MayaSubWrapHost(namespace)).create_cage()

    def sub_wrap_delete_cage(self, namespace: str) -> None:
        from adv_py.adapters.maya_sub_wrap import MayaSubWrapHost
        from adv_py.application.sub_wrap import SubWrapOperations
        SubWrapOperations(MayaSubWrapHost(namespace)).delete_cage()

    def sub_wrap_wrap_selected(self, namespace: str) -> int:
        from adv_py.adapters.maya_sub_wrap import MayaSubWrapHost
        from adv_py.application.sub_wrap import SubWrapOperations
        return SubWrapOperations(MayaSubWrapHost(namespace)).wrap_selected()

    def sub_wrap_detach(self, namespace: str) -> int:
        from adv_py.adapters.maya_sub_wrap import MayaSubWrapHost
        from adv_py.application.sub_wrap import SubWrapOperations
        return SubWrapOperations(MayaSubWrapHost(namespace)).detach()

    def sub_wrap_attach(self, namespace: str) -> int:
        from adv_py.adapters.maya_sub_wrap import MayaSubWrapHost
        from adv_py.application.sub_wrap import SubWrapOperations
        return SubWrapOperations(MayaSubWrapHost(namespace)).attach()

    def sub_wrap_exclude_selected(self, namespace: str) -> int:
        from adv_py.adapters.maya_sub_wrap import MayaSubWrapHost
        from adv_py.application.sub_wrap import SubWrapOperations
        return SubWrapOperations(MayaSubWrapHost(namespace)).exclude_selected()

    def geometry_cut_up_create(self, namespace: str) -> int:
        from adv_py.adapters.maya_geometry_cut_up import MayaGeometryCutUpHost
        from adv_py.application.geometry_cut_up import CreateGeometryCutUp
        return CreateGeometryCutUp(MayaGeometryCutUpHost(namespace)).execute()

    def geometry_skeleton_create(self, namespace: str) -> int:
        from adv_py.adapters.maya_geometry_skeleton import MayaSkeletonGeometryHost
        from adv_py.application.geometry_skeleton import CreateSkeletonGeometry

        return CreateSkeletonGeometry(MayaSkeletonGeometryHost(namespace)).execute()

    def geometry_skeleton_delete(self, namespace: str) -> None:
        from adv_py.adapters.maya_geometry_skeleton import MayaSkeletonGeometryHost
        from adv_py.application.geometry_skeleton import DeleteSkeletonGeometry

        DeleteSkeletonGeometry(MayaSkeletonGeometryHost(namespace)).execute()

    def geometry_skeleton_mirror(self, namespace: str, source_side: str) -> int:
        from adv_py.adapters.maya_geometry_skeleton import MayaSkeletonGeometryHost
        from adv_py.application.geometry_skeleton import MirrorSkeletonGeometry

        return MirrorSkeletonGeometry(MayaSkeletonGeometryHost(namespace)).execute(
            source_side)

    def geometry_muscular_create(self, namespace: str) -> tuple[int, int]:
        from adv_py.adapters.maya_geometry_muscular import MayaMuscularHost
        from adv_py.application.geometry_muscular import CreateMuscular

        return CreateMuscular(MayaMuscularHost(namespace)).execute()

    def geometry_muscular_delete(self, namespace: str) -> None:
        from adv_py.adapters.maya_geometry_muscular import MayaMuscularHost
        from adv_py.application.geometry_muscular import DeleteMuscular

        DeleteMuscular(MayaMuscularHost(namespace)).execute()

    def fit_geometry_update(self, namespace: str, *, visible=True,
                            geometry_type='boxes', gap=None) -> int:
        from adv_py.adapters.maya_fit_geometry import MayaFitGeometryHost
        from adv_py.application.fit_geometry import UpdateFitGeometry
        return UpdateFitGeometry(MayaFitGeometryHost(namespace)).execute(
            visible=visible,geometry_type=geometry_type,gap=gap)

    def geometry_poly_boxes_create(self, namespace: str) -> int:
        from adv_py.adapters.maya_geometry_poly_boxes import MayaPolyBoxesHost
        from adv_py.application.geometry_poly_boxes import CreatePolyBoxes

        return CreatePolyBoxes(MayaPolyBoxesHost(namespace)).execute()

    def geometry_poly_boxes_delete(self, namespace: str) -> None:
        from adv_py.adapters.maya_geometry_poly_boxes import MayaPolyBoxesHost
        from adv_py.application.geometry_poly_boxes import DeletePolyBoxes

        DeletePolyBoxes(MayaPolyBoxesHost(namespace)).execute()

    def geometry_poly_boxes_mirror(self, namespace: str, source_side: str) -> int:
        from adv_py.adapters.maya_geometry_poly_boxes import MayaPolyBoxesHost
        from adv_py.application.geometry_poly_boxes import MirrorPolyBoxes

        return MirrorPolyBoxes(MayaPolyBoxesHost(namespace)).execute(source_side)

    def geometry_box_skin_create(self, namespace: str) -> int:
        from adv_py.adapters.maya_geometry_box_skin import MayaBoxSkinHost
        from adv_py.application.geometry_box_skin import CreateBoxSkin

        return CreateBoxSkin(MayaBoxSkinHost(namespace)).execute()

    def geometry_box_skin_delete(self, namespace: str) -> None:
        from adv_py.adapters.maya_geometry_box_skin import MayaBoxSkinHost
        from adv_py.application.geometry_box_skin import DeleteBoxSkin

        DeleteBoxSkin(MayaBoxSkinHost(namespace)).execute()

    def geometry_boolean_create(self, namespace: str) -> int:
        from adv_py.adapters.maya_geometry_boolean import MayaBooleanHost
        from adv_py.application.geometry_boolean import CreateBoolean

        return CreateBoolean(MayaBooleanHost(namespace)).execute()

    def geometry_boolean_delete(self, namespace: str) -> None:
        from adv_py.adapters.maya_geometry_boolean import MayaBooleanHost
        from adv_py.application.geometry_boolean import DeleteBoolean

        DeleteBoolean(MayaBooleanHost(namespace)).execute()

    def geometry_warp_create(self, namespace: str) -> int:
        from adv_py.adapters.maya_geometry_warp import MayaWarpHost
        from adv_py.application.geometry_warp import CreateWarp

        return CreateWarp(MayaWarpHost(namespace)).execute()

    def geometry_warp_delete(self, namespace: str) -> None:
        from adv_py.adapters.maya_geometry_warp import MayaWarpHost
        from adv_py.application.geometry_warp import DeleteWarp

        DeleteWarp(MayaWarpHost(namespace)).execute()

    def geometry_mannequin_create(self, namespace: str) -> int:
        from adv_py.adapters.maya_geometry_mannequin import MayaMannequinHost
        from adv_py.application.geometry_mannequin import CreateMannequin

        return CreateMannequin(MayaMannequinHost(namespace)).execute()

    def geometry_mannequin_delete(self, namespace: str) -> None:
        from adv_py.adapters.maya_geometry_mannequin import MayaMannequinHost
        from adv_py.application.geometry_mannequin import DeleteMannequin

        DeleteMannequin(MayaMannequinHost(namespace)).execute()

    def geometry_cut_up_delete(self, namespace: str) -> None:
        from adv_py.adapters.maya_geometry_cut_up import MayaGeometryCutUpHost
        from adv_py.application.geometry_cut_up import DeleteGeometryCutUp
        DeleteGeometryCutUp(MayaGeometryCutUpHost(namespace)).execute()

    def skin_cage_print_reuse(self, namespace: str, *, transforms: bool,
                              shapes: bool, catch: bool) -> int:
        from adv_py.adapters.maya_skin_cage import MayaSkinCageHost

        return MayaSkinCageHost(namespace).print_reuse_commands(
            transforms=transforms, shapes=shapes, catch=catch)

    def skin_loops_create(self, namespace: str, *, mirror: bool = True) -> int:
        from adv_py.adapters.maya_skin_loops import MayaSkinLoopsHost
        from adv_py.application.skin_loops import CreateSkinLoops

        host = MayaSkinLoopsHost("" if namespace == ":" else namespace)
        return len(CreateSkinLoops(host).execute(mirror=mirror))

    def skin_loops_select_all(self, namespace: str) -> int:
        from adv_py.adapters.maya_skin_loops import MayaSkinLoopsHost
        from adv_py.application.skin_loops import SelectAllSkinLoops

        host = MayaSkinLoopsHost("" if namespace == ":" else namespace)
        return SelectAllSkinLoops(host).execute()

    def skin_loops_copy_weights(self, namespace: str) -> int:
        from adv_py.adapters.maya_skin_loops import MayaSkinLoopsHost
        from adv_py.application.skin_loops import CopySkinLoopWeights

        host = MayaSkinLoopsHost("" if namespace == ":" else namespace)
        return len(CopySkinLoopWeights(host).execute())

    def skin_loops_bind(self, namespace: str) -> int:
        from adv_py.adapters.maya_skin_loops import MayaSkinLoopsHost
        from adv_py.application.skin_loops import BindSkinLoops

        host = MayaSkinLoopsHost("" if namespace == ":" else namespace)
        return len(BindSkinLoops(host).execute())

    def skin_loops_delete_cut_up(self, namespace: str) -> None:
        from adv_py.adapters.maya_skin_loops import MayaSkinLoopsHost
        from adv_py.application.skin_loops import DeleteSkinLoopCutUp

        host = MayaSkinLoopsHost("" if namespace == ":" else namespace)
        DeleteSkinLoopCutUp(host).execute()

    def skin_loops_create_cut_up(self, namespace: str) -> int:
        from adv_py.adapters.maya_skin_loops import MayaSkinLoopsHost
        from adv_py.application.skin_loops import CreateSkinLoopCutUp

        host = MayaSkinLoopsHost("" if namespace == ":" else namespace)
        return len(CreateSkinLoopCutUp(host).execute())

    def delta_mush_apply(self, namespace: str = "") -> int:
        from adv_py.adapters.maya_delta_mush import apply_delta_mush_to_selected

        return len(apply_delta_mush_to_selected(namespace=namespace))

    def delta_mush_bake(self, namespace: str = "") -> str:
        from adv_py.adapters.maya_delta_mush import open_delta_mush_bake_tool

        return open_delta_mush_bake_tool(namespace=namespace)

    def shapers_list(self, namespace: str) -> tuple[str, ...]:
        from adv_py.adapters.maya_shapers import list_shapers

        return list_shapers(namespace)

    def shapers_plugin_root(self) -> str:
        from adv_py.adapters.maya_shapers import discover_shapers_root

        root = discover_shapers_root()
        return str(root) if root else ""

    def shapers_setup(self, root: Path, *, mode: str,
                      autoload: bool):
        from adv_py.adapters.maya_shapers import MayaShapersSetupHost
        from adv_py.application.shapers_plugin import SetupShapersPlugin

        return SetupShapersPlugin(MayaShapersSetupHost()).apply(
            root, mode=mode, autoload=autoload)

    def shapers_plugin_status(self):
        from adv_py.adapters.maya_shapers import MayaShapersSetupHost

        return MayaShapersSetupHost().status()

    def shapers_create(self, namespace: str, *, loop_controls: int,
                       snap_vertices: bool, mirror: bool,
                       bridge_controls: int,
                       bridge_snap_vertices: bool) -> int:
        from maya import cmds
        from adv_py.adapters.maya_shapers_create import MayaShapersCreateHost
        from adv_py.application.shapers_create import (
            CreateShapersEdgePacks, CreateShapersFkLoops)
        from adv_py.core.shapers_create import ShapersFkLoopOptions

        options = ShapersFkLoopOptions(
            loop_controls, snap_vertices, mirror,
            bridge_controls, bridge_snap_vertices)
        host = MayaShapersCreateHost(namespace)
        selection = cmds.ls(selection=True, flatten=True) or []
        if any(".e[" in item for item in selection):
            return CreateShapersEdgePacks(host).execute(options)
        meshes = self.preparation_read_objects(namespace, "Skin")
        if len(meshes) != 1:
            raise ValueError("Shapers FK 闭环需要 Preparation / Rig 中唯一的 Skin 网格")
        return CreateShapersFkLoops(host).execute(meshes[0], options)

    def shapers_select(self, namespace: str, node: str | None = None) -> int:
        from adv_py.adapters.maya_shapers import select_shapers

        return select_shapers(namespace, node)

    def shapers_rebind(self, namespace: str, node: str | None = None) -> int:
        from adv_py.adapters.maya_shapers import rebind_shapers

        return rebind_shapers(namespace, node)

    def shapers_delete(self, namespace: str):
        from maya import cmds
        from adv_py.adapters.maya_shapers import (
            ShapersDeleteResult, delete_shapers)

        result = delete_shapers(namespace)
        prefix = ("" if namespace in ("", ":")
                  else namespace.strip(":") + ":")
        if cmds.objExists(prefix + "buildPose.advPyPoseData"):
            try:
                self.pose_to_build(namespace)
            except (ValueError, RuntimeError) as error:
                return ShapersDeleteResult(
                    result.deformers, result.collapsed_shapes,
                    result.cleanup_errors + ("构建姿态未恢复：" + str(error),))
        return result

    def delta_mush_harden_weights(self, namespace: str = "") -> int:
        from adv_py.adapters.maya_delta_mush import harden_weights_on_selected

        return len(harden_weights_on_selected(namespace=namespace))

    def skin_export(self, namespace: str, skin: str, mesh: str,
                    destination: Path) -> int:
        result = ExportSkinWeights(self._host(namespace)).apply(
            skin, mesh, destination)
        return result.plan.document.vertex_count

    def skin_import(self, namespace: str, source: Path,
                    mapping_file: Path | None = None, *,
                    allow_unweighted_missing: bool = False) -> int:
        mapping = (load_skin_path_mapping(mapping_file)
                   if mapping_file else None)
        result = ImportSkinWeights(self._host(namespace)).apply(source,
            mapping=mapping,
            allow_unweighted_missing=allow_unweighted_missing)
        return result.edit_result.changed_vertex_count

    def skin_surface_source_export(self, namespace: str, skin: str,
                                   mesh: str, destination: Path) -> int:
        source = CaptureSkinWeightSurfaceSource(self._host(namespace)).execute(skin, mesh)
        save_skin_weight_surface_source(source, destination)
        return source.weights.vertex_count

    def skin_rebind_from_source_asset(self, namespace: str, skin: str,
            mesh: str, source_asset: Path, max_distance: float,
            *, max_discarded_weight: float = 0.0):
        from adv_py.application.skin_rebind import RebindSkinFromSurfaceSource

        source = load_skin_weight_surface_source(source_asset)
        return RebindSkinFromSurfaceSource(self._host(namespace)).apply(
            source, skin, mesh, max_distance=max_distance,
            max_discarded_weight=max_discarded_weight)

    def skin_surface_transfer(self, namespace: str, target_skin: str,
                              target_mesh: str, max_distance: float, *,
                              source_asset: Path | None = None,
                              source_skin: str = "", source_mesh: str = "",
                              mapping_file: Path | None = None,
                              redistribution_file: Path | None = None,
                              alignment_file: Path | None = None,
                              max_discarded_weight: float = 0.,
                              allow_target_extra_influences: bool = False,
                              allow_unweighted_missing: bool = False
                              ) -> PanelSkinSurfaceResult:
        if mapping_file and redistribution_file:
            raise ValueError("一对一路径映射与影响重分配不能同时使用")
        mapping = load_skin_path_mapping(mapping_file) if mapping_file else None
        redistribution = (load_skin_redistribution(redistribution_file)
                          if redistribution_file else None)
        alignment = load_surface_alignment(alignment_file) if alignment_file else None
        service = TransferSkinWeightsBySurface(self._host(namespace))
        if source_asset:
            if source_skin or source_mesh:
                raise ValueError("使用源资产时请清空场景源 Skin 和网格路径")
            source = load_skin_weight_surface_source(source_asset)
            plan, edited = service.apply_from_documents(source.weights,
                source.geometry, target_skin, target_mesh,
                max_distance=max_distance,
                max_discarded_weight=max_discarded_weight,
                source_blend_weights=source.blend_weights,
                source_member_vertices=source.member_vertices,
                mapping=mapping, redistribution=redistribution,
                alignment=alignment,
                allow_target_extra_influences=allow_target_extra_influences,
                allow_unweighted_missing=allow_unweighted_missing)
            transfer = plan.transfer
        else:
            if not source_skin or not source_mesh:
                raise ValueError("场景内转移需要源 Skin 和源网格路径")
            result = service.apply(source_skin, source_mesh,
                target_skin, target_mesh, max_distance=max_distance,
                max_discarded_weight=max_discarded_weight,
                mapping=mapping, redistribution=redistribution,
                alignment=alignment,
                allow_target_extra_influences=allow_target_extra_influences,
                allow_unweighted_missing=allow_unweighted_missing)
            transfer, edited = result.plan.transfer, result.edit_result
        return PanelSkinSurfaceResult(transfer.document.vertex_count,
            edited.changed_vertex_count, transfer.max_surface_distance,
            transfer.max_discarded_weight)

    def pose_capture(self, namespace: str, destination: Path) -> int:
        pose = CaptureBodyCharacterPose(self._host(namespace)).execute()
        save_character_pose(pose, destination)
        return len(pose.channels)

    def pose_apply(self, namespace: str, source: Path) -> int:
        pose = load_character_pose(source)
        ApplyBodyCharacterPose(self._host(namespace)).apply(pose)
        return len(pose.channels)

    def pose_to_build(self, namespace: str) -> int:
        from adv_py.application.body_build_pose import GoToBodyBuildPose

        return GoToBodyBuildPose(self._host(namespace)).apply()

    def pose_set_build(self, namespace: str) -> int:
        from adv_py.application.body_build_pose import SetBodyBuildPose

        return SetBodyBuildPose(self._host(namespace)).apply()

    def animation_capture(self, namespace: str, destination: Path,
                          start: int, end: int, step: int = 1) -> int:
        animation = CaptureBodyCharacterAnimation(self._host(namespace)).execute(
            start, end, step)
        save_character_animation(animation, destination)
        return len(animation.samples)

    def animation_apply(self, namespace: str, source: Path) -> int:
        animation = load_character_animation(source)
        ApplyBodyCharacterAnimation(self._host(namespace)).apply(animation)
        return len(animation.samples)

    def animation_key_current(self, namespace: str) -> int:
        host = self._host(namespace)
        pose = CaptureAnimatedBodyCharacterPose(host).execute()
        keyed = KeyBodyCharacterPose(host).apply(pose)
        return len(keyed.channels)

    def animation_enable_limb(self, namespace: str) -> int:
        return len(EnableBodyCharacterLimbAnimation(
            self._host(namespace)).apply().channels)

    def animation_enable_stretch(self, namespace: str) -> int:
        return len(EnableBodyCharacterStretchMatching(
            self._host(namespace)).apply().channels)

    def animation_enable_spline(self, namespace: str) -> int:
        return len(EnableBodyCharacterSplineAnimation(
            self._host(namespace)).apply().channels)

    def animation_enable_spaces(self, namespace: str) -> int:
        return len(EnableBodyCharacterSpaceAnimation(
            self._host(namespace)).apply().channels)

    def animation_bake_limb(self, namespace: str, start: int, end: int,
                            limb: str, side: str, mode: str, step: int = 1) -> int:
        animation = BakeBodyCharacterLimbMode(self._host(namespace)).execute(
            start, end, limb, side, mode, step)
        return len(animation.samples)

    def animation_limb_systems(self,namespace: str):
        registration=self._host(namespace).read_character_registration()
        if registration.source_limbs:
            return tuple((row.label,row.side) for row in registration.source_limbs)
        return tuple((label,side) for label in ('arm','leg') for side in ('R','L'))

    @staticmethod
    def _original_highlighted_time_range():
        from maya import cmds, mel
        slider=mel.eval('global string $gPlayBackSlider; $gPlayBackSlider;')
        if not slider:return None
        values=cmds.timeControl(slider,query=True,rangeArray=True)
        return tuple(float(value) for value in values) if values and values[1]-values[0]>1. else None

    def animation_match_source_limb(self,namespace: str,limb: str,side: str,mode: str):
        from adv_py.application.character_limb_animation import MatchSourceBodyLimbMode
        return MatchSourceBodyLimbMode(self._host(namespace)).execute(limb,side,mode,
            time_range=self._original_highlighted_time_range())

    def animation_bake_spine(self, namespace: str, start: int, end: int,
                             mode: str, step: int = 1) -> int:
        animation = BakeBodyCharacterSpineMode(self._host(namespace)).execute(
            start, end, mode, step)
        return len(animation.samples)

    def animation_spline_systems(self,namespace: str):
        from adv_py.core.body_spline import BodySplinePlan
        registration=self._host(namespace).read_character_registration()
        return tuple(plan.system_name for plan in (registration.spine,*registration.additional_spines)
                     if isinstance(plan,BodySplinePlan) and plan.source_curve_points)

    def animation_upgrade_source_spline(self, namespace: str, systems=None):
        from adv_py.application.source_spline_mode_upgrade import UpgradeSourceSplineMode
        return UpgradeSourceSplineMode(self._host(namespace)).apply(systems)

    def animation_upgrade_source_spline_alignment(self, namespace: str,
            replacement: str, systems=None, *, extensions=()):
        from adv_py.application.source_spline_alignment_upgrade import UpgradeSourceSplineAlignment
        if not isinstance(replacement, str) or not replacement.strip():
            raise ValueError('请填写尚未占用的重建暂存命名空间')
        _ensure_body_build_centimeters()
        return UpgradeSourceSplineAlignment(self._host(namespace)).apply(
            replacement.strip(), systems, extensions=extensions)

    def animation_match_source_spline(self,namespace: str,mode: str,system=None,*,align_only=False):
        from adv_py.application.character_spine_animation import MatchSourceBodySplineMode
        return MatchSourceBodySplineMode(self._host(namespace)).execute(mode,system,
            align_only=align_only,time_range=None if align_only else self._original_highlighted_time_range())

    def animation_switch_space(self, namespace: str, key: str,
                               mode: str, frame: int) -> str:
        pose = SwitchBodyCharacterSpace(self._host(namespace)).execute(
            key, mode, frame)
        return dict(pose.spaces)[key]

    def face_generate(self, namespace: str, neutral: str, name: str,
                      kind: str, target_mesh: str, landmarks: Path) -> int:
        target = FaceTarget(name, FaceShapeKind(kind), target_mesh)
        plan = GenerateFaceTarget(self._host(namespace)).apply(
            neutral, target, load_face_landmarks(landmarks))
        return plan.neutral.vertex_count

    def face_build(self, namespace: str, specification: Path,
                   control_name: str = "AdvPy_FaceControls",
                   deformer_name: str = "AdvPy_FaceBlendShape") -> int:
        neutral, targets = load_face_build_spec(specification)
        result = BuildFaceBlendShapes(self._host(namespace)).apply(
            neutral, targets, control_name=control_name,
            deformer_name=deformer_name)
        return len(result.binding.channels)

    def face_eye_selected_mesh(self, namespace: str) -> str:
        from adv_py.adapters.maya_face_eye import MayaFaceEyeHost

        return MayaFaceEyeHost(
            namespace=None if namespace == ":" else namespace).selected_eye_mesh()

    def face_read_original_options(self, namespace: str):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        return MayaFacePreHost(namespace=None if namespace == ':' else namespace).read_original_face_options()

    def face_set_original_options(self, namespace: str, values, *, switch_side=False):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.original_face_options import SetOriginalFaceOptions
        return SetOriginalFaceOptions(MayaFacePreHost(
            namespace=None if namespace == ':' else namespace)).apply(values, switch_side=switch_side)

    def face_multi_skin_clusters_supported(self):
        from maya import cmds
        return int(cmds.about(apiVersion=True)) >= 20240000

    def face_offset_create(self, namespace: str):
        from adv_py.adapters.maya_original_offset_face import MayaOriginalOffsetFaceHost
        from adv_py.application.original_offset_face import CreateOriginalOffsetFace
        return CreateOriginalOffsetFace(MayaOriginalOffsetFaceHost(
            namespace=None if namespace == ':' else namespace)).apply()

    def face_offset_import_choices(self, namespace: str):
        from adv_py.adapters.maya_original_offset_face import MayaOriginalOffsetFaceHost
        host = MayaOriginalOffsetFaceHost(namespace=None if namespace == ':' else namespace)
        raw = host._offset_face_raw
        return (*host.original_offset_face_import_choices(),
            raw.workspace(query=True, active=True)+'/'+raw.workspace(query=True, fileRuleEntry='scene'))

    def face_offset_import(self, namespace: str, file: str, options):
        from adv_py.adapters.maya_original_offset_face import MayaOriginalOffsetFaceHost
        from adv_py.application.original_offset_face import ImportOriginalOffsetFace
        return ImportOriginalOffsetFace(MayaOriginalOffsetFaceHost(
            namespace=None if namespace == ':' else namespace)).apply(file, options)

    def face_offset_update(self, namespace: str):
        from adv_py.adapters.maya_original_offset_face import MayaOriginalOffsetFaceHost
        from adv_py.application.original_offset_face import UpdateOriginalOffsetFaces
        return UpdateOriginalOffsetFaces(MayaOriginalOffsetFaceHost(
            namespace=None if namespace == ':' else namespace)).apply()

    def face_auto_fit(self, namespace: str, *, options=None):
        from adv_py.adapters.maya_original_auto_face_fitting import MayaOriginalAutoFaceFittingHost
        from adv_py.application.original_auto_face_fitting import AutoFitOriginalFace
        from adv_py.core.original_face_options import normalize_original_face_options
        host = MayaOriginalAutoFaceFittingHost(namespace=None if namespace == ':' else namespace)
        host._auto_face_options = normalize_original_face_options(options or {})
        return AutoFitOriginalFace(host).apply()

    def face_pre_record_mask(self, namespace: str, *, options=None):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import RecordFacePreInput

        host = MayaFacePreHost(namespace=None if namespace == ':' else namespace)
        if options is not None:
            from adv_py.core.original_face_options import normalize_original_face_options
            host._face_input_options = normalize_original_face_options(options, complete=True)
        return RecordFacePreInput(host).mask()

    def face_original_model_check(self, namespace: str):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import FacePreRole
        from adv_py.adapters.maya_model_checker import MayaModelCheckHost
        from adv_py.application.model_check import ReviewModelCheck
        host = MayaFacePreHost(namespace=None if namespace == ':' else namespace)
        geometry = host.read_face_objects(FacePreRole.FACE)
        if not geometry:
            raise ValueError('No geometry choosen for "Face"')
        host._cmds.select(geometry, replace=True)
        return ReviewModelCheck(MayaModelCheckHost()).execute(
            game_engine=(host.read_original_face_options() or {}).get('GameEngine', False))

    def face_pre_record_head_joint(self, namespace: str):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import RecordFacePreInput
        return RecordFacePreInput(MayaFacePreHost(
            namespace=None if namespace==':' else namespace)).head_joint()

    def face_pre_input_fields(self, namespace: str):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        host=MayaFacePreHost(namespace=None if namespace==':' else namespace)
        fit=host._fit()
        result={name:('Head_M' if name=='HeadJoint' else '')
                for name in ('Mask','Face','AllHead','HeadJoint','SkinCluster','RightEye','LeftEye')}
        if fit is not None:
            for name in result:
                if host._cmds.objExists(fit+'.'+name):
                    result[name]=host._cmds.getAttr(fit+'.'+name) or ''
        return result

    def face_pre_set_skin_cluster(self, namespace: str, value: str) -> None:
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        MayaFacePreHost(namespace=None if namespace == ':' else namespace).set_original_face_skin_input(value)

    def face_pre_record_eye(self,namespace: str,side: str):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import RecordFacePreInput,FaceSide
        return RecordFacePreInput(MayaFacePreHost(
            namespace=None if namespace==':' else namespace)).eye(FaceSide(side))

    def face_pre_record_objects(self, namespace: str, role: str,
                                head_joint: str | None):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import FacePreRole, RecordFacePreInput

        return RecordFacePreInput(MayaFacePreHost(
            namespace=None if namespace == ":" else namespace)).objects(
                FacePreRole(role), head_joint)

    def face_pre_reselect(self, namespace: str, role: str):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import FacePreRole

        host = MayaFacePreHost(namespace=None if namespace == ":" else namespace)
        if role == "Mask":
            return host.select_face_mask()
        return len(host.select_face_objects(FacePreRole(role)))

    def face_fit_switch_side(self, namespace: str, side: str) -> str:
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import FaceSide

        return MayaFacePreHost(namespace=None if namespace == ":" else namespace
            ).set_face_fit_side(FaceSide(side)).value

    def face_fit_current_side(self, namespace: str) -> str:
        from adv_py.adapters.maya_face_pre import MayaFacePreHost

        return MayaFacePreHost(namespace=None if namespace == ":" else namespace
            ).active_face_side().value

    def face_fit_display(self, namespace: str, operation: str, section='', part=''):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        host = MayaFacePreHost(namespace=None if namespace == ':' else namespace)
        if operation == 'reselect':
            host.reselect_original_face_fit(section, part)
            return tuple(host._cmds.ls(selection=True, flatten=True) or [])
        with host.transaction('Face Fit ' + operation):
            if operation == 'hide':
                return host.toggle_original_face_fit_visibility(section, part)
            if operation == 'show_both':
                return host.show_original_face_fit_both_sides()
            if operation == 'side_off':
                return host.switch_original_face_fit_side(2)
            if operation == 'assist':
                return host.toggle_original_face_fit_assist(section)
            if operation == 'swap':
                return host.swap_original_face_fit_upper_lower(section, part)
            if operation == 'delete':
                return host.delete_original_face_fit(section + part)
            raise ValueError('Face Fit 显示操作无效')

    def face_fit_states(self, namespace: str, rows):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        host=MayaFacePreHost(namespace=None if namespace==':' else namespace)
        return {(section,part):host.original_face_fit_exists(section,part)
                for section,part in rows}

    def face_fit_eye_ball(self, namespace: str, eye_mesh: str,
                          head_joint: str) -> str:
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import CreateFaceEyeBallFit

        return CreateFaceEyeBallFit(MayaFacePreHost(
            namespace=None if namespace == ":" else namespace)).execute(
                eye_mesh, head_joint or "Head_M")

    def face_fit_eye_lid(self, namespace: str, layer: str):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import CreateFaceEyeLidFit, EyeLidLayer, OptionalEyeLidLayer

        return CreateFaceEyeLidFit(MayaFacePreHost(
            namespace=None if namespace == ":" else namespace)).execute(
                OptionalEyeLidLayer.MAIN2 if layer == 'Main2' else EyeLidLayer(layer))

    def face_fit_lip(self, namespace: str, part: str, *, reselect: bool = False):
        if reselect:
            return len(self.face_fit_display(namespace, 'reselect', 'Lip', part))
        from adv_py.adapters.maya_face_lip_fit import MayaFaceLipFitHost
        from adv_py.application.face_lip_fit import CreateFaceLipFit
        host=MayaFaceLipFitHost(namespace=None if namespace == ":" else namespace)
        return CreateFaceLipFit(host).apply(part)

    def face_fit_lip_swap(self, namespace: str, part: str):
        from adv_py.adapters.maya_face_lip_fit import MayaFaceLipFitHost
        from adv_py.application.face_lip_fit import SwapFaceLipFit
        return SwapFaceLipFit(MayaFaceLipFitHost(
            namespace=None if namespace == ":" else namespace)).apply(part)

    def face_regions(self, namespace: str):
        from adv_py.adapters.maya_face_regions import MayaFaceRegionsHost
        from adv_py.application.face_regions import BuildFaceRegions
        return BuildFaceRegions(MayaFaceRegionsHost(
            namespace=None if namespace == ":" else namespace)).apply()

    def face_lip_build(self, namespace: str):
        from adv_py.adapters.maya_face_lip import MayaFaceLipHost
        from adv_py.application.face_lip import BuildFaceLip
        return BuildFaceLip(MayaFaceLipHost(
            namespace=None if namespace == ":" else namespace)).apply()

    def face_cage(self,namespace: str,action: str,smooth_passes=None):
        from adv_py.adapters.maya_face_expressions import MayaFaceExpressionHost
        from adv_py.application.face_cage import BuildFaceCage,TransferFaceCage,EditFaceCage,BuildFaceBrow
        from adv_py.core.face_cage import FaceCageOptions
        host=MayaFaceExpressionHost(namespace=None if namespace==":" else namespace)
        if action=="build": return BuildFaceCage(host).apply(FaceCageOptions(smooth_passes))
        if action=="transfer": return TransferFaceCage(host).apply(smooth_passes or 0)
        if action=="brow": return BuildFaceBrow(host).apply()
        return EditFaceCage(host).apply(action,smooth_passes or 0)

    def original_driving_catalog(self, namespace: str):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.application.driving_systems import EditOriginalDrivingSystems
        return EditOriginalDrivingSystems(MayaDrivingSystemsHost(
            namespace=None if namespace==":" else namespace)).catalog()

    def original_driving_systems(self, namespace: str, action: str, **options):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.application.driving_systems import EditOriginalDrivingSystems
        return EditOriginalDrivingSystems(MayaDrivingSystemsHost(
            namespace=None if namespace==":" else namespace)).apply(action,**options)

    def original_pose_functions(self, namespace: str, action: str, **options):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.application.driving_systems import EditOriginalPoseFunctions
        use_case=EditOriginalPoseFunctions(MayaDrivingSystemsHost(namespace=None if namespace==":" else namespace))
        return use_case.catalog() if action=="catalog" else use_case.apply(action,**options)

    def original_animation_bake(self, namespace: str, limbs='', mode='ik', *, catalog=False, action='fkik', **options):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.application.original_animation_bake import BakeOriginalControlAnimation
        use_case=BakeOriginalControlAnimation(MayaDrivingSystemsHost(namespace=None if namespace==':' else namespace))
        if catalog:return use_case.systems()
        if action=='to_extra':return use_case.move_to_extra(**options)
        if action=='extra':return use_case.bake_extra(**options)
        if action=='quick_ik':return use_case.bake_quick_ik(**options)
        if action!='fkik':raise ValueError('未知原版动画烘焙操作')
        return use_case.execute(limbs,mode,**options)

    def original_animation_bake_window(self, namespace: str, *, ui_name='', **state):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.adapters.maya_original_animation_bake_ui import show
        return show(MayaDrivingSystemsHost(namespace=None if namespace==':' else namespace),ui_name,**state)

    def original_animation_tools(self, namespace: str, action: str, selection=None):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.application.original_animation_tools import EditOriginalAnimationTools
        return EditOriginalAnimationTools(MayaDrivingSystemsHost(
            namespace=None if namespace==':' else namespace)).execute(action,selection)

    def original_control_clipboard(self, namespace: str, action: str, *, animation=False, **options):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.application.original_clipboard import TransferOriginalControlClipboard
        service=TransferOriginalControlClipboard(MayaDrivingSystemsHost(
            namespace=None if namespace==':' else namespace))
        if action=='copy':return service.copy(animation,**options)
        if action=='paste':return service.paste(animation,**options)
        raise ValueError('未知原版剪贴板操作：'+action)

    def original_control_mirror_options(self, namespace: str, *, ui_name='', **state):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.adapters.maya_original_mirror_options_ui import show
        return show(MayaDrivingSystemsHost(namespace=None if namespace==':' else namespace),ui_name,**state)

    def original_control_menu_binding(self, namespace: str, window: str, *, ui_name='', **state):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.adapters.maya_original_control_menu_binding import bind
        return bind(MayaDrivingSystemsHost(namespace=None if namespace==':' else namespace),window,ui_name or window,**state)

    def original_poser_commands(self, namespace: str, text: str, *, action='pose', **options):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.application.original_poser import EditOriginalPoser
        return EditOriginalPoser(MayaDrivingSystemsHost(
            namespace=None if namespace==':' else namespace)).apply(text,action,**options)

    def original_poser_window(self, namespace: str):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.adapters.maya_original_poser_ui import show
        return show(MayaDrivingSystemsHost(namespace=None if namespace==':' else namespace))

    def original_poser_new(self, namespace: str, load_data=(), *, animation=False, file_loading=False):
        from adv_py.adapters.maya_driving_systems import MayaDrivingSystemsHost
        from adv_py.adapters.maya_original_poser_ui import new_pose
        return new_pose(MayaDrivingSystemsHost(namespace=None if namespace==':' else namespace),
            load_data,animation,file_loading=file_loading)

    def original_corrective_targets(self, namespace: str, *, edit=False):
        from adv_py.adapters.maya_corrective_shapes import MayaCorrectiveShapesHost
        from adv_py.application.corrective_shapes import EditOriginalCorrectiveShapes
        return EditOriginalCorrectiveShapes(MayaCorrectiveShapesHost(
            namespace=None if namespace == ":" else namespace)).targets(edit=edit)

    def original_corrective_shapes(self, namespace: str, action: str, **options):
        from adv_py.adapters.maya_corrective_shapes import MayaCorrectiveShapesHost
        from adv_py.application.corrective_shapes import EditOriginalCorrectiveShapes
        return EditOriginalCorrectiveShapes(MayaCorrectiveShapesHost(
            namespace=None if namespace == ":" else namespace)).apply(action, **options)

    def face_original_wrinkles(self, namespace: str, action: str, **options):
        from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
        from adv_py.application.face_wrinkles import EditOriginalFaceWrinkles
        return EditOriginalFaceWrinkles(MayaOriginalFaceBuildHost(
            namespace=None if namespace == ":" else namespace)).apply(action, **options)

    def face_upgrade_original_fit(self, namespace: str):
        from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
        from adv_py.application.face_original_build import UpgradeOriginalFaceFit
        return UpgradeOriginalFaceFit(MayaOriginalFaceBuildHost(
            namespace=None if namespace == ":" else namespace)).apply()

    def face_original_build(self, namespace: str, *, step=None, keep=None,
                            manually_restore=False, cage_smooth=None, jaw_smooth=50,
                            lip_falloff=None):
        from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
        from adv_py.application.face_original_build import BuildOriginalFace, BuildOriginalFaceStep
        host = MayaOriginalFaceBuildHost(namespace=None if namespace == ":" else namespace)
        arguments = dict(keep=keep, cage_smooth=cage_smooth, jaw_smooth=jaw_smooth,
                         lip_falloff=lip_falloff)
        if step is not None:
            return BuildOriginalFaceStep(host).apply(step, **arguments)
        return BuildOriginalFace(host).apply(manually_restore=manually_restore, **arguments)

    def face_original_restore(self, namespace: str, *, keep=None):
        from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
        host = MayaOriginalFaceBuildHost(namespace=None if namespace == ":" else namespace)
        host.prepare_original_face_restore_dependencies(keep)
        with host.transaction("恢复原版 Face 重建"):
            result = host.restore_original_face(keep)
            if result is not None:
                host.complete_original_face_build_step(30)
            return result

    def face_expression(self,namespace: str,stage: str):
        from adv_py.adapters.maya_face_expressions import MayaFaceExpressionHost
        from adv_py.application.face_expressions import FitFaceExpression
        return FitFaceExpression(MayaFaceExpressionHost(namespace=None if namespace==":" else namespace)).apply(stage)

    def face_jaw(self,namespace: str,action: str,smooth_iterations: int=50):
        from adv_py.adapters.maya_face_jaw import MayaFaceJawHost
        from adv_py.application.face_jaw import BuildFaceJaw,UpdateFaceJawWeights,FinishFaceJaw,FitFaceJawPose
        host=MayaFaceJawHost(namespace=None if namespace==":" else namespace)
        operations={"build":BuildFaceJaw,"update":UpdateFaceJawWeights,"finish":FinishFaceJaw}
        if action in operations: return operations[action](host).apply(smooth_iterations)
        return FitFaceJawPose(host).apply(action,smooth_iterations)

    def face_teeth_record(self,namespace: str,part: str):
        from adv_py.adapters.maya_face_jaw import MayaFaceJawHost
        from adv_py.application.face_jaw import RecordFaceTeeth
        return RecordFaceTeeth(MayaFaceJawHost(namespace=None if namespace==":" else namespace)).apply(part)

    def face_mouth_open_design(self, namespace: str):
        from adv_py.adapters.maya_face_mouth_open import MayaFaceMouthOpenHost
        from adv_py.application.face_mouth_open import CreateFaceMouthOpenDesign
        return CreateFaceMouthOpenDesign(MayaFaceMouthOpenHost(
            namespace=None if namespace == ":" else namespace)).apply()

    def face_jaw_lip_weights(self, namespace: str):
        from adv_py.adapters.maya_face_jaw_lip_weights import MayaFaceJawLipWeightsHost
        from adv_py.application.face_jaw_lip_weights import UpdateFaceJawLipWeights
        return UpdateFaceJawLipWeights(MayaFaceJawLipWeightsHost(
            namespace=None if namespace == ":" else namespace)).apply()

    def face_lip_falloff(self, namespace: str, *, outer: int = 3, inner: int = 2,
                         iterations: int = 5, preview: bool = False, update: bool = False,
                         multi_skin_clusters: bool = False):
        from adv_py.adapters.maya_face_lip_falloff import MayaFaceLipFalloffHost
        from adv_py.application.face_lip_falloff import BuildFaceLipFalloff
        from adv_py.core.face_lip_falloff import LipFalloffOptions
        return BuildFaceLipFalloff(MayaFaceLipFalloffHost(
            namespace=None if namespace == ":" else namespace)).apply(
                LipFalloffOptions(outer,inner,iterations,preview,update,multi_skin_clusters))

    def face_fit_eye_lid_reselect(self, namespace: str, layer: str) -> int:
        return len(self.face_fit_display(namespace, 'reselect',
            'EyeLidMain2' if layer == 'Main2' else 'EyeLid',
            '' if layer == 'Main2' else layer))

    def face_fit_mirror_right_to_left(self, namespace: str,
                                      left_eye_mesh: str) -> dict:
        from adv_py.adapters.maya_face_pre import MayaFacePreHost

        return MayaFacePreHost(namespace=None if namespace == ":" else namespace
            ).mirror_right_eye_fit_to_left(left_eye_mesh)

    def face_build_set_include(self, namespace: str, include: str) -> str:
        from adv_py.adapters.maya_face_build import MayaFaceBuildHost
        from adv_py.core.face_build_requirements import FaceInclude

        return MayaFaceBuildHost(namespace=None if namespace == ":" else namespace
            ).set_include(FaceInclude(include)).value

    def face_delta_mush_create(self, namespace: str) -> str:
        from adv_py.adapters.maya_face_delta_mush import MayaFaceDeltaMushHost

        return MayaFaceDeltaMushHost(
            namespace=None if namespace == ":" else namespace
        ).create_face_delta_mush()

    def face_delta_mush_delete(self, namespace: str) -> bool:
        from adv_py.adapters.maya_face_delta_mush import MayaFaceDeltaMushHost

        return MayaFaceDeltaMushHost(
            namespace=None if namespace == ":" else namespace
        ).delete_face_delta_mush()

    def face_delta_mush_select_area(self, namespace: str,
                                    area: str) -> int:
        from adv_py.adapters.maya_face_delta_mush import MayaFaceDeltaMushHost

        return MayaFaceDeltaMushHost(
            namespace=None if namespace == ":" else namespace
        ).select_face_delta_mush_area(area)

    def face_delta_mush_zero_selected(self, namespace: str) -> tuple[str, ...]:
        from adv_py.adapters.maya_face_delta_mush import MayaFaceDeltaMushHost

        return MayaFaceDeltaMushHost(
            namespace=None if namespace == ":" else namespace
        ).zero_selected_face_delta_mush_weights()

    def face_delta_mush_paint(self, namespace: str) -> str:
        from adv_py.adapters.maya_face_delta_mush import MayaFaceDeltaMushHost

        return MayaFaceDeltaMushHost(
            namespace=None if namespace == ":" else namespace
        ).paint_face_delta_mush_weights()

    def face_tweaks_select_area(self, namespace: str, area: str,
                                *, subtract: bool = False) -> int:
        from adv_py.adapters.maya_face_tweaks import MayaFaceTweaksHost

        return MayaFaceTweaksHost(
            namespace=None if namespace == ":" else namespace
        ).select_face_area(area, subtract=subtract)

    def face_tweaks_smooth_weights(self, namespace: str,
                                   iterations: int) -> str:
        from adv_py.adapters.maya_face_tweaks import MayaFaceTweaksHost

        return MayaFaceTweaksHost(
            namespace=None if namespace == ":" else namespace
        ).smooth_selected_skin_weights(iterations)

    def face_tweaks_paint_skin(self, namespace: str) -> str:
        from adv_py.adapters.maya_face_tweaks import MayaFaceTweaksHost

        return MayaFaceTweaksHost(
            namespace=None if namespace == ":" else namespace
        ).paint_face_skin_weights()

    def face_tweaks_set_joints_visible(self, namespace: str,
                                       visible: bool) -> int:
        from adv_py.adapters.maya_face_tweaks import MayaFaceTweaksHost

        return MayaFaceTweaksHost(
            namespace=None if namespace == ":" else namespace
        ).set_face_joints_visible(visible)

    def face_tweaks_swap_spheres(self, namespace: str, *,
                                 keep_offset: bool = False
                                 ) -> tuple[str, ...]:
        from adv_py.adapters.maya_face_tweak_controls import MayaFaceTweakControlsHost

        return MayaFaceTweakControlsHost(
            namespace=None if namespace == ":" else namespace
        ).swap_face_controls_to_spheres(keep_offset=keep_offset)

    def face_tweaks_detach_controllers(self, namespace: str
                                       ) -> tuple[str, ...]:
        from adv_py.adapters.maya_face_tweak_controls import MayaFaceTweakControlsHost

        return MayaFaceTweakControlsHost(
            namespace=None if namespace == ":" else namespace
        ).detach_face_controllers()

    def face_tweaks_attach_controllers(self, namespace: str
                                       ) -> tuple[str, ...]:
        from adv_py.adapters.maya_face_tweak_controls import MayaFaceTweakControlsHost

        return MayaFaceTweakControlsHost(
            namespace=None if namespace == ":" else namespace
        ).attach_face_controllers()

    def face_skin_layers_visible(self, namespace: str) -> bool:
        from adv_py.adapters.maya_face_skin_layers import MayaFaceSkinLayersHost
        return MayaFaceSkinLayersHost(
            namespace=None if namespace == ':' else namespace
        ).face_skin_layers_visible()

    def face_skin_layers_available(self, namespace: str) -> tuple[str, ...]:
        from adv_py.adapters.maya_face_skin_layers import MayaFaceSkinLayersHost

        return MayaFaceSkinLayersHost(
            namespace=None if namespace == ":" else namespace
        ).available_face_skin_layers()

    def face_skin_layers_show(self, namespace: str,
                              layer: str) -> tuple[str, ...]:
        from adv_py.adapters.maya_face_skin_layers import MayaFaceSkinLayersHost

        return MayaFaceSkinLayersHost(
            namespace=None if namespace == ":" else namespace
        ).show_face_skin_layer(layer)

    def face_build_get_include(self, namespace: str) -> str:
        from adv_py.adapters.maya_face_build import MayaFaceBuildHost

        return MayaFaceBuildHost(namespace=None if namespace == ":" else namespace
            ).read_include().value

    def face_build_toggle_fit_advanced(self, namespace: str) -> bool:
        from adv_py.adapters.maya_face_build import MayaFaceBuildHost

        return MayaFaceBuildHost(
            namespace=None if namespace == ":" else namespace
        ).toggle_fit_advanced_visibility()

    def face_build_inspect_inputs(self, namespace: str) -> dict:
        from adv_py.adapters.maya_face_build import MayaFaceBuildHost

        return MayaFaceBuildHost(namespace=None if namespace == ":" else namespace
            ).inspect_build_inputs()

    def face_build_eye_lids(self, namespace: str, *,
                            simpler_eyelid: bool = False) -> dict:
        from adv_py.adapters.maya_face_eyelid_rig import MayaFaceEyeLidRigHost
        from adv_py.application.face_eyelid_rig import BuildFaceEyeLids

        return BuildFaceEyeLids(MayaFaceEyeLidRigHost(
            namespace=None if namespace == ":" else namespace)).execute(
                simpler_eyelid=simpler_eyelid)

    def face_fit_marker(self, namespace: str, section: str):
        from adv_py.adapters.maya_face_fit_markers import MayaFaceFitMarkersHost
        from adv_py.application.face_fit_markers import CreateFaceFitMarker
        return CreateFaceFitMarker(MayaFaceFitMarkersHost(
            namespace=None if namespace == ":" else namespace)).apply(section)

    def face_build_ctrl_box(self, namespace: str):
        from adv_py.adapters.maya_face_ctrl_box import MayaFaceCtrlBoxHost
        from adv_py.application.face_ctrl_box import BuildFaceCtrlBox
        return BuildFaceCtrlBox(MayaFaceCtrlBoxHost(
            namespace=None if namespace == ":" else namespace)).apply()

    def face_tongue(self, namespace: str, action: str):
        from adv_py.adapters.maya_face_tongue import MayaFaceTongueHost
        from adv_py.application.face_tongue import (
            RecordFaceTongue, CreateFaceTongueFit, BuildFaceTongue, FinishFaceTongue)
        services={"record":RecordFaceTongue,"fit":CreateFaceTongueFit,
                  "build":BuildFaceTongue,"finish":FinishFaceTongue}
        if action not in services: raise ValueError("Tongue 操作无效")
        return services[action](MayaFaceTongueHost(
            namespace=None if namespace == ":" else namespace)).apply()

    def face_build_jaw_fit_curves(self, namespace: str):
        from adv_py.adapters.maya_face_jaw_fit import MayaFaceJawFitHost
        from adv_py.application.face_jaw_fit import BuildFaceJawFitCurves
        return BuildFaceJawFitCurves(MayaFaceJawFitHost(
            namespace=None if namespace == ":" else namespace)).apply()

    def face_head_squash(self, namespace: str, action: str):
        from adv_py.adapters.maya_face_head_squash import MayaFaceHeadSquashHost
        from adv_py.application.face_head_squash import (
            BuildFaceHeadSquash, DeleteFaceHeadSquash,
            OptimizeFaceHeadSquash, IncludeSelectedInHeadSquash)
        services = {"create": BuildFaceHeadSquash, "delete": DeleteFaceHeadSquash,
                    "optimize": OptimizeFaceHeadSquash,
                    "include": IncludeSelectedInHeadSquash}
        if action not in services:
            raise ValueError("HeadSquash 操作无效")
        host = MayaFaceHeadSquashHost(namespace=None if namespace == ":" else namespace)
        return services[action](host).apply()

    def face_delete_advanced(self, namespace: str, *,
                             keep_build_pose: bool = False) -> bool:
        from adv_py.adapters.maya_face_eyelid_rig import MayaFaceEyeLidRigHost
        from adv_py.application.face_delete import DeleteFaceAdvanced

        return DeleteFaceAdvanced(MayaFaceEyeLidRigHost(
            namespace=None if namespace == ":" else namespace)).apply(
                keep_build_pose=keep_build_pose)

    def face_built_eye_lid_mode(self, namespace: str) -> bool | None:
        from adv_py.adapters.maya_face_eyelid_rig import MayaFaceEyeLidRigHost

        return MayaFaceEyeLidRigHost(
            namespace=None if namespace == ":" else namespace
        ).read_built_eye_lid_mode()

    def face_go_to_build_pose(self, namespace: str) -> int:
        from adv_py.adapters.maya_face_eyelid_rig import MayaFaceEyeLidRigHost
        from adv_py.application.face_build_pose import GoToFaceBuildPose

        return GoToFaceBuildPose(MayaFaceEyeLidRigHost(
            namespace=None if namespace == ":" else namespace)).apply()

    def face_set_build_pose(self, namespace: str) -> int:
        from adv_py.adapters.maya_face_eyelid_rig import MayaFaceEyeLidRigHost
        from adv_py.application.face_build_pose import SetFaceBuildPose

        return SetFaceBuildPose(MayaFaceEyeLidRigHost(
            namespace=None if namespace == ":" else namespace)).apply()

    def face_build_original_eye_lid_skin(self, namespace: str,
                                         source_mesh: str) -> dict:
        from adv_py.adapters.maya_face_source_skin import MayaFaceSourceSkinHost

        if not source_mesh.strip():
            raise ValueError("请填写当前场景中的原版头部网格")
        return MayaFaceSourceSkinHost(
            namespace=None if namespace == ":" else namespace
            ).transfer_original_eye_lid_skin(source_mesh.strip())

    def face_lid_blink_read(self, namespace: str, side: str, layer: str,
                            arc: str) -> tuple[float, float, float]:
        from adv_py.adapters.maya_face_eyelid_rig import MayaFaceEyeLidRigHost
        from adv_py.application.face_pre import EyeLidLayer, FaceSide

        return MayaFaceEyeLidRigHost(
            namespace=None if namespace == ":" else namespace
            ).read_blink_offset(FaceSide(side), EyeLidLayer(layer), arc)

    def face_lid_blink_apply(self, namespace: str, side: str, layer: str,
                             arc: str, offset: tuple[float, float, float]
                             ) -> tuple[float, float, float]:
        from adv_py.adapters.maya_face_eyelid_rig import MayaFaceEyeLidRigHost
        from adv_py.application.face_pre import EyeLidLayer, FaceSide

        return MayaFaceEyeLidRigHost(
            namespace=None if namespace == ":" else namespace
            ).set_blink_offset(FaceSide(side), EyeLidLayer(layer), arc, offset)

    def face_outer_blink_read(self, namespace: str, side: str,
                              arc: str) -> tuple[float, float, float]:
        return self.face_lid_blink_read(namespace, side, "Outer", arc)

    def face_outer_blink_apply(self, namespace: str, side: str, arc: str,
                               offset: tuple[float, float, float]
                               ) -> tuple[float, float, float]:
        return self.face_lid_blink_apply(namespace, side, "Outer", arc,
                                         offset)

    def face_eye_build(self, namespace: str, head_joint: str,
                       right_eye: str, left_eye: str):
        from adv_py.adapters.maya_face_eye import MayaFaceEyeHost
        from adv_py.application.face_eye_rig import BuildFaceEyeRig

        return BuildFaceEyeRig(MayaFaceEyeHost(
            namespace=None if namespace == ":" else namespace)).apply(
            head_joint, right_eye, left_eye)

    def face_original_blendshape_targets(self, namespace: str):
        from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
        from adv_py.application.face_conversion import EditOriginalFaceBlendShapes
        return EditOriginalFaceBlendShapes(MayaOriginalFaceBuildHost(
            namespace=None if namespace == ":" else namespace)).targets()

    def face_edit_original_blendshapes(self, namespace: str, action: str, **options):
        from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
        from adv_py.application.face_conversion import EditOriginalFaceBlendShapes
        return EditOriginalFaceBlendShapes(MayaOriginalFaceBuildHost(
            namespace=None if namespace == ":" else namespace)).apply(action, **options)

    def face_convert_original_blendshapes(self, namespace: str, *, keep_joints=False, keep_targets=False):
        from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
        from adv_py.application.face_conversion import ConvertOriginalFaceToBlendShapes
        host = MayaOriginalFaceBuildHost(namespace=None if namespace == ":" else namespace)
        return ConvertOriginalFaceToBlendShapes(host).apply(keep_joints=keep_joints, keep_targets=keep_targets)

    def face_connect_original_arkit(self, namespace: str, blendshape=None, *, mouth_close_includes_open=False):
        from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
        from adv_py.application.face_conversion import ConnectOriginalFaceARKit
        host = MayaOriginalFaceBuildHost(namespace=None if namespace == ":" else namespace)
        return ConnectOriginalFaceARKit(host).apply(blendshape, mouth_close_includes_open=mouth_close_includes_open)

    def face_disconnect_original_arkit(self, namespace: str):
        from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
        from adv_py.application.face_conversion import ConnectOriginalFaceARKit
        host = MayaOriginalFaceBuildHost(namespace=None if namespace == ":" else namespace)
        return ConnectOriginalFaceARKit(host).disconnect()

    def face_asset_export(self, namespace: str, neutral: str, name: str,
                          kind: str, target_mesh: str, destination: Path) -> int:
        target = FaceTarget(name, FaceShapeKind(kind), target_mesh)
        asset = ExportFaceTargetAsset(self._host(namespace)).execute(neutral, target)
        save_face_target_asset(asset, destination)
        return len(asset.deltas)

    def face_asset_import(self, namespace: str, neutral: str, source: Path,
                          target_mesh: str) -> int:
        asset = load_face_target_asset(source)
        result = ImportFaceTargetAsset(self._host(namespace)).apply(
            neutral, asset, target_mesh)
        return len(result.asset.deltas)

    def face_performance_apply(self, namespace: str, control_path: str,
                               source: Path) -> int:
        source = Path(source).expanduser()
        if source.stat().st_size > 8_000_000:
            raise ValueError("面部动画文档超过 8 MB")
        performance = face_performance_from_json(source.read_text(encoding="utf-8"))
        ApplyFacePerformance(self._host(namespace)).apply(control_path, performance)
        return len(performance.samples)

    def face_library_list(self, directory: Path):
        return FaceAssetLibrary(directory).list()

    def face_library_add(self, directory: Path, asset_file: Path,
                         release: str):
        return FaceAssetLibrary(directory).add(load_face_target_asset(asset_file),
                                               release)

    def face_library_export(self, directory: Path, name: str, release: str,
                            destination: Path) -> Path:
        asset = FaceAssetLibrary(directory).resolve(name, release)
        return save_face_target_asset(asset, destination)

    def face_library_merge(self, directory: Path, name: str, base: str,
                           left: str, right: str, release: str):
        return FaceAssetLibrary(directory).merge(name, base, left, right,
                                                 release)

    def presets(self, namespace: str, directory: Path):
        return InspectBodyCharacterPresets(self._host(namespace)).list(directory)

    def preset_apply(self, namespace: str, directory: Path, filename: str) -> int:
        matches = [entry for entry in self.presets(namespace, directory)
                   if entry.filename == filename]
        if len(matches) != 1 or not matches[0].applicable:
            raise ValueError("所选预设不存在或与当前角色不兼容")
        source = Path(directory) / filename
        if matches[0].kind == "pose":
            return self.pose_apply(namespace, source)
        if matches[0].kind == "animation":
            return self.animation_apply(namespace, source)
        raise ValueError("不支持的角色预设类型")

    def publish_fbx(self, namespace: str, destination: Path,
                    start: int, end: int, step: int = 1,
                    curve_policy: str = "sampled_linear",
                    value_tolerance: float = 0.0,
                    matrix_tolerance: float = 0.0, *,
                    euler_filter: bool = False,
                    include_skins: bool = False,
                    progress: Callable[[str], None] | None = None) -> PanelFbxPublication:
        destination = Path(destination).expanduser().absolute()
        if (destination.suffix.lower() != ".fbx" or not destination.parent.is_dir()
                or destination.exists()):
            raise ValueError("FBX 输出须为现有目录中尚不存在的 .fbx 文件")
        if start > end or step < 1:
            raise ValueError("FBX 发布帧范围或采样步长无效")
        selected_policy = BodyFbxCurvePolicy(curve_policy)
        host = self._host(namespace)
        profile = BodyFbxExportProfile(BodyFbxFileVersion.FBX_2020,
            host.scene_up_axis(), host.scene_linear_unit(),
            BodyFbxEncoding.BINARY, selected_policy,
            value_tolerance, matrix_tolerance, euler_filter)
        prefix = "" if namespace == ":" else namespace.strip(":") + ":"
        body_root = prefix + "Root_M"
        provenance = host.capture_body_skeleton(body_root).provenance
        if provenance is None or not provenance.source_container:
            raise ValueError("角色缺少原始 Fit 来源记录")
        container = provenance.source_container
        root_plan = BuildBodyRootMotion(host).plan(
            body_root_name=body_root, source_container=container)
        if root_plan.provenance_blockers:
            raise ValueError("角色 Body 来源无效：" +
                             "；".join(root_plan.provenance_blockers))
        cmds = host._cmds
        original_time = float(cmds.currentTime(query=True))
        original_selection = cmds.ls(selection=True, long=True) or []
        original_modified = bool(cmds.file(query=True, modified=True))
        changed = False
        cmds.undoInfo(openChunk=True, chunkName="发布 FBX")
        try:
            if cmds.objExists(root_plan.root_motion.output_path):
                if progress:
                    progress("检查并刷新已有发布层")
                host.remove_existing_body_export_layer(
                    root_plan.body, root_plan.root_motion)
                changed = True
            if progress:
                progress("构建 Root Motion")
            BuildBodyRootMotion(host).apply(body_root_name=body_root,
                                            source_container=container)
            changed = True
            if progress:
                progress("构建独立导出骨架")
            BuildBodyExportSkeleton(host).apply(body_root_name=body_root,
                                                source_container=container)
            changed = True
            if progress:
                progress("烘焙采样帧")
            baked = BakeBodyExportSkeleton(host).apply(
                start_frame=start, end_frame=end, sample_by=step,
                body_root_name=body_root, source_container=container)
            changed = True
            if progress:
                progress("写入并复核 FBX 文件")
            exported = ExportBodyFbx(host).apply(destination,
                start_frame=start, end_frame=end, sample_by=step,
                body_root_name=body_root, source_container=container,
                profile=profile, include_skins=include_skins)
        except Exception:
            cmds.undoInfo(closeChunk=True)
            if changed:
                cmds.undo()
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                cmds.currentTime(original_time, edit=True, update=True)
                if original_selection:
                    cmds.select(original_selection, replace=True)
                else:
                    cmds.select(clear=True)
                cmds.file(modified=original_modified)
            finally:
                cmds.undoInfo(stateWithoutFlush=True)
            raise
        else:
            cmds.undoInfo(closeChunk=True)
        return PanelFbxPublication(len(baked.plan.body.joints),
            len(baked.plan.bake.frames), exported.artifact.byte_count,
            exported.artifact.content_sha256,
            exported.applied_profile.euler_filtered_curves)

    def publish_migrated_maya_scene(self, namespace: str,
                                    destination: Path) -> int:
        from adv_py.adapters.maya_character_scene_export import (
            MayaCharacterSceneExport)
        return MayaCharacterSceneExport().apply(namespace, destination)

    def mocap_retarget(self, namespace: str, source: Path,
                       mapping: Path, source_namespace: str,
                       start: int, end: int, step: int = 1,
                       mode: str = "fk", *,
                       progress: Callable[[str], None] | None = None) -> PanelMocapResult:
        from adv_py.adapters import MayaMocapClipHost, MayaMocapControlHost

        if start > end or step < 1:
            raise ValueError("动捕帧范围或采样步长无效")
        services = {"fk": RetargetMocapFullFkToCharacter,
                    "limb-ik": RetargetMocapFullLimbIkToCharacter,
                    "full-ik": RetargetMocapFullIkToCharacter}
        if mode not in services:
            raise ValueError("不支持的动捕写入模式")
        preset = load_mocap_mapping_preset(mapping)
        target_namespace = "" if namespace == ":" else namespace
        target = MayaMocapControlHost(namespace=target_namespace)
        target.read_character_registration()
        clip_host = MayaMocapClipHost()
        if progress:
            progress("在独立进程读取并校验动捕 FBX")
        imported = ImportMocapFbx(clip_host).apply(source,
            namespace=source_namespace)
        try:
            if progress:
                progress("按映射预设写入角色控制曲线")
            samples = services[mode](target).apply_with_preset(imported.snapshot.root,
                preset, start_frame=start, end_frame=end, sample_by=step)
        except Exception:
            if progress:
                progress("写入失败，撤销本次来源导入")
            clip_host.rollback_import(source_namespace)
            raise
        return PanelMocapResult(len(imported.clip.joints), len(samples[0]),
                                imported.snapshot.root)
