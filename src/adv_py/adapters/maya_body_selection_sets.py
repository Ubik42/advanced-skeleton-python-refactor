"""Maya selection sets shared by Body skinning and custom controls."""
from __future__ import annotations

from adv_py.core.body_selection_sets import BodySelectionSetsPlan
from adv_py.core.character_registry import CharacterRegistration


class MayaBodySelectionSetsMixin:
    def _body_selection_set_address(self, name: str) -> str:
        address = self.scene_address(name)
        return address if address.startswith((":", "|")) else ":" + address

    def _body_build_pose_commands(self, controls: tuple[str, ...]) -> str:
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
        return "".join(commands)

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

        for path in dict.fromkeys(channel.node
                                  for channel in registration.channels):
            matches = c.ls(path, long=True) or []
            if len(matches) != 1:
                raise ValueError("登记控制通道节点不存在：" + path)
            node = matches[0]
            if c.nodeType(node) != "transform":
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
        for path in dict.fromkeys((joint.path for joint in registration.body)):
            matches = c.ls(path, long=True, type="joint") or []
            if len(matches) != 1:
                raise ValueError("登记变形关节不存在：" + path)
            if self.read_skin_influence_enabled(matches[0]):
                joints.append(matches[0])
        for path in segments:
            matches = c.ls(path, long=True, type="joint") or []
            if len(matches) != 1:
                raise ValueError("分段变形关节不存在：" + path)
            if self.read_skin_influence_enabled(matches[0]):
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
        c.sets(empty=True, name=all_set)
        c.sets(empty=True, name=root_set)
        c.sets((self._body_selection_set_address(plan.control_set),
                self._body_selection_set_address(plan.deform_set),
                all_set), add=root_set)
        pose = self._body_selection_set_address(plan.build_pose)
        c.createNode("transform", name=pose, skipSelect=True)
        for attribute, value in (("udAttr", self._body_build_pose_commands(
                plan.controls)), ("udExtraAttr", "")):
            c.addAttr(pose, longName=attribute, dataType="string")
            c.setAttr(pose + "." + attribute, value, type="string")
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
                or c.sets(all_set, query=True)
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
        if (not c.objExists(pose) or c.nodeType(pose) != "transform"
                or not c.objExists(pose + ".udAttr")
                or not c.objExists(pose + ".udExtraAttr")
                or (c.getAttr(pose + ".udAttr") or "")
                != self._body_build_pose_commands(plan.controls)
                or (c.getAttr(pose + ".udExtraAttr") or "") != ""):
            raise RuntimeError("角色 buildPose 初始复位记录不一致")
        return BodySelectionSetsPlan(members(plan.control_set),
                                     members(plan.deform_set))
