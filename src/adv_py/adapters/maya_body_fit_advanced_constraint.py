"""Build Fit parent/point/orient/scale FK constraint channels in Maya."""
from __future__ import annotations

from math import isfinite

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


def _matrix(values):
    if len(values) == 1 and isinstance(values[0], (tuple, list)):
        values = values[0]
    return tuple(float(value) for value in values)


def _reoffset_reaches_root(c, source, root):
    current = c.connectionInfo(root + ".offsetParentMatrix",
                               sourceFromDestination=True)
    visited = set()
    while current and current != source:
        node = current.rsplit(".", 1)[0]
        if (node in visited or c.nodeType(node) != "multMatrix"
                or not node.rsplit("|", 1)[-1].endswith("ReOffset")
                or current != node + ".matrixSum"):
            return False
        visited.add(node)
        current = c.connectionInfo(node + ".matrixIn[0]",
                                   sourceFromDestination=True)
    return current == source


class MayaBodyFitAdvancedConstraintMixin:
    def preflight_body_fit_advanced_constraint(
        self, spec: BodyFitAdvancedConstraintSpec,
    ) -> None:
        c = self._cmds
        if spec.kind not in _COMMANDS:
            raise ValueError("Fit Advanced Constraint 类型无效")
        if len(spec.target_joints) not in (1, 2):
            raise ValueError("Fit Advanced Constraint 目标数量无效")
        if (spec.split_name is None) != (len(spec.target_joints) == 1):
            raise ValueError("Fit Advanced Constraint 双目标权重规划不完整")
        if (spec.reoffset_name is None) != (not spec.align_target):
            raise ValueError("Fit Advanced Constraint 对齐补偿计划不完整")
        for path, kind in ((spec.fk_control, "transform"),
                           (spec.fk_offset, "transform"),
                           *((target, "joint")
                             for target in spec.target_joints)):
            if (c.ls(path, long=True, type=kind) or []) != [path]:
                raise ValueError("Fit Advanced Constraint 节点缺失：" + path)
        if any(self.find_name_collisions(name) for name in spec.node_names):
            raise ValueError("Fit Advanced Constraint 节点名称冲突")
        if c.attributeQuery(spec.attribute, node=spec.fk_control,
                            exists=True):
            raise ValueError("FK 控制器已有约束权重属性：" + spec.fk_control)
        if any(target == spec.fk_offset
               or target.startswith(spec.fk_offset + "|")
               for target in spec.target_joints):
            raise ValueError("Fit Advanced Constraint 存在 DAG 循环")
        parent = c.listRelatives(spec.fk_offset, parent=True,
                                 fullPath=True) or []
        if len(parent) != 1:
            raise ValueError("FK Offset 缺少唯一父级：" + spec.fk_offset)
        if spec.align_target or spec.source_native:
            root = spec.fk_root
            opm = root + ".offsetParentMatrix"
            upstream = c.connectionInfo(opm, sourceFromDestination=True)
            children = c.listRelatives(spec.fk_offset, children=True,
                                       type="transform", fullPath=True) or []
            if ((c.ls(root, long=True, type="transform") or []) != [root]
                    or (c.listRelatives(root, parent=True,
                                        fullPath=True) or []) != [spec.fk_offset]
                    or (not spec.source_native and children != [root])
                    or c.getAttr(opm, lock=True)
                    or (not upstream and not c.getAttr(opm, settable=True))):
                raise ValueError("FK 控制根层矩阵不可补偿：" + root)
        if spec.source_native:
            return
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
        if spec.source_native:
            from .maya_source_fit_advanced_constraint import create
            return create(self,spec)
        c = self._cmds
        offset_parent = c.listRelatives(
            spec.fk_offset, parent=True, fullPath=True)[0]
        world = tuple(float(v) for v in c.xform(
            spec.fk_offset, query=True, worldSpace=True, matrix=True))
        root_world = (tuple(float(v) for v in c.xform(
            spec.fk_root, query=True, worldSpace=True, matrix=True))
                      if spec.align_target else None)
        self._transaction_changed = True
        static = c.createNode("transform", name=spec.static_name,
                              parent=offset_parent, skipSelect=True)
        static = (c.ls(static, long=True) or [static])[0]
        c.xform(static, worldSpace=True, matrix=world)
        if (c.ls(static, long=True) or []) != [
                offset_parent + "|" + spec.static_name]:
            raise RuntimeError("Fit Advanced Constraint 静态参考路径漂移")
        command = getattr(c, _COMMANDS[spec.kind])
        created = command(static, *spec.target_joints, spec.fk_offset,
                          maintainOffset=not spec.align_target,
                          name=spec.constraint_name)
        if len(created) != 1 or created[0].rsplit("|", 1)[-1] != spec.constraint_name:
            raise RuntimeError("Fit Advanced Constraint 节点名称漂移")
        constraint = created[0]
        targets = command(constraint, query=True, targetList=True) or []
        aliases = command(constraint, query=True, weightAliasList=True) or []
        if len(targets) != 1 + len(spec.target_joints) or len(aliases) != len(targets):
            raise RuntimeError("Fit Advanced Constraint 目标权重不完整")
        resolved = tuple((c.ls(target, long=True) or [target])[0]
                         for target in targets)
        if resolved != (static, *spec.target_joints):
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
        dynamic_weight = weight + ".output"
        if spec.split_name is not None:
            split = c.createNode("multDoubleLinear", name=spec.split_name)
            c.setAttr(split + ".input2", 0.5)
            c.connectAttr(dynamic_weight, split + ".input1")
            dynamic_weight = split + ".output"
        for alias in aliases[1:]:
            c.connectAttr(dynamic_weight, constraint + "." + alias)
        if spec.align_target:
            from maya.api import OpenMaya as om

            root = spec.fk_root
            destination = root + ".offsetParentMatrix"
            old_source = c.connectionInfo(destination,
                                          sourceFromDestination=True)
            old_matrix = _matrix(c.getAttr(destination))
            current = tuple(float(v) for v in c.xform(
                spec.fk_offset, query=True, worldSpace=True, matrix=True))
            correction = tuple(om.MMatrix(world) *
                               om.MMatrix(current).inverse())
            if len(correction) != 16 or not all(map(isfinite, correction)):
                raise RuntimeError("Fit Advanced Constraint 绑定补偿矩阵无效")
            reoffset = c.createNode("multMatrix", name=spec.reoffset_name)
            c.addAttr(reoffset, longName="advPyPriorMatrixSource",
                      dataType="string")
            c.setAttr(reoffset + ".advPyPriorMatrixSource",
                      old_source or "", type="string", lock=True)
            if old_source:
                c.disconnectAttr(old_source, destination)
                c.connectAttr(old_source, reoffset + ".matrixIn[0]")
            else:
                c.setAttr(reoffset + ".matrixIn[0]", *old_matrix,
                          type="matrix")
            c.setAttr(reoffset + ".matrixIn[1]", *correction,
                      type="matrix")
            c.setAttr(reoffset + ".matrixIn[1]", lock=True)
            c.connectAttr(reoffset + ".matrixSum", destination)
            restored = tuple(float(v) for v in c.xform(
                root, query=True, worldSpace=True, matrix=True))
            if any(abs(a-b)>1e-4 for a,b in zip(root_world, restored)):
                raise RuntimeError("Fit Advanced Constraint 控制根层绑定姿态未恢复")
        after = tuple(float(v) for v in c.xform(
            spec.fk_offset, query=True, worldSpace=True, matrix=True))
        if not spec.align_target and any(
                abs(a - b) > 1e-4 for a, b in zip(world, after)):
            raise RuntimeError("Fit Advanced Constraint 改变了 FK 绑定姿态")

    def capture_body_fit_advanced_constraint(
        self, spec: BodyFitAdvancedConstraintSpec,
    ) -> bool:
        if spec.source_native:
            from .maya_source_fit_advanced_constraint import capture
            return capture(self,spec)
        c = self._cmds
        if any(not c.objExists(name) for name in spec.node_names):
            return False
        if (c.nodeType(spec.constraint_name) != _COMMANDS[spec.kind]
                or c.nodeType(spec.weight_name) != "multDoubleLinear"
                or c.nodeType(spec.reverse_name) != "reverse"
                or (spec.split_name is not None and
                    c.nodeType(spec.split_name) != "multDoubleLinear")
                or (spec.align_target and
                    c.nodeType(spec.reoffset_name) != "multMatrix")):
            return False
        if not c.attributeQuery(spec.attribute, node=spec.fk_control,
                                exists=True):
            return False
        command = getattr(c, _COMMANDS[spec.kind])
        targets = command(spec.constraint_name, query=True,
                          targetList=True) or []
        aliases = command(spec.constraint_name, query=True,
                          weightAliasList=True) or []
        if len(targets) != 1 + len(spec.target_joints) or len(aliases) != len(targets):
            return False
        resolved = tuple((c.ls(target, long=True) or [target])[0]
                         for target in targets)
        parent = c.listRelatives(spec.fk_offset, parent=True,
                                 fullPath=True) or []
        static = parent[0] + "|" + spec.static_name if parent else ""
        if resolved != (static, *spec.target_joints):
            return False
        if spec.constraint_name not in tuple(
                node.rsplit("|", 1)[-1] for node in (
                    c.listConnections(spec.fk_offset, source=True,
                                      destination=False,
                                      type=_COMMANDS[spec.kind]) or [])):
            return False
        dynamic_weight = spec.weight_name + ".output"
        split_links = ()
        if spec.split_name is not None:
            split_links = ((dynamic_weight,
                            spec.split_name + ".input1"),)
            dynamic_weight = spec.split_name + ".output"
        links = (
            (spec.fk_control + "." + spec.attribute,
             spec.weight_name + ".input1"),
            (spec.weight_name + ".output",
             spec.reverse_name + ".inputX"),
            (spec.reverse_name + ".outputX",
             spec.constraint_name + "." + aliases[0]),
        ) + split_links + tuple(
            (dynamic_weight, spec.constraint_name + "." + alias)
            for alias in aliases[1:])
        if spec.align_target:
            reoffset = spec.reoffset_name
            root = spec.fk_root
            original = c.getAttr(reoffset + ".advPyPriorMatrixSource")
            incoming = c.connectionInfo(reoffset + ".matrixIn[0]",
                                        sourceFromDestination=True) or ""
            if (not _reoffset_reaches_root(
                        c, reoffset + ".matrixSum", root)
                    or not c.getAttr(reoffset + ".matrixIn[1]", lock=True)
                    or not c.getAttr(reoffset + ".advPyPriorMatrixSource",
                                     lock=True)
                    or incoming != original
                    or len(_matrix(c.getAttr(reoffset + ".matrixIn[1]"))) != 16):
                return False
        return (all(c.isConnected(source, destination, ignoreUnitConversion=True)
                    for source, destination in links)
                and abs(float(c.getAttr(spec.weight_name + ".input2"))
                        - 0.1) <= 1e-8
                and (spec.split_name is None or abs(float(c.getAttr(
                    spec.split_name + ".input2")) - 0.5) <= 1e-8)
                and abs(float(c.getAttr(
                    spec.fk_control + "." + spec.attribute)) - 10.0) <= 1e-8)
