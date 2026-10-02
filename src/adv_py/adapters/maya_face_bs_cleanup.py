"""Original post-sampling joint/SDK cleanup and conversion finalization."""
from fnmatch import fnmatchcase


from .maya_original_skin_history import remove_unused_for_skin

class MayaFaceBSCleanupMixin:
    def _original_bs_delete_existing(self, nodes):
        found = [node for node in nodes if self._cmds.objExists(node)]
        if found:
            self._cmds.delete(found)

    def remove_original_face_bs_driving_graph(self, source, options):
        c = self._cmds
        raw = getattr(c, "raw", c)
        if options.keep_joints:
            c.parent("JawSetup", "FaceDeformationSystem")
            self._original_bs_delete_existing(("JawFollowMM_M",))
            c.setAttr("ctrlMouth_M.ty", -1)
            for follow in ("lowerTeethFollow_M", "Tongue0Follow_M"):
                if c.objExists(follow):
                    parent = c.listRelatives(follow, parent=True)[0]
                    c.createNode("transform", name="tempMatrixTransform", parent=follow)
                    c.parent("tempMatrixTransform", parent)
                    c.getAttr("tempMatrixTransform.t")
                    c.getAttr("tempMatrixTransform.r")
                    c.delete("tempMatrixTransform")
            c.setAttr("ctrlMouth_M.ty", 0)
            raw.dgdirty(allPlugs=True)
            raw.refresh()
            patterns = ("SDKEye_*", "SDKIris_*", "SDKPupil_*")
            for kind, pattern, prefix in (("blendWeighted", "bwSDK*_*_*", "bw"), ("animCurve", "SDK*_*_*", "")):
                for node in c.ls(pattern, type=kind) or []:
                    leaf = self._original_restore_leaf(node)
                    if c.sets(node, isMember="FaceAllSet") and not any(fnmatchcase(leaf, prefix + p) for p in patterns):
                        c.delete(node)
            for node in c.ls("*LipJoint*_*RollPMA") or []:
                if c.sets(node, isMember="FaceAllSet"):
                    c.delete(node)
            self._original_bs_delete_existing(("bwctrlEye_R_blink", "bwctrlEye_L_blink"))
        else:
            # asFaceToBlendShapes repeats the flood and influence removal for
            # each sampled control. Preserve the source mutation order.
            for control in source["controls"]:
                for geometry in source["target_geometry"]:
                    if geometry == source["geometry"]:
                        continue
                    skin = self.original_face_bs_skin(geometry)
                    try:
                        raw.skinPercent(skin, self.scene_address(geometry), transformValue=((self.scene_address(source["head"]), 1),))
                    except RuntimeError:
                        pass
                    remove_unused_for_skin(raw, skin)
            skin = self.scene_address(source["skin"])
            for joint in raw.listConnections(skin + ".matrix") or []:
                raw.setAttr(joint + ".liw", True)
            raw.setAttr(self.scene_address(source["head"]) + ".lockInfluenceWeights", False)
            for joint in c.listRelatives("FaceJoint_M", children=True, type="joint") or []:
                if self._original_restore_leaf(joint) not in ("EyeJoint_R", "EyeJoint_L"):
                    c.delete(joint)
            raw.skinPercent(skin, self.scene_address(source["geometry"]), transformValue=((self.scene_address(source["head"]), 1),))
            for joint in raw.listConnections(skin + ".matrix") or []:
                raw.setAttr(joint + ".liw", False)
            groups = ["SideReverse_R", "SideReverse_L", "SideReverse_M"]
            if c.objExists("upperFace_M"):
                groups += [stem + "SideReverse" + side for stem in ("upper", "middle", "lower") for side in ("_R", "_L", "_M")]
                c.setAttr("ctrlBox.UpMidLoCtrlVis", False)
            for group in groups:
                for child in c.listRelatives(group, children=True, type="transform") or []:
                    if self._original_restore_leaf(child) not in ("EyeOffset_R", "EyeOffset_L") and c.objExists(child):
                        c.delete(child)
        weighted = []
        if c.objExists("ctrlEmotions_M"):
            weighted += c.listConnections("ctrlEmotions_M", source=False, destination=True, type="blendWeighted") or []
        if c.objExists("ctrlARKit_M"):
            for bw in c.listConnections("ctrlARKit_M", source=False, destination=True, type="blendWeighted") or []:
                leaf = self._original_restore_leaf(bw)
                if not leaf.startswith("bwctrlARKit_M_eyeLook") and leaf != "bwctrlARKit_M_tongueOut":
                    weighted.append(bw)
        for bw in weighted:
            for curve in c.listConnections(bw, source=False, destination=True, type="animCurve") or []:
                if c.sets(curve, isMember="FaceAllSet") and not self._original_restore_leaf(curve).startswith("bwctrlMouth_M_translateY"):
                    c.delete(curve)
        if not source["use_skin_layers"]:
            for child in c.listRelatives("FaceDeformationSystem", children=True, type="transform") or []:
                if self._original_restore_leaf(child) != "EyeSetup":
                    c.delete(child)

    def finish_original_face_bs_conversion(self, source, options, before, envelopes):
        c = self._cmds
        raw = getattr(c, "raw", c)
        if c.objExists("ctrlPhonemes_M") and c.objExists("bwctrlPhonemes_M_lip"):
            c.setAttr("ctrlPhonemes_M.lip", 0, lock=True, keyable=False)
            c.setAttr("ctrlPhonemes_M.jaw", 1, lock=True, keyable=False)
            c.setAttr("ctrlPhonemes_M.multipliers", keyable=False)
        if options.keep_joints:
            for side in ("_R", "_L"):
                if c.objExists("EyeJointMM" + side):
                    c.connectAttr("FaceDeformationFollowHead.worldInverseMatrix[0]", "EyeJointMM" + side + ".matrixIn[1]", force=True)
            for stem in ("upper", "middle", "lower"):
                if c.objExists(stem + "FaceOffset_M") and c.objExists("SideReverseLayered_M"):
                    c.parent(stem + "FaceOffset_M", "SideReverseLayered_M")
                    c.delete(stem + "FaceAttach_M")
        if not options.keep_targets and c.objExists("asBlendShapes"):
            c.delete("asBlendShapes")
        for plug, value in envelopes:
            if raw.objExists(plug + ".envelope"):
                raw.setAttr(plug + ".envelope", value)
        right_eye = self.read_original_face_parts("RightEye")
        if right_eye and self._original_bs_physical_address(right_eye[0]).startswith(source["geometry"] + ".") and c.objExists("ctrlARKit_M"):
            for label in ("Left", "Right"):
                for action in ("Up", "Down", "Out", "In"):
                    curves = c.listConnections("bwctrlARKit_M_eyeLook" + action + label,
                                               source=False, destination=True, type="animCurve") or []
                    if curves:
                        c.delete(curves)
        tongue = self.read_original_face_parts("Tongue")
        if tongue and self._original_bs_physical_address(tongue[0]).startswith(source["geometry"] + ".") and c.objExists("ctrlARKit_M") and c.objExists("SDKJaw_M"):
            nodes = c.listConnections("SDKJaw_M", source=True, destination=False, type="blendWeighted", skipConversionNodes=True) or []
            if nodes:
                c.delete(nodes)
        for geometry in source["all_head"]:
            skin = self.original_face_bs_skin(geometry)
            try:
                raw.skinPercent(skin, self.scene_address(geometry), normalize=True)
            except RuntimeError:
                pass
        for node in c.listHistory("asFaceBS") or []:
            if c.nodeType(node).startswith("animCurve") and not c.listConnections(node, source=True, destination=False):
                c.delete(node)
        for curve in c.listConnections("asFaceBS", source=True, destination=False, type="animCurve") or []:
            for bw in c.listConnections(curve, source=True, destination=False, type="blendWeighted") or []:
                pairs = c.listConnections(bw, source=True, destination=False, plugs=True, connections=True) or []
                for index in range(2, len(pairs), 2):
                    c.disconnectAttr(pairs[index + 1], pairs[index])
        generated = []
        for node in c.ls(objectsOnly=True) or []:
            if c.nodeType(node) in ("objectSet", "partition"):
                continue
            if not before.intersection(c.ls(node, uuid=True) or []):
                generated.append(node)
        if generated:
            c.sets(generated, add="FaceAllSet")
        c.sets(clear="allBeforeConvertToBS")
        c.delete("allBeforeConvertToBS")
        self._write_face_pose_numeric_rows(self._face_pose_rows(c.sets("FaceControlSet", query=True) or []))
        if c.objExists("OnFacecontrolsLayered") and c.objExists("squashFfd"):
            for shape in c.listRelatives("OnFacecontrolsLayered", allDescendents=True, noIntermediate=True, type="nurbsCurve") or []:
                control = c.listRelatives(shape, parent=True)[0]
                if c.objExists(control + "TG"):
                    continue
                inputs = c.listConnections(shape, source=True, destination=False) or []
                if "squashFfd" not in inputs:
                    continue
                c.sets(shape, remove="squashFfdSet")
                pairs = c.listConnections(shape + ".create", source=True, destination=False, plugs=True, connections=True) or []
                if pairs:
                    c.disconnectAttr(pairs[1], pairs[0])
                for child in c.listRelatives(control, children=True) or []:
                    if c.getAttr(child + ".intermediateObject"):
                        c.delete(child)
        if c.objExists("OnFacecontrolsLayered") and c.objExists("FaceCustomSystem"):
            for child in c.listRelatives("FaceCustomSystem", children=True) or []:
                inputs = c.listConnections(child + ".offsetParentMatrix", source=True, destination=False) or []
                if inputs:
                    pairs = c.listConnections(inputs[0] + ".matrixIn", source=True, destination=False, plugs=True, connections=True) or []
                    if pairs:
                        c.disconnectAttr(pairs[-1], pairs[-2])
        c.select(clear=True)
        raw.dgdirty(allPlugs=True)
        self._transaction_changed = True
