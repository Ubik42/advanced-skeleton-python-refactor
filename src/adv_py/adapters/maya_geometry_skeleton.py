"""Original ADV bone meshes, placed and skinned on the current Body rig."""
from __future__ import annotations

from math import dist
import os
from pathlib import Path
from uuid import uuid4
from contextlib import contextmanager
import re

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
        self._fit_template = ""
        self._deform_joints=()
        self._last_source_scale=(0.,0.,0.)

    @contextmanager
    def transaction(self,label):
        from .maya_fit_geometry import MayaFitGeometryHost
        with super().transaction(label):
            with MayaFitGeometryHost(self.namespace).namespace_scope():yield

    def _main(self):
        for name in ('Main','AdvPy_Global'):
            if self.cmds.objExists(self._name(name)):return self._name(name)
        raise ValueError('Skeleton 缺少角色主控制器')

    def _rla_child(self,joint):
        c=self.cmds;fit=self._name('FitSkeleton')
        tolerance=.01*(c.getAttr(fit+'.scaleX') if c.objExists(fit) else 1.)
        children=c.listRelatives(joint,children=True,type='joint',fullPath=True) or []
        x=c.xform(joint,q=True,ws=True,t=True)[0];center=-tolerance<x<tolerance;result=''
        for child in children:
            x=c.xform(child,q=True,ws=True,t=True)[0]
            if center==(-tolerance<x<tolerance):result=child;break
        for parent_token,child_token in (('Head','Head'),('Ankle','Toes'),('Toes','Toes'),('Root','Spine')):
            if parent_token in self._leaf(joint):
                for child in children:
                    if child_token in self._leaf(child):result=child
        return result

    @staticmethod
    def _leaf(node: str) -> str:
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def capture_skeleton_input(self) -> tuple[set[str], str]:
        c = self.cmds
        deform = self._name("DeformSet")
        if not c.objExists(deform):
            raise ValueError("当前角色缺少 DeformSet")
        members = c.sets(deform, query=True) or []
        self._deform_joints=tuple(self._leaf(node) for node in members if c.nodeType(node)=='joint')
        from adv_py.core.character_identity import CharacterIdentity
        identity=CharacterIdentity(self.namespace)
        joints={self._leaf(node) for node in c.ls(type='joint') or [] if identity.owns(node)}
        if not self._deform_joints:
            raise ValueError("DeformSet 没有可用的 Body 关节")
        fit = self._name("FitSkeleton")
        template = ""
        if c.objExists(fit) and c.attributeQuery("fitSkeletonTemplate",
                                                 node=fit, exists=True):
            template = c.getAttr(fit + ".fitSkeletonTemplate") or ""
        self._fit_template = template
        return joints, template

    def preflight_skeleton_create(self, plan: tuple[BoneCopy, ...]) -> None:
        c = self.cmds
        if not plan:
            raise ValueError("当前 Body 没有可映射到原版骨形的关节")
        if not c.objExists(self._name("Geometry")):
            raise ValueError("当前角色缺少 Geometry 组")
        self._main()
        for leaf in ("SkeletonGeometry", "PolySkeleton"):
            if c.objExists(self._name(leaf)):
                raise ValueError("骨骼几何已存在；请先删除旧几何")
        targets = [spec.target for spec in plan]
        if len(set(targets)) != len(targets):
            raise ValueError("骨骼几何目标名称重复")
        skins = [spec.skin_name for spec in plan]
        if len(set(skins)) != len(skins):
            raise ValueError("骨骼蒙皮节点名称重复")
        for spec in plan:
            if not c.objExists(self._name(spec.joint)):
                raise ValueError("缺少 Body 关节：" + spec.joint)
            if c.objExists(self._name(spec.target)):
                raise ValueError("骨骼几何名称已占用：" + spec.target)
            if c.objExists(self._name(spec.skin_name)):
                raise ValueError("骨骼蒙皮节点名称已占用：" + spec.skin_name)
        self._asset = geometry_asset()

    def _axis(self, node: str, attribute: str, default: str) -> str:
        c = self.cmds
        if not c.objExists(node) or not c.attributeQuery(attribute, node=node, exists=True):
            return default
        value = c.getAttr(node + "." + attribute, asString=True)
        return str(value or default)

    def _orient_offset(self, joint: str) -> tuple[float, float, float]:
        from .maya_original_axes import original_axes
        return icon_axis_offset(*original_axes(self.cmds,joint,self._main(),
                                              fit_skeleton=self._name('FitSkeleton')))

    def _child_joint(self, spec: BoneCopy) -> str:
        c = self.cmds
        if spec.source in {'Cranium','Mandible'} and c.objExists(self._name('HeadEnd_M')):
            return self._name('HeadEnd_M')
        if spec.source == "SpineVertebras":
            if c.objExists(self._name("Head_M")):
                neck = self._landmark(self._name("CraniumBone_M"),
                                      "CraniumBoneNeck")
                if neck:
                    return neck
            for leaf in ("Neck_M", "Neck0_M", "Chest_M"):
                if c.objExists(self._name(leaf)):
                    return self._name(leaf)
        if spec.child and c.objExists(self._name(spec.child)):
            return self._name(spec.child)
        joint = self._name(spec.joint)
        return self._rla_child(joint)

    def _bone_influences(self, spec: BoneCopy) -> list[str]:
        c = self.cmds
        if spec.source in {'horseCoffin','Generic','Phalanges'}:
            return [self._name(spec.joint)]
        if spec.source == "Metacarpal":
            parent = c.listRelatives(self._name(spec.joint), parent=True,
                                     type="joint", fullPath=True) or []
            if len(parent) != 1:
                raise ValueError("Metacarpal 缺少手掌父关节：" + spec.joint)
            return [parent[0]]
        result = [self._name(spec.joint)]
        child = self._rla_child(self._name(spec.joint))
        seen = set(result)
        while child and child not in seen and re.search(r'Part\d',self._leaf(child)):
            result.append(child)
            seen.add(child)
            children = c.listRelatives(child, children=True, type="joint",
                                       fullPath=True) or []
            child = children[0] if len(children) == 1 else ""
        if spec.source == "SpineVertebras" and c.objExists(self._name("Chest_M")):
            result=[self._name('Chest_M')]
            if c.objExists(self._name('Head_M')):
                result=c.listRelatives(self._name('Head_M'),parent=True,fullPath=True) or []
            for _ in range(99):
                parents=[]
                for node in result:parents.extend(c.listRelatives(node,parent=True,fullPath=True) or [])
                result=list(dict.fromkeys(result+parents))
                if any(self._leaf(node)=='Root_M' for node in parents):break
        if spec.source == "Metatarsals":
            parent = c.listRelatives(self._name(spec.joint), parent=True,
                                     type="joint", fullPath=True) or []
            if parent:
                result = [parent[0]]
        return list(dict.fromkeys(result))

    def _place_bone(self, bone: str, spec: BoneCopy) -> None:
        c = self.cmds
        joint = self._name(spec.joint)
        if spec.source == "horseCoffin":
            c.delete(c.pointConstraint(joint, bone,
                                       maintainOffset=False))
            size = c.getAttr(bone + ".translateY")
            c.setAttr(bone + ".translateY", 0)
            self._uniform_scale(bone, size)
            self._last_source_scale=(size,size,size)
            return
        anchor = joint
        if spec.source == "Metacarpal":
            parent = c.listRelatives(joint, parent=True, type="joint",
                                     fullPath=True) or []
            if len(parent) != 1:
                raise ValueError("Metacarpal 缺少手掌父关节：" + spec.joint)
            anchor = parent[0]
        constraint = c.parentConstraint(anchor, bone, maintainOffset=False)[0]
        offset = self._orient_offset(anchor)
        c.setAttr(constraint + ".target[0].targetOffsetRotate",
                  *offset, type="float3")
        c.delete(constraint)
        if spec.source == "Metacarpal":
            c.delete(c.aimConstraint(joint, bone, aimVector=(1, 0, 0),
                                     upVector=(0, 1, 0),
                                     worldUpType="objectrotation",
                                     worldUpVector=self._secondary_vector(joint),
                                     worldUpObject=anchor))
            start = c.xform(anchor, query=True, worldSpace=True,
                            translation=True)
            end = c.xform(joint, query=True, worldSpace=True,
                          translation=True)
            length = dist(start, end)
            side = spec.side
            landmark = self._landmark(self._name("CarpalBBone" + side),
                                      "CarpalBone" + spec.joint[:-2])
            if c.objExists(landmark):
                marker = c.xform(landmark, query=True, worldSpace=True,
                                 translation=True)
                length = dist(marker, end)
            fat = float(c.getAttr(joint + ".fat"))
            front = fat * float(c.getAttr(joint + ".fatFront"))
            width = fat * float(c.getAttr(joint + ".fatWidth"))
            c.xform(bone, objectSpace=True, absolute=True,
                    scale=(length, front, width))
            self._last_source_scale=(length,front,width)
            if c.objExists(landmark):
                c.move(dist(start, marker), 0, 0, bone + ".vtx[0:9999]",
                       relative=True, objectSpace=True,
                       worldSpaceDistance=True)
            return
        child = self._child_joint(spec)
        if child:
            start = c.xform(joint, query=True, worldSpace=True, translation=True)
            end = c.xform(child, query=True, worldSpace=True, translation=True)
            length = dist(start, end)
            front,width=(self._last_source_scale[1:] if spec.source=='Generic' else (length,length))
            if c.attributeQuery('fatFront',node=joint,exists=True):
                front=float(c.getAttr(joint+'.fat'))*float(c.getAttr(joint+'.fatFront'))
                if spec.source!='Generic' or c.attributeQuery('fatWidth',node=joint,exists=True):
                    width=float(c.getAttr(joint+'.fat'))*float(c.getAttr(joint+'.fatWidth'))
            elif spec.source=='Generic' and c.attributeQuery('fatWidth',node=joint,exists=True):
                width=float(c.getAttr(joint+'.fat'))*float(c.getAttr(joint+'.fatWidth'))
            c.xform(bone,objectSpace=True,absolute=True,scale=(length,front,width))
            self._last_source_scale=(length,front,width)
        if spec.side == "_L" and spec.source not in {"Phalanges", "Generic"}:
            pivot = c.xform(joint, query=True, worldSpace=True, translation=True)
            c.scale(-1, -1, -1, bone, relative=True, pivot=pivot)
        elif spec.side == "_L":
            pivot = c.xform(joint, query=True, worldSpace=True, translation=True)
            c.scale(-1, -1, -1, bone + ".vtx[0:9999]",
                    relative=True, pivot=pivot)
            c.polyNormal(bone, normalMode=0, userNormalMode=0,
                         constructionHistory=False)

    def _landmark(self, bone: str, leaf: str) -> str:
        if not self.cmds.objExists(bone):
            return ""
        matches = [node for node in (self.cmds.listRelatives(
            bone, allDescendents=True, fullPath=True,
            type="transform") or ()) if self._leaf(node) == leaf]
        return matches[0] if len(matches) == 1 else ""

    def _take_ownership(self, bone: str, temporary: str) -> None:
        """Keep copied descendants when the imported namespace is removed."""
        c = self.cmds
        descendants = c.listRelatives(bone, allDescendents=True,
                                      fullPath=True) or []
        for node in sorted(descendants, key=lambda item: item.count("|"),
                           reverse=True):
            if node.rsplit("|", 1)[-1].startswith(temporary + ":"):
                c.rename(node, self._name(self._leaf(node)))

    def _uniform_scale(self, bone: str, value: float) -> None:
        self.cmds.setAttr(bone + ".scale", value, value, value, type="double3")

    def _secondary_vector(self, joint: str) -> tuple[int, int, int]:
        from .maya_original_axes import original_axis
        axis=original_axis(self.cmds,'secondary',joint,self._main(),
                           fit_skeleton=self._name('FitSkeleton'))
        sign = -1 if axis.startswith("-") else 1
        return tuple(sign if name == axis[-1] else 0 for name in "XYZ")

    def _soft_mod(self, mesh: str, center: tuple[float, ...],
                  radius: float, name: str) -> tuple[str, str]:
        c = self.cmds
        from .maya_face_deformer_sets import original_face_deformer_sets
        shape=c.listRelatives(mesh,shapes=True,noIntermediate=True,type='mesh',fullPath=True)[0]
        with original_face_deformer_sets(c):
            deform, handle = c.softMod(shape, name=self._name(name),falloffMode=1,falloffAroundSelection=False)[:2]
        shapes = c.listRelatives(handle, shapes=True, fullPath=True) or []
        if len(shapes) != 1:
            raise RuntimeError("骨形 SoftMod 缺少唯一手柄形状：" + mesh)
        c.setAttr(shapes[0] + ".origin", *center, type="double3")
        c.setAttr(deform + ".falloffCenter", *center, type="double3")
        c.setAttr(deform + ".falloffRadius", radius)
        c.setAttr(deform + ".falloffMode", 0)
        return deform, handle

    def _spine_adjust(self, bone: str, spec: BoneCopy) -> None:
        c = self.cmds
        root = self._name("Root_M")
        child = self._child_joint(spec)
        if c.objExists(root) and child:
            c.delete(c.aimConstraint(
                child, bone, aimVector=(1, 0, 0), upVector=(0, 1, 0),
                worldUpType="objectrotation",
                worldUpVector=self._secondary_vector(root),
                worldUpObject=root, maintainOffset=False))
        self._uniform_scale(bone, c.getAttr(bone + ".scaleX"))
        coccyx = self._landmark(bone, "SpineVertebrasCoccyx")
        femur = self._landmark(self._name("PelvisBone_M"), "PelvisBoneFemur")
        if coccyx and femur and c.objExists(root):
            start = c.xform(coccyx, query=True, worldSpace=True,
                            translation=True)
            pivot = c.xform(root, query=True, worldSpace=True,
                            translation=True)
            reference = c.xform(femur, query=True, worldSpace=True,
                                translation=True)
            radius = dist(pivot, start)
            if radius > 1e-8:
                _, handle = self._soft_mod(
                    bone, tuple(start), radius,
                    spec.target + "CoccyxSoftMod")
                c.xform(handle, worldSpace=True, pivots=pivot)
                factor = dist(pivot, reference) / radius
                c.setAttr(handle + ".scale", factor, factor, factor,
                          type="double3")
                c.delete(bone, constructionHistory=True)
        chest = self._name("Chest_M")
        head = self._name("Head_M")
        curve = self._landmark(bone, "SpineVertebrasCurve")
        if not (c.objExists(root) and c.objExists(chest)
                and c.objExists(head) and curve):
            return
        start = c.xform(root, query=True, worldSpace=True, translation=True)
        middle = c.xform(chest, query=True, worldSpace=True,
                         translation=True)
        end = c.xform(head, query=True, worldSpace=True, translation=True)
        total = dist(start, end)
        if total <= 1e-8:
            return
        shape = c.listRelatives(curve, shapes=True, type="nurbsCurve",
                                fullPath=True) or []
        if len(shape) != 1:
            raise RuntimeError("脊柱骨形缺少原版曲线标记")
        path = c.createNode("motionPath",
                            name=self._name(spec.target + "ChestPath"))
        try:
            c.setAttr(path + ".fractionMode", True)
            c.connectAttr(shape[0] + ".worldSpace[0]",
                          path + ".geometryPath")
            c.setAttr(path + ".uValue", dist(start, middle) / total)
            center = c.getAttr(path + ".allCoordinates")[0]
        finally:
            c.delete(path)
        radius = total / 2.0
        if radius > 1e-8:
            _, handle = self._soft_mod(
                bone, tuple(center), radius,
                spec.target + "ChestSoftMod")
            c.xform(handle,pivots=center)
            c.delete(c.pointConstraint(chest, handle,
                                       maintainOffset=False))
            c.delete(bone, constructionHistory=True)

    def _scapula_adjust(self, bone: str, spec: BoneCopy) -> None:
        c = self.cmds
        humerus = self._name("HumerusBone" + spec.side)
        ribs = self._name("RibsBone_M")
        if not c.objExists(humerus) or not c.objExists(ribs):
            return
        fit = self._name("FitSkeleton")
        if c.objExists(fit) and c.attributeQuery(
                "fitSkeletonTemplate", node=fit, exists=True):
            if c.getAttr(fit + ".fitSkeletonTemplate") in {"horse", "cat"}:
                return
        self._uniform_scale(bone, c.getAttr(humerus + ".scaleX"))
        near = self._landmark(bone, "ScapulaBoneLoc1")
        far = self._landmark(bone, "ScapulaBoneLoc2")
        rib = self._landmark(ribs, "RibsBoneLoc1")
        if not near or not far or not rib:
            return
        copy = c.duplicate(bone, name=self._name(spec.target + "_Copy"),
                           returnRootsOnly=True)[0]
        try:
            copy = c.parent(copy, world=True)[0]
            c.makeIdentity(copy, apply=True, translate=True,
                           rotate=True, scale=True)
            start = c.xform(near, query=True, worldSpace=True,
                            translation=True)
            end = c.xform(far, query=True, worldSpace=True,
                          translation=True)
            rib_pos = c.xform(rib, query=True, worldSpace=True,
                              translation=True)
            radius = dist(start, end)
            if radius <= 1e-8:
                return
            deform, handle = self._soft_mod(
                copy, tuple(start), radius,
                spec.target + "ScapulaSoftMod")
            c.xform(handle, worldSpace=True, pivots=start)
            c.setAttr(deform + ".falloffInY", 0)
            c.move(0, 0, (rib_pos[2] - start[2]) * 1.2, handle,
                   relative=True, worldSpace=True)
            copy_shape=c.listRelatives(copy,shapes=True,noIntermediate=True,type='mesh',fullPath=True)[0]
            bone_shape=c.listRelatives(bone,shapes=True,noIntermediate=True,type='mesh',fullPath=True)[0]
            shape = c.blendShape(copy_shape, bone_shape,
                                 name=self._name(spec.target + "ShapeBlend"))[0]
            c.setAttr(shape + ".origin", 0)
            c.setAttr(shape + ".weight[0]", 1)
            c.delete(bone, constructionHistory=True)
        finally:
            if c.objExists(copy):
                c.delete(copy)

    def _clavicle_adjust(self, bone: str, spec: BoneCopy) -> None:
        c = self.cmds
        scapula = self._name("ScapulaBone" + spec.side)
        ribs = self._name("RibsBone_M")
        chest = self._name("Chest_M")
        if not all(c.objExists(node) for node in (scapula, ribs, chest)):
            return
        rib_marker = self._landmark(ribs, "RibsBoneClavicle")
        scap_marker = self._landmark(scapula, "ScapulaBoneClavicle")
        if not rib_marker or not scap_marker:
            return
        sign = -1 if spec.side == "_L" else 1
        start = c.xform(rib_marker, query=True, worldSpace=True,
                        translation=True)
        end = c.xform(scap_marker, query=True, worldSpace=True,
                      translation=True)
        c.xform(bone, worldSpace=True,
                translation=(start[0] * sign, start[1], start[2]))
        reflected = (end[0] * sign, end[1], end[2])
        length = dist(start, reflected) * sign
        c.xform(bone, objectSpace=True, absolute=True,
                scale=(length, length, length))
        c.delete(c.aimConstraint(
            scap_marker, bone, aimVector=(sign, 0, 0),
            upVector=(0, sign, 0), worldUpType="objectrotation",
            worldUpVector=self._secondary_vector(chest),
            worldUpObject=chest, maintainOffset=False))

    def _metatarsals_adjust(self, bone: str, spec: BoneCopy) -> None:
        c = self.cmds
        ankle = self._name("Ankle" + spec.side)
        toes = self._name("Toes" + spec.side)
        talus = self._name("TalusBone" + spec.side)
        if not all(c.objExists(node) for node in (ankle, toes, talus)):
            return
        holder = self._landmark(bone, "MetatarsalsBoneLattice")
        from_toes = self._landmark(bone, "MetatarsalsBoneToes")
        to_toes = self._landmark(talus, "TalusBoneToes")
        if not holder or not from_toes or not to_toes:
            return
        shape=c.listRelatives(bone,shapes=True,noIntermediate=True,type='mesh',fullPath=True)[0]
        result = c.lattice(shape, divisions=(2, 2, 2),
                           objectCentered=True, ldivisions=(2, 2, 2))
        if len(result) != 3:
            raise RuntimeError("足掌晶格没有返回变形器与双晶格")
        lattice, base = c.parent(result[1], result[2], holder)
        for node in (lattice, base):
            c.xform(node, objectSpace=True, translation=(0, 0, 0),
                    rotation=(0, 0, 0), scale=(1, 1, 1))
        start = c.xform(from_toes, query=True, worldSpace=True,
                        translation=True)
        end = c.xform(to_toes, query=True, worldSpace=True,
                      translation=True)
        offset = tuple(end[index] - start[index] for index in range(3))
        c.select(lattice+'.pt[0][0:1][0]',lattice+'.pt[0][0:1][1]',replace=True)
        c.move(*offset,relative=True)
        c.delete(bone, constructionHistory=True)

    def _adjust_anatomy(self, bone: str, spec: BoneCopy) -> None:
        """Apply original bone-landmark proportions before Skin binding."""
        c = self.cmds
        if (self._fit_template == "horse" and spec.source == "Generic"
                and spec.joint.startswith(("Fingers", "Toes"))):
            point = c.xform(self._name(spec.joint), query=True,
                            worldSpace=True, translation=True)
            c.scale(1, 2, 2, bone + ".vtx[0:9999]",
                    relative=True, pivot=point)
        if spec.source == "SpineVertebras" and spec.side == "_M":
            self._spine_adjust(bone, spec)
        elif spec.source == "Scapula":
            self._scapula_adjust(bone, spec)
        elif spec.source == "Clavicle":
            self._clavicle_adjust(bone, spec)
        elif spec.source == "Pelvis" and spec.side == "_M":
            root = self._name("Root_M")
            children = c.listRelatives(root, children=True, type="joint",
                                       fullPath=True) or []
            marker = self._landmark(bone, "PelvisBoneFemur")
            c.xform(bone,worldSpace=True,rotation=(0,0,0))
            for right in children:
                if not self._leaf(right).endswith('_R') or not c.objExists(marker):continue
                hip = c.xform(right, query=True, worldSpace=True, translation=True)
                c.xform(bone, worldSpace=True, translation=(0, hip[1], hip[2]))
                femur = c.xform(marker, query=True, worldSpace=True,
                                translation=True)
                if abs(femur[0]) > 1e-8:
                    ratio = hip[0] / femur[0]
                    c.xform(bone,relative=True,scale=(ratio,ratio,ratio))
                    self._uniform_scale(bone, c.getAttr(bone + ".scaleX"))
        elif spec.source == "Cranium" and spec.side == "_M":
            eye = self._name("Eye_R")
            marker = self._landmark(bone, "CraniumBoneEye")
            if c.objExists(eye) and c.objExists(marker):
                target = c.xform(eye, query=True, worldSpace=True,
                                 translation=True)
                current = c.xform(marker, query=True, worldSpace=True,
                                  translation=True)
                if abs(current[0]) > 1e-8:
                    ratio = target[0] / current[0]
                    c.scale(ratio, ratio, ratio, bone, relative=True)
                    self._uniform_scale(bone, c.getAttr(bone + ".scaleZ"))
                    current = c.xform(marker, query=True, worldSpace=True,
                                      translation=True)
                    c.move(0, target[1] - current[1], 0, bone,
                           relative=True, worldSpace=True)
        elif spec.source == "Mandible" and spec.side == "_M":
            cranium = self._name("CraniumBone_M")
            if c.objExists(cranium):
                c.delete(c.parentConstraint(cranium, bone,
                                            maintainOffset=False))
                c.setAttr(bone + ".scale",
                          *c.getAttr(cranium + ".scale")[0], type="double3")
                self._last_source_scale=tuple(c.getAttr(cranium+'.scale')[0])
        elif spec.source == "Calcaneus" and all(c.objExists(self._name(name)) for name in ('Toes','Ankle','Heel')):
            ankle = self._name("Ankle" + spec.side)
            heel = self._name('Heel')
            first = self._landmark(bone, "CalcaneusBoneLoc1")
            second = self._landmark(bone, "CalcaneusBoneLoc2")
            if all(c.objExists(node) for node in (ankle, heel, first, second)):
                ankle_pos = c.xform(ankle, query=True, worldSpace=True,
                                   translation=True)
                first_pos = c.xform(first, query=True, worldSpace=True,
                                   translation=True)
                height = ankle_pos[1] - first_pos[1]
                if abs(height) > 1e-8:
                    ratio = ankle_pos[1] / height * 0.95
                    c.scale(ratio, 1, ratio, bone, relative=True)
                second_pos = c.xform(second, query=True, worldSpace=True,
                                    translation=True)
                heel_pos = c.xform(heel, query=True, worldSpace=True,
                                  translation=True)
                depth = ankle_pos[2] - second_pos[2]
                if abs(depth) > 1e-8:
                    ratio = (ankle_pos[2] - heel_pos[2]) / depth * 0.9
                    c.scale(1, ratio, 1, bone, relative=True)
                    c.setAttr(bone + ".scaleZ", c.getAttr(bone + ".scaleY"))
        elif spec.source == "Talus":
            heel_bone = self._name("CalcaneusBone" + spec.side)
            if c.objExists(heel_bone):
                self._uniform_scale(bone, c.getAttr(heel_bone + ".scaleY"))
        elif spec.source in {"Metatarsals", "Phalanxs"} and all(c.objExists(self._name(name)) for name in ('Toes','Ankle')):
            talus = self._name("TalusBone" + spec.side)
            if c.objExists(talus):
                width = c.getAttr(talus + ".scaleX")
                c.setAttr(bone + ".scaleY", width)
                c.setAttr(bone + ".scaleZ", width)
            if spec.source == "Metatarsals":
                self._metatarsals_adjust(bone, spec)

    def _skin_tweaks(self, bone: str, skin: str, spec: BoneCopy) -> None:
        c = self.cmds
        joint = self._name(spec.joint)
        if spec.source == "CarpalA":
            parents = c.listRelatives(joint, parent=True, type="joint",
                                      fullPath=True) or []
            if len(parents) == 1:
                c.skinCluster(skin, edit=True, addInfluence=parents[0],
                              dropoffRate=4)
                c.skinPercent(skin, bone + ".vtx[*]",
                              transformValue=(joint, 0.5))
        elif spec.source == "Mandible":
            parents = c.listRelatives(joint, parent=True, type="joint",
                                      fullPath=True) or []
            head = self._name("Head_M")
            if (len(parents) == 1 and self._leaf(parents[0]) == "FaceJoint_M"
                    and c.objExists(head)):
                deform, handle = c.cluster(
                    bone, name=self._name(spec.source+'BoneCluster'+spec.side),
                    envelope=1)
                handle = c.parent(handle, bone)[0]
                c.setAttr(handle + ".visibility", False)
                c.parentConstraint(head, handle, maintainOffset=True)
                c.scaleConstraint(head, handle)

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
        temporary = "AdvPyBoneTemplate_" + uuid4().hex[:12]
        c.file(str(self._asset), i=True, namespace=temporary,
               returnNewNodes=True, ignoreVersion=True)
        try:
            root = c.createNode("transform", name=self._name("SkeletonGeometry"),
                                parent=self._name("Geometry"), skipSelect=True)
            layer = c.createDisplayLayer(empty=True,
                                         name=self._name("PolySkeleton"))
            self._created.clear()
            self._last_source_scale=(0.,0.,0.)
            fit = self._name("FitSkeleton")
            fit_template = ""
            if c.objExists(fit) and c.attributeQuery("fitSkeletonTemplate",
                                                     node=fit, exists=True):
                fit_template = c.getAttr(fit + ".fitSkeletonTemplate") or ""
            # The MEL loops use DeformSet order for fingers and Generic pieces.
            order={joint:index for index,joint in enumerate(self._deform_joints)}
            staged=[]
            for family in ('named','Phalanges','Metacarpal','Generic','horseCoffin'):
                batch=[spec for spec in plan if (spec.source==family if family!='named' else spec.source not in ('Phalanges','Metacarpal','Generic','horseCoffin'))]
                if family!='named':batch.sort(key=lambda spec:order.get(spec.joint,len(order)))
                staged.extend(batch)
            for spec in staged:
                if spec.source in {'Phalanges','Metacarpal','Generic','horseCoffin'} and spec.joint not in order:continue
                if spec.source=='Generic':
                    connected=c.listConnections(self._name(spec.joint)+'.worldMatrix',source=False,destination=True) or []
                    if any(re.search(r'BoneSC_',self._leaf(node)) for node in connected):continue
                child = self._child_joint(spec)
                if spec.source in {"Phalanges", "Generic"} and not child:
                    continue
                source_leaf = spec.template
                special = fit_template + source_leaf
                if fit_template and c.objExists(temporary + ":" + special):
                    c.delete(temporary+':'+source_leaf)
                    c.rename(temporary+':'+special,temporary+':'+source_leaf)
                    for node in c.listRelatives(temporary+':'+source_leaf,allDescendents=True,type='transform',fullPath=True) or []:
                        if fit_template in self._leaf(node):c.rename(node,temporary+':'+self._leaf(node).replace(fit_template,'',1))
                source = temporary + ":" + source_leaf
                if not c.objExists(source):
                    raise ValueError("原版骨形模板缺失：" + source_leaf)
                bone = c.duplicate(source, name=self._name(spec.target),
                                   returnRootsOnly=True)[0]
                bone = c.parent(bone, root)[0]
                self._take_ownership(bone, temporary)
                self._place_bone(bone, spec)
                self._adjust_anatomy(bone, spec)
                c.setAttr(bone + ".visibility", True)
                c.editDisplayLayerMembers(layer, bone, noRecurse=True)
                influences = self._bone_influences(spec)
                skin = c.skinCluster(*(influences + [bone]),
                                     toSelectedBones=True, maximumInfluences=3,
                                     dropoffRate=4,removeUnusedInfluence=False,
                                     name=self._name(spec.skin_name))[0]
                self._skin_tweaks(bone, skin, spec)
                self._created.append((bone, skin))
            # Bone landmarks are consumed by later anatomical pieces. The
            # original procedure removes them only after every bone is built.
            for bone, _ in self._created:
                self._cleanup_landmarks(bone)
            c.select(clear=True)
            return len(self._created)
        finally:
            for leaf in ('Mannequin_Geometry','Skeleton_Geometry','SkinCage_Geometry'):
                if c.objExists(temporary+':'+leaf):c.delete(temporary+':'+leaf)
            if c.namespace(exists=temporary):
                c.namespace(moveNamespace=(':'+temporary,':'+self.namespace if self.namespace else ':'),force=True)
                c.namespace(removeNamespace=':'+temporary)

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
        for leaf in ('SkeletonGeometry','PolySkeleton','Skeleton_Geometry','Mannequin_Geometry','SkinCage_Geometry','Skeleton','tempAimAt'):
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

    def mirror_skeleton_geometry(self,
                                 pairs: tuple[tuple[str, str], ...]) -> int:
        c = self.cmds
        for source, target in pairs:
            a, b = self._name(source), self._name(target)
            if not c.getAttr(b+'.scaleX',lock=True):
                c.setAttr(b+'.scale',*c.getAttr(a+'.scale')[0],type='float3')
            count = int(c.polyEvaluate(a, vertex=True))
            for index in range(count):
                point = c.xform(f"{a}.vtx[{index}]", query=True,
                                worldSpace=True, translation=True)
                c.xform(f"{b}.vtx[{index}]", worldSpace=True,
                        translation=(-point[0], point[1], point[2]))
        return len(pairs)
