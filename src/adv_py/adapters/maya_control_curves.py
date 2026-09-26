"""Maya materialization for post-build NURBS controller curve edits."""
from __future__ import annotations

from adv_py.core.control_curves import (
    ControlCurveShapeState, ControlCurveState, ControlCurveValidationError,
)


class MayaControlCurveMixin:
    def capture_control_curves(self, controls: tuple[str, ...], *,
                               strict: bool) -> tuple[ControlCurveState, ...]:
        result = []
        resolved = set()
        for requested in controls:
            matches = self._cmds.ls(requested, long=True, type="transform") or []
            if len(matches) != 1:
                if strict:
                    raise ControlCurveValidationError(
                        f"控制器不存在或名称不唯一：{requested}")
                continue
            control = matches[0]
            if control in resolved:
                raise ControlCurveValidationError(f"控制器重复：{control}")
            shapes = self._cmds.listRelatives(
                control, shapes=True, fullPath=True, type="nurbsCurve") or []
            shapes = tuple(shape for shape in shapes
                           if not self._cmds.getAttr(shape + ".intermediateObject"))
            if not shapes:
                if strict:
                    raise ControlCurveValidationError(
                        f"节点没有可编辑的 NURBS 控制曲线：{control}")
                continue
            shape_states = []
            for shape in sorted(shapes):
                values = self._cmds.xform(
                    shape + ".cv[*]", query=True, objectSpace=True,
                    translation=True) or []
                if len(values) % 3:
                    raise ControlCurveValidationError(
                        f"控制曲线 CV 读取不完整：{shape}")
                points = tuple(tuple(float(values[index + axis]) for axis in range(3))
                               for index in range(0, len(values), 3))
                shape_states.append(ControlCurveShapeState(
                    shape, int(self._cmds.getAttr(shape + ".degree")),
                    int(self._cmds.getAttr(shape + ".form")), points))
            result.append(ControlCurveState(
                control,
                tuple(float(value) for value in self._cmds.xform(
                    control, query=True, worldSpace=True, matrix=True)),
                tuple(shape_states)))
            resolved.add(control)
        if not result:
            raise ControlCurveValidationError("没有找到可编辑的 NURBS 控制曲线")
        return tuple(result)

    def set_control_curve_points(self, shape: str,
                                 points: tuple[tuple[float, float, float], ...]) -> None:
        self._require_transaction()
        if not self._cmds.objExists(shape) or self._cmds.nodeType(shape) != "nurbsCurve":
            raise ControlCurveValidationError(f"控制曲线形状已失效：{shape}")
        current = self._cmds.xform(
            shape + ".cv[*]", query=True, objectSpace=True, translation=True
        ) or []
        if len(current) % 3:
            raise ControlCurveValidationError(f"控制曲线 CV 读取不完整：{shape}")
        count = len(current) // 3
        if count != len(points):
            raise ControlCurveValidationError(f"控制曲线 CV 数量已变化：{shape}")
        for index, point in enumerate(points):
            self._cmds.xform(f"{shape}.cv[{index}]", objectSpace=True,
                             translation=point)
        self._transaction_changed = True
