"""Python execution of the Body build pose, without evaluating MEL text."""
from __future__ import annotations

import json

from adv_py.core.body_build_pose import (
    BodyBuildPosePlan, plan_body_build_pose,
)
from adv_py.core.character_registry import REGISTRY_NAME


class MayaBodyBuildPoseMixin:
    def _body_pose_cmds(self):
        return self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds

    def read_body_build_pose(self) -> BodyBuildPosePlan:
        c = self._body_pose_cmds()
        pose = self._body_selection_set_address("buildPose")
        control_set = self._body_selection_set_address("ControlSet")
        if (not c.objExists(self._body_selection_set_address(REGISTRY_NAME))
                or not c.objExists(pose + ".advPyPoseData")
                or not c.objExists(control_set)
                or c.nodeType(control_set) != "objectSet"):
            raise ValueError("当前角色缺少 Python 构建姿态记录")
        rows = json.loads(c.getAttr(pose + ".advPyPoseData"))
        if not isinstance(rows, list):
            raise ValueError("Body 构建姿态数据不是通道列表")
        for member in c.sets(control_set, query=True) or []:
            matches = c.ls(member, long=True) or []
            if len(matches) != 1:
                raise ValueError("ControlSet 成员不存在或不唯一：" + member)
            plug = matches[0] + ".advPyBuildPoseValues"
            if c.objExists(plug):
                extra = json.loads(c.getAttr(plug))
                if not isinstance(extra, list):
                    raise ValueError("自定义控制器构建姿态数据无效")
                rows.extend(extra)
        if any(not isinstance(row, list) or len(row) != 3 for row in rows):
            raise ValueError("Body 构建姿态通道格式无效")
        return plan_body_build_pose(tuple(tuple(row) for row in rows))

    def preflight_body_build_pose(self, plan: BodyBuildPosePlan) -> None:
        c = self._body_pose_cmds()
        identity = (self._cmds.identity
                    if hasattr(self._cmds, "identity") else None)
        for item in plan.values:
            node = self._body_selection_set_address(item.node)
            matches = c.ls(node, long=True) or []
            if (len(matches) != 1
                    or (identity is not None
                        and not identity.owns(matches[0]))):
                raise ValueError("构建姿态控制器不存在或不属于当前角色："
                                 + item.node)
            plug = matches[0] + "." + item.attribute
            if not c.objExists(plug) or not c.getAttr(plug, settable=True):
                raise ValueError("构建姿态通道不可写：" + plug)

    def apply_body_build_pose(self, plan: BodyBuildPosePlan) -> None:
        self._require_transaction()
        c = self._body_pose_cmds()
        for item in plan.values:
            c.setAttr(self._body_selection_set_address(item.node)
                      + "." + item.attribute,
                      item.value)
        self._transaction_changed = True

    def capture_body_build_pose_values(
        self, plan: BodyBuildPosePlan,
    ) -> tuple[float, ...]:
        c = self._body_pose_cmds()
        return tuple(float(c.getAttr(self._body_selection_set_address(item.node)
                                     + "." + item.attribute))
                     for item in plan.values)
