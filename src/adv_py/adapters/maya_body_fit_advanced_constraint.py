"""Build Fit parent/point/orient/scale FK constraint channels in Maya."""
from __future__ import annotations

from adv_py.core.body_fit_advanced_constraint import (
    BodyFitAdvancedConstraintSpec,
)


_COMMANDS = {
    "parent": "parentConstraint",
    "point": "pointConstraint",
    "orient": "orientConstraint",
    "scale": "scaleConstraint",
}
_AFFECTED = {
    "parent": ("translate", "rotate"),
    "point": ("translate",),
    "orient": ("rotate",),
    "scale": ("scale",),
}


class MayaBodyFitAdvancedConstraintMixin:
    def preflight_body_fit_advanced_constraint(
        self, spec: BodyFitAdvancedConstraintSpec,
    ) -> None:
        c = self._cmds
        if spec.kind not in _COMMANDS:
            raise ValueError("Fit Advanced Constraint 类型无效")
        for path, kind in ((spec.fk_control, "transform"),
                           (spec.fk_offset, "transform"),
                           (spec.target_joint, "joint")):
            if (c.ls(path, long=True, type=kind) or []) != [path]:
                raise ValueError("Fit Advanced Constraint 节点缺失：" + path)
        if any(self.find_name_collisions(name) for name in spec.node_names):
            raise ValueError("Fit Advanced Constraint 节点名称冲突")
        if c.attributeQuery(spec.attribute, node=spec.fk_control,
                            exists=True):
            raise ValueError("FK 控制器已有约束权重属性：" + spec.fk_control)
        if (spec.target_joint == spec.fk_offset
                or spec.target_joint.startswith(spec.fk_offset + "|")):
            raise ValueError("Fit Advanced Constraint 存在 DAG 循环")
        parent = c.listRelatives(spec.fk_offset, parent=True,
                                 fullPath=True) or []
        if len(parent) != 1:
            raise ValueError("FK Offset 缺少唯一父级：" + spec.fk_offset)
        for channel in _AFFECTED[spec.kind]:
            for axis in "XYZ":
                plug = spec.fk_offset + "." + channel + axis
                if not c.getAttr(plug, settable=True):
                    raise ValueError("FK Offset 通道不可约束：" + plug)

    def create_body_fit_advanced_constraint(
        self, spec: BodyFitAdvancedConstraintSpec,
    ) -> None:
        self._require_transaction()
        self.preflight_body_fit_advanced_constraint(spec)
        c = self._cmds
        offset_parent = c.listRelatives(
            spec.fk_offset, parent=True, fullPath=True)[0]
        world = tuple(float(v) for v in c.xform(
            spec.fk_offset, query=True, worldSpace=True, matrix=True))
        self._transaction_changed = True
        static = c.createNode("transform", name=spec.static_name,
                              parent=offset_parent, skipSelect=True)
        static = (c.ls(static, long=True) or [static])[0]
        c.xform(static, worldSpace=True, matrix=world)
        if (c.ls(static, long=True) or []) != [
                offset_parent + "|" + spec.static_name]:
            raise RuntimeError("Fit Advanced Constraint 静态参考路径漂移")
        command = getattr(c, _COMMANDS[spec.kind])
        created = command(static, spec.target_joint, spec.fk_offset,
                          maintainOffset=True, name=spec.constraint_name)
        if len(created) != 1 or created[0].rsplit("|", 1)[-1] != spec.constraint_name:
            raise RuntimeError("Fit Advanced Constraint 节点名称漂移")
        constraint = created[0]
        targets = command(constraint, query=True, targetList=True) or []
        aliases = command(constraint, query=True, weightAliasList=True) or []
        if len(targets) != 2 or len(aliases) != 2:
            raise RuntimeError("Fit Advanced Constraint 目标权重不完整")
        resolved = tuple((c.ls(target, long=True) or [target])[0]
                         for target in targets)
        if resolved != (static, spec.target_joint):
            raise RuntimeError("Fit Advanced Constraint 目标顺序改变")
        if spec.kind in ("parent", "orient"):
            c.setAttr(constraint + ".interpType", 2)
        c.addAttr(spec.fk_control, longName=spec.attribute,
                  attributeType="double", minValue=0, maxValue=10,
                  defaultValue=10, keyable=True)
        weight = c.createNode("multDoubleLinear", name=spec.weight_name)
        reverse = c.createNode("reverse", name=spec.reverse_name)
        c.setAttr(weight + ".input2", 0.1)
        c.connectAttr(spec.fk_control + "." + spec.attribute,
                      weight + ".input1")
        c.connectAttr(weight + ".output", reverse + ".inputX")
        c.connectAttr(reverse + ".outputX", constraint + "." + aliases[0])
        c.connectAttr(weight + ".output", constraint + "." + aliases[1])
        after = tuple(float(v) for v in c.xform(
            spec.fk_offset, query=True, worldSpace=True, matrix=True))
        if any(abs(a - b) > 1e-4 for a, b in zip(world, after)):
            raise RuntimeError("Fit Advanced Constraint 改变了 FK 绑定姿态")

    def capture_body_fit_advanced_constraint(
        self, spec: BodyFitAdvancedConstraintSpec,
    ) -> bool:
        c = self._cmds
        if any(not c.objExists(name) for name in spec.node_names):
            return False
        if (c.nodeType(spec.constraint_name) != _COMMANDS[spec.kind]
                or c.nodeType(spec.weight_name) != "multDoubleLinear"
                or c.nodeType(spec.reverse_name) != "reverse"):
            return False
        if not c.attributeQuery(spec.attribute, node=spec.fk_control,
                                exists=True):
            return False
        command = getattr(c, _COMMANDS[spec.kind])
        targets = command(spec.constraint_name, query=True,
                          targetList=True) or []
        aliases = command(spec.constraint_name, query=True,
                          weightAliasList=True) or []
        if len(targets) != 2 or len(aliases) != 2:
            return False
        resolved = tuple((c.ls(target, long=True) or [target])[0]
                         for target in targets)
        parent = c.listRelatives(spec.fk_offset, parent=True,
                                 fullPath=True) or []
        static = parent[0] + "|" + spec.static_name if parent else ""
        if resolved != (static, spec.target_joint):
            return False
        if spec.constraint_name not in tuple(
                node.rsplit("|", 1)[-1] for node in (
                    c.listConnections(spec.fk_offset, source=True,
                                      destination=False,
                                      type=_COMMANDS[spec.kind]) or [])):
            return False
        links = (
            (spec.fk_control + "." + spec.attribute,
             spec.weight_name + ".input1"),
            (spec.weight_name + ".output",
             spec.reverse_name + ".inputX"),
            (spec.reverse_name + ".outputX",
             spec.constraint_name + "." + aliases[0]),
            (spec.weight_name + ".output",
             spec.constraint_name + "." + aliases[1]),
        )
        return (all(c.connectionInfo(destination,
                                     sourceFromDestination=True) == source
                    for source, destination in links)
                and abs(float(c.getAttr(spec.weight_name + ".input2"))
                        - 0.1) <= 1e-8
                and abs(float(c.getAttr(
                    spec.fk_control + "." + spec.attribute)) - 10.0) <= 1e-8)
