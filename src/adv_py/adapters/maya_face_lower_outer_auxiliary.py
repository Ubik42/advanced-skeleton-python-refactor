"""Scene port for the simpler-eyelid lower Outer auxiliary influence."""
from __future__ import annotations

import re

from adv_py.application.face_pre import EyeLidLayer, FacePreRole, FaceSide
from adv_py.core.face_lower_outer_auxiliary import (
    FaceLowerOuterAuxiliaryInput, FaceLowerOuterAuxiliaryPlan,
)
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face_build import MayaFaceBuildHost


_FACE = re.compile(r"\.f\[(\d+)\]$")


class MayaFaceLowerOuterAuxiliaryMixin:
    def _lower_outer_skin(self):
        c = self._cmds
        pre = MayaFaceBuildHost(namespace=self.namespace)
        mesh = pre.read_face_objects(FacePreRole.FACE)[0]
        shape = (c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or [None])[0]
        if shape is None:
            raise FitSkeletonValidationError("眼下外围 Face 网格 Shape 缺失")
        skins = [node for node in (c.listHistory(shape,
                  pruneDagObjects=True) or [])
                 if c.nodeType(node) == "skinCluster"]
        if len(skins) != 1:
            raise FitSkeletonValidationError("眼下外围需要唯一 Face Skin")
        return mesh, shape, skins[0]

    def capture_lower_outer_auxiliary_input(
        self, side: str, simpler_eyelid: bool,
    ) -> FaceLowerOuterAuxiliaryInput:
        if side not in ("R", "L"):
            raise ValueError("眼下外围侧别无效")
        from maya.api import OpenMaya as om

        c = self._cmds
        face_side = FaceSide.RIGHT if side == "R" else FaceSide.LEFT
        pre = MayaFaceBuildHost(namespace=self.namespace)
        mesh, shape, _ = self._lower_outer_skin()
        (_, _, positions, _, _, _,
         _) = self._surface_factors(pre, mesh, face_side)
        curve = pre.read_eye_lid_fit(EyeLidLayer.OUTER, face_side)[1]
        curve_shape = (c.listRelatives(
            curve, shapes=True, noIntermediate=True,
            fullPath=True, type="nurbsCurve") or [None])[0]
        if curve_shape is None:
            raise FitSkeletonValidationError("眼下外围下弧曲线 Shape 缺失")
        spans = int(c.getAttr(curve_shape + ".spans"))
        degree = int(c.getAttr(curve_shape + ".degree"))
        points = tuple(tuple(float(value) for value in c.xform(
            f"{curve}.cv[{index}]", query=True, worldSpace=True,
            translation=True)) for index in range(spans + degree))
        selection = om.MSelectionList()
        selection.add(shape)
        dag = selection.getDagPath(0)
        fn = om.MFnMesh(dag)
        vertex_it = om.MItMeshVertex(dag)
        adjacency = {}
        for index in range(fn.numVertices):
            vertex_it.setIndex(index)
            adjacency[index] = frozenset(
                int(neighbor) for neighbor in
                vertex_it.getConnectedVertices())
        holder, _ = pre.read_eye_lid_area(face_side)
        faces = []
        for item in (c.getAttr(holder + ".selection") or "").split():
            match = _FACE.search(item)
            if not item.startswith(mesh + ".") or match is None:
                raise FitSkeletonValidationError(
                    "眼下外围眼睑区域面记录无效")
            faces.append(int(match.group(1)))
        area_vertices = frozenset(
            int(vertex) for face in faces
            for vertex in fn.getPolygonVertices(face))
        return FaceLowerOuterAuxiliaryInput(
            side, simpler_eyelid, spans, points, positions,
            adjacency, area_vertices)

    def preflight_lower_outer_auxiliary(
        self, plan: FaceLowerOuterAuxiliaryPlan,
    ) -> None:
        c = self._cmds
        mesh, _, skin = self._lower_outer_skin()
        names = (plan.control_name, plan.control_name + "Offset",
                 plan.joint_name, plan.joint_name + "ParentConstraint")
        if any(c.objExists(name) for name in names):
            raise FitSkeletonValidationError("眼下外围辅助节点名称冲突")
        if (len(c.ls("FaceJoint_M", long=True, type="joint") or []) != 1
                or len(c.ls("FaceMotionSystem", long=True,
                            type="transform") or []) != 1
                or plan.seed_vertex >= c.polyEvaluate(mesh, vertex=True)
                or c.referenceQuery(mesh, isNodeReferenced=True)
                or c.referenceQuery(skin, isNodeReferenced=True)):
            raise FitSkeletonValidationError("眼下外围构建目标不可写或不完整")

    def create_lower_outer_auxiliary(
        self, plan: FaceLowerOuterAuxiliaryPlan,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        _, _, skin = self._lower_outer_skin()
        face_joint = c.ls("FaceJoint_M", long=True, type="joint")[0]
        motion = c.ls("FaceMotionSystem", long=True,
                      type="transform")[0]
        control = c.circle(name=plan.control_name,
                           normal=(0, 0, 1), radius=.15,
                           constructionHistory=False)[0]
        offset = c.createNode("transform",
                              name=plan.control_name + "Offset",
                              parent=motion)
        c.xform(offset, worldSpace=True, translation=plan.world_position)
        c.parent(control, offset, relative=True)
        joint = c.createNode("joint", name=plan.joint_name,
                             parent=face_joint, skipSelect=True)
        c.xform(joint, worldSpace=True, translation=plan.world_position)
        c.setAttr(joint + ".drawStyle", 2)
        c.setAttr(joint + ".segmentScaleCompensate", 0)
        c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind",
                  dataType="string")
        c.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                  "face-lower-outer-v1", type="string", lock=True)
        c.parentConstraint(control, joint, maintainOffset=True,
                           name=plan.joint_name + "ParentConstraint")
        c.skinCluster(skin, edit=True, addInfluence=joint, weight=0.)
        self._transaction_changed = True

    def set_lower_outer_auxiliary_seed_weight(
        self, plan: FaceLowerOuterAuxiliaryPlan, weight: float,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        mesh, _, skin = self._lower_outer_skin()
        c.skinPercent(skin, f"{mesh}.vtx[{plan.seed_vertex}]",
                      transformValue=(plan.joint_name, weight))
        self._transaction_changed = True

    def smooth_lower_outer_auxiliary_weights(
        self, plan: FaceLowerOuterAuxiliaryPlan,
        vertices: tuple[int, ...],
    ) -> None:
        self._require_transaction()
        c = self._cmds
        mesh, _, skin = self._lower_outer_skin()
        previous = c.ls(selection=True, long=True) or []
        try:
            c.select([f"{mesh}.vtx[{index}]" for index in vertices],
                     replace=True)
            c.skinCluster(skin, edit=True, smoothWeights=0,
                          smoothWeightsMaxIterations=plan.smooth_iterations,
                          obeyMaxInfluences=False)
            self._transaction_changed = True
        finally:
            c.select(previous, replace=True) if previous else c.select(clear=True)

    def capture_lower_outer_auxiliary(
        self, plan: FaceLowerOuterAuxiliaryPlan,
    ) -> bool:
        c = self._cmds
        mesh, _, skin = self._lower_outer_skin()
        controls = c.ls(plan.control_name, long=True,
                        type="transform") or []
        joints = c.ls(plan.joint_name, long=True, type="joint") or []
        offsets = c.ls(plan.control_name + "Offset", long=True,
                       type="transform") or []
        face_joints = c.ls("FaceJoint_M", long=True, type="joint") or []
        constraints = c.ls(plan.joint_name + "ParentConstraint",
                           type="parentConstraint") or []
        if (len(controls) != 1 or len(joints) != 1
                or len(offsets) != 1 or len(face_joints) != 1
                or len(constraints) != 1
                or (c.listRelatives(controls[0], parent=True,
                                    fullPath=True) or []) != offsets
                or (c.listRelatives(joints[0], parent=True,
                                    fullPath=True) or []) != face_joints):
            return False
        targets = c.parentConstraint(constraints[0], query=True,
                                     targetList=True) or []
        influences = c.skinCluster(skin, query=True, influence=True) or []
        weight = c.skinPercent(
            skin, f"{mesh}.vtx[{plan.seed_vertex}]", query=True,
            transform=plan.joint_name)
        return (plan.joint_name in
                {node.rsplit("|", 1)[-1] for node in influences}
                and len(targets) == 1
                and targets[0].rsplit("|", 1)[-1] == plan.control_name
                and c.getAttr(joints[0] + ".advPyAuxiliaryInfluenceKind")
                == "face-lower-outer-v1"
                and abs(float(weight) - plan.seed_weight) < 1e-5)
