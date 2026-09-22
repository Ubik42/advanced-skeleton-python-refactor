"""Read-only cross-topology sculpt transfer from two neutral scene meshes."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Protocol

from adv_py.core.character_registry import (CharacterRegistration,
    CharacterRegistryError)
from adv_py.core.face_shapes import FaceMeshSnapshot
from adv_py.core.face_target_asset import FaceTargetAsset
from adv_py.core.face_neutral_geometry import (FaceNeutralGeometry,
    FACE_NEUTRAL_GEOMETRY_MAX_BYTES, face_neutral_geometry_from_json,
    face_neutral_geometry_to_json)
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

    def execute_from_geometry(self, geometry: FaceNeutralGeometry,
                              target_neutral: str, asset: FaceTargetAsset, *,
                              max_distance: float) -> FaceAssetTransferPlan:
        if not isinstance(geometry, FaceNeutralGeometry):
            raise ValueError("源中性几何文档无效")
        registration = self._host.read_character_registration()
        destination = self._host.capture_face_mesh(target_neutral)
        if geometry.mesh.topology_digest == destination.topology_digest:
            raise ValueError("两个中性网格拓扑相同，应使用普通目标资产导入")
        result = transfer_face_target_asset(geometry.mesh, destination,
            geometry.triangles, asset, max_distance=max_distance)
        if (self._host.read_character_registration() != registration
                or self._host.capture_face_mesh(target_neutral) != destination):
            raise CharacterRegistryError("转移期间角色或目标中性网格发生变化")
        return FaceAssetTransferPlan(registration, geometry.mesh, destination,
                                     geometry.triangles, result)


class ExportFaceNeutralGeometry:
    def __init__(self, host: FaceSurfaceTransferHost):
        self._host = host

    def execute(self, neutral_mesh: str) -> FaceNeutralGeometry:
        registration = self._host.read_character_registration()
        mesh = self._host.capture_face_mesh(neutral_mesh)
        triangles = self._host.capture_face_triangles(neutral_mesh)
        geometry = FaceNeutralGeometry(mesh, triangles)
        if (self._host.read_character_registration() != registration
                or self._host.capture_face_mesh(neutral_mesh) != mesh
                or self._host.capture_face_triangles(neutral_mesh) != triangles):
            raise CharacterRegistryError("导出期间角色或中性网格发生变化")
        face_neutral_geometry_to_json(geometry)
        return geometry


def save_face_neutral_geometry(geometry: FaceNeutralGeometry,
                               destination: Path) -> Path:
    destination = Path(destination).expanduser().absolute()
    if destination.suffix.casefold() != ".json" or not destination.parent.is_dir():
        raise ValueError("源中性几何目标必须是现有目录中的 .json 文件")
    if destination.exists():
        raise FileExistsError(destination)
    text = face_neutral_geometry_to_json(geometry)
    handle, temporary_name = tempfile.mkstemp(prefix=".face-neutral-",
        suffix=".tmp", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if face_neutral_geometry_from_json(
                temporary.read_text(encoding="utf-8")) != geometry:
            raise RuntimeError("源中性几何临时文档复检失败")
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def load_face_neutral_geometry(source: Path) -> FaceNeutralGeometry:
    source = Path(source).expanduser()
    if source.stat().st_size > FACE_NEUTRAL_GEOMETRY_MAX_BYTES:
        raise ValueError("源中性几何文档超过 128 MB")
    return face_neutral_geometry_from_json(source.read_text(encoding="utf-8"))
