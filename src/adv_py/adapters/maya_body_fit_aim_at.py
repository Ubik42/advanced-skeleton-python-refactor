"""Build Fit aimAt orientation on an existing FK receiver layer."""
from __future__ import annotations

from math import isfinite

from adv_py.core.body_fit_aim_at import BodyFitAimAtSpec, BodyFitAimAtState


def _matrix(values) -> tuple[float, ...]:
    if len(values) == 1 and isinstance(values[0], (tuple, list)):
        values = values[0]
    return tuple(float(value) for value in values)


def _axis(label: str, sign: int) -> tuple[float, float, float]:
    return tuple(float(sign if axis == label else 0)
                 for axis in "xyz")


class MayaBodyFitAimAtMixin:
    def preflight_body_fit_aim_at(
        self, spec: BodyFitAimAtSpec,
    ) -> BodyFitAimAtState:
        c = self._cmds
        for path in (spec.fk_control, spec.fk_offset, spec.receiver,
                     spec.target_control):
            if (c.ls(path, long=True, type="transform") or []) != [path]:
                raise ValueError("Fit AimAt FK 控制层缺失：" + path)
        if (c.listRelatives(spec.receiver, parent=True,
                            fullPath=True) or []) != [spec.fk_offset]:
            raise ValueError("Fit AimAt 接收层不在 FK Offset 下")
        if (spec.target_control == spec.fk_offset
                or spec.target_control.startswith(spec.fk_offset + "|")):
            raise ValueError("Fit AimAt 目标位于自身 FK 控制层下")
        if any(self.find_name_collisions(name) for name in spec.node_names):
            raise ValueError("Fit AimAt 节点名称冲突")
        if c.attributeQuery("aimAt", node=spec.fk_control, exists=True):
            raise ValueError("Fit AimAt FK 控制器权重属性已存在")
        if (spec.aim_axis not in ("x", "y", "z")
                or spec.up_axis not in ("x", "y", "z")
                or spec.aim_axis == spec.up_axis
                or spec.up_object not in ("self", "target")):
            raise ValueError("Fit AimAt 轴向或 Up 来源无效")
        plug = spec.receiver + ".offsetParentMatrix"
        if c.getAttr(plug, lock=True):
            raise ValueError("Fit AimAt 接收层矩阵已锁定")
        upstream = c.connectionInfo(plug, sourceFromDestination=True) or None
        if upstream is None and not c.getAttr(plug, settable=True):
            raise ValueError("Fit AimAt 接收层矩阵不可写")
        state = BodyFitAimAtState(
            _matrix(c.xform(spec.fk_offset, query=True,
                            worldSpace=True, matrix=True)),
            _matrix(c.xform(spec.receiver, query=True,
                            worldSpace=True, matrix=True)),
            _matrix(c.xform(spec.target_control, query=True,
                            worldSpace=True, matrix=True)),
            upstream, _matrix(c.getAttr(plug)),
            bool(c.getAttr(spec.receiver + ".inheritsTransform")))
        if any(len(matrix) != 16 or not all(isfinite(value) for value in matrix)
               for matrix in (state.offset_world, state.receiver_world,
                              state.target_world, state.receiver_opm_value)):
            raise ValueError("Fit AimAt 绑定矩阵无效")
        if not spec.source_native and sum((a - b) ** 2 for a, b in zip(
                state.offset_world[12:15],
                state.target_world[12:15])) < 1e-10:
            raise ValueError("Fit AimAt 来源与目标绑定位置重合")
        return state

    def create_body_fit_aim_at(
        self, spec: BodyFitAimAtSpec, state: BodyFitAimAtState,
    ) -> None:
        self._require_transaction()
        if spec.source_native:
            from .maya_source_fit_aim_at import create
            return create(self, spec, state)
        from maya.api import OpenMaya as om

        c = self._cmds
        plug = spec.receiver + ".offsetParentMatrix"
        if (c.connectionInfo(plug, sourceFromDestination=True) or None
                ) != state.receiver_opm_source:
            raise ValueError("Fit AimAt 接收层矩阵来源已变化")
        self._transaction_changed = True
        aim = c.createNode("aimMatrix", name=spec.aim_matrix)
        c.setAttr(aim + ".primaryInputAxis",
                  *_axis(spec.aim_axis, spec.mirror_sign), type="double3")
        c.setAttr(aim + ".secondaryInputAxis",
                  *_axis(spec.up_axis, spec.mirror_sign), type="double3")
        c.setAttr(aim + ".secondaryTargetVector",
                  0.0, float(spec.mirror_sign), 0.0, type="double3")
        c.connectAttr(spec.fk_offset + ".worldMatrix[0]",
                      aim + ".inputMatrix")
        c.connectAttr(spec.target_control + ".worldMatrix[0]",
                      aim + ".primaryTargetMatrix")
        up_source = (spec.fk_offset if spec.up_object == "self"
                     else spec.target_control)
        c.connectAttr(up_source + ".worldMatrix[0]",
                      aim + ".secondaryTargetMatrix")
        aim_bind = _matrix(c.getAttr(aim + ".outputMatrix"))
        correction = tuple(om.MMatrix(state.offset_world)
                           * om.MMatrix(aim_bind).inverse())
        corrected = c.createNode("multMatrix", name=spec.corrected_matrix)
        c.setAttr(corrected + ".matrixIn[0]", *correction,
                  type="matrix")
        c.connectAttr(aim + ".outputMatrix",
                      corrected + ".matrixIn[1]")
        blend = c.createNode("blendMatrix", name=spec.blend_matrix)
        c.connectAttr(spec.fk_offset + ".worldMatrix[0]",
                      blend + ".inputMatrix")
        c.connectAttr(corrected + ".matrixSum",
                      blend + ".target[0].targetMatrix")
        c.addAttr(spec.fk_control, longName="aimAt",
                  attributeType="double", minValue=0, maxValue=10,
                  defaultValue=10, keyable=True)
        weight = c.createNode("multDoubleLinear", name=spec.weight_node)
        c.setAttr(weight + ".input2", 0.1)
        c.connectAttr(spec.fk_control + ".aimAt", weight + ".input1")
        c.connectAttr(weight + ".output",
                      blend + ".target[0].weight")
        delta = c.createNode("multMatrix", name=spec.delta_matrix)
        c.connectAttr(blend + ".outputMatrix", delta + ".matrixIn[0]")
        c.connectAttr(spec.fk_offset + ".worldInverseMatrix[0]",
                      delta + ".matrixIn[1]")
        rotation = c.createNode("pickMatrix", name=spec.rotation_pick)
        c.connectAttr(delta + ".matrixSum", rotation + ".inputMatrix")
        for attr in ("useTranslate", "useScale", "useShear"):
            c.setAttr(rotation + "." + attr, False)
        receiver = c.createNode("multMatrix", name=spec.receiver_matrix)
        if state.receiver_opm_source is None:
            c.setAttr(receiver + ".matrixIn[0]",
                      *state.receiver_opm_value, type="matrix")
        else:
            c.connectAttr(state.receiver_opm_source,
                          receiver + ".matrixIn[0]")
            c.disconnectAttr(state.receiver_opm_source, plug)
        c.connectAttr(rotation + ".outputMatrix",
                      receiver + ".matrixIn[1]")
        c.connectAttr(receiver + ".matrixSum", plug)
        actual = _matrix(c.xform(spec.receiver, query=True,
                                 worldSpace=True, matrix=True))
        if any(abs(a - b) > 1e-4 for a, b in zip(actual, state.receiver_world)):
            raise RuntimeError("Fit AimAt 改变了 FK 绑定姿态")

    def capture_body_fit_aim_at(
        self, spec: BodyFitAimAtSpec, state: BodyFitAimAtState,
    ) -> bool:
        if spec.source_native:
            from .maya_source_fit_aim_at import capture
            return capture(self, spec, state)
        from maya.api import OpenMaya as om

        c = self._cmds
        expected_types = (
            (spec.aim_matrix, "aimMatrix"),
            (spec.corrected_matrix, "multMatrix"),
            (spec.blend_matrix, "blendMatrix"),
            (spec.weight_node, "multDoubleLinear"),
            (spec.delta_matrix, "multMatrix"),
            (spec.rotation_pick, "pickMatrix"),
            (spec.receiver_matrix, "multMatrix"),
        )
        if any(not c.objExists(name) or c.nodeType(name) != kind
               for name, kind in expected_types):
            return False
        up_source = (spec.fk_offset if spec.up_object == "self"
                     else spec.target_control)
        links = [
            (spec.fk_offset + ".worldMatrix[0]",
             spec.aim_matrix + ".inputMatrix"),
            (spec.target_control + ".worldMatrix[0]",
             spec.aim_matrix + ".primaryTargetMatrix"),
            (up_source + ".worldMatrix[0]",
             spec.aim_matrix + ".secondaryTargetMatrix"),
            (spec.aim_matrix + ".outputMatrix",
             spec.corrected_matrix + ".matrixIn[1]"),
            (spec.fk_offset + ".worldMatrix[0]",
             spec.blend_matrix + ".inputMatrix"),
            (spec.corrected_matrix + ".matrixSum",
             spec.blend_matrix + ".target[0].targetMatrix"),
            (spec.fk_control + ".aimAt",
             spec.weight_node + ".input1"),
            (spec.weight_node + ".output",
             spec.blend_matrix + ".target[0].weight"),
            (spec.blend_matrix + ".outputMatrix",
             spec.delta_matrix + ".matrixIn[0]"),
            (spec.fk_offset + ".worldInverseMatrix[0]",
             spec.delta_matrix + ".matrixIn[1]"),
            (spec.delta_matrix + ".matrixSum",
             spec.rotation_pick + ".inputMatrix"),
            (spec.rotation_pick + ".outputMatrix",
             spec.receiver_matrix + ".matrixIn[1]"),
            (spec.receiver_matrix + ".matrixSum",
             spec.receiver + ".offsetParentMatrix"),
        ]
        if state.receiver_opm_source is not None:
            links.append((state.receiver_opm_source,
                          spec.receiver_matrix + ".matrixIn[0]"))
        elif any(abs(a - b) > 1e-8 for a, b in zip(
                _matrix(c.getAttr(spec.receiver_matrix + ".matrixIn[0]")),
                state.receiver_opm_value)):
            return False
        correction = _matrix(c.getAttr(
            spec.corrected_matrix + ".matrixIn[0]"))
        bind_aim = _matrix(c.getAttr(spec.aim_matrix + ".outputMatrix"))
        restored = tuple(om.MMatrix(correction) * om.MMatrix(bind_aim))
        if (len(correction) != 16
                or any(abs(a - b) > 1e-5 for a, b in zip(
                    restored, state.offset_world))
                or any(bool(c.getAttr(spec.rotation_pick + "." + attr))
                       for attr in ("useTranslate", "useScale", "useShear"))
                or abs(float(c.getAttr(spec.fk_control + ".aimAt"))
                       - 10.0) > 1e-8
                or abs(float(c.getAttr(spec.weight_node + ".input2"))
                       - 0.1) > 1e-8):
            return False
        for attr, expected in (
                ("primaryInputAxis", _axis(spec.aim_axis, spec.mirror_sign)),
                ("secondaryInputAxis", _axis(spec.up_axis, spec.mirror_sign)),
                ("secondaryTargetVector",
                 (0.0, float(spec.mirror_sign), 0.0))):
            actual = _matrix(c.getAttr(spec.aim_matrix + "." + attr))
            if len(actual) != 3 or any(abs(a - b) > 1e-8
                                       for a, b in zip(actual, expected)):
                return False
        return (all(c.isConnected(source, destination, ignoreUnitConversion=True)
                    for source, destination in links)
                and all(abs(a - b) <= 1e-4 for a, b in zip(
                    _matrix(c.xform(spec.receiver, query=True,
                                    worldSpace=True, matrix=True)),
                    state.receiver_world)))
