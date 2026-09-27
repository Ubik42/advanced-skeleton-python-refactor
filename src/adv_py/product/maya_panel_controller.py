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
    SetControlOrientationAxis,
    SetControlOrientationWorld,
    SetControlOrientationWorldAxisMatch,
    SetControlOrientationWorldMatch,
    DetachCustomControlOrientations, AttachCustomControlOrientations,
    CreateAndImportFitSkeleton, EditFitJointMetadata, EditFitJointPositions,
    ExportFitSkeleton, ExportExternalFitSkeleton, ExportSkinWeights,
    OrientSimpleFitChain,
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
})
_FIT_BOOLEAN_FIELDS = frozenset({
    FitJointField.UNTWISTER,
    FitJointField.NO_MIRROR,
    FitJointField.NO_MIRROR_LEFT,
    FitJointField.GLOBAL_TRANSLATE,
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

    def _host(self, namespace: str):
        if not isinstance(namespace, str) or not namespace.strip():
            raise ValueError("请选择角色命名空间")
        return self._host_factory(namespace=None if namespace == ":" else namespace)

    def model_check(self):
        from adv_py.adapters.maya_model_checker import MayaModelCheckHost
        from adv_py.application.model_check import CheckModel

        return CheckModel(MayaModelCheckHost()).execute()

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

    def preparation_one_joint_prop(self, namespace: str):
        from adv_py.adapters.maya_one_joint_prop import MayaOneJointPropHost
        from adv_py.application.one_joint_prop import BuildOneJointProp

        skins = self.preparation_read_objects(namespace, "Skin")
        all_meshes = self.preparation_read_objects(namespace, "All")
        return BuildOneJointProp(MayaOneJointPropHost(
            namespace=None if namespace == ":" else namespace)).apply(
            skins, all_meshes)

    def characters(self) -> tuple[PanelCharacter, ...]:
        from adv_py.adapters.maya_scene_gateway import MayaSceneGateway

        entries = []
        for namespace in MayaSceneGateway().namespaces():
            label = namespace or ":"
            host = self._host(label)
            resolver = ResolveBodyCharacter(host)
            names = resolver.discover()
            if not names:
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
        result = EditFitJointPositions(self._host(namespace)).apply(patch, container)
        return len(result.plan.changes)

    def fit_edit_metadata(self, namespace: str, joints: tuple[str, ...],
                          field: str, value: str, *, remove: bool = False) -> int:
        key, parsed = parse_fit_metadata_value(field, value, remove=remove)
        patch = FitJointPatch((FitJointFieldEdit(key, parsed),))
        result = EditFitJointMetadata(self._host(namespace)).apply(joints, patch)
        return len(result.plan.changes)

    def fit_orient(self, namespace: str, joints: tuple[str, ...],
                   container: str = "FitSkeleton", *,
                   child_selections: tuple[tuple[str, str], ...] = (),
                   world: bool = False) -> int:
        request = FitOrientationRequest(joints, tuple(
            FitOrientationChildSelection(joint, child)
            for joint, child in child_selections))
        use_case = OrientWorldFitJoints if world else OrientSimpleFitChain
        result = use_case(self._host(namespace)).apply(request, container)
        return len(result.plan.changes)

    def body_build(self, namespace: str, container: str = "FitSkeleton", *,
                   spine_segments: int | None = None,
                   head_aim: bool = False,
                   infer_missing_labels: bool = False,
                   meshes: tuple[str, ...] = (),
                   maximum_influences: int = 4,
                   segment_influences: bool = False) -> PanelCharacter:
        from adv_py.application.character_from_fit import BuildCharacterFromFit

        host = self._host(namespace)
        result = BuildCharacterFromFit(host).apply(
            container, meshes=meshes, spine_segments=spine_segments,
            maximum_influences=maximum_influences,
            include_head_aim=head_aim,
            infer_missing_labels=infer_missing_labels,
            include_segment_influences=segment_influences)
        character = result.body
        return PanelCharacter(namespace, True, len(character.registration.body),
                              len(character.registration.channels),
                              segment_joint_count=len(character.segment_influences))

    def body_build_from_source(self, namespace: str, source_root: str,
                               container: str = "FitSkeleton", *,
                               meshes: tuple[str, ...] = (),
                               maximum_influences: int = 4,
                               head_aim: bool = False,
                               segment_influences: bool = True) -> PanelCharacter:
        from adv_py.adapters.maya_source_skeleton_fit import (
            MayaSourceSkeletonFitHost)
        from adv_py.application.character_from_source import (
            BuildCharacterFromSourceSkeleton)
        from maya import cmds

        if not source_root.strip():
            raise ValueError("请填写来源骨架根关节路径")
        target_namespace, created_namespace = _target_for_source_skeleton(
            cmds, namespace, source_root)
        try:
            host = MayaSourceSkeletonFitHost(
                namespace=None if target_namespace == ":" else target_namespace)
            built = BuildCharacterFromSourceSkeleton(host).apply(
                source_root, container, meshes=meshes,
                maximum_influences=maximum_influences,
                include_head_aim=head_aim,
                include_segment_influences=segment_influences)
        except Exception:
            _remove_empty_source_target(cmds, created_namespace)
            raise
        character = built.character.body
        return PanelCharacter(target_namespace, True, len(character.registration.body),
                              len(character.registration.channels),
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
                     progress: Callable[[str], None] | None = None) -> PanelCharacter:
        if not isinstance(replacement, str) or not replacement.strip():
            raise ValueError("请填写尚未占用的重建暂存命名空间")
        host = self._host_factory(namespace="" if namespace == ":" else namespace)
        if progress:
            progress("暂存替换角色并核对需保留的数据")
        result = RebuildBodyCharacter(host).apply(replacement.strip(),
            extensions=extensions)
        if progress:
            progress("替换完成，原角色与保留数据已复核")
        return PanelCharacter(namespace, True, len(result.registration.body),
                              len(result.registration.channels))

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
            resolver = ResolveBodyCharacter(host)
            names = resolver.discover()
            if len(names) != 1:
                raise ValueError("当前命名空间必须恰好包含一个已登记角色")
            registration = resolver.execute(names[0])
            controls = tuple(dict.fromkeys(
                channel.node for channel in registration.channels))
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
        result = AutoScaleControlCurves(host).apply(
            controls, mesh.strip(), semantics, strict=strict)
        return len(result.verified)

    def control_curves_mirror(self, namespace: str, controls: tuple[str, ...],
                              source_side: str) -> int:
        if source_side not in ("R", "L"):
            raise ValueError("镜像来源侧必须是 R 或 L")
        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        if len(names) != 1:
            raise ValueError("当前命名空间必须恰好包含一个已登记角色")
        registration = resolver.execute(names[0])
        registered = tuple(dict.fromkeys(
            channel.node for channel in registration.channels))
        registered_set = set(registered)
        marker = "_" + source_side
        opposite = "_" + ("L" if source_side == "R" else "R")
        sources = controls or tuple(path for path in registered
                                    if re.search(re.escape(marker) + r"(?=\||$)", path))
        pairs = []
        for source in sources:
            matches = [path for path in registered
                       if path == source or path.rsplit("|", 1)[-1] == source]
            if len(matches) != 1:
                raise ValueError(f"镜像来源控制器未登记或名称不唯一：{source}")
            source_path = matches[0]
            if not re.search(re.escape(marker) + r"(?=\||$)", source_path):
                raise ValueError(f"控制器不属于来源侧 {source_side}：{source_path}")
            target = re.sub(re.escape(marker) + r"(?=\||$)", opposite,
                            source_path)
            if target not in registered_set:
                raise ValueError(f"镜像目标控制器未登记：{target}")
            pairs.append((source_path, target))
        result = MirrorControlCurves(host).apply(tuple(dict.fromkeys(pairs)), "x")
        return len(result.verified)

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

    def control_orient_axis(self, namespace: str, controls: tuple[str, ...],
                            primary: str, secondary: str,
                            curve_unaffected: bool = False,
                            mirror: bool = False,
                            mirrored_behavior: bool = False) -> int:
        host, resolved = self._control_orient_targets(
            namespace, controls, mirror)
        result = SetControlOrientationAxis(host).apply(
            resolved, primary, secondary,
            curve_unaffected, mirror, mirrored_behavior)
        return len(result.verified)

    def control_orient_world(self, namespace: str, controls: tuple[str, ...],
                             curve_unaffected: bool = False,
                             mirror: bool = False) -> int:
        host, resolved = self._control_orient_targets(
            namespace, controls, mirror)
        result = SetControlOrientationWorld(host).apply(
            resolved, curve_unaffected, mirror)
        return len(result.verified)

    def control_orient_world_axis_match(
            self, namespace: str, controls: tuple[str, ...],
            curve_unaffected: bool = False,
            mirror: bool = False) -> int:
        host, resolved = self._control_orient_targets(
            namespace, controls, mirror)
        result = SetControlOrientationWorldAxisMatch(host).apply(
            resolved, curve_unaffected, mirror)
        return len(result.verified)

    def control_orient_world_match(self, namespace: str,
                                   controls: tuple[str, ...], primary: str,
                                   secondary: str, world_up: str,
                                   curve_unaffected: bool = False,
                                   mirror: bool = False,
                                   child_selections: tuple[tuple[str, str], ...]
                                   = ()) -> int:
        host, resolved = self._control_orient_targets(
            namespace, controls, mirror)
        mapped = []
        for requested, child in child_selections:
            matches = tuple(path for path in resolved
                            if path == requested
                            or path.rsplit("|", 1)[-1] == requested)
            if len(matches) != 1:
                raise ValueError(
                    f"World Match 子关节指定的控制器未登记或名称不唯一：{requested}")
            mapped.append((matches[0], child))
        result = SetControlOrientationWorldMatch(host).apply(
            resolved, primary, secondary, world_up,
            curve_unaffected, mirror, tuple(mapped))
        return len(result.verified)

    def _control_orient_targets(self, namespace, controls, mirror):
        if not controls:
            raise ValueError("请指定至少一个已登记控制器")
        host = self._host(namespace)
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
        host = self._host(namespace)
        resolver = ResolveBodyCharacter(host)
        names = resolver.discover()
        if len(names) != 1:
            raise ValueError("当前命名空间必须恰好包含一个已登记角色")
        registration = resolver.execute(names[0])
        controls = tuple(dict.fromkeys(
            channel.node for channel in registration.channels))
        controls = tuple(state.control for state in
            host.capture_control_curves(controls, strict=False))
        return DetachCustomControlOrientations(host).apply(controls)

    def control_orient_custom_attach(self, namespace: str) -> int:
        host = self._host(namespace)
        return AttachCustomControlOrientations(host).apply()

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
                                match_pose: bool):
        from adv_py.adapters.maya_unreal_mannequin import MayaMannequinHost
        from adv_py.application.unreal_mannequin import CreateMannequin

        host = MayaMannequinHost(
            namespace=None if namespace == ":" else namespace)
        return CreateMannequin(host).apply(
            template_path, template=template,
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

    def unreal_twist_hierarchy(self, namespace: str, enable: bool) -> int:
        from adv_py.adapters.maya_unreal_twist import MayaUnrealTwistHost
        from adv_py.application.unreal_twist import SetUnrealTwistHierarchy

        host = MayaUnrealTwistHost(
            namespace=None if namespace == ":" else namespace)
        return SetUnrealTwistHierarchy(host).apply(enable)

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
                  influences: tuple[str, ...], skin: str, maximum: int, *,
                  maintain_maximum: bool = True) -> int:
        result = BindSkin(self._host(namespace)).apply(mesh, influences,
            skin_name=skin, maximum_influences=maximum,
            maintain_maximum_influences=maintain_maximum)
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

    def delta_mush_apply(self) -> int:
        from adv_py.adapters.maya_delta_mush import apply_delta_mush_to_selected

        return len(apply_delta_mush_to_selected())

    def delta_mush_harden_weights(self) -> int:
        from adv_py.adapters.maya_delta_mush import harden_weights_on_selected

        return len(harden_weights_on_selected())

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

    def animation_bake_spine(self, namespace: str, start: int, end: int,
                             mode: str, step: int = 1) -> int:
        animation = BakeBodyCharacterSpineMode(self._host(namespace)).execute(
            start, end, mode, step)
        return len(animation.samples)

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

    def face_pre_record_mask(self, namespace: str):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import RecordFacePreInput

        return RecordFacePreInput(MayaFacePreHost(
            namespace=None if namespace == ":" else namespace)).mask()

    def face_pre_record_objects(self, namespace: str, role: str,
                                head_joint: str):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import FacePreRole, RecordFacePreInput

        return RecordFacePreInput(MayaFacePreHost(
            namespace=None if namespace == ":" else namespace)).objects(
                FacePreRole(role), head_joint or "Head_M")

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

    def face_fit_eye_ball(self, namespace: str, eye_mesh: str,
                          head_joint: str) -> str:
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import CreateFaceEyeBallFit

        return CreateFaceEyeBallFit(MayaFacePreHost(
            namespace=None if namespace == ":" else namespace)).execute(
                eye_mesh, head_joint or "Head_M")

    def face_fit_eye_lid(self, namespace: str, layer: str):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import CreateFaceEyeLidFit, EyeLidLayer

        return CreateFaceEyeLidFit(MayaFacePreHost(
            namespace=None if namespace == ":" else namespace)).execute(
                EyeLidLayer(layer))

    def face_fit_eye_lid_reselect(self, namespace: str, layer: str) -> int:
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import EyeLidLayer

        return MayaFacePreHost(namespace=None if namespace == ":" else namespace
            ).select_eye_lid_fit(EyeLidLayer(layer))

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

    def face_build_get_include(self, namespace: str) -> str:
        from adv_py.adapters.maya_face_build import MayaFaceBuildHost

        return MayaFaceBuildHost(namespace=None if namespace == ":" else namespace
            ).read_include().value

    def face_build_inspect_inputs(self, namespace: str) -> dict:
        from adv_py.adapters.maya_face_build import MayaFaceBuildHost

        return MayaFaceBuildHost(namespace=None if namespace == ":" else namespace
            ).inspect_build_inputs()

    def face_build_eye_lids(self, namespace: str) -> dict:
        from adv_py.adapters.maya_face_eyelid_rig import MayaFaceEyeLidRigHost
        from adv_py.application.face_eyelid_rig import BuildFaceEyeLids

        return BuildFaceEyeLids(MayaFaceEyeLidRigHost(
            namespace=None if namespace == ":" else namespace)).execute()

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
