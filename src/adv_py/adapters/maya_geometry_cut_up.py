"""Maya realization of Geometry / Skin Cut-Up from face skin weights."""
from __future__ import annotations

from adv_py.core.geometry_cut_up import CutUpMeshPlan
from .maya_skin_cage import MayaSkinCageHost


class MayaGeometryCutUpHost(MayaSkinCageHost):
    def __init__(self, namespace: str = "") -> None:
        super().__init__(namespace)
        self._created: list[tuple[str, str]] = []

    def _leaf(self, node: str) -> str:
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _anchor(self, joint: str) -> str:
        c = self.cmds
        current = joint
        visited = set()
        while current and current not in visited:
            visited.add(current)
            leaf = self._leaf(current)
            if "Slider" not in leaf:
                if c.objExists(self._name("FK" + leaf)) or "Part" in leaf:
                    return current
            current = (c.listRelatives(current, parent=True, type="joint",
                                       fullPath=True) or [""])[0]
        raise ValueError("Skin Cut-Up 找不到关节控制来源：" + joint)

    def capture_cut_up_inputs(self) -> tuple[tuple, ...]:
        from maya.api import OpenMaya as om

        c = self.cmds
        selection = c.ls(selection=True, long=True) or []
        if not selection:
            raise ValueError("请选择已蒙皮的网格对象")
        meshes = tuple(dict.fromkeys(self._mesh(node) for node in selection))
        rows = []
        for mesh in meshes:
            skin = self._skin(mesh)
            if not skin:
                raise ValueError("Skin Cut-Up 网格没有 SkinCluster：" + mesh)
            influences = tuple(c.skinCluster(skin, query=True,
                                              influence=True) or ())
            if not influences:
                raise ValueError("Skin Cut-Up SkinCluster 没有影响关节")
            selection_list = om.MSelectionList()
            selection_list.add(mesh)
            mesh_path = selection_list.getDagPath(0)
            mesh_path.extendToShape()
            mesh_fn = om.MFnMesh(mesh_path)
            faces = tuple(tuple(mesh_fn.getPolygonVertices(index))
                          for index in range(mesh_fn.numPolygons))
            weights = []
            for index in range(mesh_fn.numVertices):
                values = c.skinPercent(
                    skin, mesh + f".vtx[{index}]", query=True,
                    value=True) or []
                if len(values) != len(influences):
                    raise RuntimeError("Skin Cut-Up 顶点影响权重数量不一致："
                                       + mesh)
                weights.append(tuple(float(value) for value in values))
            anchors = tuple(self._anchor(joint) for joint in influences)
            rows.append((mesh, influences, faces, tuple(weights), anchors))
        return tuple(rows)

    def preflight_cut_up(self, plans: tuple[CutUpMeshPlan, ...]) -> None:
        c = self.cmds
        if not plans:
            raise ValueError("没有可创建的 Skin Cut-Up 分片")
        if not c.objExists(self._name("Geometry")):
            raise ValueError("当前角色缺少 Geometry 系统")
        for leaf in ("CutUpGeometry", "CutUp"):
            if c.objExists(self._name(leaf)):
                raise ValueError("当前角色已有 CutUp 生成物；请先删除旧分片")

    def _setup(self) -> tuple[str, str]:
        c = self.cmds
        layer = c.createDisplayLayer(empty=True, name=self._name("CutUp"))
        c.setAttr(layer + ".color", 29)
        c.setAttr(layer + ".displayType", 2)
        geometry = c.createNode("transform", name=self._name(
            "CutUpGeometry"), parent=self._name("Geometry"),
            skipSelect=True)
        c.editDisplayLayerMembers(layer, geometry, noRecurse=True)
        return geometry, layer

    def _group(self, geometry: str, joint: str) -> str:
        c = self.cmds
        leaf = self._leaf(joint)
        stem, separator, side = leaf.rpartition("_")
        if not separator:
            raise ValueError("Skin Cut-Up 关节缺少左右侧后缀：" + leaf)
        group = self._name(stem + "CutUp_" + side)
        if c.objExists(group):
            return group
        group = c.createNode("transform", name=group, parent=geometry,
                             skipSelect=True)
        c.xform(group, worldSpace=True, matrix=c.xform(
            joint, query=True, worldSpace=True, matrix=True))
        c.parentConstraint(joint, group, maintainOffset=True)
        return group

    def _piece_name(self, joint: str) -> str:
        leaf = self._leaf(joint)
        stem, _, side = leaf.rpartition("_")
        for index in range(1, 1000):
            name = self._name(f"{stem}CutUp{index}_{side}")
            if not self.cmds.objExists(name):
                return name
        raise ValueError("Skin Cut-Up 分片名称已用尽：" + leaf)

    def create_cut_up(self, plan: CutUpMeshPlan) -> int:
        c = self.cmds
        if not c.objExists(self._name("CutUpGeometry")):
            geometry, _ = self._setup()
        else:
            geometry = self._name("CutUpGeometry")
        all_faces = set(range(plan.face_count))
        for spec in plan.pieces:
            group = self._group(geometry, spec.joint)
            piece = c.duplicate(plan.mesh, returnRootsOnly=True,
                                name=self._piece_name(spec.joint))[0]
            remove = sorted(all_faces.difference(spec.faces))
            if remove:
                c.delete([piece + f".f[{index}]" for index in remove])
            c.delete(piece, constructionHistory=True)
            piece = c.parent(piece, group)[0]
            shapes = c.listRelatives(piece, shapes=True,
                                     noIntermediate=True, type="mesh") or []
            if len(shapes) != 1:
                raise RuntimeError("Skin Cut-Up 分片网格丢失：" + piece)
            self._created.append((piece, group))
        return len(plan.pieces)

    def capture_cut_up(self, plans: tuple[CutUpMeshPlan, ...]) -> bool:
        c = self.cmds
        expected = sum(len(plan.pieces) for plan in plans)
        if len(self._created) != expected:
            return False
        for piece, group in self._created:
            if not c.objExists(piece) or not c.objExists(group):
                return False
            parent = c.listRelatives(piece, parent=True, fullPath=True) or []
            if not parent or self._leaf(parent[0]) != self._leaf(group):
                return False
            if not c.listRelatives(piece, shapes=True, type="mesh",
                                   noIntermediate=True):
                return False
            if not c.listConnections(group, type="parentConstraint"):
                return False
        return self.cut_up_exists()

    def cut_up_exists(self) -> bool:
        c = self.cmds
        return (c.objExists(self._name("CutUpGeometry"))
                or c.objExists(self._name("CutUp")))

    def delete_cut_up(self) -> None:
        c = self.cmds
        for leaf in ("CutUpGeometry", "CutUp"):
            if c.objExists(self._name(leaf)):
                c.delete(self._name(leaf))
