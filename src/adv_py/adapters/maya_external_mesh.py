"""Maya ASCII transport for one evaluated mesh, without the source rig."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaExternalMeshHost:
    def __init__(self):
        from maya import cmds
        self._cmds = cmds

    def _transform(self, mesh: str) -> str:
        c = self._cmds
        matches = c.ls(mesh, long=True) or []
        if len(matches) != 1:
            raise FitSkeletonValidationError("源网格路径不存在或不唯一")
        path = matches[0]
        if c.nodeType(path) == "mesh":
            parents = c.listRelatives(path, parent=True, fullPath=True) or []
            if len(parents) != 1:
                raise FitSkeletonValidationError("源网格缺少唯一 Transform")
            path = parents[0]
        shapes = c.listRelatives(path, shapes=True, fullPath=True,
                                 noIntermediate=True) or []
        if len(shapes) != 1 or c.nodeType(shapes[0]) != "mesh":
            raise FitSkeletonValidationError("源路径必须只有一个可见多边形网格")
        return path

    def capture_mesh_vertex_count(self, mesh: str) -> int:
        count = int(self._cmds.polyEvaluate(self._transform(mesh), vertex=True))
        if count < 3:
            raise FitSkeletonValidationError("网格至少需要三个顶点")
        return count

    def export_static_mesh(self, mesh: str, destination: Path) -> None:
        c = self._cmds
        source = self._transform(mesh)
        selection = c.ls(selection=True, long=True) or []
        duplicate = None
        temporary = None
        try:
            duplicate = c.duplicate(source, returnRootsOnly=True,
                                    renameChildren=True)[0]
            duplicate = c.parent(duplicate, world=True)[0] if (
                c.listRelatives(duplicate, parent=True) or []) else duplicate
            duplicate = c.rename(duplicate, "AdvPy_SourceMesh")
            c.delete(duplicate, constructionHistory=True)
            if self.capture_mesh_vertex_count(duplicate) != (
                    self.capture_mesh_vertex_count(source)):
                raise RuntimeError("静态网格复制后顶点数变化")
            handle, temporary = tempfile.mkstemp(
                prefix=".adv-mesh-", suffix=".ma", dir=destination.parent)
            os.close(handle)
            c.select(duplicate, replace=True)
            c.file(str(temporary), force=True, type="mayaAscii",
                   exportSelected=True, preserveReferences=False)
            if Path(temporary).stat().st_size == 0:
                raise RuntimeError("Maya 未导出网格")
            try:
                os.link(temporary, destination)
            except FileExistsError as error:
                raise FitSkeletonValidationError("网格导出目标已存在，拒绝覆盖") from error
        finally:
            if duplicate is not None and c.objExists(duplicate):
                c.delete(duplicate)
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            c.select(selection, replace=True) if selection else c.select(clear=True)

    def import_static_mesh(self, source: Path, namespace: str) -> str:
        c = self._cmds
        if c.namespace(exists=namespace):
            raise FitSkeletonValidationError("网格导入命名空间已存在")
        c.file(str(source), i=True, type="mayaAscii",
               namespace=namespace, preserveReferences=False)
        matches = c.ls(namespace + ":AdvPy_SourceMesh", long=True,
                       type="transform") or []
        if len(matches) != 1:
            raise RuntimeError("资产中缺少唯一静态网格")
        self.capture_mesh_vertex_count(matches[0])
        return matches[0]
