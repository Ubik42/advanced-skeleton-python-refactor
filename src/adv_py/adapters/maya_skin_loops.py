"""Maya edge-set operations for the original SkinLoops panel."""
from __future__ import annotations

from contextlib import contextmanager
from math import pi, sqrt
import re

from adv_py.core.skin_loops import (
    SkinLoopBindLoop, SkinLoopBindSpec, SkinLoopCopySpec,
    SkinLoopCutUpDeletePlan, SkinLoopCutUpPlan, SkinLoopSpec,
    partition_skin_loop_face_regions, partition_skin_loop_regions,
    validate_closed_loop,
)


_EDGE = re.compile(r"^(.*)\.e\[(\d+)\]$")


class MayaSkinLoopsHost:
    def __init__(self, namespace: str = "") -> None:
        from maya import cmds
        from maya.api import OpenMaya

        self.cmds = cmds
        self.om = OpenMaya
        self.namespace = namespace.strip(":")
        self._in_transaction = False

    def _name(self, leaf: str) -> str:
        return self.namespace + ":" + leaf if self.namespace else leaf

    def _unique(self, name: str, kind: str) -> str:
        matches = self.cmds.ls(name, long=True, type=kind) or []
        if len(matches) != 1:
            raise ValueError("SkinLoop 来源名称不唯一或不存在：" + name)
        return matches[0]

    def _edge_rows(self, mesh: str, edge_ids: tuple[int, ...]
                   ) -> tuple[tuple[int, int, int], ...]:
        shape = self.cmds.listRelatives(
            mesh, shapes=True, noIntermediate=True,
            fullPath=True, type="mesh") or []
        if len(shape) != 1:
            raise ValueError("SkinLoop 需要唯一的多边形网格 Shape")
        dag = self.om.MSelectionList().add(shape[0]).getDagPath(0)
        fn = self.om.MFnMesh(dag)
        if any(index < 0 or index >= fn.numEdges for index in edge_ids):
            raise ValueError("SkinLoop 网格边索引超出范围")
        return tuple((index, *fn.getEdgeVertices(index))
                     for index in edge_ids)

    def _mirrored_edges(self, mesh: str, edge_ids: tuple[int, ...]
                        ) -> tuple[int, ...]:
        shape = self.cmds.listRelatives(
            mesh, shapes=True, noIntermediate=True,
            fullPath=True, type="mesh")[0]
        dag = self.om.MSelectionList().add(shape).getDagPath(0)
        fn = self.om.MFnMesh(dag)
        points = fn.getPoints(self.om.MSpace.kWorld)
        edge_vertices = tuple(fn.getEdgeVertices(index)
                              for index in range(fn.numEdges))
        edge_by_vertices = {tuple(sorted(pair)): index
                            for index, pair in enumerate(edge_vertices)}
        vertices = {vertex for index in edge_ids
                    for vertex in edge_vertices[index]}
        mirrored_vertices = {}
        for vertex in vertices:
            point = points[vertex]
            reflected = self.om.MPoint(-point.x, point.y, point.z)
            _, face = fn.getClosestPoint(reflected, self.om.MSpace.kWorld)
            candidates = fn.getPolygonVertices(face)
            mirrored_vertices[vertex] = min(candidates, key=lambda candidate:
                (points[candidate].x - reflected.x) ** 2
                + (points[candidate].y - reflected.y) ** 2
                + (points[candidate].z - reflected.z) ** 2)
        mirrored = []
        for index in edge_ids:
            a, b = edge_vertices[index]
            opposite = edge_by_vertices.get(tuple(sorted((
                mirrored_vertices[a], mirrored_vertices[b]))))
            if opposite is None:
                raise ValueError("镜像顶点未构成对应网格边")
            mirrored.append(opposite)
        if len(set(mirrored)) != len(mirrored):
            raise ValueError("镜像 SkinLoop 网格边重复")
        return tuple(mirrored)

    def capture_skin_loop_input(self, mirror: bool):
        c = self.cmds
        selected = c.ls(selection=True, orderedSelection=True,
                        flatten=True, long=True) or []
        if len(selected) < 4 or _EDGE.fullmatch(selected[-1]):
            raise ValueError("先选择闭合网格边，最后选择 FK 控制器")
        control = self._unique(selected[-1], c.nodeType(selected[-1]))
        control_name = control.rsplit("|", 1)[-1]
        if ((self.namespace and not control_name.startswith(
                self.namespace + ":"))
                or (not self.namespace and ":" in control_name)):
            raise ValueError("FK 控制器不属于当前角色命名空间")
        edge_matches = [_EDGE.fullmatch(item) for item in selected[:-1]]
        if any(item is None for item in edge_matches):
            raise ValueError("SkinLoop 选择中只能包含一个网格的边和一个控制器")
        mesh = self._unique(edge_matches[0].group(1), "transform")
        if any(item.group(1) != mesh for item in edge_matches):
            raise ValueError("SkinLoop 网格边必须来自同一对象")
        edge_ids = tuple(int(item.group(2)) for item in edge_matches)
        leaf = control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if leaf.startswith("FK"):
            joint_leaf = leaf[2:]
        elif c.objExists(self._name("DeformSet")) and c.sets(
                control, isMember=self._name("DeformSet")):
            joint_leaf = leaf
        else:
            raise ValueError("SkinLoop 最后选择项必须是 FK 控制器或变形关节")
        deform_joint = self._unique(self._name(joint_leaf), "joint")
        opposite = None
        if mirror and joint_leaf.endswith(("_R", "_L")):
            mirror_leaf = joint_leaf[:-1] + (
                "L" if joint_leaf.endswith("_R") else "R")
            control_leaf = leaf[:-1] + (
                "L" if leaf.endswith("_R") else "R")
            mirror_control = self._unique(self._name(control_leaf),
                                          c.nodeType(control))
            mirror_joint = self._unique(self._name(mirror_leaf), "joint")
            mirror_ids = self._mirrored_edges(mesh, edge_ids)
            opposite = (mirror_control, mirror_joint,
                        self._edge_rows(mesh, mirror_ids))
        return (self._name("SkinLoops"), mesh, control, deform_joint,
                self._edge_rows(mesh, edge_ids), opposite)

    def preflight_skin_loop(self, spec: SkinLoopSpec) -> None:
        c = self.cmds
        if (c.objExists(spec.set_name)
                and c.nodeType(spec.set_name) != "objectSet"):
            raise ValueError("SkinLoop 名称被非集合节点占用：" + spec.set_name)
        if (c.objExists(spec.parent_set)
                and c.nodeType(spec.parent_set) != "objectSet"):
            raise ValueError("SkinLoops 总集合名称被占用")
        if any(c.objExists(name) and c.referenceQuery(
                name, isNodeReferenced=True)
               for name in (spec.set_name, spec.parent_set)):
            raise ValueError("不能改写引用场景中的 SkinLoop 集合")
        self._edge_rows(spec.mesh, spec.edge_ids)
        self._unique(spec.control, c.nodeType(spec.control))
        self._unique(spec.deform_joint, "joint")

    @contextmanager
    def transaction(self, label: str):
        c = self.cmds
        if self._in_transaction or not c.undoInfo(query=True, state=True):
            raise ValueError("SkinLoop 需要独立且开启 Undo 的 Maya 事务")
        self._in_transaction = True
        selection = c.ls(selection=True, long=True, flatten=True) or []
        c.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
        except Exception:
            c.undoInfo(closeChunk=True)
            c.undo()
            raise
        else:
            c.undoInfo(closeChunk=True)
        finally:
            self._in_transaction = False
            c.select(selection, replace=True) if selection else c.select(clear=True)

    def create_skin_loop(self, spec: SkinLoopSpec) -> None:
        if not self._in_transaction:
            raise RuntimeError("SkinLoop 创建必须位于事务中")
        c = self.cmds
        if not c.objExists(spec.parent_set):
            c.sets(empty=True, name=spec.parent_set)
        if c.objExists(spec.set_name):
            c.delete(spec.set_name)
        edges = [f"{spec.mesh}.e[{index}]" for index in spec.edge_ids]
        created = c.sets(edges, name=spec.set_name)
        if created != spec.set_name:
            raise RuntimeError("SkinLoop 集合名称漂移")
        c.sets(spec.set_name, add=spec.parent_set)

    def capture_skin_loop(self, spec: SkinLoopSpec) -> bool:
        c = self.cmds
        if (not c.objExists(spec.set_name)
                or c.nodeType(spec.set_name) != "objectSet"
                or not c.sets(spec.set_name, isMember=spec.parent_set)):
            return False
        members = c.ls(c.sets(spec.set_name, query=True) or [],
                       flatten=True, long=True) or []
        actual = tuple(sorted(int(match.group(2)) for item in members
                                  if (match := _EDGE.fullmatch(item))
                                  and match.group(1) == spec.mesh))
        return actual == spec.edge_ids and len(members) == len(actual)

    def select_all_skin_loops(self) -> int:
        c = self.cmds
        parent = self._name("SkinLoops")
        if not c.objExists(parent) or c.nodeType(parent) != "objectSet":
            raise ValueError("当前角色尚无 SkinLoops 集合")
        loops = [name for name in (c.sets(parent, query=True) or [])
                 if c.nodeType(name) == "objectSet"]
        if not loops:
            raise ValueError("当前角色的 SkinLoops 集合为空")
        edges = tuple(item for loop in loops
                      for item in (c.sets(loop, query=True) or []))
        if not edges:
            raise ValueError("SkinLoops 内没有网格边")
        c.select(edges, replace=True)
        return len(loops)

    def _skin(self, mesh: str) -> str | None:
        c = self.cmds
        skins = [node for node in (c.listHistory(
            mesh, pruneDagObjects=True) or [])
            if c.nodeType(node) == "skinCluster"]
        if len(skins) > 1:
            raise ValueError("SkinLoop Copy 不支持目标网格的多层 Skin")
        return skins[0] if skins else None

    def _mesh_transform(self, item: str) -> str:
        c = self.cmds
        node = item.split(".", 1)[0]
        if c.nodeType(node) == "mesh":
            parent = c.listRelatives(node, parent=True,
                                     fullPath=True) or []
            if len(parent) != 1:
                raise ValueError("SkinLoop Copy 网格 Shape 缺少唯一父级")
            node = parent[0]
        mesh = self._unique(node, "transform")
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise ValueError("SkinLoop Copy 需要唯一多边形网格 Shape")
        return mesh

    def capture_skin_loop_copy_input(self):
        c = self.cmds
        parent = self._name("SkinLoops")
        if not c.objExists(parent) or c.nodeType(parent) != "objectSet":
            raise ValueError("当前角色尚无 SkinLoops")
        loops = sorted(name for name in (c.sets(parent, query=True) or [])
                       if c.nodeType(name) == "objectSet")
        if not loops:
            raise ValueError("SkinLoops 集合没有子边环")
        first = next((item for loop in loops
                      for item in (c.ls(c.sets(loop, query=True) or [],
                                        flatten=True, long=True) or [])), None)
        if first is None or not _EDGE.fullmatch(first):
            raise ValueError("SkinLoops 集合缺少网格边")
        source_mesh = self._mesh_transform(first)
        source_skin = self._skin(source_mesh)
        if not source_skin:
            raise ValueError("SkinLoop 来源网格尚未绑定 Skin")
        influences = tuple(self._unique(node, "joint")
                           for node in (c.skinCluster(
                               source_skin, query=True, influence=True) or []))
        selected = c.ls(selection=True, long=True, flatten=True) or []
        if not selected:
            raise ValueError("先选择要复制权重的网格或网格组件")
        components = any("." in item for item in selected)
        if components and any("." not in item for item in selected):
            raise ValueError("SkinLoop Copy 不能混选网格对象和组件")
        groups: dict[str, list[str]] = {}
        for item in selected:
            mesh = self._mesh_transform(item)
            groups.setdefault(mesh, []).append(item)
        if components and len(groups) != 1:
            raise ValueError("SkinLoop Copy 的组件必须来自同一目标网格")
        targets = tuple((mesh, tuple(items) if components else (),
                         self._skin(mesh))
                        for mesh, items in groups.items())
        return (source_mesh, source_skin, influences,
                int(c.getAttr(source_skin + ".skinningMethod")), targets)

    def preflight_skin_loop_copy(self, spec: SkinLoopCopySpec) -> None:
        c = self.cmds
        if self._mesh_transform(spec.source_mesh) != spec.source_mesh:
            raise ValueError("SkinLoop 来源网格已改变")
        if self._mesh_transform(spec.target_mesh) != spec.target_mesh:
            raise ValueError("SkinLoop 目标网格已改变")
        if self._skin(spec.source_mesh) != spec.source_skin:
            raise ValueError("SkinLoop 来源 Skin 已改变")
        source_influences = tuple(self._unique(node, "joint") for node in (
            c.skinCluster(spec.source_skin, query=True, influence=True) or []))
        if (set(source_influences) != set(spec.source_influences)
                or int(c.getAttr(spec.source_skin + ".skinningMethod"))
                != spec.skinning_method):
            raise ValueError("SkinLoop 来源蒙皮设置已改变")
        if self._skin(spec.target_mesh) != spec.target_skin:
            raise ValueError("SkinLoop 目标 Skin 已改变")
        if (spec.target_components and tuple(c.ls(
                spec.target_components, long=True, flatten=True) or ())
                != spec.target_components):
            raise ValueError("SkinLoop 目标组件已改变")
        if spec.target_skin is None:
            leaf = spec.target_mesh.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            name = self._name("AdvPy_SkinLoopCopy_" + leaf)
            if c.objExists(name):
                raise ValueError("SkinLoop 新 Skin 名称被占用：" + name)
        elif c.referenceQuery(spec.target_skin, isNodeReferenced=True):
            raise ValueError("不能向引用的目标 Skin 增加影响关节")

    def copy_skin_loop_weights(self, spec: SkinLoopCopySpec) -> None:
        if not self._in_transaction:
            raise RuntimeError("SkinLoop Copy 必须位于事务中")
        c = self.cmds
        skin = spec.target_skin
        if skin is None:
            leaf = spec.target_mesh.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            skin = c.skinCluster(
                list(spec.source_influences), spec.target_mesh,
                toSelectedBones=True, maximumInfluences=3,
                name=self._name("AdvPy_SkinLoopCopy_" + leaf))[0]
        else:
            current = {self._unique(node, "joint") for node in (
                c.skinCluster(skin, query=True, influence=True) or [])}
            for joint in spec.source_influences:
                if joint not in current:
                    c.skinCluster(skin, edit=True, addInfluence=joint,
                                  lockWeights=False, weight=0.0)
        c.select(spec.source_mesh, replace=True)
        c.select(spec.target_components or (spec.target_mesh,), add=True)
        c.copySkinWeights(noMirror=True, surfaceAssociation="closestPoint",
                          influenceAssociation="closestJoint")
        c.setAttr(skin + ".skinningMethod", spec.skinning_method)
        c.skinCluster(skin, edit=True, removeUnusedInfluence=True)

    def capture_skin_loop_copy(self, spec: SkinLoopCopySpec) -> bool:
        c = self.cmds
        skin = self._skin(spec.target_mesh)
        if not skin or (spec.target_skin and skin != spec.target_skin):
            return False
        influences = {self._unique(node, "joint") for node in (
            c.skinCluster(skin, query=True, influence=True) or [])}
        return (bool(set(spec.source_influences) & influences)
                and int(c.getAttr(skin + ".skinningMethod"))
                == spec.skinning_method)

    def _bind_loop_vertices(self, loop_set: str, mesh: str,
                            edge_vertices: tuple[tuple[int, int], ...]
                            ) -> tuple[int, ...]:
        c = self.cmds
        members = c.ls(c.sets(loop_set, query=True) or [],
                       long=True, flatten=True) or []
        matches = [_EDGE.fullmatch(item) for item in members]
        if (not members or any(match is None or match.group(1) != mesh
                               for match in matches)):
            raise ValueError("SkinLoop 集合包含其他网格或非边成员：" + loop_set)
        rows = []
        for match in matches:
            index = int(match.group(2))
            if index >= len(edge_vertices):
                raise ValueError("SkinLoop 集合含无效边索引：" + loop_set)
            rows.append((index, *edge_vertices[index]))
        validate_closed_loop(tuple(rows))
        return tuple(sorted({vertex for _, a, b in rows
                             for vertex in (a, b)}))

    def capture_skin_loop_bind_input(self) -> tuple[SkinLoopBindSpec, ...]:
        c = self.cmds
        parent = self._name("SkinLoops")
        if not c.objExists(parent) or c.nodeType(parent) != "objectSet":
            raise ValueError("当前角色尚无 SkinLoops 集合")
        loop_sets = tuple(sorted(name for name in (
            c.sets(parent, query=True) or [])
            if c.nodeType(name) == "objectSet"))
        if not loop_sets:
            raise ValueError("SkinLoops 总集合没有边环")
        selected = c.ls(selection=True, long=True) or []
        if not selected or any("." in name for name in selected):
            raise ValueError("先选择待绑定的网格对象，不要选择网格组件")
        root = self._unique(self._name("Root_M"), "joint")
        specs = []
        for selected_mesh in selected:
            mesh = self._mesh_transform(selected_mesh)
            shape = c.listRelatives(mesh, shapes=True,
                                    noIntermediate=True, fullPath=True,
                                    type="mesh")[0]
            fn = self.om.MFnMesh(
                self.om.MSelectionList().add(shape).getDagPath(0))
            edges = tuple(fn.getEdgeVertices(index)
                          for index in range(fn.numEdges))
            loops = []
            for loop_set in loop_sets:
                members = c.ls(c.sets(loop_set, query=True) or [],
                               long=True, flatten=True) or []
                if not members:
                    continue
                first = _EDGE.fullmatch(members[0])
                if first is None or first.group(1) != mesh:
                    continue
                vertices = self._bind_loop_vertices(loop_set, mesh, edges)
                leaf = loop_set.rsplit(":", 1)[-1]
                if not leaf.startswith("SkinLoops_"):
                    raise ValueError("SkinLoop 子集合名称不符合原版规则："
                                     + loop_set)
                joint = self._unique(self._name(leaf[len("SkinLoops_"):]),
                                     "joint")
                parent_joint = c.listRelatives(
                    joint, parent=True, fullPath=True, type="joint") or []
                loops.append(SkinLoopBindLoop(
                    loop_set, joint,
                    parent_joint[0] if parent_joint else None, vertices))
            if not loops:
                continue
            leaf = mesh.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            specs.append(SkinLoopBindSpec(
                mesh, fn.numVertices, edges, root, self._skin(mesh),
                self._name("AdvPy_SkinLoopBind_" + leaf), tuple(loops)))
        if not specs:
            raise ValueError("所选网格没有对应的 SkinLoop 边环")
        return tuple(specs)

    def preflight_skin_loop_bind(self, spec: SkinLoopBindSpec) -> None:
        c = self.cmds
        if self._skin(spec.mesh) != spec.existing_skin:
            raise ValueError("SkinLoop 目标 Skin 在执行前改变")
        if (spec.existing_skin is None and c.objExists(spec.new_skin_name)):
            raise ValueError("SkinLoop 新 Skin 名称已被占用："
                             + spec.new_skin_name)
        if (spec.existing_skin is not None and c.referenceQuery(
                spec.existing_skin, isNodeReferenced=True)):
            raise ValueError("不能改写引用场景中的 Skin")
        if self._unique(spec.root_joint, "joint") != spec.root_joint:
            raise ValueError("SkinLoop 根关节已改变")
        shape = c.listRelatives(spec.mesh, shapes=True,
                                noIntermediate=True, fullPath=True,
                                type="mesh") or []
        if len(shape) != 1:
            raise ValueError("SkinLoop 网格 Shape 已改变")
        fn = self.om.MFnMesh(
            self.om.MSelectionList().add(shape[0]).getDagPath(0))
        if (fn.numVertices != spec.vertex_count
                or tuple(fn.getEdgeVertices(index)
                         for index in range(fn.numEdges))
                != spec.edge_vertices):
            raise ValueError("SkinLoop 网格拓扑已改变")
        for loop in spec.loops:
            if (self._bind_loop_vertices(
                    loop.set_name, spec.mesh, spec.edge_vertices)
                    != loop.vertices
                    or self._unique(loop.deform_joint, "joint")
                    != loop.deform_joint
                    or (c.listRelatives(loop.deform_joint, parent=True,
                                        fullPath=True, type="joint") or [])
                    != ([loop.parent_joint] if loop.parent_joint else [])):
                raise ValueError("SkinLoop 边环或关节父级已改变："
                                 + loop.set_name)

    def _skin_percent(self, skin: str, mesh: str,
                      vertices: tuple[int, ...] | frozenset[int],
                      values: tuple[tuple[str, float], ...]) -> None:
        if not vertices:
            return
        components = [f"{mesh}.vtx[{index}]" for index in sorted(vertices)]
        self.cmds.skinPercent(skin, components,
                              transformValue=list(values),
                              normalize=True, zeroRemainingInfluences=True)

    def _hammer_skin_vertices(self, mesh: str,
                              vertices: set[int]) -> None:
        if not vertices:
            return
        from maya import mel

        self.cmds.select([f"{mesh}.vtx[{index}]"
                          for index in sorted(vertices)], replace=True)
        mel.eval("weightHammerVerts;")

    def _active_skin_influences(self, skin: str, mesh: str, vertex: int,
                                influences: tuple[str, ...]
                                ) -> tuple[str, ...]:
        component = f"{mesh}.vtx[{vertex}]"
        return tuple(joint for joint in influences
                     if float(self.cmds.skinPercent(
                         skin, component, query=True,
                         transform=joint)) > 1e-7)

    def bind_skin_loops(self, spec: SkinLoopBindSpec) -> None:
        if not self._in_transaction:
            raise RuntimeError("SkinLoop Bind 必须位于事务中")
        c = self.cmds
        skin = spec.existing_skin
        if skin is None:
            skin = c.skinCluster(
                [spec.root_joint], spec.mesh, toSelectedBones=True,
                maximumInfluences=3, dropoffRate=4,
                name=spec.new_skin_name)[0]
        else:
            active = {self._unique(name, "joint") for name in (
                c.skinCluster(skin, query=True, influence=True) or [])}
            if spec.root_joint not in active:
                c.skinCluster(skin, edit=True, addInfluence=spec.root_joint,
                              lockWeights=False, weight=0.0)
        all_vertices = tuple(range(spec.vertex_count))
        self._skin_percent(skin, spec.mesh, all_vertices,
                           ((spec.root_joint, 1.0),))
        for loop in spec.loops:
            active = {self._unique(name, "joint") for name in (
                c.skinCluster(skin, query=True, influence=True) or [])}
            for joint in (loop.deform_joint, loop.parent_joint):
                if joint and joint not in active:
                    c.skinCluster(skin, edit=True, addInfluence=joint,
                                  lockWeights=False, weight=0.0)
                    active.add(joint)
            self._skin_percent(skin, spec.mesh, loop.vertices,
                               ((loop.deform_joint, 1.0),))
        blocked = frozenset(vertex for loop in spec.loops
                            for vertex in loop.vertices)
        neighbors = [set() for _ in range(spec.vertex_count)]
        for a, b in spec.edge_vertices:
            neighbors[a].add(b)
            neighbors[b].add(a)
        self._hammer_skin_vertices(
            spec.mesh, set(range(spec.vertex_count)) - blocked)
        near = {neighbor for vertex in blocked
                for neighbor in neighbors[vertex] if neighbor not in blocked}
        self._hammer_skin_vertices(spec.mesh, near)
        regions = partition_skin_loop_regions(
            spec.vertex_count, spec.edge_vertices, blocked)
        region_by_vertex = {vertex: index for index, region in
                            enumerate(regions) for vertex in region}
        influences = tuple(self._unique(name, "joint") for name in (
            c.skinCluster(skin, query=True, influence=True) or []))
        for loop in spec.loops:
            descendants = set(c.listRelatives(
                loop.deform_joint, allDescendents=True,
                fullPath=True, type="joint") or [])
            candidate_seeds = {}
            for vertex in loop.vertices:
                for neighbor in neighbors[vertex]:
                    if neighbor in region_by_vertex:
                        candidate_seeds.setdefault(
                            region_by_vertex[neighbor], neighbor)
            for index, seed in sorted(candidate_seeds.items()):
                active = self._active_skin_influences(
                    skin, spec.mesh, seed, influences)
                if (set(active) & descendants) or len(active) == 1:
                    self._skin_percent(
                        skin, spec.mesh, regions[index],
                        ((loop.deform_joint, 1.0),))
        for loop in spec.loops:
            leaf = loop.deform_joint.rsplit("|", 1)[-1]
            if re.search(r"Part\d+_[RLM]$", leaf) or not loop.parent_joint:
                continue
            self._skin_percent(skin, spec.mesh, loop.vertices,
                               ((loop.deform_joint, 0.5),
                                (loop.parent_joint, 0.5)))
            ring = {neighbor for vertex in loop.vertices
                    for neighbor in neighbors[vertex]
                    if neighbor not in blocked}
            self._hammer_skin_vertices(spec.mesh, ring)
        c.skinCluster(skin, edit=True, removeUnusedInfluence=True)

    def capture_skin_loop_bind(self, spec: SkinLoopBindSpec) -> bool:
        c = self.cmds
        skin = self._skin(spec.mesh)
        if not skin or (spec.existing_skin and skin != spec.existing_skin):
            return False
        influences = {self._unique(name, "joint") for name in (
            c.skinCluster(skin, query=True, influence=True) or [])}
        expected_joints = {loop.deform_joint for loop in spec.loops}
        expected_joints.update(loop.parent_joint for loop in spec.loops
                               if loop.parent_joint and not re.search(
                                   r"Part\d+_[RLM]$",
                                   loop.deform_joint.rsplit("|", 1)[-1]))
        if not expected_joints <= influences:
            return False
        for loop in spec.loops:
            leaf = loop.deform_joint.rsplit("|", 1)[-1]
            expected = (1.0 if not loop.parent_joint or re.search(
                r"Part\d+_[RLM]$", leaf) else 0.5)
            for vertex in loop.vertices:
                component = f"{spec.mesh}.vtx[{vertex}]"
                value = float(c.skinPercent(
                    skin, component, query=True,
                    transform=loop.deform_joint))
                if abs(value - expected) > 1e-4:
                    return False
                if loop.parent_joint and expected == 0.5:
                    parent_weight = float(c.skinPercent(
                        skin, component, query=True,
                        transform=loop.parent_joint))
                    if abs(parent_weight - 0.5) > 1e-4:
                        return False
        return True

    def capture_skin_loop_cut_up_delete_input(
        self,
    ) -> tuple[str | None, str | None]:
        c = self.cmds
        layer = self._name("CutUp")
        group = self._name("CutUpGeometry")
        if c.objExists(layer) and c.nodeType(layer) != "displayLayer":
            raise ValueError("CutUp 名称被非显示层节点占用")
        if c.objExists(group) and c.nodeType(group) != "transform":
            raise ValueError("CutUpGeometry 名称被非 Transform 占用")
        for name in (layer, group):
            if c.objExists(name) and c.referenceQuery(
                    name, isNodeReferenced=True):
                raise ValueError("不能删除引用场景中的 CutUp 产物")
        return (layer if c.objExists(layer) else None,
                group if c.objExists(group) else None)

    def delete_skin_loop_cut_up(
        self, plan: SkinLoopCutUpDeletePlan,
    ) -> None:
        if not self._in_transaction:
            raise RuntimeError("CutUp 删除必须位于事务中")
        c = self.cmds
        if plan.layer:
            if not c.objExists(plan.layer):
                raise ValueError("CutUp 显示层在执行前消失")
            c.delete(plan.layer)
        if plan.geometry_group:
            if not c.objExists(plan.geometry_group):
                raise ValueError("CutUp 几何组在执行前消失")
            c.delete(plan.geometry_group)

    def capture_skin_loop_cut_up_deleted(
        self, plan: SkinLoopCutUpDeletePlan,
    ) -> bool:
        return all(not self.cmds.objExists(name)
                   for name in (plan.layer, plan.geometry_group) if name)

    def capture_skin_loop_cut_up_input(
        self,
    ) -> tuple[str, str, tuple[SkinLoopBindSpec, ...]]:
        return (self._name("CutUp"), self._name("CutUpGeometry"),
                self.capture_skin_loop_bind_input())

    def preflight_skin_loop_cut_up(self, plan: SkinLoopCutUpPlan) -> None:
        c = self.cmds
        if c.objExists(plan.layer) or c.objExists(plan.geometry_group):
            raise ValueError("CutUp 已存在；重建前先使用删除入口")
        self._unique(self._name("Geometry"), "transform")
        for spec in plan.bindings:
            if self._mesh_transform(spec.mesh) != spec.mesh:
                raise ValueError("CutUp 来源网格已改变")
            for loop in spec.loops:
                if (self._bind_loop_vertices(
                        loop.set_name, spec.mesh,
                        spec.edge_vertices) != loop.vertices
                        or self._unique(loop.deform_joint, "joint")
                        != loop.deform_joint):
                    raise ValueError("CutUp 边环或关节已改变："
                                     + loop.set_name)
            leaf = spec.mesh.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            for name in ("AdvPy_SkinLoopCutUpTemp_" + leaf,
                         "AdvPy_SkinLoopCutUpTempSkin_" + leaf):
                if c.objExists(self._name(name)):
                    raise ValueError("CutUp 临时名称已被占用：" + name)
            shape = c.listRelatives(spec.mesh, shapes=True,
                                    noIntermediate=True, fullPath=True,
                                    type="mesh")[0]
            fn = self.om.MFnMesh(
                self.om.MSelectionList().add(shape).getDagPath(0))
            if (fn.numVertices != spec.vertex_count
                    or tuple(fn.getEdgeVertices(index)
                             for index in range(fn.numEdges))
                    != spec.edge_vertices):
                raise ValueError("CutUp 来源网格拓扑已改变")
            blocked = self._cut_up_loop_edges(spec)
            regions = partition_skin_loop_face_regions(
                tuple(tuple(fn.getPolygonEdges(index))
                      for index in range(fn.numPolygons)), blocked)
            if len(regions) < 2:
                raise ValueError("SkinLoop 边环未把网格面分为至少两块："
                                 + spec.mesh)
            for index in range(len(regions)):
                name = self._name(f"AdvPy_{leaf}_SkinLoopCut{index + 1}")
                if c.objExists(name):
                    raise ValueError("CutUp 分片名称已被占用：" + name)

    def _cut_up_loop_edges(self, spec: SkinLoopBindSpec) -> frozenset[int]:
        c = self.cmds
        indices = set()
        for loop in spec.loops:
            members = c.ls(c.sets(loop.set_name, query=True) or [],
                           flatten=True, long=True) or []
            for item in members:
                match = _EDGE.fullmatch(item)
                if not match or match.group(1) != spec.mesh:
                    raise ValueError("CutUp 边环成员不属于目标网格")
                indices.add(int(match.group(2)))
        return frozenset(indices)

    def _cut_up_region_joint(
        self, skin: str, mesh: str, vertices: set[int],
        candidates: tuple[str, ...],
    ) -> str:
        from maya.api import OpenMayaAnim

        c = self.cmds
        shape = c.listRelatives(mesh, shapes=True,
                                noIntermediate=True, fullPath=True,
                                type="mesh")[0]
        dag = self.om.MSelectionList().add(shape).getDagPath(0)
        skin_node = self.om.MSelectionList().add(skin).getDependNode(0)
        fn = OpenMayaAnim.MFnSkinCluster(skin_node)
        order = {path.fullPathName(): index
                 for index, path in enumerate(fn.influenceObjects())}
        candidates = tuple(joint for joint in candidates if joint in order)
        if not candidates:
            raise RuntimeError("CutUp 临时 Skin 缺少有效关节")
        component_fn = self.om.MFnSingleIndexedComponent()
        component = component_fn.create(self.om.MFn.kMeshVertComponent)
        component_fn.addElements(sorted(vertices))
        values, width = fn.getWeights(dag, component)
        if width != len(order) or len(values) != len(vertices) * width:
            raise RuntimeError("CutUp 临时 Skin 权重维度无效")
        totals = {joint: 0.0 for joint in candidates}
        for offset in range(len(vertices)):
            for joint in candidates:
                totals[joint] += float(values[offset * width + order[joint]])
        return max(candidates, key=lambda joint: totals[joint])

    def _cut_up_border_loops(
        self, piece: str,
    ) -> tuple[tuple[tuple[int, int, int], ...], ...]:
        c = self.cmds
        shape = c.listRelatives(piece, shapes=True,
                                noIntermediate=True, fullPath=True,
                                type="mesh") or []
        if len(shape) != 1:
            raise RuntimeError("CutUp 分片缺少唯一 Mesh Shape")
        fn = self.om.MFnMesh(
            self.om.MSelectionList().add(shape[0]).getDagPath(0))
        counts: dict[int, int] = {}
        for face in range(fn.numPolygons):
            for edge in fn.getPolygonEdges(face):
                counts[edge] = counts.get(edge, 0) + 1
        border = {edge: fn.getEdgeVertices(edge)
                  for edge, count in counts.items() if count == 1}
        if not border:
            return ()
        by_vertex: dict[int, set[int]] = {}
        for edge, (a, b) in border.items():
            by_vertex.setdefault(a, set()).add(edge)
            by_vertex.setdefault(b, set()).add(edge)
        remaining = set(border)
        loops = []
        while remaining:
            first = remaining.pop()
            component = {first}
            stack = [first]
            while stack:
                a, b = border[stack.pop()]
                for vertex in (a, b):
                    for neighbor in by_vertex[vertex] & remaining:
                        remaining.remove(neighbor)
                        component.add(neighbor)
                        stack.append(neighbor)
            rows = tuple((index, *border[index])
                         for index in sorted(component))
            validate_closed_loop(rows)
            loops.append(rows)
        return tuple(loops)

    def _cap_skin_loop_cut_piece(self, piece: str) -> None:
        c = self.cmds
        loops = self._cut_up_border_loops(piece)
        if not loops:
            return
        shape = c.listRelatives(piece, shapes=True,
                                noIntermediate=True, fullPath=True,
                                type="mesh")[0]
        fn = self.om.MFnMesh(
            self.om.MSelectionList().add(shape).getDagPath(0))
        points = fn.getPoints(self.om.MSpace.kWorld)
        original_count = fn.numVertices
        region_vertices = {vertex for face in range(fn.numPolygons)
                           for vertex in fn.getPolygonVertices(face)}
        center = tuple(sum(float(points[index][axis])
                           for index in region_vertices)
                       / len(region_vertices) for axis in range(3))
        loop_info = []
        for loop in loops:
            vertices = {vertex for _, a, b in loop for vertex in (a, b)}
            midpoint = tuple(sum(float(points[index][axis])
                                 for index in vertices) / len(vertices)
                             for axis in range(3))
            circumference = sum(sqrt(sum(
                (float(points[a][axis]) - float(points[b][axis])) ** 2
                for axis in range(3))) for _, a, b in loop)
            loop_info.append((vertices, midpoint,
                              circumference / (2.0 * pi)))
        c.polyExtrudeEdge(
            [f"{piece}.e[{index}]" for loop in loops
             for index, _, _ in loop],
            constructionHistory=False, keepFacesTogether=True)
        shape = c.listRelatives(piece, shapes=True,
                                noIntermediate=True, fullPath=True,
                                type="mesh")[0]
        fn = self.om.MFnMesh(
            self.om.MSelectionList().add(shape).getDagPath(0))
        after = fn.getPoints(self.om.MSpace.kWorld)
        if fn.numVertices <= original_count:
            raise RuntimeError("CutUp 边环挤出没有产生新顶点")
        assigned: list[list[int]] = [[] for _ in loops]
        for vertex in range(original_count, fn.numVertices):
            point = after[vertex]
            closest = min(range(len(loops)), key=lambda index:
                min(sum((float(point[axis])
                         - float(points[original][axis])) ** 2
                        for axis in range(3))
                    for original in loop_info[index][0]))
            assigned[closest].append(vertex)
        for indices, (_, midpoint, radius) in zip(assigned, loop_info):
            if not indices:
                raise RuntimeError("CutUp 边环挤出顶点未映射到对应切口")
            components = [f"{piece}.vtx[{index}]" for index in indices]
            c.scale(0.25, 0.25, 0.25, components,
                    pivot=midpoint, relative=True, worldSpace=True)
            direction = tuple(midpoint[axis] - center[axis]
                              for axis in range(3))
            length = sqrt(sum(value * value for value in direction))
            if length > 1e-8:
                c.move(*(value * radius * 0.5 / length
                         for value in direction),
                       components, relative=True, worldSpace=True)
        while True:
            borders = self._cut_up_border_loops(piece)
            if not borders:
                break
            c.polyCloseBorder(
                [f"{piece}.e[{index}]"
                 for index, _, _ in borders[0]],
                constructionHistory=False)
            if len(self._cut_up_border_loops(piece)) >= len(borders):
                raise RuntimeError("CutUp 切口封口后仍存在同数边界")

    def create_skin_loop_cut_up(
        self, plan: SkinLoopCutUpPlan,
    ) -> tuple[str, ...]:
        if not self._in_transaction:
            raise RuntimeError("CutUp 创建必须位于事务中")
        c = self.cmds
        c.createDisplayLayer(empty=True, name=plan.layer)
        c.setAttr(plan.layer + ".color", 29)
        c.setAttr(plan.layer + ".displayType", 2)
        group = c.createNode("transform", name=plan.geometry_group,
                             parent=self._unique(
                                 self._name("Geometry"), "transform"))
        pieces = []
        for spec in plan.bindings:
            leaf = spec.mesh.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            temp_name = self._name("AdvPy_SkinLoopCutUpTemp_" + leaf)
            temp = c.duplicate(spec.mesh, name=temp_name,
                               returnRootsOnly=True)[0]
            c.delete(temp, constructionHistory=True)
            temp = self._unique(temp_name, "transform")
            temp_bind = SkinLoopBindSpec(
                temp, spec.vertex_count, spec.edge_vertices,
                spec.root_joint, None,
                self._name("AdvPy_SkinLoopCutUpTempSkin_" + leaf),
                spec.loops)
            self.bind_skin_loops(temp_bind)
            temp_skin = self._skin(temp)
            source_shape = c.listRelatives(spec.mesh, shapes=True,
                                           noIntermediate=True,
                                           fullPath=True, type="mesh")[0]
            source_fn = self.om.MFnMesh(
                self.om.MSelectionList().add(source_shape).getDagPath(0))
            face_edges = tuple(tuple(source_fn.getPolygonEdges(index))
                               for index in range(source_fn.numPolygons))
            regions = partition_skin_loop_face_regions(
                face_edges, self._cut_up_loop_edges(spec))
            candidates = tuple(dict.fromkeys((
                spec.root_joint, *(loop.deform_joint for loop in spec.loops))))
            for index, region in enumerate(regions, 1):
                vertices = {vertex for face in region
                            for vertex in source_fn.getPolygonVertices(face)}
                joint = self._cut_up_region_joint(
                    temp_skin, temp, vertices, candidates)
                name = self._name(f"AdvPy_{leaf}_SkinLoopCut{index}")
                piece = c.duplicate(temp, name=name,
                                    returnRootsOnly=True)[0]
                c.delete(piece, constructionHistory=True)
                piece = self._unique(name, "transform")
                remove = [f"{piece}.f[{face}]"
                          for face in range(source_fn.numPolygons)
                          if face not in region]
                if remove:
                    c.delete(remove)
                self._cap_skin_loop_cut_piece(piece)
                c.delete(piece, constructionHistory=True)
                piece = c.parent(piece, group, absolute=True)[0]
                piece = self._unique(name, "transform")
                c.addAttr(piece, longName="advPySkinLoopCutUpOwner",
                          dataType="string")
                c.setAttr(piece + ".advPySkinLoopCutUpOwner",
                          spec.mesh, type="string", lock=True)
                c.parentConstraint(joint, piece, maintainOffset=True,
                                   name=name + "ParentConstraint")
                c.scaleConstraint(joint, piece, maintainOffset=True,
                                  name=name + "ScaleConstraint")
                c.editDisplayLayerMembers(plan.layer, piece,
                                          noRecurse=True)
                pieces.append(piece)
            c.delete(temp)
            if c.objExists(temp_skin):
                c.delete(temp_skin)
        return tuple(pieces)

    def capture_skin_loop_cut_up(
        self, plan: SkinLoopCutUpPlan, pieces: tuple[str, ...],
    ) -> bool:
        c = self.cmds
        if (not pieces or not c.objExists(plan.layer)
                or c.nodeType(plan.layer) != "displayLayer"
                or int(c.getAttr(plan.layer + ".color")) != 29
                or int(c.getAttr(plan.layer + ".displayType")) != 2
                or (c.ls(plan.geometry_group, long=True,
                         type="transform") or []) == []):
            return False
        group = self._unique(plan.geometry_group, "transform")
        geometry = self._unique(self._name("Geometry"), "transform")
        if (c.listRelatives(group, parent=True, fullPath=True) or []) != [geometry]:
            return False
        expected_count = 0
        for spec in plan.bindings:
            shape = c.listRelatives(spec.mesh, shapes=True,
                                    noIntermediate=True, fullPath=True,
                                    type="mesh") or []
            if len(shape) != 1:
                return False
            fn = self.om.MFnMesh(
                self.om.MSelectionList().add(shape[0]).getDagPath(0))
            expected_count += len(partition_skin_loop_face_regions(
                tuple(tuple(fn.getPolygonEdges(index))
                      for index in range(fn.numPolygons)),
                self._cut_up_loop_edges(spec)))
        if len(pieces) != expected_count:
            return False
        owners = {spec.mesh for spec in plan.bindings}
        if any(c.objExists(self._name(prefix
                                      + spec.mesh.rsplit("|", 1)[-1].rsplit(
                                          ":", 1)[-1]))
               for spec in plan.bindings
               for prefix in ("AdvPy_SkinLoopCutUpTemp_",
                              "AdvPy_SkinLoopCutUpTempSkin_")):
            return False
        for piece in pieces:
            if (not c.objExists(piece)
                    or (c.listRelatives(piece, parent=True,
                                        fullPath=True) or []) != [group]
                    or not c.objExists(piece + ".advPySkinLoopCutUpOwner")
                    or c.getAttr(piece + ".advPySkinLoopCutUpOwner") not in owners
                    or not (c.listRelatives(piece, shapes=True,
                                            noIntermediate=True,
                                            type="mesh") or [])
                    or int(c.polyEvaluate(piece, face=True)) < 1
                    or self._cut_up_border_loops(piece)
                    or not (c.listConnections(piece, source=True,
                                              destination=False,
                                              type="parentConstraint") or [])
                    or not (c.listConnections(piece, source=True,
                                              destination=False,
                                              type="scaleConstraint") or [])):
                return False
        return True
