"""asFaceRebuildRestore user attributes, shapes and orientation, 40212–40558."""
import re
from adv_py.adapters.maya_deform_skinning import freeze_native_skin_cluster


class MayaFaceRestoreControlsMixin:
    @staticmethod
    def _original_restore_leaf(node):
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def restore_original_face_user_attributes(self):
        c = self._cmds
        for previous in c.sets("prefix_FaceControlSet", query=True) or []:
            control = self._original_restore_leaf(previous).replace("prefix_", "", 1)
            if not c.objExists(control):
                continue
            for attribute in c.listAttr(previous, userDefined=True) or []:
                plug = previous + "." + attribute
                short = (c.listAttr(plug, shortNames=True) or [attribute])[0]
                kind = c.getAttr(plug, type=True)
                if kind == "float":
                    kind = "double"
                if kind.endswith("Array") or kind in ("message", "string") or re.fullmatch(r".*W[0-9]", attribute):
                    continue
                if control in ("AimEye_R", "AimEye_L") and attribute == "follow":
                    continue
                if c.objExists(control + "." + attribute):
                    continue
                flags = {"shortName": short, "longName": attribute, "attributeType": kind,
                         "defaultValue": c.getAttr(plug), "keyable": c.getAttr(plug, keyable=True)}
                if c.attributeQuery(attribute, node=previous, rangeExists=True):
                    low, high = c.attributeQuery(attribute, node=previous, range=True)
                    flags.update(hasMinValue=True, minValue=low, hasMaxValue=True, maxValue=high)
                if c.attributeQuery(attribute, node=previous, softRangeExists=True):
                    low, high = c.attributeQuery(attribute, node=previous, softRange=True)
                    flags.update(softMinValue=low, hasSoftMinValue=True,
                                 softMaxValue=high, hasSoftMaxValue=True)
                if kind == "enum":
                    flags["enumName"] = c.addAttr(plug, query=True, enumName=True)
                c.addAttr(control, **flags)
                marker = control + "_" + short + "_tweaked"
                if not c.objExists("prefix_FaceSetupEditHistory"):
                    c.createNode("transform", name="prefix_FaceSetupEditHistory", parent="prefix_ControlsSetup")
                if not c.objExists("prefix_FaceSetupEditHistory." + marker):
                    c.addAttr("prefix_FaceSetupEditHistory", longName=marker, attributeType="bool", defaultValue=True)
        if c.objExists("prefix_FaceSetupEditHistory"):
            c.parent("prefix_FaceSetupEditHistory", "ControlsSetup")
            c.rename("prefix_FaceSetupEditHistory", "FaceSetupEditHistory")
            c.sets("FaceSetupEditHistory", remove="prefix_FaceAllSet")
            c.sets("FaceSetupEditHistory", add="FaceAllSet")

    def restore_original_face_control_shapes(self, controls):
        c = self._cmds
        commands = []
        for control in controls:
            if not c.objExists(control):
                continue
            previous_control="prefix_"+self._original_restore_leaf(control)
            previous_shapes=c.listRelatives(previous_control,shapes=True,
                fullPath=True,type="nurbsCurve") or [] if c.objExists(previous_control) else []
            current_shapes=c.listRelatives(control,shapes=True,
                fullPath=True,type="nurbsCurve") or []
            for shape in current_shapes:
                current = self._original_restore_leaf(shape)
                matches=[candidate for candidate in previous_shapes
                    if self._original_restore_leaf(candidate)=="prefix_"+current]
                # Older Python slider templates had anonymous, unstable Shape
                # names. Their sole curve is unambiguous under the old control.
                if not matches and len(previous_shapes)==len(current_shapes)==1:
                    old_leaf=self._original_restore_leaf(previous_shapes[0])
                    if re.fullmatch(r"prefix_curveShape\d*",old_leaf):
                        matches=previous_shapes
                if len(matches)!=1:
                    continue
                previous=matches[0]
                if c.getAttr("prefix_FaceGroup.version") < 5.764 and current.startswith(("Iris_", "Pupil_")):
                    continue
                # Source skips every shape on this first rebuild after the
                # JawPull addition, despite its comment naming just Jaw_M.
                if c.objExists("prefix_Jaw_M") and not c.objExists("prefix_JawPull_M"):
                    continue
                count = int(c.getAttr(previous + ".spans")) + int(c.getAttr(previous + ".degree"))
                for index in range(count):
                    value = c.getAttr(previous + f".controlPoints[{index}]")[0]
                    commands.append((shape + f".controlPoints[{index}]", tuple(value)))
                commands.append((shape + ".overrideColor", (c.getAttr(previous + ".overrideColor"),)))
        for plug, values in commands:
            try:
                c.setAttr(plug, *values)
            except RuntimeError:
                raw = getattr(c, "raw", c)
                raw.warning("恢复控制器形状失败：" + plug)

    def restore_original_face_custom_orient(self, controls):
        c = self._cmds
        restored = False
        for control in controls:
            leaf = self._original_restore_leaf(control)
            if not c.objExists(control) or not c.objExists("prefix_" + leaf):
                continue
            if not c.listRelatives(control, shapes=True):
                continue
            tokens = leaf.split("_")
            name, side = tokens[0], "_" + tokens[1]
            custom = name + "CustomOrient" + side
            if not c.objExists("prefix_" + custom):
                continue
            c.createNode("transform", name=custom, parent="prefix_" + custom)
            previous_parent = c.listRelatives("prefix_" + custom, parent=True)[0]
            parent = self._original_restore_leaf(previous_parent).replace("prefix_", "", 1)
            children = c.listRelatives(parent, children=True, type="transform") or []
            c.parent(custom, parent)
            if children:
                c.parent(children, custom, relative=True)
            restored = True
        if restored:
            self.attach_original_face_restored_controllers()
        return restored

    def attach_original_face_restored_controllers(self):
        """Reuse the native attach graph inside the enclosing rebuild undo."""
        c = self._cmds
        raw = getattr(c, "raw", c)
        controls = self._face_control_members()
        selection = tuple(raw.ls(selection=True) or [])
        self._mirror_face_control_values(controls)
        for control in controls:
            leaf = self._original_restore_leaf(control)
            if not leaf.startswith(("Iris_", "Pupil_")):
                self._attach_orient_control(leaf)
        # asGetSkinCluster chooses the final history Skin; keep this policy
        # for the multi-Skin branch instead of requiring a single Skin.
        for mesh in self._all_head_meshes():
            skin = self.original_face_bs_skin(mesh)
            freeze_native_skin_cluster(skin)
            raw.setAttr(skin + ".envelope", 1)
        if c.objExists("FaceJointsLayer") and c.objExists("asFaceBS"):
            for mesh in c.listRelatives("FaceJointsLayer", children=True) or []:
                skin = self.original_face_bs_skin(mesh)
                freeze_native_skin_cluster(skin)
        raw.dgdirty(allPlugs=True)
        raw.select([item for item in selection if raw.objExists(item)], replace=True)
