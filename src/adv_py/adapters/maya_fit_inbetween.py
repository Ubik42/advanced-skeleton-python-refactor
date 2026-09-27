"""Maya operations for temporary 6.925 Inbetween Fit guides."""
from __future__ import annotations

from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_inbetween import (
    FitInbetweenGuide, FitInbetweenGuideState, FitInbetweenPlan,
    FitInbetweenReparent,
)
from adv_py.core.fit_orientation import FitOrientationSnapshot
from adv_py.core.fit_inbetween_bias import InbetweenBiasPlan
from adv_py.core.joint_labels import JointLabel


class MayaFitInbetweenMixin:
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
