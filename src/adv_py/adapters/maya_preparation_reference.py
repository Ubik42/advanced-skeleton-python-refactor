"""Maya scene operations for the Preparation / Rig reference entry."""
from __future__ import annotations

import os
from pathlib import Path
import re
import json

from adv_py.application.preparation_reference import (
    ModelReferenceInfo, ModelReferenceResult)


class MayaPreparationReferenceHost:
    def __init__(self):
        from maya import cmds
        self.cmds = cmds

    def new_scene(self) -> None:
        self.cmds.file(new=True, force=True)

    def scene_modified(self) -> bool:
        return bool(self.cmds.file(query=True, modified=True))

    def scene_name(self) -> str:
        return str(self.cmds.file(query=True, sceneName=True) or "")

    def save_scene(self, destination: Path | None = None) -> None:
        if destination is not None:
            self.cmds.file(rename=str(destination))
        name = self.scene_name()
        if not name:
            raise ValueError("当前场景尚未命名")
        scene_type = "mayaBinary" if name.lower().endswith(".mb") else "mayaAscii"
        self.cmds.file(save=True, type=scene_type, force=True)

    def reference_model(self, source: Path) -> ModelReferenceResult:
        cmds = self.cmds
        current = self.scene_name()
        if current and os.path.normcase(str(Path(current).resolve())) == os.path.normcase(str(source)):
            raise ValueError("不能将当前绑定场景引用到自身")
        if cmds.objExists("Hi") and cmds.nodeType("Hi") != "displayLayer":
            raise ValueError("场景中已有非显示层节点 Hi")
        namespace = "model"
        index = 1
        while cmds.namespace(exists=namespace):
            namespace = f"model{index}"
            index += 1
        before = set(cmds.ls(assemblies=True, long=True) or ())
        before_refs = set(cmds.ls(type="reference") or ())
        previous_selection = cmds.ls(selection=True, long=True) or []
        modified = cmds.file(query=True, modified=True)
        existing_layer = cmds.objExists("Hi")
        old_display_type = cmds.getAttr("Hi.displayType") if existing_layer else None
        try:
            cmds.file(str(source), reference=True, namespace=namespace,
                      mergeNamespacesOnClash=False, executeScriptNodes=False,
                      options="v=0;")
            roots = tuple(sorted(set(cmds.ls(assemblies=True, long=True) or ()) - before))
            if not roots:
                raise ValueError("模型文件没有可引用的顶层对象")
            reference_node = cmds.referenceQuery(roots[0], referenceNode=True)
            if not cmds.referenceQuery(reference_node, isLoaded=True):
                raise RuntimeError("模型引用未加载")
            if not cmds.objExists("Hi"):
                cmds.createDisplayLayer(name="Hi", number=1, empty=True)
            cmds.editDisplayLayerMembers("Hi", *roots, noRecurse=True)
            cmds.setAttr("Hi.displayType", 1)
            cmds.select(clear=True)
            return ModelReferenceResult(source, namespace, reference_node, roots)
        except Exception:
            for reference_node in (set(cmds.ls(type="reference") or ()) - before_refs):
                if reference_node != "sharedReferenceNode" and cmds.objExists(reference_node):
                    cmds.file(removeReference=True, referenceNode=reference_node)
            if not existing_layer and cmds.objExists("Hi"):
                cmds.delete("Hi")
            if existing_layer and cmds.objExists("Hi"):
                cmds.setAttr("Hi.displayType", old_display_type)
            if previous_selection:
                cmds.select(previous_selection, replace=True)
            else:
                cmds.select(clear=True)
            cmds.file(modified=modified)
            raise

    def inspect_model_reference(self, namespace: str) -> ModelReferenceInfo:
        cmds = self.cmds
        if not re.fullmatch(r"model(?:[1-9][0-9]*)?", namespace):
            raise ValueError("模型引用命名空间应为 model、model1 等")
        roots = tuple(sorted(node for node in
            (cmds.ls(assemblies=True, long=True) or ())
            if node.rsplit("|", 1)[-1].startswith(namespace + ":")))
        if not roots or not all(cmds.referenceQuery(node, isNodeReferenced=True)
                                 for node in roots):
            raise ValueError("命名空间没有已加载的顶层模型引用：" + namespace)
        refs = {cmds.referenceQuery(node, referenceNode=True) for node in roots}
        if len(refs) != 1:
            raise ValueError("命名空间中的顶层模型不属于同一引用")
        ref = refs.pop()
        source = Path(cmds.referenceQuery(ref, filename=True,
                                          withoutCopyNumber=True)).resolve()
        return ModelReferenceInfo(source, namespace, ref, roots)

    def _assert_unbound(self, info: ModelReferenceInfo) -> None:
        cmds = self.cmds
        for skin in cmds.ls(type="skinCluster") or ():
            for shape in cmds.skinCluster(skin, query=True, geometry=True) or ():
                shapes = cmds.ls(shape, long=True, type="mesh") or ()
                for path in shapes:
                    parents = cmds.listRelatives(path, parent=True,
                                                 fullPath=True) or ()
                    if any(parent.rsplit("|", 1)[-1].startswith(
                            info.namespace + ":") for parent in parents):
                        raise ValueError("模型已有 Skin，不能直接移除或替换引用；"
                                         "请先保存权重并处理绑定：" + skin)

    def _prune_preparation_records(self, namespace: str,
                                   *, drop_namespace: bool = False) -> None:
        from adv_py.adapters.maya_preparation_objects import (
            MayaPreparationObjectsHost, _ATTRIBUTES)

        cmds = self.cmds
        host = MayaPreparationObjectsHost()
        fit = host._fit()
        for attribute in _ATTRIBUTES.values():
            names = ()
            if cmds.objExists(host.storage) and cmds.attributeQuery(
                    attribute, node=host.storage, exists=True):
                names = tuple(json.loads(cmds.getAttr(
                    host.storage + "." + attribute) or "[]"))
            elif fit and cmds.attributeQuery(attribute, node=fit, exists=True):
                names = tuple((cmds.getAttr(fit + "." + attribute) or "").split())
            keep = tuple(name for name in names
                         if not (drop_namespace and name.startswith(namespace + ":"))
                         and cmds.objExists(name))
            if cmds.objExists(host.storage) and cmds.attributeQuery(
                    attribute, node=host.storage, exists=True):
                cmds.setAttr(host.storage + "." + attribute,
                             json.dumps(keep, ensure_ascii=False), type="string")
            if fit and cmds.attributeQuery(attribute, node=fit, exists=True):
                cmds.setAttr(fit + "." + attribute,
                             " ".join(keep), type="string")

    def reload_model_reference(self, info: ModelReferenceInfo) -> ModelReferenceInfo:
        self.cmds.file(str(info.source), loadReference=info.reference_node,
                       executeScriptNodes=False)
        result = self.inspect_model_reference(info.namespace)
        self._prune_preparation_records(info.namespace)
        return result

    def replace_model_reference(self, info: ModelReferenceInfo,
                                source: Path) -> ModelReferenceInfo:
        self._assert_unbound(info)
        current = self.scene_name()
        if current and os.path.normcase(str(Path(current).resolve())) == os.path.normcase(str(source)):
            raise ValueError("不能将当前绑定场景引用到自身")
        try:
            self.cmds.file(str(source), loadReference=info.reference_node,
                           executeScriptNodes=False)
            result = self.inspect_model_reference(info.namespace)
        except Exception:
            self.cmds.file(str(info.source), loadReference=info.reference_node,
                           executeScriptNodes=False)
            raise
        self._prune_preparation_records(info.namespace)
        return result

    def remove_model_reference(self, info: ModelReferenceInfo) -> None:
        self._assert_unbound(info)
        self.cmds.file(removeReference=True, referenceNode=info.reference_node)
        self._prune_preparation_records(info.namespace, drop_namespace=True)
