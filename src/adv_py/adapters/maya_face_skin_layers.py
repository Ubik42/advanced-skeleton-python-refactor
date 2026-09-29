"""The 6.925 Face / Skin Layers visibility switch."""
from __future__ import annotations

from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face_pre import MayaFacePreHost


class MayaFaceSkinLayersHost(MayaFacePreHost):
    @property
    def _maya(self):
        return getattr(self._cmds, "raw", self._cmds)

    def _name(self, leaf: str) -> str:
        return ":" + ((self.namespace + ":") if self.namespace else "") + leaf

    def _group_and_children(self) -> tuple[str, tuple[str, ...]]:
        c = self._maya
        group = self._name("DeformationLayers")
        if not c.objExists(group):
            raise FitSkeletonValidationError(
                "Face 场景尚未建立 DeformationLayers")
        children = tuple(c.listRelatives(group, children=True,
                                         type="transform", fullPath=True) or ())
        return group, children

    def _mode_allows_layers(self) -> bool:
        c = self._maya
        fit = self._name("FaceFitSkeleton")
        if not c.objExists(fit):
            return False
        if (c.attributeQuery("RigType", node=fit, exists=True)
                and int(c.getAttr(fit + ".RigType")) != 2):
            return False
        if (c.attributeQuery("GameEngine", node=fit, exists=True)
                and bool(c.getAttr(fit + ".GameEngine"))):
            return False
        return True

    @staticmethod
    def _leaf(path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _layers_from_children(self, children: tuple[str, ...]
                              ) -> tuple[str, ...]:
        layers = []
        for path in children:
            name = self._leaf(path).replace("Layer", "", 1)
            if name in ("template", "Template", "allHeadCombined"):
                continue
            if name and name not in layers:
                layers.append(name)
        return tuple(layers)

    def available_face_skin_layers(self) -> tuple[str, ...]:
        """Reproduce the dynamic buttons populated by asUpdateButtonEnables."""
        c = self._maya
        if (not self._mode_allows_layers()
                or not c.objExists(self._name("DeformationLayers"))):
            return ()
        _, children = self._group_and_children()
        return self._layers_from_children(children)

    def show_face_skin_layer(self, layer: str) -> tuple[str, ...]:
        """Switch mesh and layer visibility exactly as asShowLayer does."""
        if not isinstance(layer, str) or not layer:
            raise ValueError("Face SkinLayer 名称无效")
        if not self._mode_allows_layers():
            raise FitSkeletonValidationError(
                "当前 Face RigType 或 GameEngine 模式不提供 Skin Layers")
        c = self._maya
        group, children = self._group_and_children()
        available = self._layers_from_children(children)
        if layer != "Normal" and layer not in available:
            raise FitSkeletonValidationError("Face SkinLayer 不存在：" + layer)
        normal = layer == "Normal"
        meshes = []
        for role in (FacePreRole.ALL_HEAD, FacePreRole.FACE):
            for path in self.read_face_objects(role):
                resolved = self.scene_address(path)
                if resolved not in meshes:
                    meshes.append(resolved)
        if not meshes:
            raise FitSkeletonValidationError("Face / Pre 尚未记录面部网格")
        targets = tuple(path for path in children
                        if self._leaf(path).startswith(layer + "Layer"))
        for mesh in meshes:
            if (not c.objExists(mesh)
                    or not c.getAttr(mesh + ".visibility", settable=True)):
                raise FitSkeletonValidationError(
                    "Face SkinLayer 网格可见性不可写：" + mesh)
        with self.transaction("Face SkinLayer 切换为 " + layer):
            self._transaction_changed = True
            for mesh in meshes:
                c.setAttr(mesh + ".visibility", normal)
            for path in children:
                plug = path + ".visibility"
                if c.getAttr(plug, lock=True):
                    c.setAttr(plug, lock=False)
                c.setAttr(plug, False)
            c.select(clear=True)
            group_plug = group + ".visibility"
            if c.getAttr(group_plug, lock=True):
                c.setAttr(group_plug, lock=False)
            c.setAttr(group_plug, not normal)
            c.setAttr(group_plug, lock=normal)
            if not normal:
                for path in targets:
                    c.setAttr(path + ".visibility", True)
                    c.select(path, add=True)
            if any(bool(c.getAttr(path + ".visibility")) !=
                   (path in targets and not normal) for path in children):
                raise RuntimeError("Face SkinLayer 可见性写后回读不一致")
            if bool(c.getAttr(group_plug)) == normal:
                raise RuntimeError("Face DeformationLayers 可见性写后回读不一致")
        return targets
