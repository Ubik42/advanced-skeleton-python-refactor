"""Native port of the Mixed Face skin attachers, MEL 43800–44055."""
from contextlib import nullcontext
from fnmatch import fnmatchcase


class MayaFaceBSAttachersMixin:
    def _original_bs_remove_transform_shell(self, node):
        c = self._cmds
        incoming = c.listConnections(node + ".offsetParentMatrix", source=True, destination=False, plugs=True) or []
        for plug in incoming:
            c.disconnectAttr(plug, node + ".offsetParentMatrix")
        if incoming:
            c.setAttr(node + ".offsetParentMatrix", 1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1, type="matrix")
        constraints = c.listRelatives(node, children=True, type="constraint") or []
        if constraints:
            c.delete(constraints)
        children = c.listRelatives(node, children=True, type="transform") or []
        if children:
            c.parent(children, (c.listRelatives(node, parent=True) or [])[0])
        c.delete(node)

    def _connect_original_bs_control_channels(self, control, layered):
        """MEL 43911–43913 connections with reversible native lock ownership.

        SmilePull keeps locked TRS children. A compound connection can be
        created across those locks, but its native Undo cannot disconnect it.
        Journal temporary unlocks before the connection and restore each
        original lock afterwards; both final graph and channel locks match.
        """
        c = self._cmds
        for channel in ("t", "r", "s"):
            destination = layered + "." + channel
            plugs = (destination, *(destination + axis for axis in "xyz"))
            locked = tuple(plug for plug in plugs if c.getAttr(plug, lock=True))
            for plug in locked:
                c.setAttr(plug, lock=False)
            try:
                c.connectAttr(control + "." + channel, destination)
            finally:
                for plug in reversed(locked):
                    c.setAttr(plug, lock=True)

    def create_original_face_bs_attachers(self, source):
        c = self._cmds
        raw = getattr(c, "raw", c)
        c.createNode("transform", name="SkinAttachCtrls", parent="FaceDeformationSystem")
        c.setAttr("SkinAttachCtrls.v", 0, lock=True)
        items = [node for node in c.listRelatives("FaceJoint_M", children=True, type="joint") or []
                 if node not in ("EyeLidJoints_M", "LipJoints_M")]
        for root in ("LidJoints", "LipRibbonJoints"):
            items.extend(node for node in c.listRelatives(root, allDescendents=True, type="joint") or []
                         if node not in ("EyeRegionJoint_R", "EyeRegionJoint_L"))
        items.extend(("LipJoint_R", "LipJoint_L", "upperLip_M", "lowerLip_M"))
        tack = ("EyeBrowRegion_R", "EyeBrowRegion_L", "EyeRegion_R", "EyeRegion_L",
                "NoseRegion_M", "LipRegion_M", "SmilePull_R", "SmilePull_L",
                "upperLip_R", "lowerLip_R", "upperLip_L", "lowerLip_L",
                "upperFace_M", "middleFace_M", "lowerFace_M")
        items.extend(node for node in tack if c.objExists(node))
        points, attachers = [], []
        opm = self.face_use_offset_parent_matrix()
        position = (0, 0, 0)
        for item in items:
            item = item.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if item in ("Tongue0Joint_M", "LipJoints_M", "JawJoint_M", "upperTeethJoint_M", "lowerTeethJoint_M",
                        "upperFaceJoint_M", "middleFaceJoint_M", "lowerFaceJoint_M"):
                continue
            if fnmatchcase(item, "EyeJoint_*") or fnmatchcase(item, "Tongue*Joint_M"):
                continue
            stem, suffix = item.rsplit("_", 1)
            stem = stem.replace("Joint", "", 1).replace("Ribbon", "", 1)
            side = "_" + suffix
            control, attacher, attach = stem + side, stem + "Attacher" + side, stem + "Attach" + side
            c.createNode("transform", name=attacher, parent="SkinAttachCtrls")
            if c.objExists(item):
                position = c.xform(item, query=True, worldSpace=True, translation=True)
            reference = None
            if any(fnmatchcase(item, pattern) for pattern in ("EyeRegion_*", "Eye_*", "Iris_*", "Pupil_*")):
                reference = "innerLidJoint" + side
            if fnmatchcase(item, "*LipJoint_*"):
                reference = control
            reference = {"upperLip_M": "upperLipOuterCurve.cv[0]", "lowerLip_M": "lowerLipOuterCurve.cv[0]",
                         "NoseRegion_M": "NoseJoint_M", "LipRegion_M": "upperLipOuterCurve.cv[0]",
                         "upperTeeth_M": "upperLipOuterCurve.cv[0]", "lowerTeeth_M": "lowerLipOuterCurve.cv[0]",
                         "Jaw_M": "Jaw", "upperFace_M": "EyeBrowCenterJoint_M",
                         "middleFace_M": "NoseUnderJoint_M"}.get(item, reference)
            if fnmatchcase(item, "Tongue*_M"):
                reference = "lowerLipOuterCurve.cv[0]"
            if reference:
                position = c.xform(reference, query=True, worldSpace=True, translation=True)
            points.append(tuple(position))
            attachers.append(attacher)
            if c.objExists(attach):
                self._original_bs_remove_transform_shell(attach)
                self._original_bs_delete_existing((stem + "AttachMM" + side,))
            c.createNode("transform", name=attach, parent="SideReverseLayered" + side)
            if opm:
                self.constrain_original_face(attacher, attach, opm=True, pick=True)
                for attr in ("useRotate", "useScale", "useShear"):
                    c.setAttr(stem + "AttachPM" + side + "." + attr, 0)
            else:
                c.pointConstraint(attacher, attach)
            offset, layered = stem + "Offset" + side, stem + "Layered" + side
            c.rename(offset, stem + "OffsetLayered" + side)
            c.createNode("transform", name=offset, parent=attach)
            c.delete(c.orientConstraint(control, offset))
            subtract = stem + "Subtract" + side
            if c.objExists(subtract):
                self._original_bs_remove_transform_shell(subtract)
            c.createNode("transform", name=subtract, parent=offset)
            c.rename(control, layered)
            c.sets(layered, remove="FaceControlSet")
            c.createNode("transform", name=control, parent=subtract)
            c.sets(control, add="FaceControlSet")
            self._connect_original_bs_control_channels(control, layered)
            shapes = c.listRelatives(layered, shapes=True, fullPath=True) or []
            for shape in shapes:
                c.parent(shape, control, add=True, shape=True)
            original_shape = layered + "|" + layered + "Shape"
            c.parent(original_shape, removeObject=True, shape=True)
            c.rename(layered + "Shape", control + "Shape")
            remaining = c.listRelatives(layered, shapes=True, noIntermediate=True) or []
            instanced = bool(remaining and len(c.listRelatives(remaining[0], allParents=True) or []) > 1)
            if not instanced:
                from .maya_native_node_cast import native_node_cast
                native_node_cast(self, layered, control, swap_names=True)
            if item not in ("upperTeeth_M", "lowerTeeth_M", "Tongue0_M", "upperFace_M", "middleFace_M", "lowerFace_M"):
                multiply = c.createNode("multiplyDivide", name=stem + "SubtractMultiplyDivide" + side)
                c.setAttr(multiply + ".input2", -1, -1, -1, type="float3")
                c.connectAttr(control + ".t", multiply + ".input1")
                c.connectAttr(multiply + ".output", subtract + ".t")
        curve = c.curve(degree=1, point=points, name="AttacherCurve")
        c.rename((c.listRelatives(curve, shapes=True) or [])[0], "AttacherCurveShape")
        c.parent(curve, "SkinAttachCtrls")
        c.setAttr("AttacherCurveShape.dispGeometry", 0)
        for index, attacher in enumerate(attachers):
            node = c.createNode("pointOnCurveInfo", name="AttacherCurvePoci" + attacher)
            c.connectAttr("AttacherCurve.worldSpace[0]", node + ".inputCurve", force=True)
            c.setAttr(node + ".turnOnPercentage", 0)
            c.setAttr(node + ".parameter", index)
            c.connectAttr(node + ".position", attacher + ".t", force=True)
        # AddWrapInfluence is Maya's native wrap command, not an ADV procedure.
        from maya import mel
        with c._creation_namespace() if hasattr(c, "_creation_namespace") else nullcontext():
            wrap = raw.deformer(self.scene_address(curve), type="wrap", name="SkinAttachCtrlsWrap")[0]
            for attr, value in (("weightThreshold", 0), ("maxDistance", 0), ("exclusiveBind", 1),
                                ("autoWeightThreshold", 0), ("falloffMode", 0)):
                raw.setAttr(wrap + "." + attr, value)
            raw.select((self.scene_address(curve), self.scene_address(source["geometry"])), replace=True)
            mel.eval("AddWrapInfluence;")
        for control in tack:
            if not c.objExists(control):
                continue
            stem, suffix = control.rsplit("_", 1)
            side = "_" + suffix
            factor = source["ctrl_scale"]
            a = c.xform(stem + "OffsetLayered" + side, query=True, worldSpace=True, translation=True)
            b = c.xform(stem + "Attach" + side, query=True, worldSpace=True, translation=True)
            delta = tuple((a[i] - b[i]) / factor * (-1 if i == 0 and side == "_R" else 1) for i in range(3))
            if opm:
                c.setAttr(stem + "AttachMM" + side + ".matrixIn[2]", 1,0,0,0,0,1,0,0,0,0,1,0,*delta,1, type="matrix")
            else:
                c.setAttr(stem + "Attach" + side + "_pointConstraint1.offset", *delta, type="float3")
        for stem in ("EyeBrowRegion", "EyeRegion", "NoseRegion", "LipRegion", "upperFace", "middleFace", "lowerFace"):
            for side in ("_R", "_L", "_M"):
                if c.objExists(stem + side):
                    c.setAttr(stem + "Layered" + side + ".v", 0, lock=True)
                    c.connectAttr(stem + side + ".worldMatrix", stem + "MM" + side + "TGXform.matrixIn[0]", force=True)
        if c.objExists("Tongue0FollowDM_M"):
            self._original_bs_delete_existing(("Tongue0FollowDM_M", "lowerTeethFollowDM_M"))
        if c.objExists("Tongue0BM_M"):
            self._original_bs_delete_existing(("Tongue0BM_M", "lowerTeethBM_M"))
        if c.objExists("Tongue0Offset_M"):
            c.parent("lowerTeethOffset_M", "Tongue0Offset_M", "Jaw_M")
        for control in ("Tongue0_M", "lowerTeeth_M"):
            if c.objExists(control + ".followJawFollow_M"):
                c.deleteAttr(control + ".followJawFollow_M")
        for side in ("_R", "_L"):
            c.parent("SmilePullOffset" + side, "SideReverseLayered" + side)
        if c.objExists("EyeBase_R"):
            for side in ("_R", "_L"):
                parent = "EyeRegionOffsetLayered" + side
                c.parent(parent, "SideReverse" + side)
                node = c.createNode("transform", name="EyeRegionFromEyeBase" + side, parent=parent)
                for attr in ("t", "r", "s"):
                    c.connectAttr("EyeBase" + side + "." + attr, node + "." + attr)
                c.parent("SDKEyeRegion" + side, node)
        constraints = c.listRelatives("FaceJoint_M", allDescendents=True, type="constraint") or []
        if constraints:
            c.parent(constraints, "DeformJointConstraints")
        for side in ("_R", "_L"):
            c.parent("SmilePullOffset" + side, "LipAttach" + side)
