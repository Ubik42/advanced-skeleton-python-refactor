"""Maya edge-set operations for the original SkinLoops panel."""
from __future__ import annotations

from contextlib import contextmanager
from fnmatch import fnmatchcase
import re

from adv_py.core.skin_loops import (
    SkinLoopBindLoop, SkinLoopBindSpec, SkinLoopCopySpec,
    SkinLoopCutUpDeletePlan, SkinLoopCutUpPlan, SkinLoopSpec,
)


_EDGE = re.compile(r"^(.*)\.e\[(\d+)\]$")


from adv_py.adapters.maya_skin_loops_source import MayaSkinLoopsSourceMixin


class MayaSkinLoopsHost(MayaSkinLoopsSourceMixin):
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

    def _mirrored_loop_members(self, mesh: str, members) -> tuple[int, ...]:
        """asCreateSamplerMesh + closestSampler.closestVertexIndex, not
        nearest vertex on an API-selected polygon."""
        c = self.cmds
        selection = c.ls(selection=True, long=True, flatten=True) or []
        sampler = self._name("samplerMesh")
        closest = self._name("closestSampler")
        try:
            for node in (closest, sampler):
                if c.objExists(node):
                    c.delete(node)
            sampler = c.duplicate(mesh, name=sampler)[0]
            shapes = c.listRelatives(sampler, shapes=True, noIntermediate=True,
                                     fullPath=True) or []
            c.rename(shapes[0], self._name("samplerMeshShape"))
            for channel in ("translate", "rotate", "scale"):
                for axis in "XYZ":
                    c.setAttr(sampler + "." + channel + axis,
                              lock=False, keyable=True)
                c.setAttr(sampler + "." + channel, lock=False, keyable=False)
            c.setAttr(sampler + ".v", lock=False, keyable=True)
            if c.listRelatives(sampler, parent=True):
                sampler = c.parent(sampler, world=True)[0]
            self._loop_remove_intermediates(sampler)
            c.makeIdentity(sampler, apply=True, translate=True, rotate=True,
                           scale=True)
            closest = c.createNode("closestPointOnMesh", name=closest)
            shape = c.listRelatives(sampler, shapes=True, noIntermediate=True,
                                    fullPath=True, type="mesh")[0]
            c.connectAttr(shape + ".outMesh", closest + ".inMesh", force=True)
            self._loop_select(members, replace=True)
            self._loop_command("ConvertSelectionToVertices")
            mirrored = []
            for vertex in self._loop_selection(flattened=True):
                c.select(vertex, replace=True)
                point = c.xform(vertex, query=True, worldSpace=True,
                                translation=True)
                c.setAttr(closest + ".inPosition", -point[0], point[1], point[2],
                          type="double3")
                index = int(c.getAttr(closest + ".closestVertexIndex"))
                mirrored.append(f"{mesh}.vtx[{index}]")
            self._loop_select(mirrored, replace=True)
            self._loop_command("ConvertSelectionToContainedEdges")
            edges = c.ls(selection=True, flatten=True, long=True) or []
            return tuple(int(_EDGE.fullmatch(edge).group(2)) for edge in edges)
        finally:
            for node in (closest, sampler):
                if c.objExists(node):
                    c.delete(node)
            self._loop_select(selection, replace=True)

    def _validate_original_loop_members(self, members, *, mirrored=False):
        """asCreateSkinLoop validates adjacency after native vertex conversion.

        Keep the authored edge/vertex/face selection for the set itself. A
        contained-edge conversion is used only for the typed topology record.
        """
        c = self.cmds
        self._loop_select(members, replace=True)
        self._loop_command("ConvertSelectionToVertices")
        vertices = self._loop_selection(flattened=True)
        vertex_set = set(vertices)
        for vertex in vertices:
            c.select(vertex, replace=True)
            self._loop_command("ConvertSelectionToEdges")
            self._loop_command("ConvertSelectionToVertices")
            c.select(vertex, deselect=True)
            neighbors = self._loop_selection(flattened=True)
            if sum(neighbor in vertex_set for neighbor in neighbors) != 2:
                c.select(vertex, replace=True)
                raise ValueError("镜像侧不是完整闭环" if mirrored else "所选组件不是完整闭环")
        return vertices

    def _capture_loop_rows(self, members):
        c = self.cmds
        self._loop_select(members, replace=True)
        self._loop_command("ConvertSelectionToVertices")
        self._loop_command("ConvertSelectionToContainedEdges")
        converted = c.ls(selection=True, flatten=True, long=True) or []
        mesh = self._mesh_transform(members[0])
        edge_ids = tuple(int(match.group(2)) for item in converted
                         if (match := _EDGE.fullmatch(item))
                         and self._mesh_transform(item) == mesh)
        return mesh, self._edge_rows(mesh, edge_ids)

    def capture_skin_loop_input(self, mirror: bool):
        c = self.cmds
        selected = c.ls(selection=True, long=True) or []
        if not selected:
            raise ValueError("没有选择任何对象")
        control = selected[-1]
        control_name = control.rsplit("|", 1)[-1]
        leaf = self._loop_leaf(control)
        if ((self.namespace and not control_name.startswith(self.namespace + ":"))
                or (not self.namespace and ":" in control_name)):
            raise ValueError("控制器不属于当前角色命名空间")
        deform_set = self._name("DeformSet")
        from .maya_original_control_identity import command_registration, fk_bindings
        bindings = fk_bindings(command_registration(c, self.namespace))
        registered = {fk:joint for joint,fk in bindings.items()}
        if c.objExists(deform_set) and c.sets(control, isMember=deform_set):
            joint_leaf = leaf
        elif leaf in registered:
            joint_leaf = registered[leaf]
        elif leaf.startswith("FK"):
            joint_leaf = leaf[2:]
        else:
            raise ValueError("最后选择项必须是 FK 控制器或变形关节")
        members = tuple(selected[:-1])
        if not members:
            raise ValueError("请先选择闭环组件，最后选择控制器")
        self._validate_original_loop_members(members)
        mesh, rows = self._capture_loop_rows(members)
        deform_joint = self._name(joint_leaf)
        if c.objExists(deform_joint):
            deform_joint = self._unique(deform_joint, "joint")
        opposite = None
        mirrored_members = ()
        try:
            if mirror and joint_leaf.endswith(("_R", "_L")):
                mirror_leaf = joint_leaf[:-1] + ("L" if joint_leaf.endswith("_R") else "R")
                if leaf in registered:
                    control_leaf = bindings.get(mirror_leaf, "FK" + mirror_leaf)
                else:
                    # Original substitute follows the deform joint's side,
                    # not the last character of a controller's physical name.
                    control_leaf = leaf.replace("_" + joint_leaf[-1],
                                                "_" + mirror_leaf[-1], 1)
                mirror_control = self._unique(self._name(control_leaf), c.nodeType(control))
                mirror_joint = self._name(mirror_leaf)
                if c.objExists(mirror_joint):
                    mirror_joint = self._unique(mirror_joint, "joint")
                # Original samples every converted vertex, including legal
                # disconnected rings. Keep the same first mesh sampler policy.
                mirrored_ids = self._mirrored_loop_members(mesh, members)
                mirrored_members = tuple(f"{mesh}.e[{index}]" for index in mirrored_ids)
                self._validate_original_loop_members(mirrored_members, mirrored=True)
                opposite = (mirror_control, mirror_joint, self._edge_rows(mesh, mirrored_ids))
        finally:
            self._loop_select(selected, replace=True)
        return (self._name("SkinLoops"), mesh, control, deform_joint, rows,
                opposite, members, mirrored_members)

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
        selected = c.ls(selection=True, long=True) or []
        try:
            self._validate_original_loop_members(
                spec.components or tuple(f"{spec.mesh}.e[{index}]" for index in spec.edge_ids))
        finally:
            self._loop_select(selected, replace=True)
        self._unique(spec.control, c.nodeType(spec.control))

    @contextmanager
    def transaction(self, label: str):
        c = self.cmds
        if self._in_transaction or not c.undoInfo(query=True, state=True):
            raise ValueError("SkinLoop 需要独立且开启 Undo 的 Maya 事务")
        self._in_transaction = True
        selection = c.ls(selection=True, long=True, flatten=True) or []
        previous_namespace = c.namespaceInfo(currentNamespace=True, absoluteName=True)
        if previous_namespace != ":":
            c.namespace(set=":")
        c.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
        except Exception:
            c.undoInfo(closeChunk=True)
            if c.undoInfo(query=True, undoName=True) == label:
                c.undo()
            raise
        else:
            c.undoInfo(closeChunk=True)
        finally:
            self._in_transaction = False
            if previous_namespace != ":":
                c.namespace(set=previous_namespace)
            c.select(selection, replace=True) if selection else c.select(clear=True)

    def create_skin_loop(self, spec: SkinLoopSpec) -> None:
        if not self._in_transaction:
            raise RuntimeError("SkinLoop 创建必须位于事务中")
        c = self.cmds
        if not c.objExists(spec.parent_set):
            c.sets(empty=True, name=spec.parent_set)
        if c.objExists(spec.set_name):
            c.delete(spec.set_name)
        members = spec.components or tuple(f"{spec.mesh}.e[{index}]" for index in spec.edge_ids)
        created = c.sets(members, name=spec.set_name)
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
        if spec.components:
            expected = c.ls(spec.components, flatten=True, long=True) or []
            return set(members) == set(expected)
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
        c.select(parent, replace=True)
        objects = c.ls(selection=True, objectsOnly=True) or []
        if objects:
            c.select(objects, add=True)
        return len(loops)

    def _skin(self, mesh: str, *, pruned: bool = False) -> str | None:
        flags = {"pruneDagObjects": True} if pruned else {}
        skins = [node for node in (self.cmds.listHistory(mesh, **flags) or [])
                 if self.cmds.nodeType(node) == "skinCluster"]
        return skins[-1] if skins else None

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
        selected = c.ls(selection=True, long=True, flatten=True) or []
        try:
            c.select(parent, replace=True)
            objects = c.ls(selection=True, objectsOnly=True) or []
            if not objects:
                raise ValueError("SkinLoops 集合缺少网格边")
            source_mesh = self._mesh_transform(objects[0])
        finally:
            self._loop_select(selected, replace=True)
        source_skin = self._skin(source_mesh, pruned=True)
        if not source_skin:
            raise ValueError("SkinLoop 来源网格尚未绑定 Skin")
        influences = tuple(self._unique(node, "joint")
                           for node in (c.listConnections(source_skin + ".matrix") or []))
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
                         self._skin(mesh, pruned=True))
                        for mesh, items in groups.items())
        return (source_mesh, source_skin, influences,
                int(c.getAttr(source_skin + ".skinningMethod")), targets)

    def preflight_skin_loop_copy(self, spec: SkinLoopCopySpec) -> None:
        c = self.cmds
        if self._mesh_transform(spec.source_mesh) != spec.source_mesh:
            raise ValueError("SkinLoop 来源网格已改变")
        if self._mesh_transform(spec.target_mesh) != spec.target_mesh:
            raise ValueError("SkinLoop 目标网格已改变")
        if self._skin(spec.source_mesh, pruned=True) != spec.source_skin:
            raise ValueError("SkinLoop 来源 Skin 已改变")
        source_influences = tuple(self._unique(node, "joint") for node in (
            c.listConnections(spec.source_skin + ".matrix") or []))
        if (set(source_influences) != set(spec.source_influences)
                or int(c.getAttr(spec.source_skin + ".skinningMethod"))
                != spec.skinning_method):
            raise ValueError("SkinLoop 来源蒙皮设置已改变")
        if self._skin(spec.target_mesh, pruned=True) != spec.target_skin:
            raise ValueError("SkinLoop 目标 Skin 已改变")
        if (spec.target_components and tuple(c.ls(
                spec.target_components, long=True, flatten=True) or ())
                != spec.target_components):
            raise ValueError("SkinLoop 目标组件已改变")
        if spec.target_skin and c.referenceQuery(spec.target_skin, isNodeReferenced=True):
            raise ValueError("Cannot add influences to a referenced skinCluster")

    def copy_skin_loop_weights(self, spec: SkinLoopCopySpec) -> None:
        if not self._in_transaction:
            raise RuntimeError("SkinLoop Copy 必须位于事务中")
        c = self.cmds
        skin = spec.target_skin
        if skin is None:
            c.select(list(spec.source_influences), replace=True)
            c.select(spec.target_mesh, add=True)
            from .maya_original_skin_history import new_original_skin_clusters
            skin = new_original_skin_clusters(commands=c, namespace=self.namespace)[0]
        else:
            current = {self._unique(node, "joint") for node in (
                c.listConnections(skin + ".matrix") or [])}
            for joint in spec.source_influences:
                if joint not in current:
                    c.skinCluster(skin, edit=True, addInfluence=joint,
                                  lockWeights=False, weight=0.0)
        c.select(spec.source_mesh, replace=True)
        c.select(spec.target_components or (spec.target_mesh,), add=True)
        c.copySkinWeights(noMirror=True, surfaceAssociation="closestPoint",
                          influenceAssociation="closestJoint")
        c.setAttr(skin + ".skinningMethod", spec.skinning_method)
        from .maya_original_skin_history import remove_unused_for_skin
        remove_unused_for_skin(c, skin)

    def capture_skin_loop_copy(self, spec: SkinLoopCopySpec) -> bool:
        c = self.cmds
        skin = self._skin(spec.target_mesh, pruned=True)
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
        """Bind uses Maya's member conversion, not an edge-only revalidation."""
        c = self.cmds
        selected = c.ls(selection=True, long=True) or []
        try:
            vertices = self._loop_vertices(loop_set, flattened=True)
            expanded = c.ls(vertices, long=True, flatten=True) or []
            return tuple(sorted({int(match.group(2)) for component in expanded
                if (match := re.fullmatch(r"(.*)\.vtx\[(\d+)\]", component))
                and self._mesh_transform(component) == mesh}))
        finally:
            self._loop_select(selected, replace=True)

    def capture_skin_loop_bind_input(self) -> tuple[SkinLoopBindSpec, ...]:
        c = self.cmds
        parent = self._name("SkinLoops")
        if not c.objExists(parent) or c.nodeType(parent) != "objectSet":
            raise ValueError("当前角色尚无 SkinLoops 集合")
        loop_sets = tuple(sorted(name for name in (
            c.sets(parent, query=True) or [])
            if c.nodeType(name) == "objectSet"))
        selected = c.ls(selection=True, long=True) or []
        if not selected or any("." in name for name in selected):
            raise ValueError("先选择待绑定的网格对象，不要选择网格组件")
        affected_meshes = set()
        for loop_set in loop_sets:
            members = c.sets(loop_set, query=True) or []
            if members:
                affected_meshes.add(self._mesh_transform(members[0]))
        specs = []
        for selected_mesh in selected:
            # The MEL procedure skips every object with no SkinLoop before
            # evaluating its mesh topology. Mixed object selections are legal.
            resolved = c.ls(selected_mesh, long=True) or []
            if not resolved or resolved[0] not in affected_meshes:
                c.warning('SkinLoops 未定义于 "' + selected_mesh + '"，跳过')
                continue
            mesh = self._mesh_transform(selected_mesh)
            root = self._unique(self._name("Root_M"), "joint")
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
                if self._mesh_transform(members[0]) != mesh:
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
        return tuple(specs)

    def preflight_skin_loop_bind(self, spec: SkinLoopBindSpec) -> None:
        c = self.cmds
        if self._skin(spec.mesh) != spec.existing_skin:
            raise ValueError("SkinLoop 目标 Skin 在执行前改变")
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

    def bind_skin_loops(self, spec: SkinLoopBindSpec) -> None:
        self.bind_skin_loop_batch((spec,))

    def capture_skin_loop_bind(self, spec: SkinLoopBindSpec) -> bool:
        c = self.cmds
        skin = self._skin(spec.mesh)
        if not skin or (spec.existing_skin and skin != spec.existing_skin):
            return False
        # Shared loop vertices are legal in MEL. The later loop's assignment
        # wins; requiring both loops' weights simultaneously is impossible.
        expected = {}
        for loop in spec.loops:
            for vertex in loop.vertices:
                expected[vertex] = ((loop.deform_joint, 1.0),)
        for loop in spec.loops:
            if loop.parent_joint and not fnmatchcase(loop.deform_joint, "*Part[0-9]_*"):
                for vertex in loop.vertices:
                    expected[vertex] = ((loop.deform_joint, .5), (loop.parent_joint, .5))
        influences = {self._unique(node, "joint") for node in (
            c.listConnections(skin + ".matrix") or [])}
        for vertex, weights in expected.items():
            component = f"{spec.mesh}.vtx[{vertex}]"
            for joint, weight in weights:
                if joint not in influences:
                    return False
                actual = float(c.skinPercent(skin, component, query=True,
                                              transform=joint))
                if abs(actual - weight) > 1e-4:
                    return False
        return not any(c.objExists(self._name(name)) for name in (
            "CutUpWIP", "SkinLoopWeighted"))

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
        # asDeleteCutUp returns immediately without the display layer. With
        # it present, delete its connected members before the layer itself.
        if not plan.layer or not c.objExists(plan.layer):
            return
        connected = c.listConnections(plan.layer + ".drawInfo") or []
        if connected:
            c.delete(connected)
        c.delete(plan.layer)
        if plan.geometry_group and c.objExists(plan.geometry_group):
            c.delete(plan.geometry_group)

    def capture_skin_loop_cut_up_deleted(
        self, plan: SkinLoopCutUpDeletePlan,
    ) -> bool:
        if not plan.layer:
            return True
        return all(not self.cmds.objExists(name)
                   for name in (plan.layer, plan.geometry_group) if name)

    def capture_skin_loop_cut_up_input(
        self,
    ) -> tuple[str, str, tuple[SkinLoopBindSpec, ...]]:
        return (self._name("CutUp"), self._name("CutUpGeometry"),
                self.capture_skin_loop_bind_input())

    def preflight_skin_loop_cut_up(self, plan: SkinLoopCutUpPlan) -> None:
        c = self.cmds
        self._unique(self._name("Geometry"), "transform")
        for name in (self._name("CutUpWIP"), self._name("SkinLoopWeighted")):
            if c.objExists(name):
                raise ValueError("SkinLoops 临时节点名称已被占用：" + name)
        for loop in c.sets(self._name("SkinLoops"), query=True) or []:
            if c.objExists(loop + "Temp") or c.objExists(loop + "CutUp"):
                raise ValueError("SkinLoops 临时集合名称已被占用：" + loop)
        for spec in plan.bindings:
            self.preflight_skin_loop_bind(spec)
            name = self._name(self._loop_leaf(spec.mesh) + "CutUp")
            if c.objExists(name):
                raise ValueError("SkinLoops 临时网格名称已被占用：" + name)

    def create_skin_loop_cut_up(self, plan: SkinLoopCutUpPlan) -> tuple[str, ...]:
        return self._run_original_skin_loops(plan.bindings, cut_up=True)

    def capture_skin_loop_cut_up(
        self, plan: SkinLoopCutUpPlan, pieces: tuple[str, ...],
    ) -> bool:
        # The source generates pieces from downstream seeds. It neither promises
        # a graph-partition count nor closes the extruded cap into a watertight
        # mesh; imposing either condition would roll back valid source output.
        c = self.cmds
        if (not c.objExists(plan.layer)
                or c.nodeType(plan.layer) != "displayLayer"
):
            return False
        group = self._unique(plan.geometry_group, "transform")
        members = {self._unique(node, "transform") for node in (
            c.editDisplayLayerMembers(plan.layer, query=True, fullNames=True) or [])
            if c.nodeType(node) == "transform"}
        for piece in pieces:
            if (not c.objExists(piece)
                    or (c.listRelatives(piece, parent=True, fullPath=True) or []) != [group]
                    or piece not in members
                    or not (c.listRelatives(piece, shapes=True, noIntermediate=True,
                                            type="mesh") or [])
                    or int(c.polyEvaluate(piece, face=True)) < 1):
                return False
        for spec in plan.bindings:
            for loop in spec.loops:
                if (not c.objExists(loop.set_name)
                        or self._bind_loop_vertices(loop.set_name, spec.mesh,
                                                    spec.edge_vertices) != loop.vertices):
                    return False
        return not any(c.objExists(self._name(name)) for name in (
            "CutUpWIP", "SkinLoopWeighted"))
