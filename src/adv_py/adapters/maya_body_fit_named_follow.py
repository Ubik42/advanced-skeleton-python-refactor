"""Build ADV follow* target blends on existing FK receiver layers."""
from __future__ import annotations

from math import isfinite

from adv_py.core.body_fit_named_follow import (
    BodyFitNamedFollowSpec, BodyFitNamedFollowState,
)


def _matrix(values) -> tuple[float, ...]:
    if len(values) == 1 and isinstance(values[0], (tuple, list)):
        values = values[0]
    return tuple(float(value) for value in values)


class MayaBodyFitNamedFollowMixin:
    def resolve_body_fit_named_follow_targets(
        self, spec: BodyFitNamedFollowSpec,
    ) -> tuple[str, ...]:
        c = self._cmds
        leaf = spec.fk_control.rsplit("|", 1)[-1]
        namespace = leaf.split(":", 1)[0] + ":" if ":" in leaf else ""
        resolved = []
        for target in spec.targets:
            candidates = (target.name + "_" + spec.side,
                          target.name + "_M", target.name)
            if spec.side == "M":
                candidates += (target.name + "_R", target.name + "_L")
            path = None
            for candidate in dict.fromkeys(candidates):
                matches = c.ls(namespace + candidate, long=True) or []
                matches = [item for item in matches if c.nodeType(item) in
                           ("transform", "joint")]
                if len(matches) > 1:
                    raise ValueError("Follow* 目标名称不唯一：" + candidate)
                if matches:
                    path = matches[0]
                    break
            if path is None:
                raise ValueError("Follow* 目标对象缺失：" + target.name)
            if (path == spec.source_body
                    or path.startswith(spec.source_body + "|")
                    or path == spec.fk_offset
                    or path.startswith(spec.fk_offset + "|")):
                raise ValueError("Follow* 目标依赖自身 FK：" + path)
            resolved.append(path)
        return tuple(resolved)

    def preflight_body_fit_named_follow(
        self, spec: BodyFitNamedFollowSpec,
    ) -> BodyFitNamedFollowState:
        c = self._cmds
        for path in (spec.fk_control, spec.fk_offset, spec.receiver):
            if (c.ls(path, long=True, type="transform") or []) != [path]:
                raise ValueError("Follow* 控制层缺失：" + path)
        if (c.listRelatives(spec.receiver, parent=True,
                            fullPath=True) or []) != [spec.fk_offset]:
            raise ValueError("Follow* 接收层不在 FK Offset 下")
        if any(self.find_name_collisions(name) for name in spec.node_names):
            raise ValueError("Follow* 节点名称冲突")
        for target in spec.targets:
            if c.attributeQuery("follow" + target.name,
                                node=spec.fk_control, exists=True):
                raise ValueError("Follow* FK 控制器属性冲突：" + target.name)
        plug = spec.receiver + ".offsetParentMatrix"
        if c.getAttr(plug, lock=True):
            raise ValueError("Follow* 接收层矩阵已锁定")
        upstream = c.connectionInfo(plug, sourceFromDestination=True) or None
        if upstream is None and not c.getAttr(plug, settable=True):
            raise ValueError("Follow* 接收层矩阵不可写")
        paths = self.resolve_body_fit_named_follow_targets(spec)
        worlds = tuple(_matrix(c.xform(path, query=True, worldSpace=True,
                                       matrix=True)) for path in paths)
        state = BodyFitNamedFollowState(
            paths, worlds,
            _matrix(c.xform(spec.fk_offset, query=True, worldSpace=True,
                            matrix=True)),
            _matrix(c.xform(spec.receiver, query=True, worldSpace=True,
                            matrix=True)),
            upstream, _matrix(c.getAttr(plug)))
        if any(len(matrix) != 16 or not all(isfinite(value) for value in matrix)
               for matrix in worlds + (state.offset_world,
                                       state.receiver_world,
                                       state.receiver_opm_value)):
            raise ValueError("Follow* 绑定矩阵无效")
        return state

    def create_body_fit_named_follow(
        self, spec: BodyFitNamedFollowSpec,
        state: BodyFitNamedFollowState,
    ) -> None:
        self._require_transaction()
        from maya.api import OpenMaya as om

        c = self._cmds
        plug = spec.receiver + ".offsetParentMatrix"
        if (c.connectionInfo(plug, sourceFromDestination=True) or None
                ) != state.receiver_opm_source:
            raise ValueError("Follow* 接收层矩阵来源已变化")
        self._transaction_changed = True
        blend = c.createNode("blendMatrix", name=spec.blend_node)
        for index, (target, path, world) in enumerate(zip(
                spec.targets, state.target_paths, state.target_worlds)):
            matrix = c.createNode("multMatrix", name=target.matrix_node)
            offset = tuple(om.MMatrix(state.offset_world)
                           * om.MMatrix(world).inverse())
            c.setAttr(matrix + ".matrixIn[0]", *offset, type="matrix")
            c.connectAttr(path + ".worldMatrix[0]",
                          matrix + ".matrixIn[1]")
            c.connectAttr(spec.fk_offset + ".worldInverseMatrix[0]",
                          matrix + ".matrixIn[2]")
            c.connectAttr(matrix + ".matrixSum",
                          blend + f".target[{index}].targetMatrix")
            attr = "follow" + target.name
            c.addAttr(spec.fk_control, longName=attr,
                      attributeType="double", minValue=0, maxValue=10,
                      defaultValue=target.weight, keyable=True)
            weight = c.createNode("multDoubleLinear", name=target.weight_node)
            c.setAttr(weight + ".input2", 0.1)
            c.connectAttr(spec.fk_control + "." + attr,
                          weight + ".input1")
            c.connectAttr(weight + ".output",
                          blend + f".target[{index}].weight")
        receiver = c.createNode("multMatrix", name=spec.receiver_node)
        if state.receiver_opm_source is None:
            c.setAttr(receiver + ".matrixIn[0]",
                      *state.receiver_opm_value, type="matrix")
        else:
            c.connectAttr(state.receiver_opm_source,
                          receiver + ".matrixIn[0]")
            c.disconnectAttr(state.receiver_opm_source, plug)
        c.connectAttr(blend + ".outputMatrix",
                      receiver + ".matrixIn[1]")
        c.connectAttr(receiver + ".matrixSum", plug)
        current = _matrix(c.xform(spec.receiver, query=True,
                                  worldSpace=True, matrix=True))
        if any(abs(a - b) > 1e-4 for a, b in zip(
                current, state.receiver_world)):
            raise RuntimeError("Follow* 改变了 FK 绑定姿态")

    def capture_body_fit_named_follow(
        self, spec: BodyFitNamedFollowSpec,
        state: BodyFitNamedFollowState,
    ) -> bool:
        from maya.api import OpenMaya as om

        c = self._cmds
        if (c.nodeType(spec.blend_node) != "blendMatrix"
                or c.nodeType(spec.receiver_node) != "multMatrix"):
            return False
        links = [
            (spec.blend_node + ".outputMatrix",
             spec.receiver_node + ".matrixIn[1]"),
            (spec.receiver_node + ".matrixSum",
             spec.receiver + ".offsetParentMatrix"),
        ]
        if state.receiver_opm_source is not None:
            links.append((state.receiver_opm_source,
                          spec.receiver_node + ".matrixIn[0]"))
        elif any(abs(a - b) > 1e-8 for a, b in zip(
                _matrix(c.getAttr(spec.receiver_node + ".matrixIn[0]")),
                state.receiver_opm_value)):
            return False
        for index, (target, path, world) in enumerate(zip(
                spec.targets, state.target_paths, state.target_worlds)):
            if (c.nodeType(target.matrix_node) != "multMatrix"
                    or c.nodeType(target.weight_node) != "multDoubleLinear"):
                return False
            expected = tuple(om.MMatrix(state.offset_world)
                             * om.MMatrix(world).inverse())
            actual = _matrix(c.getAttr(target.matrix_node + ".matrixIn[0]"))
            if (len(actual) != 16 or any(abs(a - b) > 1e-5
                    for a, b in zip(actual, expected))):
                return False
            attr = "follow" + target.name
            if (not c.attributeQuery(attr, node=spec.fk_control, exists=True)
                    or abs(float(c.getAttr(spec.fk_control + "." + attr))
                           - target.weight) > 1e-8
                    or abs(float(c.getAttr(target.weight_node + ".input2"))
                           - 0.1) > 1e-8):
                return False
            links.extend((
                (path + ".worldMatrix[0]",
                 target.matrix_node + ".matrixIn[1]"),
                (spec.fk_offset + ".worldInverseMatrix[0]",
                 target.matrix_node + ".matrixIn[2]"),
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
                    _matrix(c.xform(spec.receiver, query=True,
                                    worldSpace=True, matrix=True)),
                    state.receiver_world)))
