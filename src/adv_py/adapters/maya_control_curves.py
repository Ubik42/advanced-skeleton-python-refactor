"""Maya materialization for post-build NURBS controller curve edits."""
from __future__ import annotations

from adv_py.core.control_curves import (
    ControlCurveAutoScaleMetric, ControlCurveColorState,
    ControlCurveShapeColorState, ControlCurveShapeState, ControlCurveState,
    ControlCurveValidationError,
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

    def measure_control_curve_auto_scale(
        self, controls: tuple[str, ...], mesh: str,
        semantic_keys: tuple[tuple[str, tuple[str, ...]], ...], *, strict: bool,
    ) -> tuple[ControlCurveAutoScaleMetric, ...]:
        from maya.api import OpenMaya as om

        matches = self._cmds.ls(mesh, long=True) or []
        mesh_shapes = []
        for match in matches:
            node_type = self._cmds.nodeType(match)
            if node_type == "mesh":
                mesh_shapes.append(match)
            elif node_type == "transform":
                mesh_shapes.extend(self._cmds.listRelatives(
                    match, shapes=True, fullPath=True, type="mesh") or [])
        mesh_shapes = tuple(dict.fromkeys(
            shape for shape in mesh_shapes
            if not self._cmds.getAttr(shape + ".intermediateObject")))
        if len(mesh_shapes) != 1:
            raise ControlCurveValidationError("Skin 必须明确解析为一个可用网格")
        mesh_shape = mesh_shapes[0]
        mesh_transform = (self._cmds.listRelatives(
            mesh_shape, parent=True, fullPath=True) or [mesh_shape])[0]
        bounds = self._cmds.exactWorldBoundingBox(mesh_transform)
        extent = tuple(float(bounds[index + 3] - bounds[index])
                       for index in range(3))
        selection = om.MSelectionList()
        selection.add(mesh_shape)
        mesh_fn = om.MFnMesh(selection.getDagPath(0))
        states = self.capture_control_curves(controls, strict=strict)
        semantic_map = dict(semantic_keys)
        result = []
        for state in states:
            pivot_values = self._cmds.xform(
                state.control, query=True, worldSpace=True, rotatePivot=True)
            pivot = om.MPoint(*pivot_values)
            closest, _ = mesh_fn.getClosestPoint(pivot, om.MSpace.kWorld)
            distance = (closest - pivot).length()
            radius = 0.0
            for shape in state.shapes:
                values = self._cmds.xform(
                    shape.path + ".cv[*]", query=True, worldSpace=True,
                    translation=True) or []
                for index in range(0, len(values), 3):
                    radius = max(radius, (om.MPoint(
                        values[index], values[index + 1], values[index + 2]
                    ) - pivot).length())
            keys = semantic_map.get(state.control, ())
            if not keys:
                requested = next((name for name in controls
                                  if (self._cmds.ls(name, long=True,
                                                   type="transform") or [None])[0]
                                  == state.control), None)
                keys = semantic_map.get(requested, ())
            result.append(ControlCurveAutoScaleMetric(
                state, tuple(keys), radius, float(distance), extent,
                self._cmds.upAxis(query=True, axis=True).lower()))
        return tuple(result)
