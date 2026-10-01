"""Blend RootX's existing Offset between Main and both IK feet."""
from __future__ import annotations

from math import isfinite

from adv_py.core.body_center_between_feet import (
    BodyCenterBetweenFeetSpec, BodyCenterBetweenFeetState,
)


def _matrix(values) -> tuple[float, ...]:
    if len(values) == 1 and isinstance(values[0], (tuple, list)):
        values = values[0]
    return tuple(float(value) for value in values)


class MayaBodyCenterBetweenFeetMixin:
    def preflight_body_center_between_feet(
        self, spec: BodyCenterBetweenFeetSpec,
    ) -> BodyCenterBetweenFeetState:
        c = self._cmds
        for path in (spec.root_offset, spec.root_control,
                     spec.offset_parent, *spec.targets):
            if (c.ls(path, long=True, type="transform") or []) != [path]:
                raise ValueError("Center Between Feet 控制层缺失：" + path)
        if (c.listRelatives(spec.root_offset, parent=True,
                            fullPath=True) or []) != [spec.offset_parent]:
            raise ValueError("Center Between Feet RootX Offset 父级已变化")
        if any(self.find_name_collisions(name) for name in spec.node_names):
            raise ValueError("Center Between Feet 节点名称冲突")
        if c.attributeQuery("centerBetweenFeet", node=spec.root_control,
                            exists=True):
            raise ValueError("RootX 已有 Center Between Feet 权重通道")
        plug = spec.root_offset + ".offsetParentMatrix"
        if c.getAttr(plug, lock=True):
            raise ValueError("Center Between Feet RootX 矩阵已锁定")
        upstream = c.connectionInfo(plug, sourceFromDestination=True) or None
        if upstream is None and not c.getAttr(plug, settable=True):
            raise ValueError("Center Between Feet RootX 矩阵不可写")
        state = BodyCenterBetweenFeetState(
            _matrix(c.xform(spec.root_offset, query=True,
                            worldSpace=True, matrix=True)),
            _matrix(c.xform(spec.offset_parent, query=True,
                            worldSpace=True, matrix=True)),
            upstream, _matrix(c.getAttr(plug)))
        if any(len(m) != 16 or not all(isfinite(v) for v in m)
               for m in (state.offset_world, state.parent_world,
                         state.opm_value)):
            raise ValueError("Center Between Feet 绑定矩阵无效")
        return state

    def create_body_center_between_feet(
        self, spec: BodyCenterBetweenFeetSpec,
        state: BodyCenterBetweenFeetState,
    ) -> None:
        self._require_transaction()
        from maya.api import OpenMaya as om

        c = self._cmds
        plug = spec.root_offset + ".offsetParentMatrix"
        if (c.connectionInfo(plug, sourceFromDestination=True) or None
                ) != state.opm_source:
            raise ValueError("Center Between Feet RootX 原矩阵来源已变化")
        self._transaction_changed = True
        center = c.createNode(
            "transform", name=spec.center,
            parent="|Group|MotionSystem|RootSystem")
        c.xform(center, worldSpace=True, matrix=state.offset_world)
        targets = spec.targets
        point = c.pointConstraint(
            *targets, center, skip="y", maintainOffset=False,
            name=spec.point_constraint)
        orient = c.orientConstraint(
            *targets, center, skip=("x", "z"),
            maintainOffset=False, name=spec.orient_constraint)
        if (len(point) != 1 or len(orient) != 1
                or c.nodeType(point[0]) != "pointConstraint"
                or c.nodeType(orient[0]) != "orientConstraint"):
            raise RuntimeError("Center Between Feet 双脚约束创建失败")
        center_world = om.MMatrix(_matrix(c.xform(
            center, query=True, worldSpace=True, matrix=True)))
        offset_world = om.MMatrix(state.offset_world)
        parent_world = om.MMatrix(state.parent_world)
        opm = om.MMatrix(state.opm_value)
        local = offset_world * parent_world.inverse() * opm.inverse()
        static = c.createNode("multMatrix", name=spec.static_matrix)
        c.setAttr(static + ".matrixIn[0]", *tuple(local), type="matrix")
        if state.opm_source is None:
            c.setAttr(static + ".matrixIn[1]",
                      *state.opm_value, type="matrix")
        else:
            c.connectAttr(state.opm_source, static + ".matrixIn[1]")
        c.connectAttr(spec.offset_parent + ".worldMatrix[0]",
                      static + ".matrixIn[2]")
        attached = c.createNode("multMatrix", name=spec.attached_matrix)
        c.setAttr(attached + ".matrixIn[0]",
                  *tuple(offset_world * center_world.inverse()),
                  type="matrix")
        c.connectAttr(center + ".worldMatrix[0]",
                      attached + ".matrixIn[1]")
        blend = c.createNode("blendMatrix", name=spec.blend_matrix)
        c.connectAttr(static + ".matrixSum", blend + ".inputMatrix")
        c.connectAttr(attached + ".matrixSum",
                      blend + ".target[0].targetMatrix")
        for attr in ("useScale", "useShear"):
            c.setAttr(blend + ".target[0]." + attr, False)
        c.addAttr(spec.root_control, longName="centerBetweenFeet",
                  attributeType="double", minValue=0, maxValue=10,
                  defaultValue=0, keyable=True)
        weight = c.createNode("multDoubleLinear", name=spec.weight_node)
        c.setAttr(weight + ".input2", 0.1)
        c.connectAttr(spec.root_control + ".centerBetweenFeet",
                      weight + ".input1")
        c.connectAttr(weight + ".output",
                      blend + ".target[0].weight")
        condition = c.createNode("condition", name=spec.state_condition)
        c.setAttr(condition + ".operation", 4)
        c.setAttr(condition + ".secondTerm", 0.1)
        c.setAttr(condition + ".colorIfTrueR", 2)
        c.setAttr(condition + ".colorIfFalseR", 0)
        c.connectAttr(spec.root_control + ".centerBetweenFeet",
                      condition + ".firstTerm")
        for constraint in (spec.point_constraint,
                           spec.orient_constraint):
            c.connectAttr(condition + ".outColorR",
                          constraint + ".nodeState", force=True)
        output = c.createNode("multMatrix", name=spec.output_matrix)
        c.setAttr(output + ".matrixIn[0]", *tuple(local.inverse()),
                  type="matrix")
        c.connectAttr(blend + ".outputMatrix", output + ".matrixIn[1]")
        c.connectAttr(spec.offset_parent + ".worldInverseMatrix[0]",
                      output + ".matrixIn[2]")
        if state.opm_source is not None:
            c.disconnectAttr(state.opm_source, plug)
        c.connectAttr(output + ".matrixSum", plug)
        actual = _matrix(c.xform(spec.root_offset, query=True,
                                 worldSpace=True, matrix=True))
        if any(abs(a - b) > 1e-4 for a, b in zip(actual, state.offset_world)):
            raise RuntimeError("Center Between Feet 改变了 Root 绑定姿态")

    def capture_body_center_between_feet(
        self, spec: BodyCenterBetweenFeetSpec,
        state: BodyCenterBetweenFeetState,
    ) -> bool:
        from maya.api import OpenMaya as om

        c = self._cmds
        kinds = (
            (spec.center, "transform"),
            (spec.point_constraint, "pointConstraint"),
            (spec.orient_constraint, "orientConstraint"),
            (spec.static_matrix, "multMatrix"),
            (spec.attached_matrix, "multMatrix"),
            (spec.blend_matrix, "blendMatrix"),
            (spec.weight_node, "multDoubleLinear"),
            (spec.state_condition, "condition"),
            (spec.output_matrix, "multMatrix"))
        if any(not c.objExists(name) or c.nodeType(name) != kind
               for name, kind in kinds):
            return False
        for command, node in ((c.pointConstraint, spec.point_constraint),
                              (c.orientConstraint, spec.orient_constraint)):
            targets = command(node, query=True, targetList=True) or []
            resolved = tuple((c.ls(target, long=True) or [target])[0]
                             for target in targets)
            if resolved != spec.targets:
                return False
        links = [
            (spec.offset_parent + ".worldMatrix[0]",
             spec.static_matrix + ".matrixIn[2]"),
            (spec.center + ".worldMatrix[0]",
             spec.attached_matrix + ".matrixIn[1]"),
            (spec.static_matrix + ".matrixSum",
             spec.blend_matrix + ".inputMatrix"),
            (spec.attached_matrix + ".matrixSum",
             spec.blend_matrix + ".target[0].targetMatrix"),
            (spec.root_control + ".centerBetweenFeet",
             spec.weight_node + ".input1"),
            (spec.weight_node + ".output",
             spec.blend_matrix + ".target[0].weight"),
            (spec.root_control + ".centerBetweenFeet",
             spec.state_condition + ".firstTerm"),
            (spec.state_condition + ".outColorR",
             spec.point_constraint + ".nodeState"),
            (spec.state_condition + ".outColorR",
             spec.orient_constraint + ".nodeState"),
            (spec.blend_matrix + ".outputMatrix",
             spec.output_matrix + ".matrixIn[1]"),
            (spec.offset_parent + ".worldInverseMatrix[0]",
             spec.output_matrix + ".matrixIn[2]"),
            (spec.output_matrix + ".matrixSum",
             spec.root_offset + ".offsetParentMatrix")]
        if state.opm_source is not None:
            links.append((state.opm_source,
                          spec.static_matrix + ".matrixIn[1]"))
        elif any(abs(a - b) > 1e-8 for a, b in zip(
                _matrix(c.getAttr(spec.static_matrix + ".matrixIn[1]")),
                state.opm_value)):
            return False
        correction = _matrix(c.getAttr(
            spec.attached_matrix + ".matrixIn[0]"))
        center_world = _matrix(c.xform(
            spec.center, query=True, worldSpace=True, matrix=True))
        if (len(correction) != 16 or any(abs(a - b) > 1e-5
                for a, b in zip(tuple(om.MMatrix(correction)
                                    * om.MMatrix(center_world)),
                                state.offset_world))):
            return False
        return (all(c.connectionInfo(dst, sourceFromDestination=True) == src
                    for src, dst in links)
                and abs(float(c.getAttr(spec.root_control
                                        + ".centerBetweenFeet"))) < 1e-8
                and abs(float(c.getAttr(spec.weight_node + ".input2"))
                        - 0.1) < 1e-8
                and int(c.getAttr(spec.state_condition + ".operation")) == 4
                and all(not bool(c.getAttr(spec.blend_matrix
                                            + ".target[0]." + attr))
                        for attr in ("useScale", "useShear"))
                and all(abs(a - b) <= 1e-4 for a, b in zip(
                    _matrix(c.xform(spec.root_offset, query=True,
                                    worldSpace=True, matrix=True)),
                    state.offset_world)))
