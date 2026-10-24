"""Original asFitSkeletonExport, including SDK delete/undo and limb extraction.

Export is intentionally outside the host's normal mutation transaction: the
source has a local delete/undo pair which must never undo a caller's chunk.
"""
from pathlib import Path
from uuid import uuid4

from adv_py.core.character_identity import CharacterIdentity


def source_fit_export_is_limb(path, namespace=''):
    parts = tuple(part for part in path.split('|') if part)
    return (len(parts) > 2 and
            parts[0] == CharacterIdentity(namespace or '').to_scene('FitSkeleton'))


class MayaSourceFitExportMixin:
    def source_fit_export_selection_is_limb(self):
        raw = getattr(self._cmds,'raw',self._cmds)
        return any(source_fit_export_is_limb(path,self.namespace)
                   for path in raw.ls(selection=True,type='joint',long=True) or ())

    def export_source_fit_scene(self, destination):
        if self._transaction_active:
            raise RuntimeError('原版 Fit 导出含独立 SDK 撤销，不能放入另一个事务')
        destination = Path(destination).resolve()
        if destination.suffix.lower() != '.ma' or not destination.parent.is_dir():
            raise ValueError('Fit 导出需要现有目录中的 Maya ASCII 文件路径')
        raw = getattr(self._cmds,'raw',self._cmds)
        if not raw.undoInfo(query=True,state=True):
            raise RuntimeError('请启用 Maya Undo，才能按原版恢复临时删除的 SDK')
        identity = CharacterIdentity(self.namespace or '')
        fit = identity.to_scene('FitSkeleton')
        matches = tuple(raw.ls(fit,long=True) or ())
        if len(matches) != 1:
            raise ValueError('Fit 导出需要唯一的 FitSkeleton')

        def uid(node):
            values = raw.ls(node,uuid=True) or ()
            if len(values) != 1:
                raise ValueError('Fit 导出节点身份不唯一：'+node)
            return values[0]

        def node(value):
            values = raw.ls(value,long=True) or ()
            if len(values) != 1:
                raise RuntimeError('Fit 导出恢复时节点丢失：'+value)
            return values[0]

        fit_uuid = uid(matches[0])
        selected = tuple(raw.ls(selection=True,type='joint',long=True) or ())
        limbs = tuple(uid(path) for path in selected
                      if source_fit_export_is_limb(path,self.namespace))
        parent = tuple(raw.listRelatives(matches[0],parent=True,fullPath=True) or ())
        parent_uuid = uid(parent[0]) if parent else None
        visibility_locked = bool(raw.getAttr(fit+'.visibility',lock=True))
        temporary = None
        original_roots = ()
        limb_parents = []
        preparation_open = False
        raw.undoInfo(openChunk=True,chunkName='ADV Fit export preparation')
        preparation_open = True
        try:
            if visibility_locked:
                raw.setAttr(fit+'.visibility',lock=False)
            raw.setAttr(fit+'.visibility',True)
            if parent_uuid is not None:
                raw.parent(node(fit_uuid),world=True)
            # Native connection query operates on the current selection. It
            # excludes FitSkeleton itself and deduplicates the first transform
            # driving each downstream animation curve in discovery order.
            drivers = []
            for curve in raw.listConnections(source=False,destination=True,type='animCurve') or ():
                sources = raw.listConnections(curve,source=True,destination=False,type='transform') or ()
                if sources and sources[0] != fit and sources[0] not in drivers:
                    drivers.append(sources[0])
            for limb in limbs:
                if temporary is None:
                    temp_name = identity.to_scene('previousFitSkeletonChildren')
                    if raw.objExists(temp_name):
                        raise ValueError('Fit 导出暂存容器已经存在：'+temp_name)
                    temporary = uid(raw.createNode('transform',name=':'+temp_name))
                    original_roots = tuple(uid(path) for path in raw.listRelatives(
                        node(fit_uuid),children=True,type='joint',fullPath=True) or ())
                    if original_roots:
                        raw.parent([node(value) for value in original_roots],node(temporary))
                parents = raw.listRelatives(node(limb),parent=True,fullPath=True) or ()
                limb_parents.append((limb,uid(parents[0]) if parents else None))
                raw.parent(node(limb),node(fit_uuid))
            raw.select(node(fit_uuid),replace=True)
            raw.undoInfo(closeChunk=True)
            preparation_open = False
            # A unique local chunk makes the source's destructive SDK removal
            # reversible independently of hierarchy preparation and callers.
            deletion_chunk = 'ADV Fit export SDK '+uuid4().hex
            deletion_started = False
            try:
                if drivers:
                    if any(not identity.owns(driver) for driver in drivers):
                        raise ValueError('Fit 导出选区包含其他角色的 SDK 驱动')
                    raw.undoInfo(openChunk=True,chunkName=deletion_chunk)
                    try:
                        deletion_started = True
                        raw.delete(drivers)
                    finally:
                        raw.undoInfo(closeChunk=True)
                raw.file(str(destination),force=True,options='v=0;',type='mayaAscii',
                         channels=True,constructionHistory=True,exportSelected=True)
            finally:
                if deletion_started:
                    if raw.undoInfo(query=True,undoName=True) != deletion_chunk:
                        raise RuntimeError('Fit 导出 SDK 撤销栈被外部操作改变，禁止撤销其他操作')
                    raw.undo()
        finally:
            if preparation_open:
                raw.undoInfo(closeChunk=True)
            raw.undoInfo(openChunk=True,chunkName='ADV Fit export restore')
            try:
                # UUIDs survive all temporary reparenting, including a selected
                # ancestor and descendant exported together.
                if parent_uuid is not None:
                    raw.parent(node(fit_uuid),node(parent_uuid))
                if visibility_locked:
                    raw.setAttr(node(fit_uuid)+'.visibility',lock=True)
                for limb,previous_parent in limb_parents:
                    if previous_parent is None:
                        raw.parent(node(limb),world=True)
                    else:
                        raw.parent(node(limb),node(previous_parent))
                if temporary is not None:
                    children = raw.listRelatives(node(temporary),children=True,fullPath=True) or ()
                    if children:
                        raw.parent(children,node(fit_uuid))
                    raw.delete(node(temporary))
            finally:
                raw.undoInfo(closeChunk=True)
        return destination
