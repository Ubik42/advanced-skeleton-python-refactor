"""Maya operations for temporary 6.925 Inbetween Fit guides."""
from __future__ import annotations

from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_inbetween import (
    FitInbetweenGuide, FitInbetweenGuideState, FitInbetweenPlan,
    FitInbetweenReparent,
)
from adv_py.core.fit_orientation import FitOrientationSnapshot
from adv_py.core.joint_labels import JointLabel


class MayaFitInbetweenMixin:
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
