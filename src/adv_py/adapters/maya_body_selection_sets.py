"""Maya selection sets shared by Body skinning and custom controls."""
from __future__ import annotations

from adv_py.core.body_selection_sets import BodySelectionSetsPlan
from adv_py.core.character_registry import CharacterRegistration


class MayaBodySelectionSetsMixin:
    def _body_selection_set_address(self, name: str) -> str:
        address = self.scene_address(name)
        return address if address.startswith((":", "|")) else ":" + address

    def resolve_body_selection_members(
        self, registration: CharacterRegistration,
        segments: tuple[str, ...], extras: tuple[str, ...],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        c = self._cmds
        controls = []
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
                controls.append(node)
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
        for name in (plan.control_set, plan.deform_set):
            if c.objExists(name):
                raise ValueError("角色选择集名称已占用：" + name)

    def create_body_selection_sets(
        self, plan: BodySelectionSetsPlan,
    ) -> None:
        self._require_transaction()
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        for name, members in ((plan.control_set, plan.controls),
                              (plan.deform_set, plan.deform_joints)):
            scene_set = self._body_selection_set_address(name)
            c.sets(empty=True, name=scene_set)
            c.sets(tuple(self.scene_address(path) for path in members),
                   add=scene_set)
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

        return BodySelectionSetsPlan(members(plan.control_set),
                                     members(plan.deform_set))
