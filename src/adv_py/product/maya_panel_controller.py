"""In-process Maya panel actions; scene changes go through application cases."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adv_py.adapters import MayaFaceHost
from adv_py.application import (ApplyBodyCharacterAnimation,
    ApplyBodyCharacterPose, ApplyFacePerformance, BindSkin,
    BuildFaceBlendShapes, BuildRegisteredBodyCharacter,
    CaptureBodyCharacterAnimation, CaptureBodyCharacterPose,
    CreateAndImportFitSkeleton, ExportFitSkeleton, ExportSkinWeights,
    ExportFaceTargetAsset, GenerateFaceTarget, ImportFaceTargetAsset,
    ImportSkinWeights, InspectBodyCharacterPresets, ResolveBodyCharacter,
    load_character_animation, load_character_pose, load_face_target_asset,
    save_character_animation, save_character_pose, save_face_target_asset)
from adv_py.core import FaceShapeKind, FaceTarget, face_performance_from_json
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
