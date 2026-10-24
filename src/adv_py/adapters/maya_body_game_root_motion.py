"""Maya implementation of the standalone Body Root Motion command."""
from __future__ import annotations

import json
from dataclasses import replace

from adv_py.core.body_game_root_motion import (
    GameRootMotionInput, GameRootMotionPlan, GameRootMotionState,
)
from adv_py.core.character_registry import (
    REGISTRY_NAME, CharacterChannel,
    CharacterRegistration, encode_registration,
)
from .maya_source_parent_inverse import parent_world_inverse

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
        if before is None:
            return
        new_root = self._root_motion_local(plan.body_path)
        from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
        from .maya_original_control_orient import _by_uuid, _parent
        removed_paths = set() if plan.create else {
            self._root_motion_local(value) for value in (
                plan.joint_path, plan.offset_path, plan.follow_path,
                plan.extra_path, plan.control_path)}
        rewrites = []
        retained = []
        for node in before.nodes:
            try:
                current = _by_uuid(self, node.uuid)
            except ValueError:
                offset = self._root_motion_local(plan.offset_path)
                if not plan.create and (node.path in removed_paths or node.path.startswith(offset + '|')):
                    removed_paths.add(node.path)
                    continue
                raise
            if self._cmds.nodeType(current) != node.node_type:
                raise ValueError("Root Motion 改变了原节点类型")
            retained.append(node)
            if current != node.path:
                rewrites.append((node.path, current))
        mapping = FitPartFinalPaths((), (), tuple(rewrites))
        if not plan.create:
            from .maya_game_scaling_state import remember_removed_joints
            remember_removed_joints(self, removed_paths)
        from .maya_driving_registration import _rebase_records
        _rebase_records(self, replace(before, nodes=tuple(retained)), mapping, (), None)
        def rewrite(value):
            return rebase_plan_paths_after_parts(value, mapping)

        body = tuple(replace(
            joint, path=rewrite(joint.path),
            parent=_parent(self._cmds, rewrite(joint.path)))
            for joint in before.body)
        channels = tuple(rewrite(channel) for channel in before.channels)
        control = self._root_motion_local(plan.control_path)
        extra = self._root_motion_local(plan.extra_path)
        owned_controls = {control, extra}
        if plan.create:
            key_prefix = "game.rootMotion."
            if any(channel.key.startswith(key_prefix) for channel in channels):
                key_prefix += plan.source.root_joint_name + "."
            channels += tuple(CharacterChannel(
                key_prefix + kind + axis, control,
                kind + axis)
                for kind in ("translate", "rotate")
                for axis in "XYZ")
            channels += tuple(CharacterChannel(
                key_prefix + "extra." + kind + axis, extra,
                kind + axis)
                for kind in ("translate", "rotate")
                for axis in "XYZ")
            channels += (CharacterChannel(
                key_prefix + "followMain", control, "followMain",
                0.0, 10.0),)
        else:
            channels = tuple(channel for channel in channels
                             if channel.node not in owned_controls and channel.node not in removed_paths)
        paths = {rewrite(node.path) for node in retained}
        new_nodes = {self._root_motion_local(path) for path in (
            plan.joint_path, plan.offset_path, plan.follow_path,
            plan.extra_path, plan.control_path)}
        if plan.create:
            paths.update(new_nodes)
        else:
            paths.difference_update(new_nodes)
        # Preserve existing member order so create/delete restores the exact
        # original registration, including previously appended Part nodes.
        ordered_paths = tuple(rewrite(node.path) for node in retained
                              if rewrite(node.path) in paths)
        ordered_paths += tuple(sorted(paths.difference(ordered_paths)))
        user_plugs = {channel.node + "." + channel.attribute for channel in channels}
        nodes = tuple(replace(node, inputs=tuple(
            (attribute, source) for attribute, source in node.inputs
            if not (node.path + "." + attribute in user_plugs
                    and self._character_direct_animation(source))))
            for node in (self._registry_node(path) for path in ordered_paths))
        updated = CharacterRegistration(
            new_root, before.container, channels, body, nodes,
            rewrite(before.spine), rewrite(before.spaces),
            rewrite(before.additional_spines),rewrite(before.source_limbs),rewrite(before.retired_body))
        document = encode_registration(updated)
        c = self._cmds
        member_plug = REGISTRY_NAME + ".members"
        c.setAttr(member_plug, lock=False)
        for index in c.getAttr(member_plug, multiIndices=True) or []:
            target = member_plug + f"[{index}]"
            # A saved multi attribute can retain element locks after its
            # parent is unlocked. Unlock the exact member before rewiring.
            c.setAttr(target, lock=False)
            source = c.connectionInfo(target, sourceFromDestination=True)
            if source:
                c.disconnectAttr(source, target)
        for index, node in enumerate(nodes):
            target = member_plug + f"[{index}]"
            c.setAttr(target, lock=False)
            c.connectAttr(node.path + ".message", target)
        c.setAttr(member_plug, lock=True)
        document_plug = REGISTRY_NAME + ".advPyRegistryDocument"
        c.setAttr(document_plug, lock=False)
        c.setAttr(document_plug, document, type="string", lock=True)
        self.read_character_registration()

    def capture_game_root_motion_creation_input(self) -> GameRootMotionInput:
        return self._capture_game_root_motion_input(for_creation=True)

    def capture_game_root_motion_input(self) -> GameRootMotionInput:
        return self._capture_game_root_motion_input(for_creation=False)

    def _capture_game_root_motion_input(self, *, for_creation: bool) -> GameRootMotionInput:
        c = self._root_motion_cmds()
        if self._cmds.objExists(REGISTRY_NAME):
            self._root_motion_node(REGISTRY_NAME, "network")
        deformation = self._root_motion_node("DeformationSystem", "transform")
        root_system = self._root_motion_node("RootSystem", "transform")
        main_system = self._root_motion_node("MainSystem", "transform")
        from .maya_original_control_identity import source_main, original_character_height
        main = self.scene_address(source_main(self))
        constraint_system = self._root_motion_node(
            "ConstraintSystem", "transform")
        control_set = self._root_motion_node("ControlSet", "objectSet")
        build_pose = self._root_motion_node("buildPose", "transform")
        body = self._root_motion_node("Root_M", "joint")
        prefix = self.namespace + ":" if self.namespace else ""
        root_name = "RootMotion_M"
        options = prefix + "asCreateGameEngineRootMotionOptions"
        if for_creation and c.objExists(options + ".useOldRootName"):
            root_name = "root"
        elif not for_creation and not c.objExists(prefix + root_name) and c.objExists(prefix + "root"):
            root_name = "root"
        root_motion = c.ls(prefix + root_name, long=True, type="joint") or []
        if len(root_motion) > 1:
            raise ValueError("Root Motion 关节不唯一")
        if root_motion and not root_motion[0].startswith(deformation + '|'):
            raise ValueError("Root Motion 关节不在 DeformationSystem 下")
        if not body.startswith(deformation + "|"):
            raise ValueError("Body 根不在 DeformationSystem 下")
        fit = self._root_motion_node("FitSkeleton", "transform")
        opm = (bool(c.getAttr(fit + ".useOffsetParentMatrix"))
               if c.attributeQuery("useOffsetParentMatrix", node=fit,
                                   exists=True) else False)
        # asgetCharHeight reads Main.height, including its zero fallback. The
        # source does not estimate the joint bounding box or clamp the radius.
        height = original_character_height(c, self.namespace or '')
        parent = deformation if for_creation else (root_motion[0] if root_motion else deformation)
        children = tuple(c.listRelatives(parent, children=True,
                                         fullPath=True, type="joint") or [])
        range_name = None
        if root_motion and c.objExists(root_motion[0] + '.advPyGameRootMotionRange'):
            range_name = self.scene_address(c.getAttr(root_motion[0] + '.advPyGameRootMotionRange'))
        constraint_name = None
        if root_motion and c.objExists(root_motion[0] + '.advPyGameRootMotionConstraint'):
            constraint_name = self.scene_address(c.getAttr(root_motion[0] + '.advPyGameRootMotionConstraint'))
        return GameRootMotionInput(
            deformation, root_system, main_system, main,
            constraint_system, body, control_set, build_pose, prefix,
            height, opm, bool(root_motion), root_name, children, range_name, constraint_name,
            root_motion[0] if root_motion else None)

    def preflight_game_root_motion(self, plan: GameRootMotionPlan) -> None:
        c = self._root_motion_cmds()
        if plan.create:
            for name in plan.node_names:
                if name in (plan.range_name, plan.matrix_name, plan.body_constraint_name,
                            plan.offset_path.rsplit('|', 1)[-1]):
                    # Source deletes the prior Offset, reuses the MM and
                    # keeps the literal Range target used by the source.
                    continue
                if c.objExists(name):
                    raise ValueError("Root Motion 节点名称已占用：" + name)
        else:
            if not c.objExists(plan.joint_path):
                raise ValueError("Root Motion 关节缺失：" + plan.joint_path)
            for path in (plan.joint_path, plan.control_path):
                if not c.objExists(path):
                    continue
                if (c.attributeQuery("advPyGameRootMotionOwner",
                                         node=path, exists=True)
                        and c.getAttr(path + ".advPyGameRootMotionOwner")
                        != "advanced-skeleton-python-refactor"):
                    raise ValueError("Root Motion 节点不属于当前实现：" + path)
            # Source deletion moves all joint children back and removes the
            # complete FKOffset hierarchy. It does not impose zero-pose,
            # animation, curve-count or CustomOrient layout restrictions.
        for path in (plan.source.body_root, plan.source.control_set,
                     plan.source.build_pose, plan.source.deformation,
                     plan.source.root_system, plan.source.main_system):
            if c.referenceQuery(path, isNodeReferenced=True):
                raise ValueError("引用角色节点不能修改 Root Motion：" + path)

    def _root_motion_pose_rows(self, plan: GameRootMotionPlan,
                               *, create: bool) -> None:
        c = self._root_motion_cmds()
        plug = plan.source.build_pose + ".advPyPoseData"
        has_pose_data = c.objExists(plug)
        rows = json.loads(c.getAttr(plug)) if has_pose_data else []
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
            # Source adds these two TRS commands to udExtraAttr. It does not
            # introduce a separate followMain reset into this command.
            command_plug = plan.source.build_pose + '.udExtraAttr'
            if not c.objExists(command_plug):
                c.addAttr(plan.source.build_pose, longName='udExtraAttr', dataType='string')
            command = c.getAttr(command_plug) or ''
            root_name = plan.source.root_joint_name
            command += ('xform -os -t 0 0 0 -ro 0 0 0 -s 1 1 1 FK' + root_name + ';'
                        'xform -os -t 0 0 0 -ro 0 0 0 -s 1 1 1 FKExtra' + root_name + ';')
            c.setAttr(command_plug, command, type='string')
        if has_pose_data:
            c.setAttr(plug, json.dumps(rows, separators=(",", ":")), type="string")
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

    def apply_game_root_motion(self, plan: GameRootMotionPlan) -> GameRootMotionPlan:
        self._require_transaction()
        c = self._root_motion_cmds()
        from .maya_game_registration import source_registration
        registration = source_registration(self)
        if registration is not None:
            registration = self.read_character_registration()
        from .maya_game_registration import scene_ids, remember_generated_nodes
        ids_before = scene_ids(self)
        self._transaction_changed = True
        if not plan.create:
            children = plan.source.deformation_children
            if children is None:
                children = (plan.source.body_root,)
            if children:
                c.parent(children, plan.source.deformation, absolute=True)
            body = plan.body_path
            if (c.ls(body, long=True, type="joint") or []) != [plan.body_path]:
                raise RuntimeError("Root Motion 删除后 Body 父级漂移")
            from .maya_source_body_matrix import rebase_fk_records
            if registration is not None:
                rebase_fk_records(self,registration,((registration.body_root,
                    self._root_motion_local(plan.body_path)),),
                    root_parent_inverse=self._root_motion_local(plan.source.deformation) + '.worldInverseMatrix[0]')
            self._root_motion_pose_rows(plan, create=False)
            c.delete(plan.joint_path)
            prefix = plan.source.namespace_prefix
            for name in (prefix + 'root_parentConstraint1', prefix + 'RootMotion_parentConstraint1'):
                if c.objExists(name):
                    c.delete(name)
            if c.objExists(plan.offset_path):
                c.delete(plan.offset_path)
            if plan.source.use_offset_parent_matrix and c.objExists(prefix + 'RootMM_M'):
                c.connectAttr(plan.source.deformation + '.worldInverseMatrix[0]',
                              prefix + 'RootMM_M.matrixIn[2]', force=True)
            self._update_root_motion_registration(registration, plan)
            c.select(clear=True)
            return plan
        options = plan.source.namespace_prefix + 'asCreateGameEngineRootMotionOptions'
        if c.objExists(options + '.useOldRootName'):
            c.delete(options)
        c.select(clear=True)
        joint = self.scene_address(self._cmds.joint(name=self._root_motion_local(plan.node_names[0])))
        joint = c.parent(joint, plan.source.deformation, absolute=True)[0]
        c.setAttr(joint + ".segmentScaleCompensate", False)
        c.addAttr(joint, longName="advPyGameRootMotionOwner",
                  dataType="string")
        c.setAttr(joint + ".advPyGameRootMotionOwner",
                  "advanced-skeleton-python-refactor", type="string",
                  lock=True)
        children = plan.source.deformation_children
        if children is None:
            children = (plan.source.body_root,)
        if children:
            c.parent(children, joint, absolute=True)
        body = plan.body_path
        if ((c.ls(joint, long=True, type="joint") or []) != [plan.joint_path]
                or (c.ls(body, long=True, type="joint") or []) != [plan.body_path]):
            raise RuntimeError("Root Motion Body 关节改挂失败")
        from .maya_source_body_matrix import rebase_fk_records
        if registration is not None:
            rebase_fk_records(self,registration,((registration.body_root,
                self._root_motion_local(plan.body_path)),),
                root_parent_inverse=self._root_motion_local(plan.joint_path) + '.worldInverseMatrix[0]')
        if c.objExists(plan.node_names[1]):
            c.delete(plan.node_names[1])
        def create_frame(name, parent):
            return self.scene_address(self._cmds.createNode('transform',
                name=self._root_motion_local(name), parent=self._root_motion_local(parent), skipSelect=True))
        offset = create_frame(plan.node_names[1], plan.source.root_system)
        follow = create_frame(plan.node_names[2], offset)
        extra = create_frame(plan.node_names[3], follow)
        control = self._cmds.circle(name=self._root_motion_local(plan.node_names[4]), normal=(0, 1, 0),
                           radius=plan.radius,
                           degree=3, sweep=360, sections=8,
                           useTolerance=False, tolerance=0.000393701,
                           constructionHistory=False)[0]
        control = c.parent(self.scene_address(control), extra, absolute=True)[0]
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
            from adv_py.core.body_parent_constraint import plan_body_parent_constraint
            source = self.capture_parent_constraint_input(
                self._root_motion_local(plan.control_path),
                self._root_motion_local(plan.joint_path), False)
            constraint = plan_body_parent_constraint(replace(source, use_offset_parent_matrix=True))
            self.create_parent_constraint(constraint)
            prefix = plan.source.namespace_prefix
            if c.objExists(prefix + 'RootMM_M'):
                c.connectAttr(plan.joint_path + '.worldInverseMatrix[0]',
                              prefix + 'RootMM_M.matrixIn[2]', force=True)
        else:
            driven = self._cmds.parentConstraint(self._root_motion_local(plan.control_path),
                                        self._root_motion_local(plan.joint_path),
                                        maintainOffset=False,
                                        name=self._root_motion_local(plan.body_constraint_name))
            if len(driven) != 1:
                raise RuntimeError("Root Motion 关节约束创建失败")
            # MEL moves the literal first constraint if it exists, even when
            # Maya gave this invocation a higher suffix after a prior delete.
            named = plan.source.namespace_prefix + plan.source.root_joint_name + '_parentConstraint1'
            if c.objExists(named):
                c.parent(named, plan.source.constraint_system, absolute=True)
            plan = replace(plan, body_constraint_name=self.scene_address(driven[0]))
            c.addAttr(plan.joint_path, longName='advPyGameRootMotionConstraint', dataType='string')
            c.setAttr(plan.joint_path + '.advPyGameRootMotionConstraint', self._root_motion_local(driven[0]),
                      type='string', lock=True)
        follow_constraint = self._cmds.parentConstraint(
            self._root_motion_local(plan.source.main_control),
            self._root_motion_local(plan.source.main_system), self._root_motion_local(plan.follow_path),
            maintainOffset=False, name=self._root_motion_local(plan.follow_constraint_name))
        follow_constraint = tuple(self.scene_address(node) for node in follow_constraint)
        if len(follow_constraint) != 1:
            raise RuntimeError("Root Motion 跟随约束创建失败")
        aliases = c.parentConstraint(follow_constraint[0], query=True,
                                      weightAliasList=True) or []
        if len(aliases) != 2:
            raise RuntimeError("Root Motion 跟随权重缺失")
        c.addAttr(control, longName="followMain", attributeType="double",
                  minValue=0, maxValue=10, defaultValue=0, keyable=True)
        self._cmds.createNode('setRange', name=self._root_motion_local(plan.range_name))
        # MEL addresses the literal Range name for all subsequent writes. On
        # recreate Maya can create Range1 while the retained Range is reused.
        value_range = plan.range_name
        c.addAttr(plan.joint_path, longName='advPyGameRootMotionRange', dataType='string')
        c.setAttr(plan.joint_path + '.advPyGameRootMotionRange', self._root_motion_local(value_range),
                  type='string', lock=True)
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
        remember_generated_nodes(self, ids_before)
        c.select(clear=True)
        return plan

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
        pose_plug = plan.source.build_pose + ".advPyPoseData"
        if c.objExists(pose_plug):
            pose_rows = json.loads(c.getAttr(pose_plug))
            in_pose = any(row[0] == plan.control_path for row in pose_rows)
        else:
            command = c.getAttr(plan.source.build_pose + '.udExtraAttr') or ''
            in_pose = 'FK' + plan.source.root_joint_name + ';' in command
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
                        parent_world_inverse(self, plan.joint_path),
                        plan.matrix_name + ".matrixIn[1]")):
                body_driver = None
        else:
            parents = c.listConnections(plan.joint_path + ".translateX",
                                        source=True, destination=False,
                                        type="parentConstraint") or []
            matching = [node for node in parents
                        if node.rsplit("|", 1)[-1]
                        == plan.body_constraint_name.rsplit("|", 1)[-1]]
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
            # Source deletion leaves Range/MM dependency nodes in the scene.
            # Only the removed joint and control hierarchy are audited here.
            tuple(name for name in plan.node_names[:5]
                  if c.objExists(name)) if not plan.create else (),
            locked_controls)
