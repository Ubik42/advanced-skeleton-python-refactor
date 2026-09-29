"""Fit-derived PolyBoxes in the original Body / Geometry hierarchy."""
from __future__ import annotations

from math import dist, sqrt

from adv_py.core.geometry_poly_boxes import PolyBoxSource, PolyBoxSpec
from .maya_skin_cage import MayaSkinCageHost


def _unit(vector):
    length = sqrt(sum(value * value for value in vector))
    if length < 1e-8:
        raise ValueError("PolyBoxes 骨段方向长度为零")
    return tuple(value / length for value in vector)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


class MayaPolyBoxesHost(MayaSkinCageHost):
    @staticmethod
    def _leaf(node: str) -> str:
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    @staticmethod
    def _holder_name(box_name: str) -> str:
        return box_name[:-2] + "ParentConstraint" + box_name[-2:]

    def _fit_child(self, joint: str) -> str:
        c = self.cmds
        children = c.listRelatives(joint, children=True,
                                   type="joint", fullPath=True) or []
        if not children:
            return ""
        stem = self._leaf(joint)
        preferred = ("Spine" if "Root" in stem else
                     "Toes" if "Ankle" in stem else
                     "Head" if "Head" in stem else "")
        if preferred:
            for child in children:
                if preferred in self._leaf(child):
                    return child
        return children[0]

    def _fit_size(self, joint: str) -> tuple[float, float]:
        c = self.cmds
        values = []
        for attribute in ("fatFrontAbs", "fatWidthAbs"):
            if not c.attributeQuery(attribute, node=joint, exists=True):
                raise ValueError("Fit 关节缺少体积属性：" + self._leaf(joint))
            values.append(float(c.getAttr(joint + "." + attribute)))
        return 1.75 * values[0], 1.75 * values[1]

    def capture_sources(self) -> tuple[PolyBoxSource, ...]:
        c = self.cmds
        fit = self._name("FitSkeleton")
        deform = self._name("DeformSet")
        if not c.objExists(fit) or not c.objExists(deform):
            raise ValueError("PolyBoxes 需要已构建的 FitSkeleton 和 DeformSet")
        members = {self._leaf(node) for node in c.sets(deform, query=True) or []
                   if c.objExists(node) and c.nodeType(node) == "joint"}
        sources = []
        seen = set()
        for joint in c.listRelatives(fit, allDescendents=True,
                                     type="joint", fullPath=True) or []:
            stem = self._leaf(joint)
            if stem.endswith("_L"):
                continue
            stem = stem.removesuffix("_R").removesuffix("_M")
            if stem in seen:
                continue
            seen.add(stem)
            if any(term in stem for term in ("Eye", "Jaw")):
                continue
            child = self._fit_child(joint)
            if not child:
                continue
            child_stem = self._leaf(child).removesuffix("_R").removesuffix("_M")
            if child_stem == stem:
                continue
            source_pos = tuple(c.xform(joint, query=True,
                                      worldSpace=True, translation=True))
            child_pos = tuple(c.xform(child, query=True,
                                     worldSpace=True, translation=True))
            length = dist(source_pos, child_pos)
            if length < 1e-5:
                continue
            start_front, start_width = self._fit_size(joint)
            end_front, end_width = self._fit_size(child)
            parts = 1
            for attribute in ("twistJoints", "inbetweenJoints"):
                if c.attributeQuery(attribute, node=joint, exists=True):
                    parts += max(0, int(c.getAttr(joint + "." + attribute)))
            for side in ("_M", "_R", "_L"):
                start_name = stem + side
                end_name = child_stem + side
                if start_name not in members:
                    continue
                start_joint = self._name(start_name)
                end_joint = self._name(end_name)
                start = tuple(c.xform(start_joint, query=True,
                                      worldSpace=True, translation=True))
                end = (tuple(c.xform(end_joint, query=True,
                                     worldSpace=True, translation=True))
                       if c.objExists(end_joint) else
                       tuple(start[axis] + child_pos[axis] - source_pos[axis]
                             for axis in range(3)))
                sources.append(PolyBoxSource(
                    stem, side, start_name, end_name, start, end,
                    start_front, start_width, end_front, end_width, parts))
        return tuple(sources)

    def preflight_create(self, plan: tuple[PolyBoxSpec, ...]) -> None:
        c = self.cmds
        for leaf in ("Geometry", "MainScaleMultiplyDivide"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("PolyBoxes 缺少角色节点：" + leaf)
        if self.exists():
            raise ValueError("PolyBoxes 已存在；请先删除旧盒体")
        for spec in plan:
            for leaf in (spec.name, self._holder_name(spec.name)):
                if c.objExists(self._name(leaf)):
                    raise ValueError("PolyBoxes 名称已占用：" + leaf)
            if not c.objExists(self._name(spec.driver)):
                raise ValueError("PolyBoxes 缺少 Body 驱动关节：" + spec.driver)

    def _box_matrix(self, spec: PolyBoxSpec):
        c = self.cmds
        x_axis = _unit(tuple(spec.end[axis] - spec.start[axis]
                             for axis in range(3)))
        driver_matrix = c.xform(self._name(spec.driver), query=True,
                                worldSpace=True, matrix=True)
        up = tuple(driver_matrix[4:7])
        if abs(sum(x_axis[i] * up[i] for i in range(3))) > 0.98:
            up = (0, 1, 0) if abs(x_axis[1]) < 0.98 else (0, 0, 1)
        z_axis = _unit(_cross(x_axis, up))
        y_axis = _unit(_cross(z_axis, x_axis))
        return (*x_axis, 0, *y_axis, 0, *z_axis, 0, *spec.start, 1)

    def _create_box(self, spec: PolyBoxSpec, parent: str) -> None:
        c = self.cmds
        holder = c.createNode("transform", name=self._name(
            self._holder_name(spec.name)), parent=parent)
        c.xform(holder, worldSpace=True, matrix=self._box_matrix(spec))
        box = c.polyCube(name=self._name(spec.name), width=1,
                         height=1, depth=1, constructionHistory=False)[0]
        c.parent(box, holder, relative=True)
        length = dist(spec.start, spec.end)
        for index in range(8):
            vertex = f"{box}.vtx[{index}]"
            old = c.xform(vertex, query=True, objectSpace=True,
                          translation=True)
            end = old[0] > 0
            front = spec.front_end if end else spec.front_start
            width = spec.width_end if end else spec.width_start
            c.xform(vertex, objectSpace=True,
                    translation=(length if end else 0,
                                 (0.875 if old[1] > 0 else -0.875) * front,
                                 (0.875 if old[2] > 0 else -0.875) * width))
        c.parentConstraint(self._name(spec.driver), holder,
                           maintainOffset=True)

    def create(self, plan: tuple[PolyBoxSpec, ...]) -> None:
        c = self.cmds
        parent = c.createNode("transform", name=self._name("BoxesGeometry"),
                              parent=self._name("Geometry"))
        c.connectAttr(self._name("MainScaleMultiplyDivide") + ".output",
                      parent + ".scale", force=True)
        layer = c.createDisplayLayer(name=self._name("PolyBoxes"),
                                     empty=True)
        c.setAttr(layer + ".color", 14)
        for spec in plan:
            self._create_box(spec, parent)
        c.editDisplayLayerMembers(layer, parent, noRecurse=False)
        c.sets(parent, edit=True, forceElement="initialShadingGroup")

    def capture_created(self, plan: tuple[PolyBoxSpec, ...]) -> bool:
        c = self.cmds
        group = self._name("BoxesGeometry")
        layer = self._name("PolyBoxes")
        if not c.objExists(group) or not c.objExists(layer):
            return False
        source = c.connectionInfo(group + ".scaleX",
                                  sourceFromDestination=True)
        if source != self._name("MainScaleMultiplyDivide") + ".outputX":
            return False
        for spec in plan:
            box = self._name(spec.name)
            holder = self._name(self._holder_name(spec.name))
            if (not c.objExists(box)
                    or not c.listRelatives(box, shapes=True,
                                           noIntermediate=True, type="mesh")
                    or not c.objExists(holder)
                    or holder not in (c.listRelatives(box, parent=True) or [])):
                return False
        return True

    def exists(self) -> bool:
        c = self.cmds
        return (c.objExists(self._name("BoxesGeometry"))
                or c.objExists(self._name("PolyBoxes")))

    def delete(self) -> None:
        c = self.cmds
        for leaf in ("BoxesGeometry", "PolyBoxes"):
            if c.objExists(self._name(leaf)):
                c.delete(self._name(leaf))

    def box_names(self) -> tuple[str, ...]:
        return tuple(name for name in self.all_box_names()
                     if name.endswith(("Box_L", "Box_R")))

    def all_box_names(self) -> tuple[str, ...]:
        c = self.cmds
        group = self._name("BoxesGeometry")
        if not c.objExists(group):
            raise ValueError("请先创建 PolyBoxes")
        return tuple(sorted(self._leaf(node)
                            for node in c.listRelatives(
                                group, allDescendents=True,
                                type="transform", fullPath=True) or []
                            if self._leaf(node).endswith((
                                "Box_M", "Box_L", "Box_R"))
                            and c.listRelatives(node, shapes=True,
                                                type="mesh")))

    def mirror(self, pairs: tuple[tuple[str, str], ...]) -> int:
        c = self.cmds
        for source_name, target_name in pairs:
            source = self._name(source_name)
            target = self._name(target_name)
            source_vertices = c.ls(source + ".vtx[*]", flatten=True) or []
            target_vertices = c.ls(target + ".vtx[*]", flatten=True) or []
            if len(source_vertices) != len(target_vertices):
                raise ValueError("PolyBoxes 镜像两侧顶点数量不同：" + source_name)
            expected = []
            for index, vertex in enumerate(source_vertices):
                position = c.xform(vertex, query=True,
                                   worldSpace=True, translation=True)
                mirrored = (-position[0], position[1], position[2])
                c.xform(target_vertices[index], worldSpace=True,
                        translation=mirrored)
                expected.append(mirrored)
            for index, position in enumerate(expected):
                actual = c.xform(target_vertices[index], query=True,
                                 worldSpace=True, translation=True)
                if dist(actual, position) > 1e-4:
                    raise RuntimeError("PolyBoxes 镜像写后读回不一致：" + target_name)
        return len(pairs)
