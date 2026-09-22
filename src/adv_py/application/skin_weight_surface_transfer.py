"""Maya-facing preflight and transactional cross-topology weight transfer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.face_shapes import FaceMeshSnapshot
from adv_py.core.face_surface_transfer import FaceSurfaceAlignment, Triangle
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_weight_io import (SkinWeightPathMapping,
    remap_skin_weight_document, skin_weight_document_from_state)
from adv_py.core.skin_weight_surface_transfer import (
    SkinWeightSurfaceTransferResult, transfer_skin_weights_by_surface)
from adv_py.core.skin_weights import SkinWeightInputState

from .skin_weight_io import SkinWeightDocumentHost
from .skin_weights import EditSkinWeights, SkinWeightEditResult


class SkinWeightSurfaceHost(SkinWeightDocumentHost, Protocol):
    def capture_face_mesh(self, path: str) -> FaceMeshSnapshot: ...
    def capture_face_triangles(self, path: str) -> tuple[Triangle, ...]: ...


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
