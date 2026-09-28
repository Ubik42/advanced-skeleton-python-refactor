"""Python execution of the Body build pose, without evaluating MEL text."""
from __future__ import annotations

import json

from adv_py.core.body_build_pose import (
    BodyBuildPoseOverrides, BodyBuildPosePlan, BodyBuildPoseValue,
    merge_body_build_pose, plan_body_build_pose,
)
from adv_py.core.character_registry import REGISTRY_NAME


class MayaBodyBuildPoseMixin:
    def _body_pose_cmds(self):
        return self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds

    def read_body_build_pose_base(self) -> BodyBuildPosePlan:
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

    def _body_pose_fit_address(self) -> str:
        c = self._body_pose_cmds()
        fit = self._body_selection_set_address("FitSkeleton")
        if not c.objExists(fit):
            raise ValueError("当前角色缺少 FitSkeleton")
        return fit

    def read_body_build_pose_overrides(self) -> BodyBuildPoseOverrides:
        c = self._body_pose_cmds()
        fit = self._body_pose_fit_address()
        plug = fit + ".advPyBuildPoseOverrides"
        if not c.objExists(plug):
            return BodyBuildPoseOverrides(())
        rows = json.loads(c.getAttr(plug))
        if (not isinstance(rows, list)
                or any(not isinstance(row, list) or len(row) != 3
                       for row in rows)):
            raise ValueError("Fit 构建姿态覆盖数据格式无效")
        values = tuple(BodyBuildPoseValue(*row) for row in rows)
        return BodyBuildPoseOverrides(values)

    def has_body_build_pose_overrides(self) -> bool:
        return bool(self.read_body_build_pose_overrides().values)

    def read_body_build_pose(self) -> BodyBuildPosePlan:
        return merge_body_build_pose(self.read_body_build_pose_base(),
                                     self.read_body_build_pose_overrides())

    def capture_current_body_build_pose(
        self, base: BodyBuildPosePlan,
    ) -> BodyBuildPosePlan:
        c = self._body_pose_cmds()
        identity = (self._cmds.identity
                    if hasattr(self._cmds, "identity") else None)
        rows = [(item.node, item.attribute,
                 float(c.getAttr(self._body_selection_set_address(item.node)
                                 + "." + item.attribute)))
                for item in base.values]
        seen = set()
        for node, attribute, _ in rows:
            matches = c.ls(self._body_selection_set_address(node),
                           long=True) or []
            if len(matches) != 1:
                raise ValueError("构建姿态控制器不存在或不唯一：" + node)
            seen.add((matches[0], attribute))
        control_set = self._body_selection_set_address("ControlSet")
        for member in c.sets(control_set, query=True) or []:
            matches = c.ls(member, long=True) or []
            if len(matches) != 1:
                raise ValueError("ControlSet 成员不存在或不唯一：" + member)
            node = matches[0]
            for attribute in c.listAttr(node, userDefined=True,
                                        keyable=True) or []:
                plug = node + "." + attribute
                key = (node, attribute)
                if key in seen or not c.getAttr(plug, settable=True):
                    continue
                value = c.getAttr(plug)
                if isinstance(value, (int, float, bool)):
                    rows.append((identity.to_local(node) if identity else node,
                                 attribute, float(value)))
                    seen.add(key)
        return plan_body_build_pose(tuple(rows))

    def write_body_build_pose_overrides(
        self, overrides: BodyBuildPoseOverrides,
    ) -> None:
        self._require_transaction()
        c = self._body_pose_cmds()
        fit = self._body_pose_fit_address()
        plug = fit + ".advPyBuildPoseOverrides"
        if not c.objExists(plug):
            c.addAttr(fit, longName="advPyBuildPoseOverrides",
                      dataType="string")
        c.setAttr(plug, json.dumps(tuple((item.node, item.attribute,
                                          item.value)
                                         for item in overrides.values),
                                   separators=(",", ":")), type="string")
        self._transaction_changed = True

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
