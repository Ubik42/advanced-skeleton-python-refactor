"""Maya materialization for post-build NURBS controller curve edits."""
from __future__ import annotations

from adv_py.core.control_curves import (
    ControlCurveColorState, ControlCurveShapeColorState, ControlCurveShapeState,
    ControlCurveState, ControlCurveValidationError,
)


class MayaControlCurveMixin:
    def _control_curve_shapes(self, requested: str, *, strict: bool):
        matches = self._cmds.ls(requested, long=True, type="transform") or []
        if len(matches) != 1:
            if strict:
                raise ControlCurveValidationError(
                    f"控制器不存在或名称不唯一：{requested}")
            return None, ()
        control = matches[0]
        shapes = self._cmds.listRelatives(
            control, shapes=True, fullPath=True, type="nurbsCurve") or []
        shapes = tuple(sorted(shape for shape in shapes
                              if not self._cmds.getAttr(
                                  shape + ".intermediateObject")))
        if not shapes and strict:
            raise ControlCurveValidationError(
                f"节点没有可编辑的 NURBS 控制曲线：{control}")
        return control, shapes

    def capture_control_curves(self, controls: tuple[str, ...], *,
                               strict: bool) -> tuple[ControlCurveState, ...]:
        result = []
        resolved = set()
        for requested in controls:
            control, shapes = self._control_curve_shapes(requested, strict=strict)
            if not control or not shapes:
                continue
            if control in resolved:
                raise ControlCurveValidationError(f"控制器重复：{control}")
            shape_states = []
            for shape in shapes:
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

    def capture_control_curve_colors(
        self, controls: tuple[str, ...],
        semantic_keys: tuple[tuple[str, tuple[str, ...]], ...], *, strict: bool,
    ) -> tuple[ControlCurveColorState, ...]:
        semantic_map = dict(semantic_keys)
        result = []
        resolved = set()
        for requested in controls:
            control, shapes = self._control_curve_shapes(requested, strict=strict)
            if not control or not shapes:
                continue
            if control in resolved:
                raise ControlCurveValidationError(f"控制器重复：{control}")
            keys = semantic_map.get(requested, semantic_map.get(control, ()))
            states = []
            for shape in shapes:
                color = tuple(float(value) for value in
                              self._cmds.getAttr(shape + ".overrideColorRGB")[0])
                states.append(ControlCurveShapeColorState(
                    shape,
                    bool(self._cmds.getAttr(shape + ".overrideEnabled")),
                    bool(self._cmds.getAttr(shape + ".overrideRGBColors")),
                    color,
                ))
            result.append(ControlCurveColorState(control, tuple(keys),
                                                 tuple(states)))
            resolved.add(control)
        if not result:
            raise ControlCurveValidationError("没有找到可着色的 NURBS 控制曲线")
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

    def set_control_curve_color(self, shape: str,
                                color: tuple[float, float, float]) -> None:
        self._require_transaction()
        if not self._cmds.objExists(shape) or self._cmds.nodeType(shape) != "nurbsCurve":
            raise ControlCurveValidationError(f"控制曲线形状已失效：{shape}")
        self._cmds.setAttr(shape + ".overrideEnabled", True)
        self._cmds.setAttr(shape + ".overrideRGBColors", True)
        self._cmds.setAttr(shape + ".overrideColorRGB", *color, type="double3")
        self._transaction_changed = True
