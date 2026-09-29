"""Build ADV geoAttach as a surface-driven FK Offset matrix blend."""
from __future__ import annotations

from math import isfinite

from adv_py.core.body_fit_geo_attach import (
    BodyFitGeoAttachSpec, BodyFitGeoAttachState,
)


def _matrix(values) -> tuple[float, ...]:
    if len(values) == 1 and isinstance(values[0], (tuple, list)):
        values = values[0]
    return tuple(float(value) for value in values)


class MayaBodyFitGeoAttachMixin:
    def preflight_body_fit_geo_attach(
        self, spec: BodyFitGeoAttachSpec,
    ) -> BodyFitGeoAttachState:
        c = self._cmds
        for path in (spec.source_body, spec.fk_control,
                     spec.fk_offset, spec.offset_parent):
            if (c.ls(path, long=True) or []) != [path]:
                raise ValueError("Geo Attach 来源控制层缺失：" + path)
        if (c.listRelatives(spec.fk_offset, parent=True,
                            fullPath=True) or []) != [spec.offset_parent]:
            raise ValueError("Geo Attach FK Offset 父级已变化")
        if any(self.find_name_collisions(name) for name in spec.node_names):
            raise ValueError("Geo Attach 节点名称冲突")
        if c.attributeQuery("attach", node=spec.fk_control, exists=True):
            raise ValueError("Geo Attach FK 控制器 attach 通道已存在")
        if spec.mode not in ("point", "orient", "parent"):
            raise ValueError("Geo Attach 模式无效")
        mesh_name = spec.mesh
        if spec.side == "L" and mesh_name.endswith("_R"):
            left_name = mesh_name[:-2] + "_L"
            if c.objExists(left_name):
                mesh_name = left_name
        matches = c.ls(mesh_name, long=True) or []
        if len(matches) != 1:
            raise ValueError("Geo Attach 网格目标不存在或不唯一：" + mesh_name)
        mesh = matches[0]
        if c.nodeType(mesh) == "mesh":
            shape = mesh
            parents = c.listRelatives(shape, parent=True, fullPath=True) or []
            if len(parents) != 1:
                raise ValueError("Geo Attach 网格形状缺少唯一父级")
            mesh = parents[0]
        elif c.nodeType(mesh) == "transform":
            shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                     fullPath=True, type="mesh") or []
            if len(shapes) != 1:
                raise ValueError("Geo Attach 目标需要唯一可见网格形状")
            shape = shapes[0]
        else:
            raise ValueError("Geo Attach 目标不是 polygon 网格")
        plug = spec.fk_offset + ".offsetParentMatrix"
        if c.getAttr(plug, lock=True):
            raise ValueError("Geo Attach FK Offset 矩阵已锁定")
        upstream = c.connectionInfo(plug, sourceFromDestination=True) or None
        if upstream is None and not c.getAttr(plug, settable=True):
            raise ValueError("Geo Attach FK Offset 矩阵不可写")
        state = BodyFitGeoAttachState(
            shape,
            tuple(float(v) for v in c.xform(
                spec.source_body, query=True, worldSpace=True,
                translation=True)),
            _matrix(c.xform(spec.fk_offset, query=True,
                            worldSpace=True, matrix=True)),
            _matrix(c.xform(spec.offset_parent, query=True,
                            worldSpace=True, matrix=True)),
            upstream, _matrix(c.getAttr(plug)))
        if (len(state.source_position) != 3
                or any(len(m) != 16 or not all(isfinite(v) for v in m)
                       for m in (state.offset_world, state.parent_world,
                                 state.opm_value))):
            raise ValueError("Geo Attach 绑定矩阵或来源位置无效")
        return state

    def create_body_fit_geo_attach(
        self, spec: BodyFitGeoAttachSpec,
        state: BodyFitGeoAttachState,
    ) -> None:
        self._require_transaction()
        from maya.api import OpenMaya as om

        c = self._cmds
        plug = spec.fk_offset + ".offsetParentMatrix"
        if (c.connectionInfo(plug, sourceFromDestination=True) or None
                ) != state.opm_source:
            raise ValueError("Geo Attach FK Offset 原矩阵来源已变化")
        self._transaction_changed = True
        sampler = c.createNode("closestPointOnMesh")
        try:
            c.connectAttr(state.mesh_shape + ".outMesh",
                          sampler + ".inMesh")
            c.connectAttr(state.mesh_shape + ".worldMatrix[0]",
                          sampler + ".inputMatrix")
            c.setAttr(sampler + ".inPosition", *state.source_position,
                      type="double3")
            face = int(c.getAttr(sampler + ".closestFaceIndex"))
        finally:
            c.delete(sampler)
        if face < 0:
            raise ValueError("Geo Attach 无法确定最近网格面")
        mesh = (c.listRelatives(state.mesh_shape, parent=True,
                                fullPath=True) or [])[0]
        surface = c.createNode(
            "transform", name=spec.surface,
            parent="|Group|MotionSystem|ConstraintSystem")
        c.xform(surface, worldSpace=True, matrix=state.offset_world)
        constraint = c.pointOnPolyConstraint(
            f"{mesh}.f[{face}]", surface,
            maintainOffset=False, name=spec.constraint)
        constraint_name = (constraint[0] if isinstance(constraint, (list, tuple))
                           else constraint)
        if (not constraint_name or c.nodeType(constraint_name)
                != "pointOnPolyConstraint"):
            raise RuntimeError("Geo Attach 网格面约束创建失败")
        surface_world = om.MMatrix(_matrix(c.xform(
            surface, query=True, worldSpace=True, matrix=True)))
        offset_world = om.MMatrix(state.offset_world)
        parent_world = om.MMatrix(state.parent_world)
        opm = om.MMatrix(state.opm_value)
        local = offset_world * parent_world.inverse() * opm.inverse()
        static = c.createNode("multMatrix", name=spec.static_matrix)
        c.setAttr(static + ".matrixIn[0]", *tuple(local), type="matrix")
        if state.opm_source is None:
            c.setAttr(static + ".matrixIn[1]",
                      *state.opm_value, type="matrix")
        else:
            c.connectAttr(state.opm_source, static + ".matrixIn[1]")
        c.connectAttr(spec.offset_parent + ".worldMatrix[0]",
                      static + ".matrixIn[2]")
        attached = c.createNode("multMatrix", name=spec.attached_matrix)
        correction = tuple(offset_world * surface_world.inverse())
        c.setAttr(attached + ".matrixIn[0]", *correction, type="matrix")
        c.connectAttr(surface + ".worldMatrix[0]",
                      attached + ".matrixIn[1]")
        blend = c.createNode("blendMatrix", name=spec.blend_matrix)
        c.connectAttr(static + ".matrixSum", blend + ".inputMatrix")
        c.connectAttr(attached + ".matrixSum",
                      blend + ".target[0].targetMatrix")
        for attr, enabled in (
                ("useTranslate", spec.mode != "orient"),
                ("useRotate", spec.mode != "point"),
                ("useScale", False), ("useShear", False)):
            c.setAttr(blend + ".target[0]." + attr, enabled)
        c.addAttr(spec.fk_control, longName="attach",
                  attributeType="double", minValue=0, maxValue=10,
                  defaultValue=10, keyable=True)
        weight = c.createNode("multDoubleLinear", name=spec.weight_node)
        c.setAttr(weight + ".input2", 0.1)
        c.connectAttr(spec.fk_control + ".attach", weight + ".input1")
        c.connectAttr(weight + ".output", blend + ".target[0].weight")
        output = c.createNode("multMatrix", name=spec.output_matrix)
        c.setAttr(output + ".matrixIn[0]", *tuple(local.inverse()),
                  type="matrix")
        c.connectAttr(blend + ".outputMatrix", output + ".matrixIn[1]")
        c.connectAttr(spec.offset_parent + ".worldInverseMatrix[0]",
                      output + ".matrixIn[2]")
        if state.opm_source is not None:
            c.disconnectAttr(state.opm_source, plug)
        c.connectAttr(output + ".matrixSum", plug)
        actual = _matrix(c.xform(spec.fk_offset, query=True,
                                 worldSpace=True, matrix=True))
        if any(abs(a - b) > 1e-4 for a, b in zip(actual, state.offset_world)):
            raise RuntimeError("Geo Attach 改变了 FK 绑定姿态")

    def capture_body_fit_geo_attach(
        self, spec: BodyFitGeoAttachSpec,
        state: BodyFitGeoAttachState,
    ) -> bool:
        c = self._cmds
        expected = (
            (spec.surface, "transform"),
            (spec.constraint, "pointOnPolyConstraint"),
            (spec.static_matrix, "multMatrix"),
            (spec.attached_matrix, "multMatrix"),
            (spec.blend_matrix, "blendMatrix"),
            (spec.weight_node, "multDoubleLinear"),
            (spec.output_matrix, "multMatrix"))
        if any(not c.objExists(name) or c.nodeType(name) != kind
               for name, kind in expected):
            return False
        links = [
            (spec.surface + ".worldMatrix[0]",
             spec.attached_matrix + ".matrixIn[1]"),
            (spec.static_matrix + ".matrixSum",
             spec.blend_matrix + ".inputMatrix"),
            (spec.attached_matrix + ".matrixSum",
             spec.blend_matrix + ".target[0].targetMatrix"),
            (spec.fk_control + ".attach",
             spec.weight_node + ".input1"),
            (spec.weight_node + ".output",
             spec.blend_matrix + ".target[0].weight"),
            (spec.blend_matrix + ".outputMatrix",
             spec.output_matrix + ".matrixIn[1]"),
            (spec.offset_parent + ".worldInverseMatrix[0]",
             spec.output_matrix + ".matrixIn[2]"),
            (spec.output_matrix + ".matrixSum",
             spec.fk_offset + ".offsetParentMatrix")]
        if state.opm_source is not None:
            links.append((state.opm_source,
                          spec.static_matrix + ".matrixIn[1]"))
        for attr, enabled in (
                ("useTranslate", spec.mode != "orient"),
                ("useRotate", spec.mode != "point"),
                ("useScale", False), ("useShear", False)):
            if bool(c.getAttr(spec.blend_matrix
                              + ".target[0]." + attr)) != enabled:
                return False
        constraint_sources = c.listConnections(
            spec.constraint, source=True, destination=False) or []
        return (state.mesh_shape in constraint_sources
                and all(c.connectionInfo(dst, sourceFromDestination=True) == src
                    for src, dst in links)
                and abs(float(c.getAttr(spec.fk_control + ".attach")) - 10)
                < 1e-8
                and all(abs(a - b) <= 1e-4 for a, b in zip(
                    _matrix(c.xform(spec.fk_offset, query=True,
                                    worldSpace=True, matrix=True)),
                    state.offset_world)))
