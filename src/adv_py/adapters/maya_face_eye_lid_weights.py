"""Original asFaceEyeLid point/row weights and dual-quaternion area, 33790–34039."""


class MayaFaceEyeLidWeightsMixin:
    def _original_lid_hammer(self, source, vertices, iterations=5):
        c = self._cmds
        raw = getattr(c, "raw", c)
        if not vertices:
            return
        raw.select(vertices, replace=True)
        fit = self._fit(required=True)
        maximum = 0
        if all(c.objExists(fit + "." + attr) for attr in ("GameEngine", "UseMaxInf", "MaxInf")):
            if c.getAttr(fit + ".GameEngine") and c.getAttr(fit + ".UseMaxInf"):
                maximum = int(c.getAttr(fit + ".MaxInf", asString=True))
        raw.skinCluster(self.scene_address(source["lid_skin"]), edit=True, smoothWeights=0,
                        smoothWeightsMaxIterations=iterations, obeyMaxInfluences=maximum > 0)

    def _original_lid_ring_vertices(self, source, layer, suffix):
        c = self._cmds
        raw = getattr(c, "raw", c)
        values = self._original_lid_fit_vertices("FaceFitEyeLid" + layer + "Curve" + suffix, source["geometry"])
        return tuple(raw.ls(values, long=True, flatten=True) or [])

    def assign_original_eye_lid_weights(self, source):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        skin = self.scene_address(source["lid_skin"])
        geometry = self.scene_address(source["geometry"])
        right = raw.sets(self.scene_address("eyeLidArea"), query=True) or []
        left = raw.sets(self.scene_address("eyeLidAreaLeft"), query=True) or []
        if len(right) != len(left):
            raw.warning("eyeLidArea 有 %s 个顶点，左侧有 %s 个，模型可能不对称" % (len(right), len(left)))
        influences = []
        last_joint = ""
        for side, suffix in (("_R", ""), ("_L", "Left")):
            if source["cyclops"] and side == "_R":
                continue
            for arc in ("upper", "lower"):
                for part in ("Main", "Outer"):
                    if part == "Outer" and source["simpler"]:
                        continue
                    count = int(c.getAttr(arc + "EyeLid" + part + "Curve" + suffix + ".spans")) + 1
                    influences.extend(self.scene_address(arc + "Lid" + part + str(i) + side)
                                      for i in range(count) if arc != "lower" or i not in (0, count - 1))
        raw.skinCluster(skin, edit=True, addInfluence=influences, lockWeights=False, weight=0)
        if c.objExists("closestSampler"):
            c.delete("closestSampler")
        sampler = c.createNode("closestPointOnMesh", name="closestSampler")
        raw.connectAttr(geometry + ".outMesh", self.scene_address(sampler) + ".inMesh", force=True)
        for side, suffix in (("_R", ""), ("_L", "Left")):
            if source["cyclops"] and side == "_R":
                continue
            for arc in ("upper", "lower"):
                for part in ("Main", "Outer"):
                    if part == "Outer" and source["simpler"]:
                        continue
                    count = int(c.getAttr(arc + "EyeLid" + part + "Curve" + suffix + ".spans")) + 1
                    vertices = self._original_lid_fit_vertices(arc + "EyeLid" + part + "Curve" + suffix, source["geometry"])
                    for index, vertex in enumerate(vertices):
                        if arc == "lower" and index in (0, count - 1):
                            continue
                        point = raw.xform(vertex, query=True, worldSpace=True, translation=True)
                        c.setAttr(sampler + ".inPosition", *point, type="float3")
                        target = geometry + f".vtx[{int(c.getAttr(sampler + '.result.closestVertexIndex'))}]"
                        raw.skinPercent(skin, target,
                                        transformValue=((self.scene_address(arc + "Lid" + part + str(index) + side), 1),))
                # Source uses the last processed ring count for Main2 and
                # retains the previous joint when Main2 has extra samples.
                if not c.objExists(arc + "EyeLidMain2Curve"):
                    continue
                vertices = self._original_lid_fit_vertices(arc + "EyeLidMain2Curve" + suffix, source["geometry"])
                for index, vertex in enumerate(vertices):
                    if arc == "lower" and index in (0, count - 1):
                        continue
                    point = raw.xform(vertex, query=True, worldSpace=True, translation=True)
                    c.setAttr(sampler + ".inPosition", *point, type="float3")
                    candidate = arc + "LidMain" + str(index) + side
                    if c.objExists(candidate):
                        last_joint = candidate
                    target = geometry + f".vtx[{int(c.getAttr(sampler + '.result.closestVertexIndex'))}]"
                    raw.skinPercent(skin, target, transformValue=((self.scene_address(last_joint), 1),))
        for suffix in ("", "Left"):
            raw.select(self.scene_address("eyeLidArea" + suffix), replace=True)
            raw.select(self._original_lid_ring_vertices(source, "Main", suffix), deselect=True)
            if c.objExists("upperEyeLidMain2Curve"):
                raw.select(self._original_lid_ring_vertices(source, "Main2", suffix), deselect=True)
            self._original_lid_hammer(source, self._original_lid_selected_vertices())
            raw.select(self.scene_address("eyeLidOuterArea" + suffix), replace=True)
            raw.select(self._original_lid_ring_vertices(source, "Outer", suffix), deselect=True)
            self._original_lid_hammer(source, self._original_lid_selected_vertices())
        self._original_lid_row_weights(source)
        raw.select(clear=True)
        c.delete("FaceBuildEyeLidCurves")
        if not source["game"]:
            raw.setAttr(skin + ".skinningMethod", 2)
            for index in range(int(raw.polyEvaluate(geometry, vertex=True))):
                raw.setAttr(skin + f".bw[{index}]", 0)
            raw.select((self.scene_address("eyeLidArea"), self.scene_address("eyeLidAreaLeft")), replace=True)
            for vertex in self._original_lid_selected_vertices():
                index = int(vertex.rsplit("[", 1)[1][:-1])
                raw.setAttr(skin + f".bw[{index}]", 1)
        main_area = []
        for suffix in ("", "Left"):
            main_area.extend(self._original_lid_ring_vertices(source, "Main", suffix))
            if c.objExists("upperEyeLidMain2Curve"):
                main_area.extend(self._original_lid_ring_vertices(source, "Main2", suffix))
        self._original_lid_area("eyeLidMainArea", main_area)

    def _original_lid_row_weights(self, source):
        c = self._cmds
        raw = getattr(c, "raw", c)
        skin = self.scene_address(source["lid_skin"])
        row_weighted = []
        row = main2 = ()
        for suffix in ("", "Left"):
            for region in (0, 1):
                outer = self._original_lid_ring_vertices(source, "Outer", suffix)
                main = self._original_lid_ring_vertices(source, "Main", suffix)
                inner = self._original_lid_ring_vertices(source, "Inner", suffix)
                if c.objExists("FaceFitEyeLidMain2"):
                    main2 = self._original_lid_ring_vertices(source, "Main2", suffix)
                boundary = outer if region == 0 else inner
                if region == 1 and inner[0] in main:
                    break
                raw.select(self.scene_address("eyeLidArea" + suffix), replace=True)
                if len(self._original_lid_selected_vertices()) > 600:
                    raw.warning("eyeLidArea 超过 600 个顶点，按原版使用简化蒙皮")
                    break
                for vertex in main:
                    raw.select(vertex, replace=True)
                    for _ in range(99):
                        edges = raw.polyListComponentConversion(raw.ls(selection=True), toEdge=True)
                        grown = raw.polyListComponentConversion(edges, toVertex=True)
                        raw.select(grown, replace=True)
                        raw.select(main, deselect=True)
                        nearest = next((v for v in self._original_lid_selected_vertices() if v in boundary), None)
                        if nearest is None:
                            continue
                        start = int(vertex.rsplit("[", 1)[1][:-1])
                        end = int(nearest.rsplit("[", 1)[1][:-1])
                        row = self._lip_least_path(source["geometry"], start, end)
                        raw.select(row, replace=True)
                        raw.select(vertex, deselect=True)
                        if region == 0:
                            raw.select(boundary, deselect=True)
                        row = self._original_lid_selected_vertices()
                        break
                    influences = raw.skinPercent(skin, vertex, ignoreBelow=.001, query=True, transform=None) or []
                    row_weighted.extend(row)
                    if region == 1:
                        if row:
                            raw.skinPercent(skin, row, transformValue=((influences[0], 1),))
                        continue
                    raw.select(vertex, replace=True)
                    previous = ()
                    for step in range(len(row)):
                        edges = raw.polyListComponentConversion(raw.ls(selection=True), toEdge=True)
                        raw.select(raw.polyListComponentConversion(edges, toVertex=True), replace=True)
                        current = self._original_lid_selected_vertices()
                        if previous:
                            raw.select(previous, deselect=True)
                        previous = current
                        for candidate in self._original_lid_selected_vertices():
                            if candidate in row:
                                raw.skinPercent(skin, candidate,
                                                transformValue=((influences[0], 1 - (step + 1) / (len(row) + 1)),))
            vertices = self._original_lid_fit_vertices("EyeLidInnerAreaMesh" + suffix, source["geometry"])
            raw.select(vertices, replace=True)
            raw.select((*row_weighted, *main, *main2, *outer, *inner), deselect=True)
            self._original_lid_hammer(source, self._original_lid_selected_vertices())

    def create_original_lid_cheek_raiser(self, source):
        c = self._cmds
        raw = getattr(c, "raw", c)
        skin = self.scene_address(source["lid_skin"])
        geometry = self.scene_address(source["geometry"])
        controls = []
        for side, suffix in (("_R", ""), ("_L", "Left")):
            index = (int(c.getAttr("lowerEyeLidOuterCurve.spans")) + 1) // 2
            position = self._lip_pos("lowerEyeLidOuterCurve" + suffix + f".cv[{index}]")
            c.xform("TempPos", worldSpace=True, translation=position)
            controls.append(self.create_original_face_pp("TempPos", "lowerLidOuter", side, 3, create_joint=True))
            joint = self.scene_address("lowerLidOuterJoint" + side)
            raw.skinCluster(skin, edit=True, dropoffRate=4, lockWeights=False, weight=0, addInfluence=joint)
            c.setAttr("closestSampler.inPosition", *position, type="float3")
            vertex = geometry + f".vtx[{int(c.getAttr('closestSampler.result.closestVertexIndex'))}]"
            raw.skinPercent(skin, vertex, transformValue=((joint, 1),))
            raw.select(vertex, replace=True)
            for _ in range(source["num_grow"]):
                raw.polySelectConstraint(propagate=1, type=1)
            raw.select((self.scene_address("eyeLidArea" + suffix), vertex), deselect=True)
            self._original_lid_hammer(source, self._original_lid_selected_vertices())
            self._original_lid_hammer(source, (vertex,))
            raw.skinPercent(skin, vertex, transformValue=((joint, .5),))
        return tuple(controls)
