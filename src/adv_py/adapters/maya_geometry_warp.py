"""Maya surface projection of selected geometry onto driven PolyBoxes."""
from __future__ import annotations

from adv_py.core.geometry_warp import WarpSpec
from .maya_geometry_boolean import MayaBooleanHost


class MayaWarpHost(MayaBooleanHost):
    def __init__(self, namespace: str = "") -> None:
        super().__init__(namespace)
        self._created_warps: tuple[str, ...] = ()

    def capture_warp_names(self) -> frozenset[str]:
        c = self.cmds
        group = self._name("WarpGeometry")
        if not c.objExists(group):
            return frozenset()
        return frozenset(self._leaf(node) for node in
            c.listRelatives(group, children=True, type="transform") or ())

    def warp_exists(self) -> bool:
        c = self.cmds
        return (c.objExists(self._name("Warp"))
                or c.objExists(self._name("WarpGeometry")))

    def preflight_warp(self, plan: tuple[WarpSpec, ...]) -> None:
        c = self.cmds
        if not c.objExists(self._name("Geometry")):
            raise ValueError("Warp 缺少 Geometry 组")
        if not c.objExists(self._name("BoxesGeometry")):
            raise ValueError("Warp 需要先创建 PolyBoxes")
        for spec in plan:
            if any(not c.objExists(node) for node in (
                    spec.source, self._name(spec.box),
                    self._name(spec.joint))):
                raise ValueError("Warp 来源或关节已丢失：" + spec.name)
            if c.objExists(self._name(spec.name)):
                raise ValueError("Warp 名称已占用：" + spec.name)
            if not c.getAttr(spec.source + ".visibility", settable=True):
                raise ValueError("Warp 来源网格可见性不可写：" + spec.source)
        for leaf in ("AdvPy_WarpClosestSampler", "AdvPy_WarpPieceTemp"):
            if c.objExists(self._name(leaf)):
                raise ValueError("Warp 临时名称已占用：" + leaf)
        boxes_layer = self._name("PolyBoxes")
        if (c.objExists(boxes_layer)
                and not c.getAttr(boxes_layer + ".visibility", settable=True)):
            raise ValueError("PolyBoxes 显示层可见性不可写")

    def _material_for_face(self, source: str, face: int,
                           shading_groups: tuple[str, ...]) -> str:
        c = self.cmds
        for group in shading_groups:
            if c.sets(f"{source}.f[{face}]", isMember=group):
                return group
        return shading_groups[0]

    def _project_warp(self, spec: WarpSpec, group: str,
                      layer: str, sampler: str,
                      shaders: tuple[str, ...]) -> str | None:
        c = self.cmds
        source_box = self._name(spec.box)
        world = c.xform(source_box, query=True, worldSpace=True, matrix=True)
        warp = c.duplicate(source_box, name=self._name(
            "AdvPy_WarpPieceTemp"), returnRootsOnly=True)[0]
        warp = c.parent(warp, group)[0]
        c.xform(warp, worldSpace=True, matrix=world)
        for axis in "tr":
            for channel in "xyz":
                plug = warp + "." + axis + channel
                if c.getAttr(plug, lock=True):
                    c.setAttr(plug, lock=False)
        c.polySmooth(warp, method=0, divisions=spec.divisions,
                     constructionHistory=True)
        c.scale(1, 0.7, 0.7, warp + ".e[0:15]",
                relative=True, objectCenterPivot=True)
        c.scale(1, 0.9, 0.9,
                warp + ".vtx[34:50]", warp + ".vtx[52]",
                warp + ".vtx[54]", warp + ".vtx[56]",
                warp + ".vtx[58]", warp + ".vtx[60]",
                warp + ".vtx[62]", warp + ".vtx[64]",
                warp + ".vtx[74:89]", relative=True,
                objectCenterPivot=True)
        c.transferAttributes(spec.source, warp, transferPositions=1,
                             transferNormals=0, transferUVs=2,
                             transferColors=2, sampleSpace=0,
                             sourceUvSpace="map1", targetUvSpace="map1",
                             searchMethod=3, flipUVs=False,
                             colorBorders=True)
        c.delete(warp, constructionHistory=True)
        if float(c.polyEvaluate(warp, area=True)) < 1.0:
            c.delete(warp)
            return None
        warp = c.rename(warp, self._name(spec.name))
        if len(shaders) == 1:
            c.sets(warp, edit=True, forceElement=shaders[0])
        elif shaders:
            count = int(c.polyEvaluate(warp, face=True))
            for index in range(count):
                positions = c.xform(f"{warp}.f[{index}]", query=True,
                                    worldSpace=True, translation=True)
                center = tuple(sum(positions[axis::3]) /
                               (len(positions) // 3) for axis in range(3))
                c.setAttr(sampler + ".inPosition", *center,
                          type="double3")
                face = int(c.getAttr(sampler + ".closestFaceIndex"))
                material = self._material_for_face(spec.source, face, shaders)
                c.sets(f"{warp}.f[{index}]", edit=True,
                       forceElement=material)
        joint = self._name(spec.joint)
        c.parentConstraint(joint, warp, maintainOffset=True)
        c.scaleConstraint(joint, warp, maintainOffset=True)
        c.editDisplayLayerMembers(layer, warp, noRecurse=True)
        return warp

    def create_warp(self, plan: tuple[WarpSpec, ...]) -> int:
        c = self.cmds
        layer = self._name("Warp")
        if not c.objExists(layer):
            layer = c.createDisplayLayer(name=layer, empty=True)
            c.setAttr(layer + ".color", 28)
            c.setAttr(layer + ".displayType", 2)
        group = self._name("WarpGeometry")
        if not c.objExists(group):
            group = c.createNode("transform", name=group,
                                 parent=self._name("Geometry"))
        visibility = {source: bool(c.getAttr(source + ".visibility"))
                      for source in {spec.source for spec in plan}}
        boxes_layer = self._name("PolyBoxes")
        if c.objExists(boxes_layer):
            visibility[boxes_layer] = bool(c.getAttr(
                boxes_layer + ".visibility"))
        created = []
        try:
            for node in visibility:
                c.setAttr(node + ".visibility", 0)
            for source in dict.fromkeys(spec.source for spec in plan):
                shape = (c.listRelatives(source, shapes=True,
                                         noIntermediate=True,
                                         type="mesh") or [])[0]
                shaders = tuple(dict.fromkeys(c.listConnections(
                    shape, type="shadingEngine") or ()))
                sampler = c.createNode("closestPointOnMesh", name=self._name(
                    "AdvPy_WarpClosestSampler"))
                try:
                    c.connectAttr(shape + ".worldMesh[0]",
                                  sampler + ".inMesh")
                    for spec in (item for item in plan
                                 if item.source == source):
                        warp = self._project_warp(spec, group, layer,
                                                  sampler, shaders)
                        if warp is not None:
                            created.append(warp)
                finally:
                    c.delete(sampler)
        finally:
            for node, value in visibility.items():
                if c.objExists(node):
                    c.setAttr(node + ".visibility", value)
        self._created_warps = tuple(created)
        return len(created)

    def capture_warp(self, count: int) -> bool:
        c = self.cmds
        group, layer = self._name("WarpGeometry"), self._name("Warp")
        if (not c.objExists(group) or not c.objExists(layer)
                or c.getAttr(layer + ".color") != 28
                or c.getAttr(layer + ".displayType") != 2
                or len(self._created_warps) != count):
            return False
        for warp in self._created_warps:
            if (not c.objExists(warp)
                    or (c.listRelatives(warp, parent=True) or []) != [group]
                    or not c.listRelatives(warp, shapes=True,
                                           noIntermediate=True, type="mesh")
                    or not c.listConnections(warp + ".translateX",
                                             source=True,
                                             type="parentConstraint")
                    or not c.listConnections(warp + ".scaleX",
                                             source=True,
                                             type="scaleConstraint")):
                return False
        return True

    def delete_warp(self) -> None:
        c = self.cmds
        for leaf in ("WarpGeometry", "Warp"):
            node = self._name(leaf)
            if c.objExists(node):
                c.delete(node)
