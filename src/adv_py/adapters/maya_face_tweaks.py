"""Original Face/Tweaks area selection and skin smoothing operations."""
from __future__ import annotations

from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face_pre import MayaFacePreHost


_AREA_NAMES = frozenset((
    "eyeBrowArea", "eyeBrowLineArea", "eyeLidArea",
    "eyeLidMainArea", "eyeLidOuterArea", "lipArea",
    "lipMainArea", "lipFalloffArea",
))


class MayaFaceTweaksHost(MayaFacePreHost):
    @property
    def _maya(self):
        return getattr(self._cmds, "raw", self._cmds)

    def _name(self, leaf: str) -> str:
        return ":" + ((self.namespace + ":") if self.namespace else "") + leaf

    def select_face_area(self, area: str, *, subtract: bool = False) -> int:
        if area not in _AREA_NAMES:
            raise ValueError("Face Tweaks 区域名称无效")
        c = self._maya
        path = self._name(area)
        if not c.objExists(path):
            raise FitSkeletonValidationError("Face Tweaks 区域不存在：" + area)
        if subtract:
            if not c.ls(selection=True):
                raise FitSkeletonValidationError("请先选择待扣除的 Face 区域")
            c.select(path, deselect=True)
        else:
            c.select(path, replace=True)
        return len(c.ls(selection=True, flatten=True) or ())

    def smooth_selected_skin_weights(self, iterations: int = 5) -> str:
        """Use the same skinCluster smoothWeights branch as asWeightHammerVerts."""
        if type(iterations) is not int or not 1 <= iterations <= 100:
            raise ValueError("Face 权重平滑迭代数必须在 1 到 100 之间")
        c = self._maya
        selected = c.ls(selection=True, long=True, flatten=True) or ()
        if not selected:
            raise FitSkeletonValidationError("请先选择 Face 网格顶点")
        meshes = {item.split(".", 1)[0] for item in selected}
        if len(meshes) != 1 or any(".vtx[" not in item for item in selected):
            raise FitSkeletonValidationError("Face 权重平滑只接受同一网格的顶点")
        mesh = next(iter(meshes))
        shapes = c.listRelatives(mesh, shapes=True,
                                 noIntermediate=True, fullPath=True,
                                 type="mesh") or ()
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Face 权重网格 Shape 缺失或不唯一")
        history = c.listHistory(shapes[0], pruneDagObjects=True) or ()
        skins = (c.ls(history, type="skinCluster") or ()) \
            if history else ()
        if len(skins) != 1:
            raise FitSkeletonValidationError("Face 网格需要唯一 SkinCluster")
        skin = skins[0]
        if c.referenceQuery(skin, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能平滑引用 SkinCluster 的权重")
        fit = self._name("FaceFitSkeleton")
        obey_max = False
        if (c.objExists(fit)
                and c.attributeQuery("GameEngine", node=fit, exists=True)
                and c.getAttr(fit + ".GameEngine")
                and c.attributeQuery("UseMaxInf", node=fit, exists=True)
                and c.getAttr(fit + ".UseMaxInf")
                and c.attributeQuery("MaxInf", node=fit, exists=True)):
            label = c.getAttr(fit + ".MaxInf", asString=True)
            try:
                obey_max = int(label) > 0
            except (TypeError, ValueError):
                raise FitSkeletonValidationError(
                    "FaceFitSkeleton.MaxInf 不是有效关节数") from None
        with self.transaction("Face Tweaks 平滑所选 Skin 权重"):
            self._transaction_changed = True
            c.skinCluster(skin, edit=True, smoothWeights=0,
                smoothWeightsMaxIterations=iterations,
                obeyMaxInfluences=obey_max)
        return skin

    def paint_face_skin_weights(self) -> str:
        """Open the native paint context on the Face mesh and matching joint."""
        from .maya_deform_skinning import open_native_face_skin_paint

        c = self._maya
        meshes = self.read_face_objects(FacePreRole.FACE)
        if len(meshes) != 1:
            raise FitSkeletonValidationError("Face / Pre 须记录唯一 Face 网格")
        mesh = self.scene_address(meshes[0])
        shape = c.listRelatives(mesh, shapes=True,
                                noIntermediate=True, fullPath=True,
                                type="mesh") or ()
        if len(shape) != 1:
            raise FitSkeletonValidationError("Face 网格 Shape 缺失或不唯一")
        history = c.listHistory(shape[0], pruneDagObjects=True) or ()
        skin = (c.ls(history, type="skinCluster") or ()) \
            if history else ()
        if len(skin) != 1:
            raise FitSkeletonValidationError("Face 网格需要唯一 SkinCluster")
        fit = self._name("FaceFitSkeleton")
        if (not c.objExists(fit)
                or not c.attributeQuery("HeadJoint", node=fit, exists=True)):
            raise FitSkeletonValidationError("Face Fit 缺少 HeadJoint 来源")
        head = c.getAttr(fit + ".HeadJoint")
        if not isinstance(head, str) or not head:
            raise FitSkeletonValidationError("Face Fit HeadJoint 名称无效")
        joint = head if ":" in head else self._name(head)
        selection = c.ls(selection=True, long=True) or ()
        if selection:
            leaf = selection[0].rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            name, separator, side = leaf.partition("_")
            if separator and side in ("R", "L", "M"):
                candidate = self._name(name + "Joint_" + side)
                if c.objExists(candidate):
                    joint = candidate
        influences = c.ls(c.skinCluster(skin[0], query=True,
                                        influence=True) or (),
                          long=True, type="joint") or ()
        resolved = c.ls(joint, long=True, type="joint") or ()
        if len(resolved) != 1 or resolved[0] not in influences:
            raise FitSkeletonValidationError(
                "Face 目标 Skin 不包含待绘制关节：" + joint)
        c.select(mesh, replace=True)
        layer = self._name("FaceJointsLayer")
        if c.objExists(layer) and not c.getAttr(layer + ".visibility"):
            c.setAttr(layer + ".visibility", True)
            c.select(layer, replace=True)
        open_native_face_skin_paint(resolved[0], cmds=c)
        return resolved[0]
