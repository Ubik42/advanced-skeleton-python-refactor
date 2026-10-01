"""Original asFaceEyeLid preparation and area sets, 32933–33208."""
from contextlib import nullcontext
from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_topology import original_face_connected_vertices


class MayaFaceEyeLidPrepMixin:
    def capture_original_face_lid_input(self):
        c = self._cmds
        fit = self._fit(required=True)
        meshes = self.read_face_objects(FacePreRole.FACE)
        if len(meshes) != 1:
            raise FitSkeletonValidationError("原版 EyeLid 需要唯一 Face 网格")
        required = ("Eye_R", "Eye_L", "EyeJoint_R", "EyeJoint_L", "EyeRegion_R", "EyeRegion_L",
                    "EyeRegionJoint_R", "EyeRegionJoint_L", "FaceJoint_M", "FaceDeformationSystem",
                    "FaceControlOrient", "FaceBuildInProgress", "FaceBuildInProgressHidden", "FaceAreas",
                    "OnFacecontrols", "ctrlBoxEye_R", "ctrlBoxEye_L")
        for node in required:
            if not c.objExists(node):
                raise FitSkeletonValidationError("原版 EyeLid 缺少前置节点：" + node)
        for suffix in ("", "Left"):
            for layer in ("Outer", "Main", "Inner"):
                for arc in ("upper", "lower"):
                    node = arc + "EyeLid" + layer + "Curve" + suffix
                    if not c.objExists(node):
                        raise FitSkeletonValidationError("原版 EyeLid 缺少 Fit 曲线：" + node)
        if c.objExists("LidSetup"):
            raise FitSkeletonValidationError("原版 EyeLid 已存在，请使用重建流程")
        head = c.getAttr(fit + ".HeadJoint")
        def option(name):
            return bool(c.objExists(fit + "." + name) and c.getAttr(fit + "." + name))
        include = c.getAttr(fit + ".Include", asString=True) if c.objExists(fit + ".Include") else "Complete"
        return {"geometry": meshes[0], "head": head, "skin": self.original_face_production_skin(meshes[0], head),
                "scale": float(c.getAttr(fit + ".faceScale")), "opm": self.face_use_offset_parent_matrix(),
                "ctrl_scale": float(c.getAttr("OnFacecontrols.sx")), "multi": option("MultiSkinClusters"),
                "non_sym": option("NonSym"), "simpler": option("SimplerEyeLid"), "socket": option("EyeSocket"),
                "game": option("GameEngine"), "cyclops": option("Cyclops"),
                "below": include not in ("Skip Below Eyes", "Skip Above+Below Eyes"),
                "lashes": self.read_original_face_parts("EyeLash")}

    def _original_lid_fit_vertices(self, name, geometry):
        return tuple(self.scene_address(v) for v in self.sample_face_fit_vertices(name, geometry))

    def _original_lid_selected_vertices(self):
        raw = getattr(self._cmds, "raw", self._cmds)
        return tuple(raw.ls(selection=True, long=True, flatten=True) or [])

    def _original_lid_area(self, name, vertices):
        c = self._cmds
        raw = getattr(c, "raw", c)
        area = c.sets(empty=True, name=name)
        if vertices:
            raw.sets(vertices, add=self.scene_address(area))
        c.sets(area, add="FaceAreas")
        return area

    def prepare_original_eye_lid(self, source):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        for side in ("_L", "_R"):
            c.setAttr("ctrlEye" + side + ".tx", 0)
            c.setAttr("ctrlEye" + side + ".ty", 0)
        self.hide_original_face_controllers(True)
        for side in ("_R", "_L"):
            c.setAttr("ctrlBoxEye" + side + ".v", True)
            c.setAttr("EyeRegionOffset" + side + ".v", True)
        c.createNode("transform", name="LidSetup", parent="FaceDeformationSystem")
        c.createNode("transform", name="LidJoints", parent="LidSetup")
        c.createNode("transform", name="TempPos")
        c.createNode("transform", name="FaceBuildEyeLidCurves", parent="FaceBuildInProgress")
        skin = self.add_original_face_multi_skin("EyeLid", source["geometry"]) if source["multi"] else source["skin"]
        source["lid_skin"] = skin
        c.select("FaceJoint_M", replace=True)
        joint = c.joint(name="EyeLidJoints_M")
        position = self._lip_pos("Eye_R")
        c.xform(joint, worldSpace=True, translation=(0, position[1], position[2]))
        c.setAttr(joint + ".drawStyle", 2)
        raw.skinCluster(self.scene_address(skin), edit=True, addInfluence=self.scene_address(joint),
                        dropoffRate=4, lockWeights=False, weight=0)
        for side in ("_R", "_L"):
            node = c.createNode("transform", name="LidSetup" + side)
            self._original_eye_align(node, "Eye" + side)
            self.constrain_original_face("EyeRegion" + side, node, force_matrix=False)
            c.parent(node, "LidSetup")
            c.parent("EyeRegionJoint" + side, "LidJoints")
        if not source["cyclops"]:
            self._original_lid_control_orient(source)
        for side, suffix in (("_R", ""), ("_L", "Left")):
            outer = self._original_lid_fit_vertices("FaceFitEyeLidOuterCurve" + suffix, source["geometry"])
            main = self._original_lid_fit_vertices("FaceFitEyeLidMainCurve" + suffix, source["geometry"])
            inner = self._original_lid_fit_vertices("FaceFitEyeLidInnerCurve" + suffix, source["geometry"])
            raw.select(main, replace=True)
            for _ in range(20):
                raw.polySelectConstraint(propagate=1, type=1)
                raw.select((*outer, *inner), deselect=True)
            raw.select(main, add=True)
            self._original_lid_area("eyeLidArea" + suffix, self._original_lid_selected_vertices())
        if source["socket"]:
            self._original_lid_eye_socket(source)
        source["num_grow"] = self._original_lid_outer_areas(source)

    def _original_lid_control_orient(self, source):
        c = self._cmds
        c.rename("FaceControlOrient", "FaceControlSuspended")
        right_a = self._lip_pos("upperEyeLidMainCurve.cv[99]")
        right_b = self._lip_pos("upperEyeLidMainCurve.cv[0]")
        c.polyPlane(name="FaceControlOrient", width=1, height=1, subdivisionsX=3,
                    subdivisionsY=1, axis=(0, 1, 0), createUVs=2, constructionHistory=False)
        c.sets("FaceControlOrient", edit=True, forceElement="asRedSG")
        c.polySoftEdge("FaceControlOrient", angle=0, constructionHistory=False)
        c.xform("FaceControlOrient", worldSpace=True,
                translation=(0, (right_a[1] + right_b[1]) / 2, (right_a[2] + right_b[2]) / 2))
        c.setAttr("FaceControlOrient.rx", 90)
        c.setAttr("FaceControlOrient.s", *(source["scale"],) * 3, type="float3")
        for suffix, ends in (("", ((4, 0), (5, 1))), ("Left", ((7, 3), (6, 2)))):
            points = (self._lip_pos("upperEyeLidMainCurve" + suffix + ".cv[99]"),
                      self._lip_pos("upperEyeLidMainCurve" + suffix + ".cv[0]"))
            for point, indices in zip(points, ends):
                for index in indices:
                    vertex = "FaceControlOrientShape" + f".vtx[{index}]"
                    current = self._lip_pos(vertex)
                    c.xform(vertex, worldSpace=True, translation=(point[0], current[1], point[2]))
        c.scale(1.1, 1.1, 1, "FaceControlOrient.vtx[0]", "FaceControlOrient.vtx[3:4]",
                "FaceControlOrient.vtx[7]", relative=True, objectCenterPivot=True)
        c.scale(.7, 1.1, 1, "FaceControlOrient.vtx[1:2]", "FaceControlOrient.vtx[5:6]",
                relative=True, objectCenterPivot=True)
        c.parent("FaceControlOrient", "FaceBuildInProgressHidden")

    def _original_lid_eye_socket(self, source):
        c = self._cmds
        raw = getattr(c, "raw", c)
        for side, suffix in (("_R", ""), ("_L", "Left")):
            inner = self._original_lid_fit_vertices("FaceFitEyeLidInnerCurve" + suffix, source["geometry"])
            raw.select(inner[0], replace=True)
            raw.polySelectConstraint(propagate=1, type=1)
            for vertex in self._original_lid_selected_vertices():
                if raw.sets(vertex, isMember=self.scene_address("eyeLidArea" + suffix)):
                    continue
                raw.select(vertex, replace=True)
                for _ in range(99):
                    raw.polySelectConstraint(propagate=1, type=1)
                    raw.select(self.scene_address("eyeLidArea" + suffix), deselect=True)
                break
            area = self._original_lid_area("eyeSocketArea" + suffix, self._original_lid_selected_vertices())
            self.create_original_face_controller("EyeSocket", side, 4)
            c.parent("EyeSocketJoint" + side, "FaceJoint_M")
            self.constrain_original_face("EyeSocket" + side, "EyeSocketJoint" + side)
            point = self._lip_pos("Eye" + side)
            c.xform("EyeSocketOffset" + side, worldSpace=True, translation=point)
            c.scale(5, 5, 5, "EyeSocket" + side + ".cv[0:7]", relative=True, pivot=point)
            c.parent("EyeSocketOffset" + side, "EyeRegion" + side)
            c.xform("EyeSocketOffset" + side, objectSpace=True, rotation=(0, 0, 0), scale=(1, 1, 1))
            self.reset_original_face_joint_matrix_scale("EyeSocketJoint" + side)
            self.project_original_face_control("EyeSocket" + side)
            raw.skinCluster(self.scene_address(source["lid_skin"]), edit=True, dropoffRate=4, lockWeights=False,
                            weight=0, addInfluence=self.scene_address("EyeSocketJoint" + side))
            vertices = raw.sets(self.scene_address(area), query=True) or []
            raw.skinPercent(self.scene_address(source["lid_skin"]), vertices,
                            transformValue=((self.scene_address("EyeSocketJoint" + side), 1),))
            raw.select(clear=True)

    def _original_lid_outer_areas(self, source):
        c = self._cmds
        raw = getattr(c, "raw", c)
        # The MEL loop leaves the final side's numGrow for CheekRaiser.
        num_grow = 0
        for side, suffix in (("_R", ""), ("_L", "Left")):
            self._original_lid_area("eyeLidOuterArea" + suffix, ())
            eye_inner = eye_outer = cheek = nose = ""
            if c.objExists("EyeBrowInner" + suffix):
                eye_inner = self._original_lid_fit_vertices("EyeBrowInner" + suffix, source["geometry"])[0]
            if c.objExists("EyeBrowOuter" + suffix):
                eye_outer = self._original_lid_fit_vertices("EyeBrowOuter" + suffix, source["geometry"])[0]
            outer = self._original_lid_fit_vertices("FaceFitEyeLidOuterCurve" + suffix, source["geometry"])
            if eye_inner and c.objExists("EyeBrowInner"):
                eye_inner = self._original_lid_brow_shell_vertex(source, suffix, outer, eye_inner)
            if source["below"]:
                cheek = self._original_lid_fit_vertices("CheekBone" + suffix, source["geometry"])[0]
                nose = self._original_lid_fit_vertices("NoseCorner" + suffix, source["geometry"])[0]
            raw.select(outer, replace=True)
            previous = ()
            for index in range(25):
                num_grow = index + 1
                raw.polySelectConstraint(propagate=1, type=1)
                raw.select(self.scene_address("eyeLidArea" + suffix), deselect=True)
                if previous:
                    raw.select(previous, deselect=True)
                previous = self._original_lid_selected_vertices()
                if eye_inner in previous or eye_outer in previous:
                    break
                if not c.objExists("EyeBrowInner") and index == 1:
                    break
                if cheek in previous or nose in previous:
                    num_grow -= 2
                    if side == "_R":
                        raw.warning("EyeLid 外围网格较稀疏，按原版缩减范围到 %s 行" % num_grow)
                    break
            raw.select(outer, replace=True)
            for _ in range(num_grow):
                raw.polySelectConstraint(propagate=1, type=1)
                raw.select(self.scene_address("eyeLidArea" + suffix), deselect=True)
            vertices = self._original_lid_selected_vertices()
            if vertices:
                raw.sets(vertices, add=self.scene_address("eyeLidOuterArea" + suffix))
        return num_grow

    def _original_lid_brow_shell_vertex(self, source, suffix, outer, vertex):
        c = self._cmds
        raw = getattr(c, "raw", c)
        # MEL calls ConvertSelectionToShell (polyConvertToShell), not a
        # persistent shell selection constraint. Resolve the same connected
        # components explicitly and record only the resulting selection.
        shell = original_face_connected_vertices(self, source["geometry"], outer)
        raw.select(shell, replace=True)
        full_vertex = (raw.ls(vertex, long=True, flatten=True) or [vertex])[0]
        if full_vertex in shell:
            return vertex
        with c._creation_namespace() if hasattr(c, "_creation_namespace") else nullcontext():
            duplicate = raw.duplicate(self.scene_address(source["geometry"]),
                                      name=self.scene_address("asTempSingleShellFace"), returnRootsOnly=True)[0]
        c.parent("asTempSingleShellFace", "FaceBuildInProgress")
        cast = [duplicate + "." + item.split(".", 1)[1] for item in shell]
        keep = set(raw.ls(raw.polyListComponentConversion(cast, toFace=True), long=True, flatten=True) or [])
        all_faces = raw.ls(duplicate + ".f[*]", long=True, flatten=True) or []
        remove = [item for item in all_faces if item not in keep]
        if remove:
            # This temporary duplicate is used only to sample the detached
            # lid shell. Record polygon deletion explicitly; generic delete
            # can abort redo after deleting components on a skinned copy.
            raw.polyDelFacet(remove, constructionHistory=False)
        if c.objExists("closestSampler"):
            c.delete("closestSampler")
        sampler = c.createNode("closestPointOnMesh", name="closestSampler")
        c.connectAttr("asTempSingleShellFace.outMesh", sampler + ".inMesh", force=True)
        point = raw.xform(vertex, query=True, worldSpace=True, translation=True)
        c.setAttr(sampler + ".inPosition", *point, type="float3")
        index = int(c.getAttr(sampler + ".result.closestVertexIndex"))
        c.delete("asTempSingleShellFace", sampler)
        return self.scene_address(source["geometry"]) + f".vtx[{index}]"
