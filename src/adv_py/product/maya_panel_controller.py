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
    BuildFaceBlendShapes, BuildRegisteredBodyCharacter,
    CaptureBodyCharacterAnimation, CaptureBodyCharacterPose,
    CaptureAnimatedBodyCharacterPose, KeyBodyCharacterPose,
    EnableBodyCharacterLimbAnimation, EnableBodyCharacterStretchMatching,
    EnableBodyCharacterSplineAnimation, EnableBodyCharacterSpaceAnimation,
    BakeBodyCharacterLimbMode, BakeBodyCharacterSpineMode,
    SwitchBodyCharacterSpace,
    AutoScaleControlCurves, ColorControlCurves, MirrorControlCurves,
    ScaleControlCurves, SwapControlCurves,
    SetControlOrientationAxis,
    DetachCustomControlOrientations, AttachCustomControlOrientations,
    CreateAndImportFitSkeleton, EditFitJointMetadata, EditFitJointPositions,
    ExportFitSkeleton, ExportSkinWeights, OrientSimpleFitChain,
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
from adv_py.core.variable_body_fit import variable_axial_description

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
                   container: str = "FitSkeleton") -> int:
        result = ExportFitSkeleton(self._host(namespace)).apply(destination, container)
        return len(result.plan.document.joints)

    def fit_import(self, namespace: str, source: Path,
                   container: str = "FitSkeleton") -> int:
        result = CreateAndImportFitSkeleton(self._host(namespace)).apply(
            source, container)
        return len(result.joint_paths)

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
                   head_aim: bool = False) -> PanelCharacter:
        description = (variable_axial_description(spine_segments)
            if spine_segments is not None else None)
        result = BuildRegisteredBodyCharacter(self._host(namespace)).apply(
            container, axial_description=description, include_head_aim=head_aim)
        return PanelCharacter(namespace, True, len(result.registration.body),
                              len(result.registration.channels))

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
        result = SetControlOrientationAxis(host).apply(
            tuple(dict.fromkeys(resolved)), primary, secondary,
            curve_unaffected, mirror, mirrored_behavior)
        return len(result.verified)

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

    def skin_bind(self, namespace: str, mesh: str,
                  influences: tuple[str, ...], skin: str, maximum: int, *,
                  maintain_maximum: bool = True) -> int:
        result = BindSkin(self._host(namespace)).apply(mesh, influences,
            skin_name=skin, maximum_influences=maximum,
            maintain_maximum_influences=maintain_maximum)
        return result.plan.input_state.vertex_count

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
        container = "|" + prefix + "FitSkeleton"
        if progress:
            progress("构建 Root Motion")
        BuildBodyRootMotion(host).apply(body_root_name=body_root,
                                        source_container=container)
        if progress:
            progress("构建独立导出骨架")
        BuildBodyExportSkeleton(host).apply(body_root_name=body_root,
                                            source_container=container)
        if progress:
            progress("烘焙采样帧")
        baked = BakeBodyExportSkeleton(host).apply(start_frame=start,
            end_frame=end, sample_by=step, body_root_name=body_root,
            source_container=container)
        if progress:
            progress("写入并复核 FBX 文件")
        exported = ExportBodyFbx(host).apply(destination, start_frame=start,
            end_frame=end, sample_by=step, body_root_name=body_root,
            source_container=container, profile=profile)
        return PanelFbxPublication(len(baked.plan.body.joints),
            len(baked.plan.bake.frames), exported.artifact.byte_count,
            exported.artifact.content_sha256,
            exported.applied_profile.euler_filtered_curves)

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
