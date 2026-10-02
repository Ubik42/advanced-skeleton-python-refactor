"""Maya materialization for post-build NURBS controller curve edits."""
from __future__ import annotations


from adv_py.core.control_curves import (
    ControlCurveAutoScaleMetric, ControlCurveColorState,
    ControlCurveShapeColorState, ControlCurveShapeState, ControlCurveState,
    ControlCurveValidationError,
)
from adv_py.core.control_curve_variants import ControlCurveVariantState
from adv_py.core.control_orientation import (
    ControlAxis, ControlOrientationState, ControlOrientationValidationError,
)


_CONTROL_AXES = tuple(ControlAxis)


class MayaControlCurveMixin:
    def confirm_original_control_build_pose(self):
        from .maya_original_build_pose_confirm import confirm_original_build_pose
        return confirm_original_build_pose(self)

    def set_original_control_orientation(self, controls, options):
        from .maya_original_control_orient import set_original_control_orient
        return set_original_control_orient(self, controls, options)

    def detach_original_control_orientation(self):
        from .maya_original_control_orient_detach import detach_original_controls
        return detach_original_controls(self)

    def attach_original_control_orientation(self, *, mirror=True):
        from .maya_original_control_orient_detach import attach_original_controls
        return attach_original_controls(self, mirror=mirror)

    def select_original_control_curves(self,controller_type,side):
        from adv_py.core.control_curve_selection import select_curve_members
        c=self._cmds
        members=c.sets('ControlSet',query=True) or [] if c.objExists('ControlSet') else []
        face=()
        if controller_type.startswith('Face:') and c.objExists('ctrlBox'):
            face=c.listConnections('ctrlBox.'+controller_type.split(':',1)[1]+'CtrlVis',
                source=False,destination=True) or []
        targets=select_curve_members(members,controller_type,side,face_connections=face)
        c.select(clear=True)
        if targets:c.select(targets,replace=True)
        return targets

    def capture_control_curve_scale_pivots(self, states):
        from maya import mel
        from maya.api import OpenMaya as om
        c=self._cmds;raw=getattr(c,'raw',c)
        selection=raw.ls(selection=True,long=True) or []
        move=mel.eval('global string $gMove; $gMove = $gMove;')
        if not move:
            raise ControlCurveValidationError('请在 Maya 图形会话中使用控制曲线缩放')
        pivots=[]
        try:
            for state in states:
                inverse=om.MMatrix(state.world_matrix).inverse()
                for shape in state.shapes:
                    raw.select(self.scene_address(shape.path)+'.cv[0:99999]',replace=True)
                    raw.refresh()
                    raw.setToolTo(move)
                    position=raw.manipMoveContext('Move',query=True,position=True)
                    local=om.MPoint(*position)*inverse
                    pivots.append((shape.path,(local.x,local.y,local.z)))
        finally:
            raw.select(selection,replace=True) if selection else raw.select(clear=True)
        return tuple(pivots)

    def set_original_control_curve_palette(self, controls, palette):
        from .maya_control_curve_style import set_palette
        return set_palette(self,controls,palette)

    def set_original_control_curve_width(self, controls, width):
        from .maya_control_curve_style import set_width
        return set_width(self,controls,width)

    def snap_rotate_control_curves(self, controls, axis):
        from .maya_control_curve_style import snap_rotate
        return snap_rotate(self,controls,axis)

    def project_control_curves(self, controls, mesh, *, strict=True):
        from .maya_control_curve_projection import project_control_curves
        return project_control_curves(self, controls, mesh, strict=strict)

    def capture_control_curve_variants(self, controls, variant):
        if variant not in ("Sub", "Extra"):
            raise ControlCurveValidationError("目标控制层只能是 Sub 或 Extra")
        c = self._cmds
        rows = []
        for requested in controls:
            control, shapes = self._control_curve_shapes(
                requested, strict=False)
            if not control or not shapes:
                continue
            leaf = control.rsplit("|", 1)[-1]
            if "Sub" in leaf or "Extra" in leaf:
                continue
            if variant == "Extra":
                candidates = c.listRelatives(
                    control, parent=True, fullPath=True,
                    type="transform") or []
            else:
                candidates = c.listRelatives(
                    control, children=True, fullPath=True,
                    type="transform") or []
            candidates = [path for path in candidates
                          if variant in path.rsplit("|", 1)[-1]]
            if not candidates:
                continue
            if len(candidates) != 1 or len(shapes) != 1:
                raise ControlCurveValidationError(
                    "控制器曲线或目标层不唯一：" + control)
            target, target_shapes = self._control_curve_shapes(
                candidates[0], strict=False)
            if not target_shapes:
                continue
            if len(target_shapes) != 1:
                raise ControlCurveValidationError(
                    "目标层曲线不唯一：" + target)

            def points(shape):
                values = c.xform(shape + ".cv[*]", query=True,
                                 worldSpace=True, translation=True) or []
                if len(values) % 3:
                    raise ControlCurveValidationError(
                        "控制曲线 CV 读取不完整：" + shape)
                return tuple(tuple(float(values[index + axis])
                                   for axis in range(3))
                             for index in range(0, len(values), 3))

            source_shape, target_shape = shapes[0], target_shapes[0]
            rows.append(ControlCurveVariantState(
                control, target, source_shape, target_shape,
                int(c.getAttr(source_shape + ".degree")),
                int(c.getAttr(target_shape + ".degree")),
                int(c.getAttr(source_shape + ".form")),
                int(c.getAttr(target_shape + ".form")),
                tuple(float(value) for value in c.xform(
                    control, query=True, worldSpace=True,
                    translation=True)),
                points(source_shape), points(target_shape),
            ))
        return tuple(rows)

    def set_control_curve_world_points(self, shape, points):
        self._require_transaction()
        c = self._cmds
        if not c.objExists(shape) or c.nodeType(shape) != "nurbsCurve":
            raise ControlCurveValidationError(
                "目标控制曲线已失效：" + shape)
        current = c.xform(shape + ".cv[*]", query=True,
                          worldSpace=True, translation=True) or []
        if len(current) != len(points) * 3:
            raise ControlCurveValidationError(
                "目标曲线 CV 数量在执行前变化：" + shape)
        self._transaction_changed = True
        for index, point in enumerate(points):
            c.xform(f"{shape}.cv[{index}]", worldSpace=True,
                    translation=point)

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
                bool(self._cmds.getAttr(control + ".mirror"))
                if self._cmds.attributeQuery(
                    "mirror", node=control, exists=True) else False,
                bool(self._cmds.getAttr(control + ".mirroredBehaviour"))
                if self._cmds.attributeQuery(
                    "mirroredBehaviour", node=control,
                    exists=True) else False,
            ))
            resolved.add(control)
        return tuple(result)

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
