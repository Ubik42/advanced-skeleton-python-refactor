"""Maya scene storage for the original Face / Pre mask and geometry rows."""
from __future__ import annotations

import json
import re

from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face import MayaFaceHost


_FACE_PATTERN = re.compile(r"^(?P<mesh>.+)\.f\[(?P<index>\d+)\]$")


class MayaFacePreHost(MayaFaceHost):
    def _fit(self, *, required=False):
        matches = self._cmds.ls("FaceFitSkeleton", long=True,
                                type="transform") or []
        if len(matches) > 1 or (required and len(matches) != 1):
            raise FitSkeletonValidationError("FaceFitSkeleton 缺失或不唯一；先记录 Mask")
        return matches[0] if matches else None

    def selected_mask(self):
        c = self._cmds
        selected = c.ls(selection=True, flatten=True, long=True) or []
        parsed = [_FACE_PATTERN.fullmatch(item) for item in selected]
        if not parsed or any(item is None for item in parsed):
            raise FitSkeletonValidationError("Mask 只接受所选面部多边形面")
        meshes = {item.group("mesh") for item in parsed}
        if len(meshes) != 1:
            raise FitSkeletonValidationError("Mask 的所有面必须来自同一件网格")
        mesh = next(iter(meshes))
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Mask 网格需要唯一可见多边形 Shape")
        indices = tuple(sorted({int(item.group("index")) for item in parsed}))
        count = int(c.polyEvaluate(mesh, face=True))
        if not indices or indices[-1] >= count:
            raise FitSkeletonValidationError("Mask 面索引已超出网格拓扑")
        bounds = tuple(float(value) for value in c.exactWorldBoundingBox(*selected))
        if len(bounds) != 6 or any(bounds[index + 3] - bounds[index] <= 1e-6
                                   for index in range(3)):
            raise FitSkeletonValidationError("Mask 包围盒无效")
        return mesh, indices, bounds

    def _read_mask_payload(self):
        fit = self._fit(required=True)
        if not self._cmds.attributeQuery("advPyMaskFaces", node=fit, exists=True):
            raise FitSkeletonValidationError("FaceFitSkeleton 尚未记录 Mask")
        value = json.loads(self._cmds.getAttr(fit + ".advPyMaskFaces"))
        if (not isinstance(value, dict) or not isinstance(value.get("mesh"), str)
                or not isinstance(value.get("faces"), list)):
            raise FitSkeletonValidationError("Mask 记录无效")
        return fit, value

    def read_face_mask(self):
        fit, data = self._read_mask_payload()
        mesh = data["mesh"]
        matches = self._cmds.ls(mesh, long=True, type="transform") or []
        if matches != [mesh]:
            raise FitSkeletonValidationError("Mask 网格已缺失或路径改变")
        count = int(self._cmds.polyEvaluate(mesh, face=True))
        indices = tuple(data["faces"])
        if (count != data.get("faceCount") or not indices
                or any(type(index) is not int or index < 0 or index >= count
                       for index in indices)):
            raise FitSkeletonValidationError("Mask 网格拓扑已改变")
        scale = float(self._cmds.getAttr(fit + ".faceScale"))
        return mesh, indices, scale

    def store_face_mask(self, mesh, faces, bounds):
        c = self._cmds
        if str(c.upAxis(query=True, axis=True)).lower() != "y":
            raise FitSkeletonValidationError("原版 Face Mask 要求 Y-up 场景")
        if str(c.currentUnit(query=True, linear=True)).lower() != "cm":
            raise FitSkeletonValidationError("Face Mask 要求厘米场景单位")
        fit = self._fit()
        if fit and c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能改写引用中的 FaceFitSkeleton")
        if fit and not c.attributeQuery("advPyMaskFaces", node=fit, exists=True):
            raise FitSkeletonValidationError("已有原版 FaceFitSkeleton，拒绝覆盖其引导曲线")
        if c.ls("FitEyeBall", long=True, type="transform"):
            raise FitSkeletonValidationError("眼球 Fit 已建立，不能重置 Mask")
        for name in ("FaceGroup", "FaceFitSkeleton"):
            matches = c.ls(name, long=True) or []
            if len(matches) > 1 or any(c.nodeType(path) != "transform"
                                      for path in matches):
                raise FitSkeletonValidationError("Face 引导节点名称已冲突：" + name)
        width = bounds[3] - bounds[0]
        height = bounds[4] - bounds[1]
        depth = bounds[5] - bounds[2]
        depth_center = (bounds[2] + bounds[5]) / 2
        if width <= 1e-6 or height <= 1e-6:
            raise FitSkeletonValidationError("Mask 宽度或高度无效")
        payload = json.dumps({"mesh": mesh, "faces": list(faces),
                              "faceCount": int(c.polyEvaluate(mesh, face=True))},
                             separators=(",", ":"))
        selection = c.ls(selection=True, long=True) or []
        with self.transaction("记录 Face Mask 并建立 Fit 范围"):
            self._transaction_changed = True
            group = c.ls("FaceGroup", long=True, type="transform") or []
            if not group:
                parent = (c.ls("|Group", long=True, type="transform") or [None])[0]
                created = c.createNode("transform", name="FaceGroup",
                                       **({"parent": parent} if parent else {}))
                group = c.ls(created, long=True, type="transform")
            if not fit:
                fit = c.createNode("transform", name="FaceFitSkeleton",
                                   parent=group[0])
                fit = c.ls(fit, long=True, type="transform")[0]
            for shape in c.listRelatives(fit, shapes=True, fullPath=True) or []:
                c.delete(shape)
            for name, upper in (
                    ("FaceFitSkeletonShape", False),
                    ("FaceFitSkeletonHeightShape", True),
                    ("FaceFitSkeletonCircleShape", False),
                    ("FaceFitSkeletonHeightCircleShape", True)):
                temporary = c.circle(center=(0, 0, 0), normal=(0, 1, 0),
                                     radius=.5, degree=3, sections=8,
                                     constructionHistory=False)[0]
                shape = (c.listRelatives(temporary, shapes=True,
                                         fullPath=True) or [None])[0]
                shape = c.parent(shape, fit, add=True, shape=True,
                                 relative=True)[0]
                c.delete(temporary)
                shape = c.rename(shape, name)
                cvs = shape + ".cv[0:99]"
                c.rotate(0, -90, 0, cvs, relative=True,
                         objectSpace=True, pivot=(0, 0, 0))
                if upper:
                    c.move(0, 1, 0, cvs, relative=True, objectSpace=True)
                c.scale(width, height, depth, cvs, relative=True,
                        pivot=(0, 0, 0))
                c.move(0, bounds[1], depth_center, cvs,
                       relative=True, objectSpace=True)
                c.setAttr(shape + ".overrideEnabled", True)
                c.setAttr(shape + ".overrideColor", 13)
            if not c.attributeQuery("faceScale", node=fit, exists=True):
                c.addAttr(fit, longName="faceScale", attributeType="double")
            c.setAttr(fit + ".faceScale", height)
            if not c.attributeQuery("advPyMaskFaces", node=fit, exists=True):
                c.addAttr(fit, longName="advPyMaskFaces", dataType="string")
            c.setAttr(fit + ".advPyMaskFaces", payload, type="string")
            if c.attributeQuery("Face", node=fit, exists=True):
                existing = c.getAttr(fit + ".Face") or ""
                if existing and (c.ls(existing, long=True,
                                       type="transform") or []) != [mesh]:
                    c.setAttr(fit + ".Face", "", type="string")
                    if c.attributeQuery("AllHead", node=fit, exists=True):
                        c.setAttr(fit + ".AllHead", "", type="string")
            c.select(selection, replace=True) if selection else c.select(clear=True)

    def selected_face_meshes(self):
        c = self._cmds
        if any("." in node for node in (c.ls(selection=True, long=True) or [])):
            raise FitSkeletonValidationError("Face / All Head 只能选择对象，不能选择组件")
        selected = c.ls(selection=True, long=True, objectsOnly=True) or []
        meshes = []
        for node in selected:
            if c.nodeType(node) == "mesh":
                node = (c.listRelatives(node, parent=True,
                                        fullPath=True) or [None])[0]
            if not node or c.nodeType(node) != "transform":
                raise FitSkeletonValidationError("Face / All Head 只接受网格对象")
            shapes = c.listRelatives(node, shapes=True, noIntermediate=True,
                                     fullPath=True, type="mesh") or []
            if len(shapes) != 1:
                raise FitSkeletonValidationError("Face / All Head 网格 Shape 不唯一")
            if node not in meshes:
                meshes.append(node)
        return tuple(meshes)

    def read_face_objects(self, role: FacePreRole):
        fit, _ = self._read_mask_payload()
        if not self._cmds.attributeQuery(role.value, node=fit, exists=True):
            return ()
        names = tuple((self._cmds.getAttr(fit + "." + role.value) or "").split())
        resolved = []
        for name in names:
            matches = self._cmds.ls(name, long=True, type="transform") or []
            if len(matches) != 1:
                raise FitSkeletonValidationError("Face Pre 网格已缺失或不唯一：" + name)
            resolved.append(matches[0])
        return tuple(resolved)

    def select_face_mask(self):
        mesh, faces, _ = self.read_face_mask()
        self._cmds.select([f"{mesh}.f[{index}]" for index in faces],
                          replace=True)
        return len(faces)

    def select_face_objects(self, role: FacePreRole):
        meshes = self.read_face_objects(role)
        if not meshes:
            raise FitSkeletonValidationError("Face Pre 尚未记录 " + role.value)
        self._cmds.select(meshes, replace=True)
        return meshes

    def store_face_objects(self, role: FacePreRole, meshes, head_joint):
        c = self._cmds
        fit, mask = self._read_mask_payload()
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能改写引用中的 FaceFitSkeleton")
        if role is FacePreRole.FACE and meshes[0] != mask["mesh"]:
            raise FitSkeletonValidationError("Face 网格必须是 Mask 所选面所属网格")
        heads = c.ls(head_joint, long=True, type="joint") or []
        if len(heads) != 1:
            raise FitSkeletonValidationError("Face Pre 需要唯一的 Head 关节")
        names = tuple(mesh.rsplit("|", 1)[-1] for mesh in meshes)
        if any((c.ls(name, long=True, type="transform") or []) != [mesh]
               for name, mesh in zip(names, meshes)):
            raise FitSkeletonValidationError("Face 网格短名在场景内不唯一")
        for mesh in meshes:
            shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                     fullPath=True, type="mesh") or []
            history = c.listHistory(shapes[0], pruneDagObjects=True) or []
            skins = [node for node in history if c.nodeType(node) == "skinCluster"]
            if len(skins) > 1:
                raise FitSkeletonValidationError("Face 网格有多个 Skin：" + mesh)
            if skins and role is FacePreRole.FACE:
                influences = c.skinCluster(skins[0], query=True, influence=True) or []
                if heads[0] not in tuple((c.ls(item, long=True) or [None])[0]
                                         for item in influences):
                    raise FitSkeletonValidationError("Face Skin 未包含 Head 关节：" + mesh)
        with self.transaction("记录 Face Pre " + role.value):
            self._transaction_changed = True
            for mesh in meshes:
                shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                         fullPath=True, type="mesh") or []
                history = c.listHistory(shapes[0], pruneDagObjects=True) or []
                if not any(c.nodeType(node) == "skinCluster" for node in history):
                    c.skinCluster(heads[0], mesh, toSelectedBones=True,
                                  maximumInfluences=1,
                                  name="AdvPy_FacePreSkin")
            if not c.attributeQuery(role.value, node=fit, exists=True):
                c.addAttr(fit, longName=role.value, dataType="string")
            c.setAttr(fit + "." + role.value, " ".join(names), type="string")
            if role is FacePreRole.FACE:
                if not c.attributeQuery("HeadJoint", node=fit, exists=True):
                    c.addAttr(fit, longName="HeadJoint", dataType="string")
                c.setAttr(fit + ".HeadJoint",
                          heads[0].rsplit("|", 1)[-1], type="string")

    def create_eye_ball_fit(self, right_eye: str, head_joint: str) -> str:
        c = self._cmds
        fit = self._fit(required=True)
        matches = c.ls(right_eye, long=True, type="transform") or []
        if matches != [right_eye]:
            raise FitSkeletonValidationError("右眼网格路径不存在或不唯一")
        shape = c.listRelatives(right_eye, shapes=True, noIntermediate=True,
                                fullPath=True, type="mesh") or []
        if len(shape) != 1:
            raise FitSkeletonValidationError("右眼需要唯一可见多边形 Shape")
        heads = c.ls(head_joint, long=True, type="joint") or []
        if len(heads) != 1:
            raise FitSkeletonValidationError("EyeBall Fit 需要唯一的 Head 关节")
        if c.ls("Eye_R", long=True, type="joint") or c.ls("Eye_M", long=True,
                                                           type="joint"):
            raise FitSkeletonValidationError(
                "已存在 Body 眼关节；当前 EyeBall Fit 不支持替换其 Skin 影响")
        for name in ("FaceFitEyeBall", "FitEyeBall", "FitEyeSphere"):
            if c.ls(name, long=True):
                raise FitSkeletonValidationError("眼球 Fit 节点名称已占用：" + name)
        bounds = tuple(float(value) for value in c.exactWorldBoundingBox(right_eye))
        diameter = bounds[4] - bounds[1]
        if diameter <= 1e-6:
            raise FitSkeletonValidationError("右眼网格高度无效")
        center = tuple((bounds[axis] + bounds[axis + 3]) / 2
                       for axis in range(3))
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能在引用中的 FaceFitSkeleton 创建眼球 Fit")
        with self.transaction("建立 Face EyeBall Fit"):
            self._transaction_changed = True
            holder = c.createNode("transform", name="FaceFitEyeBall", parent=fit)
            locator = c.spaceLocator(name="FitEyeBall")[0]
            locator = c.parent(locator, holder, absolute=True)[0]
            c.setAttr(locator + ".rotateOrder", 2)
            c.setAttr(locator + "Shape.localScale", 1.5, 1.5, 1.5,
                      type="double3")
            c.xform(locator, worldSpace=True, translation=center)
            c.setAttr(locator + ".scale", diameter, diameter, diameter,
                      type="double3")
            sphere = c.polySphere(name="FitEyeSphere", radius=.5,
                                  subdivisionsX=8, subdivisionsY=8,
                                  constructionHistory=False)[0]
            sphere = c.parent(sphere, locator, relative=True)[0]
            c.setAttr(sphere + ".rotateX", 90)
            shape = (c.listRelatives(sphere, shapes=True,
                                     fullPath=True) or [None])[0]
            c.setAttr(shape + ".overrideEnabled", True)
            c.setAttr(shape + ".overrideDisplayType", 2)
            if not c.attributeQuery("RightEye", node=fit, exists=True):
                c.addAttr(fit, longName="RightEye", dataType="string")
            c.setAttr(fit + ".RightEye", right_eye.rsplit("|", 1)[-1],
                      type="string")
            c.setAttr(locator + ".rotateZ", lock=True)
            for kind in ("translate", "rotate", "scale"):
                for axis in "XYZ":
                    c.setAttr(fit + "." + kind + axis, lock=True)
        return (c.ls(locator, long=True, type="transform") or [locator])[0]

    def read_eye_ball_fit(self) -> str:
        c = self._cmds
        fit = self._fit(required=True)
        matches = c.ls("FitEyeBall", long=True, type="transform") or []
        if len(matches) != 1 or not matches[0].startswith(fit + "|"):
            raise FitSkeletonValidationError("EyeBall Fit 缺失或父级无效")
        locator = matches[0]
        if not c.ls(locator + "|FitEyeSphere", long=True,
                    type="transform"):
            raise FitSkeletonValidationError("EyeBall Fit 的球体预览缺失")
        return locator
