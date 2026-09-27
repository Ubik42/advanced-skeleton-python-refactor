"""Build segmented Main/Outer eyelid joints from bilateral Face Fit bands."""
from __future__ import annotations

from array import array
from contextlib import nullcontext
import json
from math import dist, isfinite, radians
import re

from adv_py.application.face_pre import EyeLidLayer, FacePreRole, FaceSide
from adv_py.core.dense_skin_transfer import DenseSkinWeights
from adv_py.core.face_build_requirements import FaceInclude
from adv_py.core.face_eyelid_fit import (
    eye_lid_aperture_height, eye_lid_blink_offsets, eye_lid_sphere_blink,
    order_eye_lid_loop)
from adv_py.core.face_eyelid_skin import (
    eyelid_skin_factors, inner_eyelid_skin_factors,
    outer_eyelid_skin_factors, split_arc_weight)
from adv_py.core.face_eyelid_motion import EyeLidMotionPlan
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_dense_skin import MayaDenseSkinHost
from .maya_face_build import MayaFaceBuildHost
from .maya_face_pre import MayaFacePreHost


_COMPONENT = re.compile(r"\.((?:e)|(?:f)|(?:vtx))\[(\d+)\]$")
_CLOSED_LOWER_UPWARD_FOLLOW = .6


class MayaFaceEyeLidRigHost(MayaDenseSkinHost, MayaFacePreHost):
    def _repair_eye_lid_normals(self, mesh: str, pre: MayaFaceBuildHost,
                                eye_radii: dict[FaceSide, float],
                                mobile_inners: dict[FaceSide, bool],
                                eye_controls: dict[FaceSide, str]) -> dict:
        """Keep locked import normals from shading across a moving lid fold."""
        from maya.api import OpenMaya as om

        c = self._cmds
        active = [side for side in FaceSide if mobile_inners[side]]
        if not active:
            return {"status": "stationary_aperture"}
        shape = (c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or [None])[0]
        if shape is None:
            raise FitSkeletonValidationError("Face 网格形状缺失")
        selected = om.MSelectionList()
        selected.add(shape)
        dag = selected.getDagPath(0)
        fn = om.MFnMesh(dag)
        polygon_it = om.MItMeshPolygon(dag)
        area_faces = set()
        for side in active:
            holder, _ = pre.read_eye_lid_area(side)
            for item in (c.getAttr(holder + ".selection") or "").split():
                match = _COMPONENT.search(item)
                if match and match.group(1) == "f":
                    area_faces.add(int(match.group(2)))
        if not area_faces:
            return {"status": "no_area"}
        vertices, area_edges = set(), set()
        for face in area_faces:
            polygon_it.setIndex(face)
            vertices.update(fn.getPolygonVertices(face))
            area_edges.update(polygon_it.getEdges())
        aims = {}
        original = {}
        for side in active:
            suffix = "R" if side is FaceSide.RIGHT else "L"
            matches = c.ls("AdvPy_EyeAim_" + suffix,
                           long=True, type="transform") or []
            if len(matches) != 1:
                return {"status": "aim_unavailable"}
            aims[side] = matches[0] + ".translateY"
            original[side] = c.getAttr(aims[side])
        blinks = {side: eye_controls[side] + ".blink" for side in active}
        blink_values = {side: c.getAttr(plug) for side, plug in blinks.items()}
        if any(not c.getAttr(plug, settable=True)
               for plug in (*aims.values(), *blinks.values())):
            return {"status": "animated_controls"}
        edge_it = om.MItMeshEdge(dag)

        def sample(offset: float) -> tuple[int, set[int]]:
            for side in active:
                c.setAttr(aims[side], original[side] +
                          offset * eye_radii[side])
                c.setAttr(blinks[side], 0.)
            conflicts = 0
            for face in area_faces:
                normal = fn.getPolygonNormal(face, om.MSpace.kWorld)
                if normal.z <= .05:
                    continue
                if any(fn.getFaceVertexNormal(face, vertex,
                       om.MSpace.kWorld).z < -.05
                       for vertex in fn.getPolygonVertices(face)):
                    conflicts += 1
            creases = set()
            while not edge_it.isDone():
                faces = edge_it.getConnectedFaces()
                if (len(faces) == 2 and
                        any(face in area_faces for face in faces)):
                    first, second = (fn.getPolygonNormal(face,
                                      om.MSpace.kWorld).z for face in faces)
                    if first * second < 0.:
                        creases.add(edge_it.index())
                edge_it.next()
            edge_it.reset()
            return conflicts, creases

        try:
            neutral_count, neutral_edges = sample(0.)
            down_count, down_edges = sample(-2.)
        finally:
            for side in active:
                c.setAttr(aims[side], original[side])
                c.setAttr(blinks[side], blink_values[side])
        if down_count <= neutral_count + 2:
            return {"status": "preserved", "neutral_conflicts": neutral_count,
                    "down_conflicts": down_count}
        c.polyNormalPerVertex([f"{mesh}.vtx[{vertex}]"
                               for vertex in sorted(vertices)],
                              unFreezeNormal=True)
        c.polySoftEdge([f"{mesh}.e[{edge}]"
                        for edge in sorted(area_edges)],
                       angle=90, constructionHistory=True)
        crease_edges = neutral_edges | down_edges
        if crease_edges:
            c.polySoftEdge([f"{mesh}.e[{edge}]"
                            for edge in sorted(crease_edges)],
                           angle=0, constructionHistory=True)
        return {"status": "repaired", "neutral_conflicts": neutral_count,
                "down_conflicts": down_count,
                "unlocked_vertices": len(vertices),
                "crease_edges": len(crease_edges)}

    def _calibrate_eye_depth(self, mesh: str, eye_mesh: str,
                             eye_joint: str, eye_control: str,
                             eye_radius: float) -> dict[str, float | int | str]:
        """Seat a mobile-aperture eye behind its closed lid when geometry permits."""
        from maya.api import OpenMaya as om

        c = self._cmds
        def mesh_fn(name):
            selection = om.MSelectionList()
            selection.add(name)
            return om.MFnMesh(selection.getDagPath(0))

        head_fn, eye_fn = mesh_fn(mesh), mesh_fn(eye_mesh)
        bounds = c.exactWorldBoundingBox(eye_mesh)
        cx, cy = ((bounds[axis] + bounds[axis + 3]) / 2.
                  for axis in (0, 1))
        rx, ry = ((bounds[axis + 3] - bounds[axis]) / 2.
                  for axis in (0, 1))
        samples = [(cx + rx * ix / 10., cy + ry * iy / 10.)
                   for ix in range(-9, 10) for iy in range(-9, 10)]

        def front_depth(fn, x, y):
            hit = fn.closestIntersection(
                om.MFloatPoint(x, y, 1000.), om.MFloatVector(0., 0., -1.),
                om.MSpace.kWorld, 2000., False)
            return float(hit[0].z) if hit else None

        def measure(blink):
            c.setAttr(eye_control + ".blink", blink)
            eye_hits = visible = missing = 0
            maximum = 0.
            for x, y in samples:
                eye_z = front_depth(eye_fn, x, y)
                if eye_z is None:
                    continue
                eye_hits += 1
                lid_z = front_depth(head_fn, x, y)
                if lid_z is None or lid_z < bounds[2]:
                    visible += 1
                    missing += 1
                elif eye_z > lid_z + .001:
                    visible += 1
                    maximum = max(maximum, eye_z - lid_z)
            return eye_hits, visible, missing, maximum

        try:
            opened = measure(0)
            closed = measure(10)
            result = {"open_visible": opened[1],
                      "initial_closed_visible": closed[1],
                      "final_closed_visible": closed[1],
                      "initial_missing_front_surface": closed[2],
                      "initial_depth_deficit_cm": round(closed[3], 6),
                      "depth_limit_cm": round(eye_radius * .15, 6),
                      "applied_cm": 0., "status": "not_attempted"}
            if opened[0] < 50 or opened[1] < 20:
                result["status"] = "insufficient_open_visibility"
                return result
            if closed[2]:
                result["status"] = "missing_front_surface"
                return result
            if closed[1] / max(1, closed[0]) <= .01:
                result["status"] = "already_closed"
                return result
            correction = closed[3] + eye_radius * .03
            result["required_cm"] = round(correction, 6)
            if correction > eye_radius * .15:
                result["status"] = "depth_limit_exceeded"
                return result
            plugs = tuple(eye_joint + ".translate" + axis
                          for axis in "XYZ")
            if (c.referenceQuery(eye_joint, isNodeReferenced=True)
                    or any(c.getAttr(plug, lock=True)
                           or c.connectionInfo(plug, isDestination=True)
                           for plug in plugs)):
                result["status"] = "eye_joint_unavailable"
                return result
            position = c.xform(eye_joint, query=True, worldSpace=True,
                               translation=True)
            c.xform(eye_joint, worldSpace=True,
                    translation=(position[0], position[1],
                                 position[2] - correction))
            revised = measure(10)
            reopened = measure(0)
            if (revised[1] / max(1, revised[0]) > .01 or revised[2]
                    or reopened[1] < max(20, opened[1] * .8)):
                c.xform(eye_joint, worldSpace=True, translation=position)
                result["status"] = "calibration_rejected"
                return result
            result["final_closed_visible"] = revised[1]
            result["applied_cm"] = round(correction, 6)
            result["status"] = "aligned"
            return result
        finally:
            c.setAttr(eye_control + ".blink", 0)

    def _blink_control(self, side: FaceSide, layer: EyeLidLayer,
                       arc: str) -> str:
        if (not isinstance(side, FaceSide) or
                layer not in (EyeLidLayer.MAIN, EyeLidLayer.OUTER) or
                arc not in ("upper", "lower")):
            raise ValueError("眼睑修形的侧别、层级或上下眼睑无效")
        suffix = "_R" if side is FaceSide.RIGHT else "_L"
        name = ("ctrlUpper" if arc == "upper" else "ctrlLower") \
               + "EyeLid" + ("Outer" if layer is EyeLidLayer.OUTER else "") \
               + suffix
        controls = self._cmds.ls(name, long=True, type="transform") or []
        if len(controls) != 1 or any(not self._cmds.attributeQuery(
                "blinkOffset" + axis, node=controls[0], exists=True)
                for axis in "XYZ"):
            raise FitSkeletonValidationError("眼睑修形控制缺失；先建立眼睑绑定")
        return controls[0]

    def read_blink_offset(self, side: FaceSide, layer: EyeLidLayer,
                          arc: str) -> tuple[float, float, float]:
        control = self._blink_control(side, layer, arc)
        return tuple(float(self._cmds.getAttr(control + ".blinkOffset" + axis))
                     for axis in "XYZ")

    def set_blink_offset(self, side: FaceSide, layer: EyeLidLayer, arc: str,
                         offset: tuple[float, float, float]
                         ) -> tuple[float, float, float]:
        if len(offset) != 3 or any(not isfinite(value) for value in offset):
            raise ValueError("眼睑修形需要三个有限的局部位移值")
        control = self._blink_control(side, layer, arc)
        c = self._cmds
        if c.referenceQuery(control, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能修改引用中的眼睑修形控制")
        plugs = tuple(control + ".blinkOffset" + axis for axis in "XYZ")
        if any(c.getAttr(plug, lock=True) or
               c.connectionInfo(plug, isDestination=True) for plug in plugs):
            raise FitSkeletonValidationError("眼睑修形通道已锁定或由其他节点驱动")
        with self.transaction("调整眼睑闭眼修形"):
            self._transaction_changed = True
            for plug, value in zip(plugs, offset):
                c.setAttr(plug, float(value))
        return self.read_blink_offset(side, layer, arc)

    def read_outer_blink_offset(self, side: FaceSide,
                                arc: str) -> tuple[float, float, float]:
        return self.read_blink_offset(side, EyeLidLayer.OUTER, arc)

    def set_outer_blink_offset(self, side: FaceSide, arc: str,
                               offset: tuple[float, float, float]
                               ) -> tuple[float, float, float]:
        return self.set_blink_offset(side, EyeLidLayer.OUTER, arc, offset)

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
        main_factors = eyelid_skin_factors(adjacency, positions,
            area_vertices, boundary, main.upper_vertices,
            main.lower_vertices, inner_vertices)
        if mobile_inner:
            inner = ordered[EyeLidLayer.INNER]
            rim_factors = inner_eyelid_skin_factors(
                adjacency, positions, area_vertices,
                inner.upper_vertices, inner.lower_vertices)
            for vertex, pair in rim_factors.items():
                if sum(pair) > sum(main_factors[vertex]):
                    main_factors[vertex] = pair
            # A simple aperture follows Main, including both corner vertices.
            for vertex in inner.upper_vertices:
                main_factors[vertex] = (1., 0.)
            for vertex in inner.lower_vertices[1:-1]:
                main_factors[vertex] = (0., 1.)
        factors = {
            EyeLidLayer.MAIN: main_factors,
            EyeLidLayer.OUTER: outer_eyelid_skin_factors(adjacency,
                positions, area_vertices, outer.upper_vertices,
                outer.lower_vertices, inner_vertices, main_factors),
        }
        arcs = {(layer, "upper"): ordered[layer].upper_vertices
                for layer in (EyeLidLayer.MAIN, EyeLidLayer.OUTER)}
        arcs.update({(layer, "lower"): ordered[layer].lower_vertices
                     for layer in (EyeLidLayer.MAIN, EyeLidLayer.OUTER)})
        span = max(positions[index][0] for index in main.upper_vertices) \
             - min(positions[index][0] for index in main.upper_vertices)
        return (factors, arcs, positions, span, open_inner, mobile_inner,
                boundary | main_vertices)

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
        eye_meshes = {}
        eye_radii = {}
        eye_centers = {}
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
            eye_meshes[side] = eye_mesh
            eye_radii[side] = max(bounds[index + 3] - bounds[index]
                                  for index in range(3)) / 2.
            eye_centers[side] = tuple(float(value) for value in c.xform(
                pre.read_eye_ball_fit(side), query=True, worldSpace=True,
                translation=True))
        motion_plans = {side: EyeLidMotionPlan(eye_radii[side])
                        for side in FaceSide}
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
        fit_ring_vertices = {}
        for side in FaceSide:
            (factors[side], arcs[side], positions[side], spans[side],
             open_inners[side], mobile_inners[side],
             fit_ring_vertices[side]) = self._surface_factors(
                pre, mesh, side)
        face_scale = float(c.getAttr(fit + ".faceScale"))
        if not isfinite(face_scale) or face_scale <= 0:
            raise FitSkeletonValidationError("Face Mask 比例无效")
        outer_pose_scales = {side: min(face_scale / 14.43,
                                       eye_radii[side] * .5)
                             for side in FaceSide}
        layers = {side: (EyeLidLayer.MAIN, EyeLidLayer.OUTER)
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
                    arcs[side][(layer, "lower")], positions[side],
                    upper_share=.825)
                if layer is EyeLidLayer.OUTER:
                    blink_offsets[(side, layer)] = {
                        arc: tuple(0. for _ in values)
                        for arc, values in blink_offsets[(side, layer)].items()}
        vertical_follow_radii = dict(eye_radii)
        for side in FaceSide:
            if not mobile_inners[side]:
                continue
            aperture_height = eye_lid_aperture_height(
                arcs[side][(EyeLidLayer.MAIN, "upper")],
                arcs[side][(EyeLidLayer.MAIN, "lower")], positions[side])
            vertical_follow_radii[side] = min(eye_radii[side],
                                               aperture_height)
        names = ["FaceJoint_M", "EyeLidJoints_M", "FaceMotionSystem"]
        for side in FaceSide:
            suffix = "_R" if side is FaceSide.RIGHT else "_L"
            names.extend(("ctrlEye" + suffix,
                          "ctrlEye" + suffix + "_Offset",
                          "ctrlEye" + suffix + "BlinkFraction",
                          "ctrlEye" + suffix + "BlinkReverse"))
            if mobile_inners[side]:
                names.extend("AdvPy_EyeYawBlinkBack" + suffix + part
                             for part in ("Offset", "Limit", "Scale",
                                          "Blink", "Sum"))
            if open_inners[side] and not mobile_inners[side]:
                names.extend("ctrlEye" + suffix + label for label in (
                    "YawNegative", "YawMagnitude", "YawLimit",
                    "YawDepthScale", "MidBlink", "MidBlinkScale",
                    "MidGazeDepth"))
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
                    if arc == "lower" and mobile_inners[side]:
                        names.extend((control + "UpwardFollow",
                                      control + "UpwardBlink",
                                      control + "UpwardScale",
                                      control + "UpwardSum"))
                    if arc == "upper" and mobile_inners[side]:
                        names.extend((control + "YawNegative",
                                      control + "YawMagnitude",
                                      control + "YawDepthScale",
                                      control + "YawDepthLimit",
                                      control + "YawDepthBlink"))
                    if layer is EyeLidLayer.OUTER and mobile_inners[side]:
                        if arc == "lower":
                            names.extend((control + "YawNegative",
                                          control + "YawMagnitude"))
                        names.extend((control + "YawEdgeOffset",
                                      control + "YawEdgeLimit",
                                      control + "YawEdgeScale",
                                      control + "YawEdgeBlink"))
                    if layer in (EyeLidLayer.MAIN, EyeLidLayer.OUTER):
                        names.extend((control + "BlinkFraction",
                                      control + "BlinkOffset"))
                    curve_name = arc + "Lid" + layer.value + "WorkCurve" + suffix
                    names.append(curve_name)
                    for index in range(len(arcs[side][(layer, arc)])):
                        names.extend((curve_name + str(index) + "Scale",
                                      curve_name + str(index) + "Sum",
                                      curve_name + str(index) + "Blink"))
                    for index in range(1, len(arcs[side][(layer, arc)]) - 1):
                        name = arc + "Lid" + layer.value + str(index) + suffix
                        names.extend((name, name + "POCI", name + "Offset"))
                        if layer is EyeLidLayer.MAIN:
                            if open_inners[side] and not mobile_inners[side]:
                                names.extend((name + "Aim", name + "AimTarget",
                                              name + "AimConstraint"))
                            else:
                                names.append(name + "BlinkRoll")
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
                eye_fraction = fraction
                stationary_mid_depth = None
                if open_inners[side] and not mobile_inners[side]:
                    negative = c.createNode("multDoubleLinear",
                        name=eye_name + "YawNegative")
                    c.setAttr(negative + ".input2", -1.)
                    c.connectAttr(eye_joints[side] + ".rotateY",
                                  negative + ".input1")
                    magnitude = c.createNode("condition",
                        name=eye_name + "YawMagnitude")
                    c.setAttr(magnitude + ".operation", 2)
                    c.connectAttr(eye_joints[side] + ".rotateY",
                                  magnitude + ".firstTerm")
                    c.connectAttr(eye_joints[side] + ".rotateY",
                                  magnitude + ".colorIfTrueR")
                    c.connectAttr(negative + ".output",
                                  magnitude + ".colorIfFalseR")
                    limit = c.createNode("clamp", name=eye_name + "YawLimit")
                    c.setAttr(limit + ".maxR",
                              motion_plans[side].stationary_mid_gaze_full_angle_deg)
                    c.connectAttr(magnitude + ".outColorR",
                                  limit + ".inputR")
                    yaw_scale = c.createNode("multDoubleLinear",
                        name=eye_name + "YawDepthScale")
                    c.setAttr(yaw_scale + ".input2",
                              motion_plans[side].stationary_mid_gaze_slope_cm_per_degree)
                    c.connectAttr(limit + ".outputR",
                                  yaw_scale + ".input1")
                    mid_blink = c.createNode("multDoubleLinear",
                        name=eye_name + "MidBlink")
                    c.connectAttr(fraction + ".outputX",
                                  mid_blink + ".input1")
                    c.connectAttr(reverse + ".outputX",
                                  mid_blink + ".input2")
                    mid_scale = c.createNode("multDoubleLinear",
                        name=eye_name + "MidBlinkScale")
                    c.setAttr(mid_scale + ".input2", 4.)
                    c.connectAttr(mid_blink + ".output",
                                  mid_scale + ".input1")
                    stationary_mid_depth = c.createNode("multDoubleLinear",
                        name=eye_name + "MidGazeDepth")
                    c.connectAttr(yaw_scale + ".output",
                                  stationary_mid_depth + ".input1")
                    c.connectAttr(mid_scale + ".output",
                                  stationary_mid_depth + ".input2")
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
                        # A fixed inner aperture tears if Main/Outer chase yaw.
                        c.setAttr(conversion + ".input2X",
                                  eye_radii[side] * radians(1.) * .1
                                  if mobile_inners[side] else 0.)
                        c.setAttr(conversion + ".input2Y",
                                  -vertical_follow_radii[side] *
                                  radians(1.) * .1)
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
                        c.connectAttr(reverse + ".outputX",
                                      blink_fade + ".input2X")
                        c.connectAttr(reverse + ".outputX",
                                      blink_fade + ".input2Y")
                        motion_sum = c.createNode("plusMinusAverage",
                            name=control_name + "MotionSum")
                        c.connectAttr(control + ".translate",
                                      motion_sum + ".input3D[0]")
                        if arc == "upper" and stationary_mid_depth:
                            c.connectAttr(stationary_mid_depth + ".output",
                                motion_sum + ".input3D[5].input3Dz")
                        if arc == "lower" and mobile_inners[side]:
                            upward = c.createNode("clamp",
                                name=control_name + "UpwardFollow")
                            c.setAttr(upward + ".maxR",
                                      eye_radii[side] * 10.)
                            c.connectAttr(amount + ".outputY",
                                          upward + ".inputR")
                            upward_blink = c.createNode("multiplyDivide",
                                name=control_name + "UpwardBlink")
                            c.connectAttr(upward + ".outputR",
                                          upward_blink + ".input1X")
                            c.connectAttr(eye_fraction + ".outputX",
                                          upward_blink + ".input2X")
                            upward_scale = c.createNode("multDoubleLinear",
                                name=control_name + "UpwardScale")
                            c.setAttr(upward_scale + ".input2",
                                      _CLOSED_LOWER_UPWARD_FOLLOW)
                            c.connectAttr(upward_blink + ".outputX",
                                          upward_scale + ".input1")
                            upward_sum = c.createNode("plusMinusAverage",
                                name=control_name + "UpwardSum")
                            c.connectAttr(blink_fade + ".outputY",
                                          upward_sum + ".input1D[0]")
                            c.connectAttr(upward_scale + ".output",
                                          upward_sum + ".input1D[1]")
                            c.connectAttr(blink_fade + ".outputX",
                                          motion_sum + ".input3D[1].input3Dx")
                            c.connectAttr(upward_sum + ".output1D",
                                          motion_sum + ".input3D[1].input3Dy")
                        else:
                            c.connectAttr(blink_fade + ".output",
                                          motion_sum + ".input3D[1]")
                        if arc == "upper" and mobile_inners[side]:
                            negative = c.createNode("multDoubleLinear",
                                name=control_name + "YawNegative")
                            c.setAttr(negative + ".input2", -1.)
                            c.connectAttr(eye_joints[side] + ".rotateY",
                                          negative + ".input1")
                            magnitude = c.createNode("condition",
                                name=control_name + "YawMagnitude")
                            c.setAttr(magnitude + ".operation", 2)
                            c.connectAttr(eye_joints[side] + ".rotateY",
                                          magnitude + ".firstTerm")
                            c.connectAttr(eye_joints[side] + ".rotateY",
                                          magnitude + ".colorIfTrueR")
                            c.connectAttr(negative + ".output",
                                          magnitude + ".colorIfFalseR")
                            depth_scale = c.createNode("multDoubleLinear",
                                name=control_name + "YawDepthScale")
                            c.setAttr(depth_scale + ".input2",
                                motion_plans[side].yaw_depth_slope_cm_per_degree)
                            c.connectAttr(magnitude + ".outColorR",
                                          depth_scale + ".input1")
                            depth_limit = c.createNode("clamp",
                                name=control_name + "YawDepthLimit")
                            c.setAttr(depth_limit + ".maxR",
                                motion_plans[side].yaw_depth_limit_cm)
                            c.connectAttr(depth_scale + ".output",
                                          depth_limit + ".inputR")
                            depth_blink = c.createNode("multiplyDivide",
                                name=control_name + "YawDepthBlink")
                            c.connectAttr(depth_limit + ".outputR",
                                          depth_blink + ".input1X")
                            c.connectAttr(eye_fraction + ".outputX",
                                          depth_blink + ".input2X")
                            c.connectAttr(depth_blink + ".outputX",
                                motion_sum + ".input3D[3].input3Dz")
                        if layer is EyeLidLayer.OUTER and mobile_inners[side]:
                            if arc == "lower":
                                negative = c.createNode("multDoubleLinear",
                                    name=control_name + "YawNegative")
                                c.setAttr(negative + ".input2", -1.)
                                c.connectAttr(eye_joints[side] + ".rotateY",
                                              negative + ".input1")
                                magnitude = c.createNode("condition",
                                    name=control_name + "YawMagnitude")
                                c.setAttr(magnitude + ".operation", 2)
                                c.connectAttr(eye_joints[side] + ".rotateY",
                                              magnitude + ".firstTerm")
                                c.connectAttr(eye_joints[side] + ".rotateY",
                                              magnitude + ".colorIfTrueR")
                                c.connectAttr(negative + ".output",
                                              magnitude + ".colorIfFalseR")
                            edge_offset = c.createNode("addDoubleLinear",
                                name=control_name + "YawEdgeOffset")
                            c.setAttr(edge_offset + ".input2",
                                      -motion_plans[side].yaw_edge_start_angle_deg)
                            c.connectAttr(magnitude + ".outColorR",
                                          edge_offset + ".input1")
                            edge_limit = c.createNode("clamp",
                                name=control_name + "YawEdgeLimit")
                            c.setAttr(edge_limit + ".maxR",
                                motion_plans[side].yaw_edge_span_deg)
                            c.connectAttr(edge_offset + ".output",
                                          edge_limit + ".inputR")
                            edge_scale = c.createNode("multDoubleLinear",
                                name=control_name + "YawEdgeScale")
                            c.setAttr(edge_scale + ".input2",
                                motion_plans[side].yaw_edge_slope_cm_per_degree(arc))
                            c.connectAttr(edge_limit + ".outputR",
                                          edge_scale + ".input1")
                            edge_blink = c.createNode("multiplyDivide",
                                name=control_name + "YawEdgeBlink")
                            c.connectAttr(edge_scale + ".output",
                                          edge_blink + ".input1X")
                            c.connectAttr(eye_fraction + ".outputX",
                                          edge_blink + ".input2X")
                            c.connectAttr(edge_blink + ".outputX",
                                motion_sum + ".input3D[4].input3Dz")
                        if layer in (EyeLidLayer.MAIN, EyeLidLayer.OUTER):
                            fraction = c.createNode("multiplyDivide",
                                name=control_name + "BlinkFraction")
                            c.setAttr(fraction + ".input2X", .1)
                            c.connectAttr(eye_control + ".blink",
                                          fraction + ".input1X")
                            correction = c.createNode("multiplyDivide",
                                name=control_name + "BlinkOffset")
                            for axis in "XYZ":
                                default = 0.
                                if layer is EyeLidLayer.OUTER and mobile_inners[side]:
                                    scale = outer_pose_scales[side]
                                    if axis == "X":
                                        default = scale * (.05 if arc == "upper"
                                            else .1) * (1 if side is FaceSide.RIGHT
                                            else -1)
                                    elif axis == "Y":
                                        default = scale * (-.07 if arc == "upper"
                                            else .1)
                                elif (layer is EyeLidLayer.OUTER and
                                      open_inners[side] and
                                      not mobile_inners[side]):
                                    horizontal, vertical = (
                                        motion_plans[side].stationary_outer_offset_cm(
                                            arc, 1 if side is FaceSide.RIGHT else -1))
                                    if axis == "X":
                                        default = horizontal
                                    elif axis == "Y":
                                        default = vertical
                                elif (layer is EyeLidLayer.MAIN and
                                      arc == "lower" and axis == "Y" and
                                      open_inners[side] and
                                      not mobile_inners[side]):
                                    default = motion_plans[side].stationary_lower_main_seal_cm
                                c.addAttr(control,
                                    longName="blinkOffset" + axis,
                                    attributeType="double", keyable=True,
                                    defaultValue=default)
                                c.connectAttr(control + ".blinkOffset" + axis,
                                              correction + ".input1" + axis)
                                c.connectAttr(fraction + ".outputX",
                                              correction + ".input2" + axis)
                            c.connectAttr(correction + ".output",
                                          motion_sum + ".input3D[2]")
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
                            if layer is EyeLidLayer.MAIN:
                                depth_offset, _ = eye_lid_sphere_blink(
                                    positions[side][vertices[index]],
                                    eye_centers[side],
                                    blink_offsets[(side, layer)][arc][index])
                                c.setAttr(blink + ".input2Z",
                                          depth_offset / 10.)
                                c.connectAttr(eye_control + ".blink",
                                              blink + ".input1Z")
                                c.connectAttr(blink + ".outputZ",
                                              addition + ".input3D[2].input3Dz")
                            c.connectAttr(addition + ".output3D", point_plug)
                        for index, vertex in enumerate(vertices[1:-1], 1):
                            name = arc + "Lid" + layer.value + str(index) + suffix
                            point = c.createNode("pointOnCurveInfo",
                                                 name=name + "POCI")
                            c.connectAttr(curve_shape + ".worldSpace[0]",
                                          point + ".inputCurve")
                            c.setAttr(point + ".parameter", index)
                            stationary_main = (layer is EyeLidLayer.MAIN and
                                open_inners[side] and not mobile_inners[side])
                            if stationary_main:
                                aim = c.createNode("transform", name=name + "Aim",
                                                   parent=root)
                                c.setAttr(aim + ".inheritsTransform", False)
                                c.setAttr(aim + ".translate", *eye_centers[side],
                                          type="double3")
                                target = c.createNode("transform",
                                    name=name + "AimTarget", parent=root)
                                c.setAttr(target + ".inheritsTransform", False)
                                c.connectAttr(point + ".position",
                                              target + ".translate")
                                c.aimConstraint(target, aim, aimVector=(1, 0, 0),
                                                upVector=(0, 1, 0),
                                                worldUpType="vector",
                                                worldUpVector=(0, 1, 0),
                                                name=name + "AimConstraint")
                                joint_offset = c.createNode("transform",
                                    name=name + "Offset", parent=aim)
                                c.setAttr(joint_offset + ".translateX",
                                    dist(positions[side][vertex], eye_centers[side]))
                            else:
                                joint_offset = c.createNode("transform",
                                    name=name + "Offset", parent=root)
                                c.setAttr(joint_offset + ".inheritsTransform", False)
                                c.connectAttr(point + ".position",
                                              joint_offset + ".translate")
                            c.select(clear=True)
                            joint = c.joint(name=name)
                            joint = c.parent(joint, joint_offset,
                                             relative=True)[0]
                            if layer is EyeLidLayer.MAIN and not stationary_main:
                                delta_y = blink_offsets[(side, layer)][arc][index]
                                _, angle = eye_lid_sphere_blink(
                                    positions[side][vertex],
                                    eye_centers[side], delta_y)
                                roll = c.createNode("multiplyDivide",
                                    name=name + "BlinkRoll")
                                c.setAttr(roll + ".input2X", angle / 10.)
                                c.connectAttr(eye_control + ".blink",
                                              roll + ".input1X")
                                c.connectAttr(roll + ".outputX",
                                              joint + ".rotateX")
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
                    raise FitSkeletonValidationError(
                        f"眼睑区域顶点 {vertex} 的权重之和为 "
                        f"{1. - remaining:.6f}，超过 1")
                for source_index, target_index in enumerate(old_indices):
                    values[vertex * new_width + target_index] = (
                        before[vertex * old_width + source_index] * remaining)
                for key, target_index in lid_indices.items():
                    values[vertex * new_width + target_index] = (
                        lid_weights.get(key, 0.))
            self.apply_dense_skin(DenseSkinWeights(skin,
                original.vertex_count, new_names, values.tobytes()))
            for side in FaceSide:
                area_vertices = set(factors[side][EyeLidLayer.MAIN])
                smooth = area_vertices - fit_ring_vertices[side]
                if smooth:
                    c.select([f"{mesh}.vtx[{vertex}]"
                              for vertex in sorted(smooth)], replace=True)
                    c.skinCluster(skin, edit=True, smoothWeights=0,
                                  smoothWeightsMaxIterations=5,
                                  obeyMaxInfluences=False)
            method = int(c.getAttr(skin + ".skinningMethod"))
            if method == 0:
                blend = array("d", [0.] * original.vertex_count)
            elif method == 1:
                blend = array("d", [1.] * original.vertex_count)
            elif method == 2:
                blend = self.capture_skin_blend_weights(skin)
            else:
                raise FitSkeletonValidationError("Face Skin 变形方式无效")
            for side in FaceSide:
                for vertex in factors[side][EyeLidLayer.MAIN]:
                    blend[vertex] = 1.
            self.apply_skin_blend_weights(skin, blend)
            c.setAttr(skin + ".skinningMethod", 2)
            eye_depth_alignment = {}
            yaw_blink_eye_back = {}
            for side in FaceSide:
                suffix = "R" if side is FaceSide.RIGHT else "L"
                if mobile_inners[side]:
                    eye_depth_alignment[side.value] = self._calibrate_eye_depth(
                        mesh, eye_meshes[side], eye_joints[side],
                        eye_control_names[side], eye_radii[side])
                else:
                    eye_depth_alignment[side.value] = {
                        "applied_cm": 0., "status": "stationary_aperture"}
                c.addAttr(motion,
                    longName="advPyEyeDepthCorrection" + suffix,
                    attributeType="double",
                    defaultValue=eye_depth_alignment[side.value]["applied_cm"])
                c.setAttr(motion + ".advPyEyeDepthCorrection" + suffix,
                          lock=True)
                eye_joint = eye_joints[side]
                if (not mobile_inners[side] or
                        eye_depth_alignment[side.value]["status"] != "aligned"):
                    yaw_blink_eye_back[side.value] = {
                        "status": "not_needed", "maximum_cm": 0.}
                    continue
                depth_plug = eye_joint + ".translateZ"
                if not c.getAttr(depth_plug, settable=True):
                    yaw_blink_eye_back[side.value] = {
                        "status": "eye_joint_unavailable", "maximum_cm": 0.}
                    continue
                label = "AdvPy_EyeYawBlinkBack_" + suffix
                yaw_magnitude = c.ls(
                    "ctrlUpperEyeLidOuter_" + suffix + "YawMagnitude",
                    long=True, type="condition")
                if len(yaw_magnitude) != 1:
                    raise FitSkeletonValidationError(
                        "外眼睑转眼角度驱动缺失")
                offset = c.createNode("addDoubleLinear",
                                      name=label + "Offset")
                c.setAttr(offset + ".input2",
                          -motion_plans[side].yaw_edge_start_angle_deg)
                c.connectAttr(yaw_magnitude[0] + ".outColorR",
                              offset + ".input1")
                limit = c.createNode("clamp", name=label + "Limit")
                angle_span = motion_plans[side].yaw_edge_span_deg
                c.setAttr(limit + ".maxR", angle_span)
                c.connectAttr(offset + ".output", limit + ".inputR")
                scale = c.createNode("multDoubleLinear",
                                     name=label + "Scale")
                maximum = motion_plans[side].yaw_blink_eye_back_limit_cm
                c.setAttr(scale + ".input2",
                          motion_plans[side].yaw_blink_eye_back_slope_cm_per_degree)
                c.connectAttr(limit + ".outputR", scale + ".input1")
                blink = c.createNode("multDoubleLinear",
                                     name=label + "Blink")
                c.connectAttr(scale + ".output", blink + ".input1")
                fraction = c.ls("ctrlEye_" + suffix + "BlinkFraction",
                                long=True, type="multiplyDivide")
                if len(fraction) != 1:
                    raise FitSkeletonValidationError("眨眼比例驱动缺失")
                c.connectAttr(fraction[0] + ".outputX",
                              blink + ".input2")
                depth = c.createNode("addDoubleLinear",
                                     name=label + "Sum")
                c.setAttr(depth + ".input1", c.getAttr(depth_plug))
                c.connectAttr(blink + ".output", depth + ".input2")
                c.connectAttr(depth + ".output", depth_plug)
                yaw_blink_eye_back[side.value] = {
                    "status": "driven", "maximum_cm": round(maximum, 6)}
            normal_repair = self._repair_eye_lid_normals(
                mesh, pre, eye_radii, mobile_inners, eye_control_names)
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
                "eye_fit_centers_cm": {side.value: tuple(
                    round(value, 6) for value in eye_centers[side])
                    for side in FaceSide},
                "eye_depth_alignment": eye_depth_alignment,
                "yaw_blink_eye_back": yaw_blink_eye_back,
                "normal_repair": normal_repair,
                "work_curves": work_curves,
                "area_vertices": {side.value: len(weighted(side))
                                  for side in FaceSide},
                "main_vertices": {side.value: len(factors[side][
                    EyeLidLayer.MAIN]) for side in FaceSide},
                "outer_vertices": {side.value: len(factors[side][
                    EyeLidLayer.OUTER]) for side in FaceSide}}
