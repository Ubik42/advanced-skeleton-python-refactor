"""Maya HumanIK host; native HIK procedures remain behind this boundary."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from adv_py.core.human_ik import HumanIkAssignment, HumanIkBakePlan
from .maya_custom_controller import MayaCustomControllerHost


class MayaHumanIkHost(MayaCustomControllerHost):
    def __init__(self, *, namespace: str | None = None) -> None:
        super().__init__(namespace=namespace, face=False)
        self._character: str | None = None

    def _node(self, name: str) -> str:
        return self.scene_address(name)

    @staticmethod
    def _leaf(path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    @contextmanager
    def _namespace_scope(self) -> Iterator[None]:
        c = self._cmds
        before = c.namespaceInfo(currentNamespace=True)
        target = ":" if self.namespace is None else ":" + self.namespace.strip(":")
        c.namespace(setNamespace=target)
        try:
            yield
        finally:
            c.namespace(setNamespace=before)

    def capture_human_ik_nodes(self) -> frozenset[str]:
        c = self._cmds
        names = []
        for path in c.ls(long=True) or []:
            leaf = path.rsplit("|", 1)[-1]
            if self.namespace is None:
                if ":" in leaf:
                    continue
            elif not leaf.startswith(self.namespace.strip(":") + ":"):
                continue
            names.append(self._leaf(path))
        return frozenset(names)

    def preflight_human_ik(self, operation: str) -> None:
        if operation not in ("create", "delete", "bake"):
            raise ValueError("HumanIK 操作名称无效")
        self._unique("DeformationSystem", "transform")
        self._unique("Root_M", "joint")
        if operation in ("delete", "bake") and not self.human_ik_exists():
            raise ValueError("当前角色没有 HumanIK 定义")
        if operation == "bake":
            self._unique("RootX_M", "transform")
            root = self._unique("Root_M", "joint")
            names = [root] + (self._cmds.listRelatives(
                root, allDescendents=True, fullPath=True,
                type="joint") or [])
            for joint in names:
                prefixed = "prefix_" + self._leaf(joint)
                if self._cmds.objExists(self._node(prefixed)):
                    raise ValueError("HumanIK Bake 临时名称已占用：" + prefixed)

    def _find_character(self) -> str | None:
        c = self._cmds
        address = self._node("Character1")
        matches = c.ls(address, type="HIKCharacterNode") or []
        if len(matches) > 1:
            raise ValueError("HumanIK Character1 名称不唯一")
        return matches[0] if matches else None

    def human_ik_exists(self) -> bool:
        return self._find_character() is not None

    def remove_human_ik(self) -> None:
        self._require_transaction()
        c = self._cmds
        character = self._find_character()
        owned = set()
        frontier = [character] if character else []
        for _ in range(3):
            next_frontier = []
            for node in frontier:
                for connected in c.listConnections(node, source=True,
                                                   destination=True) or []:
                    if connected in owned:
                        continue
                    kind = c.nodeType(connected)
                    if kind == "HIKCharacterNode" and connected != character:
                        continue
                    if kind.startswith("HIK") or kind.startswith("hik"):
                        owned.add(connected)
                        next_frontier.append(connected)
            frontier = next_frontier
        for name in ("Character1_Reference", "Character1_Ctrl_Reference"):
            node = self._node(name)
            if c.objExists(node):
                self._transaction_changed = True
                c.delete(node)
        if character is None:
            return
        self._transaction_changed = True
        for node in sorted(owned, reverse=True):
            if c.objExists(node):
                c.delete(node)
        if c.objExists(character):
            c.delete(character)
        for system in ("MotionSystem", "DeformationSystem"):
            node = self._node(system)
            if c.objExists(node):
                c.setAttr(node + ".visibility", True)
        self._character = None

    def create_human_ik_definition(self) -> None:
        from maya import mel

        self._require_transaction()
        self._transaction_changed = True
        with self._namespace_scope():
            mel.eval("HIKCharacterControlsTool;")
            mel.eval("hikCreateDefinition;")
        character = self._find_character()
        if character is None:
            raise RuntimeError("Maya 未创建 Character1 HumanIK 定义")
        self._character = character

    def connect_human_ik_slot(self, assignment: HumanIkAssignment) -> None:
        self._require_transaction()
        c = self._cmds
        character = self._character or self._find_character()
        if character is None:
            raise RuntimeError("HumanIK 定义不存在")
        matches = c.ls(self._node(assignment.source), long=True) or []
        if len(matches) != 1 or c.nodeType(matches[0]) not in ("joint", "transform"):
            raise ValueError("HumanIK 映射来源不存在或不唯一：" + assignment.source)
        source = matches[0]
        slot = character + "." + assignment.slot
        if not c.objExists(slot):
            raise ValueError("HumanIK 版本缺少槽位：" + assignment.slot)
        message = source + ".Character"
        if not c.objExists(message):
            c.addAttr(source, longName="Character", shortName="ch",
                      attributeType="message")
        self._transaction_changed = True
        c.connectAttr(message, slot, force=True)

    def finish_human_ik_definition(self, create_control_rig: bool) -> None:
        from maya import mel

        self._require_transaction()
        if not create_control_rig:
            return
        self._transaction_changed = True
        with self._namespace_scope():
            mel.eval("hikCreateControlRig;")
        c = self._cmds
        if not c.objExists(self._node("Character1_Ctrl_Reference")):
            raise RuntimeError("HumanIK 控制绑定未创建")
        for name in ("FKHead_M", "FKNeck_M"):
            node = self._node(name)
            if c.objExists(node):
                c.setAttr(node + ".visibility", True)
        for system in ("MotionSystem", "DeformationSystem"):
            node = self._node(system)
            if c.objExists(node):
                c.setAttr(node + ".visibility", False)
        deformation = self._unique("DeformationSystem", "transform")
        for joint in c.listRelatives(deformation, allDescendents=True,
                                     fullPath=True, type="joint") or []:
            if c.getAttr(joint + ".drawStyle") == 2:
                c.setAttr(joint + ".drawStyle", 0)

    def capture_human_ik_slots(self) -> dict[str, str]:
        c = self._cmds
        character = self._find_character()
        if character is None:
            return {}
        slots = {}
        for attribute in c.listAttr(character, connectable=True) or []:
            sources = c.listConnections(character + "." + attribute,
                                        source=True, destination=False) or []
            if len(sources) == 1:
                slots[attribute] = self._leaf(sources[0])
        return slots

    def playback_range(self) -> tuple[float, float]:
        c = self._cmds
        return (float(c.playbackOptions(query=True, minTime=True)),
                float(c.playbackOptions(query=True, maxTime=True)))

    def bake_human_ik(self, plan: HumanIkBakePlan) -> None:
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        root = self._unique("Root_M", "joint")
        original_time = c.currentTime(query=True)
        original_auto_key = bool(c.autoKeyframe(query=True, state=True))
        original_selection = c.ls(selection=True, long=True) or []
        duplicate = None
        try:
            duplicate = c.duplicate(root, name=self._node("prefix_Root_M"),
                                    returnRootsOnly=True)[0]
            descendants = c.listRelatives(duplicate, allDescendents=True,
                                          fullPath=True) or []
            for path in descendants:
                leaf = self._leaf(path)
                if leaf.startswith("prefix_"):
                    continue
                c.rename(path, self._node("prefix_" + leaf))
            duplicate = self._unique("prefix_Root_M", "joint")
            c.parent(duplicate, world=True)
            joints = [duplicate] + (c.listRelatives(
                duplicate, allDescendents=True, fullPath=True,
                type="joint") or [])
            for prefixed in joints:
                leaf = self._leaf(prefixed)
                source_name = leaf.removeprefix("prefix_")
                source = self._node(source_name)
                if c.objExists(source):
                    c.parentConstraint(source, prefixed,
                                       maintainOffset=False)
            c.bakeResults(joints, simulation=True,
                          time=(plan.first_frame, plan.last_frame),
                          sampleBy=1, disableImplicitControl=True,
                          preserveOutsideKeys=False,
                          sparseAnimCurveBake=False,
                          removeBakedAttributeFromLayer=False,
                          bakeOnOverrideLayer=False,
                          controlPoints=False, shape=False)
            self.remove_human_ik()
            c.currentTime(-1)
            c.autoKeyframe(state=True)
            for prefixed in joints:
                if not c.objExists(prefixed):
                    continue
                source_name = self._leaf(prefixed).removeprefix("prefix_")
                source = self._node(source_name)
                if not c.objExists(source):
                    continue
                for kind in ("translate", "rotate", "scale"):
                    for axis in "XYZ":
                        source_plug = source + "." + kind + axis
                        target_plug = prefixed + "." + kind + axis
                        if (c.objExists(source_plug) and c.objExists(target_plug)
                                and not c.getAttr(target_plug, lock=True)
                                and not c.connectionInfo(target_plug,
                                    isDestination=True)):
                            c.setAttr(target_plug, c.getAttr(source_plug))
            for source_name, target_name, kind in plan.drivers:
                source = self._node(source_name)
                target = self._node(target_name)
                if not c.objExists(source) or not c.objExists(target):
                    continue
                if kind == "point":
                    c.pointConstraint(source, target,
                                      maintainOffset=False)
                else:
                    c.parentConstraint(source, target,
                                       maintainOffset=kind == "parentOffset")
            controls = [self._node(name) for name in plan.controls]
            if not controls:
                raise ValueError("HumanIK Bake 没有可烘焙的 ADV 控制器")
            c.bakeResults(controls, simulation=True,
                          time=(plan.first_frame, plan.last_frame),
                          sampleBy=1, disableImplicitControl=True,
                          preserveOutsideKeys=False,
                          sparseAnimCurveBake=False,
                          removeBakedAttributeFromLayer=False,
                          bakeOnOverrideLayer=False,
                          controlPoints=False, shape=False)
        finally:
            if duplicate and c.objExists(duplicate):
                c.delete(duplicate)
            c.currentTime(original_time)
            c.autoKeyframe(state=original_auto_key)
            if original_selection:
                c.select([node for node in original_selection if c.objExists(node)],
                         replace=True)
            else:
                c.select(clear=True)

    def capture_baked_human_ik(self, plan: HumanIkBakePlan) -> bool:
        c = self._cmds
        if self.human_ik_exists() or c.objExists(self._node("prefix_Root_M")):
            return False
        return any((c.keyframe(self._node(control), query=True,
                               keyframeCount=True,
                               time=(plan.first_frame, plan.last_frame)) or 0) > 0
                   for control in plan.controls)
