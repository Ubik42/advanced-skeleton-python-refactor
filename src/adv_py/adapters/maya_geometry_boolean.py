"""Maya implementation of the original selected-mesh / PolyBoxes Boolean."""
from __future__ import annotations

from adv_py.core.geometry_boolean import BooleanSpec
from .maya_geometry_poly_boxes import MayaPolyBoxesHost


class MayaBooleanHost(MayaPolyBoxesHost):
    def __init__(self, namespace: str = "") -> None:
        super().__init__(namespace)
        self._created_boolean: tuple[str, ...] = ()

    def capture_selected_meshes(self) -> tuple[str, ...]:
        c = self.cmds
        selected = c.ls(selection=True, long=True, objectsOnly=True) or ()
        meshes = []
        for node in selected:
            if c.nodeType(node) == "mesh":
                node = (c.listRelatives(node, parent=True,
                                        fullPath=True) or [node])[0]
            if not (c.nodeType(node) == "transform"
                    and c.listRelatives(node, shapes=True,
                                        noIntermediate=True, type="mesh")):
                raise ValueError("Boolean 仅接受所选多边形网格：" + node)
            meshes.append(node)
        return tuple(dict.fromkeys(meshes))

    def preflight_boolean(self, plan: tuple[BooleanSpec, ...]) -> None:
        c = self.cmds
        if not c.objExists(self._name("Geometry")):
            raise ValueError("Boolean 缺少 Geometry 组")
        if not c.objExists(self._name("BoxesGeometry")):
            raise ValueError("Boolean 需要先创建 PolyBoxes")
        for spec in plan:
            box = self._name(spec.box)
            joint = self._name(spec.joint)
            if (not c.objExists(spec.source)
                    or not c.objExists(box)
                    or not c.objExists(joint)
                    or not c.listRelatives(box, shapes=True,
                                           noIntermediate=True, type="mesh")):
                raise ValueError("Boolean 来源或关节已丢失：" + spec.name)
            if c.objExists(self._name(spec.name)):
                raise ValueError("Boolean 目标名称已占用：" + spec.name)
            if not c.getAttr(spec.source + ".visibility", settable=True):
                raise ValueError("Boolean 来源网格可见性不可写：" + spec.source)
        for leaf in ("AdvPy_BoolObjectTemp", "AdvPy_BoolBoxTemp"):
            if c.objExists(self._name(leaf)):
                raise ValueError("Boolean 临时名称已占用：" + leaf)
        boxes_layer = self._name("PolyBoxes")
        if (c.objExists(boxes_layer)
                and not c.getAttr(boxes_layer + ".visibility", settable=True)):
            raise ValueError("PolyBoxes 显示层可见性不可写")

    def boolean_exists(self) -> bool:
        c = self.cmds
        return (c.objExists(self._name("Bool"))
                or c.objExists(self._name("BoolGeometry")))

    def create_boolean(self, plan: tuple[BooleanSpec, ...]) -> int:
        c = self.cmds
        layer = self._name("Bool")
        if not c.objExists(layer):
            layer = c.createDisplayLayer(name=layer, empty=True)
            c.setAttr(layer + ".color", 21)
            c.setAttr(layer + ".displayType", 2)
        group = self._name("BoolGeometry")
        if not c.objExists(group):
            group = c.createNode("transform", name=group,
                                 parent=self._name("Geometry"))
        visibility = {}
        for source in {spec.source for spec in plan}:
            visibility[source] = bool(c.getAttr(source + ".visibility"))
        boxes_layer = self._name("PolyBoxes")
        if c.objExists(boxes_layer):
            visibility[boxes_layer] = bool(c.getAttr(
                boxes_layer + ".visibility"))
        created = []
        try:
            for node in visibility:
                c.setAttr(node + ".visibility", 0)
            for spec in plan:
                obj = c.duplicate(spec.source, name=self._name(
                    "AdvPy_BoolObjectTemp"), returnRootsOnly=True)[0]
                box = c.duplicate(self._name(spec.box), name=self._name(
                    "AdvPy_BoolBoxTemp"), returnRootsOnly=True)[0]
                try:
                    for copy, source in ((obj, spec.source),
                                         (box, self._name(spec.box))):
                        matrix = c.xform(source, query=True,
                                         worldSpace=True, matrix=True)
                        if c.listRelatives(copy, parent=True):
                            c.parent(copy, world=True)
                        c.xform(copy, worldSpace=True, matrix=matrix)
                        c.setAttr(copy + ".visibility", 1)
                    result = c.polyBoolOp(
                        obj, box, operation=3, constructionHistory=False)[0]
                finally:
                    for copy in (obj, box):
                        if c.objExists(copy):
                            c.delete(copy)
                if (not c.objExists(result)
                        or int(c.polyEvaluate(result, vertex=True)) == 0):
                    if c.objExists(result):
                        c.delete(result)
                    continue
                result = c.rename(result, self._name(spec.name))
                result = c.parent(result, group)[0]
                joint = self._name(spec.joint)
                c.parentConstraint(joint, result, maintainOffset=True)
                c.scaleConstraint(joint, result, maintainOffset=True)
                c.editDisplayLayerMembers(layer, result, noRecurse=True)
                created.append(result)
        finally:
            for node, value in visibility.items():
                if c.objExists(node):
                    c.setAttr(node + ".visibility", value)
        self._created_boolean = tuple(created)
        return len(created)

    def capture_boolean(self, count: int) -> bool:
        c = self.cmds
        group = self._name("BoolGeometry")
        layer = self._name("Bool")
        if (not c.objExists(group) or not c.objExists(layer)
                or c.getAttr(layer + ".color") != 21
                or c.getAttr(layer + ".displayType") != 2
                or len(self._created_boolean) != count):
            return False
        for mesh in self._created_boolean:
            if (not c.objExists(mesh)
                    or not c.listRelatives(mesh, shapes=True,
                                           noIntermediate=True, type="mesh")
                    or (c.listRelatives(mesh, parent=True) or []) != [group]
                    or not c.listConnections(mesh + ".translateX",
                                             source=True,
                                             type="parentConstraint")
                    or not c.listConnections(mesh + ".scaleX",
                                             source=True,
                                             type="scaleConstraint")):
                return False
        return True

    def delete_boolean(self) -> None:
        c = self.cmds
        for leaf in ("BoolGeometry", "Bool"):
            node = self._name(leaf)
            if c.objExists(node):
                c.delete(node)
