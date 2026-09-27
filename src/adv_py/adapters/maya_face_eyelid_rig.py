"""Build an initial joint-driven eyelid layer from bilateral Face Fit bands."""
from __future__ import annotations

from array import array
import json
import re

from adv_py.application.face_pre import EyeLidLayer, FacePreRole, FaceSide
from adv_py.core.dense_skin_transfer import DenseSkinWeights
from adv_py.core.face_build_requirements import FaceInclude
from adv_py.core.face_eyelid_fit import order_eye_lid_loop
from adv_py.core.face_eyelid_skin import eyelid_skin_factors
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_dense_skin import MayaDenseSkinHost
from .maya_face_build import MayaFaceBuildHost


_COMPONENT = re.compile(r"\.((?:e)|(?:f)|(?:vtx))\[(\d+)\]$")


class MayaFaceEyeLidRigHost(MayaDenseSkinHost):
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
        main_edges, corners = rings[EyeLidLayer.MAIN]
        main_points = {vertex: positions[vertex]
                       for _, first, second in main_edges
                       for vertex in (first, second)}
        eye_y = float(c.xform(pre.read_eye_ball_fit(side), query=True,
                              worldSpace=True, translation=True)[1])
        ordered = order_eye_lid_loop(main_edges, main_points,
                    eye_center_y=eye_y, corner_vertices=corners,
                    side=side.value)
        boundary = {vertex for layer in (EyeLidLayer.OUTER,
                        EyeLidLayer.INNER)
                    for _, first, second in rings[layer][0]
                    for vertex in (first, second)}
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
        factors = eyelid_skin_factors(adjacency, positions, area_vertices,
                    boundary, ordered.upper_vertices,
                    ordered.lower_vertices)
        centers = {}
        for arc, vertices in (("upper", ordered.upper_vertices),
                              ("lower", ordered.lower_vertices)):
            interior = vertices[1:-1]
            centers[arc] = tuple(sum(positions[index][axis]
                               for index in interior) / len(interior)
                               for axis in range(3))
        span = max(positions[index][0] for index in ordered.upper_vertices) \
             - min(positions[index][0] for index in ordered.upper_vertices)
        return factors, centers, span

    def build(self) -> dict:
        c = self._cmds
        pre = MayaFaceBuildHost(namespace=self.namespace)
        readiness = pre.inspect_build_inputs()
        if not readiness["ready"]:
            raise FitSkeletonValidationError("FaceSetup 输入缺失："
                                             + "、".join(readiness["missing"]))
        if (pre.read_include() is not FaceInclude.EYES_ONLY
                or not readiness["non_symmetrical"]):
            raise FitSkeletonValidationError(
                "当前眼睑构建阶段需要 Skip Above+Below Eyes 与左右独立 Fit")
        mesh = pre.read_face_objects(FacePreRole.FACE)[0]
        fit = pre._fit(required=True)
        head_name = c.getAttr(fit + ".HeadJoint")
        heads = c.ls(head_name, long=True, type="joint") or []
        if len(heads) != 1 or c.referenceQuery(heads[0], isNodeReferenced=True):
            raise FitSkeletonValidationError("Head 关节缺失、重名或属于引用")
        head = heads[0]
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        history = c.listHistory(shapes[0], pruneDagObjects=True) or []
        skins = [item for item in history if c.nodeType(item) == "skinCluster"]
        if len(skins) != 1:
            raise FitSkeletonValidationError("Face 网格需要唯一 Skin")
        skin = skins[0]
        names = ("FaceJoint_M", "EyeLidJoints_M", "FaceMotionSystem",
                 "ctrlUpperEyeLid_R", "ctrlLowerEyeLid_R",
                 "ctrlUpperEyeLid_L", "ctrlLowerEyeLid_L",
                 "ctrlUpperEyeLid_R_Offset", "ctrlLowerEyeLid_R_Offset",
                 "ctrlUpperEyeLid_L_Offset", "ctrlLowerEyeLid_L_Offset",
                 "upperLidMain_R", "lowerLidMain_R",
                 "upperLidMain_L", "lowerLidMain_L")
        if any(c.ls(name) for name in names):
            raise FitSkeletonValidationError("眼睑绑定节点名称已被占用")
        if c.referenceQuery(mesh, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能在引用中的 Face 网格写入眼睑权重")
        factors = {}
        centers = {}
        spans = {}
        for side in FaceSide:
            factors[side], centers[side], spans[side] = self._surface_factors(
                pre, mesh, side)
        if set(factors[FaceSide.RIGHT]) & set(factors[FaceSide.LEFT]):
            raise FitSkeletonValidationError("左右眼睑区域发生重叠")
        original = self.capture_dense_skin(skin)
        selected = c.ls(selection=True, long=True) or []
        joint_names = {}
        control_names = {}
        with self.transaction("建立双侧眼睑关节与 Skin"):
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
                for arc in ("upper", "lower"):
                    label = "Upper" if arc == "upper" else "Lower"
                    c.select(clear=True)
                    joint = c.joint(name=arc + "LidMain" + suffix,
                                    position=centers[side][arc])
                    joint = c.parent(joint, root, absolute=True)[0]
                    c.setAttr(joint + ".radius", max(spans[side] / 30., .001))
                    c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind",
                              dataType="string")
                    c.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                              "face-eyelid-v1", type="string", lock=True)
                    control = c.circle(name="ctrl" + label + "EyeLid" + suffix,
                        normal=(0, 0, 1), radius=max(spans[side] / 8., .005),
                        constructionHistory=False)[0]
                    offset = c.createNode("transform",
                        name="ctrl" + label + "EyeLid" + suffix + "_Offset",
                        parent=motion)
                    c.xform(offset, worldSpace=True,
                            translation=centers[side][arc])
                    control = c.parent(control, offset, relative=True)[0]
                    c.pointConstraint(control, joint, maintainOffset=True)
                    c.skinCluster(skin, edit=True, addInfluence=joint,
                                  weight=0.0)
                    joint_names[(side, arc)] = joint.rsplit("|", 1)[-1]
                    control_names[(side, arc)] = control.rsplit("|", 1)[-1]
            target_skin = self.capture_dense_skin(skin)
            old_width = len(original.influence_names)
            new_names = target_skin.influence_names
            new_width = len(new_names)
            old_indices = [new_names.index(name) for name in
                           original.influence_names]
            lid_indices = {key: new_names.index(name) for key, name in
                           joint_names.items()}
            before = memoryview(original.values).cast("d")
            values = array("d", [0.] * (original.vertex_count * new_width))
            for vertex in range(original.vertex_count):
                lid_weights = {key: factors[key[0]].get(vertex, (0., 0.))[
                    0 if key[1] == "upper" else 1] for key in joint_names}
                remaining = 1. - sum(lid_weights.values())
                for source_index, target_index in enumerate(old_indices):
                    values[vertex * new_width + target_index] = (
                        before[vertex * old_width + source_index] * remaining)
                for key, target_index in lid_indices.items():
                    values[vertex * new_width + target_index] = lid_weights[key]
            self.apply_dense_skin(DenseSkinWeights(skin,
                original.vertex_count, new_names, values.tobytes()))
            c.addAttr(motion, longName="advPyFaceMesh", dataType="string")
            c.setAttr(motion + ".advPyFaceMesh", mesh, type="string")
            c.select(selected, replace=True) if selected else c.select(clear=True)
        return {"skin": skin, "mesh": mesh,
                "controls": control_names, "joints": joint_names,
                "area_vertices": {side.value: len(factors[side])
                                  for side in FaceSide}}
