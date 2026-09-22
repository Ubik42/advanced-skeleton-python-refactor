"""In-process Maya panel actions; scene changes go through application cases."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from adv_py.adapters import MayaFaceHost
from adv_py.application import (ApplyBodyCharacterAnimation,
    ApplyBodyCharacterPose, ApplyFacePerformance, BindSkin,
    BakeBodyExportSkeleton, BuildBodyExportSkeleton, BuildBodyRootMotion,
    BuildFaceBlendShapes, BuildRegisteredBodyCharacter,
    CaptureBodyCharacterAnimation, CaptureBodyCharacterPose,
    CreateAndImportFitSkeleton, ExportFitSkeleton, ExportSkinWeights,
    ExportBodyFbx, ExportFaceTargetAsset, GenerateFaceTarget, ImportFaceTargetAsset,
    FaceAssetLibrary, ImportSkinWeights, InspectBodyCharacterPresets,
    RebuildBodyCharacter, ResolveBodyCharacter,
    ImportMocapFbx, RetargetMocapFullFkToCharacter,
    RetargetMocapFullLimbIkToCharacter, RetargetMocapFullIkToCharacter,
    load_mocap_mapping_preset,
    load_character_animation, load_character_pose, load_face_target_asset,
    save_character_animation, save_character_pose, save_face_target_asset)
from adv_py.core import (BodyFbxCurvePolicy, BodyFbxEncoding,
    BodyFbxExportProfile, BodyFbxFileVersion, FaceShapeKind, FaceTarget,
    face_performance_from_json)
from adv_py.core.variable_body_fit import variable_axial_description

from .input_documents import (load_face_build_spec, load_face_landmarks,
                              load_skin_path_mapping)


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
