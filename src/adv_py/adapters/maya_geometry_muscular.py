"""ADV 6.925 Muscular scene import, bone fit and curve placement."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from adv_py.core.geometry_muscular import MuscleBoneMatch
from .maya_skin_cage import MayaSkinCageHost


_PROJECT_ASSET = (Path(__file__).resolve().parents[3] / "local"
                  / "adv_6_925" / "asMuscular.ma")


def muscular_asset() -> Path:
    configured = os.environ.get("ADV_6925_MUSCULAR_FILE", "").strip()
    if configured:
        result = Path(configured).expanduser()
        if not result.is_file():
            raise ValueError("原版 asMuscular.ma 不存在：" + str(result))
        return result
    if _PROJECT_ASSET.is_file():
        return _PROJECT_ASSET
    for root in filter(None, os.environ.get("MAYA_SCRIPT_PATH", "").split(os.pathsep)):
        folder = Path(root)
        for result in (folder / "AdvancedSkeletonFiles" / "div" / "asMuscular.ma",
                       folder / "asMuscular.ma"):
            if result.is_file():
                return result
    raise ValueError("缺少 ADV 6.925 asMuscular.ma；设置 ADV_6925_MUSCULAR_FILE")


class MayaMuscularHost(MayaSkinCageHost):
    def __init__(self, namespace: str = "") -> None:
        super().__init__(namespace)
        self._asset: Path | None = None
        self._before: set[str] = set()
        self._fitted_curves: list[str] = []
        self._mirrored_groups: list[str] = []

    @staticmethod
    def _leaf(node: str) -> str:
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def preflight_muscular_create(self) -> None:
        c = self.cmds
        for leaf in ("Geometry", "SkeletonGeometry"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("先创建当前角色的 Skeleton Geometry：" + leaf)
        for leaf in ("MuscularGeometry", "Muscular_SkeletonGeometry",
                     "Muscular_Root_M", "NurbsMuscles"):
            if c.objExists(self._name(leaf)):
                raise ValueError("Muscular 场景节点已存在：" + leaf)
        self._asset = muscular_asset()

    def import_muscular_template(self) -> None:
        c = self.cmds
        assert self._asset is not None
        self._before = set(c.ls(dependencyNodes=True) or ())
        temporary = "__AdvPyMuscular_" + uuid4().hex[:12]
        c.file(str(self._asset), i=True, namespace=temporary,
               returnNewNodes=True, ignoreVersion=True)
        destination = ":" + self.namespace if self.namespace else ":"
        c.namespace(moveNamespace=(":" + temporary, destination),
                    force=True)
        c.namespace(removeNamespace=":" + temporary)
        root = self._name("MuscularGeometry")
        bones = self._name("Muscular_SkeletonGeometry")
        muscles = self._name("Muscular_Muscles")
        if not all(c.objExists(node) for node in (root, bones, muscles)):
            raise RuntimeError("原版 asMuscular.ma 缺少主要几何分组")
        c.parent(root, self._name("Geometry"))
        layer = c.createDisplayLayer(empty=True,
                                     name=self._name("NurbsMuscles"))
        c.editDisplayLayerMembers(layer, root, noRecurse=True)

    def imported_bone_names(self) -> tuple[str, ...]:
        c = self.cmds
        root = self._name("Muscular_SkeletonGeometry")
        names = []
        for node in c.listRelatives(root, children=True,
                                    type="transform", fullPath=True) or ():
            if c.listRelatives(node, shapes=True, noIntermediate=True,
                               type="mesh"):
                names.append(self._leaf(node))
        return tuple(names)

    def skeleton_bone_names(self) -> set[str]:
        c = self.cmds
        root = self._name("SkeletonGeometry")
        return {self._leaf(node) for node in (
            c.listRelatives(root, children=True, type="transform",
                            fullPath=True) or ())}

    def match_muscle_bones(self, matches: tuple[MuscleBoneMatch, ...]) -> None:
        c = self.cmds
        if not matches:
            raise ValueError("Muscular 模板没有匹配到当前 Skeleton 骨形")
        for spec in matches:
            imported = self._name(spec.template)
            skeleton = self._name(spec.skeleton)
            if not c.objExists(imported) or not c.objExists(skeleton):
                raise ValueError("Muscular 骨形配对缺失：" + spec.template)
            for axis in "XYZ":
                c.setAttr(imported + ".scale" + axis, lock=False)
                c.setAttr(imported + ".scale" + axis,
                          c.getAttr(skeleton + ".scale" + axis))
            blend = c.blendShape(
                skeleton, imported,
                name=self._name(spec.template + "BS"))[0]
            c.setAttr(blend + ".origin", 0)
            c.setAttr(blend + ".weight[0]", 1)

    def _muscle_groups(self) -> tuple[str, ...]:
        c = self.cmds
        return tuple(c.listRelatives(self._name("Muscular_Muscles"),
                                     children=True, type="transform",
                                     fullPath=True) or ())

    def _curves(self, muscle: str) -> tuple[str, ...]:
        c = self.cmds
        result = []
        for child in c.listRelatives(muscle, children=True,
                                     type="transform", fullPath=True) or ():
            if c.listRelatives(child, shapes=True, noIntermediate=True,
                               type="nurbsCurve"):
                result.append(child)
        return tuple(result)
    def _wraps(self, curve: str) -> set[str]:
        c = self.cmds
        return {node for node in (c.listHistory(curve) or ())
                if c.nodeType(node) == "wrap"}

    def fit_muscle_curves(self) -> int:
        from maya import mel

        c = self.cmds
        wraps: dict[str, str] = {}
        groups = self._muscle_groups()
        for group in groups:
            for curve in self._curves(group):
                if not c.attributeQuery("attach", node=curve, exists=True):
                    raise ValueError("原版肌肉曲线缺少 attach：" + curve)
                attach = c.getAttr(curve + ".attach")
                driver = self._name("Muscular_" + attach)
                if not c.objExists(driver):
                    raise ValueError("肌肉曲线找不到原版贴附骨形：" + driver)
                before = self._wraps(curve)
                c.select(curve, driver, replace=True)
                mel.eval('doWrapArgList 7 { "1","0","1", "2", "0", "1", "1", "0" }')
                created = self._wraps(curve) - before
                if len(created) != 1:
                    raise RuntimeError("肌肉曲线没有生成唯一 Wrap：" + curve)
                wraps[curve] = c.rename(
                    next(iter(created)),
                    self._name(self._leaf(curve) + "TempWrap"))
        for index in range(1, 5):
            source = self._name(f"Muscular_ExternalObliqueALT1_curve{index}_R")
            target = self._name(f"Muscular_ExternalOblique_curve{index}_R")
            if not c.objExists(source) or not c.objExists(target):
                continue
            blend = c.blendShape(source, target,
                                 name=target + "TempBS")[0]
            c.setAttr(blend + ".origin", 0)
            for vertex, value in {7: 0, 6: 0.2, 8: 0.2,
                                  5: 0.4, 9: 0.4, 4: 0.6,
                                  10: 0.6, 3: 0.8, 11: 0.8,
                                  2: 1, 0: 1}.items():
                c.setAttr(blend +
                          f".inputTarget[0].inputTargetGroup[0].targetWeights[{vertex}]",
                          value)
            c.setAttr(blend + ".weight[0]", 1)
        self._fitted_curves.clear()
        for group in groups:
            for curve in self._curves(group):
                cvs = c.ls(curve + ".cv[*]", flatten=True) or []
                points = [c.xform(cv, query=True, worldSpace=True,
                                  translation=True) for cv in cvs]
                c.delete(wraps[curve])
                blend = self._name(self._leaf(curve) + "TempBS")
                if "ALT" not in self._leaf(curve) and c.objExists(blend):
                    c.delete(blend)
                for cv, point in zip(cvs, points):
                    c.xform(cv, worldSpace=True, translation=point)
                if "ALT" not in self._leaf(curve):
                    self._fitted_curves.append(curve)
        bones = self._name("Muscular_SkeletonGeometry")
        if c.objExists(bones):
            c.delete(bones)
        for group in groups:
            if "ALT" in self._leaf(group) and c.objExists(group):
                c.delete(group)
        return len(self._fitted_curves)
    def _curve_skin(self, curve: str) -> str:
        c = self.cmds
        skins = [node for node in (c.listHistory(curve) or ())
                 if c.nodeType(node) == "skinCluster"]
        if len(skins) != 1:
            raise ValueError("肌肉曲线需要唯一的 SkinCluster：" + curve)
        return skins[0]

    def _mapped_influence(self, source: str, skeleton: set[str]) -> str:
        from adv_py.core.geometry_muscular import resolve_muscle_influence

        c = self.cmds
        parents: dict[str, str] = {}
        current = source
        while current and current not in parents:
            parent = c.listRelatives(current, parent=True,
                                     type="joint", fullPath=True) or []
            parents[self._leaf(current)] = (self._leaf(parent[0])
                                            if parent else "")
            current = parent[0] if parent else ""
        leaf = resolve_muscle_influence(self._leaf(source),
                                        parents, skeleton)
        return self._name(leaf)

    def transfer_muscle_skin(self) -> int:
        c = self.cmds
        skeleton = self.skeleton_bone_names()
        transferred = 0
        for curve in self._fitted_curves:
            old = self._curve_skin(curve)
            sources = c.skinCluster(old, query=True, influence=True) or []
            mapped = [self._mapped_influence(node, skeleton)
                      for node in sources]
            targets = list(dict.fromkeys(mapped))
            method = c.getAttr(old + ".skinningMethod")
            cvs = c.ls(curve + ".cv[*]", flatten=True) or []
            weights = [c.skinPercent(old, cv, query=True, value=True)
                       for cv in cvs]
            if any(len(row) != len(sources) for row in weights):
                raise RuntimeError("肌肉曲线 Skin 权重宽度不一致：" + curve)
            c.delete(old)
            skin = c.skinCluster(*(targets + [curve]),
                                 toSelectedBones=True,
                                 maximumInfluences=3, dropoffRate=4,
                                 name=self._name(self._leaf(curve) + "SC"))[0]
            c.setAttr(skin + ".skinningMethod", method)
            for cv, row in zip(cvs, weights):
                sums = {target: 0.0 for target in targets}
                for target, value in zip(mapped, row):
                    sums[target] += float(value)
                c.skinPercent(skin, cv,
                              transformValue=list(sums.items()),
                              normalize=True)
            transferred += 1
        return transferred
    def _mirror_loft(self, group: str, right: tuple[str, ...],
                     left: tuple[str, ...]) -> None:
        from adv_py.core.geometry_muscular import mirrored_name

        c = self.cmds
        stem = self._leaf(group)[:-2]
        source = self._name(stem + "_loft_R")
        target = self._name(stem + "_loft_L")
        duplicate = c.duplicate(source, name=target,
                                returnRootsOnly=True)[0]
        shapes = c.listRelatives(duplicate, shapes=True,
                                 noIntermediate=True,
                                 type="nurbsSurface") or []
        if len(shapes) != 1:
            raise RuntimeError("镜像肌肉缺少唯一的 Loft 曲面：" + target)
        old_nodes = [node for node in (c.listHistory(source) or ())
                     if c.nodeType(node) == "loft"]
        if len(old_nodes) != 1:
            raise RuntimeError("原版肌肉曲面缺少 Loft 节点：" + source)
        node = c.duplicate(old_nodes[0],
                           name=self._name(mirrored_name(stem + "_loft_R")
                                           + "Node"))[0]
        for index, curve in enumerate(left):
            shapes_curve = c.listRelatives(curve, shapes=True,
                                            noIntermediate=True,
                                            type="nurbsCurve") or []
            if len(shapes_curve) != 1:
                raise RuntimeError("镜像肌肉曲线缺少形状：" + curve)
            c.connectAttr(shapes_curve[0] + ".worldSpace[0]",
                          node + f".inputCurve[{index}]", force=True)
        c.connectAttr(node + ".outputSurface",
                      shapes[0] + ".create", force=True)
        count = int(c.getAttr(old_nodes[0] + ".reverse", size=True))
        for index in range(count):
            old = c.getAttr(old_nodes[0] + f".reverse[{index}]")
            c.setAttr(node + f".reverse[{index}]", not old)

    def mirror_muscles(self) -> int:
        from adv_py.core.geometry_muscular import mirrored_name

        c = self.cmds
        self._mirrored_groups.clear()
        for group in self._muscle_groups():
            leaf = self._leaf(group)
            if not leaf.endswith("_R") or "ALT" in leaf:
                continue
            source_loft = self._name(leaf[:-2] + "_loft_R")
            if not c.objExists(source_loft):
                continue
            right = self._curves(group)
            if not right:
                continue
            target = self._name(mirrored_name(leaf))
            if c.objExists(target):
                raise ValueError("左侧肌肉名称已占用：" + target)
            mirror = c.duplicate(group, name=target,
                                 returnRootsOnly=True)[0]
            c.setAttr(mirror + ".scaleX", -1)
            left_unrenamed = self._curves(mirror)
            if len(left_unrenamed) != len(right):
                raise RuntimeError("镜像肌肉曲线数量不匹配：" + leaf)
            left = tuple(c.rename(node, self._name(
                mirrored_name(self._leaf(source))))
                for source, node in zip(right, left_unrenamed))
            c.makeIdentity(mirror, apply=True, translate=True,
                           rotate=True, scale=True)
            for source, target_curve in zip(right, left):
                source_skin = self._curve_skin(source)
                source_joints = c.skinCluster(source_skin, query=True,
                                               influence=True) or []
                targets = []
                for joint in source_joints:
                    name = self._leaf(joint)
                    counterpart = (self._name(mirrored_name(name))
                                   if name.endswith("_R") else joint)
                    if not c.objExists(counterpart):
                        raise ValueError("镜像肌肉缺少对侧骨形：" + counterpart)
                    targets.append(counterpart)
                existing = [node for node in (c.listHistory(target_curve) or ())
                            if c.nodeType(node) == "skinCluster"]
                if existing:
                    c.delete(existing)
                target_skin = c.skinCluster(
                    *(list(dict.fromkeys(targets)) + [target_curve]),
                    toSelectedBones=True, maximumInfluences=3,
                    dropoffRate=4,
                    name=self._name(self._leaf(target_curve) + "SC"))[0]
                c.copySkinWeights(sourceSkin=source_skin,
                                  destinationSkin=target_skin,
                                  mirrorMode="YZ", mirrorInverse=True,
                                  surfaceAssociation="closestPoint",
                                  influenceAssociation="closestJoint")
            self._mirror_loft(group, right, left)
            self._mirrored_groups.append(mirror)
        return len(self._mirrored_groups)
    def finish_muscular(self) -> None:
        import json

        c = self.cmds
        source = self._name("Muscular_Root_M")
        if c.objExists(source):
            c.delete(source)
        root = self._name("MuscularGeometry")
        owned = sorted(set(c.ls(dependencyNodes=True) or ()) - self._before)
        if not c.attributeQuery("advPyCreatedNodes", node=root, exists=True):
            c.addAttr(root, longName="advPyCreatedNodes", dataType="string")
        c.setAttr(root + ".advPyCreatedNodes", json.dumps(owned),
                  type="string")
        c.select(clear=True)

    def capture_muscular(self, curve_count: int, mirror_count: int) -> bool:
        c = self.cmds
        if curve_count <= 0 or mirror_count <= 0:
            return False
        for leaf in ("MuscularGeometry", "NurbsMuscles"):
            if not c.objExists(self._name(leaf)):
                return False
        if len(self._fitted_curves) != curve_count:
            return False
        if len(self._mirrored_groups) != mirror_count:
            return False
        for curve in self._fitted_curves:
            if not c.objExists(curve):
                return False
            if not any(c.nodeType(node) == "skinCluster"
                       for node in (c.listHistory(curve) or ())):
                return False
        return all(c.objExists(group) for group in self._mirrored_groups)

    def muscular_exists(self) -> bool:
        c = self.cmds
        return any(c.objExists(self._name(leaf)) for leaf in (
            "MuscularGeometry", "Muscular_SkeletonGeometry",
            "Muscular_Root_M", "NurbsMuscles"))

    def delete_muscular(self) -> None:
        import json

        c = self.cmds
        root = self._name("MuscularGeometry")
        owned = []
        if c.objExists(root) and c.attributeQuery(
                "advPyCreatedNodes", node=root, exists=True):
            owned = json.loads(c.getAttr(root + ".advPyCreatedNodes") or "[]")
        for leaf in ("MuscularGeometry", "Muscular_SkeletonGeometry",
                     "Muscular_Root_M", "NurbsMuscles"):
            node = self._name(leaf)
            if c.objExists(node):
                c.delete(node)
        for node in reversed(owned):
            if c.objExists(node):
                c.delete(node)

