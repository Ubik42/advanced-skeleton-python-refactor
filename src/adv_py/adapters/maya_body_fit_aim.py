"""Maya nodes for the generic per-Fit-joint ADV Aim controller chain."""
from __future__ import annotations

from adv_py.core.body_fit_aim import BodyFitAimSpec
from adv_py.core.fit_settings import FitSkeletonValidationError

FULL_DECOMPOSE = "advPySourceAimFullDecompose"
SOURCE_FOLLOW = "advPySourceAimFollow"
SOURCE_SIDE_CHANNELS = "advPySourceAimSideChannels"


def create_source_aim_decompose(c, matrix, receiver, name):
    """MEL 74619–74627: receiver order and all twelve TRS/shear outputs."""
    dm = c.createNode("decomposeMatrix", name=name, skipSelect=True)
    c.setAttr(dm + ".inputRotateOrder", c.getAttr(receiver + ".rotateOrder"))
    c.connectAttr(matrix, dm + ".inputMatrix")
    for output, target in (("Translate", "translate"), ("Rotate", "rotate"),
                           ("Scale", "scale"), ("Shear", "shear")):
        for axis, suffix in zip("XYZ", ("XY", "XZ", "YZ") if target == "shear" else "XYZ"):
            c.connectAttr(dm + ".output" + output + axis, receiver + "." + target + suffix)
    c.addAttr(dm, longName=FULL_DECOMPOSE, attributeType="bool", defaultValue=True)
    c.setAttr(dm + "." + FULL_DECOMPOSE, True, lock=True)
    return dm


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
    def capture_body_fit_aim_source_order(self, hierarchy) -> tuple[str, ...]:
        """MEL 78982 keeps Maya's descendant order for both Aim passes."""
        paths = tuple(self._cmds.listRelatives(hierarchy.container,
            allDescendents=True, type="joint", fullPath=True) or ())
        expected = {joint.path for joint in hierarchy.joints}
        if len(paths) != len(expected) or set(paths) != expected:
            raise FitSkeletonValidationError("Fit Aim 原版遍历来源与层级快照不一致")
        return paths

    def create_body_fit_aim(self, spec: BodyFitAimSpec, *, global_control: str,
                            use_offset_parent_matrix: bool) -> None:
        self._create_body_fit_aim_center(spec, global_control=global_control,
                                        use_offset_parent_matrix=use_offset_parent_matrix)
        for side in spec.sides:
            self._create_body_fit_aim_side(spec, side, global_control=global_control,
                                          use_offset_parent_matrix=use_offset_parent_matrix)

    def create_body_fit_aims(self, specs, *, global_control: str,
                             use_offset_parent_matrix: bool) -> None:
        """MEL 80634: complete the original first-side pass before mirrored L."""
        created = set()
        jobs = [(spec, side) for spec in specs for side in spec.sides]
        jobs.sort(key=lambda row: (row[1].creation_mirrored,
                  row[1].source_order if row[1].source_order is not None else len(jobs)))
        for spec, side in jobs:
            if spec.root not in created:
                self._create_body_fit_aim_center(spec, global_control=global_control,
                                                use_offset_parent_matrix=use_offset_parent_matrix)
                created.add(spec.root)
            self._create_body_fit_aim_side(spec, side, global_control=global_control,
                                          use_offset_parent_matrix=use_offset_parent_matrix)

    def _create_body_fit_aim_center(self, spec: BodyFitAimSpec, *,
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
        offset_matrix = tuple(om.MMatrix(follow_world)
                              * om.MMatrix(parent_world).inverse())
        # MEL 74325–74330 stores the driven world matrix directly, then
        # multiplies by Main. It does not remove Main's initial transform.
        static_matrix = follow_world
        c.createNode("blendMatrix", name=spec.follow_blend_name,
                     skipSelect=True)
        c.addAttr(spec.follow_blend_name, longName=SOURCE_FOLLOW,
                  attributeType="bool", defaultValue=True)
        c.setAttr(spec.follow_blend_name + "." + SOURCE_FOLLOW, True, lock=True)
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
            # asParentConstraintBlend 74350–74355 emits compound TRS.
            # Its Aim caller replaces only inputMatrix (80679–80683).
            c.setAttr(decompose + ".inputRotateOrder", c.getAttr(spec.follow + ".rotateOrder"))
            c.connectAttr(spec.follow_local_name + ".matrixSum",
                          decompose + ".inputMatrix")
            c.connectAttr(decompose + ".outputTranslate", spec.follow + ".translate")
            c.connectAttr(decompose + ".outputRotate", spec.follow + ".rotate")
            c.connectAttr(decompose + ".outputScale", spec.follow + ".scale")

    def _create_body_fit_aim_side(self, spec, side, *, global_control,
                                   use_offset_parent_matrix):
        from maya.api import OpenMaya as om
        c = self._cmds
        center = spec.center_control
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
            if side.native_channels:
                # MEL 80687 calls asLockAttr(target, 0, 1, 1, 1).
                for kind, locked in (("translate", False), ("rotate", True), ("scale", True)):
                    for axis in "XYZ":
                        c.setAttr(target + "." + kind + axis, lock=locked, keyable=not locked)
                c.setAttr(target + ".translate", lock=False, keyable=False)
                c.setAttr(target + ".visibility", lock=True, keyable=False)
                c.addAttr(target, longName=SOURCE_SIDE_CHANNELS, attributeType="bool", defaultValue=True)
                c.setAttr(target + "." + SOURCE_SIDE_CHANNELS, True, lock=True)
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
            create_source_aim_decompose(c, side.local_matrix_name + ".matrixSum",
                                       side.fk_aim, side.local_matrix_name + "DM")
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
        follow_output = (spec.follow + ".offsetParentMatrix" if use_offset_parent_matrix
                         else spec.follow_local_name + "DM.inputMatrix")
        if not c.isConnected(spec.follow_local_name + ".matrixSum", follow_output):
            return False
        native_follow = c.attributeQuery(SOURCE_FOLLOW, node=spec.follow_blend_name, exists=True)
        if native_follow and (not c.getAttr(spec.follow_blend_name + "." + SOURCE_FOLLOW)
                              or not c.getAttr(spec.follow_blend_name + "." + SOURCE_FOLLOW, lock=True)):
            return False
        if not use_offset_parent_matrix:
            dm = spec.follow_local_name + "DM"
            if c.nodeType(dm) != "decomposeMatrix":
                return False
            kinds = ("Translate", "Rotate", "Scale") if native_follow else ("Translate", "Rotate")
            if any(not c.isConnected(dm + ".output" + kind, spec.follow + "." + kind.lower())
                   for kind in kinds):
                return False
            if native_follow and c.getAttr(dm + ".inputRotateOrder") != c.getAttr(spec.follow + ".rotateOrder"):
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
                if side.native_channels:
                    marker = side.target_control + "." + SOURCE_SIDE_CHANNELS
                    if (not c.objExists(marker) or not c.getAttr(marker)
                            or not c.getAttr(marker, lock=True)):
                        return False
                    for kind, locked in (("translate", False), ("rotate", True), ("scale", True)):
                        for axis in "XYZ":
                            plug = side.target_control + "." + kind + axis
                            if c.getAttr(plug, lock=True) != locked or c.getAttr(plug, keyable=True) != (not locked):
                                return False
                    if (not c.getAttr(side.target_control + ".visibility", lock=True)
                            or c.getAttr(side.target_control + ".visibility", keyable=True)
                            or c.getAttr(side.target_control + ".translate", keyable=True)):
                        return False
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
            if not use_offset_parent_matrix:
                dm = side.local_matrix_name + "DM"
                # Existing saved TR-only graphs remain readable. Fresh graphs
                # explicitly record the native output contract.
                if c.attributeQuery(FULL_DECOMPOSE, node=dm, exists=True):
                    if (not c.getAttr(dm + "." + FULL_DECOMPOSE)
                            or not c.getAttr(dm + "." + FULL_DECOMPOSE, lock=True)
                            or c.getAttr(dm + ".inputRotateOrder") != c.getAttr(side.fk_aim + ".rotateOrder")):
                        return False
                    for kind, target in (("Translate", "translate"), ("Rotate", "rotate"),
                                         ("Scale", "scale"), ("Shear", "shear")):
                        for axis, suffix in zip("XYZ", ("XY", "XZ", "YZ") if target == "shear" else "XYZ"):
                            if not c.isConnected(dm + ".output" + kind + axis, side.fk_aim + "." + target + suffix):
                                return False
        return True
