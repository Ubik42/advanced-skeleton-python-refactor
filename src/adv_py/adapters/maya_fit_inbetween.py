"""Maya operations for temporary 6.925 Inbetween Fit guides."""
from __future__ import annotations

from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_inbetween import (
    FitInbetweenGuide, FitInbetweenGuideState, FitInbetweenPlan,
    FitInbetweenReparent,
)
from adv_py.core.fit_orientation import FitOrientationSnapshot
from adv_py.core.fit_inbetween_bias import InbetweenBiasPlan
from adv_py.core.fit_inbetween_fk_anchor import InbetweenFkAnchorPlan
from adv_py.core.fit_inbetween_matrix import (
    InbetweenMatrixDestination, InbetweenMatrixPlan,
    InbetweenMatrixStep,
)
from adv_py.core.joint_labels import JointLabel


class MayaFitInbetweenMixin:
    def preflight_inbetween_fk_anchor(
        self, plan: InbetweenFkAnchorPlan
    ) -> None:
        c = self._cmds
        offsets = c.ls(plan.fk_offset_path, long=True,
                       type="transform") or []
        controls = c.ls(plan.fk_control_path, long=True,
                        type="transform") or []
        if (offsets != [plan.fk_offset_path]
                or controls != [plan.fk_control_path]):
            raise ValueError("Inbetween FK 起点控制层不存在："
                             + plan.start_body_name)
        names = (plan.base_name, plan.target_name,
                 plan.extra_name, plan.fkx_name)
        if len(set(names)) != len(names) or any(
                c.objExists(name) for name in names):
            raise ValueError("Inbetween FK 起点层名称冲突："
                             + plan.start_body_name)
        if not c.objExists(plan.fk_offset_path + ".offsetParentMatrix"):
            raise ValueError("Inbetween FK 起点不支持矩阵驱动："
                             + plan.fk_offset_path)

    def create_inbetween_fk_anchor(
        self, plan: InbetweenFkAnchorPlan
    ) -> None:
        self._require_transaction()
        c = self._cmds
        base = c.createNode("transform", name=plan.base_name,
                            parent=plan.fk_offset_path, skipSelect=True)
        extra = c.createNode("transform", name=plan.extra_name,
                             parent=plan.fk_offset_path, skipSelect=True)
        target = c.createNode("transform", name=plan.target_name,
                              parent=plan.fk_control_path, skipSelect=True)
        fkx = c.createNode("joint", name=plan.fkx_name,
                           parent=plan.fk_offset_path, skipSelect=True)
        self._transaction_changed = True
        c.setAttr(fkx + ".drawStyle", 2)
        c.setAttr(fkx + ".segmentScaleCompensate", 0)
        c.setAttr(fkx + ".rotateOrder", plan.rotate_order)
        # All four nodes start with identity local transforms. FKX's OPM
        # receives the world blend converted through Extra's parent inverse.
        for node in (base, extra, target, fkx):
            c.setAttr(node + ".translate", 0.0, 0.0, 0.0,
                      type="double3")
            c.setAttr(node + ".rotate", 0.0, 0.0, 0.0,
                      type="double3")

    def capture_inbetween_fk_anchor(
        self, plan: InbetweenFkAnchorPlan
    ) -> tuple[str | None, ...]:
        c = self._cmds
        for name, parent_name, node_type in (
            (plan.base_name, plan.fk_offset_path, "transform"),
            (plan.target_name, plan.fk_control_path, "transform"),
            (plan.extra_name, plan.fk_offset_path, "transform"),
            (plan.fkx_name, plan.fk_offset_path, "joint"),
        ):
            nodes = c.ls(name, long=True, type=node_type) or []
            if len(nodes) != 1 or (c.listRelatives(
                    nodes[0], parent=True, fullPath=True) or []) != [
                    parent_name]:
                return (None, None, None, None)
        return (plan.base_world_plug, plan.target_world_plug,
                plan.parent_inverse_plug, plan.start_fkx_opm_plug)

    def preflight_inbetween_matrix_destinations(
        self, destinations: tuple[InbetweenMatrixDestination, ...]
    ) -> None:
        c = self._cmds
        for destination in destinations:
            if (not c.objExists(destination.source_plug)
                    or not c.objExists(destination.target_plug)):
                raise ValueError("Inbetween FK 矩阵来源或接收端不存在："
                                 + destination.joint_name)
            if c.connectionInfo(destination.target_plug,
                                sourceFromDestination=True):
                raise ValueError("Inbetween FK 矩阵接收端已被占用："
                                 + destination.target_plug)

    def connect_inbetween_matrix_destination(
        self, destination: InbetweenMatrixDestination
    ) -> None:
        self._require_transaction()
        self._cmds.connectAttr(destination.source_plug,
                               destination.target_plug)
        self._transaction_changed = True

    def capture_inbetween_matrix_destination(
        self, destination: InbetweenMatrixDestination
    ) -> str | None:
        source = self._cmds.connectionInfo(
            destination.target_plug, sourceFromDestination=True)
        return source or None

    def preflight_inbetween_matrices(
        self, plan: InbetweenMatrixPlan
    ) -> None:
        c = self._cmds
        for plug in (plan.base_world_plug, plan.target_world_plug,
                     plan.parent_inverse_plug):
            if not c.objExists(plug):
                raise ValueError("Inbetween 矩阵输入不存在：" + plug)
        names = []
        for step in plan.steps:
            if not c.objExists(step.weight_plug):
                raise ValueError("Inbetween 权重输出不存在："
                                 + step.weight_plug)
            names.extend((step.blend_name, step.local_matrix_name))
            if step.index == 0:
                names.extend((step.legacy_blend_decompose_name,
                              step.legacy_target_decompose_name,
                              step.legacy_compose_name))
        if len(names) != len(set(names)) or any(
                c.objExists(name) for name in names):
            raise ValueError("Inbetween 矩阵节点名称冲突")

    def create_inbetween_matrix_step(
        self, plan: InbetweenMatrixPlan,
        step: InbetweenMatrixStep,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        blend = c.createNode("blendMatrix", name=step.blend_name)
        local = c.createNode("multMatrix", name=step.local_matrix_name)
        self._transaction_changed = True
        c.connectAttr(plan.base_world_plug, blend + ".inputMatrix")
        c.connectAttr(plan.target_world_plug,
                      blend + ".target[0].targetMatrix")
        c.connectAttr(plan.parent_inverse_plug, local + ".matrixIn[1]")
        modern = c.objExists(blend + ".target[0].translateWeight")
        if modern:
            if step.rotation_only:
                for channel in ("translateWeight", "scaleWeight",
                                "shearWeight"):
                    c.setAttr(blend + ".target[0]." + channel, 0.0)
            c.connectAttr(step.weight_plug,
                          blend + ".target[0].rotateWeight")
            c.connectAttr(blend + ".outputMatrix",
                          local + ".matrixIn[0]")
            return
        if step.rotation_only:
            for channel in ("useTranslate", "useScale", "useShear"):
                c.setAttr(blend + ".target[0]." + channel, False)
        c.connectAttr(step.weight_plug, blend + ".target[0].weight")
        if step.index > 0:
            c.connectAttr(blend + ".outputMatrix",
                          local + ".matrixIn[0]")
            return
        # Maya 2022 及更早版本没有分量权重。首节旋转来自混合矩阵，
        # 位移、缩放和剪切保持目标 FK 的世界矩阵分量。
        mixed = c.createNode("decomposeMatrix",
                             name=step.legacy_blend_decompose_name)
        target = c.createNode("decomposeMatrix",
                              name=step.legacy_target_decompose_name)
        composed = c.createNode("composeMatrix",
                                name=step.legacy_compose_name)
        c.connectAttr(blend + ".outputMatrix", mixed + ".inputMatrix")
        c.connectAttr(plan.target_world_plug, target + ".inputMatrix")
        for component in ("Translate", "Scale", "Shear"):
            c.connectAttr(target + ".output" + component,
                          composed + ".input" + component)
        c.connectAttr(mixed + ".outputRotate",
                      composed + ".inputRotate")
        c.connectAttr(composed + ".outputMatrix",
                      local + ".matrixIn[0]")

    def capture_inbetween_matrix_output(
        self, step: InbetweenMatrixStep
    ) -> str | None:
        c = self._cmds
        if not c.objExists(step.output_plug):
            return None
        modern = c.objExists(step.blend_name
                             + ".target[0].translateWeight")
        weight_destination = ("rotateWeight" if modern else "weight")
        if c.connectionInfo(step.blend_name + ".target[0]."
                            + weight_destination,
                            sourceFromDestination=True) != step.weight_plug:
            return None
        matrix_source = (step.legacy_compose_name + ".outputMatrix"
                         if step.index == 0 and not modern
                         else step.blend_name + ".outputMatrix")
        if c.connectionInfo(step.local_matrix_name + ".matrixIn[0]",
                            sourceFromDestination=True) != matrix_source:
            return None
        return step.output_plug

    def preflight_inbetween_bias(self, plan: InbetweenBiasPlan) -> None:
        c = self._cmds
        control, _, attribute = plan.control_plug.rpartition(".")
        if not control or attribute != "bias" or not c.objExists(control):
            raise ValueError("Inbetween FK Bias 控制目标无效："
                             + plan.control_plug)
        names = (plan.unit_name, plan.start_curve.name,
                 plan.mid_curve.name, plan.end_curve.name)
        if len(set(names)) != len(names) or any(c.objExists(name)
                                                for name in names):
            raise ValueError("Inbetween FK Bias 节点名称冲突："
                             + plan.start_body_name)
        if c.objExists(plan.control_plug) and not c.getAttr(
                plan.control_plug, settable=True):
            raise ValueError("Inbetween FK Bias 属性不可写："
                             + plan.control_plug)

    def create_inbetween_bias(self, plan: InbetweenBiasPlan) -> None:
        self._require_transaction()
        c = self._cmds
        control, _, _ = plan.control_plug.rpartition(".")
        if not c.objExists(plan.control_plug):
            c.addAttr(control, longName="bias", attributeType="double",
                      defaultValue=0.0, keyable=True)
        unit = c.createNode("unitConversion", name=plan.unit_name)
        c.setAttr(unit + ".conversionFactor", 0.1)
        c.connectAttr(plan.control_plug, unit + ".input")
        for curve in (plan.start_curve, plan.mid_curve,
                      plan.end_curve):
            remap = c.createNode("remapValue", name=curve.name)
            c.setAttr(remap + ".inputMin", -1.0)
            c.setAttr(remap + ".inputMax", 1.0)
            c.connectAttr(unit + ".output", remap + ".inputValue")
            for index, (input_value, output_value) in enumerate(curve.keys):
                entry = remap + f".value[{index}]"
                c.setAttr(entry + ".value_Position",
                          (input_value + 1.0) * 0.5)
                c.setAttr(entry + ".value_FloatValue", output_value)
                c.setAttr(entry + ".value_Interp", 1)
        self._transaction_changed = True

    def capture_inbetween_bias_outputs(
        self, plan: InbetweenBiasPlan
    ) -> tuple[str | None, ...]:
        c = self._cmds
        if c.connectionInfo(plan.unit_name + ".input",
                sourceFromDestination=True) != plan.control_plug:
            return (None, None, None)
        outputs = []
        for curve in (plan.start_curve, plan.mid_curve,
                      plan.end_curve):
            if c.connectionInfo(curve.name + ".inputValue",
                    sourceFromDestination=True) != plan.unit_name + ".output":
                outputs.append(None)
            else:
                outputs.append(curve.name + ".outValue")
        return tuple(outputs)

    def _one_inbetween_joint(self, name: str) -> str:
        matches = self._cmds.ls(name, long=True, type="joint") or []
        if len(matches) != 1:
            raise ValueError("Inbetween 需要唯一的 Fit 关节名称：" + name)
        return matches[0]

    def preflight_fit_inbetween(self, plan: FitInbetweenPlan) -> None:
        c = self._cmds
        planned = {guide.name for guide in plan.guides}
        if len(planned) != len(plan.guides):
            raise ValueError("Inbetween 临时导向名称重复")
        for guide in plan.guides:
            self._one_inbetween_joint(guide.start_joint)
            self._one_inbetween_joint(guide.end_joint)
            if (guide.parent_name not in planned
                    and guide.parent_name != guide.start_joint.rsplit("|", 1)[-1]):
                raise ValueError("Inbetween 临时导向父级无效：" + guide.name)
            if c.objExists(guide.name):
                raise ValueError("Inbetween 临时导向名称已占用：" + guide.name)
        for step in plan.reparents:
            child = self._one_inbetween_joint(step.child_name)
            if step.parent_guide_name not in planned:
                raise ValueError("Inbetween 改挂目标不在计划中："
                                 + step.child_name)
            if c.listConnections(child, type="skinCluster"):
                raise ValueError("Inbetween 必须在 Skin 绑定前生成")

    def create_fit_inbetween_guide(self, guide: FitInbetweenGuide) -> None:
        self._require_transaction()
        c = self._cmds
        parent = self._one_inbetween_joint(guide.parent_name)
        joint = c.createNode("joint", name=guide.name,
                             parent=parent, skipSelect=True)
        self._transaction_changed = True
        joint = self._one_inbetween_joint(guide.name)
        c.setAttr(joint + ".rotateOrder", guide.rotation_order)
        c.xform(joint, worldSpace=True,
                translation=guide.world_position)
        c.addAttr(joint, longName="tempInbetweener",
                  attributeType="bool", defaultValue=True, keyable=True)
        self.set_joint_label(joint, JointLabel.parse("Part"))
        for name, value in (
            ("fat", guide.deform_profile.fat),
            ("fatFront", guide.deform_profile.fat_front),
            ("fatWidth", guide.deform_profile.fat_width),
        ):
            c.addAttr(joint, longName=name, attributeType="double",
                      defaultValue=value, keyable=False)

    def reparent_fit_inbetween_child(
        self, step: FitInbetweenReparent
    ) -> None:
        self._require_transaction()
        child = self._one_inbetween_joint(step.child_name)
        parent = self._one_inbetween_joint(step.parent_guide_name)
        self._cmds.parent(child, parent)
        self._transaction_changed = True

    def capture_fit_inbetween_guides(
        self, names: tuple[str, ...]
    ) -> tuple[FitInbetweenGuideState, ...]:
        c = self._cmds
        result = []
        for name in names:
            joint = self._one_inbetween_joint(name)
            parent = c.listRelatives(joint, parent=True,
                                     fullPath=True) or []
            result.append(FitInbetweenGuideState(
                name,
                parent[0].rsplit("|", 1)[-1] if parent else "",
                tuple(float(value) for value in c.xform(
                    joint, query=True, worldSpace=True,
                    translation=True)),
                FitDeformProfile(*(
                    float(c.getAttr(joint + "." + attr))
                    for attr in ("fat", "fatFront", "fatWidth")
                )),
                int(c.getAttr(joint + ".rotateOrder")),
            ))
        return tuple(result)

    def restore_fit_inbetween(
        self, plan: FitInbetweenPlan,
        original: FitOrientationSnapshot,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        by_name = {node.short_name: node
                   for node in original.hierarchy.joints}
        axes = {state.joint.rsplit("|", 1)[-1]: state
                for state in original.joints}
        for step in reversed(plan.reparents):
            node = by_name[step.child_name]
            parent_name = node.dag_parent.rsplit("|", 1)[-1]
            child = self._one_inbetween_joint(step.child_name)
            parent = self._one_inbetween_joint(parent_name)
            c.parent(child, parent)
            child = self._one_inbetween_joint(step.child_name)
            c.setAttr(child + ".translate", *node.local_position,
                      type="double3")
            c.setAttr(child + ".jointOrient", *axes[step.child_name].joint_orient,
                      type="double3")
            c.setAttr(child + ".rotate", *axes[step.child_name].rotation,
                      type="double3")
        for guide in plan.guides:
            if guide.index == 1:
                c.delete(self._one_inbetween_joint(guide.name))
        self._transaction_changed = True
