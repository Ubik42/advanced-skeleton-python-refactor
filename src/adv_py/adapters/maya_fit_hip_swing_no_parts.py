"""Maya receiver for the Root HipSwinger branch without Inbetween joints."""
from __future__ import annotations

from adv_py.core.fit_hip_swing_no_parts import HipSwingNoPartsPlan


class MayaHipSwingNoPartsMixin:
    def preflight_hip_swing_no_parts(self, plan: HipSwingNoPartsPlan) -> None:
        c = self._cmds
        paths = (plan.topology.fk_root_path,
                 plan.topology.fk_root_offset_path,
                 plan.topology.root_fkx_path,
                 plan.topology.child_fk_offset_path,
                 plan.topology.root_body_path,
                 plan.topology.child_body_path)
        for path in paths:
            if (c.ls(path, long=True) or []) != [path]:
                raise ValueError("无分段 HipSwinger 来源缺失或不唯一：" + path)
        if any(c.objExists(name) for name in plan.node_names):
            raise ValueError("无分段 HipSwinger 节点名称冲突")
        for target in (plan.topology.leg_lock_matrix_input,
                       plan.topology.fk_root_matrix_input,
                       plan.topology.child_no_shear_input,
                       plan.topology.root_child_inverter_matrix_target):
            if target is None:
                continue
            node = target.split(".", 1)[0]
            if not c.objExists(node):
                raise ValueError("无分段 HipSwinger 接收端缺失：" + target)
            if c.connectionInfo(target, isDestination=True):
                raise ValueError("无分段 HipSwinger 接收端已占用：" + target)
        for channel in ("translate", "rotate"):
            for axis in "XYZ":
                plug = plan.topology.root_fkx_path + "." + channel + axis
                if not c.getAttr(plug, settable=True):
                    raise ValueError("Root FKX 通道不可编辑：" + plug)

    def create_hip_swing_no_parts(self, plan: HipSwingNoPartsPlan) -> None:
        self._require_transaction()
        self.preflight_hip_swing_no_parts(plan)
        c = self._cmds
        observed = (plan.topology.root_body_path,
                    plan.topology.child_body_path,
                    plan.topology.root_fkx_path)
        before = {path: c.xform(path, query=True, worldSpace=True,
                                 matrix=True) for path in observed}
        root_matrix = before[plan.topology.root_body_path]
        child_matrix = before[plan.topology.child_body_path]
        root_position = c.xform(plan.topology.root_body_path, query=True,
                                worldSpace=True, translation=True)
        child_position = c.xform(plan.topology.child_body_path, query=True,
                                 worldSpace=True, translation=True)
        selection = c.ls(selection=True, long=True) or []
        try:
            frame = c.createNode("transform", name=plan.frame_name,
                                 parent=plan.topology.fk_root_path,
                                 skipSelect=True)
            if (c.ls(frame, long=True) or [frame])[0] != plan.frame_path:
                raise RuntimeError("FKHSRoot 路径漂移")
            offset = c.createNode("transform", name=plan.control_offset_name,
                                  parent=plan.topology.fk_root_path,
                                  skipSelect=True)
            c.xform(offset, worldSpace=True, matrix=root_matrix)
            c.xform(offset, worldSpace=True, translation=tuple(
                (a + b) * 0.5 for a, b in zip(root_position, child_position)))
            c.setAttr(offset + ".translateX", plan.control_local_x_bias)
            control = c.circle(name=plan.control_name, normal=(1, 0, 0),
                               radius=plan.radius, degree=3, sections=16,
                               constructionHistory=False)[0]
            control = c.parent(control, offset, relative=True)[0]
            c.addAttr(control, longName="advPyHipSwingOwner",
                      dataType="string")
            c.setAttr(control + ".advPyHipSwingOwner",
                      "adv_py.hip_swing.no_parts.v1", type="string",
                      lock=True)
            for channel in ("translate", "scale"):
                for axis in "XYZ":
                    c.setAttr(control + "." + channel + axis,
                              lock=True, keyable=False)
            reverse = c.createNode("transform", name=plan.reverse_name,
                                   parent=plan.topology.fk_root_path,
                                   skipSelect=True)
            c.xform(reverse, worldSpace=True, matrix=child_matrix)
            reverse_root = c.createNode("transform",
                                        name=plan.reverse_root_name,
                                        parent=reverse, skipSelect=True)
            c.xform(reverse_root, worldSpace=True, matrix=root_matrix)
            c.parentConstraint(reverse_root, plan.topology.root_fkx_path,
                               maintainOffset=True,
                               name=plan.root_fkx_constraint_name)
            nodes = [
                (plan.remove_rotation_matrix_name, "multMatrix"),
                (plan.remove_rotation_blend_name, "blendMatrix"),
                (plan.remove_rotation_pick_name, "pickMatrix"),
                (plan.remove_rotation_inverse_name, "inverseMatrix"),
                (plan.fk_weight_blend_name, "blendMatrix"),
            ]
            if plan.topology.root_child_inverter_matrix_target:
                nodes.append((plan.root_child_matrix_name, "multMatrix"))
            for name, kind in nodes:
                c.createNode(kind, name=name, skipSelect=True)
            pick = plan.remove_rotation_pick_name
            for channel in ("Translate", "Scale", "Shear"):
                c.setAttr(pick + ".use" + channel, False)
            for source, target in plan.matrix_links:
                c.connectAttr(source, target)
            if plan.topology.leg_lock_weight is None:
                c.setAttr(plan.remove_rotation_blend_name
                          + ".target[0].weight", 1.0)
            if plan.topology.root_fk_weight is None:
                c.setAttr(plan.fk_weight_blend_name
                          + ".target[0].weight", 1.0)
            self._transaction_changed = True
            for path, original in before.items():
                after = c.xform(path, query=True, worldSpace=True,
                                matrix=True)
                if max(abs(float(a) - float(b)) for a, b in zip(
                        original, after)) > 1e-4:
                    raise RuntimeError("无分段 HipSwinger 改变绑定姿态：" + path)
        finally:
            if selection:
                c.select(selection, replace=True)
            else:
                c.select(clear=True)

    def capture_hip_swing_no_parts(self,
                                   plan: HipSwingNoPartsPlan) -> bool:
        c = self._cmds
        control = plan.control_path
        if (not c.objExists(control + ".advPyHipSwingOwner")
                or c.getAttr(control + ".advPyHipSwingOwner")
                != "adv_py.hip_swing.no_parts.v1"):
            return False
        hierarchy = (
            (plan.frame_path, plan.topology.fk_root_path),
            (plan.control_path.rsplit("|", 1)[0],
             plan.topology.fk_root_path),
            (plan.control_path,
             plan.control_path.rsplit("|", 1)[0]),
            (plan.topology.fk_root_path + "|" + plan.reverse_name,
             plan.topology.fk_root_path),
            (plan.reverse_root_path,
             plan.topology.fk_root_path + "|" + plan.reverse_name),
        )
        for path, parent in hierarchy:
            if (c.ls(path, long=True) or []) != [path]:
                return False
            actual = c.listRelatives(path, parent=True,
                                     fullPath=True) or []
            if actual != [parent]:
                return False
        constraint = c.ls(plan.root_fkx_constraint_name,
                          type="parentConstraint") or []
        if len(constraint) != 1:
            return False
        targets = c.parentConstraint(constraint[0], query=True,
                                     targetList=True) or []
        if (len(targets) != 1
                or self._resolve_connected_node(targets[0])
                != plan.reverse_root_path):
            return False
        for channel in ("Translate", "Rotate"):
            outputs = c.listConnections(
                constraint[0] + ".constraint" + channel + "X",
                source=False, destination=True, plugs=True) or []
            if (len(outputs) != 1
                    or self._canonical_plug(outputs[0])
                    != plan.topology.root_fkx_path
                    + "." + channel.lower() + "X"):
                return False
        if any(c.connectionInfo(target, sourceFromDestination=True) != source
               for source, target in plan.matrix_links):
            return False
        for weight, plug in (
            (plan.topology.leg_lock_weight,
             plan.remove_rotation_blend_name + ".target[0].weight"),
            (plan.topology.root_fk_weight,
             plan.fk_weight_blend_name + ".target[0].weight"),
        ):
            if weight is None and abs(float(c.getAttr(plug)) - 1.0) > 1e-8:
                return False
        return all(not c.getAttr(plan.remove_rotation_pick_name
                                 + ".use" + channel)
                   for channel in ("Translate", "Scale", "Shear"))
