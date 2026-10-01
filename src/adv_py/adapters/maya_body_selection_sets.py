"""Maya selection sets shared by Body skinning and custom controls."""
from __future__ import annotations

import json
import re

from adv_py.core.body_selection_sets import BodySelectionSetsPlan
from adv_py.core.body_all_set import BodyAllSetNode, BodyAllSetPlan
from adv_py.core.character_identity import CharacterIdentity
from adv_py.core.character_registry import CharacterRegistration


class MayaBodySelectionSetsMixin:
    def capture_body_rebuild_selection_members(self):
        """Preserve authored ControlSet/DeformSet membership by logical role."""
        c=self._cmds
        rows=[]
        for name in ('ControlSet','DeformSet'):
            if not c.objExists(name):continue
            members=set()
            for member in c.sets(name,q=True) or []:
                paths=c.ls(member,long=True,flatten=True) or []
                if not paths:
                    raise RuntimeError('重建选择集成员不存在：'+member)
                members.update(paths)
            rows.append((name,tuple(sorted(members))))
        return tuple(rows)

    def restore_body_rebuild_selection_members(self,rows):
        self._require_transaction()
        c=self._cmds
        for name,members in rows:
            if name not in ('ControlSet','DeformSet') or not c.objExists(name):
                raise RuntimeError('重建选择集目标不存在：'+name)
            # User-added controls/joints are retained native objects. They
            # join the stage during the later explicit extension handoff.
            identity=CharacterIdentity(self.namespace or '')
            generated=tuple(member for member in members
                            if identity.owns(self.scene_address(member)) and c.objExists(member))
            self._transaction_changed=True
            c.sets(clear=name)
            if generated:c.sets(generated,addElement=name)
            expected=tuple(sorted(generated))
            actual=dict(self.capture_body_rebuild_selection_members())[name]
            if actual!=expected:
                raise RuntimeError('重建选择集成员没有完整恢复：'+name)

    def capture_body_rebuild_selection_mode(self) -> str:
        """Retain the source character's pre-selection-set layout."""
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        names = ("ControlSet", "DeformSet", "AllSet", "Sets")
        present = tuple(c.objExists(self._body_selection_set_address(name))
                        for name in names)
        pose = self.scene_address("|Group|MotionSystem|buildPose")
        pose_present = bool(c.objExists(pose))
        if not any(present) and not pose_present:
            return "none"
        if not all(present) or not pose_present:
            raise RuntimeError("原角色选择集或 buildPose 层级不完整")
        if any(c.nodeType(self._body_selection_set_address(name)) != "objectSet"
               for name in names) or c.nodeType(pose) != "transform":
            raise RuntimeError("原角色选择集或 buildPose 节点类型无效")
        all_set = self._body_selection_set_address("AllSet")
        return "populated" if c.sets(all_set, query=True) else "empty"

    def capture_body_scene_nodes(self) -> tuple[BodyAllSetNode, ...]:
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        identity = CharacterIdentity(self.namespace or "")
        nodes = []
        for path in c.ls(long=True) or []:
            if not identity.owns(path):
                continue
            uuids = c.ls(path, uuid=True) or []
            if len(uuids) != 1:
                raise RuntimeError("角色节点身份不唯一：" + path)
            nodes.append(BodyAllSetNode(
                identity.to_local(path), c.nodeType(path),
                bool(c.referenceQuery(path, isNodeReferenced=True)),
                uuids[0]))
        return tuple(sorted(nodes, key=lambda node: node.path))

    def capture_body_proximity_pin_sources(self) -> tuple[str, ...]:
        """OriginalGeometry intermediates are outside ADV's owned rig set."""
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        identity = CharacterIdentity(self.namespace or "")
        sources = set()
        for pin in c.ls(type="proximityPin") or []:
            for source in c.listConnections(
                    pin + ".originalGeometry", source=True,
                    destination=False, shapes=True) or []:
                matches = c.ls(source, long=True) or []
                if len(matches) != 1 or not identity.owns(matches[0]):
                    continue
                sources.add(identity.to_local(matches[0]))
        return tuple(sorted(sources))

    def name_body_unit_conversions(self, plan: BodyAllSetPlan) -> None:
        self._require_transaction()
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        for path in plan.members:
            if not path.rsplit("|", 1)[-1].startswith("unitConversion"):
                continue
            node = self.scene_address(path)
            if c.nodeType(node) != "unitConversion":
                continue
            sources = c.listConnections(
                node, source=True, destination=False, plugs=True) or []
            if not sources:
                continue
            source_node, separator, attribute = sources[0].rpartition(".")
            if not separator:
                continue
            source_leaf = source_node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            target_leaf = re.sub(
                r"[^A-Za-z_0-9]", "_", source_leaf + "_" + attribute
            ) + "UC"
            if not target_leaf or target_leaf[0].isdigit():
                continue
            target = self._body_selection_set_address(target_leaf)
            self._transaction_changed = True
            renamed = c.rename(node, target)
            if not c.objExists(renamed) or c.nodeType(renamed) != "unitConversion":
                raise RuntimeError("自动生成的单位转换节点重命名失败：" + path)

    def populate_body_all_set(self, plan: BodyAllSetPlan) -> None:
        self._require_transaction()
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        target = self._body_selection_set_address(plan.set_name)
        if not c.objExists(target) or c.nodeType(target) != "objectSet":
            raise ValueError("角色 AllSet 不存在")
        if c.sets(target, query=True):
            raise ValueError("角色 AllSet 已有成员")
        members = tuple(
            address if address.startswith((":", "|")) else ":" + address
            for address in (self.scene_address(path) for path in plan.members))
        for member in members:
            if not c.objExists(member) or c.referenceQuery(
                    member, isNodeReferenced=True):
                raise ValueError("AllSet 成员缺失或属于引用：" + member)
        self._transaction_changed = True
        c.sets(members, add=target)

    def capture_body_all_set_members(self) -> tuple[str, ...]:
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        target = self._body_selection_set_address("AllSet")
        if not c.objExists(target) or c.nodeType(target) != "objectSet":
            raise RuntimeError("角色 AllSet 不存在")
        identity = CharacterIdentity(self.namespace or "")
        members = []
        for member in c.sets(target, query=True) or []:
            paths = c.ls(member, long=True) or []
            if len(paths) != 1 or not identity.owns(paths[0]):
                raise RuntimeError("角色 AllSet 成员不唯一或越界：" + member)
            members.append(identity.to_local(paths[0]))
        return tuple(members)

    def capture_body_control_history(
        self, plan: BodyAllSetPlan,
    ) -> tuple[str, ...]:
        """Match the MEL history/future/shape walk before changing its filter."""
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        control_set = self._body_selection_set_address("ControlSet")
        if not c.objExists(control_set) or c.nodeType(control_set) != "objectSet":
            raise RuntimeError("角色 ControlSet 不存在")
        identity = CharacterIdentity(self.namespace or "")
        allowed = set(plan.members)
        candidates = set()
        for member in c.sets(control_set, query=True) or []:
            controls = c.ls(member, long=True) or []
            if len(controls) != 1 or not identity.owns(controls[0]):
                raise RuntimeError("角色 ControlSet 成员不唯一或越界：" + member)
            control = controls[0]
            related = []
            for future in (False, True):
                related.extend(c.listHistory(
                    control, future=future, leaf=False, interestLevel=1,
                    pruneDagObjects=True) or [])
            related.extend(c.listRelatives(
                control, shapes=True, fullPath=True) or [])
            for node in related:
                matches = c.ls(node, long=True) or []
                if len(matches) != 1 or not identity.owns(matches[0]):
                    continue
                path = identity.to_local(matches[0])
                if path in allowed and c.objExists(
                        matches[0] + ".isHistoricallyInteresting"):
                    candidates.add(path)
        return tuple(sorted(candidates))

    def disable_body_control_history(self, nodes: tuple[str, ...]) -> None:
        self._require_transaction()
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        for path in nodes:
            plug = self.scene_address(path) + ".isHistoricallyInteresting"
            if not c.objExists(plug):
                raise RuntimeError("控制器历史节点已丢失：" + path)
            if c.getAttr(plug):
                self._transaction_changed = True
                c.setAttr(plug, 0)

    def read_body_control_history(
        self, nodes: tuple[str, ...],
    ) -> tuple[str, ...]:
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        return tuple(path for path in nodes if not c.objExists(
            self.scene_address(path) + ".isHistoricallyInteresting")
            or c.getAttr(self.scene_address(path)
                         + ".isHistoricallyInteresting"))

    def _body_selection_set_address(self, name: str) -> str:
        address = self.scene_address(name)
        return address if address.startswith((":", "|")) else ":" + address

    def _body_build_pose_commands(
        self, controls: tuple[str, ...],
        pose_channels: tuple[tuple[str, str], ...] = (),
    ) -> str:
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        commands = []
        for path in controls:
            node = self.scene_address(path)
            options = []
            for axis, flag in (("t", "translation"),
                               ("r", "rotation"), ("s", "scale")):
                if not c.getAttr(node + "." + axis + "x", keyable=True):
                    continue
                values = c.xform(node, query=True, objectSpace=True,
                                 **{flag: True})
                option = {"t": "-t", "r": "-ro", "s": "-s"}[axis]
                options.extend((option, *(f"{float(value):.3f}"
                                         for value in values)))
            if options:
                commands.append("xform -os " + " ".join(options)
                                + f' "{node}";')
            for attribute in c.listAttr(node, userDefined=True,
                                        keyable=True, shortNames=True) or []:
                value = c.getAttr(node + "." + attribute)
                if isinstance(value, (int, float, bool)):
                    commands.append(f'setAttr "{node}.{attribute}" '
                                    + str(int(value) if isinstance(value, bool)
                                          else value) + ";")
        for path, attribute in pose_channels:
            node = self.scene_address(path)
            value = c.getAttr(node + "." + attribute)
            if not isinstance(value, (int, float, bool)):
                raise ValueError("Fit Part 构建姿态通道不是数值："
                                 + path + "." + attribute)
            commands.append(f'setAttr "{node}.{attribute}" '
                            + str(int(value) if isinstance(value, bool)
                                  else value) + ";")
        return "".join(commands)

    def _body_build_pose_values(
        self, controls: tuple[str, ...],
        pose_channels: tuple[tuple[str, str], ...] = (),
    ) -> tuple[tuple[str, str, float], ...]:
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        rows = []
        standard = tuple(f"{kind}{axis}" for kind in (
            "translate", "rotate", "scale") for axis in "XYZ")
        for path in controls:
            node = self.scene_address(path)
            extras = c.listAttr(node, userDefined=True,
                                keyable=True) or []
            for attribute in (*standard, *extras):
                plug = node + "." + attribute
                if (not c.objExists(plug)
                        or not c.getAttr(plug, keyable=True)
                        or not c.getAttr(plug, settable=True)):
                    continue
                value = c.getAttr(plug)
                if isinstance(value, (int, float, bool)):
                    rows.append((path, attribute, float(value)))
        for path, attribute in pose_channels:
            plug = self.scene_address(path) + "." + attribute
            if (not c.objExists(plug)
                    or not c.getAttr(plug, keyable=True)
                    or not c.getAttr(plug, settable=True)):
                raise ValueError("Fit Part 构建姿态通道不可写：" + plug)
            value = c.getAttr(plug)
            if not isinstance(value, (int, float, bool)):
                raise ValueError("Fit Part 构建姿态通道不是数值：" + plug)
            rows.append((path, attribute, float(value)))
        return tuple(rows)

    def resolve_body_selection_members(
        self, registration: CharacterRegistration,
        segments: tuple[str, ...], extras: tuple[str, ...],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        c = self._cmds
        controls = []

        def selection_layer(control: str) -> str:
            leaf = control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            extra_names = {leaf[:index] + "Extra" + leaf[index:]
                           for index in range(1, len(leaf) + 1)}
            current = control
            while True:
                parent = c.listRelatives(current, parent=True,
                                         fullPath=True) or []
                if not parent:
                    return control
                current = parent[0]
                parent_leaf = current.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                if parent_leaf in extra_names:
                    return current

        def hidden_fk_extra(node: str) -> bool:
            # MEL removes both FK and FKExtra from ControlSet for noControl.
            # Extra curves can have their own registered animation channels,
            # so filtering only the hidden FK transform is insufficient.
            if "FKExtra" not in node.rsplit("|", 1)[-1]:
                return False
            return any(
                c.attributeQuery("advPyNoControl", node=child, exists=True)
                and c.getAttr(child + ".advPyNoControl")
                and selection_layer(child) == node
                for child in (c.listRelatives(
                    node, allDescendents=True, type="transform",
                    fullPath=True) or []))

        for path in dict.fromkeys(channel.node
                                  for channel in registration.channels):
            matches = c.ls(path, long=True) or []
            if len(matches) != 1:
                raise ValueError("登记控制通道节点不存在：" + path)
            node = matches[0]
            if c.nodeType(node) != "transform":
                continue
            if (c.attributeQuery("advPyNoControl", node=node,
                                 exists=True)
                    and c.getAttr(node + ".advPyNoControl")):
                continue
            if hidden_fk_extra(node):
                continue
            shapes = c.listRelatives(node, shapes=True,
                                     type="nurbsCurve") or []
            if shapes:
                controls.append(selection_layer(node))
        for path in extras:
            matches = c.ls(path, long=True, type="transform") or []
            if len(matches) != 1:
                raise ValueError("控制器 Extra 层不存在：" + path)
            controls.append(matches[0])
        joints = []
        def in_deform_set(node: str) -> bool:
            # ADV removes every terminal joint from DeformSet after building
            # the complete hierarchy.  A leaf can still be a Skin influence
            # on an imported character, so this affects selection only.
            return (self.read_skin_influence_enabled(node)
                    and bool(c.listRelatives(node, children=True,
                                             type="joint", fullPath=True)))

        for path in dict.fromkeys((joint.path for joint in registration.body)):
            matches = c.ls(path, long=True, type="joint") or []
            if len(matches) != 1:
                raise ValueError("登记变形关节不存在：" + path)
            if in_deform_set(matches[0]):
                joints.append(matches[0])
        for path in segments:
            matches = c.ls(path, long=True, type="joint") or []
            if len(matches) != 1:
                raise ValueError("分段变形关节不存在：" + path)
            if in_deform_set(matches[0]):
                joints.append(matches[0])
        return (tuple(dict.fromkeys(controls)),
                tuple(dict.fromkeys(joints)))

    def preflight_body_selection_sets(
        self, plan: BodySelectionSetsPlan,
    ) -> None:
        c = self._cmds
        for name in (plan.control_set, plan.deform_set,
                     plan.all_set, plan.root_set, plan.build_pose):
            if c.objExists(name):
                raise ValueError("角色选择集名称已占用：" + name)
        group = c.ls(plan.character_group, long=True,
                     type="transform") or []
        motion = c.ls(plan.motion_system, long=True,
                      type="transform") or []
        main = c.ls(plan.main_system, long=True,
                    type="transform") or []
        if (len(group) != 1 or len(motion) != 1 or len(main) != 1
                or c.listRelatives(group[0], parent=True,
                                   fullPath=True)
                or (c.listRelatives(motion[0], parent=True,
                                    fullPath=True) or []) != group
                or (c.listRelatives(main[0], parent=True,
                                    fullPath=True) or []) != motion):
            raise ValueError("角色 Group、MotionSystem、MainSystem 层级无效")
        for control in plan.controls:
            nodes = c.ls(control, long=True, type="transform") or []
            if len(nodes) != 1 or nodes[0] != control:
                raise ValueError("角色选择集控制层缺失：" + control)
            plug = control + ".selectionChildHighlighting"
            if c.objExists(plug) and not c.getAttr(plug, settable=True):
                raise ValueError("控制器子级高亮属性不可写：" + control)

    def create_body_selection_sets(
        self, plan: BodySelectionSetsPlan,
    ) -> None:
        self._require_transaction()
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        all_set = self._body_selection_set_address(plan.all_set)
        root_set = self._body_selection_set_address(plan.root_set)
        for name, members in ((plan.control_set, plan.controls),
                              (plan.deform_set, plan.deform_joints)):
            scene_set = self._body_selection_set_address(name)
            c.sets(empty=True, name=scene_set)
            c.sets(tuple(self.scene_address(path) for path in members),
                   add=scene_set)
        for control in plan.controls:
            plug = self.scene_address(control) + ".selectionChildHighlighting"
            if c.objExists(plug):
                c.setAttr(plug, False)
        c.sets(empty=True, name=all_set)
        c.sets(empty=True, name=root_set)
        c.sets((self._body_selection_set_address(plan.control_set),
                self._body_selection_set_address(plan.deform_set),
                all_set), add=root_set)
        motion = self._body_selection_set_address(plan.motion_system)
        pose = self._body_selection_set_address(plan.build_pose)
        c.createNode("transform", name=pose, parent=motion,
                     skipSelect=True)
        for attribute in ("translateX", "translateY", "translateZ",
                          "rotateX", "rotateY", "rotateZ",
                          "scaleX", "scaleY", "scaleZ", "visibility"):
            c.setAttr(pose + "." + attribute, lock=True, keyable=False,
                      channelBox=False)
        for attribute, value in (("udAttr", self._body_build_pose_commands(
                plan.controls, plan.pose_channels)), ("udExtraAttr", "")):
            c.addAttr(pose, longName=attribute, dataType="string")
            c.setAttr(pose + "." + attribute, value, type="string")
        c.addAttr(pose, longName="advPyPoseData", dataType="string")
        c.setAttr(pose + ".advPyPoseData", json.dumps(
            self._body_build_pose_values(
                plan.controls, plan.pose_channels),
            separators=(",", ":")), type="string")
        self._transaction_changed = True

    def capture_body_selection_sets(
        self, plan: BodySelectionSetsPlan,
    ) -> BodySelectionSetsPlan:
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        identity = (self._cmds.identity
                    if hasattr(self._cmds, "identity") else None)

        def members(name: str) -> tuple[str, ...]:
            address = self._body_selection_set_address(name)
            if not c.objExists(address) or c.nodeType(address) != "objectSet":
                raise RuntimeError("角色选择集不存在：" + name)
            paths = []
            for member in c.sets(address, query=True) or []:
                found = c.ls(member, long=True) or []
                if len(found) != 1:
                    raise RuntimeError("角色选择集成员不唯一：" + member)
                paths.append(identity.to_local(found[0]) if identity
                             else found[0])
            return tuple(paths)

        all_set = self._body_selection_set_address(plan.all_set)
        root_set = self._body_selection_set_address(plan.root_set)
        if (not c.objExists(all_set) or c.nodeType(all_set) != "objectSet"
                or not c.objExists(root_set)
                or c.nodeType(root_set) != "objectSet"):
            raise RuntimeError("角色选择集根层不完整")
        children = c.sets(root_set, query=True) or []
        if {item.lstrip(":") for item in children} != {
                self._body_selection_set_address(name).lstrip(":")
                for name in (plan.control_set, plan.deform_set,
                             plan.all_set)}:
            raise RuntimeError("角色选择集嵌套成员不一致")
        pose = self._body_selection_set_address(plan.build_pose)
        motion = self._body_selection_set_address(plan.motion_system)
        group = self._body_selection_set_address(plan.character_group)
        main = self._body_selection_set_address(plan.main_system)
        group_paths = c.ls(group, long=True) or []
        motion_paths = c.ls(motion, long=True) or []
        main_paths = c.ls(main, long=True) or []
        pose_paths = c.ls(pose, long=True) or []
        if (not c.objExists(pose) or c.nodeType(pose) != "transform"
                or len(group_paths) != 1
                or len(motion_paths) != 1
                or len(main_paths) != 1
                or len(pose_paths) != 1
                or c.listRelatives(group_paths[0], parent=True,
                                   fullPath=True)
                or (c.listRelatives(motion_paths[0], parent=True,
                                    fullPath=True) or []) != group_paths
                or (c.listRelatives(main_paths[0], parent=True,
                                    fullPath=True) or []) != motion_paths
                or (c.listRelatives(pose_paths[0], parent=True,
                                    fullPath=True) or []) != motion_paths
                or any(not c.getAttr(pose + "." + attribute, lock=True)
                       for attribute in (
                           "translateX", "translateY", "translateZ",
                           "rotateX", "rotateY", "rotateZ",
                           "scaleX", "scaleY", "scaleZ", "visibility"))
                or not c.objExists(pose + ".udAttr")
                or not c.objExists(pose + ".udExtraAttr")
                or not c.objExists(pose + ".advPyPoseData")
                or (c.getAttr(pose + ".udAttr") or "")
                != self._body_build_pose_commands(
                    plan.controls, plan.pose_channels)
                or (c.getAttr(pose + ".udExtraAttr") or "") != ""
                or json.loads(c.getAttr(pose + ".advPyPoseData"))
                != [list(row) for row in self._body_build_pose_values(
                    plan.controls, plan.pose_channels)]):
            raise RuntimeError("角色 buildPose 初始复位记录不一致")
        for control in plan.controls:
            plug = self.scene_address(control) + ".selectionChildHighlighting"
            if c.objExists(plug) and c.getAttr(plug):
                raise RuntimeError("控制器子级高亮未关闭：" + control)
        return BodySelectionSetsPlan(members(plan.control_set),
                                     members(plan.deform_set),
                                     plan.pose_channels)
