"""Maya graph for ADV Fit Follow without changing registered FK DAG paths."""
from __future__ import annotations

from math import isfinite

from adv_py.core.body_fit_follow import (
    BodyFitFollowSourceState, BodyFitFollowSpec,
)


def _matrix(values) -> tuple[float, ...]:
    if len(values) == 1 and isinstance(values[0], (tuple, list)):
        values = values[0]
    return tuple(float(value) for value in values)


class MayaBodyFitFollowMixin:
    def preflight_body_fit_follow(
        self, spec: BodyFitFollowSpec,
    ) -> BodyFitFollowSourceState:
        c = self._cmds
        nodes = [(spec.fk_control, "transform"),
                 (spec.fk_offset, "transform"),
                 (spec.receiver, "transform"),
                 (spec.primary_target, "joint")]
        if spec.opposite_target:
            nodes.append((spec.opposite_target, "joint"))
        if spec.ancestor_parent:
            nodes.append((spec.ancestor_parent, "joint"))
        for path, kind in nodes:
            if (c.ls(path, long=True, type=kind) or []) != [path]:
                raise ValueError("Fit Follow 节点缺失：" + path)
        if (c.listRelatives(spec.receiver, parent=True,
                            fullPath=True) or []) != [spec.fk_offset]:
            raise ValueError("Fit Follow 接收层不在 FK Offset 下")
        if any(self.find_name_collisions(name) for name in spec.node_names):
            raise ValueError("Fit Follow 节点名称冲突")
        for attr in (spec.control_attribute,) + (
                ("followLeftRight",) if spec.opposite_target else ()) + (
                ("followWorld",) if spec.world_target else ()):
            if c.attributeQuery(attr, node=spec.fk_control, exists=True):
                raise ValueError("FK 控制器已有 Follow 属性：" + attr)
        plug = spec.receiver + ".offsetParentMatrix"
        if c.getAttr(plug, lock=True):
            raise ValueError("Fit Follow 接收层矩阵已锁定")
        upstream = c.connectionInfo(plug, sourceFromDestination=True) or None
        if upstream is None and not c.getAttr(plug, settable=True):
            raise ValueError("Fit Follow 接收层矩阵不可写")
        sources = (spec.primary_target,) + (
            (spec.opposite_target,) if spec.opposite_target else ())
        if any(target == spec.fk_offset or target.startswith(
                spec.fk_offset + "|") for target in sources):
            raise ValueError("Fit Follow 目标位于自身 FK 控制层下")
        state = BodyFitFollowSourceState(
            upstream, _matrix(c.getAttr(plug)),
            _matrix(c.xform(spec.fk_offset, query=True,
                            worldSpace=True, matrix=True)),
            _matrix(c.xform(spec.receiver, query=True,
                            worldSpace=True, matrix=True)),
            _matrix(c.xform(spec.primary_target, query=True,
                            worldSpace=True, matrix=True)),
            (_matrix(c.xform(spec.opposite_target, query=True,
                             worldSpace=True, matrix=True))
             if spec.opposite_target else None),
            (_matrix(c.xform(spec.ancestor_parent, query=True,
                             worldSpace=True, matrix=True))
             if spec.ancestor_parent else None))
        matrices = (state.receiver_opm_value, state.offset_world,
                    state.receiver_world, state.primary_world) + (
                        (state.opposite_world,)
                        if state.opposite_world is not None else ()) + (
                        (state.ancestor_parent_world,)
                        if state.ancestor_parent_world is not None else ())
        if any(len(matrix) != 16 or not all(isfinite(v) for v in matrix)
               for matrix in matrices):
            raise ValueError("Fit Follow 绑定矩阵无效")
        return state

    def create_body_fit_follow(
        self, spec: BodyFitFollowSpec,
        source: BodyFitFollowSourceState,
    ) -> None:
        self._require_transaction()
        from maya.api import OpenMaya as om

        c = self._cmds
        if (source.receiver_opm_source != (
                c.connectionInfo(spec.receiver + ".offsetParentMatrix",
                                 sourceFromDestination=True) or None)):
            raise ValueError("Fit Follow 接收层矩阵来源已变化")
        self._transaction_changed = True

        def follow_matrix(name: str, target: str,
                          bind_target: tuple[float, ...]) -> None:
            c.createNode("multMatrix", name=name)
            offset = tuple(om.MMatrix(source.offset_world)
                           * om.MMatrix(bind_target).inverse())
            c.setAttr(name + ".matrixIn[0]", *offset, type="matrix")
            c.connectAttr(target + ".worldMatrix[0]",
                          name + ".matrixIn[1]")

        follow_matrix(spec.primary_matrix, spec.primary_target,
                      source.primary_world)
        primary_output = spec.primary_matrix + ".matrixSum"
        if spec.ancestor_parent is not None:
            if (source.ancestor_parent_world is None
                    or spec.primary_rotation_pick is None
                    or spec.ancestor_parent_matrix is None
                    or spec.ancestor_translation_pick is None
                    or spec.ancestor_mix is None):
                raise ValueError("Fit Follow 祖先分支矩阵规划不完整")
            rotation = c.createNode("pickMatrix",
                                    name=spec.primary_rotation_pick)
            c.connectAttr(primary_output, rotation + ".inputMatrix")
            for attr in ("useTranslate", "useScale", "useShear"):
                c.setAttr(rotation + "." + attr, False)
            follow_matrix(spec.ancestor_parent_matrix,
                          spec.ancestor_parent,
                          source.ancestor_parent_world)
            translation = c.createNode(
                "pickMatrix", name=spec.ancestor_translation_pick)
            c.connectAttr(spec.ancestor_parent_matrix + ".matrixSum",
                          translation + ".inputMatrix")
            c.setAttr(translation + ".useRotate", False)
            mixed = c.createNode("multMatrix", name=spec.ancestor_mix)
            c.connectAttr(rotation + ".outputMatrix",
                          mixed + ".matrixIn[0]")
            c.connectAttr(translation + ".outputMatrix",
                          mixed + ".matrixIn[1]")
            primary_output = mixed + ".matrixSum"
        if spec.opposite_target is not None:
            if spec.opposite_matrix is None or source.opposite_world is None:
                raise ValueError("Fit Follow 对侧矩阵规划不完整")
            follow_matrix(spec.opposite_matrix, spec.opposite_target,
                          source.opposite_world)

        blend = c.createNode("blendMatrix", name=spec.blend_matrix)
        c.connectAttr(spec.fk_offset + ".worldMatrix[0]",
                      blend + ".inputMatrix")
        c.connectAttr(primary_output,
                      blend + ".target[0].targetMatrix")
        if spec.opposite_matrix is not None:
            c.connectAttr(spec.opposite_matrix + ".matrixSum",
                          blend + ".target[1].targetMatrix")
        if spec.world_target:
            c.setAttr(blend + ".target[2].targetMatrix",
                      *source.offset_world, type="matrix")

        delta = c.createNode("multMatrix", name=spec.delta_matrix)
        c.connectAttr(blend + ".outputMatrix",
                      delta + ".matrixIn[0]")
        c.connectAttr(spec.fk_offset + ".worldInverseMatrix[0]",
                      delta + ".matrixIn[1]")
        receiver = c.createNode("multMatrix", name=spec.receiver_matrix)
        if source.receiver_opm_source is not None:
            c.connectAttr(source.receiver_opm_source,
                          receiver + ".matrixIn[0]")
            c.disconnectAttr(source.receiver_opm_source,
                             spec.receiver + ".offsetParentMatrix")
        else:
            c.setAttr(receiver + ".matrixIn[0]",
                      *source.receiver_opm_value, type="matrix")
        c.connectAttr(delta + ".matrixSum",
                      receiver + ".matrixIn[1]")
        c.connectAttr(receiver + ".matrixSum",
                      spec.receiver + ".offsetParentMatrix")

        weights = ((spec.control_attribute, spec.primary_weight, 0, 10.0),) + (
            (("followLeftRight", spec.opposite_weight, 1, 0.0),)
            if spec.opposite_target else ()) + (
            (("followWorld", spec.world_weight, 2, 0.0),)
            if spec.world_target else ())
        for attr, name, index, default in weights:
            if name is None:
                raise ValueError("Fit Follow 权重节点名称缺失")
            c.addAttr(spec.fk_control, longName=attr,
                      attributeType="double", minValue=0, maxValue=10,
                      defaultValue=default, keyable=True)
            node = c.createNode("multDoubleLinear", name=name)
            c.setAttr(node + ".input2", 0.1)
            c.connectAttr(spec.fk_control + "." + attr,
                          node + ".input1")
            c.connectAttr(node + ".output",
                          blend + f".target[{index}].weight")
        actual = _matrix(c.xform(spec.receiver, query=True,
                                 worldSpace=True, matrix=True))
        if any(abs(a - b) > 1e-4 for a, b in zip(
                actual, source.receiver_world)):
            raise RuntimeError("Fit Follow 改变了 FK 绑定姿态")

    def capture_body_fit_follow(
        self, spec: BodyFitFollowSpec,
        source: BodyFitFollowSourceState,
    ) -> bool:
        from maya.api import OpenMaya as om

        c = self._cmds
        if any(not c.objExists(name) for name in spec.node_names):
            return False
        if (c.nodeType(spec.blend_matrix) != "blendMatrix"
                or c.nodeType(spec.delta_matrix) != "multMatrix"
                or c.nodeType(spec.receiver_matrix) != "multMatrix"
                or c.nodeType(spec.primary_matrix) != "multMatrix"
                or (spec.opposite_matrix is not None and
                    c.nodeType(spec.opposite_matrix) != "multMatrix")):
            return False
        primary_output = spec.primary_matrix + ".matrixSum"
        if spec.ancestor_parent is not None:
            if (source.ancestor_parent_world is None
                    or spec.primary_rotation_pick is None
                    or spec.ancestor_parent_matrix is None
                    or spec.ancestor_translation_pick is None
                    or spec.ancestor_mix is None
                    or c.nodeType(spec.primary_rotation_pick) != "pickMatrix"
                    or c.nodeType(spec.ancestor_parent_matrix) != "multMatrix"
                    or c.nodeType(spec.ancestor_translation_pick) != "pickMatrix"
                    or c.nodeType(spec.ancestor_mix) != "multMatrix"):
                return False
            primary_output = spec.ancestor_mix + ".matrixSum"
        links = [
            (spec.primary_target + ".worldMatrix[0]",
             spec.primary_matrix + ".matrixIn[1]"),
            (spec.fk_offset + ".worldMatrix[0]",
             spec.blend_matrix + ".inputMatrix"),
            (primary_output,
             spec.blend_matrix + ".target[0].targetMatrix"),
            (spec.blend_matrix + ".outputMatrix",
             spec.delta_matrix + ".matrixIn[0]"),
            (spec.fk_offset + ".worldInverseMatrix[0]",
             spec.delta_matrix + ".matrixIn[1]"),
            (spec.delta_matrix + ".matrixSum",
             spec.receiver_matrix + ".matrixIn[1]"),
            (spec.receiver_matrix + ".matrixSum",
             spec.receiver + ".offsetParentMatrix"),
        ]
        if spec.ancestor_parent is not None:
            links.extend((
                (spec.primary_matrix + ".matrixSum",
                 spec.primary_rotation_pick + ".inputMatrix"),
                (spec.ancestor_parent + ".worldMatrix[0]",
                 spec.ancestor_parent_matrix + ".matrixIn[1]"),
                (spec.ancestor_parent_matrix + ".matrixSum",
                 spec.ancestor_translation_pick + ".inputMatrix"),
                (spec.primary_rotation_pick + ".outputMatrix",
                 spec.ancestor_mix + ".matrixIn[0]"),
                (spec.ancestor_translation_pick + ".outputMatrix",
                 spec.ancestor_mix + ".matrixIn[1]"),
            ))
            if (any(bool(c.getAttr(spec.primary_rotation_pick + "." + attr))
                    for attr in ("useTranslate", "useScale", "useShear"))
                    or bool(c.getAttr(spec.ancestor_translation_pick
                                      + ".useRotate"))):
                return False
        if source.receiver_opm_source is not None:
            links.append((source.receiver_opm_source,
                          spec.receiver_matrix + ".matrixIn[0]"))
        elif any(abs(a - b) > 1e-8 for a, b in zip(
                source.receiver_opm_value,
                _matrix(c.getAttr(spec.receiver_matrix + ".matrixIn[0]")))):
            return False
        if spec.opposite_target is not None:
            links.extend((
                (spec.opposite_target + ".worldMatrix[0]",
                 spec.opposite_matrix + ".matrixIn[1]"),
                (spec.opposite_matrix + ".matrixSum",
                 spec.blend_matrix + ".target[1].targetMatrix"),
            ))
        for name, target_world in (
                ((spec.primary_matrix, source.primary_world),)
                + (((spec.opposite_matrix, source.opposite_world),)
                   if spec.opposite_matrix is not None else ())):
            if name is None or target_world is None:
                return False
            expected = tuple(om.MMatrix(source.offset_world)
                             * om.MMatrix(target_world).inverse())
            actual = _matrix(c.getAttr(name + ".matrixIn[0]"))
            if len(actual) != 16 or any(abs(a - b) > 1e-5
                                        for a, b in zip(actual, expected)):
                return False
        if spec.ancestor_parent is not None:
            expected = tuple(om.MMatrix(source.offset_world)
                             * om.MMatrix(
                                 source.ancestor_parent_world).inverse())
            actual = _matrix(c.getAttr(
                spec.ancestor_parent_matrix + ".matrixIn[0]"))
            if len(actual) != 16 or any(abs(a - b) > 1e-5
                                        for a, b in zip(actual, expected)):
                return False
        if spec.world_target:
            actual = _matrix(c.getAttr(
                spec.blend_matrix + ".target[2].targetMatrix"))
            if len(actual) != 16 or any(abs(a - b) > 1e-5
                                        for a, b in zip(
                                            actual, source.offset_world)):
                return False
        weights = ((spec.control_attribute, spec.primary_weight, 0, 10.0),) + (
            (("followLeftRight", spec.opposite_weight, 1, 0.0),)
            if spec.opposite_target else ()) + (
            (("followWorld", spec.world_weight, 2, 0.0),)
            if spec.world_target else ())
        for attr, name, index, default in weights:
            if (name is None or c.nodeType(name) != "multDoubleLinear"
                    or not c.attributeQuery(attr, node=spec.fk_control,
                                            exists=True)
                    or abs(float(c.getAttr(
                        spec.fk_control + "." + attr)) - default) > 1e-8
                    or abs(float(c.getAttr(name + ".input2")) - 0.1) > 1e-8):
                return False
            links.extend(((spec.fk_control + "." + attr,
                           name + ".input1"),
                          (name + ".output",
                           spec.blend_matrix +
                           f".target[{index}].weight")))
        return (all(c.connectionInfo(destination,
                                     sourceFromDestination=True) == upstream
                    for upstream, destination in links)
                and all(abs(a - b) <= 1e-4 for a, b in zip(
                    _matrix(c.xform(spec.receiver, query=True,
                                    worldSpace=True, matrix=True)),
                    source.receiver_world)))
