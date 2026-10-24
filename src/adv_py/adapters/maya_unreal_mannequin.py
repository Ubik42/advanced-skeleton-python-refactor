"""Maya implementation of ADV's template-based Unreal Mannequin workflow."""
from __future__ import annotations

from pathlib import Path
from fnmatch import fnmatchcase
from math import dist

from adv_py.core.unreal_mannequin import JointMatch, MannequinPlan, native_orient_offset, RESERVED_DESTINATIONS
from .maya_original_control_identity import source_main, source_control_from_role
from .maya_custom_controller import MayaCustomControllerHost
from .maya_unreal_mannequin_export import MayaMannequinExportMixin


class MayaMannequinHost(MayaMannequinExportMixin, MayaCustomControllerHost):
    def __init__(self, *, namespace: str | None = None,
                 ctrl_button: bool | None = None) -> None:
        if ctrl_button is not None and type(ctrl_button) is not bool:
            raise ValueError('Mannequin Ctrl 状态必须是布尔值')
        super().__init__(namespace=namespace, face=False)
        self._main_scale = 1.0
        self._mannequin_ctrl_button = False
        self._mannequin_ctrl_button_override = ctrl_button

    def _mannequin_cmds(self):
        # ADV is character-scoped; the native export asset lives at scene root.
        return self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds

    def _node(self, name: str) -> str:
        return self.scene_address(name)

    def _optional(self, name: str) -> str | None:
        address = self._node(name)
        return self._unique(address, "joint") if self._cmds.objExists(address) else None

    def preflight_mannequin_creation(self, plan, template_path):
        c = self._mannequin_cmds()
        self._capture_mannequin_modifiers()
        if not Path(template_path).is_file() or Path(template_path).suffix.lower() != '.ma':
            raise FileNotFoundError('请选择原版 asUnreal.ma 模板')
        self._unique('DeformSet', 'objectSet')
        if c.objExists('|root'):
            raise ValueError('场景根级已存在 root；先删除已有 Mannequin 骨架')

    def preflight(self, plan: MannequinPlan, template_path: str) -> None:
        c = self._mannequin_cmds()
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
        for target in RESERVED_DESTINATIONS:
            if c.objExists(target):
                raise ValueError('Mannequin 目标名称已占用：' + target)
        if c.objExists(self._node("root")):
            root = self._unique("root", "joint")
            parent = (c.listRelatives(root, parent=True,
                                      fullPath=True) or [None])[0]
            if parent != self._unique("DeformationSystem", "transform"):
                raise ValueError("现有 root 关节不在 DeformationSystem 下")
            if c.objExists(self._node("rootUserCreated")):
                raise ValueError("rootUserCreated 名称已占用")
        if plan.scale_adv_to_template:
            source_main(self)

    def import_template(self, plan: MannequinPlan, template_path: str) -> None:
        self._require_transaction()
        self._transaction_changed = True
        c = self._mannequin_cmds()
        from .maya_game_registration import source_registration
        self._mannequin_registration = source_registration(self)
        if self._mannequin_registration is not None:
            self._mannequin_registration = self.read_character_registration()
        before = set(c.ls(assemblies=True, long=True) or [])
        existing_root = self._node("root")
        if c.objExists(existing_root):
            c.rename(self._unique("root", "joint"), self._node("rootUserCreated"))
        c.file(str(Path(template_path).resolve()), i=True, type="mayaAscii",
               ignoreVersion=True, mergeNamespacesOnClash=False,
               namespace="__adv_mannequin_import__")
        top = "__adv_mannequin_import__:" + plan.top_node
        if not c.objExists(top):
            raise ValueError("模板中缺少 " + plan.top_node + " 骨架组")
        children = c.listRelatives(top, children=True, fullPath=True) or []
        if not any(c.nodeType(child) == "joint" for child in children):
            raise ValueError("Unreal 模板骨架组下没有关节")
        promoted = c.parent(children, world=True) or []
        kept = set(c.ls(promoted, long=True) or [])
        imported = set(c.ls(assemblies=True, long=True) or []) - before - kept
        if imported:
            c.delete(sorted(imported))
        c.namespace(removeNamespace="__adv_mannequin_import__",
                    mergeNamespaceWithRoot=True)
        root = c.ls("root", type="joint", long=True) or []
        root = [path for path in root if path == "|root"]
        if len(root) != 1:
            raise ValueError("模板导入后没有得到唯一的场景根级 root")
        c.addAttr(root[0], longName="advPyMannequinTemplate", dataType="string")
        c.setAttr(root[0] + ".advPyMannequinTemplate", plan.template,
                  type="string")

    def fit_scale(self, plan: MannequinPlan) -> None:
        self._require_transaction()
        c = self._mannequin_cmds()
        head_end = self._optional("HeadEnd_M") or self._unique("Head_M", "joint")
        source_height = c.xform(head_end, q=True, ws=True, t=True)[1]
        template_height = c.xform("head", q=True, ws=True, t=True)[1] * 1.085
        if source_height == 0:
            raise ValueError("ADV 头部高度为零，无法确定 Mannequin 比例")
        ratio = template_height / source_height
        self._main_scale = ratio
        if plan.scale_adv_to_template:
            c.setAttr(source_main(self) + ".scale", ratio, ratio, ratio,
                      type="double3")
        else:
            c.setAttr("|root.scale", 1.0 / ratio, 1.0 / ratio, 1.0 / ratio,
                      type="double3")
            c.makeIdentity("|root", apply=True, translate=False, rotate=False,
                           scale=True)

    def connect_root_scale(self, plan: MannequinPlan) -> None:
        """Native override follows rootUserCreated and pelvis constraints."""
        self._require_transaction()
        c = self._mannequin_cmds()
        source = self._node("MainScaleMultiplyDivide") + ".output"
        if plan.scale_adv_to_template:
            name = "unrealMannequinSkeletonScaleToMatch"
            if c.objExists(name):
                c.delete(name)
            node = c.createNode("multiplyDivide", name=name)
            c.setAttr(node + ".operation", 2)
            c.connectAttr(source, node + ".input1")
            c.setAttr(node + ".input2", self._main_scale, self._main_scale,
                      self._main_scale, type="double3")
            source = node + ".output"
        c.connectAttr(source, "|root.scale", force=True)

    def _spine_joints(self) -> list[str]:
        c = self._mannequin_cmds()
        joints = []
        for index in range(1, 99):
            name = "spine_0" + str(index)
            if not c.objExists(name):
                break
            joints.append(name)
        return joints

    def _chest_joint(self) -> str:
        if self._cmds.objExists("Chest_M"):
            return self._unique("Chest_M", "joint")
        last = None
        for index in range(1, 99):
            name = "Spine" + str(index) + "_M"
            if not self._cmds.objExists(name):
                break
            last = name
        if last is None:
            raise ValueError("ADV Body 缺少 Chest_M 或连续的 SpineN_M")
        return self._unique(last, "joint")

    def match_spine(self) -> None:
        self._require_transaction()
        c = self._mannequin_cmds()
        spine = self._spine_joints()
        if not spine:
            raise ValueError("Mannequin 模板中缺少 spine_01")
        chest = self._chest_joint()
        root = self._unique("Root_M", "joint")
        pelvis = c.xform("pelvis", q=True, ws=True, t=True)
        top = c.xform(spine[-1], q=True, ws=True, t=True)
        length = dist(pelvis, top)
        if length == 0:
            raise ValueError("Mannequin 脊柱长度为零")
        factors = [dist(pelvis, c.xform(joint, q=True, ws=True, t=True)) / length
                   for joint in spine[:-1]]
        for joint, weight in zip(spine[:-1], factors):
            c.pointConstraint(chest, joint, weight=weight)
            c.pointConstraint(root, joint, weight=1 - weight)
            c.delete(joint + "_pointConstraint1")
        chain = []
        current = chest
        while current != root:
            chain.append(current)
            current = (c.listRelatives(current, parent=True, fullPath=True) or [None])[0]
            if current is None:
                raise ValueError("Chest_M 不在 Root_M 的关节链下")
        nearest = None
        for joint in spine[:-1]:
            pos = c.xform(joint, q=True, ws=True, t=True)
            minimum = 999.0
            for candidate in chain:
                distance = dist(pos, c.xform(candidate, q=True, ws=True, t=True))
                if distance < minimum:
                    minimum = distance
                    nearest = candidate
            if nearest is None:
                raise ValueError("原版脊柱匹配没有找到 999 单位以内的关节")
            self.constrain_match(JointMatch(nearest, joint, (180.0, 0.0, 0.0)))

    def capture_template_pose(self, plan: MannequinPlan) -> None:
        self._require_transaction()
        c = self._mannequin_cmds()
        # Keep the source's actual reference hierarchy. A table of world
        # matrices loses the native joint frame and parent/scale behavior used
        # by the orientConstraint pass below (MEL 60241–60250).
        if plan.match_template_pose:
            if c.namespace(exists='MannequinPose'):
                previous = c.ls('MannequinPose:*') or []
                if previous:
                    c.delete(previous)
            else:
                c.namespace(addNamespace='MannequinPose')
            try:
                c.namespace(setNamespace='MannequinPose')
                c.duplicate('|root')
                c.setAttr('MannequinPose:root.visibility', 0)
            finally:
                c.namespace(setNamespace=':')
        # Native disables SSC on the export skeleton AFTER duplicating its
        # pose reference. makeIdentity can have enabled it on the template.
        for joint in c.listRelatives('|root', allDescendents=True, type='joint') or []:
            c.setAttr(joint + '.segmentScaleCompensate', 0)
        c.setAttr('|root.segmentScaleCompensate', 0)

    def match_template_pose(self, plan: MannequinPlan) -> None:
        self._require_transaction()
        if not plan.match_template_pose:
            return
        c = self._mannequin_cmds()
        from .maya_original_transform_channels import align_original_transform
        controls = c.sets(self._node("ControlSet"), query=True) or []
        for control in controls:
            if c.attributeQuery("FKIKBlend", node=control, exists=True):
                c.setAttr(control + ".FKIKBlend", 0)
        from .maya_original_control_identity import registration
        saved = registration(self)
        if saved is not None:
            channels = {channel.key: channel for channel in saved.channels}
            for limb in saved.source_limbs:
                channel = channels[limb.blend_key]
                c.setAttr(self._node(channel.node) + '.' + channel.attribute, 0)
        swinger = self._node("HipSwinger_M")
        if c.objExists(swinger) and c.attributeQuery(
                "stabilize", node=swinger, exists=True):
            c.setAttr(swinger + ".stabilize", 0)
        joints = c.listRelatives("|root", allDescendents=True,
                                 type="joint", fullPath=True) or []
        joints.reverse()
        for joint in joints:
            leaf = joint.rsplit("|", 1)[-1]
            reference = 'MannequinPose:' + leaf
            if not c.objExists(reference) or not c.attributeQuery(
                    "matchJoint", node=joint, exists=True):
                continue
            source = c.getAttr(joint + ".matchJoint")
            source_leaf = source.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            # Only an actual FK controller may receive the pose. Unreal's
            # own hand/foot marker sources are joints, with no FK controller;
            # falling back to the joint writes into the constrained export rig.
            control = self._node(source_control_from_role(self, 'FK' + source_leaf))
            if not c.objExists(control):
                continue
            for temporary in ('tempTransform1', 'tempTransform2'):
                if c.objExists(temporary):
                    c.delete(temporary)
            base = c.createNode('transform', name='tempTransform1')
            child = c.createNode('transform', name='tempTransform2', parent=base)
            try:
                align_original_transform(c, base, joint, True, True, False, False)
                # base has moved, so child must be addressed by its current
                # short name rather than the path returned at creation.
                child = 'tempTransform2'
                align_original_transform(c, child, control, False, True, False, False)
                c.orientConstraint(reference, base, maintainOffset=False)
                constraint = c.orientConstraint(child, control,
                                                maintainOffset=False)[0]
                c.delete(constraint)
            finally:
                if c.objExists(base):
                    c.delete(base)
        if not self._mannequin_ctrl_button and c.objExists('MannequinPose:root'):
            c.delete('MannequinPose:root')

    def constrain_match(self, match: JointMatch) -> None:
        self._require_transaction()
        c = self._mannequin_cmds()
        source = (match.source if match.source.startswith("|") else
                  self._optional(match.source))
        if not source and match.source == "Chest_M":
            source = self._chest_joint()
        if not source and c.objExists(match.source):
            source = match.source
        target = match.target
        if target == "<last_spine>":
            spine = self._spine_joints()
            target = spine[-1] if spine else ""
        if not source or not c.objExists(target):
            return
        c.pointConstraint(source, target, maintainOffset=match.maintain_position)
        orient = c.orientConstraint(source, target,
                                    maintainOffset=match.maintain_orientation)[0]
        if not match.maintain_orientation:
            c.setAttr(orient + ".offset", *match.offset, type="double3")
        c.connectAttr(source + ".scale", target + ".scale")
        c.setAttr(target + ".segmentScaleCompensate",
                  c.getAttr(source + ".segmentScaleCompensate"))
        c.addAttr(target, longName="matchJoint", dataType="string")
        c.setAttr(target + ".matchJoint", source, type="string")
        constraint = target.rsplit("|", 1)[-1] + "_orientConstraint1"
        for axis in "XYZ":
            rotation = c.getAttr(target + ".rotate" + axis)
            plug = constraint + ".offset" + axis
            offset = c.getAttr(plug)
            adjusted = native_orient_offset(rotation, offset)
            if adjusted != offset:
                c.setAttr(plug, adjusted)

    def _export_constraints(self, source: str) -> tuple[str, ...]:
        c = self._mannequin_cmds()
        constraints = c.listConnections(source, source=False, destination=True,
                                        type="constraint") or []
        return tuple(node for node in constraints
                     if any(path.startswith("|root|")
                            for path in c.ls(node, long=True) or []))

    def copy_custom_joints(self) -> None:
        self._require_transaction()
        c = self._mannequin_cmds()
        deform_set = self._node("DeformSet")
        members = c.sets(deform_set, query=True) or []
        manual = self._node("manuallyAddedJoints")
        if c.objExists(manual):
            members += c.sets(manual, query=True) or []
        pending = []
        for source in members:
            if not c.objExists(source) or c.nodeType(source) != "joint":
                continue
            leaf = source.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if fnmatchcase(leaf, "*Part[0-9]*") or fnmatchcase(leaf, "*Cup_*"):
                continue
            if not c.listRelatives(source, children=True, type="joint") and "Slider" not in leaf:
                inputs = c.listConnections(source, source=True, destination=False) or []
                if not inputs or inputs[0] == source:
                    continue
            if self._export_constraints(source):
                continue
            pending.append((source, "unreal" + leaf))
        # Every duplicate exists before deciding any duplicate's parent. The
        # original DeformSet order is not a topological sorting contract.
        for source, name in pending:
            duplicate = c.duplicate(source)[0]
            duplicate = c.rename(duplicate, ":" + name)
            c.sets(duplicate, remove=deform_set)
            c.sets(duplicate, remove=self._node("AllSet"))
            duplicate = c.parent(duplicate, world=True)[0]
            children = c.listRelatives(duplicate, children=True, fullPath=True) or []
            if children:
                c.delete(children)
            parent = (c.listRelatives(duplicate, parent=True, fullPath=True) or [None])[0]
            if parent and fnmatchcase(parent.rsplit("|", 1)[-1], "transform*"):
                c.makeIdentity(parent, apply=True, translate=True, rotate=True, scale=True)
                c.parent(duplicate, world=True)
                c.delete(parent)
        for source, name in pending:
            parent = (c.listRelatives(source, parent=True, fullPath=True) or [None])[0]
            if parent:
                parent_leaf = parent.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                if c.objExists("unreal" + parent_leaf):
                    c.parent(name, "unreal" + parent_leaf)
                else:
                    for constraint in self._export_constraints(parent):
                        targets = c.listConnections(constraint, source=False,
                                                    destination=True, type="joint") or []
                        if targets:
                            c.parent(name, targets[0])
                            break
            self.constrain_match(JointMatch(source, name))

    def copy_face_joints(self) -> None:
        self._require_transaction()
        c = self._mannequin_cmds()
        root = self._optional("FaceJoint_M")
        if not root:
            return
        duplicate = c.duplicate(root, name=":unrealFaceJoint_M")[0]
        descendants = c.listRelatives(duplicate, allDescendents=True,
                                      fullPath=True) or []
        for node in descendants:
            leaf = node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            c.rename(node, ":unreal" + leaf)
        duplicate = c.parent(duplicate, "head")[0]
        parent = (c.listRelatives(duplicate, parent=True, fullPath=True) or [None])[0]
        if parent and fnmatchcase(parent.rsplit("|", 1)[-1], "transform*"):
            c.rename(parent, ":FaceScaler")
        for source in c.listRelatives(root, allDescendents=True, fullPath=True) or []:
            leaf = source.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            target = "unreal" + leaf
            if c.objExists(target):
                c.parentConstraint(source, target)
                c.scaleConstraint(source, target)

    def finish_mannequin(self) -> None:
        """Final source passes: disable SSC, then remove the export prefix."""
        self._require_transaction()
        c = self._mannequin_cmds()
        joints = c.listRelatives("|root", allDescendents=True, type="joint",
                                 fullPath=True) or []
        for joint in [*joints, "|root"]:
            c.setAttr(joint + ".segmentScaleCompensate", 0)
        from .maya_original_game_skeleton import _remove_python_build_metadata
        for joint in joints:
            _remove_python_build_metadata(c, joint)
        # Native descendant order renames children before their ancestors.
        for joint in joints:
            name = joint.rsplit("|", 1)[-1]
            if name.startswith("unreal"):
                c.rename(joint, name.removeprefix("unreal"))
        before = getattr(self, "_mannequin_registration", None)
        if before is not None:
            from .maya_game_registration import refresh_hierarchy
            refresh_hierarchy(self, before)

    def has_mannequin(self) -> bool:
        c = self._mannequin_cmds()
        return bool(c.objExists('|root') and c.objExists('|root|pelvis'))

    def transfer_skin(self) -> int:
        self._require_transaction()
        c = self._mannequin_cmds()
        if c.objExists("|Geometry"):
            raise ValueError("场景已有根级 Geometry，无法转移蒙皮")
        setup = c.createNode("transform", name="unrealMannequinSkinTransferSetup")
        c.createNode("transform", name="uemTransformGeometryXform", parent=setup)
        geometry = c.createNode("transform", name="Geometry")
        joints = ["root", "pelvis"] + (c.listRelatives(
            "pelvis", allDescendents=True, type="joint", fullPath=True) or [])
        count = 0
        # Native enumerates all SkinClusters once and chooses the first forward
        # history mesh. The commented FaceAllSet skip is not active in 6.925.
        clusters = tuple(c.ls(type="skinCluster") or [])
        try:
            for cluster in clusters:
                history = c.listHistory(cluster, pruneDagObjects=False,
                                        interestLevel=2, future=True) or []
                shape = next((node for node in history if c.nodeType(node) == "mesh"), None)
                if shape is None or c.getAttr(shape + ".intermediateObject"):
                    continue
                source = (c.listRelatives(shape, parent=True, fullPath=True) or [None])[0]
                if source is None:
                    continue
                c.showHidden(source, above=True)
                duplicate = c.duplicate(source)[0]
                if len(c.ls(duplicate) or []) > 1:
                    parent = (c.listRelatives(source, parent=True, fullPath=True) or [None])[0]
                    duplicate = c.rename(parent + "|" + duplicate,
                                         "unreal" + duplicate.rsplit("|", 1)[-1])
                for old in c.listRelatives(duplicate, shapes=True, fullPath=True) or []:
                    if c.getAttr(old + ".intermediateObject"):
                        c.delete(old)
                duplicate = c.parent(duplicate, geometry)[0]
                from .maya_original_skin_history import new_original_skin_clusters
                c.select(duplicate, joints, replace=True)
                new_original_skin_clusters(commands=c, namespace='', maximum_influences=3)
                # Native copySkinWeights chooses the SkinCluster from the
                # selected source/target transforms. Selecting the iterated
                # cluster explicitly changes the result for layered Face skin.
                c.select(source, duplicate, replace=True)
                c.copySkinWeights(noMirror=True, surfaceAssociation="closestPoint",
                                  influenceAssociation="closestJoint")
                self._copy_face_blend_shapes(source, duplicate, cluster)
                count += 1
        finally:
            c.delete(setup)
        c.select(clear=True)
        return count

    def _copy_face_blend_shapes(self, source: str, target: str,
                                skin_cluster: str) -> None:
        """Carry the ADV face target layer across the copied skin geometry."""
        c = self._mannequin_cmds()
        history = c.listHistory(skin_cluster, pruneDagObjects=True, interestLevel=1) or []
        face_blend = next((node for node in history
                           if c.nodeType(node) == "blendShape" and
                           "asFaceBS" in node), None)
        if not face_blend:
            return
        targets = c.listAttr(face_blend + ".weight", multi=True) or []
        if targets and targets[0].startswith('.'):
            targets = [alias[1:] if alias.startswith('.') else alias for alias in targets]
        if not targets:
            return
        from .maya_original_blend_shape import original_front_of_chain_blend_shape
        c.select(target, replace=True)
        new_blend = original_front_of_chain_blend_shape(c,
            name="uem" + face_blend.rsplit(":", 1)[-1])
        for index, alias in enumerate(targets):
            source_plug = face_blend + "." + alias
            driver = (c.listConnections(source_plug, source=True,
                                         destination=False, plugs=True) or [None])[0]
            shape = None
            try:
                if driver:
                    c.disconnectAttr(driver, source_plug)
                c.setAttr(source_plug, 1)
                shape = c.duplicate(source, name=alias)[0]
                c.setAttr(source_plug, 0)
                if driver:
                    c.connectAttr(driver, source_plug)
                c.blendShape(new_blend, edit=True,
                             target=(target, index, shape, 1.0))
                if (not alias.startswith("weight[")
                        and c.aliasAttr(f"{new_blend}.weight[{index}]", query=True) != alias):
                    c.aliasAttr(alias, f"{new_blend}.weight[{index}]")
                c.delete(shape)
                shape = None
                if driver:
                    c.connectAttr(driver, f"{new_blend}.weight[{index}]")
            finally:
                # The normal pass already restored the native driver. A
                # second setAttr would fail on its now-connected target.
                # Only repair an interrupted disconnected source here.
                if not driver or not c.isConnected(driver, source_plug):
                    c.setAttr(source_plug, 0)
                    if driver:
                        c.connectAttr(driver, source_plug)
                if shape is not None and c.objExists(shape):
                    c.delete(shape)

    def hide_original_geometry(self) -> None:
        self._require_transaction()
        c = self._mannequin_cmds()
        group = self._node("Group")
        original = group + "|" + self._node("Geometry")
        if not c.objExists(original):
            raise ValueError('原版 Group|Geometry 不存在，无法隐藏原始几何')
        if c.objExists(self._node("Geometry_original")):
            raise ValueError("Geometry_original 已存在")
        old = c.rename(original, self._node("Geometry_original"))
        c.setAttr(old + ".visibility", False)

    def delete_mannequin(self) -> None:
        self._require_transaction()
        c = self._mannequin_cmds()
        from .maya_game_registration import source_registration, refresh_hierarchy
        before = source_registration(self)
        for node in ("|Geometry", "|root"):
            if c.objExists(node):
                c.delete(node)
        user_root = self._node("rootUserCreated")
        if c.objExists(user_root):
            c.rename(self._unique(user_root, "joint"), self._node("root"))
        original = self._node("Geometry_original")
        if c.objExists(original):
            restored = c.rename(original, self._node("Geometry"))
            c.setAttr(restored + ".visibility", True)
        if before is not None:
            refresh_hierarchy(self, before)
        pose = self.read_body_build_pose()
        self.preflight_body_build_pose(pose)
        self.apply_body_build_pose(pose)



def retained_roots(host, registration):
    """Retain only the native Mannequin asset actually driven by this Body."""
    c = getattr(host._cmds, 'raw', host._cmds)
    # Native MEL-created Mannequins have no Python marker. Ownership comes
    # from the actual pelvis constraint targeting this registered Body root.
    if not c.objExists('|root') or not c.objExists('|root|pelvis'):
        return ()
    body_uuid = next(row.uuid for row in registration.nodes if row.path == registration.body_root)
    constraints = c.listConnections('|root|pelvis.translateX', source=True,
                                    destination=False, type='pointConstraint') or []
    driven_here = False
    for constraint in constraints:
        for joint in c.listConnections(constraint + '.target[0].targetParentMatrix',
                                       source=True, destination=False, type='joint') or []:
            if (c.ls(joint, uuid=True) or []) == [body_uuid]:
                driven_here = True
    if not driven_here:
        return ()
    roots = ['|root']
    scale = 'unrealMannequinSkeletonScaleToMatch'
    if c.objExists(scale) and c.isConnected(scale + '.output', '|root.scale'):
        roots.append(scale)
    if c.objExists('|Geometry'):
        joints = ['|root', *(c.listRelatives('|root', allDescendents=True,
                                           type='joint', fullPath=True) or [])]
        ids = {identity for joint in joints for identity in c.ls(joint, uuid=True) or []}
        for shape in c.listRelatives('|Geometry', allDescendents=True,
                                     type='mesh', fullPath=True) or []:
            clusters = [node for node in c.listHistory(shape) or [] if c.nodeType(node) == 'skinCluster']
            influences = [joint for cluster in clusters for joint in c.skinCluster(cluster, query=True, influence=True) or []]
            if any(identity in ids for joint in influences for identity in c.ls(joint, uuid=True) or []):
                roots.append('|Geometry')
                break
    return tuple(host._cmds.identity.to_local(node) if hasattr(host._cmds, 'identity') else node for node in roots)
