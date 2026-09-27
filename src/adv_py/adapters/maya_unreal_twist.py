"""Maya hierarchy port of asUnrealTwistJointsBehaviour."""
from __future__ import annotations

import re

from .maya_custom_controller import MayaCustomControllerHost


_PART = re.compile(r"Part[0-9]+(?:_[RLM])?$")


class MayaUnrealTwistHost(MayaCustomControllerHost):
    def __init__(self, *, namespace: str | None = None) -> None:
        super().__init__(namespace=namespace, face=False)

    @staticmethod
    def _leaf(path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def preflight_twist(self, enable: bool) -> None:
        self._unique("DeformationSystem", "transform")
        for joint in self._deform_joints():
            recorded = self._cmds.attributeQuery(
                "originalParent", node=joint, exists=True)
            if enable and recorded:
                raise ValueError("Unreal Twist 层级已经启用；先执行删除")
            if not enable and recorded:
                original = self._cmds.getAttr(joint + ".originalParent")
                if not self._cmds.objExists(original):
                    raise ValueError("原始父关节已不存在：" + original)

    def _deform_joints(self) -> list[str]:
        c = self._cmds
        paths = c.listRelatives(self._unique("DeformationSystem", "transform"),
                                allDescendents=True, type="joint",
                                fullPath=True) or []
        return [path.rsplit("|", 1)[-1] for path in paths]

    def set_twist_hierarchy(self, enable: bool) -> int:
        self._require_transaction()
        c = self._cmds
        count = 0
        for joint in self._deform_joints():
            joint = self._unique(joint, "joint")
            if not enable:
                if not c.attributeQuery("originalParent", node=joint,
                                        exists=True):
                    continue
                original = c.getAttr(joint + ".originalParent")
                moved = c.parent(joint, original, absolute=True)[0]
                c.deleteAttr(moved, attribute="originalParent")
                self._transaction_changed = True
                count += 1
                continue
            parent = (c.listRelatives(joint, parent=True, fullPath=True)
                      or [None])[0]
            if not parent:
                continue
            original = parent
            depth = 0
            while parent and _PART.search(self._leaf(parent)):
                parent = (c.listRelatives(parent, parent=True,
                                          fullPath=True) or [None])[0]
                depth += 1
            if not parent or depth < 1:
                continue
            base = self._leaf(parent).split("_", 1)[0]
            fit = self.scene_address(base)
            if c.objExists(fit) and c.attributeQuery(
                    "inbetweenJoints", node=fit, exists=True):
                continue
            moved = c.parent(joint, parent, absolute=True)[0]
            if _PART.search(self._leaf(moved)):
                c.reorder(moved, relative=-1)
            c.addAttr(moved, longName="originalParent", dataType="string")
            c.setAttr(moved + ".originalParent", original, type="string")
            self._transaction_changed = True
            count += 1
        c.select(clear=True)
        return count
