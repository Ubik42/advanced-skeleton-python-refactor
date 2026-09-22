"""Maya-facing preflight and transactional cross-topology weight transfer."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Protocol

from adv_py.core.face_shapes import FaceMeshSnapshot
from adv_py.core.face_neutral_geometry import FaceNeutralGeometry
from adv_py.core.face_surface_transfer import FaceSurfaceAlignment, Triangle
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.body_fbx_export import BodyFbxLinearUnit
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_weight_io import (SkinWeightDocument, SkinWeightPathMapping,
    remap_skin_weight_document, skin_weight_document_from_state)
from adv_py.core.skin_weight_surface_transfer import (
    SkinWeightSurfaceTransferResult, transfer_skin_weights_by_surface)
from adv_py.core.skin_weight_surface_source import (SkinWeightSurfaceSource,
    SKIN_WEIGHT_SURFACE_SOURCE_MAX_BYTES,
    skin_weight_surface_source_from_json, skin_weight_surface_source_to_json)
from adv_py.core.skin_weights import SkinWeightInputState, SkinWeightValidationError

from .skin_weight_io import SkinWeightDocumentHost
from .skin_weights import EditSkinWeights, SkinWeightEditResult


class SkinWeightSurfaceHost(SkinWeightDocumentHost, Protocol):
    def capture_face_mesh(self, path: str) -> FaceMeshSnapshot: ...
    def capture_face_triangles(self, path: str) -> tuple[Triangle, ...]: ...
    def scene_up_axis(self) -> FitUpAxis: ...
    def scene_linear_unit(self) -> BodyFbxLinearUnit: ...


@dataclass(frozen=True, slots=True)
class SkinWeightSurfacePlan:
    source_state: SkinWeightInputState
    target_state: SkinWeightInputState
    source_mesh: FaceMeshSnapshot
    target_mesh: FaceMeshSnapshot
    source_triangles: tuple[Triangle, ...]
    transfer: SkinWeightSurfaceTransferResult


@dataclass(frozen=True, slots=True)
class SkinWeightSurfaceResult:
    plan: SkinWeightSurfacePlan
    edit_result: SkinWeightEditResult


@dataclass(frozen=True, slots=True)
class SkinWeightDocumentSurfacePlan:
    source_document: SkinWeightDocument
    source_geometry: FaceNeutralGeometry
    target_state: SkinWeightInputState
    target_mesh: FaceMeshSnapshot
    transfer: SkinWeightSurfaceTransferResult


class TransferSkinWeightsBySurface:
    """Transfer weights between different meshes captured at compatible neutral poses."""

    def __init__(self, host: SkinWeightSurfaceHost) -> None:
        self._host = host
        self._editor = EditSkinWeights(host)

    def plan(self, source_skin: str, source_mesh: str, target_skin: str,
             target_mesh: str, *, max_distance: float,
             max_discarded_weight: float = 0.0,
             mapping: SkinWeightPathMapping | None = None,
             alignment: FaceSurfaceAlignment | None = None) -> SkinWeightSurfacePlan:
        if source_mesh == target_mesh or source_skin == target_skin:
            raise FitSkeletonValidationError("表面权重转移需要不同的源和目标 skinCluster/mesh")
        source_state = self._host.capture_all_skin_weights(source_skin, source_mesh)
        target_state = self._host.capture_all_skin_weights(target_skin, target_mesh)
        source_geometry = self._host.capture_face_mesh(source_mesh)
        target_geometry = self._host.capture_face_mesh(target_mesh)
        triangles = self._host.capture_face_triangles(source_mesh)
        document = skin_weight_document_from_state(source_state)
        if mapping is not None:
            if mapping.target_skin_name != target_skin or mapping.target_mesh_path != target_mesh:
                raise FitSkeletonValidationError("权重路径映射与目标 skinCluster/mesh 不一致")
            document = remap_skin_weight_document(document, mapping)
        transfer = transfer_skin_weights_by_surface(document, source_geometry,
            target_geometry, triangles, target_state, max_distance=max_distance,
            max_discarded_weight=max_discarded_weight, alignment=alignment)
        edit_plan = self._editor.plan(target_skin, target_mesh, transfer.document.vertices)
        if not edit_plan.ready:
            raise FitSkeletonValidationError("表面权重转移目标预检失败，场景未修改："
                                             + "；".join(edit_plan.blockers))
        return SkinWeightSurfacePlan(source_state, target_state, source_geometry,
                                     target_geometry, triangles, transfer)

    def apply(self, source_skin: str, source_mesh: str, target_skin: str,
              target_mesh: str, *, max_distance: float,
              max_discarded_weight: float = 0.0,
              mapping: SkinWeightPathMapping | None = None,
              alignment: FaceSurfaceAlignment | None = None) -> SkinWeightSurfaceResult:
        plan = self.plan(source_skin, source_mesh, target_skin, target_mesh,
            max_distance=max_distance, max_discarded_weight=max_discarded_weight,
            mapping=mapping, alignment=alignment)
        if (self._host.capture_all_skin_weights(source_skin, source_mesh) != plan.source_state
            or self._host.capture_all_skin_weights(target_skin, target_mesh) != plan.target_state
            or self._host.capture_face_mesh(source_mesh) != plan.source_mesh
            or self._host.capture_face_mesh(target_mesh) != plan.target_mesh
            or self._host.capture_face_triangles(source_mesh) != plan.source_triangles):
            raise FitSkeletonValidationError("表面权重转移输入在执行前发生变化")
        edit = self._editor.apply(target_skin, target_mesh, plan.transfer.document.vertices)
        if self._host.capture_all_skin_weights(source_skin, source_mesh) != plan.source_state:
            raise RuntimeError("表面权重转移后源权重发生变化")
        return SkinWeightSurfaceResult(plan, edit)

    def plan_from_documents(self, weights: SkinWeightDocument,
            geometry: FaceNeutralGeometry, target_skin: str, target_mesh: str,
            *, max_distance: float, max_discarded_weight: float = 0.,
            mapping: SkinWeightPathMapping | None = None,
            alignment: FaceSurfaceAlignment | None = None
            ) -> SkinWeightDocumentSurfacePlan:
        if weights.mesh_path != geometry.mesh.path or weights.vertex_count != geometry.mesh.vertex_count:
            raise FitSkeletonValidationError("源权重文档与源几何文档不属于同一网格")
        if (geometry.up_axis != self._host.scene_up_axis().value
                or geometry.linear_unit != self._host.scene_linear_unit().value):
            raise FitSkeletonValidationError("源几何与目标场景的坐标轴或长度单位不一致")
        if mapping is not None:
            if mapping.target_skin_name != target_skin or mapping.target_mesh_path != target_mesh:
                raise FitSkeletonValidationError("权重路径映射与目标 skinCluster/mesh 不一致")
            mapped = remap_skin_weight_document(weights, mapping)
        else:
            mapped = weights
        target_state = self._host.capture_all_skin_weights(target_skin, target_mesh)
        target_geometry = self._host.capture_face_mesh(target_mesh)
        transfer = transfer_skin_weights_by_surface(mapped, geometry.mesh,
            target_geometry, geometry.triangles, target_state,
            max_distance=max_distance, max_discarded_weight=max_discarded_weight,
            alignment=alignment)
        edit_plan = self._editor.plan(target_skin, target_mesh, transfer.document.vertices)
        if not edit_plan.ready:
            raise FitSkeletonValidationError("表面权重转移目标预检失败，场景未修改："
                                             + "；".join(edit_plan.blockers))
        return SkinWeightDocumentSurfacePlan(weights, geometry, target_state,
                                              target_geometry, transfer)

    def apply_from_documents(self, weights: SkinWeightDocument,
            geometry: FaceNeutralGeometry, target_skin: str, target_mesh: str,
            *, max_distance: float, max_discarded_weight: float = 0.,
            mapping: SkinWeightPathMapping | None = None,
            alignment: FaceSurfaceAlignment | None = None
            ) -> tuple[SkinWeightDocumentSurfacePlan, SkinWeightEditResult]:
        plan = self.plan_from_documents(weights, geometry, target_skin, target_mesh,
            max_distance=max_distance, max_discarded_weight=max_discarded_weight,
            mapping=mapping, alignment=alignment)
        if (self._host.capture_all_skin_weights(target_skin, target_mesh) != plan.target_state
                or self._host.capture_face_mesh(target_mesh) != plan.target_mesh
                or self._host.scene_up_axis().value != geometry.up_axis
                or self._host.scene_linear_unit().value != geometry.linear_unit):
            raise FitSkeletonValidationError("表面权重转移目标在执行前发生变化")
        edit = self._editor.apply(target_skin, target_mesh, plan.transfer.document.vertices)
        return plan, edit


class CaptureSkinWeightSurfaceSource:
    """Capture geometry in the same scene/pose as a complete source weight document."""

    def __init__(self, host: SkinWeightSurfaceHost) -> None:
        self._host = host

    def execute(self, skin_name: str, mesh_path: str) -> SkinWeightSurfaceSource:
        state = self._host.capture_all_skin_weights(skin_name, mesh_path)
        document = skin_weight_document_from_state(state)
        if document.skin_name != skin_name or document.mesh_path != mesh_path:
            raise FitSkeletonValidationError("源 skinCluster/mesh 与场景快照不一致")
        mesh = self._host.capture_face_mesh(mesh_path)
        triangles = self._host.capture_face_triangles(mesh_path)
        geometry = FaceNeutralGeometry(mesh, triangles,
            self._host.scene_up_axis().value, self._host.scene_linear_unit().value)
        if (self._host.capture_all_skin_weights(skin_name, mesh_path) != state
                or self._host.capture_face_mesh(mesh_path) != mesh
                or self._host.capture_face_triangles(mesh_path) != triangles
                or self._host.scene_up_axis().value != geometry.up_axis
                or self._host.scene_linear_unit().value != geometry.linear_unit):
            raise FitSkeletonValidationError("源权重或几何在捕获期间发生变化")
        source = SkinWeightSurfaceSource(document, geometry)
        skin_weight_surface_source_to_json(source)
        return source


def save_skin_weight_surface_source(source: SkinWeightSurfaceSource,
                                    destination: Path) -> Path:
    destination = Path(destination).expanduser().absolute()
    if destination.suffix.casefold() != ".json" or not destination.parent.is_dir():
        raise FitSkeletonValidationError("源资产目标须为现有目录中的 .json 文件")
    if destination.exists():
        raise FitSkeletonValidationError("源资产目标文件已存在，拒绝覆盖")
    text = skin_weight_surface_source_to_json(source)
    handle, temporary_name = tempfile.mkstemp(prefix=".skin-surface-",
        suffix=".tmp", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if skin_weight_surface_source_from_json(
                temporary.read_text(encoding="utf-8")) != source:
            raise RuntimeError("源资产临时文件复检失败")
        try:
            os.link(temporary, destination)
        except FileExistsError as error:
            raise FitSkeletonValidationError("源资产目标文件已存在，拒绝覆盖") from error
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def load_skin_weight_surface_source(source: Path) -> SkinWeightSurfaceSource:
    source = Path(source).expanduser()
    if source.stat().st_size > SKIN_WEIGHT_SURFACE_SOURCE_MAX_BYTES:
        raise SkinWeightValidationError("表面权重源资产超过 256 MB")
    return skin_weight_surface_source_from_json(source.read_text(encoding="utf-8"))
