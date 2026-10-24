"""Actual native geometry samples and SDK targets, source 43050–43280."""
from contextlib import nullcontext
from adv_py.core.face_blendshape_conversion import (original_face_bs_target_name,
    original_face_bs_driving_value)


from .maya_original_transform_channels import lock_original_transform_channels
from .maya_original_blend_shape import original_front_of_chain_blend_shape

class MayaFaceBSSamplingMixin:
    def _original_face_is_blended_attr(self, control, attr):
        c = self._cmds
        return (not c.getAttr(control + "." + attr, settable=True) and "_" in attr) or (
            self._original_restore_leaf(control).startswith("ctrlMouthCorner_") and
            attr in ("smile", "frown", "narrowSmile", "narrowFrown"))

    def set_original_face_blended_attribute(self, control, attr, value):
        return self.set_original_blended_attribute(control,attr,value)

    def _original_face_bs_front(self, geometry, name):
        c = self._cmds
        raw = getattr(c, "raw", c)
        with c._creation_namespace() if hasattr(c, "_creation_namespace") else nullcontext():
            return original_front_of_chain_blend_shape(raw,
                self.scene_address(geometry), name=self.scene_address(name))

    def _original_face_bs_add_target(self, geometry, node, target):
        raw = getattr(self._cmds, "raw", self._cmds)
        index = int(raw.getAttr(self.scene_address(node) + ".weight", size=True))
        raw.blendShape(self.scene_address(node), edit=True, topologyCheck=False,
                       target=(self.scene_address(geometry), index, self.scene_address(target), 1))
        # Maya may include a model namespace in an automatic target alias.
        # Source procedures subsequently address the original logical name.
        plug = node + ".weight[" + str(index) + "]"
        alias = self._original_restore_leaf(target)
        # Maya already creates this alias for unnamespaced targets. Reapplying
        # it raises "attribute already exists" instead of acting as a no-op.
        if self._cmds.aliasAttr(plug, query=True) != alias:
            self._cmds.aliasAttr(alias, plug)
        return index

    def sample_original_face_bs_targets(self, source, options):
        c = self._cmds
        raw = getattr(c, "raw", c)
        steps = {"_L": 0, "other": 0}
        targets = []
        for control in source["controls"]:
            leaf = self._original_restore_leaf(control)
            side = leaf[-2:]
            user = c.listAttr(control, userDefined=True) or []
            for attr in c.listAttr(control, keyable=True) or []:
                if attr in ("visibility", "jaw", "lip") or c.getAttr(control + "." + attr, lock=True):
                    continue
                for sign in (1, -1):
                    soft = []
                    positive_only = False
                    if attr in user and c.attributeQuery(attr, node=control, softMinExists=True):
                        soft = c.attributeQuery(attr, node=control, softMin=True)
                        positive_only = soft[0] != -10
                    if positive_only and sign == -1:
                        continue
                    limits = c.transformLimits(control, query=True, translationY=True)
                    if attr == "translateY" and sign == -1 and limits[0] == 0:
                        continue
                    key = "_L" if side == "_L" else "other"
                    steps[key] += 1
                    if leaf.startswith("ctrlEye_") and (attr in ("iris", "pupil") or
                            options.keep_joints and attr in ("translateX", "translateY")):
                        continue
                    name = original_face_bs_target_name(leaf, attr, sign, positive_only, attr in user)
                    blended = self._original_face_is_blended_attr(control, attr)
                    value = original_face_bs_driving_value(attr, sign, blended)
                    for index, geometry in enumerate(source["target_geometry"]):
                        bs = "asFaceBS" if index == 0 else "asFaceBS_" + self._original_bs_geo_tag(geometry)
                        if not c.objExists(bs):
                            self._original_face_bs_front(geometry, bs)
                        if blended:
                            self.set_original_face_blended_attribute(control, attr, 1)
                        else:
                            c.setAttr(control + "." + attr, value)
                        raw.refresh()
                        previous = c.objExists(name)
                        if previous:
                            c.rename(name, "tempRenamingBlendShapeTarget")
                        shape = c.createNode("mesh")
                        transform = c.listRelatives(shape, parent=True)[0]
                        c.rename(transform, name)
                        target_shape = c.listRelatives(name, shapes=True)[0]
                        input_shape = raw.listRelatives(self.scene_address(geometry), shapes=True,
                                                       noIntermediate=True, fullPath=True, type="mesh")[0]
                        raw.connectAttr(input_shape + ".outMesh", self.scene_address(target_shape) + ".inMesh")
                        raw.sets(self.scene_address(name), edit=True, forceElement=":initialShadingGroup")
                        raw.refresh()
                        raw.disconnectAttr(input_shape + ".outMesh", self.scene_address(target_shape) + ".inMesh")
                        c.parent(name, "asBlendShapes")
                        self._original_face_bs_add_target(geometry, bs, name)
                        if options.keep_targets:
                            target = name if index == 0 else name + "_" + self._original_bs_geo_tag(geometry)
                            if target != name:
                                c.rename(name, target)
                            if previous:
                                c.rename("tempRenamingBlendShapeTarget", name)
                            lock_original_transform_channels(c, target)
                            c.move(source["cheek_position"][0] * 2.5 * (-1 if side == "_L" else 1) * steps[key],
                                   0, 0, target, relative=True)
                        if blended:
                            self.set_original_face_blended_attribute(control, attr, 0)
                        else:
                            c.setAttr(control + "." + attr, 0)
                        if index:
                            c.connectAttr("asFaceBS." + name, bs + "." + name)
                            # Source continues here; secondary targets remain
                            # until the final asBlendShapes group cleanup.
                            continue
                        plug = bs + "." + name
                        for dv, driven in ((0, 0), (value, 1)):
                            c.setDrivenKeyframe(plug, currentDriver=control + "." + attr,
                                driverValue=dv, value=driven, inTangentType="linear", outTangentType="linear")
                        curve = bs + "_" + name
                        c.setAttr(curve + ".preInfinity", 4)
                        c.setAttr(curve + ".postInfinity", 4)
                        if attr in ("translateX", "translateY") or blended or soft and soft[0] < 0:
                            c.setAttr(curve + (".preInfinity" if sign > 0 else ".postInfinity"), 1 if sign > 0 else 0)
                        if leaf.startswith("ctrlMouthCorner_"):
                            c.connectAttr("bwctrlMouthCorner" + side + "_" + attr + ".output", curve + ".input", force=True)
                        if not options.keep_targets:
                            c.delete(name)
                    targets.append(name)
        return tuple(targets)
