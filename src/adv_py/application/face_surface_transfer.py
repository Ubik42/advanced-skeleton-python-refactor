"""Read-only cross-topology sculpt transfer from two neutral scene meshes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.character_registry import (CharacterRegistration,
    CharacterRegistryError)
from adv_py.core.face_shapes import FaceMeshSnapshot
from adv_py.core.face_target_asset import FaceTargetAsset
from adv_py.core.face_surface_transfer import (FaceSurfaceTransferResult,
    transfer_face_target_asset)


class FaceSurfaceTransferHost(Protocol):
    def read_character_registration(self) -> CharacterRegistration: ...
    def capture_face_mesh(self, path: str) -> FaceMeshSnapshot: ...
    def capture_face_triangles(self, path: str) -> tuple[tuple[int, int, int], ...]: ...


@dataclass(frozen=True, slots=True)
class FaceAssetTransferPlan:
    registration: CharacterRegistration
    source: FaceMeshSnapshot
    destination: FaceMeshSnapshot
    source_triangles: tuple[tuple[int, int, int], ...]
    result: FaceSurfaceTransferResult


class TransferFaceTargetAsset:
    def __init__(self, host: FaceSurfaceTransferHost):
        self._host = host

    def execute(self, source_neutral: str, target_neutral: str,
                asset: FaceTargetAsset, *, max_distance: float
                ) -> FaceAssetTransferPlan:
        if source_neutral == target_neutral:
            raise ValueError("跨拓扑转移需要两个不同的中性网格")
        registration = self._host.read_character_registration()
        source = self._host.capture_face_mesh(source_neutral)
        destination = self._host.capture_face_mesh(target_neutral)
        if source.topology_digest == destination.topology_digest:
            raise ValueError("两个中性网格拓扑相同，应使用普通目标资产导入")
        triangles = self._host.capture_face_triangles(source_neutral)
        result = transfer_face_target_asset(source, destination, triangles,
            asset, max_distance=max_distance)
        if (self._host.read_character_registration() != registration
                or self._host.capture_face_mesh(source_neutral) != source
                or self._host.capture_face_mesh(target_neutral) != destination
                or self._host.capture_face_triangles(source_neutral) != triangles):
            raise CharacterRegistryError("转移期间角色或中性网格发生变化")
        return FaceAssetTransferPlan(registration, source, destination,
                                     triangles, result)
