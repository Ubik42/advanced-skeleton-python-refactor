"""Maya edge-set operations for the original SkinLoops panel."""
from __future__ import annotations

from contextlib import contextmanager
import re

from adv_py.core.skin_loops import SkinLoopSpec


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
