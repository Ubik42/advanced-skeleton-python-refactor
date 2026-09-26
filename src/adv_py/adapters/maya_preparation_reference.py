"""Maya scene operations for the Preparation / Rig reference entry."""
from __future__ import annotations

import os
from pathlib import Path

from adv_py.application.preparation_reference import ModelReferenceResult


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
