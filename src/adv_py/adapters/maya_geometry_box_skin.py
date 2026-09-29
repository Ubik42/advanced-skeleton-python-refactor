"""Maya BoxSkin combine, bind and closest-vertex weight transfer."""
from __future__ import annotations

from adv_py.core.geometry_box_skin import BoxSkinPair
from .maya_geometry_poly_boxes import MayaPolyBoxesHost


class MayaBoxSkinHost(MayaPolyBoxesHost):
    def __init__(self, namespace: str = "") -> None:
        super().__init__(namespace)
        self._expected_weights: dict[int, str] = {}

    def box_skin_exists(self) -> bool:
        c = self.cmds
        return any(c.objExists(self._name(leaf)) for leaf in (
            "BoxSkin", "BoxSkinGeometry", "BoxSkinMesh",
            "BoxSkinMeshSkinCluster"))

    def preflight_box_skin(self, pairs: tuple[BoxSkinPair, ...]) -> None:
        c = self.cmds
        if not c.objExists(self._name("Geometry")):
            raise ValueError("BoxSkin 缺少 Geometry 组")
        deform = self._name("DeformSet")
        if not c.objExists(deform):
            raise ValueError("BoxSkin 缺少 DeformSet")
        influences = {self._leaf(node) for node in
                      c.sets(deform, query=True) or ()
                      if c.objExists(node) and c.nodeType(node) == "joint"}
        for pair in pairs:
            if (pair.joint not in influences
                    or not c.objExists(self._name(pair.joint))):
                raise ValueError("BoxSkin 缺少变形关节：" + pair.joint)
        if c.objExists(self._name("AdvPy_BoxSkinClosestSampler")):
            raise ValueError("BoxSkin 临时采样节点名称已占用")

    def create_box_skin(self, pairs: tuple[BoxSkinPair, ...]) -> int:
        c = self.cmds
        layer = c.createDisplayLayer(name=self._name("BoxSkin"), empty=True)
        c.setAttr(layer + ".color", 3)
        c.setAttr(layer + ".displayType", 2)
        group = c.createNode("transform", name=self._name("BoxSkinGeometry"),
                             parent=self._name("Geometry"))
        boxes_layer = self._name("PolyBoxes")
        if c.objExists(boxes_layer):
            c.setAttr(boxes_layer + ".visibility", 0)
        copies = []
        samples = []
        for index, pair in enumerate(pairs):
            source = self._name(pair.box)
            if not c.objExists(source):
                raise ValueError("BoxSkin 来源盒体已丢失：" + pair.box)
            world = c.xform(source, query=True, worldSpace=True, matrix=True)
            copy = c.duplicate(source, name=self._name(
                f"AdvPy_BoxSkinPiece{index}"), returnRootsOnly=True)[0]
            c.xform(copy, worldSpace=True, matrix=world)
            copy = c.parent(copy, group)[0]
            c.scale(0.95, 1, 1, copy, relative=True)
            copies.append(copy)
            for vertex in c.ls(copy + ".vtx[*]", flatten=True) or ():
                samples.append((pair.joint, tuple(c.xform(
                    vertex, query=True, worldSpace=True, translation=True))))
        mesh = c.polyUnite(*copies, constructionHistory=False,
                           mergeUVSets=False,
                           name=self._name("BoxSkinMesh"))[0]
        c.delete(copies)
        mesh = c.parent(mesh, group)[0]
        c.editDisplayLayerMembers(layer, mesh, noRecurse=True)
        deform = self._name("DeformSet")
        influences = tuple(sorted(self._name(self._leaf(node)) for node in
                           c.sets(deform, query=True) or ()
                           if c.objExists(node) and c.nodeType(node) == "joint"))
        skin = c.skinCluster(influences, mesh, toSelectedBones=True,
                             maximumInfluences=3, dropoffRate=4,
                             removeUnusedInfluence=False,
                             name=self._name("BoxSkinMeshSkinCluster"))[0]
        shape = (c.listRelatives(mesh, shapes=True,
                                 noIntermediate=True, type="mesh") or [])[0]
        sampler = c.createNode("closestPointOnMesh", name=self._name(
            "AdvPy_BoxSkinClosestSampler"))
        try:
            c.connectAttr(shape + ".worldMesh[0]", sampler + ".inMesh")
            expected = {}
            for joint, position in samples:
                c.setAttr(sampler + ".inPosition", *position,
                          type="double3")
                vertex = int(c.getAttr(sampler + ".closestVertexIndex"))
                c.skinPercent(skin, f"{mesh}.vtx[{vertex}]",
                              transformValue=(self._name(joint), 1.0),
                              normalize=True)
                expected[vertex] = joint
            self._expected_weights = expected
        finally:
            c.delete(sampler)
        return int(c.polyEvaluate(mesh, vertex=True))

    def capture_box_skin(self, pairs: tuple[BoxSkinPair, ...],
                         vertex_count: int) -> bool:
        c = self.cmds
        group = self._name("BoxSkinGeometry")
        mesh = self._name("BoxSkinMesh")
        skin = self._name("BoxSkinMeshSkinCluster")
        layer = self._name("BoxSkin")
        if (not all(c.objExists(node) for node in (group, mesh, skin, layer))
                or c.nodeType(skin) != "skinCluster"
                or (c.listRelatives(mesh, parent=True) or []) != [group]
                or int(c.polyEvaluate(mesh, vertex=True)) != vertex_count
                or c.getAttr(layer + ".color") != 3
                or c.getAttr(layer + ".displayType") != 2):
            return False
        influences = {self._leaf(node) for node in
                      c.skinCluster(skin, query=True, influence=True) or ()}
        if not {pair.joint for pair in pairs}.issubset(influences):
            return False
        for vertex, joint in self._expected_weights.items():
            weight = c.skinPercent(
                skin, f"{mesh}.vtx[{vertex}]", query=True,
                transform=self._name(joint))
            if abs(float(weight) - 1.0) > 1e-4:
                return False
        return bool(self._expected_weights)

    def delete_box_skin(self) -> None:
        c = self.cmds
        for leaf in ("BoxSkinGeometry", "BoxSkinMeshSkinCluster",
                     "BoxSkinMesh", "BoxSkin"):
            node = self._name(leaf)
            if c.objExists(node):
                c.delete(node)
