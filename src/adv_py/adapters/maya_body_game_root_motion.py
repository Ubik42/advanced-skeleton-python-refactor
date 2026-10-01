"""Maya implementation of the standalone Body Root Motion command."""
from __future__ import annotations

import json
from dataclasses import fields, is_dataclass, replace

from adv_py.core.body_game_root_motion import (
    GameRootMotionInput, GameRootMotionPlan, GameRootMotionState,
)
from adv_py.core.character_registry import (
    REGISTRY_NAME, CharacterBindJoint, CharacterChannel,
    CharacterRegistration, encode_registration,
)

class MayaBodyGameRootMotionMixin:
    def _root_motion_cmds(self):
        return self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds

    def _root_motion_node(self, name: str, kind: str) -> str:
        c = self._root_motion_cmds()
        prefix = self.namespace + ":" if self.namespace else ""
        matches = c.ls(prefix + name, long=True, type=kind) or []
        if len(matches) != 1:
            raise ValueError("Root Motion 缺少唯一角色节点：" + name)
        return matches[0]

    def _root_motion_local(self, path: str) -> str:
        return (self._cmds.identity.to_local(path)
                if self.namespace else path)

    def _update_root_motion_registration(
        self, before: CharacterRegistration,
        plan: GameRootMotionPlan,
    ) -> None:
        """Rebase owned Body identities after the root joint changes parent."""
        old_root = before.body_root
        new_root = self._root_motion_local(plan.body_path)
        from .maya_source_limb_aim import rebase_registered_records
        rebase_registered_records(self,before,((old_root,new_root),))

        def rewrite(value):
            if isinstance(value, str):
                if (value == old_root or value.startswith(old_root + "|")
                        or value.startswith(old_root + ".")):
                    return new_root + value[len(old_root):]
                return value
            if isinstance(value, tuple):
                return tuple(rewrite(item) for item in value)
            if isinstance(value, list):
                return [rewrite(item) for item in value]
            if isinstance(value, dict):
                return {rewrite(key): rewrite(item)
                        for key, item in value.items()}
            if is_dataclass(value) and not isinstance(value, type):
                return replace(value, **{
                    field.name: rewrite(getattr(value, field.name))
                    for field in fields(value) if field.init})
            return value

        body = tuple(replace(
            joint, path=rewrite(joint.path),
            parent=(new_root.rsplit("|", 1)[0]
                    if joint.path == old_root else rewrite(joint.parent)))
            for joint in before.body)
        channels = tuple(rewrite(channel) for channel in before.channels)
        control = self._root_motion_local(plan.control_path)
        extra = self._root_motion_local(plan.extra_path)
        owned_controls = {control, extra}
        if plan.create:
            channels += tuple(CharacterChannel(
                "game.rootMotion." + kind + axis, control,
                kind + axis)
                for kind in ("translate", "rotate")
                for axis in "XYZ")
            channels += tuple(CharacterChannel(
                "game.rootMotion.extra." + kind + axis, extra,
                kind + axis)
                for kind in ("translate", "rotate")
                for axis in "XYZ")
            channels += (CharacterChannel(
                "game.rootMotion.followMain", control, "followMain",
                0.0, 10.0),)
        else:
            channels = tuple(channel for channel in channels
                             if channel.node not in owned_controls)
        paths = {rewrite(node.path) for node in before.nodes}
        new_nodes = {self._root_motion_local(path) for path in (
            plan.joint_path, plan.offset_path, plan.follow_path,
            plan.extra_path, plan.control_path)}
        if plan.create:
            paths.update(new_nodes)
        else:
            paths.difference_update(new_nodes)
        nodes = tuple(self._registry_node(path) for path in sorted(paths))
        updated = CharacterRegistration(
            new_root, before.container, channels, body, nodes,
            rewrite(before.spine), rewrite(before.spaces),
            rewrite(before.additional_spines),rewrite(before.source_limbs))
        document = encode_registration(updated)
        c = self._cmds
        member_plug = REGISTRY_NAME + ".members"
        c.setAttr(member_plug, lock=False)
        for index in c.getAttr(member_plug, multiIndices=True) or []:
            target = member_plug + f"[{index}]"
            source = c.connectionInfo(target, sourceFromDestination=True)
            if source:
                c.disconnectAttr(source, target)
        for index, node in enumerate(nodes):
            c.connectAttr(node.path + ".message",
                          member_plug + f"[{index}]")
        c.setAttr(member_plug, lock=True)
        document_plug = REGISTRY_NAME + ".advPyRegistryDocument"
        c.setAttr(document_plug, lock=False)
        c.setAttr(document_plug, document, type="string", lock=True)
        self.read_character_registration()

    def capture_game_root_motion_input(self) -> GameRootMotionInput:
        c = self._root_motion_cmds()
        self._root_motion_node(REGISTRY_NAME, "network")
        deformation = self._root_motion_node("DeformationSystem", "transform")
        root_system = self._root_motion_node("RootSystem", "transform")
        main_system = self._root_motion_node("MainSystem", "transform")
        main = self._root_motion_node("AdvPy_Global", "transform")
        constraint_system = self._root_motion_node(
            "ConstraintSystem", "transform")
        control_set = self._root_motion_node("ControlSet", "objectSet")
        build_pose = self._root_motion_node("buildPose", "transform")
        body = self._root_motion_node("Root_M", "joint")
        prefix = self.namespace + ":" if self.namespace else ""
        root_motion = c.ls(prefix + "RootMotion_M", long=True,
                           type="joint") or []
        if len(root_motion) > 1:
            raise ValueError("Root Motion 关节不唯一")
        if root_motion and (root_motion[0].rsplit("|", 1)[0] != deformation):
            raise ValueError("Root Motion 关节不在 DeformationSystem 下")
        if not root_motion and body.rsplit("|", 1)[0] != deformation:
            raise ValueError("Body 根不在 DeformationSystem 下")
        if root_motion and body.rsplit("|", 1)[0] != root_motion[0]:
            raise ValueError("Root Motion 未承载当前 Body 根")
        fit = self._root_motion_node("FitSkeleton", "transform")
        opm = (bool(c.getAttr(fit + ".useOffsetParentMatrix"))
               if c.attributeQuery("useOffsetParentMatrix", node=fit,
                                   exists=True) else False)
        joints = (c.listRelatives(body, allDescendents=True,
                                  fullPath=True, type="joint") or []) + [body]
        heights = [float(c.xform(path, query=True, worldSpace=True,
                                 translation=True)[1]) for path in joints]
        height = max(heights) - min(heights)
        if height <= 0:
            raise ValueError("Body 角色高度无效")
        return GameRootMotionInput(
            deformation, root_system, main_system, main,
            constraint_system, body, control_set, build_pose, prefix,
            height, opm, bool(root_motion))

    def preflight_game_root_motion(self, plan: GameRootMotionPlan) -> None:
        c = self._root_motion_cmds()
        if plan.create:
            for name in plan.node_names:
                if c.objExists(name):
                    raise ValueError("Root Motion 节点名称已占用：" + name)
        else:
            for path in (plan.joint_path, plan.offset_path,
                         plan.follow_path, plan.extra_path,
                         plan.control_path):
                if not c.objExists(path):
                    raise ValueError("Root Motion 控制层缺失：" + path)
            for path in (plan.joint_path, plan.control_path):
                if (not c.attributeQuery("advPyGameRootMotionOwner",
                                         node=path, exists=True)
                        or c.getAttr(path + ".advPyGameRootMotionOwner")
                        != "advanced-skeleton-python-refactor"):
                    raise ValueError("Root Motion 节点不属于当前实现：" + path)
            children = c.listRelatives(
                plan.joint_path, children=True,
                fullPath=True) or []
            if set(children) != {plan.source.body_root}:
                raise ValueError("Root Motion 关节有未知子级，不能删除")
            follow_constraint = c.ls(
                plan.follow_constraint_name, long=True,
                type="parentConstraint") or []
            if len(follow_constraint) != 1:
                raise ValueError("Root Motion 跟随约束缺失或歧义")
            expected_children = (
                (plan.offset_path, {plan.follow_path}),
                (plan.follow_path,
                 {plan.extra_path, follow_constraint[0]}),
                (plan.extra_path, {plan.control_path}),
            )
            for path, expected in expected_children:
                actual = set(c.listRelatives(
                    path, children=True, fullPath=True) or [])
                if actual != expected:
                    raise ValueError("Root Motion 控制层含未知子节点：" + path)
            shapes = c.listRelatives(
                plan.control_path, children=True,
                fullPath=True) or []
            if (len(shapes) != 1 or
                    c.nodeType(shapes[0]) != "nurbsCurve"):
                raise ValueError("Root Motion 控制器含未知子节点")
            for path in (plan.offset_path, plan.follow_path):
                if (c.keyframe(path, query=True,
                               keyframeCount=True) or 0) > 0:
                    raise ValueError("Root Motion 控制父层已有动画：" + path)
            for path in (plan.control_path, plan.extra_path):
                if (c.keyframe(path, query=True, keyframeCount=True) or 0) > 0:
                    raise ValueError("Root Motion 控制器已有动画，不能删除：" + path)
                for kind, wanted in (("translate", 0.0),
                                     ("rotate", 0.0), ("scale", 1.0)):
                    if any(abs(float(c.getAttr(path + "." + kind + axis))
                               - wanted) > 1e-6 for axis in "XYZ"):
                        raise ValueError(
                            "Root Motion 控制器未归零，不能删除：" + path)
            if abs(float(c.getAttr(
                    plan.control_path + ".followMain"))) > 1e-6:
                raise ValueError("Root Motion followMain 未归零，不能删除")
        for path in (plan.source.body_root, plan.source.control_set,
                     plan.source.build_pose, plan.source.deformation,
                     plan.source.root_system, plan.source.main_system):
            if c.referenceQuery(path, isNodeReferenced=True):
                raise ValueError("引用角色节点不能修改 Root Motion：" + path)

    def _root_motion_pose_rows(self, plan: GameRootMotionPlan,
                               *, create: bool) -> None:
        c = self._root_motion_cmds()
        plug = plan.source.build_pose + ".advPyPoseData"
        rows = json.loads(c.getAttr(plug))
        if (not isinstance(rows, list)
                or any(not isinstance(row, list) or len(row) != 3
                       for row in rows)):
            raise ValueError("Root Motion 构建姿态记录无效")
        owned = {plan.control_path, plan.extra_path}
        rows = [row for row in rows if row[0] not in owned]
        if create:
            for path in (plan.control_path, plan.extra_path):
                for attr in ("translateX", "translateY", "translateZ",
                             "rotateX", "rotateY", "rotateZ",
                             "scaleX", "scaleY", "scaleZ"):
                    plug_name = path + "." + attr
                    if (c.getAttr(plug_name, keyable=True)
                            and c.getAttr(plug_name, settable=True)):
                        rows.append([path, attr, float(c.getAttr(plug_name))])
            rows.append([plan.control_path, "followMain", 0.0])
        c.setAttr(plug, json.dumps(rows, separators=(",", ":")),
                  type="string")
        if not create:
            fit = self._root_motion_node("FitSkeleton", "transform")
            override_plug = fit + ".advPyBuildPoseOverrides"
            if c.objExists(override_plug):
                overrides = json.loads(c.getAttr(override_plug))
                if not isinstance(overrides, list):
                    raise ValueError("Root Motion 构建姿态覆盖记录无效")
                overrides = [row for row in overrides
                             if not (isinstance(row, list)
                                     and row and row[0] in owned)]
                c.setAttr(override_plug,
                          json.dumps(overrides, separators=(",", ":")),
                          type="string")

    def apply_game_root_motion(self, plan: GameRootMotionPlan) -> None:
        self._require_transaction()
        c = self._root_motion_cmds()
        registration = self.read_character_registration()
        before_world = tuple(c.xform(
            plan.source.body_root, query=True, worldSpace=True,
            matrix=True))
        self._transaction_changed = True
        if not plan.create:
            body = c.parent(plan.source.body_root, plan.source.deformation,
                            absolute=True)[0]
            if (c.ls(body, long=True, type="joint") or []) != [plan.body_path]:
                raise RuntimeError("Root Motion 删除后 Body 父级漂移")
            self._root_motion_pose_rows(plan, create=False)
            if c.objExists(plan.body_constraint_name):
                c.delete(plan.body_constraint_name)
            c.delete(plan.offset_path)
            c.delete(plan.joint_path)
            for name in (plan.range_name, plan.matrix_name):
                if c.objExists(name):
                    c.delete(name)
            after_world = tuple(c.xform(
                plan.body_path, query=True, worldSpace=True,
                matrix=True))
            if max(abs(a - b) for a, b in zip(
                    before_world, after_world)) > 1e-5:
                raise RuntimeError("Root Motion 删除改变了 Body 世界姿态")
            self._update_root_motion_registration(registration, plan)
            return
        joint = c.createNode("joint", name=plan.node_names[0],
                             parent=plan.source.deformation,
                             skipSelect=True)
        c.setAttr(joint + ".segmentScaleCompensate", False)
        c.addAttr(joint, longName="advPyGameRootMotionOwner",
                  dataType="string")
        c.setAttr(joint + ".advPyGameRootMotionOwner",
                  "advanced-skeleton-python-refactor", type="string",
                  lock=True)
        body = c.parent(plan.source.body_root, joint, absolute=True)[0]
        if ((c.ls(joint, long=True, type="joint") or []) != [plan.joint_path]
                or (c.ls(body, long=True, type="joint") or []) != [plan.body_path]):
            raise RuntimeError("Root Motion Body 关节改挂失败")
        after_world = tuple(c.xform(
            body, query=True, worldSpace=True, matrix=True))
        if max(abs(a - b) for a, b in zip(
                before_world, after_world)) > 1e-5:
            raise RuntimeError("Root Motion 创建改变了 Body 世界姿态")
        offset = c.createNode("transform", name=plan.node_names[1],
                              parent=plan.source.root_system,
                              skipSelect=True)
        follow = c.createNode("transform", name=plan.node_names[2],
                              parent=offset, skipSelect=True)
        extra = c.createNode("transform", name=plan.node_names[3],
                             parent=follow, skipSelect=True)
        control = c.circle(name=plan.node_names[4], normal=(0, 1, 0),
                           radius=plan.radius,
                           constructionHistory=False)[0]
        control = c.parent(control, extra, relative=True)[0]
        for actual, expected in ((offset, plan.offset_path),
                                 (follow, plan.follow_path),
                                 (extra, plan.extra_path),
                                 (control, plan.control_path)):
            if (c.ls(actual, long=True, type="transform") or []) != [expected]:
                raise RuntimeError("Root Motion 控制层路径漂移")
        c.addAttr(control, longName="advPyGameRootMotionOwner",
                  dataType="string")
        c.setAttr(control + ".advPyGameRootMotionOwner",
                  "advanced-skeleton-python-refactor", type="string",
                  lock=True)
        shapes = c.listRelatives(control, shapes=True, fullPath=True,
                                 noIntermediate=True, type="nurbsCurve") or []
        if len(shapes) != 1:
            raise RuntimeError("Root Motion 控制曲线缺失")
        c.setAttr(shapes[0] + ".overrideEnabled", True)
        c.setAttr(shapes[0] + ".overrideColor", 17)
        for path in (extra, control):
            for attribute in ("scaleX", "scaleY", "scaleZ", "visibility"):
                c.setAttr(path + "." + attribute,
                          keyable=False, lock=True)
        c.sets((control, extra), add=plan.source.control_set)
        if plan.source.use_offset_parent_matrix:
            matrix = c.createNode("multMatrix", name=plan.matrix_name)
            c.connectAttr(control + ".worldMatrix[0]",
                          matrix + ".matrixIn[0]")
            c.connectAttr(joint + ".parentInverseMatrix[0]",
                          matrix + ".matrixIn[1]")
            c.connectAttr(matrix + ".matrixSum",
                          joint + ".offsetParentMatrix")
        else:
            driven = c.parentConstraint(control, joint,
                                        maintainOffset=False,
                                        name=plan.body_constraint_name)
            if len(driven) != 1:
                raise RuntimeError("Root Motion 关节约束创建失败")
            c.parent(driven[0], plan.source.constraint_system,
                     absolute=True)
        follow_constraint = c.parentConstraint(
            plan.source.main_control, plan.source.main_system, follow,
            maintainOffset=False, name=plan.follow_constraint_name)
        if len(follow_constraint) != 1:
            raise RuntimeError("Root Motion 跟随约束创建失败")
        aliases = c.parentConstraint(follow_constraint[0], query=True,
                                      weightAliasList=True) or []
        if len(aliases) != 2:
            raise RuntimeError("Root Motion 跟随权重缺失")
        c.addAttr(control, longName="followMain", attributeType="double",
                  minValue=0, maxValue=10, defaultValue=0, keyable=True)
        value_range = c.createNode("setRange", name=plan.range_name)
        for attr, value in (("maxX", 1), ("minY", 1),
                            ("oldMaxX", 10), ("oldMaxY", 10)):
            c.setAttr(value_range + "." + attr, value)
        for axis in "XY":
            c.connectAttr(control + ".followMain",
                          value_range + ".value" + axis)
        c.connectAttr(value_range + ".outValueX",
                      follow_constraint[0] + "." + aliases[0])
        c.connectAttr(value_range + ".outValueY",
                      follow_constraint[0] + "." + aliases[1])
        self._root_motion_pose_rows(plan, create=True)
        self._update_root_motion_registration(registration, plan)

    def capture_game_root_motion(self, plan: GameRootMotionPlan
                                 ) -> GameRootMotionState:
        c = self._root_motion_cmds()
        def existing(path: str) -> str | None:
            return path if c.objExists(path) else None
        control = existing(plan.control_path)
        if control:
            shapes = c.listRelatives(
                control, shapes=True, fullPath=True,
                noIntermediate=True, type="nurbsCurve") or []
            if (len(shapes) != 1
                    or not c.getAttr(shapes[0] + ".overrideEnabled")
                    or int(c.getAttr(shapes[0] + ".overrideColor")) != 17):
                control = None
        members = c.sets(plan.source.control_set, query=True) or []
        member_paths = {match for member in members
                        for match in (c.ls(member, long=True) or [])}
        pose_rows = json.loads(c.getAttr(
            plan.source.build_pose + ".advPyPoseData"))
        in_pose = any(row[0] == plan.control_path for row in pose_rows)
        locked_controls = all(
            c.getAttr(path + "." + attribute, lock=True)
            and not c.getAttr(path + "." + attribute, keyable=True)
            for path in (plan.control_path, plan.extra_path)
            if c.objExists(path)
            for attribute in ("scaleX", "scaleY", "scaleZ", "visibility"))
        locked_controls = locked_controls and bool(
            control and c.objExists(plan.extra_path))
        follow_constraints = (c.ls(plan.follow_constraint_name,
                                   type="parentConstraint") or [])
        aliases = (c.parentConstraint(
            follow_constraints[0], query=True, weightAliasList=True) or []
            if len(follow_constraints) == 1 else [])
        follow_valid = (control is not None
                        and c.objExists(plan.range_name)
                        and len(aliases) == 2
                        and c.isConnected(control + ".followMain",
                                          plan.range_name + ".valueX")
                        and c.isConnected(control + ".followMain",
                                          plan.range_name + ".valueY")
                        and c.isConnected(
                            plan.range_name + ".outValueX",
                            follow_constraints[0] + "." + aliases[0])
                        and c.isConnected(
                            plan.range_name + ".outValueY",
                            follow_constraints[0] + "." + aliases[1]))
        follow_source = control + ".followMain" if follow_valid else None
        if not c.objExists(plan.joint_path):
            body_driver = None
        elif plan.source.use_offset_parent_matrix:
            body_driver = (c.connectionInfo(
                plan.joint_path + ".offsetParentMatrix",
                sourceFromDestination=True) or None)
            if (body_driver != plan.matrix_name + ".matrixSum"
                    or not control
                    or not c.isConnected(
                        control + ".worldMatrix[0]",
                        plan.matrix_name + ".matrixIn[0]")
                    or not c.isConnected(
                        plan.joint_path + ".parentInverseMatrix[0]",
                        plan.matrix_name + ".matrixIn[1]")):
                body_driver = None
        else:
            parents = c.listConnections(plan.joint_path + ".translateX",
                                        source=True, destination=False,
                                        type="parentConstraint") or []
            matching = [node for node in parents
                        if node.rsplit("|", 1)[-1]
                        == plan.body_constraint_name]
            targets = (c.parentConstraint(
                matching[0], query=True, targetList=True) or []
                if len(matching) == 1 else [])
            target_paths = [path for target in targets
                            for path in (c.ls(target, long=True) or [])]
            body_driver = (control if target_paths == [control] else None)
        body = plan.body_path if c.objExists(plan.body_path) else ""
        return GameRootMotionState(
            existing(plan.joint_path), body,
            existing(plan.offset_path), existing(plan.follow_path),
            existing(plan.extra_path), control, follow_source,
            body_driver, control in member_paths if control else False,
            in_pose,
            tuple(name for name in plan.node_names
                  if c.objExists(name)) if not plan.create else (),
            locked_controls)
