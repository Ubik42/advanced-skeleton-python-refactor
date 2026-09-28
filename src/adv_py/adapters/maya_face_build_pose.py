"""Face control selection and numeric build-pose data for Python rigs."""
from __future__ import annotations

import json

from adv_py.core.body_build_pose import (
    BodyBuildPoseOverrides, BodyBuildPosePlan, BodyBuildPoseValue,
    merge_body_build_pose, plan_body_build_pose,
)


class MayaFaceBuildPoseMixin:
    def _face_pose_rows(self, controls: tuple[str, ...]) -> tuple[tuple[str, str, float], ...]:
        c = self._cmds
        standard = tuple(f"{kind}{axis}" for kind in (
            "translate", "rotate", "scale") for axis in "XYZ")
        rows = []
        for control in controls:
            paths = c.ls(control, long=True, type="transform") or []
            if len(paths) != 1:
                raise ValueError("Face 构建姿态控制器不存在或不唯一：" + control)
            node = paths[0]
            extras = c.listAttr(node, userDefined=True, keyable=True) or []
            for attribute in (*standard, *extras):
                plug = node + "." + attribute
                if (not c.objExists(plug)
                        or not c.getAttr(plug, keyable=True)
                        or not c.getAttr(plug, settable=True)):
                    continue
                value = c.getAttr(plug)
                if isinstance(value, (int, float, bool)):
                    rows.append((node, attribute, float(value)))
        return tuple(rows)

    def record_face_build_pose(self, controls: tuple[str, ...]) -> int:
        self._require_transaction()
        c = self._cmds
        if not controls or len(controls) != len(set(controls)):
            raise ValueError("Face 构建姿态控制器为空或重复")
        motion = c.ls("FaceMotionSystem", long=True,
                      type="transform") or []
        if len(motion) != 1:
            raise ValueError("FaceMotionSystem 不存在或不唯一")
        controls = tuple((c.ls(node, long=True,
                               type="transform") or [None])[0]
                         for node in controls)
        if None in controls or len(controls) != len(set(controls)):
            raise ValueError("Face 构建姿态控制器路径无效")
        rows = self._face_pose_rows(controls)
        plan = plan_body_build_pose(rows)
        control_set = c.sets(empty=True, name="FaceControlSet")
        c.sets(controls, add=control_set)
        pose = c.createNode("transform", name="faceBuildPose",
                            parent=motion[0], skipSelect=True)
        for attribute in ("translateX", "translateY", "translateZ",
                          "rotateX", "rotateY", "rotateZ",
                          "scaleX", "scaleY", "scaleZ", "visibility"):
            c.setAttr(pose + "." + attribute, lock=True,
                      keyable=False, channelBox=False)
        mel_pose = "".join(
            f'setAttr "{self.scene_address(node)}.{attribute}" {value:.17g};'
            for node, attribute, value in rows)
        for attribute, value in (("udAttr", mel_pose), ("udExtraAttr", ""),
                                 ("advPyPoseData", json.dumps(rows,
                                     separators=(",", ":")))):
            c.addAttr(pose, longName=attribute, dataType="string")
            c.setAttr(pose + "." + attribute, value, type="string")
        self._transaction_changed = True
        members = set(c.ls(c.sets(control_set, query=True) or [],
                           long=True, type="transform") or ())
        if (self.read_face_build_pose_base() != plan
                or members != set(controls)):
            raise RuntimeError("Face 构建姿态写后读回不一致")
        return len(plan.values)

    def read_face_build_pose_base(self) -> BodyBuildPosePlan:
        c = self._cmds
        pose = self.scene_address("faceBuildPose")
        control_set = self.scene_address("FaceControlSet")
        pose_paths = c.ls(pose, long=True, type="transform") or []
        motion_paths = c.ls("FaceMotionSystem", long=True,
                            type="transform") or []
        if (not c.objExists(pose + ".advPyPoseData")
                or not c.objExists(control_set)
                or c.nodeType(control_set) != "objectSet"
                or len(pose_paths) != 1 or len(motion_paths) != 1
                or (c.listRelatives(pose_paths[0], parent=True,
                                    fullPath=True) or []) != motion_paths):
            raise ValueError("当前角色缺少 Face 构建姿态记录")
        rows = json.loads(c.getAttr(pose + ".advPyPoseData"))
        if not isinstance(rows, list):
            raise ValueError("Face 构建姿态数据不是通道列表")
        for member in c.sets(control_set, query=True) or []:
            matches = c.ls(member, long=True, type="transform") or []
            if len(matches) != 1:
                raise ValueError("FaceControlSet 成员不存在或不唯一")
            plug = matches[0] + ".advPyBuildPoseValues"
            if c.objExists(plug):
                extra = json.loads(c.getAttr(plug))
                if not isinstance(extra, list):
                    raise ValueError("Face 自定义控制器姿态数据无效")
                rows.extend(extra)
        if any(not isinstance(row, list) or len(row) != 3 for row in rows):
            raise ValueError("Face 构建姿态通道格式无效")
        return plan_body_build_pose(tuple(tuple(row) for row in rows))

    def read_face_build_pose_overrides(self) -> BodyBuildPoseOverrides:
        c = self._cmds
        fit = self.scene_address("FaceFitSkeleton")
        if not c.objExists(fit):
            raise ValueError("当前角色缺少 FaceFitSkeleton")
        plug = fit + ".advPyBuildPoseOverrides"
        if not c.objExists(plug):
            return BodyBuildPoseOverrides(())
        rows = json.loads(c.getAttr(plug))
        if (not isinstance(rows, list)
                or any(not isinstance(row, list) or len(row) != 3
                       for row in rows)):
            raise ValueError("Face 构建姿态覆盖数据格式无效")
        return BodyBuildPoseOverrides(tuple(BodyBuildPoseValue(*row)
                                            for row in rows))

    def read_face_build_pose(self) -> BodyBuildPosePlan:
        return merge_body_build_pose(self.read_face_build_pose_base(),
                                     self.read_face_build_pose_overrides())

    def capture_current_face_build_pose(
        self, base: BodyBuildPosePlan,
    ) -> BodyBuildPosePlan:
        c = self._cmds
        rows = [(item.node, item.attribute,
                 float(c.getAttr(item.node + "." + item.attribute)))
                for item in base.values]
        seen = set()
        for node, attribute, _ in rows:
            paths = c.ls(node, long=True, type="transform") or []
            if len(paths) != 1:
                raise ValueError("Face 构建姿态控制器不存在：" + node)
            seen.add((paths[0], attribute))
        control_set = self.scene_address("FaceControlSet")
        members = c.sets(control_set, query=True) or []
        for member in members:
            paths = c.ls(member, long=True, type="transform") or []
            if len(paths) != 1:
                raise ValueError("FaceControlSet 成员不存在或不唯一")
            node = paths[0]
            for attribute in c.listAttr(node, userDefined=True,
                                        keyable=True) or []:
                plug = node + "." + attribute
                key = (node, attribute)
                if key in seen or not c.getAttr(plug, settable=True):
                    continue
                value = c.getAttr(plug)
                if isinstance(value, (int, float, bool)):
                    rows.append((node, attribute, float(value)))
                    seen.add(key)
        return plan_body_build_pose(tuple(rows))

    def write_face_build_pose_overrides(
        self, overrides: BodyBuildPoseOverrides,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        fit = self.scene_address("FaceFitSkeleton")
        if not c.objExists(fit):
            raise ValueError("当前角色缺少 FaceFitSkeleton")
        plug = fit + ".advPyBuildPoseOverrides"
        if not c.objExists(plug):
            c.addAttr(fit, longName="advPyBuildPoseOverrides",
                      dataType="string")
        c.setAttr(plug, json.dumps(tuple((item.node, item.attribute,
                                          item.value)
                                         for item in overrides.values),
                                   separators=(",", ":")), type="string")
        self._transaction_changed = True

    def preflight_face_build_pose(self, plan: BodyBuildPosePlan) -> None:
        c = self._cmds
        control_set = self.scene_address("FaceControlSet")
        members = set(c.ls(c.sets(control_set, query=True) or [],
                           long=True, type="transform") or ())
        for item in plan.values:
            paths = c.ls(item.node, long=True, type="transform") or []
            if len(paths) != 1 or paths[0] not in members:
                raise ValueError("Face 构建姿态控制器不属于当前角色："
                                 + item.node)
            plug = paths[0] + "." + item.attribute
            if not c.objExists(plug) or not c.getAttr(plug, settable=True):
                raise ValueError("Face 构建姿态通道不可写：" + plug)

    def apply_face_build_pose(self, plan: BodyBuildPosePlan) -> None:
        self._require_transaction()
        c = self._cmds
        for item in plan.values:
            c.setAttr(item.node + "." + item.attribute, item.value)
        self._transaction_changed = True

    def capture_face_build_pose_values(self, plan: BodyBuildPosePlan) -> tuple[float, ...]:
        c = self._cmds
        return tuple(float(c.getAttr(item.node + "." + item.attribute))
                     for item in plan.values)
