"""Original controller SoftMod edit and per-step completion, 45018–45149."""
from contextlib import contextmanager
import re
from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_softmod_weights import MayaFaceSoftModWeightsMixin
from .maya_face_deformer_sets import original_face_deformer_sets


class MayaFaceSoftModEditMixin(MayaFaceSoftModWeightsMixin):
    @contextmanager
    def _original_face_softmod_sets(self):
        with original_face_deformer_sets(self._cmds):
            yield

    def _original_face_falloff_commands(self, text):
        """Read generated falloff setAttr data without evaluating MEL code."""
        rows = []
        for command in (text or "").split(";"):
            if not command.strip():
                continue
            tokens = command.split()
            if len(tokens) != 3 or tokens[0] != "setAttr" or not re.fullmatch(
                    r"TempSoftMod\.falloffCurve\[\d+\]\.falloffCurve_(Position|Interp|FloatValue)", tokens[1]):
                raise FitSkeletonValidationError("falloffCurve 不是原版数值衰减曲线记录")
            value = int(tokens[2]) if tokens[1].endswith("_Interp") else float(tokens[2])
            rows.append((tokens[1].split(".", 1)[1], value))
        return rows

    def convert_original_face_control_to_softmod(self, control):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        leaf = self._original_restore_leaf(control)
        name, side = leaf.rsplit("_", 1)
        fit = self._fit(required=True)
        non_sym = bool(c.objExists(fit + ".NonSym") and c.getAttr(fit + ".NonSym"))
        if side == "L" and not non_sym:
            raise FitSkeletonValidationError("对称 Face 只允许编辑右侧控制器")
        if c.ls("convertedSoftModHandle_*", type="transform"):
            raise FitSkeletonValidationError("已有控制器处于 SoftMod 编辑，请先完成")
        if not c.sets(control, isMember="FaceControlSet"):
            raise FitSkeletonValidationError("所选对象不属于 FaceControlSet")
        radius = c.getAttr(name + ".falloffRadius") if c.objExists(name + ".falloffRadius") else c.getAttr(control + ".falloffRadius") if c.objExists(control + ".falloffRadius") else 1
        mode = c.getAttr(name + ".falloffMode") if c.objExists(name + ".falloffMode") else 1
        curve = self._original_face_falloff_commands(c.getAttr(name + ".falloffCurve")) if c.objExists(name + ".falloffCurve") else []
        geometry = self.read_face_objects(FacePreRole.FACE)[0]
        skin = self.face_skin_cluster(geometry)
        time = c.currentTime(query=True)
        selection = tuple(raw.ls(selection=True) or [])
        c.currentTime(0)
        values = {attr: tuple(c.getAttr(control + "." + attr)[0]) for attr in ("t", "r", "s")}
        c.xform(control, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1))
        raw.setAttr(self.scene_address(skin) + ".envelope", 0)
        position = c.xform(control, query=True, worldSpace=True, translation=True)
        with self._original_face_softmod_sets(), c._creation_namespace():
            soft, handle = raw.softMod(self.scene_address(geometry))
        soft = c.rename(soft, "convertedSoftMod_" + leaf)
        handle = c.rename(handle, "convertedSoftModHandle_" + leaf)
        sets = c.listConnections(soft + ".message", type="objectSet") or []
        if sets:
            c.rename(sets[0], "convertedSoftModSet_" + leaf)
        c.setAttr(soft + ".falloffRadius", radius)
        c.setAttr(soft + ".falloffMode", mode)
        c.setAttr(handle + "Shape.origin", *position, type="float3")
        c.setAttr(soft + ".falloffCenter", *position)
        c.xform(handle, pivots=position)
        target = name if c.objExists(name + ".falloffRadius") else control
        if c.objExists(target + ".falloffRadius"):
            c.connectAttr(soft + ".falloffRadius", target + ".falloffRadius")
        for attribute, value in curve:
            c.setAttr(soft + "." + attribute, value)
        for command in (c.parentConstraint, c.scaleConstraint):
            constraint = command(control, handle, maintainOffset=True)[0]
            c.setAttr(constraint + ".isHistoricallyInteresting", 0)
        if not non_sym:
            for attr, value in values.items():
                c.setAttr(control + "." + attr, *value, type="float3")
        c.sets(control + ".cv[0:999]", add="convertedSoftModSet_" + leaf)
        raw.percent(self.scene_address(soft), self.scene_address(control) + ".cv[0:999]", value=0)
        if not c.objExists(control + ".falloffRadius"):
            c.addAttr(control, longName="falloffRadius", attributeType="double", defaultValue=radius, keyable=True)
        c.connectAttr(control + ".falloffRadius", soft + ".falloffRadius")
        c.currentTime(time)
        raw.select(selection, replace=True)
        self._transaction_changed = True
        return handle

    def restore_original_face_softmod_layer(self, fit_loc, name, side, radius):
        """SoftModLayerWeight's returning-from-edit branch, 45806–45916."""
        c = self._cmds
        raw = getattr(c, "raw", c)
        fit = self._fit(required=True)
        geometry = self.read_face_objects(FacePreRole.FACE)[0]
        head = c.getAttr(fit + ".HeadJoint")
        skin = self.face_skin_cluster(geometry)
        control = name + side
        joint = name + "Joint" + side
        if c.objExists("SoftModLayer"):
            c.delete("SoftModLayer")
        c.duplicate("templateLayer", name="SoftModLayer")
        c.skinCluster(head, "SoftModLayer", toSelectedBones=True, maximumInfluences=3,
                      dropoffRate=4, removeUnusedInfluence=False, name="SoftModSC")
        values = {attr: tuple(c.getAttr(control + "." + attr)[0]) for attr in ("t", "r", "s")}
        c.xform(control, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1))
        position = c.xform(fit_loc, query=True, worldSpace=True, translation=True)
        c.skinCluster("SoftModSC", edit=True, dropoffRate=4, lockWeights=False, weight=0, addInfluence=joint)
        try:
            raw.skinPercent(self.scene_address(skin), self.scene_address(geometry), transformValue=((self.scene_address(joint), 0),))
        except RuntimeError:
            pass
        if radius > 0:
            self.weight_original_face_by_softmod(joint, "SoftModLayer", "SoftModSC", radius, 1)
        if c.objExists("asSkinWeightExludeSet"):
            vertices = []
            members = c.sets("asSkinWeightExludeSet", query=True) or []
            converted = raw.polyListComponentConversion([self.scene_address(item) for item in members], toVertex=True) or [] if members else []
            for member in raw.ls(converted, flatten=True) or []:
                if ".vtx[" in member:
                    vertices.append("SoftModLayer." + member.split(".", 1)[1])
            if vertices:
                c.skinPercent("SoftModSC", vertices, transformValue=((head, 1),))
        raw.select(self.scene_address(geometry), replace=True)
        raw.polySelectConstraint(mode=3, type=1, dist=1, distbound=(0, radius), distpoint=position)
        raw.polySelectConstraint(mode=0)
        vertices = tuple(raw.ls(selection=True, flatten=True) or [])
        c.select(clear=True)
        numbers, weights = [], []
        for vertex in vertices:
            component = vertex.split(".", 1)[1]
            numbers.append(int(component.removeprefix("vtx[").removesuffix("]")))
            weights.append(c.skinPercent("SoftModSC", "SoftModLayer." + component, query=True, transform=joint))
        self.set_original_face_joint_weights(joint, geometry, skin, numbers, weights)
        c.delete("convertedSoftModHandle_" + name + side)
        for attr, kind, default, extra in (("falloffRadius", "double", 1, {}),
                ("falloffMode", "enum", 1, {"enumName": "volume:surface:"}), ("type", "bool", 1, {})):
            if not c.objExists(fit_loc + "." + attr):
                c.addAttr(fit_loc, longName=attr, attributeType=kind, defaultValue=default, keyable=True, **extra)
        c.setAttr(fit_loc + ".falloffRadius", radius)
        c.setAttr(fit_loc + ".falloffMode", 1)
        non_sym = bool(c.objExists(fit + ".NonSym") and c.getAttr(fit + ".NonSym"))
        if not non_sym:
            for attr, value in values.items():
                c.setAttr(control + "." + attr, *value, type="float3")
        return len(vertices)

    def convert_original_face_softmod_to_control(self, handle):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        raw.setToolTo("selectSuperContext")
        leaf = self._original_restore_leaf(handle)
        if not leaf.startswith("convertedSoftModHandle_"):
            raise FitSkeletonValidationError("必须选择 convertedSoftModHandle")
        name, side = leaf.removeprefix("convertedSoftModHandle_").rsplit("_", 1)
        side = "_" + side
        fit = self._fit(required=True)
        non_sym = bool(c.objExists(fit + ".NonSym") and c.getAttr(fit + ".NonSym"))
        fit_loc = name + "Left" if non_sym and side == "_L" else name
        time = c.currentTime(query=True)
        c.currentTime(0)
        radius = c.getAttr(fit_loc + ".falloffRadius")
        self._original_prefix_lock_joints(True)
        c.setAttr(c.getAttr(fit + ".HeadJoint") + ".lockInfluenceWeights", False)
        count = self.restore_original_face_softmod_layer(fit_loc, name, side, radius)
        geometry = self.read_face_objects(FacePreRole.FACE)[0]
        raw.setAttr(self.scene_address(self.face_skin_cluster(geometry)) + ".envelope", 1)
        # Preserve source's fitLoc-based cleanup, including its NonSym naming.
        if c.objExists(fit_loc + side + ".falloffRadius"):
            c.deleteAttr(fit_loc + side + ".falloffRadius")
        c.currentTime(time)
        c.select(clear=True)
        self._transaction_changed = True
        return count

    def complete_original_face_softmod_edits(self):
        """asConvertAllSoftModBackToControl, including NonSym left replay."""
        c = self._cmds
        raw = getattr(c, "raw", c)
        time = c.currentTime(query=True)
        selection = tuple(raw.ls(selection=True) or [])
        fit = self._fit(required=True)
        non_sym = bool(c.objExists(fit + ".NonSym") and c.getAttr(fit + ".NonSym"))
        count = 0
        for handle in tuple(c.ls("convertedSoftModHandle_*", assemblies=True) or []):
            leaf = self._original_restore_leaf(handle)
            self.convert_original_face_softmod_to_control(handle)
            count += 1
            if non_sym and leaf.endswith("_R"):
                name = leaf.removeprefix("convertedSoftModHandle_").removesuffix("_R")
                c.setAttr(name + "Left.falloffRadius", c.getAttr(name + ".falloffRadius"))
                mirrored = self.convert_original_face_control_to_softmod(name + "_L")
                self.convert_original_face_softmod_to_control(mirrored)
                count += 1
        c.currentTime(0)
        if not non_sym:
            geometry = self.read_face_objects(FacePreRole.FACE)[0]
            skin = self.scene_address(self.face_skin_cluster(geometry))
            raw.copySkinWeights(sourceSkin=skin, destinationSkin=skin, mirrorMode="YZ", mirrorInverse=True,
                               surfaceAssociation="closestPoint", influenceAssociation="closestJoint")
        c.currentTime(time)
        raw.select(selection, replace=True)
        return count
