"""Original ADV bone meshes, placed and skinned on the current Body rig."""
from __future__ import annotations

from math import dist
import os
from pathlib import Path
from uuid import uuid4

from adv_py.core.adv_icon_axis import icon_axis_offset
from adv_py.core.geometry_skeleton import BoneCopy
from .maya_skin_cage import MayaSkinCageHost


_PROJECT_ASSET = (Path(__file__).resolve().parents[3] / "local"
                  / "adv_6_925" / "asGeometry.ma")


def geometry_asset() -> Path:
    configured = os.environ.get("ADV_6925_GEOMETRY_FILE", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_file():
            raise ValueError("原版 asGeometry.ma 不存在：" + str(candidate))
        return candidate
    if _PROJECT_ASSET.is_file():
        return _PROJECT_ASSET
    for root in filter(None, os.environ.get("MAYA_SCRIPT_PATH", "").split(os.pathsep)):
        folder = Path(root)
        for candidate in (folder / "AdvancedSkeletonFiles" / "div" / "asGeometry.ma",
                          folder / "asGeometry.ma"):
            if candidate.is_file():
                return candidate
    raise ValueError("缺少 ADV 6.925 asGeometry.ma；设置 ADV_6925_GEOMETRY_FILE")


class MayaSkeletonGeometryHost(MayaSkinCageHost):
    def __init__(self, namespace: str = "") -> None:
        super().__init__(namespace)
        self._created: list[tuple[str, str]] = []
        self._asset: Path | None = None

    @staticmethod
    def _leaf(node: str) -> str:
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def capture_skeleton_input(self) -> tuple[set[str], str]:
        c = self.cmds
        deform = self._name("DeformSet")
        if not c.objExists(deform):
            raise ValueError("当前角色缺少 DeformSet")
        members = c.sets(deform, query=True) or []
        joints = {self._leaf(node) for node in members
                  if c.objExists(node) and c.nodeType(node) == "joint"}
        if not joints:
            raise ValueError("DeformSet 没有可用的 Body 关节")
        fit = self._name("FitSkeleton")
        template = ""
        if c.objExists(fit) and c.attributeQuery("fitSkeletonTemplate",
                                                 node=fit, exists=True):
            template = c.getAttr(fit + ".fitSkeletonTemplate") or ""
        return joints, template

    def preflight_skeleton_create(self, plan: tuple[BoneCopy, ...]) -> None:
        c = self.cmds
        if not plan:
            raise ValueError("当前 Body 没有可映射到原版骨形的关节")
        if not c.objExists(self._name("Geometry")):
            raise ValueError("当前角色缺少 Geometry 组")
        if not c.objExists(self._name("Main")):
            raise ValueError("当前角色缺少 Main 控制器")
        for leaf in ("SkeletonGeometry", "PolySkeleton"):
            if c.objExists(self._name(leaf)):
                raise ValueError("骨骼几何已存在；请先删除旧几何")
        targets = [spec.target for spec in plan]
        if len(set(targets)) != len(targets):
            raise ValueError("骨骼几何目标名称重复")
        for spec in plan:
            if not c.objExists(self._name(spec.joint)):
                raise ValueError("缺少 Body 关节：" + spec.joint)
            if c.objExists(self._name(spec.target)):
                raise ValueError("骨骼几何名称已占用：" + spec.target)
        self._asset = geometry_asset()

    def _axis(self, node: str, attribute: str, default: str) -> str:
        c = self.cmds
        if not c.objExists(node) or not c.attributeQuery(attribute, node=node, exists=True):
            return default
        value = c.getAttr(node + "." + attribute, asString=True)
        return str(value or default)

    def _orient_offset(self, joint: str) -> tuple[float, float, float]:
        c = self.cmds
        main = self._name("Main")
        primary = self._axis(main, "primaryAxis", "X")
        secondary = self._axis(main, "secondaryAxis", "Y")
        fit = self._name("FitSkeleton")
        if c.objExists(fit) and c.attributeQuery("worldmatch", node=fit, exists=True):
            if c.getAttr(fit + ".worldmatch"):
                primary = self._axis(joint, "primaryAxis", primary)
                secondary = self._axis(joint, "secondaryAxis", secondary)
        return icon_axis_offset(primary, secondary)

    def _child_joint(self, spec: BoneCopy) -> str:
        c = self.cmds
        if spec.child and c.objExists(self._name(spec.child)):
            return self._name(spec.child)
        joint = self._name(spec.joint)
        children = c.listRelatives(joint, children=True, type="joint",
                                   fullPath=True) or []
        while len(children) == 1 and "Part" in self._leaf(children[0]):
            # ADV binds Part joints as additional influences; the first
            # Part still determines the nearest anatomical segment length.
            return children[0]
        return children[0] if len(children) == 1 else ""

    def _influences(self, spec: BoneCopy) -> list[str]:
        c = self.cmds
        result = [self._name(spec.joint)]
        child = self._child_joint(spec)
        seen = set(result)
        while child and child not in seen and "Part" in self._leaf(child):
            result.append(child)
            seen.add(child)
            children = c.listRelatives(child, children=True, type="joint",
                                       fullPath=True) or []
            child = children[0] if len(children) == 1 else ""
        if spec.source == "SpineVertebras" and c.objExists(self._name("Chest_M")):
            result.append(self._name("Chest_M"))
        if spec.source == "Metatarsals":
            parent = c.listRelatives(self._name(spec.joint), parent=True,
                                     type="joint", fullPath=True) or []
            if parent:
                result = [parent[0]]
        return list(dict.fromkeys(result))

    def _place_bone(self, bone: str, spec: BoneCopy) -> None:
        c = self.cmds
        joint = self._name(spec.joint)
        constraint = c.parentConstraint(joint, bone, maintainOffset=False)[0]
        offset = self._orient_offset(joint)
        c.setAttr(constraint + ".target[0].targetOffsetRotate",
                  *offset, type="double3")
        c.delete(constraint)
        child = self._child_joint(spec)
        if child:
            start = c.xform(joint, query=True, worldSpace=True, translation=True)
            end = c.xform(child, query=True, worldSpace=True, translation=True)
            length = dist(start, end)
            if length > 1e-8:
                front = width = length
                if c.attributeQuery("fatFront", node=joint, exists=True):
                    fat = float(c.getAttr(joint + ".fat"))
                    front = fat * float(c.getAttr(joint + ".fatFront"))
                    width = fat * float(c.getAttr(joint + ".fatWidth"))
                c.xform(bone, objectSpace=True, absolute=True,
                        scale=(length, front, width))
        if spec.side == "_L" and spec.source != "Phalanges":
            pivot = c.xform(joint, query=True, worldSpace=True, translation=True)
            c.scale(-1, -1, -1, bone, relative=True, pivot=pivot)

    def _cleanup_landmarks(self, bone: str) -> None:
        c = self.cmds
        shapes = c.listRelatives(bone, allDescendents=True, fullPath=True,
                                 type="locator") or []
        shapes += c.listRelatives(bone, allDescendents=True, fullPath=True,
                                  type="nurbsCurve") or []
        transforms = set()
        for shape in shapes:
            transforms.update(c.listRelatives(shape, parent=True, fullPath=True) or ())
        if transforms:
            c.delete(sorted(transforms, key=lambda item: item.count("|"), reverse=True))

    def create_skeleton_geometry(self, plan: tuple[BoneCopy, ...]) -> int:
        c = self.cmds
        assert self._asset is not None
        temporary = "__AdvPyBoneTemplate_" + uuid4().hex[:12]
        c.file(str(self._asset), i=True, namespace=temporary,
               returnNewNodes=True, ignoreVersion=True)
        try:
            root = c.createNode("transform", name=self._name("SkeletonGeometry"),
                                parent=self._name("Geometry"), skipSelect=True)
            layer = c.createDisplayLayer(empty=True,
                                         name=self._name("PolySkeleton"))
            self._created.clear()
            fit = self._name("FitSkeleton")
            fit_template = ""
            if c.objExists(fit) and c.attributeQuery("fitSkeletonTemplate",
                                                     node=fit, exists=True):
                fit_template = c.getAttr(fit + ".fitSkeletonTemplate") or ""
            for spec in plan:
                child = self._child_joint(spec)
                if spec.source == "Phalanges" and not child:
                    continue
                source_leaf = spec.template
                special = fit_template + source_leaf
                if fit_template and c.objExists(temporary + ":" + special):
                    source_leaf = special
                source = temporary + ":" + source_leaf
                if not c.objExists(source):
                    raise ValueError("原版骨形模板缺失：" + source_leaf)
                bone = c.duplicate(source, name=self._name(spec.target),
                                   returnRootsOnly=True)[0]
                bone = c.parent(bone, root)[0]
                self._place_bone(bone, spec)
                c.setAttr(bone + ".visibility", True)
                c.editDisplayLayerMembers(layer, bone, noRecurse=True)
                influences = self._influences(spec)
                skin = c.skinCluster(*(influences + [bone]),
                                     toSelectedBones=True, maximumInfluences=3,
                                     dropoffRate=4,
                                     name=self._name(spec.target + "SC"))[0]
                self._cleanup_landmarks(bone)
                self._created.append((bone, skin))
            return len(self._created)
        finally:
            if c.namespace(exists=temporary):
                c.namespace(removeNamespace=temporary,
                            deleteNamespaceContent=True)

    def capture_skeleton_geometry(self, count: int) -> bool:
        c = self.cmds
        if count == 0 or count != len(self._created):
            return False
        if not c.objExists(self._name("SkeletonGeometry")):
            return False
        if not c.objExists(self._name("PolySkeleton")):
            return False
        for bone, skin in self._created:
            if not c.objExists(bone) or not c.objExists(skin):
                return False
            parent = c.listRelatives(bone, parent=True, fullPath=True) or []
            if len(parent) != 1 or self._leaf(parent[0]) != "SkeletonGeometry":
                return False
            if skin not in (c.listHistory(bone, pruneDagObjects=True) or []):
                return False
        return True

    def skeleton_geometry_exists(self) -> bool:
        c = self.cmds
        return any(c.objExists(self._name(leaf))
                   for leaf in ("SkeletonGeometry", "PolySkeleton"))

    def delete_skeleton_geometry(self) -> None:
        c = self.cmds
        for leaf in ("SkeletonGeometry", "PolySkeleton"):
            node = self._name(leaf)
            if c.objExists(node):
                c.delete(node)

    def capture_skeleton_bone_names(self) -> set[str]:
        c = self.cmds
        root = self._name("SkeletonGeometry")
        if not c.objExists(root):
            raise ValueError("当前角色没有 SkeletonGeometry")
        return {self._leaf(node) for node in (
            c.listRelatives(root, children=True, type="transform",
                            fullPath=True) or ())}

    def preflight_skeleton_mirror(self,
                                  pairs: tuple[tuple[str, str], ...]) -> None:
        c = self.cmds
        if not pairs:
            raise ValueError("骨骼几何没有可镜像的左右配对")
        for source, target in pairs:
            a, b = self._name(source), self._name(target)
            if not c.objExists(a) or not c.objExists(b):
                raise ValueError("骨骼几何镜像配对缺失：" + source)
            if int(c.polyEvaluate(a, vertex=True)) != int(
                    c.polyEvaluate(b, vertex=True)):
                raise ValueError("骨骼几何左右顶点数量不同：" + source)
            if any(c.getAttr(b + ".scale" + axis, lock=True)
                   for axis in "XYZ"):
                raise ValueError("目标骨骼几何缩放已锁定：" + target)

    def mirror_skeleton_geometry(self,
                                 pairs: tuple[tuple[str, str], ...]) -> int:
        c = self.cmds
        for source, target in pairs:
            a, b = self._name(source), self._name(target)
            c.setAttr(b + ".scale", *c.getAttr(a + ".scale")[0],
                      type="double3")
            count = int(c.polyEvaluate(a, vertex=True))
            for index in range(count):
                point = c.xform(f"{a}.vtx[{index}]", query=True,
                                worldSpace=True, translation=True)
                c.xform(f"{b}.vtx[{index}]", worldSpace=True,
                        translation=(-point[0], point[1], point[2]))
        return len(pairs)
