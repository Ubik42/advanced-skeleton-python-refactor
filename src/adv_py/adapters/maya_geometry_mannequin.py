"""Duplicate and bind original ADV Mannequin templates onto Body joints."""
from __future__ import annotations

from math import sqrt
from uuid import uuid4

from adv_py.core.geometry_mannequin import MannequinPiece, MannequinSegment
from .maya_geometry_skeleton import MayaSkeletonGeometryHost, geometry_asset


def _unit(vector):
    magnitude = sqrt(sum(value * value for value in vector))
    if magnitude < 1e-8:
        raise ValueError("Mannequin 足部方向长度为零")
    return tuple(value / magnitude for value in vector)


class MayaMannequinHost(MayaSkeletonGeometryHost):
    def __init__(self, namespace: str = "") -> None:
        super().__init__(namespace)
        self._mannequin_created: list[tuple[str, str]] = []

    def _fit_heel(self, joint: str) -> tuple[float, float, float] | None:
        c = self.cmds
        stem = self._leaf(joint)[:-2]
        if not stem.startswith("Ankle"):
            return None
        fit_joint = self._name(stem)
        if not c.objExists(fit_joint):
            return None
        children = c.listRelatives(fit_joint, children=True,
                                   type="joint", fullPath=True) or []
        for child in children:
            label = (str(c.getAttr(child + ".otherType") or "")
                     if c.getAttr(child + ".drawLabel")
                     and int(c.getAttr(child + ".type")) == 18 else "")
            if "Heel" not in label and "Heel" not in self._leaf(child):
                continue
            position = tuple(float(value) for value in c.xform(
                child, query=True, worldSpace=True, translation=True))
            side_factor = -1 if self._leaf(joint).endswith("_L") else 1
            return (position[0] * side_factor, position[1], position[2])
        return None

    def _rla_child(self, joint: str, center_tolerance: float) -> str:
        c = self.cmds
        children = c.listRelatives(joint, children=True,
                                   type="joint", fullPath=True) or []
        if not children:
            return ""
        stem = self._leaf(joint)
        if stem.startswith("Wrist"):
            for child in children:
                if self._leaf(child).startswith("MiddleFinger1"):
                    return child
        preferred = ("Spine" if stem.startswith("Root") else
                     "Toes" if stem.startswith(("Ankle", "Toes")) else
                     "Head" if stem.startswith("Head") else "")
        if preferred:
            for child in children:
                if preferred in self._leaf(child):
                    return child
        center = abs(float(c.xform(joint, query=True,
                                   worldSpace=True, translation=True)[0]))
        for child in children:
            child_x = float(c.xform(child, query=True,
                                    worldSpace=True, translation=True)[0])
            if (center < center_tolerance) == (abs(child_x) < center_tolerance):
                return child
        return ""

    def capture_mannequin_input(
        self,
    ) -> tuple[tuple[MannequinSegment, ...], float]:
        c = self.cmds
        deform = self._name("DeformSet")
        if not c.objExists(deform):
            raise ValueError("Mannequin 需要当前角色 DeformSet")
        joints = sorted({self._name(self._leaf(node)) for node in
                        c.sets(deform, query=True) or ()
                        if c.objExists(node) and c.nodeType(node) == "joint"})
        if not joints:
            raise ValueError("DeformSet 没有 Body 关节")
        fit = self._name("FitSkeleton")
        scale = (float(c.getAttr(fit + ".scaleX"))
                 if c.objExists(fit) else 1.0)
        tolerance = abs(scale) * 0.01
        segments = []
        all_y = []
        for joint in joints:
            position = tuple(float(value) for value in c.xform(
                joint, query=True, worldSpace=True, translation=True))
            all_y.append(position[1])
            if "Part" in self._leaf(joint):
                continue
            child = self._rla_child(joint, tolerance)
            while child and "Part" in self._leaf(child):
                descendants = c.listRelatives(child, children=True,
                                               type="joint", fullPath=True) or []
                child = descendants[0] if len(descendants) == 1 else ""
            if not child:
                continue
            end = tuple(float(value) for value in c.xform(
                child, query=True, worldSpace=True, translation=True))
            segments.append(MannequinSegment(self._leaf(joint),
                self._leaf(child), position, end, self._fit_heel(joint)))
        return tuple(segments), max(all_y) - min(all_y)

    def preflight_mannequin(self,
                           plan: tuple[MannequinPiece, ...]) -> None:
        c = self.cmds
        if not c.objExists(self._name("Geometry")):
            raise ValueError("Mannequin 缺少 Geometry 组")
        if self.mannequin_exists():
            raise ValueError("Mannequin 已存在；请先删除旧几何")
        for piece in plan:
            if not c.objExists(self._name(piece.joint)):
                raise ValueError("Mannequin 缺少 Body 关节：" + piece.joint)
            for leaf in (piece.name, piece.name + "SkinCluster"):
                if c.objExists(self._name(leaf)):
                    raise ValueError("Mannequin 名称已占用：" + leaf)
        for leaf in ("shaderMannequin", "shaderMannequinSG"):
            if c.objExists(self._name(leaf)):
                raise ValueError("Mannequin 材质名称已占用：" + leaf)
        self._asset = geometry_asset()

    def _foot_pose(self, mesh: str, piece: MannequinPiece) -> None:
        c = self.cmds
        start, end = piece.start, piece.end
        z_axis = _unit((end[0] - start[0], 0.0,
                        end[2] - start[2]))
        x_axis = (z_axis[2], 0.0, -z_axis[0])
        y_axis = (0.0, 1.0, 0.0)
        center = ((start[0] + end[0]) / 2, 0.0,
                  (start[2] + end[2]) / 2)
        c.xform(mesh, worldSpace=True, matrix=(
            *x_axis, 0, *y_axis, 0, *z_axis, 0, *center, 1))

    def _place_piece(self, mesh: str, piece: MannequinPiece) -> None:
        c = self.cmds
        joint = self._name(piece.joint)
        if piece.source == "Mannequin_Foot":
            self._foot_pose(mesh, piece)
        else:
            c.xform(mesh, worldSpace=True, matrix=c.xform(
                joint, query=True, worldSpace=True, matrix=True))
            offset = self._orient_offset(joint)
            if piece.source != "Mannequin_Sphere" and any(offset):
                c.rotate(*offset, mesh, relative=True, objectSpace=True)
        c.setAttr(mesh + ".scale", *piece.scale, type="double3")
        c.makeIdentity(mesh, apply=True, translate=False,
                       rotate=False, scale=True)

    def create_mannequin(self, plan: tuple[MannequinPiece, ...]) -> int:
        c = self.cmds
        assert self._asset is not None
        temporary = "__AdvPyMannequin_" + uuid4().hex[:12]
        c.file(str(self._asset), i=True, namespace=temporary,
               returnNewNodes=True, ignoreVersion=True)
        try:
            root = c.createNode("transform", name=self._name(
                "MannequinGeometry"), parent=self._name("Geometry"))
            layer = c.createDisplayLayer(name=self._name("Mannequin"),
                                         empty=True)
            c.setAttr(layer + ".color", 24)
            c.setAttr(layer + ".displayType", 2)
            c.editDisplayLayerMembers(layer, root, noRecurse=True)
            self._mannequin_created.clear()
            for piece in plan:
                source = temporary + ":" + piece.source
                if not c.objExists(source):
                    raise ValueError("原版 Mannequin 模板缺失：" + piece.source)
                mesh = c.duplicate(source, name=self._name(piece.name),
                                   returnRootsOnly=True)[0]
                mesh = c.parent(mesh, root)[0]
                self._take_ownership(mesh, temporary)
                c.setAttr(mesh + ".visibility", True)
                self._place_piece(mesh, piece)
                skin = c.skinCluster(self._name(piece.joint), mesh,
                    toSelectedBones=True, maximumInfluences=3,
                    dropoffRate=4,
                    name=self._name(piece.name + "SkinCluster"))[0]
                self._mannequin_created.append((mesh, skin))
            shader = c.shadingNode("lambert", asShader=True,
                name=self._name("shaderMannequin"))
            shading_group = c.sets(renderable=True, noSurfaceShader=True,
                empty=True, name=self._name("shaderMannequinSG"))
            c.connectAttr(shader + ".outColor",
                          shading_group + ".surfaceShader", force=True)
            c.setAttr(shader + ".color", 0.78, 0.63, 0.42,
                      type="double3")
            c.setAttr(shader + ".ambientColor", 0.53, 0.42, 0.25,
                      type="double3")
            c.sets(root, edit=True, forceElement=shading_group)
            return len(self._mannequin_created)
        finally:
            if c.namespace(exists=temporary):
                c.namespace(removeNamespace=temporary,
                            deleteNamespaceContent=True)

    def capture_mannequin(self, count: int) -> bool:
        c = self.cmds
        root = self._name("MannequinGeometry")
        layer = self._name("Mannequin")
        if (count == 0 or count != len(self._mannequin_created)
                or not c.objExists(root) or not c.objExists(layer)
                or c.getAttr(layer + ".color") != 24
                or c.getAttr(layer + ".displayType") != 2
                or not c.objExists(self._name("shaderMannequinSG"))):
            return False
        for mesh, skin in self._mannequin_created:
            if (not c.objExists(mesh) or not c.objExists(skin)
                    or not c.listRelatives(mesh, shapes=True,
                                           noIntermediate=True, type="mesh")
                    or (c.listRelatives(mesh, parent=True) or []) != [root]
                    or skin not in (c.listHistory(mesh) or [])):
                return False
        return True

    def mannequin_exists(self) -> bool:
        c = self.cmds
        return (c.objExists(self._name("MannequinGeometry"))
                or c.objExists(self._name("Mannequin")))

    def delete_mannequin(self) -> None:
        c = self.cmds
        for leaf in ("MannequinGeometry", "Mannequin",
                     "shaderMannequinSG", "shaderMannequin"):
            node = self._name(leaf)
            if c.objExists(node):
                c.delete(node)
