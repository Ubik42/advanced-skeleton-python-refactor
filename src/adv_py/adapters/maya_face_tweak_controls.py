"""Original Face/Tweaks control-shape and detach/attach scene operations."""
from __future__ import annotations

from math import dist

from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face_pre import MayaFacePreHost


_FACE_SHADERS = (
    ("asFaceBlue", (0.0, 0.0, 1.0)),
    ("asFaceBrown", (0.541, 0.282, 0.2)),
    ("asFaceGreen", (0.0, 0.275, 0.098)),
    ("asFaceCyan", (0.0, 0.5, 0.5)),
    ("asFaceRed", (0.4, 0.0, 0.0)),
)


class MayaFaceTweakControlsHost(MayaFacePreHost):
    @property
    def _maya(self):
        return getattr(self._cmds, "raw", self._cmds)

    def _name(self, leaf: str) -> str:
        return ":" + ((self.namespace + ":") if self.namespace else "") + leaf

    def _all_head_meshes(self) -> tuple[str, ...]:
        meshes = self.read_face_objects(FacePreRole.ALL_HEAD)
        if not meshes:
            raise FitSkeletonValidationError(
                "Face / Pre 须先记录 All Head 蒙皮网格")
        return tuple(self.scene_address(path) for path in meshes)

    def _mesh_skin(self, mesh: str) -> str:
        c = self._maya
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or ()
        if len(shapes) != 1:
            raise FitSkeletonValidationError("Face 网格 Shape 缺失或不唯一：" + mesh)
        history = c.listHistory(shapes[0], pruneDagObjects=True) or ()
        skins = c.ls(history, type="skinCluster") or ()
        if len(skins) != 1:
            raise FitSkeletonValidationError(
                "Face 网格需要唯一 SkinCluster：" + mesh)
        return skins[0]

    def _all_head_skins(self) -> tuple[str, ...]:
        c = self._maya
        skins = tuple(dict.fromkeys(self._mesh_skin(mesh)
                                    for mesh in self._all_head_meshes()))
        if any(c.referenceQuery(skin, isNodeReferenced=True)
               for skin in skins):
            raise FitSkeletonValidationError(
                "引用中的 Face SkinCluster 不能直接 Detach／Attach")
        return skins

    def detach_face_controllers(self) -> tuple[str, ...]:
        """asFaceDetachControllers disables every All Head Skin envelope."""
        c = self._maya
        skins = self._all_head_skins()
        if any(not c.getAttr(skin + ".envelope", settable=True)
               for skin in skins):
            raise FitSkeletonValidationError("Face SkinCluster envelope 不可写")
        with self.transaction("Face Tweaks 分离控制器"):
            self._transaction_changed = True
            for skin in skins:
                c.setAttr(skin + ".envelope", 0)
        return skins

    def _ensure_face_shaders(self) -> None:
        c = self._maya
        for leaf, color in _FACE_SHADERS:
            shader = self._name(leaf)
            shading_group = self._name(leaf + "SG")
            if c.objExists(shader) and c.objExists(shading_group):
                continue
            self._transaction_changed = True
            for node in (shader, shading_group):
                if c.objExists(node):
                    c.delete(node)
            c.shadingNode("lambert", asShader=True, name=shader)
            c.sets(renderable=True, noSurfaceShader=True, empty=True,
                   name=shading_group)
            c.connectAttr(shader + ".outColor",
                          shading_group + ".surfaceShader", force=True)
            for attribute in ("color", "ambientColor", "incandescence"):
                c.setAttr(shader + "." + attribute, *color, type="float3")

    def _face_visibility_controls(self) -> tuple[tuple[str, str], ...]:
        c = self._maya
        box = self._name("ctrlBox")
        if not c.objExists(box):
            raise FitSkeletonValidationError("Face ctrlBox 不存在")
        rows = []
        for attribute, shader in (("ACtrlVis", "asFaceGreenSG"),
                                  ("BCtrlVis", "asFaceRedSG"),
                                  ("CCtrlVis", "asFaceBlueSG")):
            if not c.attributeQuery(attribute, node=box, exists=True):
                raise FitSkeletonValidationError(
                    "Face ctrlBox 缺少可见性属性：" + attribute)
            connected = c.listConnections(box + "." + attribute,
                                          source=False, destination=True) or ()
            for node in connected:
                found = c.ls(node, long=True, type="transform") or ()
                if len(found) == 1 and found[0] not in {row[0] for row in rows}:
                    rows.append((found[0], self._name(shader)))
        return tuple(rows)

    def swap_face_controls_to_spheres(self, *, keep_offset: bool = False
                                      ) -> tuple[str, ...]:
        """Replace A/B/C on-face curve shapes with original shaded spheres."""
        if type(keep_offset) is not bool:
            raise ValueError("Face 球形控制器偏移选项无效")
        c = self._maya
        fit = self._name("FaceFitSkeleton")
        if (not c.objExists(fit)
                or not c.attributeQuery("faceScale", node=fit, exists=True)):
            raise FitSkeletonValidationError("Face Fit 缺少 faceScale")
        scale = float(c.getAttr(fit + ".faceScale"))
        if scale <= 0:
            raise FitSkeletonValidationError("Face Fit faceScale 必须大于零")
        controls = self._face_visibility_controls()
        selection = tuple(c.ls(selection=True, long=True) or ())
        changed = []
        with self.transaction("Face Tweaks 控制器改为球形"):
            try:
                self._ensure_face_shaders()
                for control, shading_group in controls:
                    leaf = control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                    if leaf.startswith("SmilePull_"):
                        continue
                    curves = c.listRelatives(control, shapes=True,
                                             noIntermediate=True,
                                             fullPath=True,
                                             type="nurbsCurve") or ()
                    if len(curves) != 1:
                        continue
                    pos_a = c.xform(control + ".cv[1]", query=True,
                                    worldSpace=True, translation=True)
                    pos_b = c.xform(control + ".cv[5]", query=True,
                                    worldSpace=True, translation=True)
                    radius = dist(pos_a, pos_b) * 5.0 / scale
                    if radius <= 0:
                        raise FitSkeletonValidationError(
                            "Face 控制曲线大小为零：" + control)
                    self._transaction_changed = True
                    sphere = c.sphere(name=self._name(leaf + "Sphere"),
                                      pivot=(0, 0, 0), axis=(0, 1, 0),
                                      radius=radius, degree=3, sections=8,
                                      spans=4, constructionHistory=False)[0]
                    shapes = c.listRelatives(sphere, shapes=True,
                                              fullPath=True,
                                              type="nurbsSurface") or ()
                    if len(shapes) != 1:
                        raise RuntimeError("Face 球形控制器 Shape 创建失败")
                    attached = c.parent(shapes[0], control, add=True,
                                        shape=True, relative=True)
                    if len(attached) != 1:
                        raise RuntimeError("Face 球形 Shape 挂接失败")
                    c.delete(curves[0])
                    final_shape = c.rename(attached[0], leaf + "Shape")
                    c.delete(sphere)
                    c.sets(final_shape, edit=True,
                           forceElement=shading_group)
                    if keep_offset:
                        surface = c.xform(control + ".cv[0][0]",
                                          query=True, worldSpace=True,
                                          translation=True)
                        offset = dist(pos_a, surface)
                        c.move(0, 0, offset,
                               control + ".cv[0:99][0:99]", relative=True)
                    changed.append(control)
            finally:
                c.select(selection, replace=True) if selection else c.select(
                    clear=True)
        return tuple(changed)

    def _face_control_members(self) -> tuple[str, ...]:
        c = self._maya
        control_set = self._name("FaceControlSet")
        if not c.objExists(control_set):
            raise FitSkeletonValidationError("FaceControlSet 不存在")
        members = []
        for item in c.sets(control_set, query=True) or ():
            paths = c.ls(item, long=True, type="transform") or ()
            if len(paths) == 1 and paths[0] not in members:
                members.append(paths[0])
        if not members:
            raise FitSkeletonValidationError("FaceControlSet 没有控制器")
        return tuple(sorted(members))

    def _mirror_face_control_values(self, controls: tuple[str, ...]) -> None:
        """The Face branch of asMirror copies keyable R values to L."""
        c = self._maya
        by_leaf = {path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]: path
                   for path in controls}
        for leaf, source in sorted(by_leaf.items()):
            if not leaf.endswith("_R"):
                continue
            destination = by_leaf.get(leaf[:-2] + "_L")
            if destination is None:
                continue
            for attribute in c.listAttr(source, keyable=True) or ():
                if attribute == "visibility":
                    continue
                target_attribute = attribute.replace("_R", "_L")
                target_plug = destination + "." + target_attribute
                if (not c.attributeQuery(target_attribute,
                                         node=destination, exists=True)
                        or not c.getAttr(target_plug, settable=True)):
                    continue
                value = c.getAttr(source + "." + attribute)
                if type(value) in (bool, int, float):
                    c.setAttr(target_plug, value)

    def _resolve_face_control(self, leaf: str) -> str:
        paths = self._maya.ls(self._name(leaf), long=True,
                             type="transform") or ()
        if len(paths) != 1:
            raise RuntimeError("Face 控制器在改挂后缺失或重名：" + leaf)
        return paths[0]

    def _attach_orient_control(self, leaf: str) -> bool:
        c = self._maya
        control = self._resolve_face_control(leaf)
        if not (c.getAttr(control + ".translateX", keyable=True)
                or c.getAttr(control + ".rotateX", keyable=True)):
            return False
        translation = c.getAttr(control + ".translate")[0]
        rotation = c.getAttr(control + ".rotate")[0]
        if not any(abs(float(value)) > 1e-9
                   for value in (*translation, *rotation)):
            return False
        name, separator, side = leaf.rpartition("_")
        if not separator or side not in ("R", "L", "M"):
            raise FitSkeletonValidationError(
                "Face 控制器名称缺少侧别：" + leaf)
        suffix = "_" + side
        custom_name = name + "CustomOrient" + suffix
        custom = self._name(custom_name)
        if not c.objExists(custom):
            sdk = self._name("SDK" + name + suffix)
            node = sdk if c.objExists(sdk) else control
            parents = c.listRelatives(node, parent=True,
                                      fullPath=True) or ()
            if len(parents) != 1:
                raise FitSkeletonValidationError(
                    "Face 控制器缺少可插入朝向层的父级：" + leaf)
            c.createNode("transform", name=custom, parent=parents[0])
            c.parent(node, custom, absolute=True)
            control = self._resolve_face_control(leaf)
        custom_paths = c.ls(custom, long=True, type="transform") or ()
        if len(custom_paths) != 1:
            raise RuntimeError("Face CustomOrient 路径无效：" + custom_name)
        custom = custom_paths[0]
        temp = c.createNode("transform", name=self._name("AdvPyFaceOrientTemp"),
                            parent=control)
        parent = (c.listRelatives(custom, parent=True, fullPath=True) or (None,))[0]
        if parent is None:
            raise RuntimeError("Face CustomOrient 缺少父级：" + custom_name)
        temp = c.parent(temp, parent, absolute=True)[0]
        constraint = c.parentConstraint(temp, custom,
                                        maintainOffset=False) or ()
        if len(constraint) != 1:
            raise RuntimeError("Face CustomOrient 定向失败：" + custom_name)
        c.delete(constraint[0], temp)
        control = self._resolve_face_control(leaf)
        c.xform(control, objectSpace=True,
                translation=(0, 0, 0), rotation=(0, 0, 0))
        if (("Lip" in name and name[-1:].isupper())
                or name == "cornerLip"):
            ribbon = self._name(name + "RibbonJointOffset" + suffix)
            if c.objExists(ribbon):
                children = c.listRelatives(ribbon, children=True,
                                           type="transform", fullPath=True) or ()
                if children:
                    moved = c.parent(children, world=True, absolute=True)
                    world_rotation = c.xform(control, query=True,
                                             worldSpace=True, rotation=True)
                    c.xform(ribbon, worldSpace=True,
                            rotation=world_rotation)
                    c.parent(moved, ribbon, absolute=True)
        attach = self._name(name + "Attach" + suffix)
        if c.objExists(attach):
            second = self._name(name + "CustomOrient2" + suffix)
            offset = self._name(name + "Offset" + suffix)
            subtract = self._name(name + "Subtract" + suffix)
            if (c.objExists(second) or not c.objExists(offset)
                    or not c.objExists(subtract)):
                raise FitSkeletonValidationError(
                    "Face Mixed-Mode 朝向层不完整或重复：" + leaf)
            c.createNode("transform", name=second, parent=custom)
            c.parent(second, offset, absolute=True)
            c.parent(subtract, second, relative=True)
        return True

    def attach_face_controllers(self) -> tuple[str, ...]:
        """Mirror, absorb oriented control offsets, and rebind Face skins."""
        from .maya_deform_skinning import freeze_native_skin_cluster

        c = self._maya
        controls = self._face_control_members()
        skins = self._all_head_skins()
        if any(not c.getAttr(skin + ".envelope", settable=True)
               for skin in skins):
            raise FitSkeletonValidationError("Face SkinCluster envelope 不可写")
        # Maya may reparent a selected controller while absorbing its offset.
        # Shortest unique names survive that DAG path change like MEL's ls -sl.
        selection = tuple(c.ls(selection=True) or ())
        changed = []
        with self.transaction("Face Tweaks 重新附着控制器"):
            try:
                self._transaction_changed = True
                self._mirror_face_control_values(controls)
                for path in controls:
                    leaf = path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                    if leaf.startswith(("Iris_", "Pupil_")):
                        continue
                    if self._attach_orient_control(leaf):
                        changed.append(leaf)
                for skin in skins:
                    freeze_native_skin_cluster(skin)
                    c.setAttr(skin + ".envelope", 1)
                face_layer = self._name("FaceJointsLayer")
                face_bs = self._name("asFaceBS")
                if c.objExists(face_layer) and c.objExists(face_bs):
                    for child in c.listRelatives(face_layer, children=True,
                                                 fullPath=True) or ():
                        history = c.listHistory(child,
                                                pruneDagObjects=True) or ()
                        for skin in c.ls(history, type="skinCluster") or ():
                            freeze_native_skin_cluster(skin)
                c.dgdirty(allPlugs=True)
            finally:
                remaining = tuple(item for item in selection if c.objExists(item))
                c.select(remaining, replace=True) if remaining else c.select(
                    clear=True)
        return tuple(changed)
