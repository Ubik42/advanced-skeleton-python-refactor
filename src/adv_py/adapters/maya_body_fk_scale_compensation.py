"""Maya matrix graph for ADV FK segment scale compensation."""
from __future__ import annotations

from adv_py.core.body_fk_scale_compensation import (
    BodyFkScaleCompensationSpec,
)


def _matrix(values) -> tuple[float, ...]:
    if len(values) == 1 and isinstance(values[0], (tuple, list)):
        values = values[0]
    return tuple(float(value) for value in values)


class MayaBodyFkScaleCompensationMixin:
    def preflight_body_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec,
    ) -> None:
        c = self._cmds
        parent = c.ls(spec.parent_control_path, long=True,
                      type="transform") or []
        offset = c.ls(spec.offset_path, long=True,
                      type="transform") or []
        if (parent != [spec.parent_control_path]
                or offset != [spec.offset_path]
                or (c.listRelatives(spec.offset_path, parent=True,
                                    fullPath=True) or []) != parent):
            raise ValueError("FK 缩放补偿父子控制层无效："
                             + spec.offset_path)
        if any(self.find_name_collisions(name)
               for name in spec.node_names):
            raise ValueError("FK 缩放补偿节点名称冲突："
                             + spec.offset_path)
        if (c.ls(spec.control_path, long=True, type="transform") or []) != [
                spec.control_path]:
            raise ValueError("FK 缩放补偿控制器无效：" + spec.control_path)
        if (c.ls(spec.scale_source_path, long=True,
                 type="transform") or []) != [spec.scale_source_path]:
            raise ValueError("FK 缩放来源无效：" + spec.scale_source_path)
        if c.attributeQuery("inheritScale", node=spec.control_path,
                            exists=True):
            raise ValueError("FK 控制器已有 inheritScale 属性："
                             + spec.control_path)
        if c.connectionInfo(spec.offset_path + ".offsetParentMatrix",
                            isDestination=True):
            raise ValueError("FK Offset 已有矩阵驱动：" + spec.offset_path)
        static_opm = _matrix(c.getAttr(spec.offset_path
                                       + ".offsetParentMatrix"))
        identity = (1.0, 0.0, 0.0, 0.0,
                    0.0, 1.0, 0.0, 0.0,
                    0.0, 0.0, 1.0, 0.0,
                    0.0, 0.0, 0.0, 1.0)
        if (len(static_opm) != 16 or any(
                abs(a - b) > 1e-6
                for a, b in zip(static_opm, identity))):
            raise ValueError("FK Offset 静态矩阵不是单位矩阵："
                             + spec.offset_path)
        if any(not c.getAttr(spec.offset_path + "." + attr,
                             settable=True)
               for attr in ("translateX", "translateY", "translateZ",
                            "rotateX", "rotateY", "rotateZ",
                            "scaleX", "scaleY", "scaleZ")):
            raise ValueError("FK Offset 本地通道不可写："
                             + spec.offset_path)

    def connect_body_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        offset = spec.offset_path
        parent = spec.parent_control_path
        local = _matrix(c.getAttr(offset + ".matrix"))
        if len(local) != 16:
            raise RuntimeError("FK Offset 局部矩阵无效：" + offset)
        self._transaction_changed = True
        world = c.createNode("multMatrix", name=spec.world_matrix_name)
        pick = c.createNode("pickMatrix", name=spec.pick_matrix_name)
        relative = c.createNode("multMatrix",
                                name=spec.relative_matrix_name)
        c.setAttr(world + ".matrixIn[0]", *local, type="matrix")
        c.connectAttr(spec.scale_source_path + ".worldMatrix[0]",
                      world + ".matrixIn[1]")
        c.connectAttr(world + ".matrixSum", pick + ".inputMatrix")
        c.addAttr(spec.control_path, longName="inheritScale",
                  attributeType="bool", defaultValue=spec.inherit_scale,
                  keyable=False)
        c.connectAttr(spec.control_path + ".inheritScale",
                      pick + ".useScale")
        c.connectAttr(spec.control_path + ".inheritScale",
                      pick + ".useShear")
        c.connectAttr(pick + ".outputMatrix",
                      relative + ".matrixIn[0]")
        c.connectAttr(parent + ".worldInverseMatrix[0]",
                      relative + ".matrixIn[1]")
        c.setAttr(offset + ".translate", 0, 0, 0)
        c.setAttr(offset + ".rotate", 0, 0, 0)
        c.setAttr(offset + ".scale", 1, 1, 1)
        c.connectAttr(relative + ".matrixSum",
                      offset + ".offsetParentMatrix")

    def capture_body_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec,
    ) -> bool:
        c = self._cmds
        world, pick, relative = spec.node_names
        if any(not c.objExists(name) or c.nodeType(name) != kind
               for name, kind in ((world, "multMatrix"),
                                  (pick, "pickMatrix"),
                                  (relative, "multMatrix"))):
            return False
        links = (
            (spec.scale_source_path + ".worldMatrix[0]",
             world + ".matrixIn[1]"),
            (world + ".matrixSum", pick + ".inputMatrix"),
            (spec.control_path + ".inheritScale", pick + ".useScale"),
            (spec.control_path + ".inheritScale", pick + ".useShear"),
            (pick + ".outputMatrix", relative + ".matrixIn[0]"),
            (spec.parent_control_path + ".worldInverseMatrix[0]",
             relative + ".matrixIn[1]"),
            (relative + ".matrixSum",
             spec.offset_path + ".offsetParentMatrix"),
        )
        if (not c.attributeQuery("inheritScale", node=spec.control_path,
                                 exists=True)
                or bool(c.getAttr(spec.control_path + ".inheritScale"))
                != spec.inherit_scale
                or any(c.connectionInfo(target,
                       sourceFromDestination=True) != source
                       for source, target in links)):
            return False
        for attr, expected in (("translate", (0.0, 0.0, 0.0)),
                               ("rotate", (0.0, 0.0, 0.0)),
                               ("scale", (1.0, 1.0, 1.0))):
            current = c.getAttr(spec.offset_path + "." + attr)[0]
            if any(abs(float(a) - b) > 1e-5
                   for a, b in zip(current, expected)):
                return False
        actual = _matrix(c.xform(spec.offset_path, query=True,
                                 worldSpace=True, matrix=True))
        expected = tuple(value for axis in spec.world_axes
                         for value in (*axis, 0.0)) + (
                             *spec.world_position, 1.0)
        return (len(actual) == 16
                and all(abs(a - b) <= 1e-4
                        for a, b in zip(actual, expected)))
