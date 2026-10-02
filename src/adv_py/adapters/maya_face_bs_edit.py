"""Original live BlendShape editing and half-side mirror geometry."""
from contextlib import nullcontext
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_blendshape_edit import BLENDED_FACE_TARGETS, original_face_bs_mirror_name
from adv_py.core.fit_settings import FitSkeletonValidationError


from .maya_original_transform_channels import lock_original_transform_channels

class MayaFaceBSEditMixin:
    def original_face_bs_aliases(self, node="asFaceBS"):
        c = self._cmds
        values = c.listAttr(node + ".weight", multi=True) or []
        # Maya 2025 may return a leading dot from listAttr -multi.
        return tuple(value.lstrip(".") for value in values)

    def original_face_bs_editable_targets(self):
        c = self._cmds
        if not c.objExists("asFaceBS"):
            raise FitSkeletonValidationError("请先将 Face 驱动转换为 BlendShape")
        return tuple(name for name in self.original_face_bs_aliases()
                     if not name.endswith("_L") and not name.startswith("weight")
                     and c.listConnections("asFaceBS." + name, source=True, destination=False,
                                           skipConversionNodes=True, type="animCurve"))

    def set_original_face_bs_edit_weight(self, target, value):
        self._require_transaction()
        if target not in self.original_face_bs_editable_targets():
            raise FitSkeletonValidationError("请选择原版 BlendShape 编辑目标")
        if not 0 <= value <= 1:
            raise FitSkeletonValidationError("BlendShape 编辑权重范围为 0 到 1")
        self._transaction_changed = True
        self._cmds.setAttr("asFaceBS." + target, float(value))
        getattr(self._cmds,"raw",self._cmds).refresh()
        return {"target":target,"weight":float(value)}

    def capture_original_face_bs_edit(self):
        c = self._cmds
        raw = getattr(c, "raw", c)
        self.original_face_bs_editable_targets()
        faces = self.read_face_objects(FacePreRole.FACE)
        if len(faces) != 1:
            raise FitSkeletonValidationError("BlendShape 编辑需要唯一 Face 网格")
        geometry = self._original_bs_physical_address(raw.ls(self.scene_address(faces[0]), long=True)[0])
        geos = [geometry]
        for mesh in self.read_face_objects(FacePreRole.ALL_HEAD):
            path = self._original_bs_physical_address(raw.ls(self.scene_address(mesh), long=True)[0])
            if path not in geos:
                geos.append(path)
        extras = set()
        for part in ("Eyebrow", "EyeLash", "Extras"):
            for mesh in self.read_original_face_parts(part):
                paths = raw.ls(self.scene_address(mesh.split(".", 1)[0]), long=True) or []
                extras.update(self._original_bs_physical_address(path) for path in paths)
        half = []
        for mesh in geos:
            if mesh not in extras:
                continue
            lower = raw.getAttr(mesh + ".boundingBoxMin")[0]
            upper = raw.getAttr(mesh + ".boundingBoxMax")[0]
            if lower[0] > 0 or upper[0] < 0:
                half.append(mesh)
        fit = self._fit(required=True)
        return {"geometry": geometry, "geos": tuple(geos), "half": tuple(half),
                "skin": self.original_face_production_skin(geometry, c.getAttr(fit + ".HeadJoint")),
                "cheek": tuple(c.xform("JawPivot", query=True, worldSpace=True, translation=True))}

    def _original_bs_mesh_sample(self, source, name, parent="deleteThis"):
        c = self._cmds
        raw = getattr(c, "raw", c)
        shape = c.createNode("mesh")
        transform = c.rename(c.listRelatives(shape, parent=True)[0], name)
        shape = c.listRelatives(transform, shapes=True)[0]
        input_shape = raw.listRelatives(source, shapes=True, noIntermediate=True, fullPath=True, type="mesh")[0]
        raw.connectAttr(input_shape + ".outMesh", self.scene_address(shape) + ".inMesh")
        raw.refresh()
        raw.disconnectAttr(input_shape + ".outMesh", self.scene_address(shape) + ".inMesh")
        raw.sets(self.scene_address(transform), edit=True, forceElement=":initialShadingGroup")
        lock_original_transform_channels(c, transform)
        c.parent(transform, parent)
        return name

    def _original_bs_mesh_shape(self, node):
        return self._cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True, type="mesh")[0]

    def _original_bs_native_wrap(self, target, driver, *, exclusive=True, name=None, add=False):
        c = self._cmds
        raw = getattr(c, "raw", c)
        from maya import mel
        before = set(raw.ls(type="wrap") or [])
        raw.select((self.scene_address(target), self.scene_address(driver)), replace=True)
        with c._creation_namespace() if hasattr(c, "_creation_namespace") else nullcontext():
            if add:
                mel.eval("AddWrapInfluence;")
            else:
                mel.eval('doWrapArgList "7" { "1","0","1", "2", "' + str(int(exclusive)) + '", "1", "1", "0" };')
        created = [node for node in raw.ls(type="wrap") or [] if node not in before]
        if created and name:
            c.rename(created[0], name)
        return tuple(created)

    def _original_bs_prepare_half_meshes(self, source):
        c = self._cmds
        raw = getattr(c, "raw", c)
        blends = c.ls("asFaceBS*", type="blendShape") or []
        for node in blends:
            c.setAttr(node + ".envelope", 0)
        for name, enabled in (("faceCombinedDefault", False), ("faceCombined", True)):
            if enabled:
                for node in blends:
                    c.setAttr(node + ".envelope", 1)
            copies = []
            for index, mesh in enumerate(source["half"]):
                copies.append(self._original_bs_mesh_sample(mesh, "halfSideSample" + str(index)))
            if len(copies) > 1:
                combined = c.polyUnite(copies, constructionHistory=False, mergeUVSets=1, name=name)[0]
                c.delete(copies)
                c.parent(combined, "deleteThis")
            else:
                c.rename(copies[0], name)
            raw.sets(self.scene_address(name), edit=True, forceElement=":initialShadingGroup")
            c.setAttr(name + ".v", 0)
        c.duplicate("faceCombined", name="faceCombinedMirrorDriver")
        c.move(c.getAttr("ctrlBoxOffset.tx") * 2, 0, 0, "faceCombinedMirrorDriver", relative=True)
        c.setAttr("faceCombinedMirrorDriver.sx", -1)
        c.move(source["cheek"][0] * 2.5, 0, 0, "faceCombined", relative=True)
        c.connectAttr(self._original_bs_mesh_shape("faceCombined") + ".outMesh",
                      self._original_bs_mesh_shape("faceCombinedMirrorDriver") + ".inMesh")
        c.blendShape("faceCombinedDefault", "faceCombinedMirrorDriver",
                     name="faceCombinedMirrorDriverBS", frontOfChain=True)

    def _original_bs_mark_tweaked(self, target):
        c = self._cmds
        fit = self._fit(required=True)
        attr = target + "_tweaked"
        if not c.objExists(fit + "." + attr):
            c.addAttr(fit, longName=attr, attributeType="bool", defaultValue=1, keyable=True)
        c.setAttr(fit + "." + attr, 1)

    def adjust_original_face_bs_target(self, source=None, *, auto_mirror=True, multiplier=1):
        self._require_transaction()
        source = source or self.capture_original_face_bs_edit()
        c = self._cmds
        raw = getattr(c, "raw", c)
        self._transaction_changed = True
        targets = list(self.original_face_bs_editable_targets())
        targets.extend(target.replace("_R", "_L", 1) for target in tuple(targets) if target.endswith("_R"))
        dirty = False
        for target in targets:
            if c.getAttr("asFaceBS." + target) == 1 and any(name in target for name in BLENDED_FACE_TARGETS):
                for other in targets:
                    if other != target:
                        c.setAttr("asFaceBS." + other, 0)
                dirty = True
        weights = [(target, float(c.getAttr("asFaceBS." + target))) for target in targets
                   if c.listConnections("asFaceBS." + target, source=True, destination=False,
                                        skipConversionNodes=True, type="animCurve")]
        if not .99 <= sum(value for _, value in weights) <= 1.01:
            raise FitSkeletonValidationError('必须一个目标为 1，其余目标为 0')
        active = [name for name, value in weights if .99 < value < 1.01]
        if not active:
            raise FitSkeletonValidationError("没有完整激活的 BlendShape 目标")
        self._transaction_changed = True
        if c.objExists("deleteThis"):
            c.delete("deleteThis")
        c.createNode("transform", name="deleteThis")
        self._original_bs_mark_tweaked(active[-1])
        if source["half"]:
            self._original_bs_prepare_half_meshes(source)
        edited = []
        for ordinal, geometry in enumerate(source["geos"]):
            bs = "asFaceBS" if ordinal == 0 else "asFaceBS_" + self._original_bs_geo_tag(geometry)
            if not c.objExists(bs):
                continue
            aliases = self.original_face_bs_aliases(bs)
            groups = c.getAttr(bs + ".inputTarget[0].inputTargetGroup", multiIndices=True) or []
            eligible = []
            for index, alias in enumerate(aliases):
                if alias == "FaceJointsLayer" or alias.startswith("UpMidLoLayer") or alias.startswith("weight"):
                    continue
                inputs = c.listConnections(bs + "." + alias, source=True, destination=False, plugs=True,
                                           skipConversionNodes=True) or []
                if ordinal == 0 and not c.listConnections(bs + "." + alias, source=True,
                                           destination=False, type="animCurve", skipConversionNodes=True):
                    continue
                if ordinal and inputs and c.nodeType(inputs[0].split(".",1)[0]) == "blendShape":
                    if not c.listConnections(inputs[0], source=True, destination=False, type="animCurve", skipConversionNodes=True):
                        continue
                eligible.append((index, alias, float(c.getAttr(bs + "." + alias))))
            if sum(value for _, _, value in eligible) < 1:
                continue
            choices = [(index, alias) for index, alias, value in eligible if .99 < value < 1.01]
            if not choices:
                continue
            index, alias = choices[-1]
            original_alias = alias
            if not any(side in alias for side in ("_R", "_L", "_M")):
                c.aliasAttr(alias + "_M", bs + "." + alias)
                alias += "_M"
            name = alias if ordinal == 0 else alias + "_" + self._original_bs_geo_tag(geometry)
            if c.objExists(name):
                raise FitSkeletonValidationError("目标对象已存在：" + name)
            mirrored = original_face_bs_mirror_name(name)
            if "_R" in name:
                self._original_bs_mark_tweaked(mirrored)
            if multiplier != 1:
                c.setAttr(bs + ".weight[" + str(index) + "]", multiplier)
            skin = self.scene_address(source["skin"])
            raw.setAttr(skin + ".envelope", 0)
            self._original_bs_mesh_sample(geometry, name)
            c.addAttr(name, longName="sourceObject", dataType="string")
            c.setAttr(name + ".sourceObject", geometry, type="string")
            raw.setAttr(skin + ".envelope", 1)
            destination = bs + ".inputTarget[0].inputTargetGroup[" + str(groups[index]) + "].inputTargetItem[6000].inputGeomTarget"
            c.connectAttr(self._original_bs_mesh_shape(name) + ".worldMesh[0]", destination, force=True)
            raw.refresh()
            c.move(source["cheek"][0] * 2.5, 0, 0, name, relative=True)
            half = geometry in source["half"]
            if half:
                self._original_bs_native_wrap("faceCombined", name, exclusive=False,
                    name="faceCombinedWrap", add=c.objExists("faceCombinedWrap"))
            if original_alias != alias:
                c.aliasAttr(original_alias, bs + "." + alias)
            if "_R" in name and "_M_" not in name and auto_mirror:
                c.setAttr(bs + ".envelope", 0)
                self._original_bs_mesh_sample(geometry, mirrored)
                c.setAttr(bs + ".envelope", 1)
                c.move(c.getAttr("ctrlBoxOffset.tx") * 2, 0, 0, mirrored, relative=True)
                mirror_driver = "faceCombinedMirrorDriver" if half else mirrored + "MirrorDriver"
                if not half:
                    c.duplicate(mirrored, name=mirror_driver)
                    c.setAttr(mirror_driver + ".sx", -1)
                    c.setAttr(mirror_driver + ".v", 0)
                if c.objExists("faceCombinedMirrorDriverBS"):
                    c.setAttr("faceCombinedMirrorDriverBS.faceCombinedDefault", 1)
                self._original_bs_native_wrap(mirrored, mirror_driver)
                if c.objExists("faceCombinedMirrorDriverBS"):
                    c.setAttr("faceCombinedMirrorDriverBS.faceCombinedDefault", 0)
                if not half:
                    c.connectAttr(self._original_bs_mesh_shape(name) + ".outMesh",
                        self._original_bs_mesh_shape(mirror_driver) + ".inMesh", force=True)
                for other_index, other in enumerate(aliases):
                    if other == mirrored or other + "_" + self._original_bs_geo_tag(geometry) == mirrored:
                        target = bs + ".inputTarget[0].inputTargetGroup[" + str(groups[other_index]) + "].inputTargetItem[6000].inputGeomTarget"
                        c.connectAttr(self._original_bs_mesh_shape(mirrored) + ".worldMesh[0]", target, force=True)
                edited.append(mirrored)
            edited.append(name)
        if dirty:
            raw.dgdirty(allPlugs=True)
        if not edited:
            raise FitSkeletonValidationError("当前完整权重目标没有可提取的几何体")
        c.select("deleteThis" if len(source["geos"]) > 1 else edited[-1], replace=True)
        return tuple(edited)
