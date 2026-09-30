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
        parent = c.ls(spec.parent_control_path, long=True) or []
        offset = c.ls(spec.offset_path, long=True,
                      type="transform") or []
        if (parent != [spec.parent_control_path]
                or c.nodeType(parent[0]) not in ("transform", "joint")
                or offset != [spec.offset_path]
                or (c.listRelatives(spec.offset_path, parent=True,
                                    fullPath=True) or []) != parent):
            raise ValueError("FK 缩放补偿父子控制层无效："
                             + spec.offset_path)
        if spec.independent_parent and not spec.use_offset_parent_matrix:
            raise ValueError("FK 独立父级矩阵只适用于 OPM 控制层："
                             + spec.offset_path)
        if spec.independent_parent and (
                spec.main_scale_source_path is None
                or (c.ls(spec.main_scale_source_path, long=True,
                         type="transform") or [])
                != [spec.main_scale_source_path]):
            raise ValueError("FK 独立父级矩阵缺少 Main 缩放来源："
                             + spec.offset_path)
        if any(self.find_name_collisions(name)
               for name in spec.node_names):
            raise ValueError("FK 缩放补偿节点名称冲突："
                             + spec.offset_path)
        if (c.ls(spec.control_path, long=True, type="transform") or []) != [
                spec.control_path]:
            raise ValueError("FK 缩放补偿控制器无效：" + spec.control_path)
        if ((c.ls(spec.scale_source_path, long=True) or [])
                != [spec.scale_source_path]
                or c.nodeType(spec.scale_source_path)
                not in ("transform", "joint")):
            raise ValueError("FK 缩放来源无效：" + spec.scale_source_path)
        if spec.mel_non_opm_fkx:
            if (spec.use_offset_parent_matrix
                    or c.nodeType(spec.parent_control_path) != "joint"
                    or spec.parent_fk_control_path is None
                    or (c.ls(spec.parent_fk_control_path, long=True,
                             type="transform") or [])
                    != [spec.parent_fk_control_path]
                    or spec.driven_joint_path is None
                    or (c.ls(spec.driven_joint_path, long=True,
                             type="joint") or [])
                    != [spec.driven_joint_path]):
                raise ValueError("非 OPM FKX 缩放补偿来源无效："
                                 + spec.offset_path)
            if spec.body_joint_path is not None and (
                    (c.ls(spec.body_joint_path, long=True,
                          type="joint") or []) != [spec.body_joint_path]
                    or not c.getAttr(spec.body_joint_path
                                     + ".segmentScaleCompensate",
                                     settable=True)):
                raise ValueError("FKX 对应 Body 关节缩放补偿属性不可写："
                                 + spec.offset_path)
            if any(self.find_name_collisions(name)
                   for name in spec.node_names):
                raise ValueError("FKPS 节点名称冲突：" + spec.offset_path)
            if (not c.getAttr(spec.parent_control_path
                              + ".segmentScaleCompensate", settable=True)
                    or not c.getAttr(spec.driven_joint_path
                                     + ".segmentScaleCompensate",
                                     settable=True)):
                raise ValueError("FKX 或被驱动关节缩放补偿属性不可写："
                                 + spec.offset_path)
            return
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
                            "scaleX", "scaleY", "scaleZ",
                            "shearXY", "shearXZ", "shearYZ")):
            raise ValueError("FK Offset 本地通道不可写："
                             + spec.offset_path)

    def connect_body_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec,
    ) -> None:
        self._require_transaction()
        if spec.mel_non_opm_fkx:
            self._connect_mel_non_opm_fk_scale_compensation(spec)
            return
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
        if spec.use_fkx_world_source:
            c.setAttr(pick + ".useShear", False)
        else:
            c.connectAttr(spec.control_path + ".inheritScale",
                          pick + ".useShear")
        if spec.independent_parent:
            main_scale = c.createNode("pickMatrix",
                                      name=spec.main_scale_pick_name)
            reverse = c.createNode("reverse",
                                   name=spec.inherit_scale_reverse_name)
            c.connectAttr(spec.main_scale_source_path + ".worldMatrix[0]",
                          main_scale + ".inputMatrix")
            c.setAttr(main_scale + ".useTranslate", False)
            c.setAttr(main_scale + ".useRotate", False)
            c.setAttr(main_scale + ".useShear", False)
            c.connectAttr(spec.control_path + ".inheritScale",
                          reverse + ".inputX")
            c.connectAttr(reverse + ".outputX",
                          main_scale + ".useScale")
            c.connectAttr(main_scale + ".outputMatrix",
                          relative + ".matrixIn[0]")
            c.connectAttr(pick + ".outputMatrix",
                          relative + ".matrixIn[1]")
            c.setAttr(offset + ".inheritsTransform", False)
        else:
            c.connectAttr(pick + ".outputMatrix",
                          relative + ".matrixIn[0]")
            c.connectAttr(parent + ".worldInverseMatrix[0]",
                          relative + ".matrixIn[1]")
        c.setAttr(offset + ".translate", 0, 0, 0)
        c.setAttr(offset + ".rotate", 0, 0, 0)
        c.setAttr(offset + ".scale", 1, 1, 1)
        c.setAttr(offset + ".shear", 0, 0, 0)
        if spec.use_offset_parent_matrix:
            c.connectAttr(relative + ".matrixSum",
                          offset + ".offsetParentMatrix")
        else:
            decompose = c.createNode("decomposeMatrix",
                                     name=spec.decompose_matrix_name)
            c.setAttr(decompose + ".inputRotateOrder",
                      c.getAttr(offset + ".rotateOrder"))
            c.connectAttr(relative + ".matrixSum",
                          decompose + ".inputMatrix")
            for source, destination in (
                    ("outputTranslate", "translate"),
                    ("outputRotate", "rotate"),
                    ("outputScale", "scale"),
                    ("outputShear", "shear")):
                c.connectAttr(decompose + "." + source,
                              offset + "." + destination)

    def capture_body_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec,
    ) -> bool:
        if spec.mel_non_opm_fkx:
            return self._capture_mel_non_opm_fk_scale_compensation(spec)
        c = self._cmds
        world = spec.world_matrix_name
        pick = spec.pick_matrix_name
        relative = spec.relative_matrix_name
        extra_nodes = (
            ((spec.main_scale_pick_name, "pickMatrix"),
             (spec.inherit_scale_reverse_name, "reverse"))
            if spec.independent_parent else ())
        if any(not c.objExists(name) or c.nodeType(name) != kind
               for name, kind in ((world, "multMatrix"),
                                  (pick, "pickMatrix"),
                                  (relative, "multMatrix"))
               + (((spec.decompose_matrix_name, "decomposeMatrix"),)
                  if not spec.use_offset_parent_matrix else ())
               + extra_nodes):
            return False
        links = (
            (spec.scale_source_path + ".worldMatrix[0]",
             world + ".matrixIn[1]"),
            (world + ".matrixSum", pick + ".inputMatrix"),
            (spec.control_path + ".inheritScale", pick + ".useScale"),
        )
        if spec.use_fkx_world_source:
            if (bool(c.getAttr(pick + ".useShear"))
                    or c.connectionInfo(pick + ".useShear",
                                        sourceFromDestination=True)):
                return False
        else:
            links += ((spec.control_path + ".inheritScale",
                       pick + ".useShear"),)
        if spec.independent_parent:
            links += (
                (spec.main_scale_source_path + ".worldMatrix[0]",
                 spec.main_scale_pick_name + ".inputMatrix"),
                (spec.control_path + ".inheritScale",
                 spec.inherit_scale_reverse_name + ".inputX"),
                (spec.inherit_scale_reverse_name + ".outputX",
                 spec.main_scale_pick_name + ".useScale"),
                (spec.main_scale_pick_name + ".outputMatrix",
                 relative + ".matrixIn[0]"),
                (pick + ".outputMatrix", relative + ".matrixIn[1]"),
            )
        else:
            links += ((pick + ".outputMatrix",
                       relative + ".matrixIn[0]"),)
            links += ((spec.parent_control_path + ".worldInverseMatrix[0]",
                       relative + ".matrixIn[1]"),)
        if spec.use_offset_parent_matrix:
            links += ((relative + ".matrixSum",
                       spec.offset_path + ".offsetParentMatrix"),)
        else:
            decompose = spec.decompose_matrix_name
            links += ((relative + ".matrixSum",
                       decompose + ".inputMatrix"),)
            links += tuple((decompose + "." + source,
                            spec.offset_path + "." + destination)
                           for source, destination in (
                               ("outputTranslate", "translate"),
                               ("outputRotate", "rotate"),
                               ("outputScale", "scale"),
                               ("outputShear", "shear")))
        if (not c.attributeQuery("inheritScale", node=spec.control_path,
                                 exists=True)
                or bool(c.getAttr(spec.control_path + ".inheritScale"))
                != spec.inherit_scale
                or (not spec.use_offset_parent_matrix
                    and c.getAttr(spec.decompose_matrix_name
                                  + ".inputRotateOrder")
                    != c.getAttr(spec.offset_path + ".rotateOrder"))
                or any(c.connectionInfo(target,
                       sourceFromDestination=True) != source
                       for source, target in links)):
            return False
        if spec.independent_parent:
            if (bool(c.getAttr(spec.offset_path + ".inheritsTransform"))
                    or any(bool(c.getAttr(spec.main_scale_pick_name
                                          + ".use" + attr))
                           for attr in ("Translate", "Rotate", "Shear"))):
                return False
        elif not bool(c.getAttr(spec.offset_path + ".inheritsTransform")):
            return False
        if spec.use_offset_parent_matrix:
            for attr, expected in (("translate", (0.0, 0.0, 0.0)),
                                   ("rotate", (0.0, 0.0, 0.0)),
                                   ("scale", (1.0, 1.0, 1.0)),
                                   ("shear", (0.0, 0.0, 0.0))):
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

    def _connect_mel_non_opm_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec,
    ) -> None:
        c = self._cmds
        self._transaction_changed = True
        if spec.inherit_scale:
            # MEL's non-OPM branch lets this segment inherit parent scale.
            c.setAttr(spec.driven_joint_path + ".segmentScaleCompensate", 0)
            if (spec.body_joint_path is not None
                    and spec.body_joint_path != spec.driven_joint_path):
                c.setAttr(spec.body_joint_path
                          + ".segmentScaleCompensate", 0)
            c.setAttr(spec.parent_control_path
                      + ".segmentScaleCompensate", 0)
            return
        if not spec.mel_non_opm_fkps_enabled:
            return
        ps1 = c.createNode("transform", name=spec.fkps1_name,
                           parent=spec.parent_fk_control_path,
                           skipSelect=True)
        ps2 = c.createNode("transform", name=spec.fkps2_name,
                           parent=spec.control_path,
                           skipSelect=True)
        order = int(c.getAttr(spec.offset_path + ".rotateOrder"))
        c.setAttr(ps1 + ".rotateOrder", order)
        c.setAttr(ps2 + ".rotateOrder", order)
        c.delete(c.pointConstraint(spec.control_path, ps2,
                                   maintainOffset=False))
        c.parent(ps2, ps1)
        c.parent(ps1, spec.parent_control_path)
        ps1 = (c.ls(spec.fkps1_name, long=True,
                    type="transform") or [])[0]
        ps2 = ps1 + "|" + spec.fkps2_name
        c.scaleConstraint(spec.scale_source_path, ps1,
                          maintainOffset=False,
                          name=spec.fkps_scale_constraint_name)
        c.pointConstraint(ps2, spec.offset_path,
                          maintainOffset=True,
                          name=spec.fkps_point_constraint_name)

    def _capture_mel_non_opm_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec,
    ) -> bool:
        c = self._cmds
        if (c.ls(spec.parent_control_path, long=True,
                 type="joint") or []) != [spec.parent_control_path]:
            return False
        if spec.inherit_scale:
            return (not bool(c.getAttr(
                spec.parent_control_path + ".segmentScaleCompensate"))
                and not bool(c.getAttr(
                    spec.driven_joint_path + ".segmentScaleCompensate"))
                and (spec.body_joint_path is None or not bool(c.getAttr(
                    spec.body_joint_path + ".segmentScaleCompensate"))))
        if not spec.mel_non_opm_fkps_enabled:
            return True
        ps1 = c.ls(spec.fkps1_name, long=True,
                   type="transform") or []
        ps2 = c.ls(spec.fkps2_name, long=True,
                   type="transform") or []
        if (len(ps1) != 1 or len(ps2) != 1
                or (c.listRelatives(ps1[0], parent=True,
                                    fullPath=True) or [])
                != [spec.parent_control_path]
                or (c.listRelatives(ps2[0], parent=True,
                                    fullPath=True) or []) != ps1):
            return False
        scale = c.ls(spec.fkps_scale_constraint_name,
                     type="scaleConstraint") or []
        point = c.ls(spec.fkps_point_constraint_name,
                     type="pointConstraint") or []
        if len(scale) != 1 or len(point) != 1:
            return False
        scale_targets = c.scaleConstraint(
            scale[0], query=True, targetList=True) or []
        point_targets = c.pointConstraint(
            point[0], query=True, targetList=True) or []
        return (len(scale_targets) == 1
                and (c.ls(scale_targets[0], long=True) or [])
                == [spec.scale_source_path]
                and len(point_targets) == 1
                and (c.ls(point_targets[0], long=True) or []) == [ps2[0]]
                and scale[0] in (c.listConnections(
                    ps1[0], source=True, destination=False,
                    type="scaleConstraint") or [])
                and point[0] in (c.listConnections(
                    spec.offset_path, source=True, destination=False,
                    type="pointConstraint") or []))
