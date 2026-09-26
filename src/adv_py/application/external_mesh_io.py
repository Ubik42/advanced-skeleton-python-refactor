"""Move one evaluated Maya mesh into a clean character scene."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Protocol

from adv_py.core.fit_settings import FitSkeletonValidationError


class ExternalMeshHost(Protocol):
    def capture_mesh_vertex_count(self, mesh: str) -> int: ...
    def export_static_mesh(self, mesh: str, destination: Path) -> None: ...
    def import_static_mesh(self, source: Path, namespace: str) -> str: ...


@dataclass(frozen=True, slots=True)
class ExternalMeshResult:
    path: Path
    mesh: str
    vertex_count: int


def _asset_path(value: str | os.PathLike[str]) -> Path:
    path = Path(value).expanduser().resolve()
    if path.suffix.casefold() != ".ma":
        raise FitSkeletonValidationError("静态网格资产必须是 .ma 文件")
    return path


class ExportExternalMesh:
    def __init__(self, host: ExternalMeshHost):
        self._host = host

    def apply(self, mesh: str, destination: str | os.PathLike[str]
              ) -> ExternalMeshResult:
        path = _asset_path(destination)
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise FitSkeletonValidationError("网格导出目录不存在或是符号链接")
        if path.exists() or path.is_symlink():
            raise FitSkeletonValidationError("网格导出目标已存在，拒绝覆盖")
        count = self._host.capture_mesh_vertex_count(mesh)
        self._host.export_static_mesh(mesh, path)
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("Maya 未写出静态网格资产")
        return ExternalMeshResult(path, mesh, count)


class ImportExternalMesh:
    def __init__(self, host: ExternalMeshHost):
        self._host = host

    def apply(self, source: str | os.PathLike[str], *,
              namespace: str = "advMesh") -> ExternalMeshResult:
        path = _asset_path(source)
        if not path.is_file():
            raise FitSkeletonValidationError("静态网格资产不存在")
        if not isinstance(namespace, str) or not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*", namespace):
            raise FitSkeletonValidationError("网格命名空间无效")
        mesh = self._host.import_static_mesh(path, namespace)
        return ExternalMeshResult(path, mesh,
                                  self._host.capture_mesh_vertex_count(mesh))
