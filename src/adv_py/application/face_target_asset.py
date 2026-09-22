"""Export and re-create sculpt targets through a validated portable document."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Protocol

from adv_py.core.character_registry import CharacterRegistration, CharacterRegistryError
from adv_py.core.face_shapes import FaceMeshSnapshot, FaceTarget
from adv_py.core.face_target_asset import (FACE_TARGET_ASSET_MAX_BYTES,
    FaceTargetAsset, face_target_asset_from_json, face_target_asset_from_meshes,
    face_target_asset_to_json)


@dataclass(frozen=True, slots=True)
class FaceTargetAssetImportPlan:
    registration: CharacterRegistration
    neutral: FaceMeshSnapshot
    target: FaceTarget
    asset: FaceTargetAsset
    points: tuple[tuple[float, float, float], ...]
    provenance: str


class FaceTargetAssetHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def capture_face_mesh(self, path: str) -> FaceMeshSnapshot: ...
    def face_target_path_available(self, path: str) -> bool: ...
    def create_face_target_from_asset(self, plan: FaceTargetAssetImportPlan) -> None: ...
    def read_face_target_provenance(self, path: str) -> str: ...


class ExportFaceTargetAsset:
    def __init__(self, host: FaceTargetAssetHost):
        self._host = host

    def execute(self, neutral_mesh: str, target: FaceTarget) -> FaceTargetAsset:
        if not isinstance(target, FaceTarget):
            raise ValueError("面部目标语义无效")
        registration = self._host.read_character_registration()
        neutral = self._host.capture_face_mesh(neutral_mesh)
        sculpt = self._host.capture_face_mesh(target.mesh)
        asset = face_target_asset_from_meshes(neutral, target, sculpt)
        if (self._host.read_character_registration() != registration
                or self._host.capture_face_mesh(neutral_mesh) != neutral
                or self._host.capture_face_mesh(target.mesh) != sculpt):
            raise CharacterRegistryError("导出面部目标时角色或网格发生变化")
        face_target_asset_to_json(asset)
        return asset


class ImportFaceTargetAsset:
    def __init__(self, host: FaceTargetAssetHost):
        self._host = host

    def plan(self, neutral_mesh: str, asset: FaceTargetAsset,
             target_mesh: str) -> FaceTargetAssetImportPlan:
        asset = face_target_asset_from_json(face_target_asset_to_json(asset))
        target = FaceTarget(asset.name, asset.kind, target_mesh)
        if (target.mesh != "|" + target.mesh.lstrip("|")
                or "|" in target.mesh[1:] or target.mesh == neutral_mesh):
            raise ValueError("导入目标须位于角色命名空间根部")
        registration = self._host.read_character_registration()
        neutral = self._host.capture_face_mesh(neutral_mesh)
        if not self._host.face_target_path_available(target.mesh):
            raise CharacterRegistryError("导入目标路径已存在：" + target.mesh)
        points = asset.points_for(neutral)
        document = json.loads(face_target_asset_to_json(asset))
        provenance = json.dumps({"version": 1, "source": "portable_asset",
            "asset_digest": document["digest"],
            "neutral_topology": asset.topology_digest,
            "neutral_positions": asset.neutral_position_digest,
            "channel": asset.name, "kind": asset.kind.value},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return FaceTargetAssetImportPlan(registration, neutral, target,
                                         asset, points, provenance)

    def apply(self, neutral_mesh: str, asset: FaceTargetAsset,
              target_mesh: str) -> FaceTargetAssetImportPlan:
        plan = self.plan(neutral_mesh, asset, target_mesh)
        with self._host.transaction("Import portable face target asset"):
            if self.plan(neutral_mesh, asset, target_mesh) != plan:
                raise CharacterRegistryError("面部目标资产或中性网格在写入前发生变化")
            self._host.create_face_target_from_asset(plan)
            self.audit(plan)
        return plan

    def audit(self, plan: FaceTargetAssetImportPlan) -> FaceMeshSnapshot:
        result = self._host.capture_face_mesh(plan.target.mesh)
        if (result.topology_digest != plan.asset.topology_digest
                or result.vertex_count != plan.asset.vertex_count
                or any(abs(a - b) > 1e-6
                       for actual, expected in zip(result.points, plan.points)
                       for a, b in zip(actual, expected))
                or self._host.read_face_target_provenance(plan.target.mesh)
                   != plan.provenance):
            raise RuntimeError("导入目标的几何或资产来源复检失败")
        return result


def save_face_target_asset(asset: FaceTargetAsset, destination: Path) -> Path:
    destination = Path(destination).expanduser().absolute()
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    text = face_target_asset_to_json(asset)
    handle, temporary_name = tempfile.mkstemp(prefix=".face-asset-",
        suffix=".tmp", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if face_target_asset_from_json(temporary.read_text(encoding="utf-8")) != asset:
            raise RuntimeError("面部目标资产临时文件复检失败")
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def load_face_target_asset(source: Path) -> FaceTargetAsset:
    source = Path(source).expanduser()
    if source.stat().st_size > FACE_TARGET_ASSET_MAX_BYTES:
        raise ValueError("面部目标资产文件超过 64 MB")
    return face_target_asset_from_json(source.read_text(encoding="utf-8"))
