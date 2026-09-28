"""Maya construction boundary for 6.925 Bendy guide curves."""
from __future__ import annotations

from typing import TYPE_CHECKING

from adv_py.core.fit_bendy import FitBendyChainSpec

if TYPE_CHECKING:
    from adv_py.application.fit_bendy import FitBendyFollowSpec, FitBendyWorldSource


_GROUPS = ("AdvPy_BendSystem", "AdvPy_BendCurve",
           "AdvPy_BendJoints", "AdvPy_BendMPX")
_SECONDARY_GROUPS = ("AdvPy_Bend2Curve", "AdvPy_Bend2Joints",
                     "AdvPy_Bend2MPX")
_MICRO_GROUP = "AdvPy_MicroSystem"
_OWNER = "adv_py.fit_bendy_guides.v1"


class MayaFitBendyMixin:
    def preflight_fit_bendy_secondary(self,
                                      spec: FitBendyChainSpec) -> None:
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
        drivers = (spec.control_names[1], spec.control_names[0],
                   spec.child_start_control or spec.end_proxy_name)
        positions = (spec.start_position, spec.master_position,
                     spec.end_position)
        influences = []
        for name, position, driver in zip(
                spec.secondary_influence_names, positions, drivers):
            joint = c.createNode("joint", name=name,
                                 parent=_SECONDARY_GROUPS[1],
                                 skipSelect=True)
            c.xform(joint, worldSpace=True, translation=position)
            c.setAttr(joint + ".drawStyle", 2)
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
            c.setAttr(path + ".fractionMode", True)
            c.setAttr(path + ".follow", True)
            c.setAttr(path + ".worldUpType", 2)
            c.setAttr(path + ".frontAxis", 0)
            c.setAttr(path + ".upAxis", 1)
            c.setAttr(path + ".uValue",
                      index / (spec.control_count + 1))
            c.connectAttr(spec.control_names[0] + ".worldMatrix[0]",
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
                    or not c.objExists(follow)
                    or c.nodeType(follow) != "parentConstraint"
                    or abs(float(c.getAttr(path + ".uValue"))
                           - index / (spec.control_count + 1)) > 1e-8):
                return False
        return True

    def preflight_fit_bendy_deform(self, spec: FitBendyChainSpec) -> None:
        c = self._cmds
        for index, (name, output, constraint, scale_pick,
                    scale_mult) in enumerate(zip(
                spec.deform_names, spec.micro_output_names,
                spec.deform_constraint_names,
                spec.deform_scale_pick_names,
                spec.deform_scale_mult_names)):
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
                    or c.objExists(scale_mult)):
                raise ValueError("Bendy 变形节点名称已占用：" + name)
            if c.listConnections(joints[0], type="skinCluster"):
                raise ValueError("Bendy 接管必须在 Skin 绑定前执行：" + name)

    def connect_fit_bendy_deform(self, spec: FitBendyChainSpec) -> None:
        self._require_transaction()
        c = self._cmds
        poses = {}
        for (name, output, offset, constraint, scale_pick,
             scale_mult_name) in zip(
                spec.deform_names, spec.micro_output_names,
                spec.micro_offset_names,
                spec.deform_constraint_names,
                spec.deform_scale_pick_names,
                spec.deform_scale_mult_names):
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
            c.connectAttr(offset + ".scale", scale_mult + ".input2")
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
             scale_mult) in zip(
                spec.deform_names, spec.micro_output_names,
                spec.micro_offset_names,
                spec.deform_constraint_names,
                spec.deform_scale_pick_names,
                spec.deform_scale_mult_names):
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
                    != offset + ".scale"):
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

    def preflight_fit_bendy_micro(self, spec: FitBendyChainSpec) -> None:
        c = self._cmds
        if any(c.objExists(name) for name in spec.micro_node_names):
            raise ValueError("Bendy 微控制节点名称已占用：" + spec.curve_name)
        if c.objExists(_MICRO_GROUP):
            marker = _MICRO_GROUP + ".advPyBendyGuideOwner"
            if not c.objExists(marker) or c.getAttr(marker) != _OWNER:
                raise ValueError("Bendy 微控制组不属于当前构建")

    def preflight_fit_bendy_follow(self, spec: "FitBendyFollowSpec") -> None:
        c = self._cmds
        if any(c.objExists(name) for name in spec.chain.follow_node_names):
            raise ValueError("Bendy 跟随节点名称已占用：" + spec.chain.curve_name)
        for source in (spec.start, spec.end):
            for plug in (source.fk_matrix, source.ik_matrix, source.blend_plug):
                if plug is not None and not c.objExists(plug):
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
            parent = _GROUPS[0] if index else None
            options = {"parent": parent} if parent else {}
            node = c.createNode("transform", name=group,
                                skipSelect=True, **options)
            c.addAttr(node, longName="advPyBendyGuideOwner",
                      dataType="string")
            c.setAttr(node + ".advPyBendyGuideOwner", _OWNER,
                      type="string", lock=True)
            self._transaction_changed = True

    def create_fit_bendy_guides(
        self, spec: FitBendyChainSpec
    ) -> None:
        self._require_transaction()
        c = self._cmds
        self._ensure_fit_bendy_groups()
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
            control = c.circle(name=name, normal=(1, 0, 0),
                               radius=0.25, constructionHistory=False)[0]
            parent = (spec.control_names[0]
                      if index == 2 and spec.control_count == 1
                      else _GROUPS[0])
            control = c.parent(control, parent)[0]
            c.xform(control, worldSpace=True, translation=position)
            controls.append((c.ls(control, long=True) or [control])[0])
        if spec.parent_bendy:
            junction_offset = c.createNode(
                "transform", name=spec.junction_offset_name,
                parent=controls[1], skipSelect=True)
            c.xform(junction_offset, worldSpace=True,
                    translation=start)
            junction = c.circle(name=spec.junction_name,
                                normal=(1, 0, 0), radius=0.18,
                                constructionHistory=False)[0]
            c.parent(junction, junction_offset, absolute=True)
            c.xform(junction, worldSpace=True, translation=start)
            c.createNode("transform", name=spec.junction_output_name,
                         parent=junction, skipSelect=True)
        end_proxy = c.createNode("transform", name=spec.end_proxy_name,
                                 parent=_GROUPS[0], skipSelect=True)
        c.xform(end_proxy, worldSpace=True, translation=end)
        drivers = ((spec.junction_output_name if spec.parent_bendy
                    else controls[1]), *controls[2:], end_proxy)
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
        for index, (path_name, transform_name) in enumerate(zip(
                spec.motion_path_names,
                spec.motion_transform_names)):
            path = c.createNode("motionPath", name=path_name,
                                skipSelect=True)
            transform = c.createNode("transform", name=transform_name,
                                     parent=_GROUPS[3], skipSelect=True)
            c.setAttr(path + ".fractionMode", True)
            c.setAttr(path + ".uValue",
                      index / (len(spec.part_names) + 1))
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
        for index, control in enumerate(chain.control_names):
            position = (chain.master_position if index == 0
                        else chain.control_positions[index - 1])
            offset = c.createNode("transform", name=control + "Offset",
                                  parent=_GROUPS[0], skipSelect=True)
            c.xform(offset, worldSpace=True, translation=position)
            c.parent(control, offset, absolute=True)
            targets = ((start_proxy, end_proxy) if index == 0
                       or index > 1 else (start_proxy,))
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
        c.parentConstraint(end_proxy, chain.end_proxy_name,
                           maintainOffset=True,
                           name=f"AdvPy_{chain.end_proxy_name}Follow")
        self._transaction_changed = True

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
        for control in spec.chain.control_names:
            offset = control + "Offset"
            follow = f"AdvPy_{control}Follow"
            if (not c.objExists(offset) or not c.objExists(follow)
                    or c.nodeType(follow) != "parentConstraint"
                    or (c.listRelatives(control, parent=True) or [])
                    != [offset]):
                return False
        return (c.objExists(names[-1])
                and c.nodeType(names[-1]) == "parentConstraint")

    def create_fit_bendy_twist_projections(
            self, spec: FitBendyChainSpec) -> None:
        self._require_transaction()
        c = self._cmds
        for control, (output, matrix_name, decompose_name,
                      project_name) in zip(spec.control_names,
                                           spec.twist_projection_names):
            offset = control + "Offset"
            child = c.createNode("transform", name=output,
                                 parent=control, skipSelect=True)
            matrix = c.createNode("multMatrix", name=matrix_name,
                                  skipSelect=True)
            decompose = c.createNode("decomposeMatrix",
                                     name=decompose_name,
                                     skipSelect=True)
            project = c.createNode("quatToEuler", name=project_name,
                                   skipSelect=True)
            c.connectAttr(child + ".worldMatrix[0]",
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

    def create_fit_bendy_micro(self, spec: FitBendyChainSpec) -> None:
        """Place animator micro controls on the curve's sampled frames."""
        self._require_transaction()
        c = self._cmds
        if not c.objExists(_MICRO_GROUP):
            group = c.createNode("transform", name=_MICRO_GROUP,
                                 skipSelect=True)
            c.addAttr(group, longName="advPyBendyGuideOwner",
                      dataType="string")
            c.setAttr(group + ".advPyBendyGuideOwner", _OWNER,
                      type="string", lock=True)
        master = spec.control_names[0]
        c.addAttr(master, longName="microVis", attributeType="bool",
                  defaultValue=False, keyable=False)
        c.setAttr(master + ".microVis", channelBox=True)
        positions = (spec.start_position, *spec.part_positions)
        for index, (offset_name, control_name, output_name,
                    guide_name, position) in enumerate(zip(
                        spec.micro_offset_names, spec.micro_control_names,
                        spec.micro_output_names,
                        spec.motion_transform_names, positions)):
            offset = c.createNode("transform", name=offset_name,
                                  parent=_MICRO_GROUP, skipSelect=True)
            c.xform(offset, worldSpace=True, translation=position)
            control = c.circle(name=control_name, normal=(1, 0, 0),
                               radius=0.15,
                               constructionHistory=False)[0]
            c.parent(control, offset, absolute=True)
            c.xform(control, worldSpace=True, translation=position)
            c.createNode("transform", name=output_name,
                         parent=control, skipSelect=True)
            c.connectAttr(master + ".microVis", offset + ".visibility")
            target = (spec.motion_transform_names[index + 1]
                      if index + 1 < len(spec.motion_transform_names)
                      else spec.end_proxy_name)
            blend_name, decompose_name, up_name = (
                spec.micro_orientation_names[index])
            blend = c.createNode("blendMatrix", name=blend_name,
                                 skipSelect=True)
            decompose = c.createNode("decomposeMatrix",
                                     name=decompose_name,
                                     skipSelect=True)
            up = c.createNode("transform", name=up_name,
                              parent=_GROUPS[0], skipSelect=True)
            c.connectAttr(spec.follow_node_names[0] + ".worldMatrix[0]",
                          blend + ".inputMatrix")
            c.connectAttr(spec.follow_node_names[1] + ".worldMatrix[0]",
                          blend + ".target[0].targetMatrix")
            c.setAttr(blend + ".target[0].weight",
                      index / (len(spec.part_names) + 1))
            c.connectAttr(blend + ".outputMatrix",
                          decompose + ".inputMatrix")
            c.connectAttr(decompose + ".outputRotate",
                          up + ".rotate")
            c.aimConstraint(target, guide_name,
                            aimVector=((-1 if spec.side == "L" else 1),
                                       0, 0), upVector=(0, 0, 1),
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
            c.connectAttr(twist_add + ".output1D",
                          output_name + ".rotateX")
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
            c.connectAttr(scale_add + ".output3D",
                          offset + ".scale")
        self._transaction_changed = True

    def capture_fit_bendy_micro(self, spec: FitBendyChainSpec) -> bool:
        c = self._cmds
        master = spec.control_names[0]
        if (not c.objExists(_MICRO_GROUP)
                or not c.objExists(master + ".microVis")):
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
        for index, (offset, control, output, guide) in enumerate(zip(
                spec.micro_offset_names, spec.micro_control_names,
                spec.micro_output_names, spec.motion_transform_names)):
            blend, decompose, up = spec.micro_orientation_names[index]
            twist_add, twist_mults = spec.micro_twist_names[index]
            scale_add, delta_names, weight_names = (
                spec.micro_scale_names[index])
            if (not c.objExists(offset) or not c.objExists(control)
                    or not c.objExists(output)
                    or not c.objExists(blend)
                    or c.nodeType(blend) != "blendMatrix"
                    or not c.objExists(decompose)
                    or c.nodeType(decompose) != "decomposeMatrix"
                    or not c.objExists(up)
                    or not c.objExists(twist_add)
                    or c.nodeType(twist_add) != "plusMinusAverage"
                    or c.connectionInfo(output + ".rotateX",
                                        sourceFromDestination=True)
                    != twist_add + ".output1D"
                    or not c.objExists(scale_add)
                    or c.nodeType(scale_add) != "plusMinusAverage"
                    or c.connectionInfo(offset + ".scale",
                                        sourceFromDestination=True)
                    != scale_add + ".output3D"
                    or not c.objExists(guide + "Aim")
                    or c.nodeType(guide + "Aim") != "aimConstraint"
                    or not c.objExists(guide + "MicroFollow")
                    or c.nodeType(guide + "MicroFollow")
                    != "parentConstraint"
                    or c.connectionInfo(offset + ".visibility",
                                        sourceFromDestination=True)
                    != master + ".microVis"):
                return False
            for projection, mult_name, weight in zip(
                    spec.twist_projection_names, twist_mults,
                    spec.twist_weights(index)):
                if (not c.objExists(mult_name)
                        or c.nodeType(mult_name) != "multDoubleLinear"
                        or c.connectionInfo(mult_name + ".input1",
                                            sourceFromDestination=True)
                        != projection[3] + ".outputRotateX"
                        or abs(float(c.getAttr(mult_name + ".input2"))
                               - weight) > 1e-8):
                    return False
            for bend_control, delta_name, weight_name, weight in zip(
                    spec.control_names, delta_names, weight_names,
                    spec.control_weights(index)):
                if (not c.objExists(delta_name)
                        or c.nodeType(delta_name) != "plusMinusAverage"
                        or c.connectionInfo(delta_name + ".input3D[0]",
                                            sourceFromDestination=True)
                        != bend_control + ".scale"
                        or not c.objExists(weight_name)
                        or c.nodeType(weight_name) != "multiplyDivide"
                        or c.connectionInfo(weight_name + ".input1",
                                            sourceFromDestination=True)
                        != delta_name + ".output3D"
                        or abs(float(c.getAttr(weight_name + ".input2X"))
                               - weight) > 1e-8):
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
                        or abs(float(c.getAttr(twist_end + ".input2"))
                               - index / len(spec.part_names)) > 1e-8
                        or not c.objExists(scale_delta)
                        or not c.objExists(scale_weight)
                        or c.connectionInfo(scale_delta + ".input3D[0]",
                                            sourceFromDestination=True)
                        != spec.child_start_control + ".scale"):
                    return False
        return True

    def capture_fit_bendy_guides(
        self, spec: FitBendyChainSpec
    ) -> bool:
        c = self._cmds
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
        for name in spec.influence_names:
            constraint = "AdvPy_BendGuide" + name
            if (not c.objExists(name) or c.nodeType(name) != "joint"
                    or not c.objExists(constraint)
                    or c.nodeType(constraint) != "parentConstraint"):
                return False
        for name in (*spec.control_names, spec.end_proxy_name):
            if not c.objExists(name) or c.nodeType(name) != "transform":
                return False
        if spec.parent_bendy and any(
                not c.objExists(name) or c.nodeType(name) != "transform"
                for name in (spec.junction_offset_name,
                             spec.junction_name,
                             spec.junction_output_name)):
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
                    or not c.getAttr(path + ".fractionMode")
                    or abs(float(c.getAttr(path + ".uValue"))
                           - index / (len(spec.part_names) + 1)) > 1e-8):
                return False
        return True
