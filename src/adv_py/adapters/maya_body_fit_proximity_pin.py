"""Use Maya's native ProximityPin generator, then wire its output in Python."""
from __future__ import annotations

from math import isfinite

from adv_py.core.body_fit_proximity_pin import (
    BodyFitProximityPinSpec, BodyFitProximityPinState,
)


def _matrix(values) -> tuple[float, ...]:
    if len(values) == 1 and isinstance(values[0], (tuple, list)):
        values = values[0]
    return tuple(float(value) for value in values)


class MayaBodyFitProximityPinMixin:
    def preflight_body_fit_proximity_pin(
        self, spec: BodyFitProximityPinSpec,
    ) -> BodyFitProximityPinState:
        c = self._cmds
        raw = getattr(c, "raw", c)
        if int(raw.about(apiVersion=True)) < 20200000:
            raise ValueError("Proximity Pin 需要 Maya 2020 或更新版本")
        for path in (spec.source_body, spec.fk_control,
                     spec.fk_offset, spec.receiver):
            if (c.ls(path, long=True) or []) != [path]:
                raise ValueError("Proximity Pin 来源控制层缺失：" + path)
        if (c.listRelatives(spec.receiver, parent=True,
                            fullPath=True) or []) != [spec.fk_offset]:
            raise ValueError("Proximity Pin 接收层不在 FK Offset 下")
        if any(self.find_name_collisions(name)
               for name in spec.node_names + (spec.input_transform,)):
            raise ValueError("Proximity Pin 节点名称冲突")
        if c.attributeQuery("pin", node=spec.fk_control, exists=True):
            raise ValueError("Proximity Pin FK 控制器 pin 通道已存在")
        mesh_name = spec.mesh
        if spec.side == "L" and mesh_name.endswith("_R"):
            left_name = mesh_name[:-2] + "_L"
            lookup = left_name if ":" in left_name else ":" + left_name
            if raw.objExists(lookup):
                mesh_name = left_name
        lookup = mesh_name if ":" in mesh_name else ":" + mesh_name
        matches = raw.ls(lookup, long=True) or []
        if len(matches) != 1:
            raise ValueError("Proximity Pin 网格目标不存在或不唯一："
                             + mesh_name)
        mesh = matches[0]
        if raw.nodeType(mesh) == "mesh":
            shapes = [mesh]
            parents = raw.listRelatives(mesh, parent=True, fullPath=True) or []
            if len(parents) != 1:
                raise ValueError("Proximity Pin 网格形状缺少唯一父级")
            mesh = parents[0]
        elif raw.nodeType(mesh) == "transform":
            shapes = raw.listRelatives(mesh, shapes=True,
                                       noIntermediate=True,
                                       fullPath=True, type="mesh") or []
            if len(shapes) != 1:
                raise ValueError("Proximity Pin 目标需要唯一可见网格形状")
        else:
            raise ValueError("Proximity Pin 目标不是 polygon 网格")
        offset_scene = self.scene_address(spec.fk_offset)
        if mesh == offset_scene or mesh.startswith(offset_scene + "|"):
            raise ValueError("Proximity Pin 网格不能位于自身 FK Offset 下")
        source_scene = self.scene_address(spec.source_body)
        for history in raw.listHistory(shapes[0], pruneDagObjects=True) or []:
            if raw.nodeType(history) != "skinCluster":
                continue
            influences = raw.skinCluster(history, query=True,
                                         influence=True) or []
            for influence in influences:
                if any(path == source_scene
                       or path.startswith(source_scene + "|")
                       for path in (raw.ls(influence, long=True) or [])):
                    raise ValueError(
                        "Proximity Pin 网格蒙皮依赖自身 FK 驱动关节：" + mesh)
        plug = spec.receiver + ".offsetParentMatrix"
        if c.getAttr(plug, lock=True):
            raise ValueError("Proximity Pin 接收层矩阵已锁定")
        upstream = c.connectionInfo(plug, sourceFromDestination=True) or None
        if upstream is None and not c.getAttr(plug, settable=True):
            raise ValueError("Proximity Pin 接收层矩阵不可写")
        state = BodyFitProximityPinState(
            mesh,
            _matrix(c.xform(spec.fk_offset, query=True,
                            worldSpace=True, matrix=True)),
            _matrix(c.xform(spec.receiver, query=True,
                            worldSpace=True, matrix=True)),
            upstream, _matrix(c.getAttr(plug)),
            bool(c.getAttr(spec.receiver + ".inheritsTransform")))
        if any(len(matrix) != 16 or not all(isfinite(v) for v in matrix)
               for matrix in (state.offset_world, state.receiver_world,
                              state.receiver_opm_value)):
            raise ValueError("Proximity Pin 绑定矩阵无效")
        return state

    def _generate_body_proximity_pin(
        self, spec: BodyFitProximityPinSpec,
        state: BodyFitProximityPinState,
    ) -> str:
        from maya import mel  # type: ignore[import-not-found]

        c = self._cmds
        raw = getattr(c, "raw", c)
        input_node = c.createNode("transform", name=spec.input_transform)
        input_scene = self.scene_address(input_node)
        raw.xform(input_scene, worldSpace=True, matrix=state.offset_world)
        before = set(raw.ls(type="proximityPin") or [])
        before_transforms = set(raw.ls(type="transform", long=True) or [])
        previous_selection = raw.ls(selection=True, long=True) or []
        previous_namespace = raw.namespaceInfo(
            currentNamespace=True, absoluteName=True)
        try:
            target_namespace = ":" + self.namespace if self.namespace else ":"
            raw.namespace(setNamespace=target_namespace)
            raw.select(state.mesh_transform, input_scene, replace=True)
            mel.eval("ProximityPin")
        finally:
            raw.namespace(setNamespace=previous_namespace)
            if previous_selection:
                raw.select(previous_selection, replace=True)
            else:
                raw.select(clear=True)
        created = set(raw.ls(type="proximityPin") or []) - before
        if len(created) != 1:
            raise RuntimeError("Maya ProximityPin 未生成唯一节点")
        target_name = self.scene_address(spec.pin_node)
        pin = raw.rename(created.pop(), ":" + target_name.lstrip(":"))
        input_plug = pin + ".inputMatrix[0]"
        input_value = _matrix(raw.getAttr(input_plug))
        source = raw.connectionInfo(input_plug,
                                    sourceFromDestination=True) or None
        source_node = source.split(".", 1)[0] if source else None
        if source:
            raw.disconnectAttr(source, input_plug)
        raw.setAttr(input_plug, *input_value, type="matrix")
        output_plug = pin + ".outputMatrix[0]"
        destinations = raw.listConnections(
            output_plug, source=False, destination=True,
            plugs=True) or []
        if spec.source_native:
            input_outputs=[destination for destination in destinations
                if (raw.ls(destination.split('.',1)[0],long=True) or []) == [input_scene]]
            if not input_outputs:
                raw.connectAttr(output_plug,input_scene+'.offsetParentMatrix',force=True)
                raw.xform(input_scene,objectSpace=True,translation=(0,0,0),rotation=(0,0,0))
                destinations.append(input_scene+'.offsetParentMatrix')
        for destination in destinations:
            if raw.isConnected(output_plug,destination):
                raw.disconnectAttr(output_plug, destination)
        generated_transforms = set(
            raw.ls(type="transform", long=True) or []) - before_transforms
        if source_node:
            paths = raw.ls(source_node, long=True) or []
            if (len(paths) == 1 and paths[0] in generated_transforms
                    and paths[0] != input_scene):
                raw.delete(paths[0])
        for destination in destinations:
            node = destination.split(".", 1)[0]
            paths = raw.ls(node, long=True) or []
            if (len(paths) == 1 and paths[0] in generated_transforms
                    and paths[0] != input_scene):
                raw.delete(paths[0])
        if not spec.source_native:
            raw.delete(input_scene)
        for attr in ("coordMode", "normalAxis", "relativeSpaceMode"):
            raw.setAttr(pin + "." + attr, 0)
        if spec.source_native:
            c.parent(spec.input_transform,spec.fk_offset,relative=True)
        return pin

    def create_body_fit_proximity_pin(
        self, spec: BodyFitProximityPinSpec,
        state: BodyFitProximityPinState,
    ) -> None:
        self._require_transaction()
        if spec.source_native:
            from .maya_source_fit_proximity_pin import create
            return create(self, spec, state)
        from maya.api import OpenMaya as om

        c = self._cmds
        plug = spec.receiver + ".offsetParentMatrix"
        if (c.connectionInfo(plug, sourceFromDestination=True) or None
                ) != state.receiver_opm_source:
            raise ValueError("Proximity Pin 接收层矩阵来源已变化")
        self._transaction_changed = True
        self._generate_body_proximity_pin(spec, state)
        pin_bind = om.MMatrix(_matrix(c.getAttr(
            spec.pin_node + ".outputMatrix[0]")))
        correction = tuple(om.MMatrix(state.offset_world)
                           * pin_bind.inverse())
        corrected = c.createNode("multMatrix", name=spec.corrected_matrix)
        c.setAttr(corrected + ".matrixIn[0]", *correction,
                  type="matrix")
        c.connectAttr(spec.pin_node + ".outputMatrix[0]",
                      corrected + ".matrixIn[1]")
        blend = c.createNode("blendMatrix", name=spec.blend_matrix)
        c.connectAttr(spec.fk_offset + ".worldMatrix[0]",
                      blend + ".inputMatrix")
        c.connectAttr(corrected + ".matrixSum",
                      blend + ".target[0].targetMatrix")
        c.setAttr(blend + ".target[0].useScale", False)
        c.setAttr(blend + ".target[0].useShear", False)
        c.addAttr(spec.fk_control, longName="pin",
                  attributeType="double", minValue=0, maxValue=10,
                  defaultValue=10, keyable=True)
        weight = c.createNode("multDoubleLinear", name=spec.weight_node)
        c.setAttr(weight + ".input2", 0.1)
        c.connectAttr(spec.fk_control + ".pin", weight + ".input1")
        c.connectAttr(weight + ".output", blend + ".target[0].weight")
        delta = c.createNode("multMatrix", name=spec.delta_matrix)
        c.connectAttr(blend + ".outputMatrix", delta + ".matrixIn[0]")
        c.connectAttr(spec.fk_offset + ".worldInverseMatrix[0]",
                      delta + ".matrixIn[1]")
        receiver = c.createNode("multMatrix", name=spec.receiver_matrix)
        if state.receiver_opm_source is None:
            c.setAttr(receiver + ".matrixIn[0]",
                      *state.receiver_opm_value, type="matrix")
        else:
            c.connectAttr(state.receiver_opm_source,
                          receiver + ".matrixIn[0]")
            c.disconnectAttr(state.receiver_opm_source, plug)
        c.connectAttr(delta + ".matrixSum", receiver + ".matrixIn[1]")
        c.connectAttr(receiver + ".matrixSum", plug)
        actual = _matrix(c.xform(spec.receiver, query=True,
                                 worldSpace=True, matrix=True))
        if any(abs(a - b) > 1e-4 for a, b in zip(actual, state.receiver_world)):
            raise RuntimeError("Proximity Pin 改变了 FK 绑定姿态")

    def capture_body_fit_proximity_pin(
        self, spec: BodyFitProximityPinSpec,
        state: BodyFitProximityPinState,
    ) -> bool:
        if spec.source_native:
            from .maya_source_fit_proximity_pin import capture
            return capture(self, spec, state)
        from maya.api import OpenMaya as om

        c = self._cmds
        expected = (
            (spec.pin_node, "proximityPin"),
            (spec.corrected_matrix, "multMatrix"),
            (spec.blend_matrix, "blendMatrix"),
            (spec.weight_node, "multDoubleLinear"),
            (spec.delta_matrix, "multMatrix"),
            (spec.receiver_matrix, "multMatrix"))
        if any(not c.objExists(name) or c.nodeType(name) != kind
               for name, kind in expected):
            return False
        if c.objExists(spec.input_transform):
            return False
        links = [
            (spec.pin_node + ".outputMatrix[0]",
             spec.corrected_matrix + ".matrixIn[1]"),
            (spec.corrected_matrix + ".matrixSum",
             spec.blend_matrix + ".target[0].targetMatrix"),
            (spec.fk_offset + ".worldMatrix[0]",
             spec.blend_matrix + ".inputMatrix"),
            (spec.fk_control + ".pin",
             spec.weight_node + ".input1"),
            (spec.weight_node + ".output",
             spec.blend_matrix + ".target[0].weight"),
            (spec.blend_matrix + ".outputMatrix",
             spec.delta_matrix + ".matrixIn[0]"),
            (spec.fk_offset + ".worldInverseMatrix[0]",
             spec.delta_matrix + ".matrixIn[1]"),
            (spec.delta_matrix + ".matrixSum",
             spec.receiver_matrix + ".matrixIn[1]"),
            (spec.receiver_matrix + ".matrixSum",
             spec.receiver + ".offsetParentMatrix")]
        if state.receiver_opm_source:
            links.append((state.receiver_opm_source,
                          spec.receiver_matrix + ".matrixIn[0]"))
        correction = _matrix(c.getAttr(
            spec.corrected_matrix + ".matrixIn[0]"))
        pin_output = _matrix(c.getAttr(
            spec.pin_node + ".outputMatrix[0]"))
        if (len(correction) != 16 or len(pin_output) != 16
                or any(abs(a - b) > 1e-5 for a, b in zip(
                    tuple(om.MMatrix(correction) * om.MMatrix(pin_output)),
                    state.offset_world))
                or abs(float(c.getAttr(spec.weight_node + ".input2"))
                       - 0.1) > 1e-8
                or any(bool(c.getAttr(spec.blend_matrix
                                      + ".target[0]." + attr))
                       for attr in ("useScale", "useShear"))):
            return False
        return (all(c.isConnected(src, dst, ignoreUnitConversion=True)
                    for src, dst in links)
                and all(int(c.getAttr(spec.pin_node + "." + attr)) == 0
                        for attr in ("coordMode", "normalAxis",
                                     "relativeSpaceMode"))
                and abs(float(c.getAttr(spec.fk_control + ".pin")) - 10.0)
                < 1e-8
                and all(abs(a - b) <= 1e-4 for a, b in zip(
                    _matrix(c.xform(spec.receiver, query=True,
                                    worldSpace=True, matrix=True)),
                    state.receiver_world)))
