"""Drive FK Offset OPM from ADV Main/Root/Chest/Parent follow spaces."""
from __future__ import annotations

from math import isfinite

from adv_py.core.body_fit_follow_spaces import (
    BodyFitFollowSpacesSpec, BodyFitFollowSpacesState,
)


def _matrix(values) -> tuple[float, ...]:
    if len(values) == 1 and isinstance(values[0], (tuple, list)):
        values = values[0]
    return tuple(float(value) for value in values)


class MayaBodyFitFollowSpacesMixin:
    def preflight_body_fit_follow_spaces(
        self, spec: BodyFitFollowSpacesSpec,
    ) -> BodyFitFollowSpacesState:
        c = self._cmds
        for path in (spec.fk_control, spec.fk_offset):
            if (c.ls(path, long=True, type="transform") or []) != [path]:
                raise ValueError("Follow Spaces 控制层缺失：" + path)
        if ((c.ls(spec.offset_parent, long=True) or [])
                != [spec.offset_parent]
                or c.nodeType(spec.offset_parent)
                not in ("transform", "joint")):
            raise ValueError("Follow Spaces FK Offset 父级缺失："
                             + spec.offset_parent)
        if (c.listRelatives(spec.fk_offset, parent=True,
                            fullPath=True) or []) != [spec.offset_parent]:
            raise ValueError("Follow Spaces FK Offset 父级已变化")
        if any(self.find_name_collisions(name) for name in spec.node_names):
            raise ValueError("Follow Spaces 节点名称冲突")
        for target in spec.targets:
            if (c.ls(target.source, long=True) or []) != [target.source]:
                raise ValueError("Follow Spaces 目标缺失：" + target.source)
            if c.nodeType(target.source) not in ("transform", "joint"):
                raise ValueError("Follow Spaces 目标类型无效：" + target.source)
            if c.attributeQuery("follow" + target.label,
                                node=spec.fk_control, exists=True):
                raise ValueError("Follow Spaces FK 权重属性已存在："
                                 + target.label)
        plug = spec.fk_offset + ".offsetParentMatrix"
        if c.getAttr(plug, lock=True):
            raise ValueError("Follow Spaces FK Offset 矩阵已锁定")
        upstream = c.connectionInfo(plug, sourceFromDestination=True) or None
        if upstream is None and not c.getAttr(plug, settable=True):
            raise ValueError("Follow Spaces FK Offset 矩阵不可写")
        state = BodyFitFollowSpacesState(
            _matrix(c.xform(spec.fk_offset, query=True,
                            worldSpace=True, matrix=True)),
            _matrix(c.xform(spec.offset_parent, query=True,
                            worldSpace=True, matrix=True)),
            tuple(_matrix(c.xform(target.source, query=True,
                                  worldSpace=True, matrix=True))
                  for target in spec.targets),
            upstream, _matrix(c.getAttr(plug)))
        if any(len(matrix) != 16 or not all(isfinite(value) for value in matrix)
               for matrix in (state.offset_world, state.parent_world,
                              state.opm_value, *state.target_worlds)):
            raise ValueError("Follow Spaces 绑定矩阵无效")
        return state

    def create_body_fit_follow_spaces(
        self, spec: BodyFitFollowSpacesSpec,
        state: BodyFitFollowSpacesState,
    ) -> None:
        self._require_transaction()
        from maya.api import OpenMaya as om

        c = self._cmds
        plug = spec.fk_offset + ".offsetParentMatrix"
        if (c.connectionInfo(plug, sourceFromDestination=True) or None
                ) != state.opm_source:
            raise ValueError("Follow Spaces FK Offset 原矩阵来源已变化")
        offset_world = om.MMatrix(state.offset_world)
        parent_world = om.MMatrix(state.parent_world)
        opm = om.MMatrix(state.opm_value)
        local_inverse = (offset_world * parent_world.inverse()
                         * opm.inverse()).inverse()
        self._transaction_changed = True
        blend = c.createNode("blendMatrix", name=spec.blend_node)
        c.setAttr(blend + ".inputMatrix", *state.offset_world,
                  type="matrix")
        for index, (target, world) in enumerate(zip(
                spec.targets, state.target_worlds)):
            matrix = c.createNode("multMatrix", name=target.matrix_node)
            offset = tuple(offset_world * om.MMatrix(world).inverse())
            c.setAttr(matrix + ".matrixIn[0]", *offset, type="matrix")
            c.connectAttr(target.source + ".worldMatrix[0]",
                          matrix + ".matrixIn[1]")
            c.connectAttr(matrix + ".matrixSum",
                          blend + f".target[{index}].targetMatrix")
            attr = "follow" + target.label
            c.addAttr(spec.fk_control, longName=attr,
                      attributeType="double", minValue=0, maxValue=10,
                      defaultValue=target.weight, keyable=True)
            weight = c.createNode("multDoubleLinear", name=target.weight_node)
            c.setAttr(weight + ".input2", 0.1)
            c.connectAttr(spec.fk_control + "." + attr,
                          weight + ".input1")
            c.connectAttr(weight + ".output",
                          blend + f".target[{index}].weight")
        output = c.createNode("multMatrix", name=spec.output_node)
        c.setAttr(output + ".matrixIn[0]", *tuple(local_inverse),
                  type="matrix")
        c.connectAttr(blend + ".outputMatrix",
                      output + ".matrixIn[1]")
        c.connectAttr(spec.offset_parent + ".worldInverseMatrix[0]",
                      output + ".matrixIn[2]")
        if state.opm_source is not None:
            c.disconnectAttr(state.opm_source, plug)
        c.connectAttr(output + ".matrixSum", plug)
        actual = _matrix(c.xform(spec.fk_offset, query=True,
                                 worldSpace=True, matrix=True))
        if any(abs(a - b) > 1e-4 for a, b in zip(actual, state.offset_world)):
            raise RuntimeError("Follow Spaces 改变了 FK 绑定姿态")

    def capture_body_fit_follow_spaces(
        self, spec: BodyFitFollowSpacesSpec,
        state: BodyFitFollowSpacesState,
    ) -> bool:
        from maya.api import OpenMaya as om

        c = self._cmds
        if (c.nodeType(spec.blend_node) != "blendMatrix"
                or c.nodeType(spec.output_node) != "multMatrix"):
            return False
        offset_world = om.MMatrix(state.offset_world)
        parent_world = om.MMatrix(state.parent_world)
        opm = om.MMatrix(state.opm_value)
        expected_local_inverse = tuple((offset_world
            * parent_world.inverse() * opm.inverse()).inverse())
        actual_local_inverse = _matrix(c.getAttr(
            spec.output_node + ".matrixIn[0]"))
        input_world = _matrix(c.getAttr(spec.blend_node + ".inputMatrix"))
        if (len(actual_local_inverse) != 16
                or any(abs(a - b) > 1e-5 for a, b in zip(
                    actual_local_inverse, expected_local_inverse))
                or any(abs(a - b) > 1e-5 for a, b in zip(
                    input_world, state.offset_world))):
            return False
        links = [
            (spec.blend_node + ".outputMatrix",
             spec.output_node + ".matrixIn[1]"),
            (spec.offset_parent + ".worldInverseMatrix[0]",
             spec.output_node + ".matrixIn[2]"),
            (spec.output_node + ".matrixSum",
             spec.fk_offset + ".offsetParentMatrix"),
        ]
        for index, (target, world) in enumerate(zip(
                spec.targets, state.target_worlds)):
            if (c.nodeType(target.matrix_node) != "multMatrix"
                    or c.nodeType(target.weight_node) != "multDoubleLinear"):
                return False
            expected = tuple(offset_world * om.MMatrix(world).inverse())
            actual = _matrix(c.getAttr(target.matrix_node + ".matrixIn[0]"))
            attr = "follow" + target.label
            if (len(actual) != 16 or any(abs(a - b) > 1e-5
                    for a, b in zip(actual, expected))
                    or not c.attributeQuery(attr, node=spec.fk_control,
                                            exists=True)
                    or abs(float(c.getAttr(spec.fk_control + "." + attr))
                           - target.weight) > 1e-8
                    or abs(float(c.getAttr(target.weight_node + ".input2"))
                           - 0.1) > 1e-8):
                return False
            links.extend((
                (target.source + ".worldMatrix[0]",
                 target.matrix_node + ".matrixIn[1]"),
                (target.matrix_node + ".matrixSum",
                 spec.blend_node + f".target[{index}].targetMatrix"),
                (spec.fk_control + "." + attr,
                 target.weight_node + ".input1"),
                (target.weight_node + ".output",
                 spec.blend_node + f".target[{index}].weight"),
            ))
        return (all(c.connectionInfo(destination,
                                     sourceFromDestination=True) == source
                    for source, destination in links)
                and all(abs(a - b) <= 1e-4 for a, b in zip(
                    _matrix(c.xform(spec.fk_offset, query=True,
                                    worldSpace=True, matrix=True)),
                    state.offset_world)))
