from dataclasses import replace

from adv_py.core.body_parent_constraint import (
    audit_body_parent_constraint, plan_body_parent_constraint)
from adv_py.core.body_torso import (
    BodySpaceAttachmentState, BodyTorsoSnapshot,
    torso_opm_attachment_nodes)
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_adv_icons import create_adv_icon


class MayaBodyTorsoMixin:
    """Torso operations share the owning MayaBodyBuildHost transaction."""

    def _preflight_torso_channels(self, node, attributes):
        matches = self._cmds.ls(node, long=True) or []
        if (matches != [node] or self._cmds.referenceQuery(node, isNodeReferenced=True)
                or any(self._cmds.lockNode(node, query=True, lock=True) or [])):
            raise FitSkeletonValidationError(f"Torso 对象不可编辑：{node}")
        for attr in attributes:
            plug = f"{node}.{attr}"
            if (not self._cmds.getAttr(plug, settable=True)
                    or self._cmds.listConnections(plug, source=True, destination=False)):
                raise FitSkeletonValidationError(f"Torso 通道已有输入或锁定：{plug}")

    def preflight_body_torso(self, plan):
        if type(plan.use_offset_parent_matrix) is not bool:
            raise FitSkeletonValidationError("Torso OPM 开关无效")
        outer = plan.cogs[0] if plan.cogs else plan.root_x
        if outer is not None:
            parent = outer.offset_path.rsplit("|", 1)[0]
            if self._cmds.ls(parent, long=True, type="transform") != [parent]:
                raise FitSkeletonValidationError("根控制层缺少 RootFollowMain 父级")
        if plan.use_offset_parent_matrix:
            for spec in plan.attachments:
                if spec.kind == "parentConstraint" and not spec.translation_only:
                    for name in torso_opm_attachment_nodes(spec):
                        if self.find_name_collisions(name):
                            raise FitSkeletonValidationError(
                                "Torso OPM 节点名称冲突：" + name)
        planned_joints = {j.path for j in plan.spine.joints} if plan.spine else set()
        if plan.spline:
            planned_joints.update(j.path for j in plan.spline.joints)
            for target in plan.spline.body_joints[1:]:
                self._preflight_torso_channels(target,tuple(kind+axis for kind in ('translate','rotate','scale') for axis in 'XYZ'))
        if plan.spine:
            for target in plan.spine.body_joints[1:]:
                self._preflight_torso_channels(target, tuple(kind + axis for kind in ("translate", "rotate") for axis in "XYZ"))
        for spec in plan.controls.controls:
            if spec.driven_joint in planned_joints:
                continue
            attributes = tuple(f"rotate{axis}" for axis in "XYZ")
            if spec.translation_constraint_name is not None:
                attributes += tuple(f"translate{axis}" for axis in "XYZ")
            if spec.driven_joint == plan.pelvis_translation.target:
                attributes += tuple(f"{kind}{axis}" for kind in ("translate", "scale") for axis in "XYZ")
            self._preflight_torso_channels(spec.driven_joint, attributes)

    def create_body_torso(self, plan):
        self._require_transaction()
        self.preflight_body_torso(plan)
        if any(self.find_name_collisions(name) for name in plan.node_names):
            raise FitSkeletonValidationError("Torso 名称在执行前发生冲突")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            for spec in (*plan.cogs,
                         *((plan.root_x,) if plan.root_x is not None else ())):
                root_x = spec is plan.root_x
                self._transaction_changed = True
                offset = self._cmds.createNode(
                    "transform", name=spec.offset_name,
                    parent=spec.offset_path.rsplit("|", 1)[0],
                    skipSelect=True)
                offset = (self._cmds.ls(offset, long=True) or [offset])[0]
                if offset != spec.offset_path:
                    raise RuntimeError("根控制 Offset 路径漂移")
                self._cmds.xform(offset, worldSpace=True,
                                 translation=spec.world_position)
                extra = self._cmds.createNode(
                    "transform", name=spec.extra_name, parent=offset,
                    skipSelect=True)
                extra = (self._cmds.ls(extra, long=True) or [extra])[0]
                if extra != spec.extra_path:
                    raise RuntimeError("根控制 Extra 路径漂移")
                control = create_adv_icon(
                    self._cmds, name=spec.control_name, parent=extra,
                    template="Root_icon" if root_x else "COG_icon",
                    radius=spec.radius,
                    fallback_normal=(0.0, 1.0, 0.0))
                if control != spec.control_path:
                    raise RuntimeError("根控制路径漂移")
                if root_x:
                    self._cmds.setAttr(control + ".rotateOrder", 3)
            created_root = self.create_body_control_root(
                plan.controls.root_name,
                parent_path=plan.controls.root_path.rsplit("|", 1)[0]
                if plan.root_x is not None else None)
            if created_root != plan.controls.root_path:
                raise RuntimeError("Torso 控制根路径漂移")
            if plan.spine:
                self.prepare_body_spine(plan.spine)
            if plan.spline:
                from .maya_spline import prepare
                prepare(self,plan.spline)
            for spec in plan.controls.controls:
                self._create_body_limb_fk_control(spec, "Torso")
                locked = [f"scale{axis}" for axis in "XYZ"]
                if spec.driven_joint != plan.pelvis_translation.target:
                    locked += [f"translate{axis}" for axis in "XYZ"]
                for attr in locked:
                    self._cmds.setAttr(f"{spec.control_path}.{attr}", lock=True, keyable=False)
            lock = plan.leg_lock
            lock_path = self._cmds.createNode(
                "transform", name=lock.path.rsplit("|", 1)[-1],
                parent=lock.path.rsplit("|", 1)[0], skipSelect=True)
            lock_path = (self._cmds.ls(lock_path, long=True)
                         or [lock_path])[0]
            if lock_path != lock.path:
                raise RuntimeError("腿部锁定空间路径漂移")
            self._cmds.createNode("multMatrix", name=lock.matrix_name,
                                  skipSelect=True)
            self._cmds.createNode("decomposeMatrix", name=lock.decompose_name,
                                  skipSelect=True)
            if lock.static_source is not None:
                from maya.api import OpenMaya as om

                root_world = om.MMatrix(self._cmds.xform(
                    lock.root_fkx_path, query=True,
                    worldSpace=True, matrix=True))
                static_world = om.MMatrix(self._cmds.xform(
                    lock.static_source, query=True,
                    worldSpace=True, matrix=True))
                static = self._cmds.createNode(
                    "multMatrix", name=lock.static_matrix_name,
                    skipSelect=True)
                self._cmds.setAttr(
                    static + ".matrixIn[0]",
                    *tuple(root_world * static_world.inverse()),
                    type="matrix")
                self._cmds.connectAttr(
                    lock.static_source + ".worldMatrix[0]",
                    static + ".matrixIn[1]")
                if lock.enabled:
                    blend = self._cmds.createNode(
                        "blendMatrix", name=lock.blend_name,
                        skipSelect=True)
                    self._cmds.connectAttr(
                        static + ".matrixSum", blend + ".inputMatrix")
                    self._cmds.connectAttr(
                        lock.root_fkx_path + ".worldMatrix[0]",
                        blend + ".target[0].targetMatrix")
                    self._cmds.addAttr(
                        lock.weight_control, longName="legLock",
                        attributeType="double", minValue=0,
                        maxValue=10, defaultValue=10, keyable=True)
                    weight = self._cmds.createNode(
                        "multDoubleLinear", name=lock.weight_name,
                        skipSelect=True)
                    self._cmds.setAttr(weight + ".input2", 0.1)
                    self._cmds.connectAttr(
                        lock.weight_control + ".legLock",
                        weight + ".input1")
                    self._cmds.connectAttr(
                        weight + ".output",
                        blend + ".target[0].weight")
            self._cmds.connectAttr(lock.matrix_source, lock.source_input)
            self._cmds.connectAttr(
                lock.matrix_name + ".matrixSum",
                lock.decompose_name + ".inputMatrix")
            for channel in ("Translate", "Rotate", "Scale", "Shear"):
                self._cmds.connectAttr(
                    lock.decompose_name + ".output" + channel,
                    lock.path + "." + channel.lower())
            if plan.spine:
                self.create_body_spine(plan.spine)
            if plan.spline:
                from .maya_spline import create
                create(self,plan.spline)
            if plan.head_aim:
                from .maya_head_aim import create
                create(self,plan.head_aim)
            for spec in (plan.pelvis_translation,) + plan.attachments:
                self._preflight_torso_channels(spec.target, spec.attributes)
                if (plan.use_offset_parent_matrix
                        and spec.kind == "parentConstraint"
                        and not spec.translation_only):
                    source = replace(
                        self.capture_parent_constraint_input(
                            spec.source, spec.target, True),
                        use_offset_parent_matrix=True,
                        skip_scale=True,
                        include_pick_matrix=True)
                    matrix_plan = plan_body_parent_constraint(source)
                    self.preflight_parent_constraint(matrix_plan)
                    self.create_parent_constraint(matrix_plan)
                    issues = audit_body_parent_constraint(
                        matrix_plan,
                        self.capture_parent_constraint_state(matrix_plan))
                    if issues:
                        raise RuntimeError("Torso OPM 写后复检失败："
                                           + "；".join(issues))
                    continue
                command = self._cmds.parentConstraint if spec.kind == "parentConstraint" else self._cmds.pointConstraint
                self._transaction_changed = True
                options = {"skipRotate": ("x", "y", "z")} if spec.translation_only else {}
                nodes = command(spec.source, spec.target, maintainOffset=True, name=spec.name, **options)
                if len(nodes) != 1 or nodes[0].rsplit("|", 1)[-1] != spec.name:
                    raise RuntimeError(f"Torso 约束名称漂移：{spec.name}")
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_torso(self, plan):
        if plan.spline:
            from .maya_spline import audit
            audit(self,plan.spline)
        if plan.head_aim:
            from .maya_head_aim import audit
            audit(self,plan.head_aim.head_control,plan.head_aim.target)
        states = []
        for spec in (plan.pelvis_translation,) + plan.attachments:
            if (plan.use_offset_parent_matrix
                    and spec.kind == "parentConstraint"
                    and not spec.translation_only):
                mm, pm = torso_opm_attachment_nodes(spec)
                c = self._cmds
                parents = c.listRelatives(spec.target, parent=True,
                                          fullPath=True) or []
                expected_parent = (parents[0] + ".worldInverseMatrix[0]"
                                   if parents else "")
                if (c.nodeType(mm) != "multMatrix"
                        or c.nodeType(pm) != "pickMatrix"
                        or c.connectionInfo(mm + ".matrixIn[1]",
                            sourceFromDestination=True)
                        != spec.source + ".worldMatrix[0]"
                        or c.connectionInfo(mm + ".matrixIn[2]",
                            sourceFromDestination=True) != expected_parent
                        or c.connectionInfo(pm + ".inputMatrix",
                            sourceFromDestination=True) != mm + ".matrixSum"
                        or c.connectionInfo(spec.target + ".offsetParentMatrix",
                            sourceFromDestination=True) != pm + ".outputMatrix"
                        or bool(c.getAttr(pm + ".useScale"))):
                    raise RuntimeError("Torso OPM 空间连接读回失败："
                                       + spec.name)
                states.append(BodySpaceAttachmentState(
                    spec.name, "pickMatrix", (spec.source,),
                    ((spec.target + ".offsetParentMatrix", spec.name),)))
                continue
            nodes = self._cmds.ls(spec.name, long=True) or []
            if len(nodes) != 1:
                raise RuntimeError(f"Torso 约束缺失或不唯一：{spec.name}")
            kind = self._cmds.nodeType(nodes[0])
            if kind != spec.kind:
                raise RuntimeError(f"Torso 约束类型错误：{spec.name}")
            command = self._cmds.parentConstraint if kind == "parentConstraint" else self._cmds.pointConstraint
            sources = tuple(self._resolve_connected_node(node) for node in (command(nodes[0], query=True, targetList=True) or []))
            inputs = []
            for attr in spec.attributes:
                plug = f"{spec.target}.{attr}"
                connected = self._cmds.listConnections(plug, source=True, destination=False) or []
                owner = None
                if len(connected) == 1:
                    resolved = self._resolve_connected_node(connected[0])
                    owner = spec.name if resolved == nodes[0] else resolved
                inputs.append((plug, owner))
            states.append(BodySpaceAttachmentState(spec.name, kind, sources, tuple(inputs)))
        root_control = plan.controls.controls[0]
        fkx = self._cmds.ls(plan.root_fkx_path, long=True) or []
        internal = plan.root_fkx_path.startswith(
            root_control.control_path + "|")
        expected_type = ("joint" if root_control.source_override_joint
                         else "transform")
        if (fkx != [plan.root_fkx_path]
                or self._cmds.nodeType(fkx[0])
                not in ((expected_type,) if internal else
                        ("joint", "transform"))):
            raise FitSkeletonValidationError("Root FKX 接收层缺失或不唯一")
        fkx_parent = self._cmds.listRelatives(
            fkx[0], parent=True, fullPath=True) or []
        lock = plan.leg_lock
        lock_nodes = self._cmds.ls(lock.path, long=True,
                                   type="transform") or []
        if lock_nodes != [lock.path]:
            raise FitSkeletonValidationError("腿部锁定空间缺失或不唯一")
        lock_parent = self._cmds.listRelatives(
            lock.path, parent=True, fullPath=True) or []
        def source(plug):
            inputs = self._cmds.listConnections(
                plug, source=True, destination=False, plugs=True) or []
            return self._canonical_plug(inputs[0]) if len(inputs) == 1 else None
        return BodyTorsoSnapshot(
            self._capture_body_limb_fk_controls(plan.controls, "Torso"),
            tuple(states),
            fkx_parent[0] if fkx_parent else None,
            lock_parent[0] if lock_parent else None,
            source(lock.source_input),
            source(lock.compensation_input),
            source(lock.decompose_name + ".inputMatrix"),
            tuple(source(lock.path + "." + channel)
                  for channel in ("translate", "rotate", "scale", "shear")),
            (source(lock.static_matrix_name + ".matrixIn[1]")
             if lock.static_source is not None else None),
            (source(lock.blend_name + ".target[0].targetMatrix")
             if lock.static_source is not None and lock.enabled else None),
            (source(lock.weight_name + ".input1")
             if lock.static_source is not None and lock.enabled else None),
            (float(self._cmds.getAttr(lock.weight_control + ".legLock"))
             if lock.static_source is not None and lock.enabled else None),
            (source(lock.blend_name + ".inputMatrix")
             if lock.static_source is not None and lock.enabled else None),
            (source(lock.blend_name + ".target[0].weight")
             if lock.static_source is not None and lock.enabled else None),
            (float(self._cmds.getAttr(lock.weight_name + ".input2"))
             if lock.static_source is not None and lock.enabled else None),
            (self._capture_body_root_control(plan.root_x)
             if plan.root_x is not None else None),
            tuple(self._capture_body_root_control(spec)
                  for spec in plan.cogs),
        )

    def _capture_body_root_control(self, spec):
        from adv_py.core.body_torso import BodyRootControlState
        c = self._cmds
        for path in (spec.offset_path, spec.extra_path,
                     spec.control_path):
            if c.ls(path, long=True, type="transform") != [path]:
                raise FitSkeletonValidationError("根控制层缺失：" + path)
        def parent(path):
            values = c.listRelatives(path, parent=True,
                                     fullPath=True) or []
            return values[0] if len(values) == 1 else None
        shapes = c.listRelatives(spec.control_path, shapes=True,
                                 noIntermediate=True, fullPath=True) or []
        return BodyRootControlState(
            parent(spec.offset_path), parent(spec.extra_path),
            parent(spec.control_path),
            tuple(float(value) for value in c.xform(
                spec.control_path, query=True, worldSpace=True,
                translation=True)),
            int(c.getAttr(spec.control_path + ".rotateOrder")),
            c.nodeType(shapes[0]) if len(shapes) == 1 else None)
