"""Build segmented Main/Outer eyelid joints from bilateral Face Fit bands."""
from __future__ import annotations

from array import array
from contextlib import nullcontext
import json
from math import radians
import re

from adv_py.application.face_pre import EyeLidLayer, FacePreRole, FaceSide
from adv_py.core.dense_skin_transfer import DenseSkinWeights
from adv_py.core.face_build_requirements import FaceInclude
from adv_py.core.face_eyelid_fit import (
    eye_lid_blink_offsets, order_eye_lid_loop)
from adv_py.core.face_eyelid_skin import (
    eyelid_skin_factors, inner_eyelid_skin_factors,
    outer_eyelid_skin_factors, split_arc_weight)
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_dense_skin import MayaDenseSkinHost
from .maya_face_build import MayaFaceBuildHost
from .maya_face_pre import MayaFacePreHost


_COMPONENT = re.compile(r"\.((?:e)|(?:f)|(?:vtx))\[(\d+)\]$")


class MayaFaceEyeLidRigHost(MayaDenseSkinHost, MayaFacePreHost):
    def _ring(self, pre: MayaFaceBuildHost, mesh: str, mesh_fn, side: FaceSide,
              layer: EyeLidLayer):
        c = self._cmds
        pre.read_eye_lid_fit(layer, side)
        suffix = "Left" if side is FaceSide.LEFT else ""
        holder = (c.ls("FaceFitEyeLid" + layer.value + suffix,
                       long=True, type="transform") or [None])[0]
        if int(c.getAttr(holder + ".advPyFaceCount")) != mesh_fn.numPolygons:
            raise FitSkeletonValidationError("眼睑 Fit 后 Face 网格面数已改变")
        record = (c.getAttr(holder + ".selection") or "").split()
        edges = []
        corners = []
        for item in record:
            if not item.startswith(mesh + "."):
                raise FitSkeletonValidationError("眼睑 Fit 与当前 Face 网格不一致")
            match = _COMPONENT.search(item)
            if match is None:
                raise FitSkeletonValidationError("眼睑 Fit 组件记录无效")
            index = int(match.group(2))
            if match.group(1) == "e":
                edges.append((index, *mesh_fn.getEdgeVertices(index)))
            elif match.group(1) == "vtx":
                corners.append(index)
            else:
                raise FitSkeletonValidationError("眼睑 Fit 混入面组件")
        expected = [tuple(row) for row in json.loads(
            c.getAttr(holder + ".advPyEdgeVertices"))]
        observed = [(index, *sorted((first, second)))
                    for index, first, second in sorted(edges)]
        if observed != expected:
            raise FitSkeletonValidationError("眼睑 Fit 后 Face 网格边连接已改变")
        return tuple(edges), tuple(corners)

    def _surface_factors(self, pre: MayaFaceBuildHost, mesh: str,
                         side: FaceSide):
        from maya.api import OpenMaya as om

        c = self._cmds
        shape = (c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or [None])[0]
        selection = om.MSelectionList()
        selection.add(shape)
        fn = om.MFnMesh(selection.getDagPath(0))
        positions = {index: tuple(float(fn.getPoint(index,
                        om.MSpace.kWorld)[axis]) for axis in range(3))
                     for index in range(fn.numVertices)}
        adjacency = {index: set() for index in range(fn.numVertices)}
        for index in range(fn.numEdges):
            first, second = fn.getEdgeVertices(index)
            adjacency[first].add(second)
            adjacency[second].add(first)
        rings = {layer: self._ring(pre, mesh, fn, side, layer)
                 for layer in EyeLidLayer}
        eye_y = float(c.xform(pre.read_eye_ball_fit(side), query=True,
                              worldSpace=True, translation=True)[1])
        ordered = {}
        for layer in (EyeLidLayer.MAIN, EyeLidLayer.OUTER,
                      EyeLidLayer.INNER):
            edges, corners = rings[layer]
            points = {vertex: positions[vertex]
                      for _, first, second in edges
                      for vertex in (first, second)}
            if layer is not EyeLidLayer.INNER:
                ordered[layer] = order_eye_lid_loop(edges, points,
                        eye_center_y=eye_y, corner_vertices=corners,
                        side=side.value)
        boundary = {vertex for layer in (EyeLidLayer.OUTER,
                        EyeLidLayer.INNER)
                    for _, first, second in rings[layer][0]
                    for vertex in (first, second)}
        selected_inner_edges = {row[0] for row in rings[EyeLidLayer.INNER][0]}
        boundary_edges = set()
        edge_it = om.MItMeshEdge(selection.getDagPath(0))
        while not edge_it.isDone():
            if len(edge_it.getConnectedFaces()) == 1:
                boundary_edges.add(edge_it.index())
            edge_it.next()
        open_inner = selected_inner_edges <= boundary_edges
        if selected_inner_edges & boundary_edges and not open_inner:
            raise FitSkeletonValidationError(
                "EyeLid Inner 环混合了眼孔边界与表面内部边")
        inner_vertices = {vertex for _, first, second in
                          rings[EyeLidLayer.INNER][0]
                          for vertex in (first, second)}
        boundary_degrees = {vertex: 0 for vertex in inner_vertices}
        for edge in boundary_edges:
            for vertex in fn.getEdgeVertices(edge):
                if vertex in boundary_degrees:
                    boundary_degrees[vertex] += 1
        # A branched rim belongs to a larger open boundary. Original Max
        # leaves that rim on Head_M; only a simple hole gets Inner joints.
        mobile_inner = (open_inner and
                        all(degree == 2 for degree in
                            boundary_degrees.values()))
        if mobile_inner:
            edges, corners = rings[EyeLidLayer.INNER]
            ordered[EyeLidLayer.INNER] = order_eye_lid_loop(
                edges, {vertex: positions[vertex]
                        for _, first, second in edges
                        for vertex in (first, second)},
                eye_center_y=eye_y, corner_vertices=corners,
                side=side.value)
        area, _ = pre.read_eye_lid_area(side)
        face_ids = []
        for item in (c.getAttr(area + ".selection") or "").split():
            if not item.startswith(mesh + "."):
                raise FitSkeletonValidationError("眼睑区域与当前 Face 网格不一致")
            match = _COMPONENT.search(item)
            if match is None or match.group(1) != "f":
                raise FitSkeletonValidationError("眼睑区域面记录无效")
            face_ids.append(int(match.group(2)))
        area_vertices = {vertex for face in face_ids
                         for vertex in fn.getPolygonVertices(face)}
        main = ordered[EyeLidLayer.MAIN]
        outer = ordered[EyeLidLayer.OUTER]
        main_vertices = set(main.upper_vertices) | set(main.lower_vertices)
        if not main_vertices <= area_vertices or not boundary <= area_vertices:
            raise FitSkeletonValidationError(
                "眼睑区域与所选三层边环不一致："
                f"Main 缺 {len(main_vertices - area_vertices)} 顶点，"
                f"Outer／Inner 缺 {len(boundary - area_vertices)} 顶点")
        shared_corners = {main.upper_vertices[0],
                          main.upper_vertices[-1]}
        if (main_vertices & inner_vertices or
                (main_vertices & boundary) - shared_corners):
            raise FitSkeletonValidationError("眼睑 Main 与 Outer／Inner 环重叠")
        factors = {
            EyeLidLayer.MAIN: eyelid_skin_factors(adjacency, positions,
                area_vertices, boundary, main.upper_vertices,
                main.lower_vertices),
            EyeLidLayer.OUTER: outer_eyelid_skin_factors(adjacency,
                positions, area_vertices, outer.upper_vertices,
                outer.lower_vertices),
        }
        if mobile_inner:
            inner = ordered[EyeLidLayer.INNER]
            factors[EyeLidLayer.INNER] = inner_eyelid_skin_factors(
                adjacency, positions, area_vertices,
                inner.upper_vertices, inner.lower_vertices)
            for vertex, pair in factors[EyeLidLayer.INNER].items():
                remaining = 1. - sum(pair)
                for layer in (EyeLidLayer.MAIN, EyeLidLayer.OUTER):
                    old = factors[layer].get(vertex)
                    if old is not None:
                        factors[layer][vertex] = tuple(
                            value * remaining for value in old)
        arcs = {(layer, "upper"): ordered[layer].upper_vertices
                for layer in (EyeLidLayer.MAIN, EyeLidLayer.OUTER)}
        arcs.update({(layer, "lower"): ordered[layer].lower_vertices
                     for layer in (EyeLidLayer.MAIN, EyeLidLayer.OUTER)})
        if mobile_inner:
            arcs[(EyeLidLayer.INNER, "upper")] = (
                ordered[EyeLidLayer.INNER].upper_vertices)
            arcs[(EyeLidLayer.INNER, "lower")] = (
                ordered[EyeLidLayer.INNER].lower_vertices)
        span = max(positions[index][0] for index in main.upper_vertices) \
             - min(positions[index][0] for index in main.upper_vertices)
        return factors, arcs, positions, span, open_inner, mobile_inner

    def build(self) -> dict:
        c = self._cmds
        pre = MayaFaceBuildHost(namespace=self.namespace)
        fit = pre._fit(required=True)
        symmetric = not (c.attributeQuery("NonSym", node=fit, exists=True)
                         and c.getAttr(fit + ".NonSym"))
        if symmetric:
            try:
                pre.read_eye_ball_fit(FaceSide.LEFT)
                for layer in EyeLidLayer:
                    pre.read_eye_lid_fit(layer, FaceSide.LEFT)
            except FitSkeletonValidationError:
                if pre.read_include() is not FaceInclude.EYES_ONLY:
                    raise FitSkeletonValidationError(
                        "当前眼睑构建阶段需要 Skip Above+Below Eyes")
                eye_groups = c.ls("AdvPy_FaceEyes", long=True,
                                  type="transform") or []
                if len(eye_groups) != 1 or not c.attributeQuery(
                        "advPyLeftEyeMesh", node=eye_groups[0], exists=True):
                    raise FitSkeletonValidationError(
                        "先从 Face / Pre 构建双眼控制与蒙皮，再建立眼睑")
                left_eye = c.getAttr(eye_groups[0] + ".advPyLeftEyeMesh")
                with self.transaction("镜像 Fit 并建立双侧眼睑与 Skin"):
                    self._transaction_changed = True
                    mirror = self.mirror_right_eye_fit_to_left(left_eye)
                    result = self._build_prepared()
                    result["symmetric_mirror"] = mirror
                    return result
        return self._build_prepared()

    def _build_prepared(self) -> dict:
        c = self._cmds
        pre = MayaFaceBuildHost(namespace=self.namespace)
        readiness = pre.inspect_build_inputs()
        if not readiness["ready"]:
            raise FitSkeletonValidationError("FaceSetup 输入缺失："
                                             + "、".join(readiness["missing"]))
        if pre.read_include() is not FaceInclude.EYES_ONLY:
            raise FitSkeletonValidationError(
                "当前眼睑构建阶段需要 Skip Above+Below Eyes")
        if not readiness["non_symmetrical"]:
            try:
                pre.read_eye_ball_fit(FaceSide.LEFT)
                for layer in EyeLidLayer:
                    pre.read_eye_lid_fit(layer, FaceSide.LEFT)
            except FitSkeletonValidationError as error:
                raise FitSkeletonValidationError(
                    "对称角色先镜像右侧 Fit 到左侧") from error
        mesh = pre.read_face_objects(FacePreRole.FACE)[0]
        fit = pre._fit(required=True)
        head_name = c.getAttr(fit + ".HeadJoint")
        heads = c.ls(head_name, long=True, type="joint") or []
        if len(heads) != 1 or c.referenceQuery(heads[0], isNodeReferenced=True):
            raise FitSkeletonValidationError("Head 关节缺失、重名或属于引用")
        head = heads[0]
        eye_group = (c.ls("AdvPy_FaceEyes", long=True,
                          type="transform") or [None])[0]
        if (eye_group is None or
                c.listRelatives(eye_group, parent=True,
                                fullPath=True) != [head]):
            raise FitSkeletonValidationError(
                "先从 Face / Pre 构建双眼控制与蒙皮，再建立眼睑")
        eye_joints = {}
        eye_radii = {}
        for side in FaceSide:
            suffix = "_R" if side is FaceSide.RIGHT else "_L"
            joints = c.ls("AdvPy_Eye" + suffix, long=True, type="joint") or []
            mesh_attr = ("advPyRightEyeMesh" if side is FaceSide.RIGHT
                         else "advPyLeftEyeMesh")
            eye_mesh = c.getAttr(eye_group + "." + mesh_attr)
            if (len(joints) != 1 or not joints[0].startswith(eye_group + "|")
                    or not c.objExists(eye_mesh)
                    or c.getAttr(joints[0] + ".advPyAuxiliaryInfluenceKind")
                    != "face-eye-v1"):
                raise FitSkeletonValidationError("双眼控制与当前 Head 不匹配")
            bounds = c.exactWorldBoundingBox(eye_mesh)
            eye_joints[side] = joints[0]
            eye_radii[side] = max(bounds[index + 3] - bounds[index]
                                  for index in range(3)) / 2.
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        history = c.listHistory(shapes[0], pruneDagObjects=True) or []
        skins = [item for item in history if c.nodeType(item) == "skinCluster"]
        if len(skins) != 1:
            raise FitSkeletonValidationError("Face 网格需要唯一 Skin")
        skin = skins[0]
        if c.referenceQuery(mesh, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能在引用中的 Face 网格写入眼睑权重")
        factors = {}
        arcs = {}
        positions = {}
        spans = {}
        open_inners = {}
        mobile_inners = {}
        for side in FaceSide:
            (factors[side], arcs[side], positions[side], spans[side],
             open_inners[side], mobile_inners[side]) = self._surface_factors(
                pre, mesh, side)
        layers = {side: ((EyeLidLayer.MAIN, EyeLidLayer.OUTER,
                          EyeLidLayer.INNER) if mobile_inners[side] else
                         (EyeLidLayer.MAIN, EyeLidLayer.OUTER))
                  for side in FaceSide}
        def weighted(side):
            return {vertex for layer in layers[side]
                    for vertex, pair in factors[side][layer].items()
                    if sum(pair) > 1e-9}
        if weighted(FaceSide.RIGHT) & weighted(FaceSide.LEFT):
            raise FitSkeletonValidationError("左右眼睑区域发生重叠")
        blink_offsets = {}
        for side in FaceSide:
            for layer in layers[side]:
                blink_offsets[(side, layer)] = eye_lid_blink_offsets(
                    arcs[side][(layer, "upper")],
                    arcs[side][(layer, "lower")], positions[side])
        names = ["FaceJoint_M", "EyeLidJoints_M", "FaceMotionSystem"]
        for side in FaceSide:
            suffix = "_R" if side is FaceSide.RIGHT else "_L"
            names.extend(("ctrlEye" + suffix,
                          "ctrlEye" + suffix + "_Offset",
                          "ctrlEye" + suffix + "BlinkFraction",
                          "ctrlEye" + suffix + "BlinkReverse"))
            for layer in layers[side]:
                for arc in ("upper", "lower"):
                    label = "Upper" if arc == "upper" else "Lower"
                    control = "ctrl" + label + "EyeLid" + (
                        "Outer" if layer is EyeLidLayer.OUTER else
                        "Inner" if layer is EyeLidLayer.INNER else "") + suffix
                    names.extend((control, control + "_Offset"))
                    names.extend((control + "FleshyScale",
                                  control + "FleshyAmount",
                                  control + "FleshyBlink",
                                  control + "MotionSum"))
                    curve_name = arc + "Lid" + layer.value + "WorkCurve" + suffix
                    names.append(curve_name)
                    for index in range(len(arcs[side][(layer, arc)])):
                        names.extend((curve_name + str(index) + "Scale",
                                      curve_name + str(index) + "Sum",
                                      curve_name + str(index) + "Blink"))
                    for index in range(1, len(arcs[side][(layer, arc)]) - 1):
                        name = arc + "Lid" + layer.value + str(index) + suffix
                        names.extend((name, name + "POCI", name + "Offset"))
        if any(c.ls(name) for name in names):
            raise FitSkeletonValidationError("眼睑绑定节点名称已被占用")
        original = self.capture_dense_skin(skin)
        selected = c.ls(selection=True, long=True) or []
        joint_names = {}
        control_names = {}
        eye_control_names = {}
        work_curves = {}
        with (nullcontext() if self._transaction_active else
              self.transaction("建立双侧多关节眼睑与 Skin")):
            self._transaction_changed = True
            c.select(clear=True)
            face_joint = c.joint(name="FaceJoint_M")
            face_joint = c.parent(face_joint, head, absolute=True)[0]
            c.setAttr(face_joint + ".drawStyle", 2)
            c.select(clear=True)
            root = c.joint(name="EyeLidJoints_M")
            root = c.parent(root, face_joint, absolute=True)[0]
            c.setAttr(root + ".drawStyle", 2)
            motion = c.createNode("transform", name="FaceMotionSystem",
                                  parent=head)
            for side in FaceSide:
                suffix = "_R" if side is FaceSide.RIGHT else "_L"
                eye_name = "ctrlEye" + suffix
                eye_control = c.circle(name=eye_name, normal=(0, 0, 1),
                    radius=max(spans[side] / 5., .01),
                    constructionHistory=False)[0]
                eye_offset = c.createNode("transform",
                    name=eye_name + "_Offset", parent=motion)
                eye_center = c.xform(pre.read_eye_ball_fit(side), query=True,
                                     worldSpace=True, translation=True)
                c.xform(eye_offset, worldSpace=True, translation=eye_center)
                eye_control = c.parent(eye_control, eye_offset, relative=True)[0]
                c.addAttr(eye_control, longName="blink", attributeType="double",
                          minValue=0, maxValue=10, defaultValue=0, keyable=True)
                fraction = c.createNode("multiplyDivide",
                    name=eye_name + "BlinkFraction")
                c.setAttr(fraction + ".input2X", .1)
                c.connectAttr(eye_control + ".blink", fraction + ".input1X")
                reverse = c.createNode("reverse",
                    name=eye_name + "BlinkReverse")
                c.connectAttr(fraction + ".outputX", reverse + ".inputX")
                eye_control_names[side] = (
                    c.ls(eye_control, long=True, type="transform") or [eye_control])[0]
                for layer in layers[side]:
                    for arc in ("upper", "lower"):
                        vertices = arcs[side][(layer, arc)]
                        interior = vertices[1:-1]
                        label = "Upper" if arc == "upper" else "Lower"
                        control_name = "ctrl" + label + "EyeLid" + (
                            "Outer" if layer is EyeLidLayer.OUTER else
                            "Inner" if layer is EyeLidLayer.INNER else "") + suffix
                        center = tuple(sum(positions[side][index][axis]
                                         for index in interior) / len(interior)
                                       for axis in range(3))
                        control = c.circle(name=control_name,
                            normal=(0, 0, 1),
                            radius=max(spans[side] / 8., .005),
                            constructionHistory=False)[0]
                        offset = c.createNode("transform",
                            name=control_name + "_Offset", parent=motion)
                        c.xform(offset, worldSpace=True, translation=center)
                        control = c.parent(control, offset, relative=True)[0]
                        if layer is EyeLidLayer.INNER:
                            c.setAttr(control + ".visibility", False)
                        fleshy_default = (7. if arc == "upper" else 3.)
                        if layer is EyeLidLayer.OUTER:
                            fleshy_default /= 5.
                        c.addAttr(control, longName="fleshy",
                            attributeType="double", minValue=0, maxValue=10,
                            defaultValue=fleshy_default, keyable=True)
                        conversion = c.createNode("multiplyDivide",
                            name=control_name + "FleshyScale")
                        c.setAttr(conversion + ".input2X",
                                  eye_radii[side] * radians(1.) * .1)
                        c.setAttr(conversion + ".input2Y",
                                  -eye_radii[side] * radians(1.) * .1)
                        c.connectAttr(eye_joints[side] + ".rotateY",
                                      conversion + ".input1X")
                        c.connectAttr(eye_joints[side] + ".rotateX",
                                      conversion + ".input1Y")
                        amount = c.createNode("multiplyDivide",
                            name=control_name + "FleshyAmount")
                        c.connectAttr(conversion + ".output",
                                      amount + ".input1")
                        c.connectAttr(control + ".fleshy",
                                      amount + ".input2X")
                        c.connectAttr(control + ".fleshy",
                                      amount + ".input2Y")
                        blink_fade = c.createNode("multiplyDivide",
                            name=control_name + "FleshyBlink")
                        c.connectAttr(amount + ".output",
                                      blink_fade + ".input1")
                        c.setAttr(blink_fade + ".input2X", 1.)
                        c.connectAttr(reverse + ".outputX",
                                      blink_fade + ".input2Y")
                        motion_sum = c.createNode("plusMinusAverage",
                            name=control_name + "MotionSum")
                        c.connectAttr(control + ".translate",
                                      motion_sum + ".input3D[0]")
                        c.connectAttr(blink_fade + ".output",
                                      motion_sum + ".input3D[1]")
                        control_names[(side, layer, arc)] = (
                            c.ls(control, long=True, type="transform") or [control])[0]
                        curve = pre.read_eye_lid_fit(layer, side)[
                            0 if arc == "upper" else 1]
                        curve_name = arc + "Lid" + layer.value + "WorkCurve" + suffix
                        work_curve = c.duplicate(curve, name=curve_name,
                                                 returnRootsOnly=True)[0]
                        work_curve = c.parent(work_curve, motion, absolute=True)[0]
                        work_curves[(side, layer, arc)] = work_curve
                        curve_shape = (c.listRelatives(work_curve, shapes=True,
                                      fullPath=True, type="nurbsCurve") or [None])[0]
                        for index in range(len(vertices)):
                            point_plug = curve_shape + ".controlPoints[" + str(index) + "]"
                            base = c.getAttr(point_plug)[0]
                            tapered = index / (len(vertices) - 1)
                            tapered = min(1., 2. * min(tapered, 1. - tapered))
                            scale = c.createNode("multiplyDivide",
                                name=curve_name + str(index) + "Scale")
                            c.setAttr(scale + ".input2", tapered, tapered,
                                      tapered, type="double3")
                            c.connectAttr(motion_sum + ".output3D",
                                          scale + ".input1")
                            addition = c.createNode("plusMinusAverage",
                                name=curve_name + str(index) + "Sum")
                            c.setAttr(addition + ".input3D[0]", *base,
                                      type="double3")
                            c.connectAttr(scale + ".output",
                                          addition + ".input3D[1]")
                            blink = c.createNode("multiplyDivide",
                                name=curve_name + str(index) + "Blink")
                            c.setAttr(blink + ".input2Y",
                                blink_offsets[(side, layer)][arc][index] / 10.)
                            c.connectAttr(eye_control + ".blink",
                                          blink + ".input1Y")
                            c.connectAttr(blink + ".outputY",
                                          addition + ".input3D[2].input3Dy")
                            c.connectAttr(addition + ".output3D", point_plug)
                        for index, vertex in enumerate(vertices[1:-1], 1):
                            name = arc + "Lid" + layer.value + str(index) + suffix
                            point = c.createNode("pointOnCurveInfo",
                                                 name=name + "POCI")
                            c.connectAttr(curve_shape + ".worldSpace[0]",
                                          point + ".inputCurve")
                            c.setAttr(point + ".parameter", index)
                            joint_offset = c.createNode("transform",
                                name=name + "Offset", parent=root)
                            c.setAttr(joint_offset + ".inheritsTransform", False)
                            c.connectAttr(point + ".position",
                                          joint_offset + ".translate")
                            c.select(clear=True)
                            joint = c.joint(name=name)
                            joint = c.parent(joint, joint_offset,
                                             relative=True)[0]
                            c.setAttr(joint + ".radius",
                                      max(spans[side] / 40., .001))
                            c.addAttr(joint,
                                longName="advPyAuxiliaryInfluenceKind",
                                dataType="string")
                            c.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                                "face-eyelid-segment-v2", type="string",
                                lock=True)
                            c.skinCluster(skin, edit=True, addInfluence=joint,
                                          weight=0.0)
                            joint_names[(side, layer, arc, vertex)] = (
                                c.ls(joint, long=True, type="joint") or [joint])[0]
            target_skin = self.capture_dense_skin(skin)
            old_width = len(original.influence_names)
            new_names = target_skin.influence_names
            new_width = len(new_names)
            old_indices = [new_names.index(name) for name in
                           original.influence_names]
            lid_indices = {key: new_names.index(name.rsplit("|", 1)[-1])
                           for key, name in
                           joint_names.items()}
            before = memoryview(original.values).cast("d")
            values = array("d", [0.] * (original.vertex_count * new_width))
            for vertex in range(original.vertex_count):
                lid_weights = {}
                for side in FaceSide:
                    for layer in layers[side]:
                        pair = factors[side][layer].get(vertex, (0., 0.))
                        for arc, mass in (("upper", pair[0]),
                                          ("lower", pair[1])):
                            if mass <= 0:
                                continue
                            segments = split_arc_weight(
                                positions[side][vertex][0], positions[side],
                                arcs[side][(layer, arc)][1:-1], mass)
                            for segment_vertex, weight in segments.items():
                                key = (side, layer, arc, segment_vertex)
                                lid_weights[key] = (
                                    lid_weights.get(key, 0.) + weight)
                remaining = 1. - sum(lid_weights.values())
                if remaining < -1e-6:
                    raise FitSkeletonValidationError("眼睑区域权重之和超过 1")
                for source_index, target_index in enumerate(old_indices):
                    values[vertex * new_width + target_index] = (
                        before[vertex * old_width + source_index] * remaining)
                for key, target_index in lid_indices.items():
                    values[vertex * new_width + target_index] = (
                        lid_weights.get(key, 0.))
            self.apply_dense_skin(DenseSkinWeights(skin,
                original.vertex_count, new_names, values.tobytes()))
            c.addAttr(motion, longName="advPyFaceMesh", dataType="string")
            c.setAttr(motion + ".advPyFaceMesh", mesh, type="string")
            c.select(selected, replace=True) if selected else c.select(clear=True)
        return {"skin": skin, "mesh": mesh,
                "controls": control_names, "joints": joint_names,
                "aperture_sides": tuple(side.value for side in FaceSide
                                        if open_inners[side]),
                "stationary_aperture_sides": tuple(
                    side.value for side in FaceSide
                    if open_inners[side] and not mobile_inners[side]),
                "eye_controls": eye_control_names,
                "work_curves": work_curves,
                "area_vertices": {side.value: len(weighted(side))
                                  for side in FaceSide},
                "main_vertices": {side.value: len(factors[side][
                    EyeLidLayer.MAIN]) for side in FaceSide},
                "outer_vertices": {side.value: len(factors[side][
                    EyeLidLayer.OUTER]) for side in FaceSide}}
