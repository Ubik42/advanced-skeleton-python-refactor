"""Maya implementation of the FK-loop branch of 6.925 Shapers Create."""
from __future__ import annotations

import json
from math import dist
import re

from adv_py.core.shapers_create import (
    ShapersEdge, ShapersEdgePack, ShapersFkLoop, ShapersFkLoopOptions,
    plan_shapers_edge_packs,
)
from .maya_shapers import _cmds, _python_shapers


class MayaShapersCreateHost:
    def __init__(self, namespace: str):
        self.cmds = _cmds()
        self.prefix = "" if namespace in ("", ":") else namespace.strip(":") + ":"

    def selected_fk_controls(self) -> tuple[str, ...]:
        return tuple(self.cmds.ls(selection=True, long=True,
                                  transforms=True) or ())

    def capture_edge_input(self) -> tuple[
        str, tuple[ShapersEdge, ...],
        dict[int, tuple[float, float, float]], int | None,
    ]:
        c = self.cmds
        selection = c.ls(selection=True, flatten=True, long=True) or []
        pattern = re.compile(r"(.+)\.e\[(\d+)\]$")
        vertex_pattern = re.compile(r"(.+)\.vtx\[(\d+)\]$")
        edges = []
        start_vertex = None
        mesh = None
        positions = {}
        for item in selection:
            edge_match = pattern.fullmatch(item)
            vertex_match = vertex_pattern.fullmatch(item)
            if not edge_match and not vertex_match:
                raise ValueError("Shapers 边模式只能选择同一网格的边和起点顶点")
            item_mesh = (edge_match or vertex_match).group(1)
            if mesh is None:
                mesh = item_mesh
            elif item_mesh != mesh:
                raise ValueError("Shapers 选边必须属于同一网格")
            if vertex_match:
                if start_vertex is not None:
                    raise ValueError("Shapers 起点顶点最多选择一个")
                start_vertex = int(vertex_match.group(2))
                continue
            info = c.polyInfo(item, edgeToVertex=True) or []
            numbers = [int(value) for value in re.findall(r"\d+", info[0])]
            if len(numbers) < 3:
                raise ValueError("无法读取 Shapers 网格边端点：" + item)
            index = int(edge_match.group(2))
            start, end = numbers[-2:]
            edges.append(ShapersEdge(index, start, end))
            for vertex in (start, end):
                if vertex not in positions:
                    positions[vertex] = tuple(c.xform(
                        f"{mesh}.vtx[{vertex}]", query=True,
                        worldSpace=True, translation=True))
        if mesh is None or not edges:
            raise ValueError("请选择网格边以创建 Shapers")
        return mesh, tuple(edges), positions, start_vertex

    def preflight_edge_packs(self, mesh: str,
                             packs: tuple[ShapersEdgePack, ...]) -> None:
        self.preflight_fk_loops((), mesh)
        if not packs:
            raise ValueError("Shapers 选边没有形成可用路径")
        for pack in packs:
            if len(pack.edges) < (3 if pack.closed else 2):
                raise ValueError("Shapers 闭环至少三条边，桥接至少两条边")

    def _one(self, name: str) -> str:
        matches = self.cmds.ls(name, long=True) or []
        if len(matches) != 1:
            raise ValueError("Shapers 节点不存在或名称不唯一：" + name)
        return matches[0]

    def _skin_cluster(self, mesh: str) -> str | None:
        clusters = [node for node in self.cmds.listHistory(mesh) or []
                    if self.cmds.nodeType(node) == "skinCluster"]
        if len(clusters) > 1:
            raise ValueError("Shapers Skin 网格存在多个 SkinCluster")
        return clusters[0] if clusters else None

    def preflight_fk_loops(self, loops: tuple[ShapersFkLoop, ...],
                           mesh: str) -> None:
        c = self.cmds
        mesh = self._one(mesh)
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise ValueError("Shapers Skin 必须是单一多边形网格")
        loaded = [name for name in c.pluginInfo(query=True,
                                                 listPlugins=True) or []
                  if "shapersDeformer" in (
                      c.pluginInfo(name, query=True, dependNode=True) or [])]
        if len(loaded) != 1:
            raise ValueError("请先设置并加载 Shapers 插件")
        self._skin_cluster(mesh)
        for loop in loops:
            control = self._one(loop.control)
            joint = self._one(loop.deform_joint)
            if c.nodeType(joint) != "joint":
                raise ValueError("Shapers 对应变形关节不是 joint：" + joint)
            if (self.prefix and not control.rsplit("|", 1)[-1].startswith(self.prefix)):
                raise ValueError("FK 控制器不属于当前角色")
            for component, neutral in (("translate", (0, 0, 0)),
                                       ("rotate", (0, 0, 0)),
                                       ("scale", (1, 1, 1))):
                value = c.getAttr(control + "." + component)[0]
                if any(abs(float(a) - b) > 1e-4
                       for a, b in zip(value, neutral)):
                    raise ValueError("请先把 FK 控制器返回构建姿态：" + control)

    def _ensure_skin(self, mesh: str) -> str:
        c = self.cmds
        existing = self._skin_cluster(mesh)
        if existing:
            return existing
        joint = self.prefix + "ShapesJoint"
        if not c.objExists(joint):
            c.select(clear=True)
            joint = c.joint(name=joint)
        return c.skinCluster(joint, mesh, toSelectedBones=True,
                             maximumInfluences=3, dropoffRate=4,
                             removeUnusedInfluence=False)[0]

    def _controls_root(self) -> str:
        c = self.cmds
        root = self.prefix + "ShaperControls"
        if not c.objExists(root):
            motion = self.prefix + "MotionSystem"
            if c.objExists(motion):
                root = c.createNode("transform", name=root, parent=motion)
            else:
                root = c.createNode("transform", name=root)
        main = self.prefix + "Main"
        if not c.objExists(main):
            main = c.createNode("transform", name=main)
        for attribute, default in (("shaperVis", 1), ("shaperDisable", 0)):
            if not c.attributeQuery(attribute, node=main, exists=True):
                c.addAttr(main, longName=attribute, attributeType="bool",
                          defaultValue=default, keyable=False)
                c.setAttr(main + "." + attribute, channelBox=True)
        if not c.isConnected(main + ".shaperVis", root + ".visibility"):
            c.connectAttr(main + ".shaperVis", root + ".visibility",
                          force=True)
        return root

    def _unique_name(self, loop: ShapersFkLoop) -> tuple[str, str]:
        c = self.cmds
        for index in range(99):
            suffix = (chr(65 + index) if index < 26 else
                      chr(64 + index // 26) + chr(65 + index % 26))
            name = self.prefix + "Shaper" + loop.fit_stem + suffix + loop.side
            if not c.objExists(name):
                return name, suffix
        raise ValueError("Shapers 同名闭环数量超过 99")

    def _nearest_vertex(self, sampler: str, mesh: str,
                        position: tuple[float, ...]) -> tuple[int, tuple[float, ...]]:
        c = self.cmds
        c.setAttr(sampler + ".inPosition", *position, type="double3")
        index = int(c.getAttr(sampler + ".closestVertexIndex"))
        vertex = tuple(c.xform(f"{mesh}.vtx[{index}]", query=True,
                               worldSpace=True, translation=True))
        return index, vertex

    def _edge_source(self, mesh: str, pack: ShapersEdgePack,
                     skin: str) -> ShapersFkLoop:
        c = self.cmds
        influences = c.skinCluster(skin, query=True, influence=True) or []
        if not influences:
            raise ValueError("Shapers 网格没有 Skin 影响关节")
        totals = {joint: 0.0 for joint in influences}
        for vertex in pack.vertices:
            weights = c.skinPercent(skin, f"{mesh}.vtx[{vertex}]",
                                    query=True, value=True) or []
            if len(weights) != len(influences):
                raise RuntimeError("Shapers 顶点权重与影响关节数量不一致")
            for joint, weight in zip(influences, weights):
                totals[joint] += weight
        joint = max(influences, key=lambda name: totals[name])
        current = joint
        fit_stem = ""
        while current:
            leaf = current.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            stem = re.sub(r"_[MRL]$", "", leaf)
            if c.objExists(self.prefix + stem):
                fit_stem = stem
                break
            parents = c.listRelatives(current, parent=True,
                                      fullPath=True, type="joint") or []
            current = parents[0] if parents else ""
        if not fit_stem:
            fit_stem = re.sub(r"_[MRL]$", "", joint.rsplit("|", 1)[-1]
                              .rsplit(":", 1)[-1])
        leaf = joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        side_match = re.search(r"_([MRL])$", leaf)
        if side_match:
            side = "_" + side_match.group(1)
        else:
            x = c.xform(joint, query=True, worldSpace=True,
                        translation=True)[0]
            side = "_M" if abs(x) < 1e-5 else "_L" if x > 0 else "_R"
        return ShapersFkLoop("", joint, fit_stem, side)

    def _make_edge_curve(self, mesh: str, pack: ShapersEdgePack,
                         options: ShapersFkLoopOptions, parent: str,
                         positions: dict[int, tuple[float, float, float]],
                         ) -> tuple[str, float, int]:
        c = self.cmds
        points = [positions[vertex] for vertex in pack.vertices]
        scale = max(dist(a, b) for a in points for b in points) / 2.0
        if pack.closed:
            points.append(points[0])
        curve = c.curve(name=self.prefix + "AdvPy_ShaperTemp#",
                        degree=1, point=points)
        c.rebuildCurve(curve, constructionHistory=False,
                       replaceOriginal=True, rebuildType=0,
                       endKnots=1, keepRange=0, keepControlPoints=False,
                       keepEndPoints=True, keepTangents=False,
                       spans=(options.loop_controls if pack.closed else
                              options.bridge_controls - 1), degree=3,
                       tolerance=0.01)
        from maya import mel
        c.select(curve, replace=True)
        mel.eval("nurbsCurveToBezier")
        curve_name = parent.rsplit("|", 1)[-1].replace(
            "Shaper", "ShaperCurve", 1)
        curve = c.rename(curve, curve_name)
        c.parent(curve, parent)
        for attribute, value in (("displayCV", 1),
                                 ("overrideEnabled", 1),
                                 ("overrideColor", 16),
                                 ("overrideDisplayType", 2)):
            c.setAttr(curve + "." + attribute, value)
        shape = (c.listRelatives(curve, shapes=True, fullPath=True) or [])[0]
        count = int(c.getAttr(shape + ".spans")) + int(c.getAttr(shape + ".degree"))
        if pack.closed:
            count -= 1
        return curve, max(scale, 1e-4), count

    def _make_curve(self, loop: ShapersFkLoop, mesh: str,
                    options: ShapersFkLoopOptions, parent: str,
                    sampler: str) -> tuple[str, float, int]:
        c = self.cmds
        from maya import mel

        joint_pos = tuple(c.xform(loop.deform_joint, query=True,
                                  worldSpace=True, translation=True))
        control_pos = tuple(c.xform(loop.control + ".ep[0]", query=True,
                                    worldSpace=True, translation=True))
        radius = max(dist(joint_pos, control_pos) * 0.7, 1e-4)
        curve = c.circle(name=self.prefix + "AdvPy_ShaperTemp#",
                         center=(0, 0, 0), normal=(1, 0, 0),
                         sweep=360, radius=radius, degree=3,
                         sections=4, constructionHistory=False)[0]
        c.xform(curve, worldSpace=True,
                matrix=c.xform(loop.deform_joint, query=True,
                               worldSpace=True, matrix=True))
        for index in range(4):
            point = curve + f".ep[{index}]"
            locator = c.createNode("transform", name=self.prefix + "AdvPy_ShaperSnap#")
            try:
                c.xform(locator, worldSpace=True, translation=c.xform(
                    point, query=True, worldSpace=True, translation=True))
                constraint = c.geometryConstraint(mesh, locator)[0]
                c.delete(constraint)
                c.xform(point, worldSpace=True, translation=c.xform(
                    locator, query=True, worldSpace=True, translation=True))
            finally:
                c.delete(locator)
        c.rebuildCurve(curve, constructionHistory=False,
                       replaceOriginal=True, rebuildType=0,
                       endKnots=1, keepRange=0, keepControlPoints=False,
                       keepEndPoints=True, keepTangents=False,
                       spans=options.loop_controls, degree=3,
                       tolerance=0.01)
        c.select(curve, replace=True)
        mel.eval("nurbsCurveToBezier")
        curve_name = parent.rsplit("|", 1)[-1].replace(
            "Shaper", "ShaperCurve", 1)
        curve = c.rename(curve, curve_name)
        c.parent(curve, parent)
        c.setAttr(curve + ".displayCV", 1)
        c.setAttr(curve + ".overrideEnabled", 1)
        c.setAttr(curve + ".overrideColor", 16)
        c.setAttr(curve + ".overrideDisplayType", 2)
        shape = (c.listRelatives(curve, shapes=True, fullPath=True) or [])[0]
        spans = int(c.getAttr(shape + ".spans"))
        degree = int(c.getAttr(shape + ".degree"))
        return curve, radius, spans + degree - 1

    def _add_loop(self, loop: ShapersFkLoop, mesh: str,
                  options: ShapersFkLoopOptions, root: str,
                  sampler: str, skin: str,
                  edge_pack: ShapersEdgePack | None = None,
                  positions_by_vertex: dict[int, tuple[float, float, float]] | None = None,
                  ) -> str:
        c = self.cmds
        group_name, letter = self._unique_name(loop)
        group = c.createNode("transform", name=group_name, parent=root)
        control_group = c.createNode(
            "transform", name=self.prefix + "ShaperControls" +
            loop.fit_stem + letter + loop.side, parent=group)
        for attribute, value in (("deformJoint", loop.deform_joint),
                                 ("skin", mesh)):
            c.addAttr(group, longName=attribute, dataType="string")
            c.setAttr(group + "." + attribute, value, type="string")
        c.addAttr(group, longName="loop", attributeType="bool",
                  defaultValue=edge_pack is None or edge_pack.closed)
        if edge_pack is None:
            curve, radius, count = self._make_curve(loop, mesh, options,
                                                    group, sampler)
        else:
            curve, radius, count = self._make_edge_curve(
                mesh, edge_pack, options, group, positions_by_vertex or {})
        closed = edge_pack is None or edge_pack.closed
        if count < (9 if closed else 7) or (count % 3 if closed else (count - 1) % 3):
            raise RuntimeError("Shapers Bezier 控制点数无效")
        positions = [tuple(c.xform(curve + f".cv[{index}]", query=True,
                                   worldSpace=True, translation=True))
                     for index in range(count)]
        vertices: list[int] = []
        for index, position in enumerate(positions):
            if closed and index % 3:
                vertices.append(-1)
                continue
            vertex, snap = self._nearest_vertex(sampler, mesh, position)
            vertices.append(vertex)
            if options.snap_vertices if closed else options.bridge_snap_vertices:
                c.xform(curve + f".cv[{index}]", worldSpace=True,
                        translation=snap)
                positions[index] = snap
        controls = []
        offsets = []
        for index, position in enumerate(positions):
            suffix = str(index) + loop.fit_stem + letter + loop.side
            name = self.prefix + "Shaper" + suffix
            control = c.sphere(name=name, pivot=(0, 0, 0),
                               axis=(0, 1, 0), radius=1, degree=3,
                               sections=8, spans=4,
                               constructionHistory=False)[0]
            size = radius / (10 if index % 3 == 0 else 20)
            c.scale(size, size, size, control + ".cv[*]", relative=True)
            if vertices[index] >= 0:
                c.addAttr(control, longName="vtxNr", attributeType="long",
                          defaultValue=vertices[index])
            attach = c.createNode("transform", name=self.prefix +
                                  "Shaper" + str(index) + "Attach" +
                                  loop.fit_stem + letter + loop.side,
                                  parent=control_group)
            offset = c.createNode("transform", name=self.prefix +
                                  "Shaper" + str(index) + "Offset" +
                                  loop.fit_stem + letter + loop.side,
                                  parent=attach)
            c.parent(control, offset)
            c.xform(offset, worldSpace=True, translation=position)
            if index % 3 == 0:
                weights = c.skinPercent(skin,
                                        f"{mesh}.vtx[{vertices[index]}]",
                                        query=True, value=True) or []
                influences = c.skinCluster(skin, query=True,
                                           influence=True) or []
                driver = influences[max(range(len(weights)),
                                        key=lambda n: weights[n])]
                c.parentConstraint(driver, attach, maintainOffset=True)
            dm = c.createNode("decomposeMatrix", name=self.prefix +
                              "Shaper" + str(index) + "DM" +
                              loop.fit_stem + letter + loop.side)
            c.connectAttr(control + ".worldMatrix[0]", dm + ".inputMatrix")
            controls.append((control, dm))
            offsets.append(offset)
            control_set = self.prefix + "ControlSet"
            if c.objExists(control_set):
                c.sets(control, add=control_set)
        c.xform(curve, worldSpace=True, translation=(0, 0, 0),
                rotation=(0, 0, 0))
        for index, (control, dm) in enumerate(controls):
            if index % 3:
                anchor = index - 1 if index % 3 == 1 else (index + 1) % count
                c.parent(offsets[index], controls[anchor][0])
            c.connectAttr(dm + ".outputTranslate",
                          curve + f".cv[{index}]", force=True)
        if closed:
            c.connectAttr(controls[0][1] + ".outputTranslate",
                          curve + f".cv[{count}]", force=True)
        os_curve = c.duplicate(curve, name=curve.replace(
            "ShaperCurve", "ShaperOSCurve", 1))[0]
        c.setAttr(os_curve + ".visibility", 0, lock=True)
        for index, (control, _) in enumerate(controls):
            anchor = index if index % 3 == 0 else (
                index - 1 if index % 3 == 1 else (index + 1) % count)
            mm = c.createNode("multMatrix", name=self.prefix +
                              "Shaper" + str(index) + "MM" +
                              loop.fit_stem + letter + loop.side)
            c.connectAttr(control + ".worldMatrix[0]", mm + ".matrixIn[0]")
            c.connectAttr(offsets[anchor] + ".worldInverseMatrix[0]",
                          mm + ".matrixIn[1]")
            c.setAttr(mm + ".matrixIn[2]", *c.getAttr(offsets[anchor] +
                                                        ".matrix")[0], type="matrix")
            dm2 = c.createNode("decomposeMatrix", name=self.prefix +
                               "Shaper" + str(index) + "DM2" +
                               loop.fit_stem + letter + loop.side)
            c.connectAttr(mm + ".matrixSum", dm2 + ".inputMatrix")
            c.connectAttr(dm2 + ".outputTranslate",
                          os_curve + f".cv[{index}]", force=True)
            if index == 0 and closed:
                c.connectAttr(dm2 + ".outputTranslate",
                              os_curve + f".cv[{count}]", force=True)
        pose = self.prefix + "buildPose"
        if c.objExists(pose + ".advPyPoseData"):
            plug = pose + ".advPyPoseData"
            rows = json.loads(c.getAttr(plug) or "[]")
            for control, _ in controls:
                for attribute, value in (("translateX", 0),
                                         ("translateY", 0),
                                         ("translateZ", 0),
                                         ("rotateX", 0),
                                         ("rotateY", 0),
                                         ("rotateZ", 0),
                                         ("scaleX", 1),
                                         ("scaleY", 1),
                                         ("scaleZ", 1)):
                    rows.append([control, attribute, float(value)])
            c.setAttr(plug, json.dumps(rows, separators=(",", ":")),
                      type="string")
        elif c.objExists(pose):
            plug = pose + ".udExtraAttr"
            if not c.objExists(plug):
                c.addAttr(pose, longName="udExtraAttr", dataType="string")
            script = c.getAttr(plug) or ""
            script += "".join(
                'xform -os -t 0 0 0 -ro 0 0 0 -s 1 1 1 "' +
                control + '";' for control, _ in controls)
            c.setAttr(plug, script, type="string")
        return os_curve

    def _bind_curves(self, mesh: str, curves: list[str]) -> None:
        c = self.cmds
        existing = [node for node in c.listHistory(mesh) or []
                    if c.nodeType(node) == "shapersDeformer"]
        c.select([mesh, *curves], replace=True)
        native = getattr(c, "shapersAddCurve" if existing else
                         "shapersCreate", None)
        if native:
            native()
        else:
            module = _python_shapers(c)
            (module.add_curve if existing else module.create)()
        deformers = [node for node in c.listHistory(mesh) or []
                     if c.nodeType(node) == "shapersDeformer"]
        if not deformers:
            raise RuntimeError("Shapers 插件未创建变形器")
        for curve in curves:
            connected = c.listConnections(
                curve + ".worldSpace[0]", source=False,
                destination=True, type="shapersDeformer") or []
            if not set(connected).intersection(deformers):
                raise RuntimeError("Shapers 插件未绑定控制曲线：" + curve)
        main = self.prefix + "Main"
        for node in deformers:
            if not c.isConnected(main + ".shaperDisable",
                                 node + ".nodeState"):
                c.connectAttr(main + ".shaperDisable",
                              node + ".nodeState", force=True)

    def _loop_anchors(self, group: str) -> tuple[tuple[str, int], ...]:
        c = self.cmds
        anchors = []
        for node in c.listRelatives(group, allDescendents=True,
                                    type="transform", fullPath=True) or []:
            leaf = node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            match = re.match(r"Shaper(\d+)(?!Attach|Offset|DM)", leaf)
            if (not match or int(match.group(1)) % 3
                    or not c.attributeQuery("vtxNr", node=node,
                                            exists=True)):
                continue
            anchors.append((node, int(c.getAttr(node + ".vtxNr"))))
        return tuple(sorted(anchors, key=lambda item: int(re.match(
            r"Shaper(\d+)", item[0].rsplit("|", 1)[-1]
            .rsplit(":", 1)[-1]).group(1))))

    def _related_fit_joints(self, loop: ShapersFkLoop) -> set[str]:
        c = self.cmds
        fit = self.prefix + loop.fit_stem
        if not c.objExists(fit):
            return set()
        relatives = set()
        parents = c.listRelatives(fit, parent=True, type="joint") or []
        if parents:
            relatives.add(parents[0].rsplit(":", 1)[-1] + loop.side)
        children = c.listRelatives(fit, children=True, type="joint") or []
        controlled = []
        for child in children:
            stem = child.rsplit(":", 1)[-1]
            side = loop.side
            if (c.objExists(self.prefix + "FK" + stem + side)
                    or c.objExists(self.prefix + "AdvPy_" + stem +
                                   "FK" + side)):
                controlled.append(stem + side)
        if len(controlled) == 1:
            relatives.add(controlled[0])
        return relatives

    def _shortest_edge_pack(self, mesh: str, start: int,
                            end: int) -> ShapersEdgePack | None:
        c = self.cmds
        if start == end:
            return None
        components = c.polySelect(mesh, query=True, asSelectString=True,
                                  shortestEdgePath=(start, end)) or []
        if isinstance(components, str):
            components = [components]
        edges = []
        positions = {}
        for component in components:
            match = re.search(r"\.e\[(\d+)\]$", str(component))
            if match is None:
                raise RuntimeError("Maya 最短边路径返回了非边组件")
            index = int(match.group(1))
            info = c.polyInfo(f"{mesh}.e[{index}]",
                              edgeToVertex=True) or []
            numbers = [int(value) for value in re.findall(r"\d+", info[0])]
            if len(numbers) < 3:
                raise RuntimeError("无法读取 Shapers 桥接边拓扑")
            a, b = numbers[-2:]
            edges.append(ShapersEdge(index, a, b))
            for vertex in (a, b):
                if vertex not in positions:
                    positions[vertex] = tuple(c.xform(
                        f"{mesh}.vtx[{vertex}]", query=True,
                        worldSpace=True, translation=True))
        if len(edges) < 2:
            return None
        packs = plan_shapers_edge_packs(tuple(edges), positions, start)
        if len(packs) != 1 or packs[0].closed:
            raise RuntimeError("Shapers 最短边路径未形成单条开放桥接")
        return packs[0]

    def _automatic_bridges(
        self, loop: ShapersFkLoop, group: str, mesh: str,
        options: ShapersFkLoopOptions, root: str, sampler: str,
        skin: str,
    ) -> list[str]:
        c = self.cmds
        related = self._related_fit_joints(loop)
        if not related:
            return []
        other_anchors = []
        for candidate in c.listRelatives(root, children=True,
                                         type="transform", fullPath=True) or []:
            if (candidate == group
                    or not c.objExists(candidate + ".deformJoint")
                    or not c.objExists(candidate + ".skin")
                    or not c.objExists(candidate + ".loop")
                    or not c.getAttr(candidate + ".loop")):
                continue
            other = c.getAttr(candidate + ".deformJoint") or ""
            if (c.getAttr(candidate + ".skin") or "") != mesh:
                continue
            if other.rsplit("|", 1)[-1].rsplit(":", 1)[-1] not in related:
                continue
            other_anchors.extend(self._loop_anchors(candidate))
        curves = []
        made = set()
        for control, start in self._loop_anchors(group):
            position = tuple(c.xform(control, query=True,
                                     worldSpace=True, translation=True))
            nearest = sorted(other_anchors, key=lambda item: dist(
                position, c.xform(item[0], query=True,
                                  worldSpace=True, translation=True)))[:2]
            for _, end in nearest:
                pair = tuple(sorted((start, end)))
                if pair in made:
                    continue
                made.add(pair)
                pack = self._shortest_edge_pack(mesh, start, end)
                if pack is None:
                    continue
                positions = {vertex: tuple(c.xform(
                    f"{mesh}.vtx[{vertex}]", query=True,
                    worldSpace=True, translation=True))
                    for vertex in pack.vertices}
                source = self._edge_source(mesh, pack, skin)
                curves.append(self._add_loop(
                    source, mesh, options, root, sampler, skin,
                    edge_pack=pack, positions_by_vertex=positions))
        return curves

    def _end_joint_bridges(
        self, loop: ShapersFkLoop, group: str, mesh: str,
        options: ShapersFkLoopOptions, root: str, sampler: str,
        skin: str,
    ) -> list[str]:
        c = self.cmds
        fit = self.prefix + loop.fit_stem
        if not c.objExists(fit):
            return []
        children = c.listRelatives(fit, children=True,
                                   type="joint", fullPath=True) or []
        if len(children) != 1:
            return []
        child = children[0]
        stem = child.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if (c.listRelatives(child, children=True, type="joint")
                or c.objExists(self.prefix + "FK" + stem + loop.side)
                or c.objExists(self.prefix + "AdvPy_" + stem +
                               "FK" + loop.side)):
            return []
        position = c.xform(child, query=True, worldSpace=True,
                           translation=True)
        target = (-position[0], position[1], position[2]) if loop.side == "_L" else tuple(position)
        end, _ = self._nearest_vertex(sampler, mesh, target)
        curves = []
        made = set()
        for _, start in self._loop_anchors(group):
            pair = tuple(sorted((start, end)))
            if pair in made:
                continue
            made.add(pair)
            pack = self._shortest_edge_pack(mesh, start, end)
            if pack is None:
                continue
            positions = {vertex: tuple(c.xform(
                f"{mesh}.vtx[{vertex}]", query=True,
                worldSpace=True, translation=True))
                for vertex in pack.vertices}
            source = self._edge_source(mesh, pack, skin)
            curves.append(self._add_loop(
                source, mesh, options, root, sampler, skin,
                edge_pack=pack, positions_by_vertex=positions))
        return curves

    def _share_intersection_controls(self, root: str,
                                     mesh: str) -> None:
        c = self.cmds
        by_vertex: dict[int, list[tuple[str, bool]]] = {}
        for group in c.listRelatives(root, children=True,
                                     type="transform", fullPath=True) or []:
            if (not c.objExists(group + ".skin")
                    or c.getAttr(group + ".skin") != mesh
                    or not c.objExists(group + ".loop")):
                continue
            loop = bool(c.getAttr(group + ".loop"))
            for control, vertex in self._loop_anchors(group):
                by_vertex.setdefault(vertex, []).append((control, loop))
        for controls in by_vertex.values():
            if len(controls) < 2:
                continue
            controls.sort(key=lambda item: (
                not item[1],
                "IntersectDriven" in ((c.listRelatives(
                    item[0], parent=True, fullPath=True) or [""])[0]),
                item[0]))
            master = controls[0][0]
            for slave, _ in controls[1:]:
                offset = (c.listRelatives(slave, parent=True,
                                          fullPath=True) or [])[0]
                if "IntersectDriven" in offset:
                    continue
                name = offset.rsplit("|", 1)[-1].replace(
                    "Offset", "IntersectDriven", 1)
                driven = c.createNode("transform", name=name,
                                      parent=offset)
                c.parent(slave, driven)
                c.parentConstraint(master, driven, maintainOffset=False)
                for shape in c.listRelatives(slave, shapes=True,
                                             fullPath=True) or []:
                    c.setAttr(shape + ".visibility", 0, lock=False)

    def create_fk_loops(self, loops: tuple[ShapersFkLoop, ...],
                        mesh: str, options: ShapersFkLoopOptions) -> int:
        c = self.cmds
        selection = c.ls(selection=True, long=True) or []
        c.undoInfo(openChunk=True, chunkName="创建 Shapers FK 闭环")
        failed = False
        try:
            mesh = self._one(mesh)
            skin = self._ensure_skin(mesh)
            root = self._controls_root()
            sampler = c.createNode("closestPointOnMesh",
                                   name=self.prefix + "AdvPy_ShaperSampler#")
            shape = (c.listRelatives(mesh, shapes=True,
                                     noIntermediate=True, fullPath=True,
                                     type="mesh") or [])[0]
            c.connectAttr(shape + ".outMesh", sampler + ".inMesh")
            curves = []
            auto_bridge = len({loop.fit_stem for loop in loops}) > 1
            created_on_side: dict[str, int] = {}
            for loop in loops:
                curve = self._add_loop(loop, mesh, options,
                                       root, sampler, skin)
                curves.append(curve)
                if auto_bridge:
                    group = (c.listRelatives(curve, parent=True,
                                             fullPath=True) or [])[0]
                    if created_on_side.get(loop.side, 0):
                        curves.extend(self._automatic_bridges(
                            loop, group, mesh, options, root, sampler, skin))
                    curves.extend(self._end_joint_bridges(
                        loop, group, mesh, options, root, sampler, skin))
                created_on_side[loop.side] = created_on_side.get(loop.side, 0) + 1
            c.delete(sampler)
            self._share_intersection_controls(root, mesh)
            self._bind_curves(mesh, curves)
            return len(curves)
        except Exception:
            failed = True
            raise
        finally:
            c.undoInfo(closeChunk=True)
            if failed:
                c.undo()
            else:
                existing = [node for node in selection if c.objExists(node)]
                c.select(existing, replace=True) if existing else c.select(clear=True)

    def _mirrored_edge_packs(
        self, mesh: str, packs: tuple[ShapersEdgePack, ...],
        sampler: str,
    ) -> tuple[ShapersEdgePack, ...]:
        c = self.cmds
        source_edges = {edge for pack in packs for edge in pack.edges}
        mirrored = []
        for pack in packs:
            vertex_map = {}
            positions = {}
            for vertex in pack.vertices:
                source = tuple(c.xform(f"{mesh}.vtx[{vertex}]", query=True,
                                       worldSpace=True, translation=True))
                target, position = self._nearest_vertex(
                    sampler, mesh, (-source[0], source[1], source[2]))
                vertex_map[vertex] = target
                positions[target] = position
            if len(positions) != len(pack.vertices):
                raise ValueError("Shapers 镜像顶点不是一一对应")
            edges = []
            ordered = pack.vertices + ((pack.vertices[0],) if pack.closed else ())
            for start, end in zip(ordered, ordered[1:]):
                a, b = vertex_map[start], vertex_map[end]
                info = c.polyInfo(f"{mesh}.vtx[{a}]",
                                  vertexToEdge=True) or []
                candidates = [int(value) for value in re.findall(r"\d+", info[0])][1:]
                matching = []
                for index in candidates:
                    edge_info = c.polyInfo(f"{mesh}.e[{index}]",
                                           edgeToVertex=True) or []
                    pair = [int(value) for value in re.findall(
                        r"\d+", edge_info[0])][-2:]
                    if set(pair) == {a, b}:
                        matching.append(index)
                if len(matching) != 1:
                    raise ValueError("Shapers 镜像边无法唯一对应")
                edges.append(ShapersEdge(matching[0], a, b))
            if set(edges_item.index for edges_item in edges) <= source_edges:
                continue
            mirror = plan_shapers_edge_packs(
                tuple(edges), positions, vertex_map[pack.vertices[0]])
            if len(mirror) != 1:
                raise RuntimeError("Shapers 镜像选边未形成单条路径")
            mirrored.append(mirror[0])
        return tuple(mirrored)

    def create_edge_packs(self, mesh: str,
                          packs: tuple[ShapersEdgePack, ...],
                          options: ShapersFkLoopOptions) -> int:
        c = self.cmds
        selection = c.ls(selection=True, long=True) or []
        c.undoInfo(openChunk=True, chunkName="创建 Shapers 边控制")
        failed = False
        try:
            mesh = self._one(mesh)
            skin = self._ensure_skin(mesh)
            root = self._controls_root()
            sampler = c.createNode("closestPointOnMesh",
                                   name=self.prefix + "AdvPy_ShaperSampler#")
            shape = (c.listRelatives(mesh, shapes=True,
                                     noIntermediate=True, fullPath=True,
                                     type="mesh") or [])[0]
            c.connectAttr(shape + ".outMesh", sampler + ".inMesh")
            all_packs = list(packs)
            if options.mirror:
                all_packs.extend(self._mirrored_edge_packs(
                    mesh, packs, sampler))
            curves = []
            created_on_side: dict[str, int] = {}
            for pack in all_packs:
                positions = {vertex: tuple(c.xform(
                    f"{mesh}.vtx[{vertex}]", query=True, worldSpace=True,
                    translation=True)) for vertex in pack.vertices}
                source = self._edge_source(mesh, pack, skin)
                curve = self._add_loop(
                    source, mesh, options, root, sampler, skin,
                    edge_pack=pack, positions_by_vertex=positions)
                curves.append(curve)
                if pack.closed and len(packs) > 1:
                    group = (c.listRelatives(curve, parent=True,
                                             fullPath=True) or [])[0]
                    if created_on_side.get(source.side, 0):
                        curves.extend(self._automatic_bridges(
                            source, group, mesh, options, root, sampler, skin))
                    curves.extend(self._end_joint_bridges(
                        source, group, mesh, options, root, sampler, skin))
                if pack.closed:
                    created_on_side[source.side] = (
                        created_on_side.get(source.side, 0) + 1)
            c.delete(sampler)
            self._share_intersection_controls(root, mesh)
            self._bind_curves(mesh, curves)
            return len(curves)
        except Exception:
            failed = True
            raise
        finally:
            c.undoInfo(closeChunk=True)
            if failed:
                c.undo()
            else:
                existing = [node for node in selection if c.objExists(node)]
                c.select(existing, replace=True) if existing else c.select(clear=True)
