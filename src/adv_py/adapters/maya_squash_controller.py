"""Maya host for the Body Squash Controller lattice and spline graph."""
from __future__ import annotations

import json
from math import dist

from adv_py.core.squash_controller import (
    LATTICE_DIVISIONS, SquashPlan, SquashSelection,
)
from adv_py.core.squash_graph import plan_squash_graph
from .maya_custom_controller import MayaCustomControllerHost


_BOX_POINTS = ((1, 1, 1), (1, -1, 1), (-1, -1, 1), (-1, 1, 1),
               (1, 1, 1), (1, 1, -1), (1, -1, -1), (1, -1, 1),
               (1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1),
               (-1, 1, -1), (-1, 1, 1), (-1, -1, 1), (-1, -1, -1))
_CROSS_POINTS = ((0, 1, 0), (0, -1, 0), (0, 0, 0),
                 (1, 0, 0), (-1, 0, 0))


class MayaSquashControllerHost(MayaCustomControllerHost):
    def __init__(self, *, namespace: str | None = None) -> None:
        super().__init__(namespace=namespace, face=False)

    def _node(self, name: str) -> str:
        return self.scene_address(name)

    @staticmethod
    def _leaf(path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def capture_squash_selection(self) -> SquashSelection:
        c = self._cmds
        vertices = tuple(c.filterExpand(c.ls(selection=True, long=True,
                                             flatten=True) or [],
                                        selectionMask=31, expand=True) or ())
        if not vertices:
            raise ValueError("须先选择 Squash 影响的多边形顶点")
        meshes = {item.split(".vtx[", 1)[0] for item in vertices}
        if len(meshes) != 1:
            raise ValueError("一次 Squash 操作只能选择一件网格的顶点")
        mesh = self._mesh(next(iter(meshes)))
        bounds = tuple(float(value) for value in c.exactWorldBoundingBox(
            vertices))
        center = tuple((bounds[i] + bounds[i + 3]) / 2.0 for i in range(3))
        candidates = self.deform_joint_candidates(mesh)
        if not candidates:
            raise ValueError("Squash 缺少可用的 DeformationSystem 关节")
        parent = min(candidates, key=lambda item: dist(item.center, center)).path
        leaf = self._leaf(parent)
        stem, separator, side = leaf.rpartition("_")
        if not separator or side not in ("R", "L", "M"):
            raise ValueError("Squash 父关节名称须以 _R、_L 或 _M 结尾")
        deformation = self._unique("DeformationSystem", "transform")
        joints = c.listRelatives(deformation, allDescendents=True,
                                 fullPath=True, type="joint") or []
        fit = self._node("FitSkeleton")
        game_engine = bool(c.objExists(fit) and c.attributeQuery(
            "gameEngine", node=fit, exists=True)
            and c.getAttr(fit + ".gameEngine"))
        return SquashSelection(vertices, mesh, bounds, parent,
                               "_" + side, len(joints) == 1, game_engine)

    def choose_squash_name(self, selection: SquashSelection) -> str:
        stem = self._leaf(selection.parent_joint).rsplit("_", 1)[0]
        for index in range(1, 100):
            name = "Squash%d%s" % (index, stem)
            if not self._cmds.objExists(self._node(name + selection.side)):
                return name
        raise ValueError("Squash 自动名称已用尽")

    def capture_squash_mirror_candidates(self, plan: SquashPlan
            ) -> tuple[str, tuple[tuple[str, tuple[float, float, float]], ...], str]:
        from maya.api import OpenMaya as om

        c = self._cmds
        parent_leaf = self._leaf(plan.parent_joint)
        if not parent_leaf.endswith("_R"):
            raise ValueError("Squash 右侧父关节名称无效")
        mirror_parent = self._unique(parent_leaf[:-1] + "L", "joint")
        center = (-plan.center[0], plan.center[1], plan.center[2])
        meshes = []
        for shape in c.ls(type="mesh", noIntermediate=True,
                          long=True) or []:
            mesh = (c.listRelatives(shape, parent=True,
                                    fullPath=True) or [None])[0]
            if mesh is None:
                continue
            if (self.namespace is not None
                    and not shape.rsplit("|", 1)[-1].startswith(
                        self.namespace.strip(":") + ":")):
                continue
            bounds = c.exactWorldBoundingBox(mesh)
            distance = sum((center[axis] - min(max(center[axis], bounds[axis]),
                                                bounds[axis + 3])) ** 2
                           for axis in range(3))
            meshes.append((distance, mesh, shape))
        if not meshes:
            raise ValueError("Squash 镜像侧没有可用网格")
        meshes.sort(key=lambda item: (item[0],
                                      item[1] != plan.mesh, item[1]))
        _, mesh, shape = meshes[0]
        selection = om.MSelectionList()
        selection.add(shape)
        fn = om.MFnMesh(selection.getDagPath(0))
        vertices = tuple(("%s.vtx[%d]" % (mesh, index),
                          (float(point.x), float(point.y), float(point.z)))
                         for index, point in enumerate(
                             fn.getPoints(om.MSpace.kWorld)))
        return mesh, vertices, mirror_parent

    def find_name_collisions(self, name: str) -> tuple[str, ...]:
        return tuple(self._cmds.ls(self._node(name), long=True) or ())

    def preflight_squash_controller(self, plan: SquashPlan) -> None:
        c = self._cmds
        self._unique("DeformationSystem", "transform")
        self._unique("MotionSystem", "transform")
        self._unique("Main", "transform")
        self._unique("ControlSet", "objectSet")
        self._unique("MainScaleMultiplyDivide", "multiplyDivide")
        self._unique(plan.parent_joint, "joint")
        self._mesh(plan.mesh)
        if c.referenceQuery(plan.mesh, isNodeReferenced=True):
            raise ValueError("引用模型无法直接插入 Squash FFD")

    def _curve(self, name: str, points: tuple[tuple[int, int, int], ...],
               parent: str, color: int) -> str:
        c = self._cmds
        curve = c.curve(degree=1, point=points,
                        name=self._node(name))
        curve = c.parent(curve, parent, relative=True)[0]
        for shape in c.listRelatives(curve, shapes=True,
                                     fullPath=True, type="nurbsCurve") or []:
            c.setAttr(shape + ".overrideEnabled", True)
            c.setAttr(shape + ".overrideColor", color)
        return curve

    def _ring_center(self, lattice: str, index: int) -> tuple[float, float, float]:
        c = self._cmds
        points = [c.xform("%s.pt[%d][%d][%d]" % (lattice, x, index, z),
                          query=True, worldSpace=True, translation=True)
                  for x in (0, 1) for z in (0, 1)]
        return tuple(sum(point[axis] for point in points) / 4.0
                     for axis in range(3))

    def _resolve_graph_plug(self, plug: str, plan: SquashPlan,
                            curve_shape: str) -> str:
        node, attribute = plug.split(".", 1)
        if node == plan.name + "IKCurveShape" + plan.side:
            return curve_shape + "." + attribute
        if node.startswith("|") or ":" in node:
            return node + "." + attribute
        return self._node(node) + "." + attribute

    def create_squash_controller(self, plan: SquashPlan) -> None:
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        selection = c.ls(selection=True, long=True) or []
        before = set(c.ls(dependencyNodes=True, long=True) or [])
        try:
            self._build_squash(plan)
            after = set(c.ls(dependencyNodes=True, long=True) or [])
            shared = {"CustomSystem"}
            new_nodes = sorted(node for node in after - before
                               if self._leaf(node) not in shared)
            attach = self._node(plan.name + "Attach" + plan.side)
            c.addAttr(attach, longName="advPySquashNodes", dataType="string")
            c.setAttr(attach + ".advPySquashNodes",
                      json.dumps(new_nodes, ensure_ascii=False), type="string")
        finally:
            c.select(selection, replace=True) if selection else c.select(clear=True)

    def _build_squash(self, plan: SquashPlan) -> None:
        c = self._cmds
        name = lambda token: self._node(plan.name + token + plan.side)
        parent = self._unique(plan.parent_joint, "joint")
        system = self._custom_system()
        ffd, lattice, base_lattice = c.lattice(
            list(plan.vertices), divisions=LATTICE_DIVISIONS,
            ldivisions=(2, 2, 2), objectCentered=True)
        ffd = c.rename(ffd, name("Ffd"))
        lattice = c.rename(lattice, name("FfdLattice"))
        base_lattice = c.rename(base_lattice, name("FfdBase"))
        ffd_sets = c.listConnections(ffd + ".message", source=False,
                                     destination=True, type="objectSet") or []
        if len(ffd_sets) != 1:
            raise RuntimeError("Squash FFD 缺少唯一变形对象集")
        c.rename(ffd_sets[0], name("FfdSet"))
        c.setAttr(ffd + ".outsideLattice", 1)
        c.setAttr(ffd + ".local", False)
        for frame in (lattice, base_lattice):
            c.delete(c.orientConstraint(
                parent, frame, maintainOffset=False,
                offset=(0, 0, -90 * plan.axis_sign)))
        lower = self._ring_center(lattice, 0)
        upper = self._ring_center(lattice, 10)
        one = self._ring_center(lattice, 1)
        step = dist(lower, one) * plan.axis_sign
        if abs(step) < 1e-8:
            raise ValueError("Squash 晶格纵向相邻层距离为零")
        attach = c.createNode("transform", name=name("Attach"),
                              parent=system, skipSelect=True)
        anchor = lower if plan.one_joint_prop else c.xform(
            parent, query=True, worldSpace=True, translation=True)
        c.xform(attach, worldSpace=True, translation=anchor)
        c.delete(c.orientConstraint(parent, attach))
        c.parentConstraint(parent, attach, maintainOffset=True)
        c.scaleConstraint(parent, attach, maintainOffset=False)
        ws = c.createNode("transform", name=name("WS"),
                          parent=attach, skipSelect=True)
        c.setAttr(ws + ".inheritsTransform", False, lock=True)
        base = self._curve(plan.name + "Base" + plan.side,
                           _CROSS_POINTS, attach, 17)
        base_radius = plan.falloff_radius / 1.6
        c.scale(base_radius, base_radius, base_radius,
                base + ".cv[0:4]", relative=True, pivot=(0, 0, 0))
        c.addAttr(base, longName="localOrient", attributeType="bool",
                  defaultValue=True)
        offset = c.createNode("transform", name=name("Offset"),
                              parent=base, skipSelect=True)
        c.xform(offset, worldSpace=True, translation=upper)
        control = self._curve(plan.control, _BOX_POINTS, offset, 13)
        control_radius = abs(dist(lower, upper)) / 5.0
        c.scale(control_radius, control_radius, control_radius,
                control + ".cv[0:15]", relative=True, pivot=(0, 0, 0))
        c.addAttr(control, longName="localOrient", attributeType="bool",
                  defaultValue=True)
        c.addAttr(control, longName="SquashControl", attributeType="bool",
                  defaultValue=True)
        c.addAttr(control, longName="parent", dataType="string")
        c.setAttr(control + ".parent", parent, type="string")
        c.setAttr(control + ".rotateOrder", 1)
        for attr, default in (("volume", 10.0), ("squash", True),
                              ("stretch", True), ("bend", True),
                              ("latticeVis", False), ("curveVis", False)):
            kind = "double" if attr == "volume" else "bool"
            options = {"minValue": 0.0, "maxValue": 10.0} if attr == "volume" else {}
            c.addAttr(control, longName=attr, attributeType=kind,
                      defaultValue=default, keyable=attr not in
                      ("latticeVis", "curveVis"), **options)
            if attr in ("latticeVis", "curveVis"):
                c.setAttr(control + "." + attr, channelBox=True)
        c.addAttr(control, longName="outsideLattice", attributeType="enum",
                  enumName="Inside:All:Falloff", defaultValue=1,
                  keyable=True)
        c.parent(lattice, ws)
        c.parent(base_lattice, base)
        joints = []
        for index in range(11):
            ancestor = base if index == 0 else joints[-1]
            joint = c.createNode("joint", name=name("IKX%d" % index),
                                 parent=ancestor, skipSelect=True)
            if index:
                c.setAttr(joint + ".translateX", step)
            joints.append(joint)
        handle, effector, curve = c.ikHandle(
            startJoint=joints[0], endEffector=joints[-1],
            solver="ikSplineSolver", createCurve=True,
            numSpans=2, parentCurve=False)
        handle = c.rename(handle, name("IKHandle"))
        c.rename(effector, name("IKEffector"))
        curve = c.rename(curve, name("IKCurve"))
        c.parent((handle, curve), ws)
        c.setAttr(handle + ".visibility", False, lock=True)
        curve_shape = (c.listRelatives(curve, shapes=True,
                                       fullPath=True, type="nurbsCurve") or [None])[0]
        if curve_shape is None:
            raise RuntimeError("Squash Spline IK 曲线缺少形状")
        cluster_handles = []
        for index in range(5):
            cluster, cluster_handle = c.cluster(
                "%s.cv[%d]" % (curve, index),
                name=name("IKCluster%d" % index))
            cluster_handle = c.rename(cluster_handle,
                                      name("IKClusterHandle%d" % index))
            c.setAttr(cluster_handle + ".visibility", False, lock=True)
            cluster_handles.append(cluster_handle)
        c.parent(cluster_handles[0], cluster_handles[1], base)
        handle4_offset = c.createNode("transform", name=name(
            "IKClusterHandle4Offset"), parent=offset, skipSelect=True)
        c.parent(cluster_handles[4], handle4_offset)
        c.parent(cluster_handles[3], cluster_handles[4])
        c.parent(cluster_handles[2], ws)
        c.parentConstraint(cluster_handles[4], cluster_handles[0],
                           cluster_handles[2], maintainOffset=True)
        skin = c.skinCluster(joints, lattice, toSelectedBones=True,
                             maximumInfluences=3, dropoffRate=4,
                             removeUnusedInfluence=False,
                             name=name("IKSC"))[0]
        for index, joint in enumerate(joints):
            points = ["%s.pt[0:1][%d][%d]" % (lattice, index, z)
                      for z in (0, 1)]
            c.skinPercent(skin, points,
                          transformValue=[(joint, 1.0)])
        self._apply_squash_graph(plan, curve_shape, step)
        c.setAttr(joints[0] + ".visibility", False, lock=True)
        c.sets((control, base), add=self._node("ControlSet"))
        self._update_custom_build_pose(control, base=base, add=True)

    def _apply_squash_graph(self, plan: SquashPlan,
                            curve_shape: str, step: float) -> None:
        c = self._cmds
        graph = plan_squash_graph(plan)
        for node in graph.nodes:
            c.createNode(node.type, name=self._node(node.name),
                         skipSelect=True)
        for setting in graph.values:
            c.setAttr(self._resolve_graph_plug(setting.plug, plan,
                                               curve_shape), setting.value)
        info = self._node(plan.name + "IKCurveInfo" + plan.side)
        normalize = self._node(plan.name + "IKCurveInfoNormalize" + plan.side)
        stretch = self._node(plan.name + "IKStretch" + plan.side)
        for link in graph.links:
            source = self._resolve_graph_plug(link.source, plan, curve_shape)
            target = self._resolve_graph_plug(link.target, plan, curve_shape)
            c.connectAttr(source, target)
        arc = float(c.getAttr(info + ".arcLength"))
        if arc <= 0:
            raise RuntimeError("Squash 初始 IK 曲线长度为零")
        c.setAttr(normalize + ".input2X", arc)
        c.setAttr(stretch + ".input1X", step)

    def capture_squash_controller(self, control: str) -> tuple[str, str, int]:
        c = self._cmds
        path = self._unique(control, "transform")
        parent = c.getAttr(path + ".parent")
        name = self._leaf(path)
        stem, separator, side = name.rpartition("_")
        joints = sum(bool(c.objExists(self._node(stem +
                     "IKX%d_%s" % (index, side)))) for index in range(11))
        return path, parent, joints

    def resolve_squash_pair(self, selected_control: str) -> tuple[str, ...]:
        c = self._cmds
        path = self._unique(selected_control, "transform")
        if not c.attributeQuery("SquashControl", node=path, exists=True):
            raise ValueError("所选对象不是 Squash Controller")
        leaf = self._leaf(path)
        stem, separator, side = leaf.rpartition("_")
        if not separator or side not in ("R", "L", "M"):
            raise ValueError("Squash Controller 名称无效")
        names = [leaf]
        if side in ("R", "L"):
            other = stem + "_" + ("L" if side == "R" else "R")
            if c.objExists(self._node(other)):
                if not c.attributeQuery("SquashControl",
                                        node=self._node(other), exists=True):
                    raise ValueError("对侧同名节点不是 Squash Controller")
                names.append(other)
        return tuple(names)

    def delete_squash_controller(self, control: str) -> None:
        self._require_transaction()
        c = self._cmds
        path = self._unique(control, "transform")
        if not c.attributeQuery("SquashControl", node=path, exists=True):
            raise ValueError("所选对象不是 Squash Controller")
        self._transaction_changed = True
        self._update_custom_build_pose(path, add=False)
        stem, separator, side = self._leaf(path).rpartition("_")
        attach = self._unique(stem + "Attach_" + side, "transform")
        payload = c.getAttr(attach + ".advPySquashNodes")
        nodes = json.loads(payload)
        if not isinstance(nodes, list) or not all(isinstance(n, str)
                                                  for n in nodes):
            raise ValueError("Squash 节点清单损坏")
        for node in reversed(nodes):
            if c.objExists(node):
                c.delete(node)
