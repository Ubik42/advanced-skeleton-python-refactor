"""Maya materialization for post-build NURBS controller curve edits."""
from __future__ import annotations

import json

from adv_py.core.control_curves import (
    ControlCurveAutoScaleMetric, ControlCurveColorState,
    ControlCurveShapeColorState, ControlCurveShapeState, ControlCurveState,
    ControlCurveValidationError,
)
from adv_py.core.control_orientation import (
    ControlAxis, ControlOrientationState, ControlOrientationValidationError,
    CustomOrientationPreview,
)


_CONTROL_AXES = tuple(ControlAxis)
_CUSTOM_SESSION = "AdvPy_ControlOrientCustomSession"
_CUSTOM_GROUP = "AdvPy_ControlOrientDetached"


class MayaControlCurveMixin:
    def detach_custom_control_orientations(self, states):
        self._require_transaction()
        c = self._cmds
        if c.objExists(_CUSTOM_SESSION) or c.objExists(_CUSTOM_GROUP):
            raise ControlOrientationValidationError(
                "当前角色已有手工方向编辑会话或同名节点")
        if not states or len({state.control for state in states}) != len(states):
            raise ControlOrientationValidationError("手工方向目标为空或重复")
        for state in states:
            control, shapes = self._control_curve_shapes(state.control, strict=True)
            if self.capture_control_orientations((control,))[0] != state:
                raise ControlOrientationValidationError(
                    f"手工方向预检期间控制器已变化：{control}")
            for axis in "XYZ":
                plug = control + ".rotate" + axis
                if (abs(float(c.getAttr(plug))) > 1e-7
                        or c.listConnections(plug, source=True,
                                             destination=False)):
                    raise ControlOrientationValidationError(
                        f"手工方向要求全部控制器处于零旋转构建姿态：{control}")
            for shape in shapes:
                for attribute in ("overrideEnabled", "overrideVisibility"):
                    plug = shape + "." + attribute
                    if (c.getAttr(plug, lock=True)
                            or c.listConnections(plug, source=True,
                                                 destination=False)):
                        raise ControlOrientationValidationError(
                            f"控制曲线显示状态不可写：{plug}")
        self._transaction_changed = True
        session = c.createNode("network", name=_CUSTOM_SESSION, skipSelect=True)
        group = c.createNode("transform", name=_CUSTOM_GROUP, skipSelect=True)
        c.addAttr(session, longName="document", dataType="string")
        c.addAttr(session, longName="members", attributeType="message",
                  multi=True)
        rows = []
        proxies = []
        for index, state in enumerate(states):
            control, shapes = self._control_curve_shapes(state.control, strict=True)
            proxy = c.createNode(
                "transform", name=f"AdvPy_OrientPreview_{index:03d}",
                parent=group, skipSelect=True)
            proxy = c.ls(proxy, long=True, type="transform")[0]
            c.xform(proxy, worldSpace=True, matrix=state.world_matrix)
            c.connectAttr(proxy + ".message", session + f".members[{index}]")
            styles = []
            for shape in shapes:
                styles.append((shape, bool(c.getAttr(shape + ".overrideEnabled")),
                               bool(c.getAttr(shape + ".overrideVisibility"))))
                temporary = c.duplicateCurve(
                    shape, constructionHistory=False, local=True)[0]
                duplicate_shape = (c.listRelatives(
                    temporary, shapes=True, fullPath=True,
                    type="nurbsCurve") or [])[0]
                copy = c.parent(duplicate_shape, proxy, shape=True,
                                relative=True)[0]
                c.delete(temporary)
                c.setAttr(copy + ".overrideEnabled", True)
                c.setAttr(copy + ".overrideVisibility", True)
                c.setAttr(copy + ".overrideRGBColors", True)
                c.setAttr(copy + ".overrideColorRGB", .98, .52, .12,
                          type="double3")
                c.setAttr(shape + ".overrideEnabled", True)
                c.setAttr(shape + ".overrideVisibility", False)
            rows.append({
                "control": control,
                "uuid": c.ls(control, uuid=True)[0],
                "matrix": list(state.world_matrix),
                "styles": styles,
            })
            proxies.append(proxy)
        c.setAttr(session + ".document", json.dumps(
            {"version": 1, "rows": rows}, separators=(",", ":")),
                  type="string")
        c.select(proxies, replace=True)
        return tuple(proxies)

    def _custom_orientation_session(self):
        c = self._cmds
        if not c.objExists(_CUSTOM_SESSION) or not c.objExists(_CUSTOM_GROUP):
            raise ControlOrientationValidationError("当前角色没有手工方向编辑会话")
        if c.nodeType(_CUSTOM_SESSION) != "network":
            raise ControlOrientationValidationError("手工方向会话节点类型无效")
        try:
            document = json.loads(c.getAttr(_CUSTOM_SESSION + ".document"))
            rows = document["rows"]
            if (document["version"] != 1 or not isinstance(rows, list)
                    or not rows):
                raise ValueError("invalid document")
        except (TypeError, ValueError, KeyError) as exc:
            raise ControlOrientationValidationError(
                "手工方向会话文档无效") from exc
        proxies = []
        for index, row in enumerate(rows):
            connected = c.listConnections(
                _CUSTOM_SESSION + f".members[{index}]", source=True,
                destination=False, type="transform") or []
            if len(connected) != 1:
                raise ControlOrientationValidationError(
                    "手工方向预览节点缺失或连接歧义")
            proxy = c.ls(connected[0], long=True, type="transform")[0]
            if (c.listRelatives(proxy, parent=True, fullPath=True) or []) != [
                    c.ls(_CUSTOM_GROUP, long=True, type="transform")[0]]:
                raise ControlOrientationValidationError(
                    "手工方向预览节点已移出编辑组")
            control = row["control"]
            if (not c.objExists(control)
                    or c.ls(control, uuid=True) != [row["uuid"]]):
                raise ControlOrientationValidationError(
                    f"手工方向原控制器身份已变化：{control}")
            proxies.append(proxy)
        return rows, tuple(proxies)

    def capture_custom_control_orientation_previews(self):
        rows, proxies = self._custom_orientation_session()
        c = self._cmds
        return tuple(CustomOrientationPreview(
            row["control"], tuple(float(v) for v in row["matrix"]),
            tuple(float(v) for v in c.xform(
                proxy, query=True, worldSpace=True, matrix=True)))
            for row, proxy in zip(rows, proxies))

    def finish_custom_control_orientations(self):
        self._require_transaction()
        rows, _ = self._custom_orientation_session()
        c = self._cmds
        self._transaction_changed = True
        for row in rows:
            for shape, enabled, visible in row["styles"]:
                if not c.objExists(shape):
                    raise ControlOrientationValidationError(
                        f"手工方向原曲线已消失：{shape}")
                c.setAttr(shape + ".overrideEnabled", enabled)
                c.setAttr(shape + ".overrideVisibility", visible)
        c.delete(_CUSTOM_SESSION)
        if c.objExists(_CUSTOM_GROUP):
            c.delete(_CUSTOM_GROUP)

    def capture_control_orientations(
        self, controls: tuple[str, ...]
    ) -> tuple[ControlOrientationState, ...]:
        result = []
        resolved = set()
        for requested in controls:
            control, shapes = self._control_curve_shapes(requested, strict=True)
            if control in resolved:
                raise ControlOrientationValidationError(
                    f"控制器重复：{control}")
            def axis(attribute, default):
                if not self._cmds.attributeQuery(
                        attribute, node=control, exists=True):
                    return default
                index = int(self._cmds.getAttr(control + "." + attribute))
                if not 0 <= index < len(_CONTROL_AXES):
                    raise ControlOrientationValidationError(
                        f"控制器轴枚举无效：{control}.{attribute}")
                return _CONTROL_AXES[index]
            result.append(ControlOrientationState(
                control,
                tuple(float(value) for value in self._cmds.xform(
                    control, query=True, worldSpace=True, matrix=True)),
                axis("primaryAxis", ControlAxis.X),
                axis("secondaryAxis", ControlAxis.Y),
                bool(self._cmds.getAttr(control + ".curveUnafeccted"))
                if self._cmds.attributeQuery(
                    "curveUnafeccted", node=control, exists=True) else False,
            ))
            resolved.add(control)
        return tuple(result)

    def apply_control_orientation(self, state: ControlOrientationState) -> None:
        from math import degrees
        from maya.api import OpenMaya as om

        self._require_transaction()
        control, _ = self._control_curve_shapes(state.control, strict=True)
        original_selection = self._cmds.ls(selection=True, long=True) or []
        for axis in "XYZ":
            plug = control + ".rotate" + axis
            if self._cmds.listConnections(plug, source=True,
                                          destination=False):
                raise ControlOrientationValidationError(
                    f"控制器必须在无旋转输入的构建姿态设置方向：{control}")
            if abs(float(self._cmds.getAttr(plug))) > 1e-7:
                raise ControlOrientationValidationError(
                    f"控制器必须在零旋转的构建姿态设置方向：{control}")
        children = self._cmds.listRelatives(
            control, children=True, fullPath=True, type="transform") or []
        child_world = tuple((child, tuple(self._cmds.xform(
            child, query=True, worldSpace=True, matrix=True)))
                            for child in children)
        parents = self._cmds.listRelatives(
            control, parent=True, fullPath=True, type="transform") or []
        parent_world = (om.MMatrix(self._cmds.xform(
            parents[0], query=True, worldSpace=True, matrix=True))
                        if parents else om.MMatrix())
        local_target = om.MMatrix(state.world_matrix) * parent_world.inverse()
        orientation = om.MTransformationMatrix(
            local_target).rotation(asQuaternion=True)
        euler = orientation.asEulerRotation()
        self._cmds.setAttr(control + ".rotateAxis",
                           degrees(euler.x), degrees(euler.y),
                           degrees(euler.z), type="double3")
        for child, matrix in child_world:
            self._cmds.xform(child, worldSpace=True, matrix=matrix)
        enum_names = ":".join(axis.value for axis in _CONTROL_AXES)
        for attribute, value in (("primaryAxis", state.primary_axis),
                                 ("secondaryAxis", state.secondary_axis)):
            if not self._cmds.attributeQuery(attribute, node=control,
                                             exists=True):
                self._cmds.addAttr(control, longName=attribute,
                                   attributeType="enum", enumName=enum_names)
            self._cmds.setAttr(control + "." + attribute,
                               _CONTROL_AXES.index(value))
        if not self._cmds.attributeQuery(
                "curveUnafeccted", node=control, exists=True):
            self._cmds.addAttr(control, longName="curveUnafeccted",
                               attributeType="bool")
        self._cmds.setAttr(control + ".curveUnafeccted",
                           state.curve_unaffected)
        if original_selection:
            self._cmds.select(original_selection, replace=True)
        else:
            self._cmds.select(clear=True)
        self._transaction_changed = True

    def capture_control_curve_world_points(self, controls):
        result = []
        for control in controls:
            _, shapes = self._control_curve_shapes(control, strict=True)
            for shape in shapes:
                values = self._cmds.xform(
                    shape + ".cv[*]", query=True, worldSpace=True,
                    translation=True) or []
                if len(values) % 3:
                    raise ControlOrientationValidationError(
                        f"控制曲线 CV 读取不完整：{shape}")
                result.append((shape, tuple(
                    (float(values[index]), float(values[index + 1]),
                     float(values[index + 2]))
                    for index in range(0, len(values), 3))))
        return tuple(result)

    def restore_control_curve_world_points(self, shapes):
        self._require_transaction()
        for shape, points in shapes:
            if not self._cmds.objExists(shape):
                raise ControlOrientationValidationError(
                    f"控制曲线形状已失效：{shape}")
            values = self._cmds.xform(
                shape + ".cv[*]", query=True, objectSpace=True,
                translation=True) or []
            if len(values) != len(points) * 3:
                raise ControlOrientationValidationError(
                    f"控制曲线 CV 数量已变化：{shape}")
            for index, point in enumerate(points):
                self._cmds.xform(f"{shape}.cv[{index}]", worldSpace=True,
                                 translation=point)
        self._transaction_changed = True

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

    def replace_control_curve_shapes(self, source: str, target: str) -> None:
        self._require_transaction()
        source_control, source_shapes = self._control_curve_shapes(
            source, strict=True)
        target_control, target_shapes = self._control_curve_shapes(
            target, strict=True)
        if source_control == target_control:
            raise ControlCurveValidationError("自定义曲线不能同时作为替换目标")
        original_selection = self._cmds.ls(selection=True, long=True) or []
        style_shape = target_shapes[0]
        style = {
            "overrideEnabled": bool(self._cmds.getAttr(
                style_shape + ".overrideEnabled")),
            "overrideRGBColors": bool(self._cmds.getAttr(
                style_shape + ".overrideRGBColors")),
            "overrideColor": int(self._cmds.getAttr(
                style_shape + ".overrideColor")),
            "overrideColorRGB": tuple(float(value) for value in
                self._cmds.getAttr(style_shape + ".overrideColorRGB")[0]),
            "lineWidth": float(self._cmds.getAttr(style_shape + ".lineWidth")),
        }
        self._cmds.delete(list(target_shapes))
        base = target_control.rsplit("|", 1)[-1].split(":")[-1] + "Shape"
        for index, source_shape in enumerate(source_shapes):
            temporary = self._cmds.duplicateCurve(
                source_shape, constructionHistory=False, local=True)[0]
            duplicate_shape = (self._cmds.listRelatives(
                temporary, shapes=True, fullPath=True, type="nurbsCurve") or [])[0]
            parented = self._cmds.parent(
                duplicate_shape, target_control, shape=True, relative=True)[0]
            if self._cmds.objExists(temporary):
                self._cmds.delete(temporary)
            path = self._cmds.rename(parented, base if index == 0
                                     else f"{base}{index + 1}")
            self._cmds.setAttr(path + ".overrideEnabled",
                               style["overrideEnabled"])
            self._cmds.setAttr(path + ".overrideRGBColors",
                               style["overrideRGBColors"])
            self._cmds.setAttr(path + ".overrideColor", style["overrideColor"])
            self._cmds.setAttr(path + ".overrideColorRGB",
                               *style["overrideColorRGB"], type="double3")
            self._cmds.setAttr(path + ".lineWidth", style["lineWidth"])
        if original_selection:
            self._cmds.select(original_selection, replace=True)
        else:
            self._cmds.select(clear=True)
        self._transaction_changed = True
