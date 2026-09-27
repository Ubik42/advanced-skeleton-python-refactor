"""Maya implementation of ADV's template-based Unreal Mannequin workflow."""
from __future__ import annotations

from pathlib import Path

from adv_py.core.unreal_mannequin import JointMatch, MannequinPlan
from .maya_custom_controller import MayaCustomControllerHost


class MayaMannequinHost(MayaCustomControllerHost):
    def __init__(self, *, namespace: str | None = None) -> None:
        super().__init__(namespace=namespace, face=False)
        self._template_pose: dict[str, tuple[float, ...]] = {}

    def _node(self, name: str) -> str:
        return self.scene_address(name)

    def _optional(self, name: str) -> str | None:
        address = self._node(name)
        return self._unique(address, "joint") if self._cmds.objExists(address) else None

    def preflight(self, plan: MannequinPlan, template_path: str) -> None:
        c = self._cmds
        if not Path(template_path).is_file() or Path(template_path).suffix.lower() != ".ma":
            raise FileNotFoundError("请选择 ADV 安装包中的 AdvancedSkeletonFiles/div/asUnreal.ma")
        self._unique("DeformSet", "objectSet")
        self._unique("MainScaleMultiplyDivide", "multiplyDivide")
        if plan.match_template_pose:
            self._unique("ControlSet", "objectSet")
        for name in ("Root_M", "Hip_R", "Knee_R", "Ankle_R"):
            self._unique(name, "joint")
        if c.objExists("|root"):
            raise ValueError("场景根级已存在 root；先删除已有 Mannequin 骨架")
        if c.objExists(self._node("root")):
            root = self._unique("root", "joint")
            parent = (c.listRelatives(root, parent=True,
                                      fullPath=True) or [None])[0]
            if parent != self._unique("DeformationSystem", "transform"):
                raise ValueError("现有 root 关节不在 DeformationSystem 下")
            if c.objExists(self._node("rootUserCreated")):
                raise ValueError("rootUserCreated 名称已占用")
        if plan.scale_adv_to_template:
            self._unique("Main", "transform")

    def import_template(self, plan: MannequinPlan, template_path: str) -> None:
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        before = set(c.ls(long=True) or [])
        existing_root = self._node("root")
        if c.objExists(existing_root):
            c.rename(self._unique("root", "joint"),
                     self._node("rootUserCreated"))
        c.file(str(Path(template_path).resolve()), i=True, type="mayaAscii",
               ignoreVersion=True, mergeNamespacesOnClash=False,
               namespace="__adv_mannequin_import__")
        top = "__adv_mannequin_import__:" + plan.top_node
        if not c.objExists(top):
            raise ValueError("模板中缺少 " + plan.top_node + " 骨架组")
        children = c.listRelatives(top, children=True, fullPath=True) or []
        joints = [child for child in children if c.nodeType(child) == "joint"]
        if not joints:
            raise ValueError("Unreal 模板骨架组下没有关节")
        for joint in joints:
            c.parent(joint, world=True)
        imported = set(c.ls(long=True) or []) - before
        for node in sorted(imported, key=lambda item: item.count("|")):
            if not c.objExists(node) or c.nodeType(node) != "transform":
                continue
            if c.objExists("|root") and (node == "|root" or node.startswith("|root|")):
                continue
            if node.startswith("|__adv_mannequin_import__:"):
                c.delete(node)
        if c.namespace(exists="__adv_mannequin_import__"):
            c.namespace(removeNamespace="__adv_mannequin_import__",
                        mergeNamespaceWithRoot=True)
        root = c.ls("root", type="joint", long=True) or []
        if len(root) != 1 or root[0] != "|root":
            raise ValueError("模板导入后没有得到唯一的场景根级 root")
        c.addAttr(root[0], longName="advPyMannequinTemplate", dataType="string")
        c.setAttr(root[0] + ".advPyMannequinTemplate", plan.template,
                  type="string")

    def fit_scale(self, plan: MannequinPlan) -> None:
        self._require_transaction()
        c = self._cmds
        head_end = self._optional("HeadEnd_M") or self._unique("Head_M", "joint")
        source_height = c.xform(head_end, q=True, ws=True, t=True)[1]
        template_height = c.xform("head", q=True, ws=True, t=True)[1] * 1.085
        if abs(source_height) < 1e-8:
            raise ValueError("ADV 头部高度为零，无法确定 Mannequin 比例")
        ratio = template_height / source_height
        if plan.scale_adv_to_template:
            c.setAttr(self._node("Main") + ".scale", ratio, ratio, ratio,
                      type="double3")
            node = c.createNode("multiplyDivide",
                                name="unrealMannequinSkeletonScaleToMatch")
            c.setAttr(node + ".operation", 2)
            c.connectAttr(self._node("MainScaleMultiplyDivide") + ".output",
                          node + ".input1", force=True)
            c.setAttr(node + ".input2", ratio, ratio, ratio, type="double3")
            c.connectAttr(node + ".output", "root.scale", force=True)
        else:
            c.setAttr("root.scale", 1.0 / ratio, 1.0 / ratio, 1.0 / ratio,
                      type="double3")
            c.makeIdentity("root", apply=True, translate=False, rotate=False,
                           scale=True)
            c.connectAttr(self._node("MainScaleMultiplyDivide") + ".output",
                          "root.scale", force=True)
        for joint in ["root"] + (c.listRelatives("root", allDescendents=True,
                                                  type="joint") or []):
            c.setAttr(joint + ".segmentScaleCompensate", 0)

    def match_spine(self) -> None:
        self._require_transaction()
        c = self._cmds
        spine = [f"spine_{i:02d}" for i in range(1, 99)
                 if c.objExists(f"spine_{i:02d}")]
        if not spine:
            raise ValueError("Mannequin 模板中缺少 spine_01")
        chain = []
        chest = self._node("Chest_M")
        if not c.objExists(chest):
            available = [self._node(f"Spine{i}_M") for i in range(1, 99)
                         if c.objExists(self._node(f"Spine{i}_M"))]
            if not available:
                raise ValueError("ADV Body 缺少 Chest_M 或 SpineN_M")
            chest = available[-1]
        current = self._unique(chest, "joint")
        root = self._unique("Root_M", "joint")
        while current != root:
            chain.append(current)
            current = (c.listRelatives(current, parent=True, fullPath=True) or [None])[0]
            if current is None:
                raise ValueError("Chest_M 不在 Root_M 的关节链下")
        a = c.xform("pelvis", q=True, ws=True, t=True)
        b = c.xform(spine[-1], q=True, ws=True, t=True)
        length = sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
        if length < 1e-8:
            raise ValueError("Mannequin 脊柱长度为零")
        for joint in spine[:-1]:
            pos = c.xform(joint, q=True, ws=True, t=True)
            weight = (sum((x - y) ** 2 for x, y in zip(a, pos)) ** 0.5) / length
            target = [a[k] * (1 - weight) + b[k] * weight for k in range(3)]
            nearest = min(chain, key=lambda item: sum(
                (x - y) ** 2 for x, y in zip(
                    c.xform(item, q=True, ws=True, t=True), target)))
            self.constrain_match(JointMatch(nearest, joint, (180.0, 0.0, 0.0)))

    def capture_template_pose(self, plan: MannequinPlan) -> None:
        self._require_transaction()
        self._template_pose.clear()
        if not plan.match_template_pose:
            return
        c = self._cmds
        joints = ["|root"] + (c.listRelatives(
            "|root", allDescendents=True, type="joint",
            fullPath=True) or [])
        for joint in joints:
            leaf = joint.rsplit("|", 1)[-1]
            self._template_pose[leaf] = tuple(c.xform(
                joint, query=True, worldSpace=True, matrix=True))

    def match_template_pose(self, plan: MannequinPlan) -> None:
        self._require_transaction()
        if not plan.match_template_pose:
            return
        c = self._cmds
        controls = c.sets(self._node("ControlSet"), query=True) or []
        for control in controls:
            if c.attributeQuery("FKIKBlend", node=control, exists=True):
                c.setAttr(control + ".FKIKBlend", 0)
        swinger = self._node("HipSwinger_M")
        if c.objExists(swinger) and c.attributeQuery(
                "stabilize", node=swinger, exists=True):
            c.setAttr(swinger + ".stabilize", 0)
        joints = c.listRelatives("|root", allDescendents=True,
                                 type="joint", fullPath=True) or []
        joints.reverse()
        for joint in joints:
            leaf = joint.rsplit("|", 1)[-1]
            if leaf not in self._template_pose or not c.attributeQuery(
                    "matchJoint", node=joint, exists=True):
                continue
            source = c.getAttr(joint + ".matchJoint")
            source_leaf = source.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            control = self._node("FK" + source_leaf)
            if not c.objExists(control):
                continue
            base = c.createNode("transform")
            child = c.createNode("transform", parent=base)
            pose = c.createNode("transform")
            try:
                c.xform(base, worldSpace=True, matrix=c.xform(
                    joint, query=True, worldSpace=True, matrix=True))
                c.xform(child, worldSpace=True, rotation=c.xform(
                    control, query=True, worldSpace=True, rotation=True))
                c.xform(pose, worldSpace=True,
                        matrix=self._template_pose[leaf])
                c.orientConstraint(pose, base, maintainOffset=False)
                constraint = c.orientConstraint(child, control,
                                                maintainOffset=False)[0]
                c.delete(constraint)
            finally:
                c.delete(base, pose)

    def constrain_match(self, match: JointMatch) -> None:
        self._require_transaction()
        c = self._cmds
        source = (match.source if match.source.startswith("|") else
                  self._optional(match.source))
        if not source and match.source == "Chest_M":
            available = [self._node(f"Spine{i}_M") for i in range(1, 99)
                         if c.objExists(self._node(f"Spine{i}_M"))]
            if available:
                source = self._unique(available[-1], "joint")
        if not source and c.objExists(match.source):
            source = match.source
        target = match.target
        if target == "<last_spine>":
            spine = [f"spine_{i:02d}" for i in range(1, 99)
                     if c.objExists(f"spine_{i:02d}")]
            target = spine[-1] if spine else ""
        if not source or not c.objExists(target):
            return
        c.pointConstraint(source, target, maintainOffset=False)
        orient = c.orientConstraint(source, target,
                                    maintainOffset=match.maintain_orientation)[0]
        if not match.maintain_orientation:
            c.setAttr(orient + ".offset", *match.offset, type="double3")
        if c.objExists(source + ".scale") and not c.isConnected(
                source + ".scale", target + ".scale"):
            c.connectAttr(source + ".scale", target + ".scale", force=True)
        c.setAttr(target + ".segmentScaleCompensate",
                  c.getAttr(source + ".segmentScaleCompensate"))
        if not c.attributeQuery("matchJoint", node=target, exists=True):
            c.addAttr(target, longName="matchJoint", dataType="string")
        c.setAttr(target + ".matchJoint", source, type="string")

    def copy_custom_joints(self) -> None:
        self._require_transaction()
        c = self._cmds
        members = c.sets(self._node("DeformSet"), query=True) or []
        manual = self._node("manuallyAddedJoints")
        if c.objExists(manual):
            members += c.sets(manual, query=True) or []
        for source in members:
            if not c.objExists(source) or c.nodeType(source) != "joint":
                continue
            leaf = source.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if "Part" in leaf or "Cup_" in leaf:
                continue
            if not c.listRelatives(source, children=True, type="joint") and "Slider" not in leaf:
                continue
            if any(c.nodeType(node) == "constraint" for node in
                   c.listConnections(source, source=False, destination=True) or []):
                continue
            name = "unreal" + leaf
            if c.objExists(name):
                raise ValueError("自定义 Unreal 关节名称已占用：" + name)
            duplicate = c.duplicate(source, parentOnly=True, name=name)[0]
            parent = (c.listRelatives(source, parent=True, fullPath=True) or [None])[0]
            target_parent = None
            if parent:
                parent_leaf = parent.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                if c.objExists("unreal" + parent_leaf):
                    target_parent = "unreal" + parent_leaf
                else:
                    links = c.listConnections(parent, source=False,
                                              destination=True, type="constraint") or []
                    for link in links:
                        targets = c.listConnections(link, source=False,
                                                    destination=True, type="joint") or []
                        target_parent = next((item for item in targets
                                              if item.startswith("root|") or
                                              item.startswith("|root|")), None)
                        if target_parent:
                            break
            c.parent(duplicate, target_parent or "root", absolute=True)
            self.constrain_match(JointMatch(source, duplicate))

    def copy_face_joints(self) -> None:
        self._require_transaction()
        c = self._cmds
        root = self._optional("FaceJoint_M")
        if not root:
            return
        duplicate = c.duplicate(root, returnRootsOnly=True,
                                name="unrealFaceJoint_M")[0]
        c.parent(duplicate, "head", absolute=True)
        descendants = c.listRelatives(duplicate, allDescendents=True,
                                      type="joint", fullPath=True) or []
        for joint in descendants:
            leaf = joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if not leaf.startswith("unreal"):
                c.rename(joint, "unreal" + leaf)
        for source in [root] + (c.listRelatives(root, allDescendents=True,
                                                type="joint", fullPath=True) or []):
            leaf = source.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            target = "unreal" + leaf
            if c.objExists(target):
                c.parentConstraint(source, target, maintainOffset=False)
                c.scaleConstraint(source, target, maintainOffset=False)

    def has_mannequin(self) -> bool:
        return bool(self._cmds.objExists("|root") and
                    self._cmds.objExists("|root|pelvis") and
                    self._cmds.attributeQuery("advPyMannequinTemplate",
                                              node="|root", exists=True))

    def transfer_skin(self) -> int:
        self._require_transaction()
        c = self._cmds
        if c.objExists("|Geometry"):
            raise ValueError("场景已有根级 Geometry，无法安全转移蒙皮")
        geometry = c.createNode("transform", name="Geometry")
        joints = ["root", "pelvis"] + (c.listRelatives(
            "pelvis", allDescendents=True, type="joint") or [])
        count = 0
        seen = set()
        for cluster in c.ls(type="skinCluster") or []:
            face_set = self._node("FaceAllSet")
            if c.objExists(face_set) and c.sets(cluster, isMember=face_set):
                continue
            for shape in c.skinCluster(cluster, query=True, geometry=True) or []:
                if c.nodeType(shape) != "mesh" or c.getAttr(shape + ".intermediateObject"):
                    continue
                source = (c.listRelatives(shape, parent=True, fullPath=True) or [None])[0]
                if not source or source in seen:
                    continue
                seen.add(source)
                duplicate = c.duplicate(source, returnRootsOnly=True)[0]
                for old in c.listRelatives(duplicate, shapes=True,
                                            fullPath=True) or []:
                    if c.getAttr(old + ".intermediateObject"):
                        c.delete(old)
                c.parent(duplicate, geometry, absolute=True)
                target_skin = c.skinCluster(joints, duplicate, bindMethod=0,
                                            maximumInfluences=3,
                                            dropoffRate=4)[0]
                c.copySkinWeights(sourceSkin=cluster,
                                  destinationSkin=target_skin,
                                  noMirror=True, surfaceAssociation="closestPoint",
                                  influenceAssociation="closestJoint")
                self._copy_face_blend_shapes(source, duplicate, cluster)
                count += 1
        if count == 0:
            c.delete(geometry)
            raise ValueError("没有可转移的蒙皮网格")
        return count

    def _copy_face_blend_shapes(self, source: str, target: str,
                                skin_cluster: str) -> None:
        """Carry the ADV face target layer across the copied skin geometry."""
        c = self._cmds
        history = c.listHistory(skin_cluster, pruneDagObjects=True) or []
        face_blend = next((node for node in history
                           if c.nodeType(node) == "blendShape" and
                           "asFaceBS" in node), None)
        if not face_blend:
            return
        indices = c.getAttr(face_blend + ".weight", multiIndices=True) or []
        if not indices:
            return
        new_blend = c.blendShape(target, frontOfChain=True,
                                 name="uem" + face_blend.rsplit(":", 1)[-1])[0]
        aliases = dict(zip(*[iter(c.aliasAttr(face_blend, query=True) or [])] * 2))
        for index in indices:
            source_plug = f"{face_blend}.weight[{index}]"
            driver = (c.listConnections(source_plug, source=True,
                                         destination=False, plugs=True) or [None])[0]
            old_weight = c.getAttr(source_plug)
            try:
                if driver:
                    c.disconnectAttr(driver, source_plug)
                c.setAttr(source_plug, 1)
                shape = c.duplicate(source, returnRootsOnly=True)[0]
                c.setAttr(source_plug, 0)
                c.blendShape(new_blend, edit=True,
                             target=(target, index, shape, 1.0))
                alias = next((name for name, plug in aliases.items()
                              if plug == f"weight[{index}]"), None)
                if alias:
                    c.aliasAttr(alias, f"{new_blend}.weight[{index}]")
                c.delete(shape)
                if driver:
                    c.connectAttr(driver, f"{new_blend}.weight[{index}]",
                                  force=True)
            finally:
                c.setAttr(source_plug, old_weight)
                if driver and not c.isConnected(driver, source_plug):
                    c.connectAttr(driver, source_plug, force=True)

    def hide_original_geometry(self) -> None:
        self._require_transaction()
        c = self._cmds
        group = self._node("Group")
        original = group + "|" + self._node("Geometry")
        if c.objExists(original):
            if c.objExists(self._node("Geometry_original")):
                raise ValueError("Geometry_original 已存在")
            old = c.rename(original, self._node("Geometry_original"))
            c.setAttr(old + ".visibility", False)

    def delete_mannequin(self) -> None:
        self._require_transaction()
        c = self._cmds
        if not self.has_mannequin():
            raise ValueError("场景中没有本工具创建的 Mannequin 骨架")
        for node in ("|Geometry", "|root", "unrealMannequinSkeletonScaleToMatch"):
            if c.objExists(node):
                c.delete(node)
        user_root = self._node("rootUserCreated")
        if c.objExists(user_root):
            c.rename(self._unique(user_root, "joint"), self._node("root"))
        original = self._node("Geometry_original")
        if c.objExists(original):
            restored = c.rename(original, self._node("Geometry"))
            c.setAttr(restored + ".visibility", True)
        main = self._node("Main")
        if c.objExists(main):
            c.setAttr(main + ".scale", 1, 1, 1, type="double3")
