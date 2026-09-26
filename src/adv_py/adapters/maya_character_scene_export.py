"""Export a migrated local character without its original Maya reference."""
from __future__ import annotations

from pathlib import Path
import os
import tempfile

from .maya_original_skin_migration import _without_undo_recording


class MayaCharacterSceneExport:
    def __init__(self, cmds=None):
        if cmds is None:
            from maya import cmds as maya_cmds
            cmds = maya_cmds
        self._cmds = cmds

    def apply(self, namespace: str, destination: Path) -> int:
        c = self._cmds
        namespace = namespace.strip(":")
        destination = Path(destination).expanduser().absolute()
        if (not namespace or not namespace.endswith("_AdvPy")
                or not c.namespace(exists=namespace)):
            raise ValueError("请选择从原版引用迁移出的本地角色")
        if (destination.suffix.lower() != ".mb"
                or not destination.parent.is_dir() or destination.exists()):
            raise ValueError("输出须为现有目录中尚不存在的 .mb 文件")
        nodes = c.ls(namespace + ":*", long=True) or []
        if (not nodes or not c.objExists(namespace + ":AdvPy_MigratedMesh")
                or not c.objExists(namespace + ":AdvPy_MigratedSkin")):
            raise ValueError("当前角色没有完整的迁移网格和 Skin")
        if any(c.referenceQuery(node, isNodeReferenced=True) for node in nodes):
            raise ValueError("迁移角色仍包含引用节点")
        pending = list(nodes)
        inspected = set()
        while pending:
            node = pending.pop()
            if node in inspected:
                continue
            inspected.add(node)
            if c.referenceQuery(node, isNodeReferenced=True):
                raise ValueError("迁移角色仍依赖引用节点：" + node)
            pending.extend(c.listConnections(node, source=True,
                                             destination=False) or [])

        selected = c.ls(selection=True, long=True) or []
        handle, temporary_name = tempfile.mkstemp(
            prefix="." + destination.stem + "-", suffix=".mb",
            dir=destination.parent)
        os.close(handle)
        temporary = Path(temporary_name)
        try:
            with _without_undo_recording(c):
                try:
                    c.select(clear=True)
                    c.select(nodes, replace=True, noExpand=True)
                    c.file(str(temporary), exportSelected=True,
                           type="mayaBinary", force=True,
                           preserveReferences=False)
                finally:
                    c.select(clear=True)
                    if selected:
                        c.select(selected, replace=True, noExpand=True)
            if temporary.stat().st_size == 0:
                raise RuntimeError("Maya 未写出有效角色场景")
            os.link(temporary, destination)
            return destination.stat().st_size
        finally:
            temporary.unlink(missing_ok=True)
