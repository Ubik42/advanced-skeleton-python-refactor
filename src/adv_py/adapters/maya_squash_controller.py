"""Maya host for the Body Squash Controller lattice and spline graph."""
from __future__ import annotations

import json
from contextlib import contextmanager, nullcontext
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

    def confirm_squash_build_pose(self):
        from .maya_original_build_pose_confirm import confirm_original_build_pose
        with self.transaction("Squash 构建姿态确认"):
            return confirm_original_build_pose(self)

    def capture_squash_selection(self) -> SquashSelection:
        # Selection identifies real DAG instances, not character-local aliases.
        from maya import cmds as c
        selected = tuple(c.ls(selection=True, long=True, flatten=True) or ())
        if not selected:
            raise ValueError("须先选择 Squash 影响的模型或组件")
        # Native selection can name a shape. Keep its component suffix while
        # resolving its owner, so the plan never mistakes a shape for a mesh.
        vertices = tuple(self._mesh(item.split('.', 1)[0]) +
                         ("." + item.split('.', 1)[1] if "." in item else "")
                         for item in selected)
        meshes = tuple(dict.fromkeys(item.split('.', 1)[0] for item in vertices))
        mesh = meshes[0]
        bounds = [999.,999.,999.,-999.,-999.,-999.]
        for item in selected:
            box = c.xform(item, query=True, worldSpace=True, boundingBox=True)
            for axis in range(3):
                if box[axis] < bounds[axis]:bounds[axis] = box[axis]
                if box[axis+3] > bounds[axis+3]:bounds[axis+3] = box[axis+3]
        bounds = tuple(bounds)
        center = tuple((bounds[i] + bounds[i + 3]) / 2.0 for i in range(3))
        # asDeformer selects its newly created SoftMod handle before asCCLayout
        # reads preferred parents. The second originally selected mesh is not
        # the second transform in that dialog's selection.
        candidates = self.deform_joint_candidates(mesh, include_preferred=False)
        if not candidates:
            raise ValueError("Squash 缺少可用的 DeformationSystem 关节")
        from types import SimpleNamespace
        rows = self.custom_parent_candidates(SimpleNamespace(center=center), candidates, None)
        parent = rows[0].path
        leaf = self._leaf(parent)
        stem, separator, side = leaf.rpartition("_")
        side = "M" if leaf.endswith("_M") else "L" if center[0] > 0 else "R"
        deformation = self._unique("DeformationSystem", "transform")
        joints = c.listRelatives(deformation, allDescendents=True,
                                 fullPath=True, type="joint") or []
        fit = self._node("FitSkeleton")
        game_engine = bool(c.objExists(fit) and c.attributeQuery(
            "gameEngine", node=fit, exists=True)
            and c.getAttr(fit + ".gameEngine"))
        return SquashSelection(vertices, mesh, bounds, parent,
                               "_" + side, len(joints) == 1, game_engine)

    @contextmanager
    def squash_build_pose_session(self, plan):
        """Source temporary SoftMod and UV mapping precede lattice fitting."""
        from .maya_face_deformer_sets import original_face_deformer_sets
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        source = handle = None
        try:
            c.select(plan.vertices, replace=True)
            with original_face_deformer_sets(c):
                source, handle = c.softMod(falloffMode=1, falloffAroundSelection=False)
            source = c.rename(source, self._node("asTempSoftMod"))
            handle = c.rename(handle, self._node("asTempSoftModHandle"))
            c.setAttr(source + ".falloffRadius", plan.falloff_radius)
            with self.build_pose_session(source):
                yield
                # Consume the handle inside the mapping session, just as ADV
                # does, to keep the completed controller at build pose.
                c.delete(handle)
                handle = None
        finally:
            for node in (handle, source):
                if node and c.objExists(node):
                    c.delete(node)

    def choose_squash_name(self, selection: SquashSelection) -> str:
        stem = self._leaf(selection.parent_joint).rsplit("_", 1)[0]
        for index in range(1, 100):
            name = "Squash%d%s" % (index, stem)
            if not self._cmds.objExists(self._node(name + selection.side)):
                return name
        raise ValueError("Squash 自动名称已用尽")

    def capture_squash_mirror_candidates(self, plan: SquashPlan
            ) -> tuple[str, tuple[tuple[str, tuple[float, float, float]], ...], str]:
        """Source mirrored box considers every visible non-intermediate mesh."""
        from maya.api import OpenMaya as om
        c = self._cmds
        raw = getattr(c, "raw", c)
        mirror_parent = self.mirrored_parent_joint(plan.parent_joint)
        vertices = []
        first_mesh = None
        for shape in raw.ls(type="mesh", noIntermediate=True, long=True, visible=True) or []:
            parents = raw.listRelatives(shape, parent=True, fullPath=True) or []
            if not parents:continue
            mesh = parents[0]
            if first_mesh is None:first_mesh = mesh
            selection = om.MSelectionList();selection.add(shape)
            fn = om.MFnMesh(selection.getDagPath(0))
            vertices.extend((mesh + ".vtx[%d]" % index,
                            (float(point.x),float(point.y),float(point.z)))
                            for index,point in enumerate(fn.getPoints(om.MSpace.kWorld)))
        if first_mesh is None:raise ValueError("Squash 镜像侧没有可用网格")
        return first_mesh, tuple(vertices), mirror_parent

    def capture_squash_mirror_selection(self, plan):
        """MEL 58558–58574: native axis constraints and their intersection."""
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        raw = getattr(c, "raw", c)
        prior = raw.ls(selection=True, long=True, flatten=True) or []
        low = tuple(plan.bounds[i] - plan.falloff_radius / 10. for i in range(3))
        high = tuple(plan.bounds[i+3] + plan.falloff_radius / 10. for i in range(3))
        hits = []
        try:
            raw.select(raw.ls(type="mesh", noIntermediate=True, long=True, visible=True) or [], replace=True)
            for axis in range(3):
                direction = tuple(int(i == axis) for i in range(3))
                origin = [0., 0., 0.]
                origin[axis] = (low[axis] + high[axis]) / 2. * (-1 if axis == 0 else 1)
                raw.polySelectConstraint(m=3, t=1, d=3,
                    db=(0., (high[axis]-low[axis])/2.),
                    da=direction, dp=origin)
                hits.append(tuple(raw.ls(selection=True, flatten=True, long=True) or []))
            raw.polySelectConstraint(mode=0)
            # Native stringArrayIntersector retains the first array's order.
            common = set(hits[1]).intersection(hits[2])
            vertices = tuple(vertex for vertex in hits[0] if vertex in common)
            if not vertices:
                raise ValueError("Squash 镜像范围内没有顶点")
            vertices = tuple(self._mesh(v.split('.', 1)[0]) + "." + v.split('.', 1)[1]
                             for v in vertices)
            bounds = [999., 999., 999., -999., -999., -999.]
            for vertex in vertices:
                box = raw.xform(vertex, query=True, worldSpace=True, boundingBox=True)
                for axis in range(3):
                    bounds[axis] = min(bounds[axis], box[axis])
                    bounds[axis+3] = max(bounds[axis+3], box[axis+3])
            return SquashSelection(vertices, vertices[0].split('.', 1)[0], tuple(bounds),
                                   self.mirrored_parent_joint(plan.parent_joint),
                                   "_L", plan.one_joint_prop, False)
        finally:
            raw.polySelectConstraint(mode=0)
            raw.select(prior, replace=True) if prior else raw.select(clear=True)

    def find_name_collisions(self, name: str) -> tuple[str, ...]:
        return tuple(self._cmds.ls(self._node(name), long=True) or ())

    def preflight_squash_controller(self, plan: SquashPlan) -> None:
        c = self._cmds
        self._unique("DeformationSystem", "transform")
        self._unique("MotionSystem", "transform")
        self._unique("Main", "transform")
        self._unique("ControlSet", "objectSet")
        self._unique_custom_parent(plan.parent_joint)
        for mesh in plan.meshes:
            self._mesh(mesh)
            if c.referenceQuery(mesh, isNodeReferenced=True):
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
        raw = getattr(c, "raw", c)
        selection = c.ls(selection=True, long=True) or []
        before = set(raw.ls(dependencyNodes=True, long=True) or [])
        try:
            self._build_squash(plan)
            after = set(raw.ls(dependencyNodes=True, long=True) or [])
            shared = {"CustomSystem", "asSquashControlShader", "asSquashControlShaderSG"}
            new_nodes = sorted(node for node in after - before
                               if self._leaf(node) not in shared)
            attach = self._node(plan.name + "Attach" + plan.side)
            c.addAttr(attach, longName="advPySquashNodes", dataType="string")
            nodes = [{"uuid": raw.ls(node, uuid=True)[0], "type": raw.nodeType(node)}
                     for node in new_nodes]
            c.setAttr(attach + ".advPySquashNodes",
                      json.dumps({"version": 2, "nodes": nodes}, ensure_ascii=False), type="string")
        finally:
            c.select(selection, replace=True) if selection else c.select(clear=True)

    def _build_squash(self, plan: SquashPlan) -> None:
        """asCreateSquashDeformSetup's lattice/curve frame, MEL 58929–59108."""
        from .maya_face_deformer_sets import original_face_deformer_sets
        from .maya_original_skin_history import new_original_skin_clusters
        from maya import mel
        c = self._cmds
        raw = getattr(c, "raw", c)
        name = lambda token: self._node(plan.name + token + plan.side)
        parent = self._unique_custom_parent(plan.parent_joint)
        system = self._custom_system()
        shader = self._node("asSquashControlShader")
        if not c.objExists(shader):
            c.shadingNode("lambert", name=shader, asShader=True)
            group = c.sets(renderable=True, noSurfaceShader=True, empty=True,
                           name=self._node("asSquashControlShaderSG"))
            c.connectAttr(shader + ".outColor", group + ".surfaceShader", force=True)
            c.setAttr(shader + ".color", 1, 1, 0, type="float3")
        # The source rotates Main before asking Maya to fit the lattice. An
        # axis-aligned lattice fitted first and rotated later has other bounds.
        temporary = c.createNode("transform", name=self._node("tempTransform1"), parent=parent)
        temporary = c.parent(temporary, world=True)[0]
        c.orientConstraint(temporary, self._node("Main"), maintainOffset=True)
        c.setAttr(temporary + ".rotate", 0, 0, 90 * plan.axis_sign, type="float3")
        with original_face_deformer_sets(c):
            ffd, lattice, base_lattice = c.lattice(
                list(plan.vertices), divisions=LATTICE_DIVISIONS,
                ldivisions=(2, 2, 2), objectCentered=True)
        ffd = c.rename(ffd, name("Ffd"))
        lattice = c.rename(lattice, name("FfdLattice"))
        base_lattice = c.rename(base_lattice, name("FfdBase"))
        ffd_sets = c.listConnections(ffd + ".message", source=False,
                                     destination=True, type="objectSet") or []
        c.rename(ffd_sets[0], name("FfdSet"))
        c.setAttr(ffd + ".outsideLattice", 1)
        c.setAttr(ffd + ".local", 0)
        c.parent(lattice, base_lattice, self._node("Main"))
        c.delete(temporary)
        c.setAttr(self._node("Main") + ".rotate", 0, 0, 0, type="float3")
        c.parent(name("FfdLattice"), name("FfdBase"), world=True)
        lattice, base_lattice = name("FfdLattice"), name("FfdBase")
        squash_distance = c.getAttr(lattice + ".scaleY")
        attach = c.createNode("transform", name=name("Attach"), parent=system)
        # Main reset leaves the native lattice at the source's authored frame.
        anchor = (self._ring_center(lattice, 0) if plan.one_joint_prop else
                  c.xform(parent, query=True, worldSpace=True, translation=True))
        c.xform(attach, worldSpace=True, translation=anchor)
        c.delete(c.orientConstraint(parent, attach))
        ws = c.createNode("transform", name=name("WS"), parent=attach)
        c.setAttr(ws + ".inheritsTransform", 0, lock=True)
        base = self._curve(plan.name + "Base" + plan.side, _CROSS_POINTS, attach, 17)
        base_radius = plan.falloff_radius / 4. / .4
        c.scale(base_radius, base_radius, base_radius, base + ".cv[0:4]",
                relative=True, pivot=(0, 0, 0))
        c.addAttr(base, longName="localOrient", attributeType="bool", defaultValue=1)
        offset = c.createNode("transform", name=name("Offset"))
        control = self._curve(plan.control, _BOX_POINTS, offset, 13)
        size = squash_distance / 5.
        c.scale(size, size, size, control + ".cv[0:99]", relative=True, pivot=(0,0,0))
        c.addAttr(control, longName="localOrient", attributeType="bool", defaultValue=1)
        c.addAttr(control, longName="SquashControl", attributeType="bool", defaultValue=1)
        c.addAttr(control, longName="parent", dataType="string")
        c.setAttr(control + ".parent", parent, type="string")
        c.setAttr(control + ".rotateOrder", 1)
        c.addAttr(control, longName="volume", attributeType="double", defaultValue=10,
                  softMinValue=0, hasSoftMinValue=True, softMaxValue=10,
                  hasSoftMaxValue=True, keyable=True)
        for attr in ("squash", "stretch", "bend"):
            c.addAttr(control, longName=attr, attributeType="bool", defaultValue=1, keyable=True)
        c.delete(c.orientConstraint(parent, offset))
        for frame in (lattice, base_lattice):
            c.delete(c.orientConstraint(parent, frame, offset=(0,0,-90 * plan.axis_sign)))
        c.parent(lattice, ws)
        c.parent(base_lattice, base)
        c.parentConstraint(parent, attach, maintainOffset=True)
        c.scaleConstraint(parent, attach)
        upper = self._ring_center(name("FfdLattice"), 10)
        c.xform(offset, worldSpace=True, translation=upper)
        c.parent(offset, base)
        lattice = name("FfdLattice")
        first = c.xform(lattice + ".pt[0][0][0]", query=True, worldSpace=True, translation=True)
        second = c.xform(lattice + ".pt[0][1][0]", query=True, worldSpace=True, translation=True)
        step = dist(first, second) * plan.axis_sign
        c.select(base, replace=True)
        joints = []
        for index in range(11):
            joint = c.joint(name=name("IKX%d" % index))
            if index:c.setAttr(joint + ".translateX", step)
            joints.append(joint)
        handle, effector, curve = c.ikHandle(name=self._node("squashIKHandle"),
            startJoint=name("IKX0"), endEffector=name("IKX10"),
            solver="ikSplineSolver", createCurve=True, numSpans=2)
        c.rename(handle, name("IKHandle"));c.rename(effector, name("IKEffector"))
        c.rename(curve, name("IKCurve"))
        c.parent(name("IKHandle"), name("IKCurve"), ws)
        c.setAttr(name("IKHandle") + ".visibility", 0, lock=True)
        curve_shape = c.listRelatives(name("IKCurve"), shapes=True,
                                     fullPath=True, type="nurbsCurve")[0]
        handles = []
        for index in range(5):
            c.select(name("IKCurve") + ".cv[%d]" % index, replace=True)
            with getattr(c, "_creation_namespace", nullcontext)(), original_face_deformer_sets(c):
                cluster, cluster_handle = mel.eval('newCluster " -envelope 1";')
            c.rename(cluster, name("IKCluster%d" % index))
            cluster_handle = c.rename(cluster_handle, name("IKClusterHandle%d" % index))
            c.setAttr(cluster_handle + ".visibility", 0, lock=True)
            handles.append(cluster_handle)
        c.select(clear=True)
        for joint in joints:c.select(joint, add=True)
        c.select(lattice, add=True)
        skin = new_original_skin_clusters(commands=raw, namespace=self.namespace)[0]
        skin = c.rename(skin, name("IKSC"))
        for index, joint in enumerate(joints):
            c.skinPercent(skin, [lattice + ".pt[0:1][%d][0]" % index,
                                lattice + ".pt[0:1][%d][1]" % index],
                          transformValue=[(joint, 1.)])
        # Two native additions retain their authored .95/.05 endpoint bias.
        constraint = c.pointConstraint(handles[4], handles[3], weight=.95)[0]
        c.pointConstraint(handles[2], handles[3], weight=.05)
        c.delete(constraint)
        c.parent(handles[3], handles[4])
        c.parent(handles[0], handles[1], base)
        handle_offset = c.createNode("transform", name=name("IKClusterHandle4Offset"), parent=name("Offset"))
        c.parent(handles[4], handle_offset)
        c.parent(handles[2], ws)
        c.parentConstraint(name("IKClusterHandle4"), name("IKClusterHandle0"),
                           name("IKClusterHandle2"), maintainOffset=True)
        control = name("")
        for attr in ("latticeVis", "curveVis"):
            c.addAttr(control, longName=attr, attributeType="bool", defaultValue=0)
            c.setAttr(control + "." + attr, channelBox=True)
        c.addAttr(control, longName="outsideLattice", attributeType="enum",
                  enumName="Inside:All:Falloff", defaultValue=1, keyable=True)
        self._apply_squash_graph(plan, curve_shape, step)
        c.setAttr(name("IKX0") + ".visibility", 0, lock=True)
        c.sets((control, name("Base")), add=self._node("ControlSet"))
        self._update_custom_build_pose(control, base=name("Base"), add=True)

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
            if link.source == "MainScaleMultiplyDivide.outputY" and not c.objExists(source):
                continue
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
        stem, separator, side = self._leaf(path).rpartition("_")
        attach = self._unique(stem + "Attach_" + side, "transform")
        raw = getattr(c, "raw", c)
        payload = json.loads(c.getAttr(attach + ".advPySquashNodes"))
        nodes = []
        if isinstance(payload, list) and all(isinstance(n, str) for n in payload):
            # Compatibility with earlier same-layout scenes.
            nodes = [node for node in payload if raw.objExists(node)]
        elif isinstance(payload, dict) and payload.get("version") == 2:
            for item in payload.get("nodes", ()):
                if not isinstance(item, dict) or set(item) != {"uuid", "type"}:
                    raise ValueError("Squash 节点身份记录损坏")
                matches = raw.ls(item["uuid"], long=True) or []
                if not matches:
                    continue
                if len(matches) != 1 or raw.nodeType(matches[0]) != item["type"]:
                    raise ValueError("Squash 节点身份或类型发生变化")
                nodes.append(matches[0])
        else:
            raise ValueError("Squash 节点清单损坏")
        self._transaction_changed = True
        self._update_custom_build_pose(path, add=False)
        # Source deletion removes the Attach subtree. UUIDs clean up only its
        # own residual DG nodes even after namespace changes or reparenting.
        raw.delete(attach)
        for node in reversed(nodes):
            if raw.objExists(node):
                raw.delete(node)
