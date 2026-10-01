"""Maya nodes for the generic per-Fit-joint ADV Aim controller chain."""
from __future__ import annotations

from adv_py.core.body_fit_aim import BodyFitAimSpec
from adv_py.core.fit_settings import FitSkeletonValidationError


def _matrix(value):
    if len(value) == 1 and isinstance(value[0], (tuple, list)):
        value = value[0]
    return tuple(float(item) for item in value)


def _set_matrix(cmds, plug, values):
    cmds.setAttr(plug, *_matrix(values), type="matrix")


def _cross(cmds, name, parent, radius, color):
    points = [(0, radius, 0), (0, -radius, 0), (0, 0, 0),
              (radius, 0, 0), (-radius, 0, 0)]
    curve = cmds.curve(degree=1, point=points, knot=list(range(5)), name=name)
    curve = cmds.parent(curve, parent, relative=True)[0]
    curve = (cmds.ls(curve, long=True) or [curve])[0]
    shape = (cmds.listRelatives(curve, shapes=True, fullPath=True) or [])[0]
    if shape.rsplit('|',1)[-1] != name+'Shape':
        cmds.rename(shape,name+'Shape')
        shape=(cmds.listRelatives(curve,shapes=True,fullPath=True) or [])[0]
    if shape != curve + "|" + name + "Shape":
        raise FitSkeletonValidationError("Aim 曲线 Shape 名称漂移：" + name)
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideColor", color)
    return curve, shape


class MayaBodyFitAimMixin:
    def create_body_fit_aim(self, spec: BodyFitAimSpec, *,
                            global_control: str,
                            use_offset_parent_matrix: bool) -> None:
        self._require_transaction()
        c = self._cmds
        for path in (spec.root.rsplit("|", 1)[0], spec.follow_joint,
                     global_control, *(side.fk_aim for side in spec.sides)):
            if (c.ls(path, long=True) or []) != [path]:
                raise FitSkeletonValidationError("通用 Aim 构建来源不存在：" + path)
        self._transaction_changed = True
        c.createNode("transform", name=spec.root.rsplit("|", 1)[-1],
                     parent=spec.root.rsplit("|", 1)[0], skipSelect=True)
        c.createNode("transform", name=spec.offset.rsplit("|", 1)[-1],
                     parent=spec.root, skipSelect=True)
        c.createNode("transform", name=spec.follow.rsplit("|", 1)[-1],
                     parent=spec.offset, skipSelect=True)
        c.xform(spec.offset, worldSpace=True, translation=spec.center_position)
        center, _ = _cross(c, spec.center_control.rsplit("|", 1)[-1],
                           spec.follow, spec.control_radius, 17)
        if center != spec.center_control:
            raise RuntimeError("Aim 中央控制路径漂移")
        c.addAttr(center, longName="follow", attributeType="double",
                  minValue=0.0, maxValue=10.0, defaultValue=10.0,
                  keyable=True)

        # The target keeps its bind offset from the source parent. The static
        # branch freezes its initial world pose when follow is zero.
        from maya.api import OpenMaya as om
        follow_world = _matrix(c.xform(spec.follow, query=True,
                                       worldSpace=True, matrix=True))
        parent_world = _matrix(c.xform(spec.follow_joint, query=True,
                                       worldSpace=True, matrix=True))
        main_world = _matrix(c.xform(global_control, query=True,
                                     worldSpace=True, matrix=True))
        offset_matrix = tuple(om.MMatrix(follow_world)
                              * om.MMatrix(parent_world).inverse())
        static_matrix = tuple(om.MMatrix(follow_world)
                              * om.MMatrix(main_world).inverse())
        c.createNode("blendMatrix", name=spec.follow_blend_name,
                     skipSelect=True)
        c.createNode("multMatrix", name=spec.follow_target_name,
                     skipSelect=True)
        c.createNode("multMatrix", name=spec.follow_static_name,
                     skipSelect=True)
        c.createNode("multMatrix", name=spec.follow_local_name,
                     skipSelect=True)
        c.createNode("multDoubleLinear", name=spec.follow_weight_name,
                     skipSelect=True)
        _set_matrix(c, spec.follow_static_name + ".matrixIn[0]", static_matrix)
        c.connectAttr(global_control + ".worldMatrix[0]",
                      spec.follow_static_name + ".matrixIn[1]")
        c.connectAttr(spec.follow_static_name + ".matrixSum",
                      spec.follow_blend_name + ".inputMatrix")
        _set_matrix(c, spec.follow_target_name + ".matrixIn[0]", offset_matrix)
        c.connectAttr(spec.follow_joint + ".worldMatrix[0]",
                      spec.follow_target_name + ".matrixIn[1]")
        c.connectAttr(spec.follow_target_name + ".matrixSum",
                      spec.follow_blend_name + ".target[0].targetMatrix")
        c.connectAttr(center + ".follow",
                      spec.follow_weight_name + ".input1")
        c.setAttr(spec.follow_weight_name + ".input2", 0.1)
        c.connectAttr(spec.follow_weight_name + ".output",
                      spec.follow_blend_name + ".target[0].weight")
        c.connectAttr(spec.follow_blend_name + ".outputMatrix",
                      spec.follow_local_name + ".matrixIn[0]")
        c.connectAttr(spec.offset + ".worldInverseMatrix[0]",
                      spec.follow_local_name + ".matrixIn[1]")
        if use_offset_parent_matrix:
            c.connectAttr(spec.follow_local_name + ".matrixSum",
                          spec.follow + ".offsetParentMatrix")
        else:
            decompose = c.createNode("decomposeMatrix",
                                     name=spec.follow_local_name + "DM",
                                     skipSelect=True)
            c.connectAttr(spec.follow_local_name + ".matrixSum",
                          decompose + ".inputMatrix")
            c.connectAttr(decompose + ".outputTranslate", spec.follow + ".translate")
            c.connectAttr(decompose + ".outputRotate", spec.follow + ".rotate")

        for side in spec.sides:
            if side.suffix == "M":
                target = center
            else:
                c.createNode("transform",
                             name=side.target_offset.rsplit("|", 1)[-1],
                             parent=center, skipSelect=True)
                c.xform(side.target_offset, worldSpace=True,
                        translation=side.bind_position)
                c.setAttr(side.target_offset + ".scale", 0.2, 0.2, 0.2)
                c.setAttr(side.target_offset + ".translateZ", 0.0)
                target, shape = _cross(
                    c, side.target_control.rsplit("|", 1)[-1],
                    side.target_offset, spec.control_radius, 17)
                if target != side.target_control:
                    raise RuntimeError("Aim 侧控制路径漂移")
                c.connectAttr(global_control + ".aimLRVis",
                              shape + ".visibility")
            c.createNode("aimMatrix", name=side.aim_matrix_name,
                         skipSelect=True)
            c.setAttr(side.aim_matrix_name + ".secondaryInputAxis",
                      0.0, 0.0, 1.0, type="double3")
            c.setAttr(side.aim_matrix_name + ".secondaryTargetVector",
                      0.0, 0.0, 1.0, type="double3")
            c.connectAttr(target + ".worldMatrix[0]",
                          side.aim_matrix_name + ".primaryTargetMatrix")
            for input_name in ("inputMatrix", "secondaryTargetMatrix"):
                c.connectAttr(side.fk_offset + ".worldMatrix[0]",
                              side.aim_matrix_name + "." + input_name)
            c.createNode("multMatrix", name=side.local_matrix_name,
                         skipSelect=True)
            c.connectAttr(side.aim_matrix_name + ".outputMatrix",
                          side.local_matrix_name + ".matrixIn[1]")
            c.connectAttr(side.fk_offset + ".worldInverseMatrix[0]",
                          side.local_matrix_name + ".matrixIn[2]")
            # Evaluate the same native inverse without attaching and deleting
            # a temporary DG sink: Maya can prune its otherwise unused input.
            correction = tuple(om.MMatrix(_matrix(c.getAttr(
                side.local_matrix_name + '.matrixSum'))).inverse())
            _set_matrix(c, side.local_matrix_name + ".matrixIn[0]", correction)
            if use_offset_parent_matrix:
                c.connectAttr(side.local_matrix_name + ".matrixSum",
                              side.fk_aim + ".offsetParentMatrix")
            else:
                decompose = c.createNode("decomposeMatrix",
                                         name=side.local_matrix_name + "DM",
                                         skipSelect=True)
                c.connectAttr(side.local_matrix_name + ".matrixSum",
                              decompose + ".inputMatrix")
                c.connectAttr(decompose + ".outputTranslate",
                              side.fk_aim + ".translate")
                c.connectAttr(decompose + ".outputRotate",
                              side.fk_aim + ".rotate")
            shapes = c.listRelatives(side.fk_control, shapes=True,
                                     fullPath=True, type="nurbsCurve") or []
            if len(shapes) != 1:
                raise FitSkeletonValidationError("Aim FK 控制曲线不唯一："
                                                 + side.fk_control)
            c.connectAttr(global_control + ".aimFKVis",
                          shapes[0] + ".visibility", force=True)

    def capture_body_fit_aim(self, spec: BodyFitAimSpec, *,
                             global_control: str,
                             use_offset_parent_matrix: bool) -> bool:
        c = self._cmds
        expected = ((spec.root, "transform"), (spec.offset, "transform"),
                    (spec.follow, "transform"),
                    (spec.center_control, "transform"),
                    (spec.follow_blend_name, "blendMatrix"),
                    (spec.follow_target_name, "multMatrix"),
                    (spec.follow_static_name, "multMatrix"),
                    (spec.follow_local_name, "multMatrix"),
                    (spec.follow_weight_name, "multDoubleLinear"))
        if any((c.ls(name, long=True) or []) != [name]
               if name.startswith("|") else not c.objExists(name)
               for name, _ in expected):
            return False
        if any(c.nodeType(name) != kind for name, kind in expected):
            return False
        center_shapes = c.listRelatives(
            spec.center_control, shapes=True, fullPath=True,
            type="nurbsCurve") or []
        if (center_shapes != [spec.center_control + "|"
                              + spec.center_control.rsplit("|", 1)[-1]
                              + "Shape"]
                or not c.getAttr(center_shapes[0] + ".overrideEnabled")
                or c.getAttr(center_shapes[0] + ".overrideColor") != 17):
            return False
        if not c.isConnected(spec.follow_joint + ".worldMatrix[0]",
                             spec.follow_target_name + ".matrixIn[1]"):
            return False
        if not c.isConnected(spec.center_control + ".follow",
                             spec.follow_weight_name + ".input1"):
            return False
        if (abs(float(c.getAttr(spec.center_control + ".follow")) - 10.0) > 1e-6
                or abs(float(c.getAttr(spec.follow_weight_name + ".input2"))
                       - 0.1) > 1e-8):
            return False
        for source, target in (
                (global_control + ".worldMatrix[0]",
                 spec.follow_static_name + ".matrixIn[1]"),
                (spec.follow_static_name + ".matrixSum",
                 spec.follow_blend_name + ".inputMatrix"),
                (spec.follow_target_name + ".matrixSum",
                 spec.follow_blend_name + ".target[0].targetMatrix"),
                (spec.follow_weight_name + ".output",
                 spec.follow_blend_name + ".target[0].weight"),
                (spec.follow_blend_name + ".outputMatrix",
                 spec.follow_local_name + ".matrixIn[0]"),
                (spec.offset + ".worldInverseMatrix[0]",
                 spec.follow_local_name + ".matrixIn[1]")):
            if not c.isConnected(source, target):
                return False
        if not c.isConnected(spec.follow_local_name + ".matrixSum",
                             spec.follow + (".offsetParentMatrix" if
                                            use_offset_parent_matrix else
                                            "DM.inputMatrix")):
            return False
        for side in spec.sides:
            for path in ((side.target_offset,) if side.suffix != "M" else ()) + (
                         side.target_control,
                         side.fk_offset, side.fk_aim, side.fk_control):
                if (c.ls(path, long=True) or []) != [path]:
                    return False
            if (c.nodeType(side.aim_matrix_name) != "aimMatrix"
                    or c.nodeType(side.local_matrix_name) != "multMatrix"):
                return False
            if not c.isConnected(side.target_control + ".worldMatrix[0]",
                                 side.aim_matrix_name + ".primaryTargetMatrix"):
                return False
            for source, target in (
                    (side.fk_offset + ".worldMatrix[0]",
                     side.aim_matrix_name + ".inputMatrix"),
                    (side.fk_offset + ".worldMatrix[0]",
                     side.aim_matrix_name + ".secondaryTargetMatrix"),
                    (side.aim_matrix_name + ".outputMatrix",
                     side.local_matrix_name + ".matrixIn[1]"),
                    (side.fk_offset + ".worldInverseMatrix[0]",
                     side.local_matrix_name + ".matrixIn[2]")):
                if not c.isConnected(source, target):
                    return False
            fk_shapes = c.listRelatives(
                side.fk_control, shapes=True, fullPath=True,
                type="nurbsCurve") or []
            if (len(fk_shapes) != 1
                    or not c.isConnected(global_control + ".aimFKVis",
                                         fk_shapes[0] + ".visibility")):
                return False
            if side.suffix != "M":
                target_shapes = c.listRelatives(
                    side.target_control, shapes=True, fullPath=True,
                    type="nurbsCurve") or []
                if (len(target_shapes) != 1
                        or target_shapes[0] != side.target_control + "|"
                        + side.target_control.rsplit("|", 1)[-1] + "Shape"
                        or not c.getAttr(target_shapes[0] + ".overrideEnabled")
                        or c.getAttr(target_shapes[0] + ".overrideColor") != 17
                        or not c.isConnected(global_control + ".aimLRVis",
                                             target_shapes[0] + ".visibility")):
                    return False
            output = (side.fk_aim + ".offsetParentMatrix" if
                      use_offset_parent_matrix else
                      side.local_matrix_name + "DM.inputMatrix")
            if not c.isConnected(side.local_matrix_name + ".matrixSum",
                                 output):
                return False
        return True
