"""Face DeltaMush operations corresponding to the 6.925 Face panel."""
from __future__ import annotations

from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face_pre import MayaFacePreHost


class MayaFaceDeltaMushHost(MayaFacePreHost):
    @property
    def _maya(self):
        return getattr(self._cmds, "raw", self._cmds)

    def _name(self, leaf: str) -> str:
        return ":" + ((self.namespace + ":") if self.namespace else "") + leaf

    def _require_supported_mode(self) -> None:
        fit = self._name("FaceFitSkeleton")
        c = self._maya
        if (c.objExists(fit)
                and c.attributeQuery("GameEngine", node=fit, exists=True)
                and c.getAttr(fit + ".GameEngine")):
            raise FitSkeletonValidationError(
                "Face Game Engine 模式下原版禁用 DeltaMush")

    def _face_mesh(self) -> str:
        meshes = self.read_face_objects(FacePreRole.FACE)
        if len(meshes) != 1:
            raise FitSkeletonValidationError(
                "Face / Pre 须记录唯一 Face 网格")
        mesh = self.scene_address(meshes[0])
        shapes = self._maya.listRelatives(
            mesh, shapes=True, noIntermediate=True,
            fullPath=True, type="mesh") or ()
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Face 网格 Shape 缺失或不唯一")
        return mesh

    def _deformer(self, *, required: bool) -> str | None:
        c = self._maya
        name = self._name("asFaceDeltaMush")
        matches = c.ls(name, long=True,
                       type="deltaMush") or ()
        if len(matches) > 1 or (required and len(matches) != 1):
            raise FitSkeletonValidationError(
                "asFaceDeltaMush 缺失或不唯一")
        if matches:
            return matches[0]
        if c.objExists(name):
            raise FitSkeletonValidationError(
                "asFaceDeltaMush 名称已由其他节点占用")
        return None

    def _face_history_deformer(self, mesh: str,
                               preferred: str | None = None) -> str:
        c = self._maya
        shape = (c.listRelatives(mesh, shapes=True,
                 noIntermediate=True, fullPath=True, type="mesh") or ())[0]
        history = c.listHistory(shape, pruneDagObjects=True) or ()
        deformers = (c.ls(history, long=True, type="deltaMush") or ()) \
            if history else ()
        if preferred is not None:
            if preferred not in deformers:
                raise FitSkeletonValidationError(
                    "asFaceDeltaMush 未连接到 Face 网格")
            return preferred
        if len(deformers) != 1:
            raise FitSkeletonValidationError(
                "Face 网格需要唯一 DeltaMush 才能编辑权重")
        return deformers[0]

    def _scale_source(self) -> str | None:
        c = self._maya
        name = self._name("MainScaleMultiplyDivide")
        if not c.objExists(name):
            return None
        matches = c.ls(name, long=True,
                       type="multiplyDivide") or ()
        if len(matches) != 1:
            raise FitSkeletonValidationError("Face DeltaMush 主缩放来源不唯一")
        return matches[0]

    def create_face_delta_mush(self) -> str:
        c = self._maya
        self._require_supported_mode()
        mesh = self._face_mesh()
        if self._deformer(required=False) is not None:
            raise FitSkeletonValidationError("asFaceDeltaMush 已存在")
        source = self._scale_source()
        if c.objExists(self._name("asFaceDeltaMushSet")):
            raise FitSkeletonValidationError("asFaceDeltaMushSet 名称已被占用")
        with self.transaction("创建 Face DeltaMush"):
            self._transaction_changed = True
            from .maya_face_deformer_sets import original_face_deformer_sets
            with original_face_deformer_sets(c):
                created = c.deltaMush(
                    mesh, smoothingIterations=10, smoothingStep=.5,
                    pinBorderVertices=True, envelope=1.)
            if len(created) != 1:
                raise RuntimeError("Face DeltaMush 创建结果不唯一")
            deformer = c.rename(created[0], self._name("asFaceDeltaMush"))
            sets = c.listConnections(deformer + ".message",
                                     type="objectSet") or ()
            if len(sets) != 1:
                raise RuntimeError("Face DeltaMush 缺少传统变形器集合")
            c.rename(sets[0], self._name("asFaceDeltaMushSet"))
            if source is not None:
                for axis in "XYZ":
                    c.connectAttr(source + ".output" + axis,
                                  deformer + ".s" + axis.lower())
            eye_lid = self._name("eyeLidArea")
            lip = self._name("lipArea")
            if c.objExists(eye_lid) and c.objExists(lip):
                c.select((eye_lid, lip), replace=True)
                c.percent(deformer, value=0)
            if (self._deformer(required=True) is None
                    or self._face_history_deformer(
                        mesh, self._deformer(required=True)) !=
                    self._deformer(required=True)):
                raise RuntimeError("Face DeltaMush 未正确连接到 Face 网格")
            if (int(c.getAttr(deformer + ".smoothingIterations")) != 10
                    or abs(float(c.getAttr(deformer + ".smoothingStep"))
                           - .5) > 1e-6
                    or not c.getAttr(deformer + ".pinBorderVertices")
                    or abs(float(c.getAttr(deformer + ".envelope"))
                           - 1.) > 1e-6):
                raise RuntimeError("Face DeltaMush 原版参数未正确写入")
            if source is not None and any(not c.isConnected(
                    source + ".output" + axis,
                    deformer + ".s" + axis.lower())
                    for axis in "XYZ"):
                raise RuntimeError("Face DeltaMush 主缩放未正确连接")
            c.select(mesh, replace=True)
        return self._deformer(required=True)

    def delete_face_delta_mush(self) -> bool:
        c = self._maya
        self._require_supported_mode()
        deformer = self._deformer(required=False)
        if deformer is None:
            return False
        if c.referenceQuery(deformer, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能删除引用中的 Face DeltaMush")
        with self.transaction("删除 Face DeltaMush"):
            self._transaction_changed = True
            c.delete(deformer)
            if self._deformer(required=False) is not None:
                raise RuntimeError("Face DeltaMush 删除后仍存在")
        return True

    def zero_selected_face_delta_mush_weights(self) -> tuple[str, ...]:
        c = self._maya
        self._require_supported_mode()
        mesh = self._face_mesh()
        deformer = self._deformer(required=False)
        if deformer is not None:
            deformers = (self._face_history_deformer(mesh, deformer),)
        else:
            shape = c.listRelatives(mesh, shapes=True,
                                    noIntermediate=True, fullPath=True,
                                    type="mesh")[0]
            history = c.listHistory(shape, pruneDagObjects=True) or ()
            deformers = tuple(c.ls(history, long=True,
                                   type="deltaMush") or ()) if history else ()
            if not deformers:
                raise FitSkeletonValidationError(
                    "Face 网格没有可归零权重的 DeltaMush")
        selected = tuple(c.ls(selection=True, long=True,
                              flatten=True) or ())
        if not selected:
            raise FitSkeletonValidationError("请先选择 Face 顶点或区域集合")
        with self.transaction("Face DeltaMush 所选区域权重归零"):
            self._transaction_changed = True
            for item in deformers:
                c.percent(item, value=0)
        return deformers

    def select_face_delta_mush_area(self, area: str) -> int:
        if area not in ("eyeLidArea", "lipArea"):
            raise ValueError("Face DeltaMush 区域名称无效")
        self._require_supported_mode()
        c = self._maya
        scoped = self._name(area)
        if not c.objExists(scoped):
            raise FitSkeletonValidationError("Face 区域尚未建立：" + area)
        c.select(scoped, replace=True)
        return len(c.ls(selection=True, flatten=True) or ())

    def paint_face_delta_mush_weights(self) -> str:
        from .maya_deform_skinning import open_native_delta_mush_paint

        self._require_supported_mode()
        deformer = self._deformer(required=True)
        self._face_history_deformer(self._face_mesh(), deformer)
        open_native_delta_mush_paint()
        return deformer
