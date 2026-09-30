"""Maya construction boundary for 6.925 Bendy guide curves."""
from __future__ import annotations

from math import isfinite
from typing import TYPE_CHECKING

from adv_py.core.fit_bendy import FitBendyChainSpec, FitBendyFkScaleSpec
from .maya_adv_icons import create_adv_icon, original_fit_icon_axis_offset

if TYPE_CHECKING:
    from adv_py.application.fit_bendy import FitBendyFollowSpec, FitBendyWorldSource


_GROUPS = ("AdvPy_BendSystem", "AdvPy_BendCurve",
           "AdvPy_BendJoints", "AdvPy_BendMPX")
_SECONDARY_GROUPS = ("AdvPy_Bend2Curve", "AdvPy_Bend2Joints",
                     "AdvPy_Bend2MPX")
_MICRO_GROUP = "AdvPy_MicroSystem"
_OWNER = "adv_py.fit_bendy_guides.v1"
# ADV 6.925 replaces the master Bend icon with this closed XZ curve.
_MASTER_BEND_PROFILE_XZ = (
    (-.04560501961, -.4902758548), (-.02387150518, -.4243238881),
    (.0867648719, -.4160438261), (.1914883666, -.3794110646),
    (.2377719073, -.4311782409), (.3278486135, -.3669356583),
    (.4017890057, -.2846332024), (.3555394961, -.2328353326),
    (.4036869496, -.132881309), (.4243238168, -.02387162653),
    (.4922974722, -.009672600642), (.4817001901, .1004570578),
    (.447394422, .2056424402), (.3794114127, .1914885915),
    (.3169220717, .2831625695), (.2328354286, .3555395649),
    (.2545254871, .4215060432), (.1538514984, .4673931203),
    (.04560501961, .4902759141), (.02387149831, .4243239682),
    (-.08676488394, .416043931), (-.1914883839, .3794111943),
    (-.2377719246, .4311783832), (-.3278486135, .3669357177),
    (-.4017890057, .2846332618), (-.355539503, .2328354127),
    (-.4036869461, .1328813396), (-.4243238081, .02387163224),
    (-.4922974593, .009672597803), (-.481700116, -.1004573535),
    (-.4473939713, -.2056428819), (-.3794109995, -.1914885403),
    (-.316922063, -.2831625638), (-.2328354251, -.3555395344),
    (-.2545254785, -.4215060253), (-.1538514984, -.4673930609),
    (-.04560501961, -.4902758548),
)


def _bendy_dag_name(path: str) -> str:
    return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]


def _bendy_parent_name(cmds, node: str) -> str | None:
    parents = cmds.listRelatives(node, parent=True,
                                 fullPath=True) or []
    return _bendy_dag_name(parents[0]) if len(parents) == 1 else None


class MayaFitBendyMixin:
    def capture_bendy_deform_path(self, name: str) -> str:
        paths = self._cmds.ls(name, long=True, type="joint") or []
        if (len(paths) != 1
                or paths[0].rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                != name):
            raise ValueError("Bendy 变形关节无法唯一定位：" + name)
        return paths[0]

    def _align_bendy_control(
            self, node: str, position: tuple[float, float, float],
            axes: tuple[tuple[float, float, float], ...] | None) -> None:
        c = self._cmds
        if axes is None:
            c.xform(node, worldSpace=True, translation=position)
            return
        matrix = tuple(value for axis in axes
                       for value in (*axis, 0.0)) + (*position, 1.0)
        c.xform(node, worldSpace=True, matrix=matrix)

    def _bendy_bind_parameter(self, shape: str,
                              position: tuple[float, ...]) -> float:
        c = self._cmds
        nearest = c.createNode("nearestPointOnCurve", skipSelect=True)
        try:
            c.connectAttr(shape + ".worldSpace[0]",
                          nearest + ".inputCurve")
            c.setAttr(nearest + ".inPosition", *position,
                      type="double3")
            parameter = float(c.getAttr(nearest + ".parameter"))
        finally:
            c.delete(nearest)
        if not isfinite(parameter) or not 0.0 <= parameter <= 1.0:
            raise ValueError("Bendy 绑定曲线参数超出原版 0–1 范围："
                             + shape)
        return parameter

    def _set_bendy_motion_parameter(self, path: str,
                                    parameter: float) -> None:
        c = self._cmds
        c.setAttr(path + ".uValue", parameter)
        c.addAttr(path, longName="advPyBendyBindU",
                  attributeType="double", defaultValue=parameter)
        c.setAttr(path + ".advPyBendyBindU", lock=True)

    def _bendy_motion_parameter_matches(self, path: str) -> bool:
        c = self._cmds
        plug = path + ".advPyBendyBindU"
        if not c.objExists(plug) or not c.getAttr(plug, lock=True):
            return False
        value = float(c.getAttr(path + ".uValue"))
        return (isfinite(value) and 0.0 <= value <= 1.0
                and abs(value - float(c.getAttr(plug))) <= 1e-8)

    def capture_bendy_control_path(
        self, name: str, ancestors: tuple[str, ...],
    ) -> str:
        """Resolve an animator control only under its planned Bendy chain."""
        c = self._cmds
        if (not name or not ancestors
                or ancestors[-1] not in (_GROUPS[0], _MICRO_GROUP)):
            raise ValueError("Bendy 控制器父链计划无效：" + name)
        matches = sorted(set(c.ls(name, "*:" + name, long=True,
                                  type="transform") or []))
        if len(matches) != 1:
            raise ValueError("Bendy 控制器不唯一或不存在：" + name)
        path = matches[0]
        parent = path
        for expected in ancestors:
            rows = c.listRelatives(parent, parent=True,
                                   fullPath=True) or []
            if len(rows) != 1 or _bendy_dag_name(rows[0]) != expected:
                raise ValueError("Bendy 控制器父链与计划不一致：" + name)
            parent = rows[0]
        marker = parent + ".advPyBendyGuideOwner"
        if not c.objExists(marker) or c.getAttr(marker) != _OWNER:
            raise ValueError("Bendy 控制器系统归属无效：" + name)
        return path

    def preflight_fit_bendy_secondary(self,
                                      spec: FitBendyChainSpec) -> None:
        if spec.control_count == 1:
            return
        c = self._cmds
        if any(c.objExists(name) for name in spec.secondary_node_names):
            raise ValueError("Bendy 第二曲线节点名称已占用："
                             + spec.secondary_curve_name)
        for group in _SECONDARY_GROUPS:
            if c.objExists(group):
                marker = group + ".advPyBendyGuideOwner"
                if (not c.objExists(marker)
                        or c.getAttr(marker) != _OWNER):
                    raise ValueError("Bendy 第二曲线组不属于当前构建："
                                     + group)

    def create_fit_bendy_secondary(self,
                                   spec: FitBendyChainSpec) -> None:
        """A three-influence follow curve positions interior Bend controls."""
        if spec.control_count == 1:
            return
        self._require_transaction()
        c = self._cmds
        for group in _SECONDARY_GROUPS:
            if c.objExists(group):
                continue
            node = c.createNode("transform", name=group,
                                parent=_GROUPS[0], skipSelect=True)
            c.addAttr(node, longName="advPyBendyGuideOwner",
                      dataType="string")
            c.setAttr(node + ".advPyBendyGuideOwner", _OWNER,
                      type="string", lock=True)
        curve = c.curve(name=spec.secondary_curve_name, degree=1,
                        point=(spec.start_position, spec.end_position))
        c.rebuildCurve(curve, ch=False, rpo=True, rt=0, end=1,
                       kr=0, kcp=False, kep=False, kt=False,
                       s=2, d=3, tol=0.01)
        curve = c.parent(curve, _SECONDARY_GROUPS[0])[0]
        shapes = c.listRelatives(curve, shapes=True,
                                 fullPath=True) or []
        if len(shapes) != 1:
            raise RuntimeError("Bendy 第二曲线形状数量不正确")
        child_output = (spec.child_start_control.replace(
            "Bend", "BendX", 1) if spec.child_start_control else None)
        child_driver = (child_output
                        if child_output and c.objExists(child_output)
                        and _bendy_parent_name(c, child_output)
                        == spec.child_start_control else
                        spec.child_start_control)
        drivers = ((spec.control_names[1]
                    if spec.legacy_twist_outputs else
                    spec.twist_projection_names[1][0]),
                   (spec.control_names[0]
                    if spec.legacy_twist_outputs else
                    spec.twist_projection_names[0][0]),
                   child_driver or spec.end_proxy_name)
        positions = (spec.start_position, spec.master_position,
                     spec.end_position)
        influences = []
        for index, (name, position, driver) in enumerate(zip(
                spec.secondary_influence_names, positions, drivers)):
            joint = c.createNode("joint", name=name,
                                 parent=_SECONDARY_GROUPS[1],
                                 skipSelect=True)
            c.xform(joint, worldSpace=True, translation=position)
            c.setAttr(joint + ".drawStyle", 2)
            if index == 2 and spec.child_start_control:
                translate_name, rotate_name, world_name = (
                    spec.secondary_end_matrix_names)
                translation = c.createNode("pickMatrix",
                                           name=translate_name)
                rotation = c.createNode("pickMatrix", name=rotate_name)
                world = c.createNode("multMatrix", name=world_name)
                c.connectAttr(driver + ".worldMatrix[0]",
                              translation + ".inputMatrix")
                parent_frame = (spec.parent_untwist_names[3]
                                if c.objExists(spec.parent_untwist_names[3])
                                else spec.follow_node_names[0])
                c.connectAttr(parent_frame + ".worldMatrix[0]",
                              rotation + ".inputMatrix")
                for attribute in ("useRotate", "useScale", "useShear"):
                    c.setAttr(translation + "." + attribute, False)
                for attribute in ("useTranslate", "useScale", "useShear"):
                    c.setAttr(rotation + "." + attribute, False)
                c.connectAttr(rotation + ".outputMatrix",
                              world + ".matrixIn[0]")
                c.connectAttr(translation + ".outputMatrix",
                              world + ".matrixIn[1]")
                c.connectAttr(joint + ".parentInverseMatrix[0]",
                              world + ".matrixIn[2]")
                c.setAttr(joint + ".translate", 0, 0, 0)
                c.setAttr(joint + ".rotate", 0, 0, 0)
                c.connectAttr(world + ".matrixSum",
                              joint + ".offsetParentMatrix")
                actual = c.xform(joint, query=True, worldSpace=True,
                                 translation=True)
                if any(abs(float(a) - b) > 1e-4
                       for a, b in zip(actual, position)):
                    raise RuntimeError("Bendy 第二曲线末端绑定位置不一致："
                                       + joint)
            else:
                c.parentConstraint(driver, joint, maintainOffset=False,
                                   name="AdvPy_Bend2Guide" + name)
            influences.append(joint)
        skin = c.skinCluster(*(influences + [curve]),
                             name=spec.secondary_skin_name,
                             maximumInfluences=2,
                             normalizeWeights=1,
                             toSelectedBones=True)[0]
        if int(c.getAttr(shapes[0] + ".controlPoints", size=True)) != 5:
            raise RuntimeError("Bendy 第二曲线 CV 数量不正确")
        for index in range(5):
            joint = (influences[0] if index <= 1
                     else influences[1] if index == 2
                     else influences[2])
            c.skinPercent(skin, curve + f".cv[{index}]",
                          transformValue=[(joint, 1.0)])
        for index in (1, 3):
            c.skinPercent(skin, curve + f".cv[{index}]",
                          transformValue=[(influences[1], 0.4)])
        c.setAttr(shapes[0] + ".visibility", False)
        for index, (path_name, transform_name, control) in enumerate(zip(
                spec.secondary_motion_path_names,
                spec.secondary_motion_transform_names,
                spec.control_names[2:]), start=1):
            path = c.createNode("motionPath", name=path_name,
                                skipSelect=True)
            transform = c.createNode("transform", name=transform_name,
                                     parent=_SECONDARY_GROUPS[2],
                                     skipSelect=True)
            c.connectAttr(spec.control_names[0] + ".parametric",
                          path + ".fractionMode")
            c.setAttr(path + ".follow", True)
            c.setAttr(path + ".worldUpType", 2)
            c.setAttr(path + ".frontAxis", 0)
            c.setAttr(path + ".upAxis", 1)
            position = tuple(c.xform(control, query=True,
                                     worldSpace=True, translation=True))
            self._set_bendy_motion_parameter(path,
                self._bendy_bind_parameter(shapes[0], position))
            up_control = (spec.control_names[0]
                          if spec.legacy_twist_outputs else
                          spec.twist_projection_names[0][0])
            c.connectAttr(up_control + ".worldMatrix[0]",
                          path + ".worldUpMatrix")
            c.connectAttr(shapes[0] + ".worldSpace[0]",
                          path + ".geometryPath")
            c.connectAttr(path + ".allCoordinates",
                          transform + ".translate")
            c.connectAttr(path + ".rotate", transform + ".rotate")
            follow = f"AdvPy_{control}Follow"
            c.delete(follow)
            c.parentConstraint(transform, control + "Offset",
                               maintainOffset=True, name=follow)
        self._transaction_changed = True

    def capture_fit_bendy_secondary(self,
                                     spec: FitBendyChainSpec) -> bool:
        if spec.control_count == 1:
            return True
        c = self._cmds
        curves = c.ls(spec.secondary_curve_name, long=True,
                      type="transform") or []
        if len(curves) != 1:
            return False
        shapes = c.listRelatives(curves[0], shapes=True,
                                 fullPath=True) or []
        if (len(shapes) != 1 or c.nodeType(shapes[0]) != "nurbsCurve"
                or not c.objExists(spec.secondary_skin_name)
                or c.nodeType(spec.secondary_skin_name) != "skinCluster"):
            return False
        influences = c.skinCluster(spec.secondary_skin_name, query=True,
                                   influence=True) or []
        if {name.rsplit("|", 1)[-1] for name in influences} != set(
                spec.secondary_influence_names):
            return False
        drivers = ((spec.control_names[1]
                    if spec.legacy_twist_outputs else
                    spec.twist_projection_names[1][0]),
                   (spec.control_names[0]
                    if spec.legacy_twist_outputs else
                    spec.twist_projection_names[0][0]))
        for name, driver in zip(spec.secondary_influence_names[:2], drivers):
            constraint = "AdvPy_Bend2Guide" + name
            targets = (c.parentConstraint(
                constraint, query=True, targetList=True) or []
                if c.objExists(constraint) else [])
            if (len(targets) != 1
                    or _bendy_dag_name(targets[0]) != driver):
                return False
        end = spec.secondary_influence_names[-1]
        if spec.child_start_control:
            translation, rotation, world = spec.secondary_end_matrix_names
            child_output = spec.child_start_control.replace(
                "Bend", "BendX", 1)
            child_driver = (child_output
                            if c.objExists(child_output)
                            and _bendy_parent_name(c, child_output)
                            == spec.child_start_control else
                            spec.child_start_control)
            if (not c.objExists(translation)
                    or c.nodeType(translation) != "pickMatrix"
                    or not c.objExists(rotation)
                    or c.nodeType(rotation) != "pickMatrix"
                    or not c.objExists(world)
                    or c.nodeType(world) != "multMatrix"
                    or c.connectionInfo(translation + ".inputMatrix",
                                        sourceFromDestination=True)
                    != child_driver + ".worldMatrix[0]"
                    or c.connectionInfo(rotation + ".inputMatrix",
                                        sourceFromDestination=True)
                    != ((spec.parent_untwist_names[3]
                         if c.objExists(spec.parent_untwist_names[3])
                         else spec.follow_node_names[0])
                        + ".worldMatrix[0]")
                    or c.connectionInfo(world + ".matrixIn[0]",
                                        sourceFromDestination=True)
                    != rotation + ".outputMatrix"
                    or c.connectionInfo(world + ".matrixIn[1]",
                                        sourceFromDestination=True)
                    != translation + ".outputMatrix"
                    or c.connectionInfo(world + ".matrixIn[2]",
                                        sourceFromDestination=True)
                    != end + ".parentInverseMatrix[0]"
                    or c.connectionInfo(end + ".offsetParentMatrix",
                                        sourceFromDestination=True)
                    != world + ".matrixSum"):
                return False
            for node, disabled in ((translation, ("useRotate", "useScale",
                                                  "useShear")),
                                   (rotation, ("useTranslate", "useScale",
                                               "useShear"))):
                if any(c.getAttr(node + "." + attribute)
                       for attribute in disabled):
                    return False
        else:
            constraint = "AdvPy_Bend2Guide" + end
            targets = (c.parentConstraint(
                constraint, query=True, targetList=True) or []
                if c.objExists(constraint) else [])
            if (len(targets) != 1
                    or _bendy_dag_name(targets[0])
                    != spec.end_proxy_name):
                return False
        for index, (path, transform, control) in enumerate(zip(
                spec.secondary_motion_path_names,
                spec.secondary_motion_transform_names,
                spec.control_names[2:]), start=1):
            follow = f"AdvPy_{control}Follow"
            if (not c.objExists(path) or c.nodeType(path) != "motionPath"
                    or not c.objExists(transform)
                    or c.connectionInfo(path + ".geometryPath",
                                        sourceFromDestination=True)
                    != shapes[0] + ".worldSpace[0]"
                    or c.connectionInfo(transform + ".translate",
                                        sourceFromDestination=True)
                    != path + ".allCoordinates"
                    or c.connectionInfo(transform + ".rotate",
                                        sourceFromDestination=True)
                    != path + ".rotate"
                    or c.connectionInfo(path + ".fractionMode",
                                        sourceFromDestination=True)
                    != spec.control_names[0] + ".parametric"
                    or c.connectionInfo(path + ".worldUpMatrix",
                                        sourceFromDestination=True)
                    != ((spec.control_names[0]
                         if spec.legacy_twist_outputs else
                         spec.twist_projection_names[0][0])
                        + ".worldMatrix[0]")
                    or not c.objExists(follow)
                    or c.nodeType(follow) != "parentConstraint"
                    or not self._bendy_motion_parameter_matches(path)):
                return False
        return True

    def preflight_fit_bendy_deform(self, spec: FitBendyChainSpec) -> None:
        c = self._cmds
        for index, (name, output, constraint, scale_pick,
                    scale_mult, micro_scale_names) in enumerate(zip(
                spec.deform_names, spec.micro_output_names,
                spec.deform_constraint_names,
                spec.deform_scale_pick_names,
                spec.deform_scale_mult_names,
                spec.deform_micro_scale_names)):
            joints = c.ls(name, long=True, type="joint") or []
            drivers = c.ls(output, long=True, type="transform") or []
            if len(joints) != 1 or len(drivers) != 1:
                raise ValueError("Bendy 变形关节或 Micro 输出不唯一：" + name)
            marker = ("advPySourceJoint" if index == 0
                      else "advPyAuxiliaryInfluenceKind")
            if not c.objExists(joints[0] + "." + marker):
                raise ValueError("Bendy 变形关节不属于当前角色：" + name)
            if index and c.getAttr(joints[0] + "." + marker) != "fit-part-v1":
                raise ValueError("Bendy 需要 Twist Part 关节：" + name)
            if (c.objExists(constraint) or c.objExists(scale_pick)
                    or c.objExists(scale_mult)
                    or (spec.micro_local_scale and any(
                        c.objExists(node) for node in micro_scale_names))):
                raise ValueError("Bendy 变形节点名称已占用：" + name)
            if c.listConnections(joints[0], type="skinCluster"):
                raise ValueError("Bendy 接管必须在 Skin 绑定前执行：" + name)

    def connect_fit_bendy_deform(self, spec: FitBendyChainSpec) -> None:
        self._require_transaction()
        c = self._cmds
        poses = {}
        for (name, output, offset, constraint, scale_pick,
             scale_mult_name, micro_scale_names) in zip(
                spec.deform_names, spec.micro_output_names,
                spec.micro_offset_names,
                spec.deform_constraint_names,
                spec.deform_scale_pick_names,
                spec.deform_scale_mult_names,
                spec.deform_micro_scale_names):
            joint = (c.ls(name, long=True, type="joint") or [])[0]
            poses[name] = tuple(float(value) for value in c.xform(
                joint, query=True, worldSpace=True, matrix=True))
            scale_value = c.getAttr(joint + ".scale")[0]
            scale_source = c.connectionInfo(joint + ".scale",
                                            sourceFromDestination=True)
            if scale_source:
                c.disconnectAttr(scale_source, joint + ".scale")
            scale_mult = c.createNode("multiplyDivide",
                                      name=scale_mult_name)
            if scale_source:
                c.connectAttr(scale_source, scale_mult + ".input1")
            else:
                for axis, value in zip("XYZ", scale_value):
                    destination = joint + ".scale" + axis
                    source = c.connectionInfo(destination,
                                              sourceFromDestination=True)
                    if source:
                        c.disconnectAttr(source, destination)
                        c.connectAttr(source,
                                      scale_mult + ".input1" + axis)
                    else:
                        c.setAttr(scale_mult + ".input1" + axis,
                                  float(value))
            if spec.micro_local_scale:
                relative_name, decompose_name, combine_name = (
                    micro_scale_names)
                relative = c.createNode(
                    "multMatrix", name=relative_name,
                    skipSelect=True)
                decompose = c.createNode(
                    "decomposeMatrix", name=decompose_name,
                    skipSelect=True)
                combine = c.createNode(
                    "multiplyDivide", name=combine_name,
                    skipSelect=True)
                c.connectAttr(output + ".worldMatrix[0]",
                              relative + ".matrixIn[0]")
                c.connectAttr(offset + ".worldInverseMatrix[0]",
                              relative + ".matrixIn[1]")
                c.connectAttr(relative + ".matrixSum",
                              decompose + ".inputMatrix")
                c.connectAttr(offset + ".scale",
                              combine + ".input1")
                c.connectAttr(decompose + ".outputScale",
                              combine + ".input2")
                c.connectAttr(combine + ".output",
                              scale_mult + ".input2")
            else:
                c.connectAttr(offset + ".scale",
                              scale_mult + ".input2")
            c.connectAttr(scale_mult + ".output", joint + ".scale")
            for attribute in ("translate", "rotate", "offsetParentMatrix"):
                destination = joint + "." + attribute
                source = c.connectionInfo(destination,
                                          sourceFromDestination=True)
                old_matrix = (c.getAttr(destination)
                              if attribute == "offsetParentMatrix" else None)
                if source:
                    c.disconnectAttr(source, destination)
                if attribute == "offsetParentMatrix":
                    pick = c.createNode("pickMatrix", name=scale_pick)
                    c.setAttr(pick + ".useTranslate", False)
                    c.setAttr(pick + ".useRotate", False)
                    c.setAttr(pick + ".useShear", False)
                    if source:
                        c.connectAttr(source, pick + ".inputMatrix")
                    else:
                        if old_matrix and isinstance(old_matrix[0],
                                                     (tuple, list)):
                            old_matrix = old_matrix[0]
                        c.setAttr(pick + ".inputMatrix", *old_matrix,
                                  type="matrix")
                    c.connectAttr(pick + ".outputMatrix", destination)
                    continue
                for axis in "XYZ":
                    destination = joint + "." + attribute + axis
                    source = c.connectionInfo(destination,
                                              sourceFromDestination=True)
                    if source:
                        c.disconnectAttr(source, destination)
            c.xform(joint, worldSpace=True, matrix=poses[name])
            driver = (c.ls(output, long=True, type="transform") or [])[0]
            c.parentConstraint(driver, joint, maintainOffset=True,
                               name=constraint)
            after = c.xform(joint, query=True, worldSpace=True, matrix=True)
            if any(abs(a - float(b)) > 1e-3
                   for a, b in zip(poses[name], after)):
                raise RuntimeError("Bendy 接管改变绑定姿态：" + name)
        self._transaction_changed = True

    def capture_fit_bendy_deform(self, spec: FitBendyChainSpec) -> bool:
        c = self._cmds
        for (name, output, offset, constraint, scale_pick,
             scale_mult, micro_scale_names) in zip(
                spec.deform_names, spec.micro_output_names,
                spec.micro_offset_names,
                spec.deform_constraint_names,
                spec.deform_scale_pick_names,
                spec.deform_scale_mult_names,
                spec.deform_micro_scale_names):
            joints = c.ls(name, long=True, type="joint") or []
            drivers = c.ls(output, long=True, type="transform") or []
            if (len(joints) != 1 or len(drivers) != 1
                    or not c.objExists(constraint)
                    or c.nodeType(constraint) != "parentConstraint"
                    or not c.objExists(scale_pick)
                    or c.nodeType(scale_pick) != "pickMatrix"
                    or c.connectionInfo(joints[0] + ".offsetParentMatrix",
                                        sourceFromDestination=True)
                    != scale_pick + ".outputMatrix"
                    or not c.objExists(scale_mult)
                    or c.nodeType(scale_mult) != "multiplyDivide"
                    or c.connectionInfo(joints[0] + ".scale",
                                        sourceFromDestination=True)
                    != scale_mult + ".output"
                    or c.connectionInfo(scale_mult + ".input2",
                                        sourceFromDestination=True)
                    != ((micro_scale_names[2] + ".output")
                        if spec.micro_local_scale else
                        offset + ".scale")):
                return False
            if spec.micro_local_scale:
                relative, decompose, combine = micro_scale_names
                if (not c.objExists(relative)
                        or c.nodeType(relative) != "multMatrix"
                        or not c.objExists(decompose)
                        or c.nodeType(decompose) != "decomposeMatrix"
                        or not c.objExists(combine)
                        or c.nodeType(combine) != "multiplyDivide"
                        or c.connectionInfo(relative + ".matrixIn[0]",
                                            sourceFromDestination=True)
                        != output + ".worldMatrix[0]"
                        or c.connectionInfo(relative + ".matrixIn[1]",
                                            sourceFromDestination=True)
                        != offset + ".worldInverseMatrix[0]"
                        or c.connectionInfo(decompose + ".inputMatrix",
                                            sourceFromDestination=True)
                        != relative + ".matrixSum"
                        or c.connectionInfo(combine + ".input1",
                                            sourceFromDestination=True)
                        != offset + ".scale"
                        or c.connectionInfo(combine + ".input2",
                                            sourceFromDestination=True)
                        != decompose + ".outputScale"):
                    return False
            targets = c.parentConstraint(constraint, query=True,
                                         targetList=True) or []
            if len(targets) != 1 or targets[0].rsplit("|", 1)[-1] != output:
                return False
            for attribute in ("translate", "rotate"):
                for axis in "XYZ":
                    destination = joints[0] + "." + attribute + axis
                    source = c.connectionInfo(destination,
                                              sourceFromDestination=True)
                    if not source or source.rsplit("|", 1)[-1].split(".")[0] != constraint:
                        return False
        return True

    def preflight_fit_bendy_fk_scale(
        self, spec: FitBendyFkScaleSpec,
    ) -> None:
        c = self._cmds
        if ((c.ls(spec.body_joint, long=True, type="joint") or [])
                != [spec.body_joint]
                or (c.ls(spec.control_path, long=True,
                         type="transform") or [])
                != [spec.control_path]
                or not c.objExists(spec.bendy_scale_name)
                or c.nodeType(spec.bendy_scale_name) != "multiplyDivide"
                or c.objExists(spec.multiply_name)
                or c.connectionInfo(spec.body_joint + ".scale",
                                    sourceFromDestination=True)
                != spec.bendy_scale_name + ".output"):
            raise ValueError("通用 Bendy FK 缩放的 Body 或来源无效："
                             + spec.body_joint)

    def connect_fit_bendy_fk_scale(
        self, spec: FitBendyFkScaleSpec,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        node = c.createNode("multiplyDivide", name=spec.multiply_name,
                            skipSelect=True)
        c.setAttr(node + ".operation", 1)
        c.disconnectAttr(spec.bendy_scale_name + ".output",
                         spec.body_joint + ".scale")
        c.connectAttr(spec.bendy_scale_name + ".output",
                      node + ".input1")
        c.connectAttr(spec.control_path + ".scale",
                      node + ".input2")
        c.connectAttr(node + ".output", spec.body_joint + ".scale")
        self._transaction_changed = True

    def capture_fit_bendy_fk_scale(
        self, spec: FitBendyFkScaleSpec,
    ) -> bool:
        c = self._cmds
        node = spec.multiply_name
        return (c.objExists(node)
                and c.nodeType(node) == "multiplyDivide"
                and int(c.getAttr(node + ".operation")) == 1
                and c.connectionInfo(node + ".input1",
                                     sourceFromDestination=True)
                == spec.bendy_scale_name + ".output"
                and c.connectionInfo(node + ".input2",
                                     sourceFromDestination=True)
                == spec.control_path + ".scale"
                and c.connectionInfo(spec.body_joint + ".scale",
                                     sourceFromDestination=True)
                == node + ".output")

    def preflight_fit_bendy_micro(self, spec: FitBendyChainSpec) -> None:
        c = self._cmds
        if any(c.objExists(name) for name in spec.micro_node_names):
            raise ValueError("Bendy 微控制节点名称已占用：" + spec.curve_name)
        if (spec.micro_matrix_aim
                and "aimMatrix" not in (c.allNodeTypes() or [])):
            raise ValueError("Bendy 微控制朝向需要 aimMatrix 节点")
        if c.objExists(_MICRO_GROUP):
            marker = _MICRO_GROUP + ".advPyBendyGuideOwner"
            if not c.objExists(marker) or c.getAttr(marker) != _OWNER:
                raise ValueError("Bendy 微控制组不属于当前构建")

    def preflight_fit_bendy_follow(
            self, spec: "FitBendyFollowSpec",
            planned_sources: frozenset[str] = frozenset()) -> None:
        c = self._cmds
        if any(c.objExists(name) for name in spec.node_names):
            raise ValueError("Bendy 跟随节点名称已占用：" + spec.chain.curve_name)
        if (spec.master_aim_follow
                and "aimMatrix" not in (c.allNodeTypes() or [])):
            raise ValueError("Bendy 主控制跟随需要 aimMatrix 节点")
        if spec.untwist_plug and not c.objExists(spec.untwist_plug):
            raise ValueError("Bendy 去扭转来源不存在："
                             + spec.untwist_plug)
        if spec.up_twist_plug and not c.objExists(spec.up_twist_plug):
            raise ValueError("Bendy 上行扭转来源不存在："
                             + spec.up_twist_plug)
        for source in (spec.start, spec.end):
            for plug in (source.fk_matrix, source.ik_matrix, source.blend_plug):
                if (plug is not None and not c.objExists(plug)
                        and plug not in planned_sources):
                    raise ValueError("Bendy 独立驱动插口不存在：" + plug)

    def preflight_fit_bendy_guides(
        self, spec: FitBendyChainSpec
    ) -> None:
        c = self._cmds
        if any(c.objExists(name) for name in spec.guide_node_names):
            raise ValueError("Bendy 节点名称已占用：" + spec.curve_name)
        for group in _GROUPS:
            if c.objExists(group):
                marker = group + ".advPyBendyGuideOwner"
                if (not c.objExists(marker)
                        or c.getAttr(marker) != _OWNER):
                    raise ValueError("Bendy 系统组不属于当前构建：" + group)
        for name in (spec.start_body, spec.end_body):
            matches = c.ls(name, long=True, type="joint") or []
            if matches != [name]:
                raise ValueError("Bendy 两端 Body 不唯一：" + name)

    def _ensure_fit_bendy_groups(self) -> None:
        c = self._cmds
        for index, group in enumerate(_GROUPS):
            if c.objExists(group):
                continue
            parent = (_GROUPS[0] if index else
                      "|Group|MotionSystem|BendSystem"
                      if c.objExists("|Group|MotionSystem|BendSystem")
                      else None)
            options = {"parent": parent} if parent else {}
            node = c.createNode("transform", name=group,
                                skipSelect=True, **options)
            c.addAttr(node, longName="advPyBendyGuideOwner",
                      dataType="string")
            c.setAttr(node + ".advPyBendyGuideOwner", _OWNER,
                      type="string", lock=True)
            if index == 2 and c.objExists(
                    "MainScaleMultiplyDivide.output"):
                c.connectAttr("MainScaleMultiplyDivide.output",
                              node + ".scale")
            self._transaction_changed = True

    def create_fit_bendy_guides(
        self, spec: FitBendyChainSpec
    ) -> None:
        self._require_transaction()
        c = self._cmds
        self._ensure_fit_bendy_groups()
        axis_offset = original_fit_icon_axis_offset(
            c, (spec.source_joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1],))
        start, end = spec.start_position, spec.end_position
        curve = c.curve(name=spec.curve_name, degree=1,
                        point=(start, end))
        c.rebuildCurve(curve, ch=False, rpo=True, rt=0, end=1,
                       kr=0, kcp=False, kep=False, kt=False,
                       s=spec.control_count + 1, d=3, tol=0.01)
        curve = c.parent(curve, _GROUPS[1])[0]
        curve = (c.ls(curve, long=True) or [curve])[0]
        shapes = c.listRelatives(curve, shapes=True,
                                 fullPath=True) or []
        if len(shapes) != 1:
            raise RuntimeError("Bendy 曲线形状数量不正确")
        c.setAttr(shapes[0] + ".overrideEnabled", True)
        c.setAttr(shapes[0] + ".overrideDisplayType", 1)

        positions = (start, *spec.control_positions[1:], end)
        controls = []
        for index, (name, position) in enumerate(zip(
                spec.control_names, (spec.master_position,
                                     *spec.control_positions))):
            parent = (spec.control_names[0]
                      if index == 2 and spec.legacy_simple_control
                      else _GROUPS[0])
            if index == 0:
                control = c.curve(
                    name=name, degree=1,
                    point=tuple((x * spec.master_icon_scale, 0,
                                 z * spec.master_icon_scale)
                                for x, z in _MASTER_BEND_PROFILE_XZ))
                shape = (c.listRelatives(control, shapes=True) or [])[0]
                c.setAttr(shape + ".overrideEnabled", True)
                c.setAttr(shape + ".overrideColor", 29)
            else:
                control = create_adv_icon(
                    c, name=name, parent=parent, template="Bend_icon",
                    radius=spec.master_icon_scale,
                    fallback_normal=(1.0, 0.0, 0.0),
                    axis_offset=axis_offset, mirror_left=spec.side == "L")
                if index == 1:
                    c.move(spec.start_icon_offset, 0, 0,
                           control + ".cv[0:99]", relative=True,
                           objectSpace=True, worldSpaceDistance=True)
            if index == 0:
                control = c.parent(control, parent)[0]
            self._align_bendy_control(
                control, position, spec.start_world_axes)
            c.setAttr(control + ".rotateOrder", spec.rotation_order)
            if index == 0:
                c.addAttr(control, longName="parametric",
                          attributeType="bool", defaultValue=True,
                          keyable=False)
                c.setAttr(control + ".parametric", channelBox=True)
            controls.append((c.ls(control, long=True) or [control])[0])
        for control, projection in zip(
                controls, spec.twist_projection_names):
            c.createNode("transform", name=projection[0],
                         parent=control, skipSelect=True)
        if spec.simple_proxy_layout:
            middle = c.createNode(
                "transform", name=spec.simple_proxy_name,
                parent=controls[0], skipSelect=True)
            self._align_bendy_control(
                middle, spec.control_positions[1],
                spec.start_world_axes)
            c.setAttr(middle + ".rotateOrder", spec.rotation_order)
        if spec.parent_bendy:
            junction_offset = c.createNode(
                "transform", name=spec.junction_offset_name,
                parent=controls[1], skipSelect=True)
            c.setAttr(junction_offset + ".rotateOrder",
                      spec.rotation_order)
            c.xform(junction_offset, worldSpace=True,
                    translation=start)
            junction_extra = c.createNode(
                "transform", name=spec.junction_extra_name,
                parent=junction_offset, skipSelect=True)
            c.setAttr(junction_extra + ".rotateOrder",
                      spec.rotation_order)
            junction = create_adv_icon(
                c, name=spec.junction_name, parent=junction_extra,
                template="BendMid_icon",
                radius=spec.master_icon_scale,
                fallback_normal=(1.0, 0.0, 0.0),
                axis_offset=axis_offset, mirror_left=spec.side == "L")
            c.xform(junction, worldSpace=True, translation=start)
            c.setAttr(junction + ".rotateOrder", spec.rotation_order)
            c.addAttr(junction, longName="circular",
                      attributeType="double", softMinValue=0.0,
                      softMaxValue=10.0, defaultValue=0.0,
                      keyable=True)
            c.createNode("transform", name=spec.junction_output_name,
                         parent=junction, skipSelect=True)
        end_proxy = c.createNode("transform", name=spec.end_proxy_name,
                                 parent=_GROUPS[0], skipSelect=True)
        self._align_bendy_control(
            end_proxy, end, spec.start_world_axes)
        bend_drivers = (controls if spec.legacy_twist_outputs else
                        tuple(row[0] for row in
                              spec.twist_projection_names))
        drivers = ((spec.junction_output_name if spec.parent_bendy
                    else bend_drivers[1]),
                   *((spec.simple_proxy_name,) if spec.simple_proxy_layout
                     else bend_drivers[2:]),
                   end_proxy)
        influences = []
        for name, position, driver in zip(
                spec.influence_names, positions, drivers):
            joint = c.createNode("joint", name=name, parent=_GROUPS[2],
                                 skipSelect=True)
            c.xform(joint, worldSpace=True, translation=position)
            c.setAttr(joint + ".drawStyle", 2)
            c.parentConstraint(driver, joint, maintainOffset=False,
                               name="AdvPy_BendGuide" + name)
            influences.append(joint)
        skin = c.skinCluster(*(influences + [curve]),
                             name=spec.skin_name,
                             maximumInfluences=2,
                             normalizeWeights=1,
                             toSelectedBones=True)[0]
        cv_count = int(c.getAttr(shapes[0] + ".controlPoints",
                                 size=True))
        if cv_count < len(influences) + 1:
            raise RuntimeError("Bendy 曲线控制点不足")
        if cv_count != spec.control_count + 4:
            raise RuntimeError("Bendy 曲线 CV 数量与原版重建规则不一致")
        for index in range(cv_count):
            c.skinPercent(skin, curve + f".cv[{index}]",
                          transformValue=[(influences[0], 1.0)])
        for index in (cv_count - 2, cv_count - 1):
            c.skinPercent(skin, curve + f".cv[{index}]",
                          transformValue=[(influences[-1], 1.0)])
        for index, joint in enumerate(influences[1:-1], start=1):
            c.skinPercent(skin, curve + f".cv[{index + 1}]",
                          transformValue=[(joint, 1.0)])
        c.skinPercent(skin, curve + ".cv[1]",
                      transformValue=[(influences[1], 0.4)])
        c.skinPercent(skin, curve + f".cv[{cv_count - 2}]",
                      transformValue=[(influences[-2], 0.4)])
        for path_name, transform_name, position in zip(
                spec.motion_path_names,
                spec.motion_transform_names,
                (spec.start_position, *spec.part_positions)):
            path = c.createNode("motionPath", name=path_name,
                                skipSelect=True)
            transform = c.createNode("transform", name=transform_name,
                                     parent=_GROUPS[3], skipSelect=True)
            c.connectAttr(spec.control_names[0] + ".parametric",
                          path + ".fractionMode")
            self._set_bendy_motion_parameter(path,
                self._bendy_bind_parameter(shapes[0], position))
            c.connectAttr(shapes[0] + ".worldSpace[0]",
                          path + ".geometryPath")
            c.connectAttr(path + ".allCoordinates",
                          transform + ".translate")
        self._transaction_changed = True

    def create_fit_bendy_follow(self, spec: "FitBendyFollowSpec") -> None:
        """Keep animator channels free while the guide follows independent Rig."""
        self._require_transaction()
        c = self._cmds
        chain = spec.chain
        names = chain.follow_node_names
        start_proxy, end_proxy = names[:2]

        def source_proxy(name: str, world_name: str, blend_name: str,
                         source: "FitBendyWorldSource") -> None:
            proxy = c.createNode("transform", name=name,
                                 parent=_GROUPS[0], skipSelect=True)
            matrix = source.fk_matrix
            if source.ik_matrix is not None:
                blend = c.createNode("blendMatrix", name=blend_name,
                                     skipSelect=True)
                c.connectAttr(source.fk_matrix, blend + ".inputMatrix")
                c.connectAttr(source.ik_matrix,
                              blend + ".target[0].targetMatrix")
                c.connectAttr(source.blend_plug,
                              blend + ".target[0].weight")
                matrix = blend + ".outputMatrix"
            world = c.createNode("multMatrix", name=world_name,
                                 skipSelect=True)
            c.connectAttr(matrix, world + ".matrixIn[0]")
            c.connectAttr(proxy + ".parentInverseMatrix[0]",
                          world + ".matrixIn[1]")
            c.connectAttr(world + ".matrixSum",
                          proxy + ".offsetParentMatrix")

        source_proxy(start_proxy, names[2], names[4], spec.start)
        source_proxy(end_proxy, names[3], names[5], spec.end)
        parent_proxy = (self._create_fit_bendy_parent_untwist(
            chain, start_proxy, spec.untwist_plug)
            if spec.untwist_plug else start_proxy)
        for index, control in enumerate(chain.control_names):
            position = (chain.master_position if index == 0
                        else chain.control_positions[index - 1])
            offset = c.createNode("transform", name=control + "Offset",
                                  parent=_GROUPS[0], skipSelect=True)
            self._align_bendy_control(
                offset, position, chain.start_world_axes)
            c.setAttr(offset + ".rotateOrder", chain.rotation_order)
            if index == 0 and chain.start_world_axes is not None:
                c.addAttr(offset, longName="advPyBendyOrientedBind",
                          attributeType="bool", defaultValue=True)
                c.setAttr(offset + ".advPyBendyOrientedBind",
                          lock=True)
            extra = c.createNode("transform", name=control + "Extra",
                                  parent=offset, skipSelect=True)
            c.setAttr(extra + ".rotateOrder", chain.rotation_order)
            c.parent(control, extra, absolute=True)
            if index == 0 and spec.master_aim_follow:
                self._create_fit_bendy_master_aim_follow(
                    chain, offset, start_proxy, end_proxy,
                    parent_proxy, spec.start_control_blend)
                continue
            targets = ((chain.control_names[0],)
                       if chain.legacy_simple_control and index == 2 else
                       (parent_proxy, end_proxy) if index == 0
                       or index > 1 else (parent_proxy,))
            constraint = c.parentConstraint(
                *targets, offset, maintainOffset=True,
                name=f"AdvPy_{control}Follow")[0]
            if len(targets) == 2:
                fraction = (0.5 if index == 0
                            else (index - 1) / (chain.control_count + 1))
                weights = c.parentConstraint(
                    constraint, query=True, weightAliasList=True)
                if len(weights) != 2:
                    raise RuntimeError("Bendy 跟随约束权重数量不正确")
                c.setAttr(constraint + "." + weights[0], 1.0 - fraction)
                c.setAttr(constraint + "." + weights[1], fraction)
        if chain.child_start_influence or spec.end_matrix_follow:
            translate_name, rotate_name, world_name = (
                chain.end_follow_matrix_names)
            translation = c.createNode("pickMatrix",
                                       name=translate_name)
            rotation = c.createNode("pickMatrix", name=rotate_name)
            world = c.createNode("multMatrix", name=world_name)
            end_translation = (chain.child_start_influence
                               if chain.child_start_influence else end_proxy)
            c.connectAttr(end_translation + ".worldMatrix[0]",
                          translation + ".inputMatrix")
            c.connectAttr(parent_proxy + ".worldMatrix[0]",
                          rotation + ".inputMatrix")
            for attribute in ("useRotate", "useShear"):
                c.setAttr(translation + "." + attribute, False)
            if not chain.child_start_influence:
                c.setAttr(translation + ".useScale", False)
            for attribute in ("useTranslate", "useScale", "useShear"):
                c.setAttr(rotation + "." + attribute, False)
            c.connectAttr(rotation + ".outputMatrix",
                          world + ".matrixIn[0]")
            c.connectAttr(translation + ".outputMatrix",
                          world + ".matrixIn[1]")
            c.connectAttr(chain.end_proxy_name + ".parentInverseMatrix[0]",
                          world + ".matrixIn[2]")
            c.setAttr(chain.end_proxy_name + ".translate", 0, 0, 0)
            c.setAttr(chain.end_proxy_name + ".rotate", 0, 0, 0)
            c.connectAttr(world + ".matrixSum",
                          chain.end_proxy_name + ".offsetParentMatrix")
            actual = c.xform(chain.end_proxy_name, query=True,
                             worldSpace=True, translation=True)
            if any(abs(float(a) - b) > 1e-4 for a, b in zip(
                    actual, chain.end_position)):
                raise RuntimeError("Bendy 主曲线末端绑定位置不一致："
                                   + chain.end_proxy_name)
        else:
            c.parentConstraint(end_proxy, chain.end_proxy_name,
                               maintainOffset=True,
                               name=f"AdvPy_{chain.end_proxy_name}Follow")
        self._transaction_changed = True

    def _create_fit_bendy_parent_untwist(
            self, chain: FitBendyChainSpec, start_proxy: str,
            twist_plug: str) -> str:
        """Remove the source axial twist from the Bend parent frame."""
        c = self._cmds
        negate_name, compose_name, world_name, frame_name = (
            chain.parent_untwist_names)
        frame = c.createNode("transform", name=frame_name,
                             parent=_GROUPS[0], skipSelect=True)
        negate = c.createNode("multDoubleLinear", name=negate_name,
                              skipSelect=True)
        c.connectAttr(twist_plug, negate + ".input1")
        c.setAttr(negate + ".input2", -1.0)
        compose = c.createNode("composeMatrix", name=compose_name,
                               skipSelect=True)
        c.connectAttr(negate + ".output",
                      compose + ".inputRotateX")
        world = c.createNode("multMatrix", name=world_name,
                             skipSelect=True)
        c.connectAttr(compose + ".outputMatrix",
                      world + ".matrixIn[0]")
        c.connectAttr(start_proxy + ".worldMatrix[0]",
                      world + ".matrixIn[1]")
        c.connectAttr(frame + ".parentInverseMatrix[0]",
                      world + ".matrixIn[2]")
        c.connectAttr(world + ".matrixSum",
                      frame + ".offsetParentMatrix")
        c.setAttr(frame + ".visibility", False)
        position = c.xform(frame, query=True, worldSpace=True,
                           translation=True)
        if any(abs(float(actual) - expected) > 1e-4
               for actual, expected in zip(position,
                                           chain.start_position)):
            raise RuntimeError("Bendy 去扭转父级改变绑定位置："
                               + chain.curve_name)
        return frame

    def _create_fit_bendy_master_aim_follow(
            self, chain: FitBendyChainSpec, offset: str,
            start_proxy: str, end_proxy: str,
            parent_proxy: str,
            start_control_blend: bool) -> None:
        """Mirror MEL's translated blend and half-strength aimed BendOffset."""
        from maya.api import OpenMaya as om

        c = self._cmds
        (blend_name, translate_name, rotate_name, mix_name, aim_name,
         bind_name, world_name, pick_name) = chain.master_follow_matrix_names
        blend = c.createNode("blendMatrix", name=blend_name,
                             skipSelect=True)
        bend_start = ((chain.control_names[1]
                       if chain.legacy_twist_outputs else
                       chain.twist_projection_names[1][0])
                      if start_control_blend else start_proxy)
        c.connectAttr(bend_start + ".worldMatrix[0]",
                      blend + ".inputMatrix")
        c.connectAttr(end_proxy + ".worldMatrix[0]",
                      blend + ".target[0].targetMatrix")
        c.setAttr(blend + ".target[0].weight", 0.5)
        translate = c.createNode("pickMatrix", name=translate_name,
                                 skipSelect=True)
        c.connectAttr(blend + ".outputMatrix",
                      translate + ".inputMatrix")
        for attribute in ("useRotate", "useScale", "useShear"):
            c.setAttr(translate + "." + attribute, False)
        rotate = c.createNode("pickMatrix", name=rotate_name,
                              skipSelect=True)
        c.connectAttr(parent_proxy + ".worldMatrix[0]",
                      rotate + ".inputMatrix")
        for attribute in ("useTranslate", "useScale", "useShear"):
            c.setAttr(rotate + "." + attribute, False)
        mix = c.createNode("multMatrix", name=mix_name,
                           skipSelect=True)
        c.connectAttr(rotate + ".outputMatrix", mix + ".matrixIn[0]")
        c.connectAttr(translate + ".outputMatrix", mix + ".matrixIn[1]")
        aim = c.createNode("aimMatrix", name=aim_name,
                           skipSelect=True)
        side = chain.aim_axis_sign
        c.setAttr(aim + ".envelope", 0.5)
        c.setAttr(aim + ".primaryInputAxis", side, 0, 0)
        c.setAttr(aim + ".secondaryInputAxis", 0, 0, side)
        c.setAttr(aim + ".secondaryTargetVector", 0, 0, side)
        c.connectAttr(mix + ".matrixSum", aim + ".inputMatrix")
        c.connectAttr(end_proxy + ".worldMatrix[0]",
                      aim + ".primaryTargetMatrix")
        c.connectAttr(parent_proxy + ".worldMatrix[0]",
                      aim + ".secondaryTargetMatrix")
        rest = om.MMatrix(c.xform(
            offset, query=True, worldSpace=True, matrix=True))
        value = c.getAttr(aim + ".outputMatrix")
        if len(value) == 1 and isinstance(value[0], (tuple, list)):
            value = value[0]
        bind_offset = rest * om.MMatrix(value).inverse()
        bind = c.createNode("multMatrix", name=bind_name,
                            skipSelect=True)
        c.setAttr(bind + ".matrixIn[0]",
                  *(float(bind_offset[row][column])
                    for row in range(4) for column in range(4)),
                  type="matrix")
        c.connectAttr(aim + ".outputMatrix", bind + ".matrixIn[1]")
        world = c.createNode("multMatrix", name=world_name,
                             skipSelect=True)
        c.connectAttr(bind + ".matrixSum", world + ".matrixIn[0]")
        c.connectAttr(offset + ".parentInverseMatrix[0]",
                      world + ".matrixIn[1]")
        pick = c.createNode("pickMatrix", name=pick_name,
                            skipSelect=True)
        c.connectAttr(world + ".matrixSum", pick + ".inputMatrix")
        c.setAttr(pick + ".useScale", False)
        c.setAttr(pick + ".useShear", False)
        c.setAttr(offset + ".translate", 0, 0, 0)
        c.setAttr(offset + ".rotate", 0, 0, 0)
        c.setAttr(offset + ".scale", 1, 1, 1)
        c.setAttr(offset + ".shear", 0, 0, 0)
        c.connectAttr(pick + ".outputMatrix",
                      offset + ".offsetParentMatrix")
        current = c.xform(offset, query=True, worldSpace=True,
                          translation=True)
        expected = chain.master_position
        if any(abs(float(a) - b) > 1e-4
               for a, b in zip(current, expected)):
            raise RuntimeError("Bendy 主控制瞄准跟随改变绑定位置："
                               + chain.curve_name)

    def create_fit_bendy_circular(self,
                                   spec: FitBendyChainSpec) -> None:
        if not spec.has_master_circular:
            return
        self._require_transaction()
        c = self._cmds
        master = spec.control_names[0]
        circular = c.createNode("transform", name=spec.circular_name,
                                parent=master + "Offset", skipSelect=True)
        c.parent(master + "Extra", circular, absolute=True)
        if not spec.child_junction_control:
            self._transaction_changed = True
            return
        relative_name, angle_name, length_name, amount_name = (
            spec.circular_graph_names)
        relative = c.createNode("multMatrix", name=relative_name,
                                skipSelect=True)
        angle = c.createNode("decomposeMatrix", name=angle_name,
                             skipSelect=True)
        length = c.createNode("multDoubleLinear", name=length_name,
                              skipSelect=True)
        amount = c.createNode("multDoubleLinear", name=amount_name,
                              skipSelect=True)
        child_proxy = spec.child_source_proxy
        parent_proxy = spec.follow_node_names[0]
        c.connectAttr(child_proxy + ".worldMatrix[0]",
                      relative + ".matrixIn[0]")
        c.connectAttr(parent_proxy + ".worldInverseMatrix[0]",
                      relative + ".matrixIn[1]")
        c.connectAttr(relative + ".matrixSum",
                      angle + ".inputMatrix")
        c.connectAttr(angle + ".outputRotateZ",
                      length + ".input1")
        span = sum((a - b) ** 2 for a, b in zip(
            spec.start_position, spec.end_position)) ** 0.5
        c.setAttr(length + ".input2",
                  -0.000375 * span * (-1 if spec.side == "L" else 1))
        c.connectAttr(length + ".output", amount + ".input1")
        c.connectAttr(spec.child_junction_control + ".circular",
                      amount + ".input2")
        c.connectAttr(amount + ".output", circular + ".translateY")
        self._transaction_changed = True

    def capture_fit_bendy_circular(self,
                                    spec: FitBendyChainSpec) -> bool:
        if not spec.has_master_circular:
            return True
        c = self._cmds
        circular = spec.circular_name
        if not spec.child_junction_control:
            return (c.objExists(circular)
                    and c.nodeType(circular) == "transform"
                    and _bendy_parent_name(c, circular)
                    == spec.control_names[0] + "Offset"
                    and _bendy_parent_name(
                        c, spec.control_names[0] + "Extra") == circular)
        relative, angle, length, amount = spec.circular_graph_names
        return (c.objExists(circular)
                and c.nodeType(circular) == "transform"
                and _bendy_parent_name(c, circular)
                == spec.control_names[0] + "Offset"
                and _bendy_parent_name(
                    c, spec.control_names[0] + "Extra") == circular
                and c.objExists(relative)
                and c.nodeType(relative) == "multMatrix"
                and c.objExists(angle)
                and c.nodeType(angle) == "decomposeMatrix"
                and c.objExists(length)
                and c.nodeType(length) == "multDoubleLinear"
                and c.objExists(amount)
                and c.nodeType(amount) == "multDoubleLinear"
                and c.connectionInfo(relative + ".matrixIn[0]",
                                     sourceFromDestination=True)
                == spec.child_source_proxy + ".worldMatrix[0]"
                and c.connectionInfo(relative + ".matrixIn[1]",
                                     sourceFromDestination=True)
                == spec.follow_node_names[0] + ".worldInverseMatrix[0]"
                and c.connectionInfo(angle + ".inputMatrix",
                                     sourceFromDestination=True)
                == relative + ".matrixSum"
                and c.connectionInfo(length + ".input1",
                                     sourceFromDestination=True)
                == angle + ".outputRotateZ"
                and c.connectionInfo(amount + ".input1",
                                     sourceFromDestination=True)
                == length + ".output"
                and c.connectionInfo(amount + ".input2",
                                     sourceFromDestination=True)
                == spec.child_junction_control + ".circular"
                and c.connectionInfo(circular + ".translateY",
                                     sourceFromDestination=True)
                == amount + ".output")

    def capture_fit_bendy_follow(self, spec: "FitBendyFollowSpec") -> bool:
        c = self._cmds
        names = spec.chain.follow_node_names
        for proxy, world, source, blend in (
                (names[0], names[2], spec.start, names[4]),
                (names[1], names[3], spec.end, names[5])):
            if (not c.objExists(proxy) or c.nodeType(proxy) != "transform"
                    or not c.objExists(world)
                    or c.nodeType(world) != "multMatrix"
                    or c.connectionInfo(proxy + ".offsetParentMatrix",
                                        sourceFromDestination=True)
                    != world + ".matrixSum"):
                return False
            expected = source.fk_matrix
            if source.ik_matrix is not None:
                if (not c.objExists(blend) or c.nodeType(blend) != "blendMatrix"
                        or c.connectionInfo(blend + ".inputMatrix",
                                            sourceFromDestination=True)
                        != source.fk_matrix
                        or c.connectionInfo(blend + ".target[0].targetMatrix",
                                            sourceFromDestination=True)
                        != source.ik_matrix
                        or c.connectionInfo(blend + ".target[0].weight",
                                            sourceFromDestination=True)
                        != source.blend_plug):
                    return False
                expected = blend + ".outputMatrix"
            if c.connectionInfo(world + ".matrixIn[0]",
                                sourceFromDestination=True) != expected:
                return False
        parent_proxy = (spec.chain.parent_untwist_names[3]
                        if spec.untwist_plug else names[0])
        if (spec.untwist_plug
                and not self._capture_fit_bendy_parent_untwist(
                    spec.chain, names[0], spec.untwist_plug)):
            return False
        for index, control in enumerate(spec.chain.control_names):
            offset = control + "Offset"
            extra = control + "Extra"
            follow = f"AdvPy_{control}Follow"
            extra_parent = (spec.chain.circular_name
                            if control == spec.chain.control_names[0]
                            and spec.chain.has_master_circular else offset)
            if (not c.objExists(offset) or not c.objExists(extra)
                    or int(c.getAttr(offset + ".rotateOrder"))
                    != spec.chain.rotation_order
                    or int(c.getAttr(extra + ".rotateOrder"))
                    != spec.chain.rotation_order
                    or _bendy_parent_name(c, extra) != extra_parent
                    or _bendy_parent_name(c, control) != extra):
                return False
            expected_position = (
                spec.chain.master_position if index == 0
                else spec.chain.control_positions[index - 1])
            position = c.xform(offset, query=True,
                               worldSpace=True, translation=True)
            if any(abs(float(actual) - expected) > 1e-4
                   for actual, expected in zip(
                       position, expected_position)):
                return False
            if index == 0:
                marker = offset + ".advPyBendyOrientedBind"
                if (bool(c.objExists(marker))
                        != (spec.chain.start_world_axes is not None)):
                    return False
                if (spec.chain.start_world_axes is not None
                        and (not c.getAttr(marker)
                             or not c.getAttr(marker, lock=True))):
                    return False
            if index == 0 and spec.master_aim_follow:
                if not self._capture_fit_bendy_master_aim_follow(
                        spec.chain, offset, names[0], names[1],
                        parent_proxy, spec.start_control_blend):
                    return False
            elif (not c.objExists(follow)
                  or c.nodeType(follow) != "parentConstraint"):
                return False
            if spec.chain.legacy_simple_control and index == 2:
                targets = c.parentConstraint(
                    follow, query=True, targetList=True) or []
                if (len(targets) != 1
                        or _bendy_dag_name(targets[0])
                        != spec.chain.control_names[0]):
                    return False
        chain = spec.chain
        end_position = c.xform(chain.end_proxy_name, query=True,
                               worldSpace=True, translation=True)
        if any(abs(float(actual) - expected) > 1e-4
               for actual, expected in zip(
                   end_position, chain.end_position)):
            return False
        if chain.child_start_influence or spec.end_matrix_follow:
            translation, rotation, world = chain.end_follow_matrix_names
            end = chain.end_proxy_name
            if (not c.objExists(translation)
                    or c.nodeType(translation) != "pickMatrix"
                    or not c.objExists(rotation)
                    or c.nodeType(rotation) != "pickMatrix"
                    or not c.objExists(world)
                    or c.nodeType(world) != "multMatrix"
                    or c.connectionInfo(translation + ".inputMatrix",
                                        sourceFromDestination=True)
                    != ((chain.child_start_influence or names[1])
                        + ".worldMatrix[0]")
                    or c.connectionInfo(rotation + ".inputMatrix",
                                        sourceFromDestination=True)
                    != parent_proxy + ".worldMatrix[0]"
                    or c.connectionInfo(world + ".matrixIn[0]",
                                        sourceFromDestination=True)
                    != rotation + ".outputMatrix"
                    or c.connectionInfo(world + ".matrixIn[1]",
                                        sourceFromDestination=True)
                    != translation + ".outputMatrix"
                    or c.connectionInfo(world + ".matrixIn[2]",
                                        sourceFromDestination=True)
                    != end + ".parentInverseMatrix[0]"
                    or c.connectionInfo(end + ".offsetParentMatrix",
                                        sourceFromDestination=True)
                    != world + ".matrixSum"):
                return False
            for node, disabled in ((translation, ("useRotate", "useShear")),
                                   (rotation, ("useTranslate", "useScale",
                                               "useShear"))):
                if any(c.getAttr(node + "." + attribute)
                       for attribute in disabled):
                    return False
            if (not chain.child_start_influence
                    and bool(c.getAttr(translation + ".useScale"))):
                return False
            return True
        end_follow = f"AdvPy_{chain.end_proxy_name}Follow"
        return (c.objExists(end_follow)
                and c.nodeType(end_follow) == "parentConstraint")

    def _capture_fit_bendy_parent_untwist(
            self, chain: FitBendyChainSpec, start_proxy: str,
            twist_plug: str) -> bool:
        c = self._cmds
        negate, compose, world, frame = chain.parent_untwist_names
        return (all(c.objExists(name) and c.nodeType(name) == kind
                    for name, kind in (
                        (negate, "multDoubleLinear"),
                        (compose, "composeMatrix"),
                        (world, "multMatrix"),
                        (frame, "transform")))
                and abs(float(c.getAttr(negate + ".input2")) + 1.0)
                < 1e-6
                and _bendy_parent_name(c, frame) == _GROUPS[0]
                and not bool(c.getAttr(frame + ".visibility"))
                and c.connectionInfo(negate + ".input1",
                                     sourceFromDestination=True)
                == twist_plug
                and c.connectionInfo(compose + ".inputRotateX",
                                     sourceFromDestination=True)
                == negate + ".output"
                and c.connectionInfo(world + ".matrixIn[0]",
                                     sourceFromDestination=True)
                == compose + ".outputMatrix"
                and c.connectionInfo(world + ".matrixIn[1]",
                                     sourceFromDestination=True)
                == start_proxy + ".worldMatrix[0]"
                and c.connectionInfo(world + ".matrixIn[2]",
                                     sourceFromDestination=True)
                == frame + ".parentInverseMatrix[0]"
                and c.connectionInfo(frame + ".offsetParentMatrix",
                                     sourceFromDestination=True)
                == world + ".matrixSum")

    def _capture_fit_bendy_master_aim_follow(
            self, chain: FitBendyChainSpec, offset: str,
            start_proxy: str, end_proxy: str,
            parent_proxy: str,
            start_control_blend: bool) -> bool:
        c = self._cmds
        (blend, translate, rotate, mix, aim, bind,
         world, pick) = chain.master_follow_matrix_names
        nodes = ((blend, "blendMatrix"), (translate, "pickMatrix"),
                 (rotate, "pickMatrix"), (mix, "multMatrix"),
                 (aim, "aimMatrix"), (bind, "multMatrix"),
                 (world, "multMatrix"), (pick, "pickMatrix"))
        if any(not c.objExists(name) or c.nodeType(name) != kind
               for name, kind in nodes):
            return False
        bend_start = ((chain.control_names[1]
                       if chain.legacy_twist_outputs else
                       chain.twist_projection_names[1][0])
                      if start_control_blend else start_proxy)
        connections = (
            (blend + ".inputMatrix", bend_start + ".worldMatrix[0]"),
            (blend + ".target[0].targetMatrix",
             end_proxy + ".worldMatrix[0]"),
            (translate + ".inputMatrix", blend + ".outputMatrix"),
            (rotate + ".inputMatrix", parent_proxy + ".worldMatrix[0]"),
            (mix + ".matrixIn[0]", rotate + ".outputMatrix"),
            (mix + ".matrixIn[1]", translate + ".outputMatrix"),
            (aim + ".inputMatrix", mix + ".matrixSum"),
            (aim + ".primaryTargetMatrix",
             end_proxy + ".worldMatrix[0]"),
            (aim + ".secondaryTargetMatrix",
             parent_proxy + ".worldMatrix[0]"),
            (bind + ".matrixIn[1]", aim + ".outputMatrix"),
            (world + ".matrixIn[0]", bind + ".matrixSum"),
            (world + ".matrixIn[1]",
             offset + ".parentInverseMatrix[0]"),
            (pick + ".inputMatrix", world + ".matrixSum"),
            (offset + ".offsetParentMatrix", pick + ".outputMatrix"))
        if any(c.connectionInfo(destination,
                                sourceFromDestination=True) != source
               for destination, source in connections):
            return False
        if c.connectionInfo(bind + ".matrixIn[0]",
                            sourceFromDestination=True):
            return False
        if (abs(float(c.getAttr(blend + ".target[0].weight")) - 0.5)
                > 1e-6
                or abs(float(c.getAttr(aim + ".envelope")) - 0.5)
                > 1e-6):
            return False
        for node, disabled in ((translate, ("useRotate", "useScale",
                                            "useShear")),
                               (rotate, ("useTranslate", "useScale",
                                         "useShear")),
                               (pick, ("useScale", "useShear"))):
            if any(c.getAttr(node + "." + attribute)
                   for attribute in disabled):
                return False
        side = chain.aim_axis_sign
        axes = (("primaryInputAxis", (side, 0, 0)),
                ("secondaryInputAxis", (0, 0, side)),
                ("secondaryTargetVector", (0, 0, side)))
        for attribute, expected in axes:
            actual = c.getAttr(aim + "." + attribute)[0]
            if any(abs(float(a) - b) > 1e-6
                   for a, b in zip(actual, expected)):
                return False
        return True

    def create_fit_bendy_twist_projections(
            self, spec: FitBendyChainSpec) -> None:
        self._require_transaction()
        c = self._cmds
        for control, (output, matrix_name, decompose_name,
                      project_name) in zip(spec.control_names,
                                           spec.twist_projection_names):
            offset = control + "Offset"
            if (_bendy_parent_name(c, output) != control
                    or c.nodeType(output) != "transform"):
                raise ValueError("Bendy 控制器输出层不存在：" + output)
            matrix = c.createNode("multMatrix", name=matrix_name,
                                  skipSelect=True)
            decompose = c.createNode("decomposeMatrix",
                                     name=decompose_name,
                                     skipSelect=True)
            c.setAttr(decompose + ".inputRotateOrder",
                      spec.rotation_order)
            project = c.createNode("quatToEuler", name=project_name,
                                   skipSelect=True)
            c.connectAttr(output + ".worldMatrix[0]",
                          matrix + ".matrixIn[0]")
            c.connectAttr(offset + ".worldInverseMatrix[0]",
                          matrix + ".matrixIn[1]")
            c.connectAttr(matrix + ".matrixSum",
                          decompose + ".inputMatrix")
            c.connectAttr(decompose + ".outputQuatX",
                          project + ".inputQuatX")
            c.connectAttr(decompose + ".outputQuatW",
                          project + ".inputQuatW")
        self._transaction_changed = True

    def create_fit_bendy_micro(
            self, spec: FitBendyChainSpec,
            base_twist_plug: str | None = None,
            up_twist_plug: str | None = None) -> None:
        """Place animator micro controls on the curve's sampled frames."""
        self._require_transaction()
        c = self._cmds
        if not c.objExists(_MICRO_GROUP):
            parent = "|Group|MotionSystem"
            options = ({"parent": parent} if c.objExists(parent) else {})
            group = c.createNode("transform", name=_MICRO_GROUP,
                                 skipSelect=True, **options)
            c.addAttr(group, longName="advPyBendyGuideOwner",
                      dataType="string")
            c.setAttr(group + ".advPyBendyGuideOwner", _OWNER,
                      type="string", lock=True)
            if c.objExists("MainScaleMultiplyDivide.output"):
                c.connectAttr("MainScaleMultiplyDivide.output",
                              group + ".scale")
        master = spec.control_names[0]
        c.addAttr(master, longName="microVis", attributeType="bool",
                  defaultValue=False, keyable=False)
        c.setAttr(master + ".microVis", channelBox=True)
        positions = (spec.start_position, *spec.part_positions)
        for index, (offset_name, extra_name, control_name, output_name,
                    guide_name, position, radius) in enumerate(zip(
                        spec.micro_offset_names, spec.micro_extra_names,
                        spec.micro_control_names,
                        spec.micro_output_names,
                        spec.motion_transform_names, positions,
                        spec.micro_radii)):
            offset = c.createNode("transform", name=offset_name,
                                  parent=_MICRO_GROUP, skipSelect=True)
            self._align_bendy_control(
                offset, position, spec.start_world_axes)
            extra = c.createNode("transform", name=extra_name,
                                 parent=offset, skipSelect=True)
            control = create_adv_icon(
                c, name=control_name, parent=extra,
                template="Micro_icon", radius=radius,
                fallback_normal=(1.0, 0.0, 0.0),
                mirror_left=spec.side == "L")
            self._align_bendy_control(
                control, position, spec.start_world_axes)
            c.createNode("transform", name=output_name,
                         parent=control, skipSelect=True)
            c.connectAttr(master + ".microVis", offset + ".visibility")
            target = (spec.motion_transform_names[index + 1]
                      if index + 1 < len(spec.motion_transform_names)
                      else spec.end_proxy_name)
            if spec.micro_matrix_aim:
                names = spec.micro_matrix_orientation_names[index]
                second_name, third_name = names[-2:]
                twist_compose = c.createNode(
                    "composeMatrix", name=second_name,
                    skipSelect=True)
                twist_world = c.createNode(
                    "multMatrix", name=third_name,
                    skipSelect=True)
                c.connectAttr(twist_compose + ".outputMatrix",
                              twist_world + ".matrixIn[0]")
                if spec.micro_blended_up:
                    blend = c.createNode("blendMatrix", name=names[0],
                                         skipSelect=True)
                    start_frame = (spec.parent_untwist_names[3]
                                   if c.objExists(spec.parent_untwist_names[3])
                                   else spec.follow_node_names[0])
                    c.connectAttr(start_frame + ".worldMatrix[0]",
                                  blend + ".inputMatrix")
                    c.connectAttr(spec.follow_node_names[1]
                                  + ".worldMatrix[0]",
                                  blend + ".target[0].targetMatrix")
                    c.setAttr(blend + ".target[0].weight",
                              index / (len(spec.part_names) + 1))
                    up_source = blend + ".outputMatrix"
                else:
                    up_source = (spec.follow_node_names[0]
                                 + ".worldMatrix[0]")
                c.connectAttr(up_source,
                              twist_world + ".matrixIn[1]")
            else:
                blend_name, second_name, third_name = (
                    spec.micro_orientation_names[index])
                blend = c.createNode("blendMatrix", name=blend_name,
                                     skipSelect=True)
                decompose = c.createNode("decomposeMatrix",
                                         name=second_name,
                                         skipSelect=True)
                up = c.createNode("transform", name=third_name,
                                  parent=_GROUPS[0], skipSelect=True)
                start_frame = (spec.parent_untwist_names[3]
                               if c.objExists(spec.parent_untwist_names[3])
                               else spec.follow_node_names[0])
                c.connectAttr(start_frame + ".worldMatrix[0]",
                              blend + ".inputMatrix")
                c.connectAttr(spec.follow_node_names[1]
                              + ".worldMatrix[0]",
                              blend + ".target[0].targetMatrix")
                c.setAttr(blend + ".target[0].weight",
                          index / (len(spec.part_names) + 1))
                c.connectAttr(blend + ".outputMatrix",
                              decompose + ".inputMatrix")
                c.connectAttr(decompose + ".outputRotate",
                              up + ".rotate")
            if spec.micro_matrix_aim:
                compose_name, aim_name, aim_decompose_name = (
                    spec.micro_aim_matrix_names[index])
                compose = c.createNode("composeMatrix", name=compose_name,
                                       skipSelect=True)
                aim = c.createNode("aimMatrix", name=aim_name,
                                   skipSelect=True)
                aim_decompose = c.createNode(
                    "decomposeMatrix", name=aim_decompose_name,
                    skipSelect=True)
                c.connectAttr(spec.motion_path_names[index]
                              + ".allCoordinates",
                              compose + ".inputTranslate")
                c.connectAttr(compose + ".outputMatrix",
                              aim + ".inputMatrix")
                c.connectAttr(target + ".worldMatrix[0]",
                              aim + ".primaryTargetMatrix")
                c.connectAttr(twist_world + ".matrixSum",
                              aim + ".secondaryTargetMatrix")
                c.setAttr(aim + ".primaryInputAxis",
                          spec.aim_axis_sign, 0, 0)
                c.setAttr(aim + ".secondaryMode", 2)
                c.setAttr(aim + ".secondaryInputAxis", 0, 0, 1)
                c.setAttr(aim + ".secondaryTargetVector", 0, 0, 1)
                c.connectAttr(aim + ".outputMatrix",
                              aim_decompose + ".inputMatrix")
                c.connectAttr(aim_decompose + ".outputRotate",
                              guide_name + ".rotate")
            else:
                c.aimConstraint(target, guide_name,
                                aimVector=(spec.aim_axis_sign, 0, 0),
                                upVector=(0, 0, 1),
                                worldUpType="objectrotation",
                                worldUpObject=up,
                                name=guide_name + "Aim")
            c.parentConstraint(guide_name, offset, maintainOffset=True,
                               name=guide_name + "MicroFollow")
            twist_add_name, twist_mult_names = spec.micro_twist_names[index]
            twist_add = c.createNode("plusMinusAverage",
                                     name=twist_add_name,
                                     skipSelect=True)
            for control_index, (bend_control, mult_name, weight) in enumerate(
                    zip(spec.control_names, twist_mult_names,
                        spec.twist_weights(index))):
                mult = c.createNode("multDoubleLinear", name=mult_name,
                                    skipSelect=True)
                projection = spec.twist_projection_names[
                    control_index][3] + ".outputRotateX"
                c.connectAttr(projection,
                              mult + ".input1")
                c.setAttr(mult + ".input2", weight)
                c.connectAttr(mult + ".output",
                              twist_add + f".input1D[{control_index}]")
            if spec.child_start_control:
                end_twist = c.createNode(
                    "multDoubleLinear",
                    name=spec.micro_end_twist_names[index],
                    skipSelect=True)
                child_projection = ("AdvPy_" + spec.child_start_control
                                    + "TwistQTE.outputRotateX")
                c.connectAttr(child_projection,
                              end_twist + ".input1")
                c.setAttr(end_twist + ".input2",
                          index / len(spec.part_names))
                c.connectAttr(end_twist + ".output",
                              twist_add + f".input1D[{len(spec.control_names)}]")
            if spec.micro_base_twist:
                if not base_twist_plug or not c.objExists(base_twist_plug):
                    raise ValueError("Bendy 基础扭转来源不存在："
                                     + str(base_twist_plug))
                deform_joint = spec.deform_names[index]
                amount_plug = deform_joint + ".twistAmount"
                addition_plug = deform_joint + ".twistAddition"
                if not c.objExists(amount_plug):
                    c.addAttr(deform_joint, longName="twistAmount",
                              attributeType="double", minValue=0,
                              maxValue=1,
                              defaultValue=index / (len(spec.part_names) + 1),
                              keyable=True)
                if not c.objExists(addition_plug):
                    c.addAttr(deform_joint, longName="twistAddition",
                              attributeType="double", defaultValue=0,
                              keyable=True)
                offset_name, mult_name = (
                    spec.micro_base_twist_names[index])
                amount_offset = c.createNode(
                    "plusMinusAverage", name=offset_name,
                    skipSelect=True)
                c.connectAttr(amount_plug,
                              amount_offset + ".input1D[0]")
                c.setAttr(amount_offset + ".input1D[1]", -1)
                mult = c.createNode("multDoubleLinear", name=mult_name,
                                    skipSelect=True)
                c.connectAttr(base_twist_plug, mult + ".input1")
                c.connectAttr(amount_offset + ".output1D",
                              mult + ".input2")
                next_index = (len(spec.control_names)
                              + int(bool(spec.child_start_control)))
                c.connectAttr(mult + ".output",
                              twist_add + f".input1D[{next_index}]")
                c.connectAttr(addition_plug,
                              twist_add + f".input1D[{next_index + 1}]")
            if spec.micro_up_twist and index > 0:
                if not up_twist_plug or not c.objExists(up_twist_plug):
                    raise ValueError("Bendy 上行扭转来源不存在："
                                     + str(up_twist_plug))
                amount_plug = (spec.deform_names[index]
                               + ".twistAmount")
                if not c.objExists(amount_plug):
                    raise ValueError("Bendy Part 缺少扭转比例："
                                     + amount_plug)
                up_name = spec.micro_up_twist_names[index - 1]
                up = c.createNode("multDoubleLinear", name=up_name,
                                  skipSelect=True)
                c.connectAttr(up_twist_plug, up + ".input1")
                c.connectAttr(amount_plug, up + ".input2")
                up_index = (len(spec.control_names)
                            + int(bool(spec.child_start_control))
                            + 2 * int(spec.micro_base_twist))
                c.connectAttr(up + ".output",
                              twist_add + f".input1D[{up_index}]")
            c.connectAttr(twist_add + ".output1D",
                          (twist_compose + ".inputRotateX"
                           if spec.micro_matrix_aim else
                           output_name + ".rotateX"))
            scale_add_name, delta_names, weight_names = (
                spec.micro_scale_names[index])
            scale_add = c.createNode("plusMinusAverage",
                                     name=scale_add_name,
                                     skipSelect=True)
            c.setAttr(scale_add + ".input3D[0]", 1.0, 1.0, 1.0,
                      type="float3")
            for control_index, (bend_control, delta_name,
                                weight_name, weight) in enumerate(zip(
                                    spec.control_names, delta_names,
                                    weight_names,
                                    spec.control_weights(index)), start=1):
                delta = c.createNode("plusMinusAverage",
                                     name=delta_name, skipSelect=True)
                c.setAttr(delta + ".operation", 2)
                c.connectAttr(bend_control + ".scale",
                              delta + ".input3D[0]")
                c.setAttr(delta + ".input3D[1]", 1.0, 1.0, 1.0,
                          type="float3")
                mult = c.createNode("multiplyDivide", name=weight_name,
                                    skipSelect=True)
                c.connectAttr(delta + ".output3D", mult + ".input1")
                c.setAttr(mult + ".input2", weight, weight, weight)
                c.connectAttr(mult + ".output",
                              scale_add + f".input3D[{control_index}]")
            if spec.child_start_control:
                delta_name, weight_name = (
                    spec.micro_end_scale_names[index])
                delta = c.createNode("plusMinusAverage",
                                     name=delta_name, skipSelect=True)
                c.setAttr(delta + ".operation", 2)
                c.connectAttr(spec.child_start_control + ".scale",
                              delta + ".input3D[0]")
                c.setAttr(delta + ".input3D[1]", 1.0, 1.0, 1.0,
                          type="float3")
                weight = c.createNode("multiplyDivide",
                                      name=weight_name, skipSelect=True)
                c.connectAttr(delta + ".output3D",
                              weight + ".input1")
                end_weight = 1.0 - spec.control_weights(index)[1]
                c.setAttr(weight + ".input2", end_weight,
                          end_weight, end_weight)
                c.connectAttr(weight + ".output",
                              scale_add + f".input3D[{len(spec.control_names) + 1}]")
            if spec.micro_yz_scale_only:
                for axis in "YZ":
                    c.connectAttr(scale_add + ".output3D"
                                  + axis.lower(),
                                  offset + ".scale" + axis)
            else:
                c.connectAttr(scale_add + ".output3D",
                              offset + ".scale")
        self._transaction_changed = True

    def _capture_fit_bendy_micro_aim(
            self, spec: FitBendyChainSpec, index: int,
            guide: str, up_matrix: str) -> bool:
        c = self._cmds
        if not spec.micro_matrix_aim:
            constraint = guide + "Aim"
            return (c.objExists(constraint)
                    and c.nodeType(constraint) == "aimConstraint")
        compose, aim, decompose = spec.micro_aim_matrix_names[index]
        target = (spec.motion_transform_names[index + 1]
                  if index + 1 < len(spec.motion_transform_names)
                  else spec.end_proxy_name)
        if (not c.objExists(compose)
                or c.nodeType(compose) != "composeMatrix"
                or not c.objExists(aim)
                or c.nodeType(aim) != "aimMatrix"
                or not c.objExists(decompose)
                or c.nodeType(decompose) != "decomposeMatrix"
                or c.connectionInfo(compose + ".inputTranslate",
                                    sourceFromDestination=True)
                != spec.motion_path_names[index] + ".allCoordinates"
                or c.connectionInfo(aim + ".inputMatrix",
                                    sourceFromDestination=True)
                != compose + ".outputMatrix"
                or c.connectionInfo(aim + ".primaryTargetMatrix",
                                    sourceFromDestination=True)
                != target + ".worldMatrix[0]"
                or c.connectionInfo(aim + ".secondaryTargetMatrix",
                                    sourceFromDestination=True)
                != up_matrix + ".matrixSum"
                or c.connectionInfo(decompose + ".inputMatrix",
                                    sourceFromDestination=True)
                != aim + ".outputMatrix"
                or c.connectionInfo(guide + ".rotate",
                                    sourceFromDestination=True)
                != decompose + ".outputRotate"
                or int(c.getAttr(aim + ".secondaryMode")) != 2):
            return False
        for attribute, expected in (
                ("primaryInputAxis", (spec.aim_axis_sign, 0, 0)),
                ("secondaryInputAxis", (0, 0, 1)),
                ("secondaryTargetVector", (0, 0, 1))):
            values = c.getAttr(aim + "." + attribute)[0]
            if any(abs(float(a) - b) > 1e-6
                   for a, b in zip(values, expected)):
                return False
        return True

    def capture_fit_bendy_micro(
            self, spec: FitBendyChainSpec,
            base_twist_plug: str | None = None,
            up_twist_plug: str | None = None) -> bool:
        c = self._cmds
        master = spec.control_names[0]
        if (not c.objExists(_MICRO_GROUP)
                or not c.objExists(master + ".microVis")):
            return False
        if c.objExists("|Group|MotionSystem"):
            if ((c.listRelatives(_MICRO_GROUP, parent=True,
                                 fullPath=True) or [])
                    != ["|Group|MotionSystem"]
                    or c.connectionInfo(
                        _MICRO_GROUP + ".scale",
                        sourceFromDestination=True)
                    != "MainScaleMultiplyDivide.output"):
                return False
        for control, (output, matrix, decompose, project) in zip(
                spec.control_names, spec.twist_projection_names):
            if (not c.objExists(output)
                    or c.nodeType(output) != "transform"
                    or not c.objExists(matrix)
                    or c.nodeType(matrix) != "multMatrix"
                    or not c.objExists(decompose)
                    or c.nodeType(decompose) != "decomposeMatrix"
                    or not c.objExists(project)
                    or c.nodeType(project) != "quatToEuler"
                    or c.connectionInfo(matrix + ".matrixIn[0]",
                                        sourceFromDestination=True)
                    != output + ".worldMatrix[0]"
                    or c.connectionInfo(matrix + ".matrixIn[1]",
                                        sourceFromDestination=True)
                    != control + "Offset.worldInverseMatrix[0]"
                    or c.connectionInfo(project + ".inputQuatX",
                                        sourceFromDestination=True)
                    != decompose + ".outputQuatX"
                    or c.connectionInfo(project + ".inputQuatW",
                                        sourceFromDestination=True)
                    != decompose + ".outputQuatW"):
                return False
        for index, (offset, extra, control, output, guide) in enumerate(zip(
                spec.micro_offset_names, spec.micro_extra_names,
                spec.micro_control_names,
                spec.micro_output_names, spec.motion_transform_names)):
            if spec.micro_matrix_aim:
                names = spec.micro_matrix_orientation_names[index]
                second, third = names[-2:]
                if spec.micro_blended_up:
                    blend = names[0]
                    start_frame = (spec.parent_untwist_names[3]
                                   if c.objExists(spec.parent_untwist_names[3])
                                   else spec.follow_node_names[0])
                    if (not c.objExists(blend)
                            or c.nodeType(blend) != "blendMatrix"
                            or c.connectionInfo(blend + ".inputMatrix",
                                                sourceFromDestination=True)
                            != start_frame + ".worldMatrix[0]"
                            or c.connectionInfo(
                                blend + ".target[0].targetMatrix",
                                sourceFromDestination=True)
                            != spec.follow_node_names[1]
                            + ".worldMatrix[0]"
                            or abs(float(c.getAttr(
                                blend + ".target[0].weight"))
                                - index / (len(spec.part_names) + 1)) > 1e-8):
                        return False
                    up_source = blend + ".outputMatrix"
                else:
                    up_source = (spec.follow_node_names[0]
                                 + ".worldMatrix[0]")
            else:
                blend, second, third = (
                    spec.micro_orientation_names[index])
                start_frame = (spec.parent_untwist_names[3]
                               if c.objExists(spec.parent_untwist_names[3])
                               else spec.follow_node_names[0])
                if (not c.objExists(blend)
                        or c.nodeType(blend) != "blendMatrix"
                        or c.connectionInfo(blend + ".inputMatrix",
                                            sourceFromDestination=True)
                        != start_frame + ".worldMatrix[0]"
                        or c.connectionInfo(
                            blend + ".target[0].targetMatrix",
                            sourceFromDestination=True)
                        != spec.follow_node_names[1]
                        + ".worldMatrix[0]"
                        or abs(float(c.getAttr(
                            blend + ".target[0].weight"))
                            - index / (len(spec.part_names) + 1)) > 1e-8):
                    return False
            twist_add, twist_mults = spec.micro_twist_names[index]
            scale_add, delta_names, weight_names = (
                spec.micro_scale_names[index])
            if (not c.objExists(offset) or not c.objExists(extra)
                    or c.nodeType(extra) != "transform"
                    or _bendy_parent_name(c, extra) != offset
                    or not c.objExists(control)
                    or _bendy_parent_name(c, control) != extra
                    or not c.objExists(output)
                    or _bendy_parent_name(c, output) != control
                    or not c.objExists(second)
                    or c.nodeType(second) != (
                        "composeMatrix" if spec.micro_matrix_aim
                        else "decomposeMatrix")
                    or not c.objExists(third)
                    or c.nodeType(third) != (
                        "multMatrix" if spec.micro_matrix_aim
                        else "transform")
                    or not c.objExists(twist_add)
                    or c.nodeType(twist_add) != "plusMinusAverage"
                    or c.connectionInfo(output + ".rotateX",
                                        sourceFromDestination=True)
                    != ("" if spec.micro_matrix_aim
                        else twist_add + ".output1D")
                    or not c.objExists(scale_add)
                    or c.nodeType(scale_add) != "plusMinusAverage"
                    or any(abs(float(value) - 1.0) > 1e-8
                           for value in c.getAttr(
                               scale_add + ".input3D[0]")[0])
                    or (not spec.micro_yz_scale_only
                        and c.connectionInfo(offset + ".scale",
                                             sourceFromDestination=True)
                        != scale_add + ".output3D")
                    or not self._capture_fit_bendy_micro_aim(
                        spec, index, guide, third)
                    or not c.objExists(guide + "MicroFollow")
                    or c.nodeType(guide + "MicroFollow")
                    != "parentConstraint"
                    or c.connectionInfo(offset + ".visibility",
                                        sourceFromDestination=True)
                    != master + ".microVis"):
                return False
            if spec.micro_yz_scale_only:
                if (c.connectionInfo(offset + ".scaleX",
                                     sourceFromDestination=True)
                        or any(c.connectionInfo(
                            offset + ".scale" + axis.upper(),
                            sourceFromDestination=True)
                            != scale_add + ".output3D" + axis
                            for axis in "yz")):
                    return False
            if spec.micro_matrix_aim:
                if (c.connectionInfo(second + ".inputRotateX",
                                     sourceFromDestination=True)
                        != twist_add + ".output1D"
                        or c.connectionInfo(third + ".matrixIn[0]",
                                            sourceFromDestination=True)
                        != second + ".outputMatrix"
                        or c.connectionInfo(third + ".matrixIn[1]",
                                            sourceFromDestination=True)
                        != up_source):
                    return False
            elif (c.connectionInfo(second + ".inputMatrix",
                                   sourceFromDestination=True)
                  != blend + ".outputMatrix"
                  or c.connectionInfo(third + ".rotate",
                                      sourceFromDestination=True)
                  != second + ".outputRotate"):
                return False
            if spec.micro_base_twist:
                deform_joint = spec.deform_names[index]
                amount = deform_joint + ".twistAmount"
                addition = deform_joint + ".twistAddition"
                amount_offset, mult = spec.micro_base_twist_names[index]
                next_index = (len(spec.control_names)
                              + int(bool(spec.child_start_control)))
                if (not base_twist_plug
                        or not c.objExists(amount)
                        or not c.objExists(addition)
                        or not c.getAttr(amount, keyable=True)
                        or not c.getAttr(addition, keyable=True)
                        or not c.objExists(amount_offset)
                        or c.nodeType(amount_offset) != "plusMinusAverage"
                        or not c.objExists(mult)
                        or c.nodeType(mult) != "multDoubleLinear"
                        or c.connectionInfo(
                            amount_offset + ".input1D[0]",
                            sourceFromDestination=True) != amount
                        or abs(float(c.getAttr(
                            amount_offset + ".input1D[1]")) + 1) > 1e-8
                        or c.connectionInfo(mult + ".input1",
                                            sourceFromDestination=True)
                        != base_twist_plug
                        or c.connectionInfo(mult + ".input2",
                                            sourceFromDestination=True)
                        != amount_offset + ".output1D"
                        or c.connectionInfo(
                            twist_add + f".input1D[{next_index}]",
                            sourceFromDestination=True) != mult + ".output"
                        or c.connectionInfo(
                            twist_add + f".input1D[{next_index + 1}]",
                            sourceFromDestination=True) != addition):
                    return False
            if spec.micro_up_twist and index > 0:
                up_name = spec.micro_up_twist_names[index - 1]
                up_index = (len(spec.control_names)
                            + int(bool(spec.child_start_control))
                            + 2 * int(spec.micro_base_twist))
                if (not up_twist_plug
                        or not c.objExists(up_name)
                        or c.nodeType(up_name) != "multDoubleLinear"
                        or c.connectionInfo(up_name + ".input1",
                                            sourceFromDestination=True)
                        != up_twist_plug
                        or c.connectionInfo(up_name + ".input2",
                                            sourceFromDestination=True)
                        != spec.deform_names[index] + ".twistAmount"
                        or c.connectionInfo(
                            twist_add + f".input1D[{up_index}]",
                            sourceFromDestination=True)
                        != up_name + ".output"):
                    return False
            for control_index, (projection, mult_name, weight) in enumerate(zip(
                    spec.twist_projection_names, twist_mults,
                    spec.twist_weights(index))):
                if (not c.objExists(mult_name)
                        or c.nodeType(mult_name) != "multDoubleLinear"
                        or c.connectionInfo(mult_name + ".input1",
                                            sourceFromDestination=True)
                        != projection[3] + ".outputRotateX"
                        or c.connectionInfo(
                            twist_add + f".input1D[{control_index}]",
                            sourceFromDestination=True)
                        != mult_name + ".output"
                        or abs(float(c.getAttr(mult_name + ".input2"))
                               - weight) > 1e-8):
                    return False
            for control_index, (bend_control, delta_name, weight_name,
                                weight) in enumerate(zip(
                    spec.control_names, delta_names, weight_names,
                    spec.control_weights(index)), start=1):
                if (not c.objExists(delta_name)
                        or c.nodeType(delta_name) != "plusMinusAverage"
                        or int(c.getAttr(delta_name + ".operation")) != 2
                        or c.connectionInfo(delta_name + ".input3D[0]",
                                            sourceFromDestination=True)
                        != bend_control + ".scale"
                        or any(abs(float(value) - 1.0) > 1e-8
                               for value in c.getAttr(
                                   delta_name + ".input3D[1]")[0])
                        or not c.objExists(weight_name)
                        or c.nodeType(weight_name) != "multiplyDivide"
                        or c.connectionInfo(weight_name + ".input1",
                                            sourceFromDestination=True)
                        != delta_name + ".output3D"
                        or c.connectionInfo(
                            scale_add + f".input3D[{control_index}]",
                            sourceFromDestination=True)
                        != weight_name + ".output"
                        or any(abs(float(value) - weight) > 1e-8
                               for value in c.getAttr(
                                   weight_name + ".input2")[0])):
                    return False
            if spec.child_start_control:
                twist_end = spec.micro_end_twist_names[index]
                scale_delta, scale_weight = (
                    spec.micro_end_scale_names[index])
                if (not c.objExists(twist_end)
                        or c.nodeType(twist_end) != "multDoubleLinear"
                        or c.connectionInfo(twist_end + ".input1",
                                            sourceFromDestination=True)
                        != ("AdvPy_" + spec.child_start_control
                            + "TwistQTE.outputRotateX")
                        or c.connectionInfo(
                            twist_add + f".input1D[{len(spec.control_names)}]",
                            sourceFromDestination=True)
                        != twist_end + ".output"
                        or abs(float(c.getAttr(twist_end + ".input2"))
                               - index / len(spec.part_names)) > 1e-8
                        or not c.objExists(scale_delta)
                        or c.nodeType(scale_delta) != "plusMinusAverage"
                        or not c.objExists(scale_weight)
                        or c.nodeType(scale_weight) != "multiplyDivide"
                        or c.connectionInfo(scale_delta + ".input3D[0]",
                                            sourceFromDestination=True)
                        != spec.child_start_control + ".scale"
                        or int(c.getAttr(scale_delta + ".operation")) != 2
                        or any(abs(float(value) - 1.0) > 1e-8
                               for value in c.getAttr(
                                   scale_delta + ".input3D[1]")[0])
                        or c.connectionInfo(scale_weight + ".input1",
                                            sourceFromDestination=True)
                        != scale_delta + ".output3D"
                        or any(abs(float(value)
                                   - (1.0 - spec.control_weights(index)[1]))
                               > 1e-8 for value in c.getAttr(
                                   scale_weight + ".input2")[0])
                        or c.connectionInfo(
                            scale_add + f".input3D[{len(spec.control_names) + 1}]",
                            sourceFromDestination=True)
                        != scale_weight + ".output"):
                    return False
        return True

    def capture_fit_bendy_guides(
        self, spec: FitBendyChainSpec
    ) -> bool:
        c = self._cmds
        bend_path = "|Group|MotionSystem|BendSystem"
        if c.objExists(bend_path):
            if (c.listRelatives(_GROUPS[0], parent=True,
                                fullPath=True) or []) != [bend_path]:
                return False
            if (c.connectionInfo(_GROUPS[2] + ".scale",
                                 sourceFromDestination=True)
                    != "MainScaleMultiplyDivide.output"):
                return False
        curve = c.ls(spec.curve_name, long=True,
                     type="transform") or []
        if len(curve) != 1:
            return False
        shapes = c.listRelatives(curve[0], shapes=True,
                                 fullPath=True) or []
        if (len(shapes) != 1 or c.nodeType(shapes[0]) != "nurbsCurve"
                or not c.objExists(spec.skin_name)
                or c.nodeType(spec.skin_name) != "skinCluster"):
            return False
        influences = c.skinCluster(spec.skin_name, query=True,
                                   influence=True) or []
        if {name.rsplit("|", 1)[-1] for name in influences} != set(
                spec.influence_names):
            return False
        bend_drivers = (spec.control_names if spec.legacy_twist_outputs
                        else tuple(row[0] for row in
                                   spec.twist_projection_names))
        expected_drivers = (
            spec.junction_output_name if spec.parent_bendy
            else bend_drivers[1],
            *((spec.simple_proxy_name,) if spec.simple_proxy_layout
              else bend_drivers[2:]),
            spec.end_proxy_name)
        for name, driver in zip(spec.influence_names, expected_drivers):
            constraint = "AdvPy_BendGuide" + name
            if (not c.objExists(name) or c.nodeType(name) != "joint"
                    or not c.objExists(constraint)
                    or c.nodeType(constraint) != "parentConstraint"):
                return False
            targets = c.parentConstraint(
                constraint, query=True, targetList=True) or []
            if (len(targets) != 1
                    or _bendy_dag_name(targets[0]) != driver):
                return False
        for name in (*spec.control_names, spec.end_proxy_name):
            if not c.objExists(name) or c.nodeType(name) != "transform":
                return False
        for control, projection in zip(
                spec.control_names, spec.twist_projection_names):
            output = projection[0]
            if (not c.objExists(output)
                    or c.nodeType(output) != "transform"
                    or _bendy_parent_name(c, output) != control):
                return False
        if spec.simple_proxy_layout:
            proxy = spec.simple_proxy_name
            if (not c.objExists(proxy)
                    or c.nodeType(proxy) != "transform"
                    or _bendy_parent_name(c, proxy)
                    != spec.control_names[0]
                    or int(c.getAttr(proxy + ".rotateOrder"))
                    != spec.rotation_order
                    or c.objExists(spec.prefix + "1_" + spec.side)):
                return False
        master_shapes = c.listRelatives(spec.control_names[0],
                                         shapes=True, fullPath=True) or []
        if (len(master_shapes) != 1
                or c.nodeType(master_shapes[0]) != "nurbsCurve"
                or int(c.getAttr(master_shapes[0] + ".controlPoints",
                                 size=True)) != len(_MASTER_BEND_PROFILE_XZ)
                or not c.getAttr(master_shapes[0] + ".overrideEnabled")
                or int(c.getAttr(master_shapes[0] + ".overrideColor")) != 29):
            return False
        first_x, first_z = _MASTER_BEND_PROFILE_XZ[0]
        if (abs(float(c.getAttr(master_shapes[0]
                                + ".controlPoints[0].xValue"))
                - first_x * spec.master_icon_scale) > 1e-4
                or abs(float(c.getAttr(master_shapes[0]
                                       + ".controlPoints[0].zValue"))
                       - first_z * spec.master_icon_scale) > 1e-4):
            return False
        if any(int(c.getAttr(name + ".rotateOrder"))
               != spec.rotation_order for name in spec.control_names):
            return False
        start_shapes = c.listRelatives(spec.control_names[1],
                                       shapes=True, fullPath=True) or []
        if (len(start_shapes) != 1
                or c.nodeType(start_shapes[0]) != "nurbsCurve"):
            return False
        count = int(c.getAttr(start_shapes[0] + ".controlPoints",
                              size=True))
        if count < 4:
            return False
        center_x = sum(float(c.getAttr(
            start_shapes[0] + f".controlPoints[{index}].xValue"))
            for index in range(count)) / count
        if abs(center_x - spec.start_icon_offset) > 1e-4:
            return False
        if not c.objExists(spec.control_names[0] + ".parametric"):
            return False
        if spec.parent_bendy and any(
                not c.objExists(name) or c.nodeType(name) != "transform"
                for name in (spec.junction_offset_name,
                             spec.junction_extra_name,
                             spec.junction_name,
                             spec.junction_output_name)):
            return False
        if spec.parent_bendy and any(
                int(c.getAttr(name + ".rotateOrder"))
                != spec.rotation_order for name in (
                    spec.junction_offset_name,
                    spec.junction_extra_name, spec.junction_name)):
            return False
        if (spec.parent_bendy
                and (_bendy_parent_name(c, spec.junction_extra_name)
                     != spec.junction_offset_name
                     or _bendy_parent_name(c, spec.junction_name)
                     != spec.junction_extra_name)):
            return False
        if (spec.parent_bendy
                and not c.objExists(spec.junction_name + ".circular")):
            return False
        for index, (path, transform) in enumerate(zip(
                spec.motion_path_names, spec.motion_transform_names)):
            if (not c.objExists(path) or c.nodeType(path) != "motionPath"
                    or not c.objExists(transform)
                    or c.connectionInfo(path + ".geometryPath",
                        sourceFromDestination=True)
                    != shapes[0] + ".worldSpace[0]"
                    or c.connectionInfo(transform + ".translate",
                        sourceFromDestination=True)
                    != path + ".allCoordinates"
                    or c.connectionInfo(path + ".fractionMode",
                                        sourceFromDestination=True)
                    != spec.control_names[0] + ".parametric"
                    or not self._bendy_motion_parameter_matches(path)):
                return False
        return True
