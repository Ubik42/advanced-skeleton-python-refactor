"""Original Mixed Face local matrix and layered control conversion."""


class MayaFaceBSMixedMixin:
    def make_original_face_bs_mixed_local(self, source):
        c = self._cmds
        raw = getattr(c, "raw", c)
        for geometry in source["all_head"]:
            skin = self._original_pupil_skin(self.scene_address(geometry), exclude_prefix=False)
            for joint in c.listConnections(skin + ".matrix") or []:
                raw.setAttr(self.scene_address(joint) + ".liw", not bool(c.sets(joint, isMember="FaceAllSet")))
            raw.setAttr(self.scene_address(source["head"]) + ".liw", False)
            try:
                raw.skinPercent(skin, self.scene_address(geometry), transformValue=((self.scene_address(source["head"]), 1),))
            except RuntimeError:
                pass
            raw.skinCluster(skin, edit=True, removeUnusedInfluence=True)
            bs = "asFaceBS" if geometry == source["geometry"] else "asFaceBS_" + self._original_bs_geo_tag(geometry, first_colon=True)
            c.setAttr(bs + ".FaceJointsLayer", 1)
        self._original_bs_delete_existing(tuple("FaceDeformationFollowHead_" + kind + "1" for kind in ("pointConstraint", "orientConstraint", "parentConstraint")))
        c.createNode("transform", name="FaceMotionSystemStatic", parent="FaceGroup")
        c.reorder("FaceMotionSystemStatic", relative=-1)
        c.parent("OnFacecontrols", "FaceMotionSystemStatic")
        c.createNode("transform", name="OnFacecontrolsLayered", parent="OnFacecontrols")
        c.parent("OnFacecontrolsLayered", "ControlsSetup")
        c.parent("ConstrainedSetup", "FaceMotionSystemStatic")
        for side in ("_R", "_L", "_M"):
            c.createNode("transform", name="SideReverseLayered" + side, parent="OnFacecontrolsLayered")
        c.setAttr("SideReverseLayered_R.sx", -1)
        self._original_bs_delete_existing(tuple("EyeLattice2" + side + "_" + kind + "1" for side in ("_R", "_L") for kind in ("parentConstraint", "scaleConstraint")))
        for part, side in (("RightEye", "_R"), ("LeftEye", "_L")):
            if not c.objExists("squashEyeFfd1Set_R"):
                continue
            for mesh in self.read_original_face_parts(part):
                if "." in mesh:
                    continue
                layer = "FaceJointsLayer_" + self._original_bs_geo_tag(mesh, first_colon=True)
                for number in (1, 2):
                    raw.sets(self._original_bs_physical_address(mesh), remove=self.scene_address("squashEyeFfd" + str(number) + "Set" + side))
                    c.sets(layer, add="squashEyeFfd" + str(number) + "Set" + side)
                c.reorderDeformers(layer + "SC", "squashEyeFfd1" + side, layer)
        if c.objExists("upperSideReverse_R"):
            self.rebuild_original_face_bs_up_mid_lo(source)
        if c.objExists("EyeBaseOffset_R"):
            c.parent("EyeBaseOffset_R", "EyeBaseOffset_L", "EyeControls")
        opm = self.face_use_offset_parent_matrix()
        for stem in ("Eye", "Iris", "Pupil", "Jaw", "upperTeeth", "lowerTeeth", "Tongue0", "Tongue1", "Tongue2", "Tongue3"):
            for side in ("_R", "_L", "_M"):
                control, joint = stem + side, stem + "Joint" + side
                if not c.objExists(joint):
                    continue
                path = c.ls(stem + "Offset" + side, long=True)[0]
                scaled = any(part.rsplit(":", 1)[-1].startswith("SideReverse") for part in path.split("|")[:-1])
                if scaled:
                    if stem not in ("Tongue1", "Tongue2", "Tongue3"):
                        c.parent(stem + "Offset" + side, "SideReverseLayered" + side)
                    multiply = c.createNode("multiplyDivide", name=stem + "ScaledMPD" + side)
                    c.setAttr(multiply + ".input2", *(source["ctrl_scale"],) * 3, type="float3")
                constraints = c.listConnections(joint, source=True, destination=False, type="constraint") or []
                if constraints:
                    c.delete(constraints)
                matrix = c.createNode("multMatrix", name=control + "_mm")
                if opm:
                    c.connectAttr(matrix + ".matrixSum", joint + ".offsetParentMatrix", force=True)
                else:
                    decompose = c.createNode("decomposeMatrix", name=control + "_dm")
                    c.connectAttr(matrix + ".matrixSum", decompose + ".inputMatrix")
                    for short, long in (("t", "Translate"), ("r", "Rotate"), ("s", "Scale")):
                        for axis in "XYZ":
                            c.connectAttr(decompose + ".output" + long + axis, joint + "." + short + axis.lower(), force=True)
                c.getAttr(joint + ".matrix")
                c.connectAttr(control + ".worldMatrix", matrix + ".matrixIn[1]")
                if stem.startswith("Tongue"):
                    c.setAttr(joint + ".jointOrient", 0, 0, 0, type="float3")
                if not c.objExists("HeadMatrixInverter_M"):
                    c.createNode("transform", name="HeadMatrixInverter_M", parent="FaceDeformationSystem")
                    self.constrain_original_face("Head_M", "HeadMatrixInverter_M", True, opm=False)
                c.connectAttr("HeadMatrixInverter_M.inverseMatrix", matrix + ".matrixIn[2]", force=True)
                parent = c.listRelatives(joint, parent=True)[0]
                c.connectAttr(parent + ".worldInverseMatrix", matrix + ".matrixIn[3]")
                if scaled:
                    c.createNode("transform", name="tempXform")
                    c.setAttr("tempXform.s", *(source["ctrl_scale"],) * 3, type="float3")
                    inverse = self.original_face_matrix_values("tempXform.inverseMatrix")
                    c.delete("tempXform")
                    c.setAttr(matrix + ".matrixIn[0]", *inverse, type="matrix")
        self._original_bs_delete_existing(("LipFollowHead_parentConstraint1", "LipFollowHead_scaleConstraint1", "LipFollowHeadMM_LipFollowHead"))
        for side in ("_R", "_L", "_M"):
            node = "JawFollow" + side
            constraints = c.listRelatives(node, children=True, type="constraint") or []
            if constraints:
                c.delete(constraints)
            c.parentConstraint("JawJoint_M", node, maintainOffset=True)
            c.scaleConstraint("JawJoint_M", node, maintainOffset=True)
        self.create_original_face_bs_attachers(source)
