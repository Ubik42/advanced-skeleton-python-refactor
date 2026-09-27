"""Maya scene storage for the original Face / Pre mask and geometry rows."""
from __future__ import annotations

import json
from contextlib import nullcontext
import re

from adv_py.application.face_pre import EyeLidLayer, FacePreRole, FaceSide
from adv_py.core.face_eyelid_fit import (
    EyeLidLoop, eye_lid_area_faces, order_eye_lid_loop)
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face import MayaFaceHost


_FACE_PATTERN = re.compile(r"^(?P<mesh>.+)\.f\[(?P<index>\d+)\]$")
_EDGE_PATTERN = re.compile(r"^(?P<mesh>.+)\.e\[(?P<index>\d+)\]$")
_VERTEX_PATTERN = re.compile(r"^(?P<mesh>.+)\.vtx\[(?P<index>\d+)\]$")


class MayaFacePreHost(MayaFaceHost):
    def _fit(self, *, required=False):
        matches = self._cmds.ls("FaceFitSkeleton", long=True,
                                type="transform") or []
        if len(matches) > 1 or (required and len(matches) != 1):
            raise FitSkeletonValidationError("FaceFitSkeleton 缺失或不唯一；先记录 Mask")
        return matches[0] if matches else None

    def active_face_side(self) -> FaceSide:
        fit = self._fit(required=True)
        c = self._cmds
        if (c.attributeQuery("NonSymSide", node=fit, exists=True)
                and c.getAttr(fit + ".NonSymSide") == "Left"):
            return FaceSide.LEFT
        return FaceSide.RIGHT

    def set_face_fit_side(self, side: FaceSide) -> FaceSide:
        if not isinstance(side, FaceSide):
            raise ValueError("Face Fit 编辑侧别无效")
        c = self._cmds
        fit = self._fit(required=True)
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能切换引用中的 FaceFitSkeleton")
        with self.transaction("切换 Face Fit 编辑侧"):
            self._transaction_changed = True
            if not c.attributeQuery("NonSym", node=fit, exists=True):
                c.addAttr(fit, longName="NonSym", attributeType="bool")
            if not c.attributeQuery("NonSymSide", node=fit, exists=True):
                c.addAttr(fit, longName="NonSymSide", dataType="string")
            c.setAttr(fit + ".NonSym", True)
            c.setAttr(fit + ".NonSymSide", side.value, type="string")
            for child in c.listRelatives(fit, children=True, type="transform",
                                         fullPath=True) or []:
                c.setAttr(child + ".visibility",
                          child.rsplit("|", 1)[-1].endswith("Left")
                          == (side is FaceSide.LEFT))
        return self.active_face_side()

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
        if (c.ls("FitEyeBall", long=True, type="transform")
                or c.ls("FitEyeBallLeft", long=True, type="transform")):
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

    def create_eye_ball_fit(self, eye_mesh: str, head_joint: str,
                            side: FaceSide = FaceSide.RIGHT) -> str:
        c = self._cmds
        fit = self._fit(required=True)
        suffix = "Left" if side is FaceSide.LEFT else ""
        matches = c.ls(eye_mesh, long=True, type="transform") or []
        if matches != [eye_mesh]:
            raise FitSkeletonValidationError("当前侧眼网格路径不存在或不唯一")
        shape = c.listRelatives(eye_mesh, shapes=True, noIntermediate=True,
                                fullPath=True, type="mesh") or []
        if len(shape) != 1:
            raise FitSkeletonValidationError("眼网格需要唯一可见多边形 Shape")
        heads = c.ls(head_joint, long=True, type="joint") or []
        if len(heads) != 1:
            raise FitSkeletonValidationError("EyeBall Fit 需要唯一的 Head 关节")
        if c.ls("Eye_R", long=True, type="joint") or c.ls("Eye_M", long=True,
                                                           type="joint"):
            raise FitSkeletonValidationError(
                "已存在 Body 眼关节；当前 EyeBall Fit 不支持替换其 Skin 影响")
        for name in ("FaceFitEyeBall" + suffix, "FitEyeBall" + suffix,
                     "FitEyeSphere" + suffix):
            if c.ls(name, long=True):
                raise FitSkeletonValidationError("眼球 Fit 节点名称已占用：" + name)
        bounds = tuple(float(value) for value in c.exactWorldBoundingBox(eye_mesh))
        diameter = bounds[4] - bounds[1]
        if diameter <= 1e-6:
            raise FitSkeletonValidationError("眼网格高度无效")
        center = tuple((bounds[axis] + bounds[axis + 3]) / 2
                       for axis in range(3))
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能在引用中的 FaceFitSkeleton 创建眼球 Fit")
        with (nullcontext() if self._transaction_active else
              self.transaction("建立 Face EyeBall Fit")):
            self._transaction_changed = True
            holder = c.createNode("transform", name="FaceFitEyeBall" + suffix,
                                  parent=fit)
            locator = c.spaceLocator(name="FitEyeBall" + suffix)[0]
            locator = c.parent(locator, holder, absolute=True)[0]
            c.setAttr(locator + ".rotateOrder", 2)
            c.setAttr(locator + "Shape.localScale", 1.5, 1.5, 1.5,
                      type="double3")
            c.xform(locator, worldSpace=True, translation=center)
            c.setAttr(locator + ".scale", diameter, diameter, diameter,
                      type="double3")
            sphere = c.polySphere(name="FitEyeSphere" + suffix, radius=.5,
                                  subdivisionsX=8, subdivisionsY=8,
                                  constructionHistory=False)[0]
            sphere = c.parent(sphere, locator, relative=True)[0]
            c.setAttr(sphere + ".rotateX", 90)
            shape = (c.listRelatives(sphere, shapes=True,
                                     fullPath=True) or [None])[0]
            c.setAttr(shape + ".overrideEnabled", True)
            c.setAttr(shape + ".overrideDisplayType", 2)
            attr = "LeftEye" if side is FaceSide.LEFT else "RightEye"
            if not c.attributeQuery(attr, node=fit, exists=True):
                c.addAttr(fit, longName=attr, dataType="string")
            c.setAttr(fit + "." + attr, eye_mesh.rsplit("|", 1)[-1],
                      type="string")
            c.setAttr(locator + ".rotateZ", lock=True)
            for kind in ("translate", "rotate", "scale"):
                for axis in "XYZ":
                    c.setAttr(fit + "." + kind + axis, lock=True)
        return (c.ls(locator, long=True, type="transform") or [locator])[0]

    def read_eye_ball_fit(self, side: FaceSide | None = None) -> str:
        c = self._cmds
        fit = self._fit(required=True)
        side = side or self.active_face_side()
        suffix = "Left" if side is FaceSide.LEFT else ""
        matches = c.ls("FitEyeBall" + suffix, long=True,
                       type="transform") or []
        if len(matches) != 1 or not matches[0].startswith(fit + "|"):
            raise FitSkeletonValidationError("EyeBall Fit 缺失或父级无效")
        locator = matches[0]
        if not c.ls(locator + "|FitEyeSphere" + suffix, long=True,
                    type="transform"):
            raise FitSkeletonValidationError("EyeBall Fit 的球体预览缺失")
        return locator

    def eye_ball_fit_center_y(self) -> float:
        return float(self._cmds.xform(self.read_eye_ball_fit(), query=True,
                                      worldSpace=True, translation=True)[1])

    def selected_eye_lid_edges(self):
        from maya.api import OpenMaya as om

        c = self._cmds
        selected = c.ls(selection=True, flatten=True, long=True) or []
        edge_matches = [_EDGE_PATTERN.fullmatch(item) for item in selected]
        corner_matches = [_VERTEX_PATTERN.fullmatch(item) for item in selected]
        if (not selected or not any(edge_matches)
                or any(edge is None and corner is None
                       for edge, corner in zip(edge_matches, corner_matches))):
            raise FitSkeletonValidationError("EyeLid Fit 需要闭合边环，可加选一至两个眼角顶点")
        meshes = {match.group("mesh") for match in edge_matches + corner_matches
                  if match is not None}
        if len(meshes) != 1:
            raise FitSkeletonValidationError("EyeLid Fit 只接受同一网格的边和顶点")
        mesh = next(iter(meshes))
        if self.read_face_objects(FacePreRole.FACE) != (mesh,):
            raise FitSkeletonValidationError("眼睑边必须属于 Face 网格")
        indices = tuple(sorted({int(match.group("index")) for match in edge_matches
                                if match is not None}))
        corners = tuple(int(match.group("index")) for match in corner_matches
                        if match is not None)
        if len(corners) > 2 or len(set(corners)) != len(corners):
            raise FitSkeletonValidationError("EyeLid Fit 至多接受两个不同眼角顶点")
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Face 网格 Shape 缺失或不唯一")
        selection = om.MSelectionList()
        selection.add(self.scene_address(shapes[0]))
        mesh_fn = om.MFnMesh(selection.getDagPath(0))
        if not indices or indices[-1] >= mesh_fn.numEdges:
            raise FitSkeletonValidationError("眼睑边索引已超出网格拓扑")
        edges = tuple((index, *mesh_fn.getEdgeVertices(index))
                      for index in indices)
        vertices = {vertex for _, first, second in edges
                    for vertex in (first, second)}
        positions = {vertex: (float(point.x), float(point.y), float(point.z))
                     for vertex in vertices
                     for point in (mesh_fn.getPoint(vertex, om.MSpace.kWorld),)}
        return mesh, edges, positions, corners

    def create_eye_lid_fit(self, layer: EyeLidLayer, mesh: str,
                           loop: EyeLidLoop, positions,
                           edges, selected_corners) -> tuple[str, str]:
        c = self._cmds
        fit = self._fit(required=True)
        side = self.active_face_side()
        suffix = "Left" if side is FaceSide.LEFT else ""
        self.read_eye_ball_fit()
        if self.read_face_objects(FacePreRole.FACE) != (mesh,):
            raise FitSkeletonValidationError("眼睑边与 Face 网格不一致")
        if layer is EyeLidLayer.MAIN:
            self.read_eye_lid_fit(EyeLidLayer.OUTER)
        elif layer is EyeLidLayer.INNER:
            self.read_eye_lid_fit(EyeLidLayer.OUTER)
            self.read_eye_lid_fit(EyeLidLayer.MAIN)
        area_faces = (self._eye_lid_area_faces(mesh, loop.edge_ids, side)
                      if layer is EyeLidLayer.INNER else ())
        part = layer.value
        holder_name = "FaceFitEyeLid" + part + suffix
        geo_name = "FaceFitEyeLid" + part + "Geo" + suffix
        curve_parent_name = "FaceFitEyeLid" + part + "Curve" + suffix
        loc_name = "FaceFitEyeLid" + part + "Loc" + suffix
        curve_names = ("upperEyeLid" + part + "Curve" + suffix,
                       "lowerEyeLid" + part + "Curve" + suffix)
        names = (holder_name, geo_name, curve_parent_name,
                 loc_name, *curve_names)
        if layer is EyeLidLayer.INNER:
            names += ("EyeLidInnerAreaMesh" + suffix,
                      "EyeLidInnerAreaMeshExtrude" + suffix)
        if any(c.ls(name, long=True) for name in names):
            raise FitSkeletonValidationError("眼睑 Fit 节点名称已占用：" + part)
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能在引用的 FaceFitSkeleton 下建立眼睑")
        selected = c.ls(selection=True, long=True) or []
        with (nullcontext() if self._transaction_active else
              self.transaction("建立 EyeLid " + part + " Fit")):
            self._transaction_changed = True
            holder = c.createNode("transform", name=holder_name, parent=fit)
            geo_holder = c.createNode("transform", name=geo_name,
                                      parent=holder)
            curve_holder = c.createNode("transform", name=curve_parent_name,
                                        parent=holder)
            c.createNode("transform", name=loc_name, parent=holder)
            paths = []
            for name, vertices in zip(curve_names,
                                      (loop.upper_vertices, loop.lower_vertices)):
                points = [positions[index] for index in vertices]
                curve = c.curve(name=name, degree=1, point=points)
                curve = c.parent(curve, curve_holder, absolute=True)[0]
                shape = (c.listRelatives(curve, shapes=True,
                                         fullPath=True) or [None])[0]
                c.setAttr(shape + ".overrideEnabled", True)
                c.setAttr(shape + ".overrideColor", {
                    EyeLidLayer.OUTER: 14, EyeLidLayer.MAIN: 13,
                    EyeLidLayer.INNER: 15}[layer])
                paths.append((c.ls(curve, long=True,
                                    type="transform") or [curve])[0])
            radius = float(c.getAttr(fit + ".faceScale")) / 400.0
            for name, curve in zip(("upper", "lower"), paths):
                profile = c.circle(normal=(0, 1, 0), radius=radius,
                                   constructionHistory=False)[0]
                tube = c.extrude(profile, curve, constructionHistory=False,
                                 extrudeType=2, fixedPath=True,
                                 useComponentPivot=True,
                                 useProfileNormal=True)[0]
                c.delete(profile)
                tube = c.rename(tube, name + "EyeLidCylinder" + part + suffix)
                tube = c.parent(tube, geo_holder, absolute=True)[0]
                c.setAttr(tube + ".overrideEnabled", True)
                c.setAttr(tube + ".overrideDisplayType", 2)
            if layer is EyeLidLayer.INNER:
                self._create_eye_lid_area(mesh, area_faces, geo_holder, fit,
                                          side)
            c.addAttr(holder, longName="selection", dataType="string")
            c.setAttr(holder + ".selection", " ".join(
                [f"{mesh}.e[{index}]" for index in loop.edge_ids]
                + [f"{mesh}.vtx[{index}]" for index in selected_corners]),
                type="string")
            c.addAttr(holder, longName="advPyFaceCount", attributeType="long")
            c.setAttr(holder + ".advPyFaceCount",
                      int(c.polyEvaluate(mesh, face=True)))
            c.addAttr(holder, longName="advPyEdgeVertices", dataType="string")
            c.setAttr(holder + ".advPyEdgeVertices", json.dumps(
                [(index, *sorted((first, second)))
                 for index, first, second in sorted(edges)],
                separators=(",", ":")), type="string")
            c.select(selected, replace=True) if selected else c.select(clear=True)
        return tuple(paths)

    def mirror_right_eye_fit_to_left(self, left_eye_mesh: str) -> dict:
        """Build left EyeBall and eyelid Fit on a symmetric Face mesh."""
        from maya.api import OpenMaya as om

        c = self._cmds
        fit = self._fit(required=True)
        if (c.attributeQuery("NonSym", node=fit, exists=True)
                and c.getAttr(fit + ".NonSym")):
            raise FitSkeletonValidationError("非对称 Face Fit 应单独编辑左侧")
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能镜像引用中的 Face Fit")
        mesh = self.read_face_objects(FacePreRole.FACE)[0]
        self.read_eye_ball_fit(FaceSide.RIGHT)
        if c.ls("FaceFitEyeBallLeft", long=True):
            raise FitSkeletonValidationError("左侧 Face Fit 已存在")
        eye_meshes = c.ls(left_eye_mesh, long=True, type="transform") or []
        heads = c.ls(c.getAttr(fit + ".HeadJoint"), long=True,
                     type="joint") or []
        if len(eye_meshes) != 1 or len(heads) != 1:
            raise FitSkeletonValidationError("镜像眼睑需要唯一左眼网格和 Head 关节")
        shape = (c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or [None])[0]
        selection = om.MSelectionList()
        selection.add(shape)
        mesh_fn = om.MFnMesh(selection.getDagPath(0))
        points = [tuple(float(mesh_fn.getPoint(index, om.MSpace.kWorld)[axis])
                        for axis in range(3))
                  for index in range(mesh_fn.numVertices)]
        edge_lookup = {tuple(sorted(mesh_fn.getEdgeVertices(index))): index
                       for index in range(mesh_fn.numEdges)}
        right_rows = {}
        vertices = set()
        for layer in EyeLidLayer:
            self.read_eye_lid_fit(layer, FaceSide.RIGHT)
            holder = (c.ls("FaceFitEyeLid" + layer.value,
                           long=True, type="transform") or [None])[0]
            if int(c.getAttr(holder + ".advPyFaceCount")) != mesh_fn.numPolygons:
                raise FitSkeletonValidationError("右侧眼睑 Fit 与 Face 面数不一致")
            record = (c.getAttr(holder + ".selection") or "").split()
            edges, corners = [], []
            for item in record:
                edge = _EDGE_PATTERN.fullmatch(item)
                corner = _VERTEX_PATTERN.fullmatch(item)
                if edge and edge.group("mesh") == mesh:
                    index = int(edge.group("index"))
                    if index >= mesh_fn.numEdges:
                        raise FitSkeletonValidationError("右侧眼睑边索引无效")
                    first, second = mesh_fn.getEdgeVertices(index)
                    edges.append((index, first, second))
                    vertices.update((first, second))
                elif corner and corner.group("mesh") == mesh:
                    index = int(corner.group("index"))
                    if index >= mesh_fn.numVertices:
                        raise FitSkeletonValidationError("右侧眼角顶点索引无效")
                    corners.append(index)
                    vertices.add(index)
                else:
                    raise FitSkeletonValidationError("右侧眼睑选择记录无效")
            expected = [tuple(row) for row in json.loads(
                c.getAttr(holder + ".advPyEdgeVertices"))]
            observed = [(index, *sorted((first, second)))
                        for index, first, second in sorted(edges)]
            if not edges or observed != expected:
                raise FitSkeletonValidationError("右侧眼睑边连接已改变")
            right_rows[layer] = (tuple(edges), tuple(corners))
        bounds = c.exactWorldBoundingBox(eye_meshes[0])
        if (bounds[0] + bounds[3]) / 2. <= 1e-6:
            raise FitSkeletonValidationError("所选左眼网格必须位于正 X 侧")
        diameter = max(bounds[index + 3] - bounds[index]
                       for index in range(3))
        tolerance = max(diameter * .05, 1e-4)
        candidates = [index for index, point in enumerate(points)
                      if point[0] > 1e-6]
        if not candidates:
            raise FitSkeletonValidationError("Face 网格缺少左侧顶点")
        mirrored = {}
        maximum_distance = 0.
        for vertex in sorted(vertices):
            source = points[vertex]
            if source[0] >= -1e-6:
                raise FitSkeletonValidationError("右侧眼睑 Fit 跨越对称中线")
            target = (-source[0], source[1], source[2])
            counterpart = min(candidates, key=lambda index:
                sum((points[index][axis] - target[axis]) ** 2
                    for axis in range(3)))
            distance_sq = sum((points[counterpart][axis] - target[axis]) ** 2
                              for axis in range(3))
            if distance_sq > tolerance * tolerance:
                raise FitSkeletonValidationError(
                    f"Face 网格左右眼睑顶点不对称：右顶点 {vertex} "
                    f"镜像距离 {distance_sq ** .5:.6f} cm，"
                    f"容差 {tolerance:.6f} cm")
            maximum_distance = max(maximum_distance, distance_sq ** .5)
            mirrored[vertex] = counterpart
        if len(set(mirrored.values())) != len(mirrored):
            raise FitSkeletonValidationError("镜像眼睑顶点映射不唯一")
        eye_y = (bounds[1] + bounds[4]) / 2.
        left_rows = {}
        for layer, (edges, corners) in right_rows.items():
            reflected = []
            for _, first, second in edges:
                left_first, left_second = mirrored[first], mirrored[second]
                edge_id = edge_lookup.get(tuple(sorted((left_first,
                                                        left_second))))
                if edge_id is None:
                    raise FitSkeletonValidationError("镜像侧缺少对应眼睑边")
                reflected.append((edge_id, left_first, left_second))
            left_corners = tuple(mirrored[index] for index in corners)
            left_positions = {index: points[index] for _, first, second in
                              reflected for index in (first, second)}
            loop = order_eye_lid_loop(tuple(reflected), left_positions,
                eye_center_y=eye_y, corner_vertices=left_corners,
                side=FaceSide.LEFT.value)
            left_rows[layer] = (loop, left_positions,
                                tuple(reflected), left_corners)
        selected = c.ls(selection=True, long=True) or []
        with self.transaction("从右侧镜像生成左侧眼睑 Fit"):
            self._transaction_changed = True
            if not c.attributeQuery("NonSymSide", node=fit, exists=True):
                c.addAttr(fit, longName="NonSymSide", dataType="string")
            c.setAttr(fit + ".NonSymSide", "Left", type="string")
            self.create_eye_ball_fit(eye_meshes[0], heads[0], FaceSide.LEFT)
            for layer in EyeLidLayer:
                self.create_eye_lid_fit(layer, mesh, *left_rows[layer])
            c.setAttr(fit + ".NonSymSide", "Right", type="string")
            c.select(selected, replace=True) if selected else c.select(clear=True)
        return {"mapped_vertices": len(mirrored),
                "layers": tuple(layer.value for layer in EyeLidLayer),
                "maximum_distance_cm": maximum_distance,
                "tolerance_cm": tolerance}

    def _eye_lid_area_faces(self, mesh: str, inner_edges: tuple[int, ...],
                            side: FaceSide) -> tuple[int, ...]:
        from maya.api import OpenMaya as om

        c = self._cmds
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Face 网格 Shape 缺失或不唯一")
        selection = om.MSelectionList()
        selection.add(self.scene_address(shapes[0]))
        mesh_fn = om.MFnMesh(selection.getDagPath(0))

        def stored_edges(layer: EyeLidLayer) -> tuple[int, ...]:
            self.read_eye_lid_fit(layer, side)
            suffix = "Left" if side is FaceSide.LEFT else ""
            holder = (c.ls("FaceFitEyeLid" + layer.value + suffix, long=True,
                           type="transform") or [None])[0]
            record = c.getAttr(holder + ".selection") or ""
            components = [_EDGE_PATTERN.fullmatch(item) for item in record.split()
                          if ".e[" in item]
            if (not components or any(match is None or
                    match.group("mesh") != mesh for match in components)
                    or int(c.getAttr(holder + ".advPyFaceCount"))
                       != mesh_fn.numPolygons):
                raise FitSkeletonValidationError("眼睑 " + layer.value
                                                + " 与当前 Face 拓扑不一致")
            expected = json.loads(c.getAttr(holder + ".advPyEdgeVertices"))
            indices = tuple(sorted(int(match.group("index"))
                                   for match in components))
            if (indices[-1] >= mesh_fn.numEdges or
                    [(index, *sorted(mesh_fn.getEdgeVertices(index)))
                     for index in indices] != [tuple(row) for row in expected]):
                raise FitSkeletonValidationError("眼睑 " + layer.value
                                                + " 边连接已改变")
            return indices

        outer = stored_edges(EyeLidLayer.OUTER)
        main = stored_edges(EyeLidLayer.MAIN)
        poly_it = om.MItMeshPolygon(selection.getDagPath(0))
        face_edges = []
        while not poly_it.isDone():
            face_edges.append(tuple(poly_it.getEdges()))
            poly_it.next()
        edge_it = om.MItMeshEdge(selection.getDagPath(0))
        edge_faces = []
        while not edge_it.isDone():
            edge_faces.append(tuple(edge_it.getConnectedFaces()))
            edge_it.next()
        return eye_lid_area_faces(face_edges, edge_faces,
                                  outer_edges=outer, main_edges=main,
                                  inner_edges=inner_edges)

    def _create_eye_lid_area(self, mesh: str, faces: tuple[int, ...],
                             geo_holder: str, fit: str,
                             side: FaceSide) -> None:
        c = self._cmds
        suffix = "Left" if side is FaceSide.LEFT else ""
        area = c.duplicate(mesh, name="EyeLidInnerAreaMesh" + suffix,
                           returnRootsOnly=True)[0]
        area = c.parent(area, geo_holder, absolute=True)[0]
        outside = set(range(int(c.polyEvaluate(area, face=True)))) - set(faces)
        if outside:
            c.polyDelFacet([f"{area}.f[{index}]" for index in sorted(outside)],
                           constructionHistory=True)
        if int(c.polyEvaluate(area, face=True)) != len(faces):
            raise FitSkeletonValidationError("EyeLid Inner 区域网格面数不一致")
        c.addAttr(area, longName="selection", dataType="string")
        c.setAttr(area + ".selection", " ".join(
            f"{mesh}.f[{index}]" for index in faces), type="string")
        preview = c.duplicate(area, name="EyeLidInnerAreaMeshExtrude" + suffix,
                              returnRootsOnly=True)[0]
        if (c.listRelatives(preview, parent=True, fullPath=True) or [None])[0] \
                != (c.ls(geo_holder, long=True) or [geo_holder])[0]:
            preview = c.parent(preview, geo_holder, absolute=True)[0]
        c.setAttr(area + ".visibility", False)
        c.polyExtrudeFacet(preview + ".f[0:"
                           + str(len(faces) - 1) + "]",
                           localTranslateZ=float(c.getAttr(fit + ".faceScale"))
                           / 500.0, keepFacesTogether=True,
                           constructionHistory=True)
        shader_name = "AdvPyFaceFitRed"
        group_name = "AdvPyFaceFitRedSG"
        if not c.objExists(shader_name):
            shader = c.shadingNode("lambert", asShader=True, name=shader_name)
            c.setAttr(shader + ".color", .65, .08, .08, type="double3")
        elif c.nodeType(shader_name) != "lambert":
            raise FitSkeletonValidationError("Face Fit 预览材质名称已被占用")
        if not c.objExists(group_name):
            group = c.sets(renderable=True, noSurfaceShader=True, empty=True,
                           name=group_name)
            c.connectAttr(shader_name + ".outColor", group + ".surfaceShader",
                          force=True)
        elif c.nodeType(group_name) != "shadingEngine":
            raise FitSkeletonValidationError("Face Fit 预览材质组名称已被占用")
        c.sets(preview, edit=True, forceElement=group_name)

    def read_eye_lid_area(self, side: FaceSide | None = None) -> tuple[str, str]:
        c = self._cmds
        side = side or self.active_face_side()
        suffix = "Left" if side is FaceSide.LEFT else ""
        self.read_eye_lid_fit(EyeLidLayer.INNER, side)
        holder = (c.ls("FaceFitEyeLidInner" + suffix, long=True,
                       type="transform") or [None])[0]
        geo_holder = holder + "|FaceFitEyeLidInnerGeo" + suffix
        paths = tuple(geo_holder + "|" + name for name in
                      ("EyeLidInnerAreaMesh" + suffix,
                       "EyeLidInnerAreaMeshExtrude" + suffix))
        if any((c.ls(path, long=True, type="transform") or []) != [path]
               or not c.listRelatives(path, shapes=True, type="mesh")
               for path in paths):
            raise FitSkeletonValidationError("EyeLid Inner 区域网格缺失")
        return paths

    def read_eye_lid_fit(self, layer: EyeLidLayer,
                         side: FaceSide | None = None) -> tuple[str, str]:
        c = self._cmds
        fit = self._fit(required=True)
        side = side or self.active_face_side()
        suffix = "Left" if side is FaceSide.LEFT else ""
        holder = c.ls("FaceFitEyeLid" + layer.value + suffix, long=True,
                      type="transform") or []
        if len(holder) != 1 or not holder[0].startswith(fit + "|"):
            raise FitSkeletonValidationError("眼睑 Fit 缺失或父级无效：" + layer.value)
        curve_parent = holder[0] + "|FaceFitEyeLid" + layer.value \
                       + "Curve" + suffix
        paths = tuple(curve_parent + "|" + prefix + "EyeLid" + layer.value
                      + "Curve" + suffix for prefix in ("upper", "lower"))
        if any((c.ls(path, long=True, type="transform") or []) != [path]
               for path in paths):
            raise FitSkeletonValidationError("眼睑 Fit 曲线缺失：" + layer.value)
        return paths

    def select_eye_lid_fit(self, layer: EyeLidLayer) -> int:
        from maya.api import OpenMaya as om

        side = self.active_face_side()
        suffix = "Left" if side is FaceSide.LEFT else ""
        self.read_eye_lid_fit(layer, side)
        c = self._cmds
        holder = (c.ls("FaceFitEyeLid" + layer.value + suffix, long=True,
                       type="transform") or [None])[0]
        selected = tuple((c.getAttr(holder + ".selection") or "").split())
        edge_matches = [_EDGE_PATTERN.fullmatch(item) for item in selected]
        corner_matches = [_VERTEX_PATTERN.fullmatch(item) for item in selected]
        if (not any(edge_matches)
                or any(edge is None and corner is None
                       for edge, corner in zip(edge_matches, corner_matches))):
            raise FitSkeletonValidationError("眼睑边选择记录无效")
        mesh = next(match.group("mesh") for match in edge_matches
                    if match is not None)
        if (not c.objExists(mesh)
                or any(match.group("mesh") != mesh
                       for match in edge_matches + corner_matches
                       if match is not None)
                or int(c.polyEvaluate(mesh, face=True))
                    != int(c.getAttr(holder + ".advPyFaceCount"))):
            raise FitSkeletonValidationError("眼睑网格拓扑已改变")
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("眼睑 Face 网格已缺失")
        selection = om.MSelectionList()
        selection.add(self.scene_address(shapes[0]))
        mesh_fn = om.MFnMesh(selection.getDagPath(0))
        expected = json.loads(c.getAttr(holder + ".advPyEdgeVertices"))
        indices = sorted(int(match.group("index")) for match in edge_matches
                         if match is not None)
        corners = tuple(int(match.group("index")) for match in corner_matches
                        if match is not None)
        if indices[-1] >= mesh_fn.numEdges or any(
                index >= mesh_fn.numVertices for index in corners):
            raise FitSkeletonValidationError("眼睑边索引已超出网格拓扑")
        observed = [(index, *sorted(mesh_fn.getEdgeVertices(index)))
                    for index in indices]
        if observed != [tuple(row) for row in expected]:
            raise FitSkeletonValidationError("眼睑边连接已改变，不能使用旧 Fit 选择")
        if any(vertex not in {item for _, first, second in observed
                              for item in (first, second)} for vertex in corners):
            raise FitSkeletonValidationError("眼角顶点已不在旧 Fit 边环上")
        c.select(selected, replace=True)
        return len(indices)
