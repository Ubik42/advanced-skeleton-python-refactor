"""Maya node boundary for the generic Fit-driven Part hierarchy."""
from __future__ import annotations

from adv_py.core.fit_part import (
    FitPartChildState,
    FitPartJointSpec,
    FitPartJointState,
    FitPartReparentSpec,
)
from adv_py.core.body_skeleton import FitDeformProfile

from .maya_body import MayaBodyBuildHost


_FIT_PART_KIND = "fit-part-v1"


class MayaFitPartHost(MayaBodyBuildHost):
    def _unique_fit_part_joint(self, name: str) -> str:
        matches = self._cmds.ls(name, long=True, type="joint") or []
        if len(matches) != 1:
            raise ValueError("Fit Part 需要唯一关节名称：" + name)
        return matches[0]

    def preflight_fit_part_hierarchy(
        self,
        joints: tuple[FitPartJointSpec, ...],
        reparents: tuple[FitPartReparentSpec, ...],
    ) -> None:
        c = self._cmds
        planned_names = {item.name for item in joints}
        for spec in joints:
            self._unique_fit_part_joint(spec.start_body_name)
            self._unique_fit_part_joint(spec.end_body_name)
            if (spec.parent_name not in planned_names
                    and spec.parent_name != spec.start_body_name):
                raise ValueError("Fit Part 父关节不在构建计划中：" + spec.name)
        for spec in reparents:
            child = self._unique_fit_part_joint(spec.child_name)
            if spec.parent_part_name not in planned_names:
                raise ValueError("Fit Part 改挂父关节不在构建计划中："
                                 + spec.parent_part_name)
            # A bound joint must not move beneath a new influence hierarchy.
            if c.listConnections(child, type="skinCluster"):
                raise ValueError("Fit Part 改挂必须在 Skin 绑定前执行："
                                 + spec.child_name)

    def create_fit_part_joint(self, spec: FitPartJointSpec) -> None:
        self._require_transaction()
        c = self._cmds
        parent = self._unique_fit_part_joint(spec.parent_name)
        joint = c.createNode("joint", name=spec.name, parent=parent,
                             skipSelect=True)
        joint = self._unique_fit_part_joint(spec.name)
        self._transaction_changed = True
        c.setAttr(joint + ".rotateOrder", spec.rotation_order)
        c.setAttr(joint + ".segmentScaleCompensate",
                  spec.segment_scale_compensate)
        c.xform(joint, worldSpace=True, translation=spec.world_position)
        c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind",
                  dataType="string")
        c.setAttr(joint + ".advPyAuxiliaryInfluenceKind", _FIT_PART_KIND,
                  type="string", lock=True)
        c.addAttr(joint, longName="advPySkinEnabled", attributeType="bool",
                  defaultValue=spec.skin_enabled)
        for name, value in (
            ("fat", spec.deform_profile.fat),
            ("fatFront", spec.deform_profile.fat_front),
            ("fatWidth", spec.deform_profile.fat_width),
        ):
            c.addAttr(joint, longName=name, attributeType="double",
                      minValue=0.0, defaultValue=value, keyable=False)

    def reparent_fit_part_child(self, spec: FitPartReparentSpec) -> None:
        self._require_transaction()
        c = self._cmds
        child = self._unique_fit_part_joint(spec.child_name)
        parent = self._unique_fit_part_joint(spec.parent_part_name)
        # Parenting preserves the child's world transform. Resolve names
        # again on each call because every reparent changes descendant paths.
        c.parent(child, world=True)
        child = self._unique_fit_part_joint(spec.child_name)
        parent = self._unique_fit_part_joint(spec.parent_part_name)
        c.parent(child, parent)
        self._transaction_changed = True

    def capture_fit_part_joints(
        self, names: tuple[str, ...]
    ) -> tuple[FitPartJointState, ...]:
        c = self._cmds
        result = []
        for name in names:
            joint = self._unique_fit_part_joint(name)
            parent = c.listRelatives(joint, parent=True, fullPath=True) or []
            result.append(FitPartJointState(
                name,
                parent[0].rsplit("|", 1)[-1] if parent else "",
                tuple(float(value) for value in c.xform(
                    joint, query=True, worldSpace=True, translation=True)),
                FitDeformProfile(*(
                    float(c.getAttr(joint + "." + attr))
                    for attr in ("fat", "fatFront", "fatWidth")
                )),
                bool(c.getAttr(joint + ".advPySkinEnabled")),
                int(c.getAttr(joint + ".rotateOrder")),
                bool(c.getAttr(joint + ".segmentScaleCompensate")),
            ))
        return tuple(result)

    def capture_fit_part_children(
        self, names: tuple[str, ...]
    ) -> tuple[FitPartChildState, ...]:
        c = self._cmds
        result = []
        for name in names:
            child = self._unique_fit_part_joint(name)
            parent = c.listRelatives(child, parent=True, fullPath=True) or []
            result.append(FitPartChildState(
                name, parent[0].rsplit("|", 1)[-1] if parent else ""))
        return tuple(result)
