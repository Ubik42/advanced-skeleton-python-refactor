"""Maya storage for Preparation / Rig model selections."""
from __future__ import annotations

import json

from adv_py.core.preparation_objects import PreparationObjectRole


_ATTRIBUTES = {
    PreparationObjectRole.SKIN: "objectsSkin",
    PreparationObjectRole.ALL: "objectsAll",
    PreparationObjectRole.RIGHT_EYE: "objectsRightEye",
    PreparationObjectRole.LEFT_EYE: "objectsLeftEye",
}


class MayaPreparationObjectsHost:
    def __init__(self, namespace: str = ":"):
        from maya import cmds

        self.cmds = cmds
        self.namespace = namespace.strip(":")
        suffix = "_" + self.namespace.replace(":", "_") if self.namespace else ""
        self.storage = "AdvPy_Preparation" + suffix

    def _fit(self) -> str | None:
        expected = (self.namespace + ":" if self.namespace else "") + "FitSkeleton"
        matches = tuple(node for node in self.cmds.ls(type="transform", long=True) or ()
                        if node.rsplit("|", 1)[-1] == expected)
        if len(matches) > 1:
            raise ValueError("当前命名空间有多个 FitSkeleton，无法确定记录目标")
        return matches[0] if matches else None

    def _resolve_name(self, name: str) -> str:
        matches = tuple(self.cmds.ls(name, long=True) or ())
        if len(matches) != 1 or not self.cmds.objExists(matches[0]):
            raise ValueError("准备模型名称已缺失或不唯一：" + name)
        return matches[0]

    def selected_meshes(self) -> tuple[str, ...]:
        cmds = self.cmds
        selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []
        meshes = []
        for node in selected:
            if cmds.nodeType(node) == "mesh":
                node = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
            if not node or cmds.nodeType(node) != "transform":
                continue
            shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                        fullPath=True) or []
            if not any(cmds.nodeType(shape) == "mesh" for shape in shapes):
                continue
            short = node.rsplit("|", 1)[-1].split(":")[-1]
            if short == "Eye" or short.startswith("Eye."):
                raise ValueError("模型不能命名为 Eye；该名称由原版眼部绑定使用")
            if node not in meshes:
                meshes.append(node)
        return tuple(meshes)

    def _stored_names(self, role: PreparationObjectRole) -> tuple[str, ...]:
        cmds = self.cmds
        fit = self._fit()
        attribute = _ATTRIBUTES[role]
        if fit and cmds.attributeQuery(attribute, node=fit, exists=True):
            value = cmds.getAttr(fit + "." + attribute) or ""
            if value.strip():
                return tuple(value.split())
        if cmds.objExists(self.storage):
            if cmds.nodeType(self.storage) != "network":
                raise ValueError("准备记录名称已被其他节点占用：" + self.storage)
            if cmds.attributeQuery(attribute, node=self.storage, exists=True):
                value = cmds.getAttr(self.storage + "." + attribute) or ""
                if value:
                    decoded = json.loads(value)
                    if not isinstance(decoded, list) or any(
                            not isinstance(item, str) for item in decoded):
                        raise ValueError("准备记录格式无效：" + attribute)
                    return tuple(decoded)
        return ()

    def read_objects(self, role: PreparationObjectRole) -> tuple[str, ...]:
        return tuple(self._resolve_name(name) for name in self._stored_names(role))

    def write_objects(self, role: PreparationObjectRole,
                      objects: tuple[str, ...]) -> None:
        cmds = self.cmds
        attribute = _ATTRIBUTES[role]
        if cmds.objExists(self.storage) and cmds.nodeType(self.storage) != "network":
            raise ValueError("准备记录名称已被其他节点占用：" + self.storage)
        if (cmds.objExists(self.storage)
                and cmds.attributeQuery(attribute, node=self.storage, exists=True)
                and not cmds.getAttr(self.storage + "." + attribute, settable=True)):
            raise ValueError("准备记录字段不可写：" + attribute)
        names = tuple(node.rsplit("|", 1)[-1] for node in objects)
        for node, short in zip(objects, names):
            if self._resolve_name(short) != node:
                raise ValueError("模型短名不是场景内唯一名称：" + short)
        fit = self._fit()
        if fit and cmds.attributeQuery(attribute, node=fit, exists=True):
            if not cmds.getAttr(fit + "." + attribute, settable=True):
                raise ValueError("FitSkeleton 准备字段不可写：" + attribute)
        changed = False
        cmds.undoInfo(openChunk=True, chunkName="记录准备模型 " + role.value)
        try:
            if not cmds.objExists(self.storage):
                cmds.createNode("network", name=self.storage)
                changed = True
            if not cmds.attributeQuery(attribute, node=self.storage, exists=True):
                cmds.addAttr(self.storage, longName=attribute, dataType="string")
                changed = True
            cmds.setAttr(self.storage + "." + attribute,
                         json.dumps(names, ensure_ascii=False), type="string")
            changed = True
            if fit:
                if not cmds.attributeQuery(attribute, node=fit, exists=True):
                    cmds.addAttr(fit, longName=attribute, dataType="string")
                cmds.setAttr(fit + "." + attribute, " ".join(names), type="string")
            if self.read_objects(role) != objects:
                raise RuntimeError("准备模型记录写后读回不一致")
        except Exception:
            cmds.undoInfo(closeChunk=True)
            if changed:
                cmds.undo()
            raise
        else:
            cmds.undoInfo(closeChunk=True)

    def select_objects(self, objects: tuple[str, ...]) -> None:
        self.cmds.select(list(objects), replace=True)
