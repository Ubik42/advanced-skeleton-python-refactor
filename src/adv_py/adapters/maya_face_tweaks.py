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
        if type(iterations) is not int:
            raise ValueError("Face 权重平滑迭代数必须为整数")
        c = self._maya
        selected = c.ls(selection=True, long=True) or ()
        if not selected:
            return ""
        # asWeightHammerVerts uses the first selected object's related Skin;
        # it accepts Maya selection state directly (not vertices-only input).
        from .maya_original_skin_history import related_skin_cluster
        mesh = selected[0].split(".", 1)[0]
        skin = related_skin_cluster(mesh)
        if not skin:
            return ""
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
            tokens = leaf.split("_")
            name, side = tokens[0], tokens[1] if len(tokens) > 1 else ""
            if side:
                candidate = self._name(name + "Joint_" + side)
                if c.objExists(candidate):
                    joint = candidate
        c.select(mesh, replace=True)
        layer = self._name("FaceJointsLayer")
        if c.objExists(layer) and not c.getAttr(layer + ".visibility"):
            self._show_face_joints_layer(mesh)
        if c.objExists(layer):
            c.select(layer, replace=True)
        open_native_face_skin_paint(joint, cmds=c)
        return joint

    def _show_face_joints_layer(self, face_mesh: str) -> None:
        """Mirror asShowLayer FaceJoints when Skin Layers are present."""
        del face_mesh
        from .maya_face_skin_layers import MayaFaceSkinLayersHost

        MayaFaceSkinLayersHost(namespace=self.namespace).show_face_skin_layer(
            "FaceJoints")

    def set_face_joints_visible(self, visible: bool) -> int:
        """Apply asJointsVisibility, including old Fit drawStyle recovery."""
        if type(visible) is not bool:
            raise ValueError("Face 关节显示状态无效")
        c = self._maya
        main = self._name("Main")
        legacy_root = self._name("root")
        fit = self._name("FitSkeleton")
        main_plug = (main + ".jointVis"
                     if c.objExists(main) and c.attributeQuery(
                         "jointVis", node=main, exists=True) else None)
        has_root = c.objExists(legacy_root)
        fit_paths = c.ls(fit, long=True, type="transform") or ()
        if not main_plug and not has_root and not fit_paths:
            raise FitSkeletonValidationError(
                "Face 场景中没有可切换显示的角色关节")
        restored = 0
        with self.transaction("Face Tweaks 显示关节" if visible
                              else "Face Tweaks 隐藏关节"):
            if main_plug:
                self._transaction_changed = True
                c.setAttr(main_plug, visible)
            if has_root and not c.getAttr(legacy_root + ".visibility",
                                          lock=True):
                try:
                    c.setAttr(legacy_root + ".visibility", visible)
                except RuntimeError:
                    pass  # The MEL branch also ignores locked legacy roots.
                else:
                    self._transaction_changed = True
            if visible:
                for fit_path in fit_paths:
                    joints = c.listRelatives(
                        fit_path, allDescendents=True, type="joint",
                        fullPath=True) or ()
                    for joint in joints:
                        if int(c.getAttr(joint + ".drawStyle")) != 2:
                            continue
                        self._transaction_changed = True
                        c.setAttr(joint + ".drawStyle", 0)
                        restored += 1
        return restored
