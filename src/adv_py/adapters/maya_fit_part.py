"""Maya node boundary for the generic Fit-driven Part hierarchy."""
from __future__ import annotations

from math import isfinite

from adv_py.core.fit_part import (
    FitPartChildState,
    FitPartJointSpec,
    FitPartJointState,
    FitPartReparentSpec,
)
from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_symmetry import FitBuildSide
from adv_py.core.body_direct_fk_scale import BodyDirectFkScaleSpec
from adv_py.core.fit_part_twist import (
    FitPartTwistControlRewire, FitPartTwistProjection, FitPartTwistStep,
)
from adv_py.core.fit_part_scale import (
    FitPartEndScale, FitPartInheritedScaleChain, FitPartLimbScaleChain,
    FitPartScaleStep, FitPartToeScale,
)

_FIT_PART_KIND = "fit-part-v1"
_FIT_INBETWEEN_KIND = "fit-inbetween-v1"


class MayaFitPartMixin:
    def create_source_part_twist_references(self, inputs, independent, blended, *, main_scale_plug=None):
        from .maya_source_part_reference import create
        return create(self, inputs, independent, blended, main_scale_plug=main_scale_plug)

    def _has_fit_part_parent_chain(self, child: str,
                                   ancestor: str) -> bool:
        """Require every inserted joint between two Body nodes to be a Part."""
        c = self._cmds
        current = child
        while current != ancestor:
            parents = c.listRelatives(current, parent=True,
                                      fullPath=True) or []
            if len(parents) != 1:
                return False
            current = parents[0]
            if current == ancestor:
                return True
            marker = current + ".advPyAuxiliaryInfluenceKind"
            if (c.nodeType(current) != "joint"
                    or not c.objExists(marker)
                    or c.getAttr(marker) not in (
                        _FIT_PART_KIND, _FIT_INBETWEEN_KIND)):
                return False
        return True

    def preflight_fit_part_toe_scale(self, toe: FitPartToeScale) -> None:
        c = self._cmds
        body = self._unique_fit_part_joint(toe.body_name)
        if any(not c.objExists(plug) for plug in
               (toe.fk_scale_plug, toe.mode_plug)):
            raise ValueError("Fit Part 脚趾缺少 FK／IK 缩放输入："
                             + toe.body_name)
        if any(c.objExists(name) for name in
               (toe.blend_name, toe.scale_compose_name,
                toe.scale_matrix_name) if name):
            raise ValueError("Fit Part 脚趾缩放节点名称冲突："
                             + toe.body_name)
        if toe.use_offset_parent_matrix:
            if (not toe.scale_compose_name or not toe.scale_matrix_name
                    or not c.objExists(body + ".offsetParentMatrix")):
                raise ValueError("Fit Part 脚趾缺少 OPM 矩阵目标："
                                 + toe.body_name)
        elif any(not c.getAttr(body + ".scale" + axis,
                               settable=True) for axis in "XYZ"):
            raise ValueError("Fit Part 脚趾 Body 缩放目标不可写："
                             + toe.body_name)

    def connect_fit_part_toe_scale(self, toe: FitPartToeScale) -> None:
        self._require_transaction()
        c = self._cmds
        body = self._unique_fit_part_joint(toe.body_name)
        blend = c.createNode("blendColors", name=toe.blend_name)
        self._transaction_changed = True
        c.setAttr(blend + ".color1", 1.0, 1.0, 1.0)
        c.connectAttr(toe.fk_scale_plug, blend + ".color2")
        c.connectAttr(toe.mode_plug, blend + ".blender")
        if toe.use_offset_parent_matrix:
            target = body + ".offsetParentMatrix"
            old_source = c.connectionInfo(target,
                                          sourceFromDestination=True)
            old_matrix = c.getAttr(target)
            if old_matrix and isinstance(old_matrix[0], (tuple, list)):
                old_matrix = old_matrix[0]
            compose = c.createNode("composeMatrix",
                                   name=toe.scale_compose_name)
            matrix = c.createNode("multMatrix",
                                  name=toe.scale_matrix_name)
            for axis, color in zip("XYZ", "RGB"):
                c.connectAttr(blend + ".output" + color,
                              compose + ".inputScale" + axis)
            c.connectAttr(compose + ".outputMatrix",
                          matrix + ".matrixIn[0]")
            if old_source:
                c.disconnectAttr(old_source, target)
                c.connectAttr(old_source, matrix + ".matrixIn[1]")
            else:
                c.setAttr(matrix + ".matrixIn[1]", *old_matrix,
                          type="matrix")
            c.connectAttr(matrix + ".matrixSum", target)
        else:
            c.connectAttr(blend + ".output", body + ".scale")

    def capture_fit_part_toe_scale(self, toe: FitPartToeScale) -> bool:
        c = self._cmds
        body = self._unique_fit_part_joint(toe.body_name)
        if (not c.objExists(toe.blend_name)
                or c.nodeType(toe.blend_name) != "blendColors"
                or c.connectionInfo(toe.blend_name + ".color2",
                    sourceFromDestination=True) != toe.fk_scale_plug
                or c.connectionInfo(toe.blend_name + ".blender",
                    sourceFromDestination=True) != toe.mode_plug
                or any(abs(float(value) - 1.0) > 1e-8 for value in
                       c.getAttr(toe.blend_name + ".color1")[0])):
            return False
        if not toe.use_offset_parent_matrix:
            return c.connectionInfo(body + ".scale",
                sourceFromDestination=True) == toe.output_plug
        if (not c.objExists(toe.scale_compose_name)
                or c.nodeType(toe.scale_compose_name) != "composeMatrix"
                or not c.objExists(toe.scale_matrix_name)
                or c.nodeType(toe.scale_matrix_name) != "multMatrix"
                or c.connectionInfo(body + ".offsetParentMatrix",
                    sourceFromDestination=True)
                    != toe.scale_matrix_name + ".matrixSum"
                or c.connectionInfo(toe.scale_matrix_name + ".matrixIn[0]",
                    sourceFromDestination=True)
                    != toe.scale_compose_name + ".outputMatrix"):
            return False
        return all(c.connectionInfo(toe.scale_compose_name
                   + ".inputScale" + axis, sourceFromDestination=True)
                   == toe.blend_name + ".output" + color
                   for axis, color in zip("XYZ", "RGB"))

    def preflight_fit_part_end_scale(self, end: FitPartEndScale) -> None:
        c = self._cmds
        body = self._unique_fit_part_joint(end.body_name)
        ik_driver = self._unique_fit_part_joint(end.ik_driver_name)
        if any(not c.objExists(plug) for plug in (
                end.fk_scale_plug, end.ik_scale_plug, end.mode_plug)):
            raise ValueError("Fit Part 末端缺少 FK／IK 缩放输入："
                             + end.body_name)
        if any(not c.getAttr(ik_driver + ".scale" + axis,
                             settable=True) for axis in "XYZ"):
            raise ValueError("Fit Part 末端 IK 驱动缩放目标不可写："
                             + end.ik_driver_name)
        if any(c.objExists(name) for name in (
                end.blend_name, end.scale_compose_name,
                end.scale_matrix_name) if name):
            raise ValueError("Fit Part 末端缩放节点名称冲突：" + end.body_name)
        if end.use_offset_parent_matrix:
            if (not end.scale_compose_name or not end.scale_matrix_name
                    or not c.objExists(body + ".offsetParentMatrix")):
                raise ValueError("Fit Part 末端缺少 OPM 矩阵目标："
                                 + end.body_name)
        elif any(not c.getAttr(body + ".scale" + axis,
                               settable=True) for axis in "XYZ"):
            raise ValueError("Fit Part 末端 Body 缩放目标不可写："
                             + end.body_name)

    def connect_fit_part_end_scale(self, end: FitPartEndScale) -> None:
        self._require_transaction()
        c = self._cmds
        body = self._unique_fit_part_joint(end.body_name)
        ik_driver = self._unique_fit_part_joint(end.ik_driver_name)
        blend = c.createNode("blendColors", name=end.blend_name)
        self._transaction_changed = True
        c.connectAttr(end.ik_scale_plug, ik_driver + ".scale")
        for color, source_axis in zip("RGB", end.ik_axes):
            c.connectAttr(end.ik_scale_plug + source_axis,
                          blend + ".color1" + color)
        c.connectAttr(end.fk_scale_plug, blend + ".color2")
        c.connectAttr(end.mode_plug, blend + ".blender")
        if end.use_offset_parent_matrix:
            target = body + ".offsetParentMatrix"
            old_source = c.connectionInfo(target,
                                          sourceFromDestination=True)
            old_matrix = c.getAttr(target)
            if old_matrix and isinstance(old_matrix[0], (tuple, list)):
                old_matrix = old_matrix[0]
            compose = c.createNode("composeMatrix",
                                   name=end.scale_compose_name)
            matrix = c.createNode("multMatrix",
                                  name=end.scale_matrix_name)
            for axis, color in zip("XYZ", "RGB"):
                c.connectAttr(blend + ".output" + color,
                              compose + ".inputScale" + axis)
            c.connectAttr(compose + ".outputMatrix",
                          matrix + ".matrixIn[0]")
            if old_source:
                c.disconnectAttr(old_source, target)
                c.connectAttr(old_source, matrix + ".matrixIn[1]")
            else:
                c.setAttr(matrix + ".matrixIn[1]", *old_matrix,
                          type="matrix")
            c.connectAttr(matrix + ".matrixSum", target)
        else:
            c.connectAttr(blend + ".output", body + ".scale")

    def capture_fit_part_end_scale(self, end: FitPartEndScale) -> bool:
        c = self._cmds
        body = self._unique_fit_part_joint(end.body_name)
        ik_driver = self._unique_fit_part_joint(end.ik_driver_name)
        if (not c.objExists(end.blend_name)
                or c.nodeType(end.blend_name) != "blendColors"
                or c.connectionInfo(ik_driver + ".scale",
                    sourceFromDestination=True) != end.ik_scale_plug):
            return False
        links = [
            (end.ik_scale_plug + source_axis,
             end.blend_name + ".color1" + color)
            for color, source_axis in zip("RGB", end.ik_axes)
        ] + [
            (end.fk_scale_plug, end.blend_name + ".color2"),
            (end.mode_plug, end.blend_name + ".blender"),
        ]
        if any(c.connectionInfo(target, sourceFromDestination=True)
               != source for source, target in links):
            return False
        if not end.use_offset_parent_matrix:
            return c.connectionInfo(body + ".scale",
                sourceFromDestination=True) == end.output_plug
        if (not c.objExists(end.scale_compose_name)
                or c.nodeType(end.scale_compose_name) != "composeMatrix"
                or not c.objExists(end.scale_matrix_name)
                or c.nodeType(end.scale_matrix_name) != "multMatrix"
                or c.connectionInfo(body + ".offsetParentMatrix",
                    sourceFromDestination=True)
                    != end.scale_matrix_name + ".matrixSum"
                or c.connectionInfo(end.scale_matrix_name + ".matrixIn[0]",
                    sourceFromDestination=True)
                    != end.scale_compose_name + ".outputMatrix"):
            return False
        return all(c.connectionInfo(end.scale_compose_name
                   + ".inputScale" + axis, sourceFromDestination=True)
                   == end.blend_name + ".output" + color
                   for axis, color in zip("XYZ", "RGB"))

    def inspect_fit_part_inherited_scale(
        self, chain: FitPartInheritedScaleChain
    ) -> bool:
        c = self._cmds
        allowed_parents = {chain.start_body_name, *chain.part_names}
        self._unique_fit_part_joint(chain.start_body_name)
        for name in chain.part_names:
            part = self._unique_fit_part_joint(name)
            parent = c.listRelatives(part, parent=True,
                                     fullPath=True) or []
            if (len(parent) != 1
                    or parent[0].rsplit("|", 1)[-1]
                    not in allowed_parents - {name}
                    or c.getAttr(part + ".segmentScaleCompensate")):
                return False
            for axis in "XYZ":
                scale = part + ".scale" + axis
                if (abs(float(c.getAttr(scale)) - 1.0) > 1e-8
                        or c.connectionInfo(scale,
                            sourceFromDestination=True)):
                    return False
        return True

    def preflight_body_direct_fk_scale(
        self, spec: BodyDirectFkScaleSpec
    ) -> None:
        c = self._cmds
        body = self._unique_fit_part_joint(
            spec.body_joint.rsplit("|", 1)[-1])
        if body != spec.body_joint or not self._is_owned_body_or_mechanism(body):
            raise ValueError("FK 缩放需要本工程 Body：" + spec.body_joint)
        for axis in "XYZ":
            source = spec.source_scale + axis
            destination = body + ".scale" + axis
            if (not c.objExists(source)
                    or not c.getAttr(destination, settable=True)
                    or c.connectionInfo(destination,
                        sourceFromDestination=True)):
                raise ValueError("Body FK 缩放来源或目标不可用："
                                 + spec.body_joint)

    def connect_body_direct_fk_scale(
        self, spec: BodyDirectFkScaleSpec
    ) -> None:
        self._require_transaction()
        c = self._cmds
        body = self._unique_fit_part_joint(
            spec.body_joint.rsplit("|", 1)[-1])
        for axis in "XYZ":
            c.connectAttr(spec.source_scale + axis,
                          body + ".scale" + axis)
        self._transaction_changed = True

    def capture_body_direct_fk_scale(
        self, spec: BodyDirectFkScaleSpec
    ) -> bool:
        c = self._cmds
        body = self._unique_fit_part_joint(
            spec.body_joint.rsplit("|", 1)[-1])
        return all(c.isConnected(spec.source_scale + axis,
                   body + ".scale" + axis)
                   for axis in "XYZ")

    def preflight_fit_part_limb_scale(
        self, chain: FitPartLimbScaleChain
    ) -> None:
        c = self._cmds
        required = (chain.fk_scale_plug, chain.volume_plug,
                    chain.mode_plug, chain.fatness_control)
        if any(not c.objExists(plug) for plug in required):
            raise ValueError("Fit Part 四肢缩放缺少控制或体积输入："
                             + chain.start_body_name)
        if any(c.objExists(name) for name in
               (chain.blend_name, chain.fatness_add_name,
                chain.scale_compose_name, chain.scale_matrix_name) if name):
            raise ValueError("Fit Part 四肢缩放节点名称冲突："
                             + chain.start_body_name)
        if chain.use_offset_parent_matrix:
            body = self._unique_fit_part_joint(chain.start_body_name)
            if not c.objExists(body + ".offsetParentMatrix"):
                raise ValueError("Fit Part OPM 缺少 Body 矩阵目标："
                                 + chain.start_body_name)
        else:
            body = self._unique_fit_part_joint(chain.start_body_name)
            if any(not c.getAttr(body + ".scale" + axis, settable=True)
                   for axis in "XYZ"):
                raise ValueError("Fit Part 四肢 Body 缩放目标不可写："
                                 + chain.start_body_name)
        for name in chain.part_names:
            part = self._unique_fit_part_joint(name)
            if (bool(c.getAttr(part + ".segmentScaleCompensate"))
                    == chain.use_offset_parent_matrix):
                raise ValueError("Fit Part 四肢缩放目标不可写：" + name)
            if not chain.use_offset_parent_matrix and any(
                    not c.getAttr(part + ".scale" + axis,
                                  settable=True) for axis in "XYZ"):
                raise ValueError("Fit Part 四肢缩放目标不可写：" + name)

    def connect_fit_part_limb_scale(
        self, chain: FitPartLimbScaleChain
    ) -> None:
        self._require_transaction()
        c = self._cmds
        control_attr = chain.fatness_control + "." + chain.fatness_attribute
        if not c.objExists(control_attr):
            c.addAttr(chain.fatness_control,
                      longName=chain.fatness_attribute,
                      attributeType="double", defaultValue=0.0,
                      keyable=True)
        blend = c.createNode("blendColors", name=chain.blend_name)
        fatness = c.createNode("plusMinusAverage",
                               name=chain.fatness_add_name)
        self._transaction_changed = True
        c.setAttr(blend + ".color1", 1.0, 1.0, 1.0)
        c.connectAttr(chain.volume_plug, blend + ".color1R")
        c.connectAttr(chain.volume_plug, fatness + ".input1D[0]")
        c.connectAttr(control_attr, fatness + ".input1D[1]")
        for color in "GB":
            c.connectAttr(fatness + ".output1D",
                          blend + ".color1" + color)
        c.connectAttr(chain.fk_scale_plug, blend + ".color2")
        c.connectAttr(chain.mode_plug, blend + ".blender")
        if chain.use_offset_parent_matrix:
            body = self._unique_fit_part_joint(chain.start_body_name)
            target = body + ".offsetParentMatrix"
            old_source = c.connectionInfo(target,
                                          sourceFromDestination=True)
            old_matrix = c.getAttr(target)
            if old_matrix and isinstance(old_matrix[0], (tuple, list)):
                old_matrix = old_matrix[0]
            compose = c.createNode("composeMatrix",
                                   name=chain.scale_compose_name)
            matrix = c.createNode("multMatrix",
                                  name=chain.scale_matrix_name)
            for axis, color in zip("XYZ", "RGB"):
                c.connectAttr(blend + ".output" + color,
                              compose + ".inputScale" + axis)
            c.connectAttr(compose + ".outputMatrix",
                          matrix + ".matrixIn[0]")
            if old_source:
                c.disconnectAttr(old_source, target)
                c.connectAttr(old_source, matrix + ".matrixIn[1]")
            else:
                c.setAttr(matrix + ".matrixIn[1]", *old_matrix,
                          type="matrix")
            c.connectAttr(matrix + ".matrixSum", target)
        else:
            body = self._unique_fit_part_joint(chain.start_body_name)
            c.connectAttr(blend + ".output", body + ".scale")
            for name in chain.part_names:
                part = self._unique_fit_part_joint(name)
                c.connectAttr(blend + ".output", part + ".scale")

    def capture_fit_part_limb_scale(
        self, chain: FitPartLimbScaleChain
    ) -> bool:
        c = self._cmds
        control = chain.fatness_control + "." + chain.fatness_attribute
        if (not c.objExists(control)
                or not c.getAttr(control, keyable=True)
                or not c.getAttr(control, settable=True)
                or abs(float(c.getAttr(control))) > 1e-8
                or not c.objExists(chain.fatness_add_name)
                or c.nodeType(chain.fatness_add_name)
                != "plusMinusAverage"
                or not c.objExists(chain.blend_name)
                or c.nodeType(chain.blend_name) != "blendColors"):
            return False
        links = (
            (chain.volume_plug, chain.blend_name + ".color1R"),
            (chain.volume_plug,
             chain.fatness_add_name + ".input1D[0]"),
            (control, chain.fatness_add_name + ".input1D[1]"),
            (chain.fatness_add_name + ".output1D",
             chain.blend_name + ".color1G"),
            (chain.fatness_add_name + ".output1D",
             chain.blend_name + ".color1B"),
            (chain.fk_scale_plug, chain.blend_name + ".color2"),
            (chain.mode_plug, chain.blend_name + ".blender"),
        )
        if any(c.connectionInfo(target, sourceFromDestination=True)
               != source for source, target in links):
            return False
        if chain.use_offset_parent_matrix:
            body = self._unique_fit_part_joint(chain.start_body_name)
            if c.connectionInfo(body + ".offsetParentMatrix",
                    sourceFromDestination=True) != chain.scale_matrix_name + ".matrixSum":
                return False
            if c.connectionInfo(chain.scale_matrix_name + ".matrixIn[0]",
                    sourceFromDestination=True) != (
                    chain.scale_compose_name + ".outputMatrix"):
                return False
            return all(c.connectionInfo(chain.scale_compose_name
                       + ".inputScale" + axis, sourceFromDestination=True)
                       == chain.blend_name + ".output" + color
                       for axis, color in zip("XYZ", "RGB"))
        return all(c.connectionInfo(self._unique_fit_part_joint(name)
                   + ".scale", sourceFromDestination=True)
                   == chain.output_plug
                   for name in (chain.start_body_name, *chain.part_names))

    def preflight_fit_part_scale(self, step: FitPartScaleStep) -> None:
        c = self._cmds
        part = self._unique_fit_part_joint(step.part_name)
        self._unique_fit_part_joint(step.start_body_name)
        if (c.getAttr(part + ".segmentScaleCompensate") != 1
                or not c.objExists(step.source_plug)
                or any(not c.getAttr(part + ".scale" + axis, settable=True)
                       for axis in "XYZ")):
            raise ValueError("Fit Part 缩放来源或目标不可用：" + step.part_name)

    def connect_fit_part_scale(self, step: FitPartScaleStep) -> None:
        self._require_transaction()
        self._cmds.connectAttr(step.source_plug, step.target_plug)
        self._transaction_changed = True

    def capture_fit_part_scale_source(
        self, step: FitPartScaleStep
    ) -> str | None:
        return (step.source_plug if self._cmds.isConnected(
            step.source_plug, step.target_plug) else None)

    def _unique_fit_part_joint(self, name: str) -> str:
        matches = self._cmds.ls(name, long=True, type="joint") or []
        if len(matches) != 1:
            raise ValueError("Fit Part 需要唯一关节名称：" + name)
        return matches[0]

    def _is_owned_body_or_mechanism(self, path: str) -> bool:
        """Body receivers and FK/IK mechanisms have distinct creator markers."""
        c = self._cmds
        return (c.objExists(path + ".advPySourceJoint")
                or (c.objExists(path + ".advPySkinEnabled")
                    and c.objExists(path + ".advPyFitHasDeformProfile")))

    def preflight_fit_part_hierarchy(
        self,
        joints: tuple[FitPartJointSpec, ...],
        reparents: tuple[FitPartReparentSpec, ...],
    ) -> None:
        c = self._cmds
        planned_names = {item.name for item in joints}
        for spec in joints:
            if spec.kind not in ("twist", "inbetween"):
                raise ValueError("Fit Part 类型无效：" + spec.name)
            self._unique_fit_part_joint(spec.start_body_name)
            end = self._unique_fit_part_joint(spec.end_body_name)
            if spec.kind == "twist" and not isfinite(float(c.getAttr(
                    end + ".translateX"))):
                raise ValueError("Fit Part 下游局部长度无效："
                                 + spec.end_body_name)
            if (spec.parent_name not in planned_names
                    and spec.parent_name != spec.start_body_name):
                raise ValueError("Fit Part 父关节不在构建计划中：" + spec.name)
        for spec in reparents:
            child = self._unique_fit_part_joint(spec.child_name)
            if spec.parent_part_name not in planned_names:
                raise ValueError("Fit Part 改挂父关节不在构建计划中："
                                 + spec.parent_part_name)
            if spec.reason == "end_of_chain":
                if (not spec.segment_parts
                        or spec.segment_parts[-1] != spec.parent_part_name
                        or spec.segment_index != len(spec.segment_parts)
                        or len(set(spec.segment_parts)) != len(spec.segment_parts)
                        or not set(spec.segment_parts) <= planned_names):
                    raise ValueError("Fit Part 段长分配计划不完整："
                                     + spec.child_name)
                divider = ("AdvPy_" + spec.parent_part_name
                           + "_SegmentDistance")
                if c.objExists(divider):
                    raise ValueError("Fit Part 段长节点名称冲突：" + divider)
            elif spec.reason == "child_of_part" and spec.segment_parts:
                if (not 1 <= spec.segment_index <= len(spec.segment_parts)
                        or spec.segment_parts[spec.segment_index - 1]
                        != spec.parent_part_name):
                    raise ValueError("ChildOfPart 段长计划与目标 Part 不一致："
                                     + spec.child_name)
                residual = "AdvPy_" + spec.child_name + "_ChildOfPartDistance"
                if (spec.segment_index < len(spec.segment_parts)
                        and c.objExists(residual)):
                    raise ValueError("ChildOfPart 段长节点名称冲突：" + residual)
            # A bound joint must not move beneath a new influence hierarchy.
            if c.listConnections(child, type="skinCluster"):
                raise ValueError("Fit Part 改挂必须在 Skin 绑定前执行："
                                 + spec.child_name)

    def create_fit_part_joint(self, spec: FitPartJointSpec) -> None:
        self._require_transaction()
        c = self._cmds
        parent = self._unique_fit_part_joint(spec.parent_name)
        joint = c.createNode("joint", name=spec.name, parent=parent,
                             skipSelect=True)
        joint = self._unique_fit_part_joint(spec.name)
        self._transaction_changed = True
        c.setAttr(joint + ".rotateOrder", spec.rotation_order)
        c.setAttr(joint + ".side", {
            FitBuildSide.MIDDLE: 0,
            FitBuildSide.LEFT: 1,
            FitBuildSide.RIGHT: 2,
        }[spec.side])
        c.setAttr(joint + ".segmentScaleCompensate",
                  spec.segment_scale_compensate)
        if (spec.segment_scale_compensate
                and not c.connectionInfo(joint + ".inverseScale",
                                         sourceFromDestination=True)):
            # MEL's `joint` command wires this automatically.  A joint
            # created with createNode may otherwise inherit parent scale
            # twice in the non-OPM Part chain.
            c.connectAttr(parent + ".scale", joint + ".inverseScale")
        if spec.kind == "twist":
            # The MEL Part pass places every segment at the downstream
            # Body's pre-reparent local X distance divided by N + 1.
            end = self._unique_fit_part_joint(spec.end_body_name)
            distance = float(c.getAttr(end + ".translateX"))
            if not isfinite(distance):
                raise ValueError("Fit Part 下游局部长度无效：" + spec.end_body_name)
            c.setAttr(joint + ".translateX", distance / (spec.count + 1))
            position = c.xform(joint, query=True, worldSpace=True,
                               translation=True)
            if any(abs(float(actual) - planned) > 1e-4
                   for actual, planned in zip(position, spec.world_position)):
                raise RuntimeError("Fit Part 局部段长与 Body 朝向不一致："
                                   + spec.name)
        else:
            c.xform(joint, worldSpace=True, translation=spec.world_position)
        c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind",
                  dataType="string")
        marker = (_FIT_INBETWEEN_KIND if spec.kind == "inbetween"
                  else _FIT_PART_KIND)
        c.setAttr(joint + ".advPyAuxiliaryInfluenceKind", marker,
                  type="string", lock=True)
        c.addAttr(joint, longName="advPySkinEnabled", attributeType="bool",
                  defaultValue=spec.skin_enabled)
        for name, value in (
            ("fat", spec.deform_profile.fat),
            ("fatFront", spec.deform_profile.fat_front),
            ("fatWidth", spec.deform_profile.fat_width),
        ):
            c.addAttr(joint, longName=name, attributeType="double",
                      minValue=0.0, defaultValue=value, keyable=False)

    def reparent_fit_part_child(self, spec: FitPartReparentSpec) -> None:
        self._require_transaction()
        c = self._cmds
        child = self._unique_fit_part_joint(spec.child_name)
        parent = self._unique_fit_part_joint(spec.parent_part_name)
        # The limb rig may already drive the full start-to-end distance.
        # Detach that source while Maya preserves the bind pose during the
        # parent operation, then distribute it over all chain intervals.
        segment_sources = {}
        if spec.reason == "end_of_chain":
            for axis in "XYZ":
                destination = child + ".translate" + axis
                source = c.connectionInfo(destination,
                                          sourceFromDestination=True)
                if source:
                    segment_sources[axis] = source
                    c.disconnectAttr(source, destination)
        elif spec.reason == "child_of_part" and spec.segment_parts:
            divider = ("AdvPy_" + spec.segment_parts[-1]
                       + "_SegmentDistance")
            for axis in "XYZ":
                destination = child + ".translate" + axis
                source = c.connectionInfo(destination,
                                          sourceFromDestination=True)
                if source and source.rsplit("|", 1)[-1] == (
                        divider + ".output" + axis):
                    segment_sources[axis] = source
                    c.disconnectAttr(source, destination)
        # Parenting preserves the child's world transform. Resolve names
        # again on each call because every reparent changes descendant paths.
        c.parent(child, world=True)
        child = self._unique_fit_part_joint(spec.child_name)
        parent = self._unique_fit_part_joint(spec.parent_part_name)
        c.parent(child, parent)
        child = self._unique_fit_part_joint(spec.child_name)
        if (c.getAttr(child + ".segmentScaleCompensate")
                and not c.isConnected(parent + ".scale",
                                      child + ".inverseScale")):
            # The newly inserted Part is now the compensation parent.
            # Reparenting may leave an inverseScale link to the old Body.
            old_scale = c.connectionInfo(child + ".inverseScale",
                                         sourceFromDestination=True)
            if old_scale:
                c.disconnectAttr(old_scale, child + ".inverseScale")
            c.connectAttr(parent + ".scale", child + ".inverseScale")
        if segment_sources and spec.reason == "end_of_chain":
            divider = c.createNode("multiplyDivide",
                name="AdvPy_" + spec.parent_part_name + "_SegmentDistance")
            factor = 1.0 / (len(spec.segment_parts) + 1)
            c.setAttr(divider + ".input2", factor, factor, factor)
            for axis, source in segment_sources.items():
                c.connectAttr(source, divider + ".input1" + axis)
                for name in (*spec.segment_parts, spec.child_name):
                    joint = self._unique_fit_part_joint(name)
                    c.connectAttr(divider + ".output" + axis,
                                  joint + ".translate" + axis)
        elif segment_sources and spec.reason == "child_of_part":
            remaining = len(spec.segment_parts) + 1 - spec.segment_index
            output_by_axis = segment_sources
            if remaining > 1:
                residual = c.createNode("multiplyDivide",
                    name="AdvPy_" + spec.child_name
                    + "_ChildOfPartDistance")
                c.setAttr(residual + ".input2", remaining, remaining,
                          remaining)
                output_by_axis = {}
                for axis, source in segment_sources.items():
                    c.connectAttr(source, residual + ".input1" + axis)
                    output_by_axis[axis] = residual + ".output" + axis
            for axis, source in output_by_axis.items():
                c.connectAttr(source, child + ".translate" + axis)
        self._transaction_changed = True

    def capture_fit_part_joints(
        self, names: tuple[str, ...]
    ) -> tuple[FitPartJointState, ...]:
        c = self._cmds
        result = []
        for name in names:
            joint = self._unique_fit_part_joint(name)
            parent = c.listRelatives(joint, parent=True, fullPath=True) or []
            result.append(FitPartJointState(
                name,
                parent[0].rsplit("|", 1)[-1] if parent else "",
                tuple(float(value) for value in c.xform(
                    joint, query=True, worldSpace=True, translation=True)),
                FitDeformProfile(*(
                    float(c.getAttr(joint + "." + attr))
                    for attr in ("fat", "fatFront", "fatWidth")
                )),
                bool(c.getAttr(joint + ".advPySkinEnabled")),
                int(c.getAttr(joint + ".rotateOrder")),
                bool(c.getAttr(joint + ".segmentScaleCompensate")),
                joint,
                c.connectionInfo(joint + ".inverseScale",
                                 sourceFromDestination=True) or None,
                True,
            ))
        return tuple(result)

    def capture_fit_part_children(
        self, names: tuple[str, ...]
    ) -> tuple[FitPartChildState, ...]:
        c = self._cmds
        result = []
        for name in names:
            child = self._unique_fit_part_joint(name)
            parent = c.listRelatives(child, parent=True, fullPath=True) or []
            result.append(FitPartChildState(
                name, parent[0].rsplit("|", 1)[-1] if parent else "",
                child,
                bool(c.getAttr(child + ".segmentScaleCompensate")),
                c.connectionInfo(child + ".inverseScale",
                                 sourceFromDestination=True) or None))
        return tuple(result)

    def capture_fit_part_body_paths(
        self, names: tuple[str, ...]
    ) -> tuple[tuple[str, str], ...]:
        return tuple((name, self._unique_fit_part_joint(name))
                     for name in names)

    def preflight_fit_part_twist_projection(
        self, projection: FitPartTwistProjection,
        planned_outputs: frozenset[str] = frozenset(),
    ) -> None:
        c = self._cmds
        inputs = projection.input
        plugs = (inputs.rotation_plug, inputs.rotate_order_plug,
                 inputs.up_twist_plug, inputs.ik_rotation_plug,
                 inputs.ik_rotate_order_plug, inputs.ik_fk_blend_plug,
                 inputs.world_matrix_plug,
                 inputs.fk_world_matrix_plug,
                 inputs.ik_world_matrix_plug)
        for plug in plugs:
            if (plug and not (plug == inputs.up_twist_plug
                              and plug in planned_outputs)
                    and not c.objExists(plug)):
                raise ValueError("Fit Part 扭转投影来源不存在：" + plug)
        if (inputs.reference_inverse_plug
                and not c.objExists(inputs.reference_inverse_plug)):
            raise ValueError("Fit Part 参考逆矩阵不存在："
                             + inputs.reference_inverse_plug)
        if (inputs.world_matrix_plug or projection.matrix_blend_name
                or projection.static_source_name):
            if not (projection.reference_name
                    or inputs.reference_inverse_plug):
                raise ValueError("Fit Part 矩阵投影缺少参考逆矩阵")
            matches = c.ls(inputs.start_body, long=True, type="joint") or []
            if matches != [inputs.start_body]:
                raise ValueError("Fit Part 矩阵投影起点关节无效")
            if projection.static_source_name:
                source_parent = inputs.static_parent_body
                if (not source_parent
                        or not self._has_fit_part_parent_chain(
                            inputs.start_body, source_parent)):
                    raise ValueError("静态下游 Twist 来源不在原 Body 父链")
                channels = ("rotate", "rotateX", "rotateY", "rotateZ")
                if (any(c.connectionInfo(inputs.start_body + "." + attr,
                        sourceFromDestination=True) for attr in channels)
                        or c.connectionInfo(
                            inputs.start_body + ".offsetParentMatrix",
                            sourceFromDestination=True)):
                    raise ValueError("Body 已有旋转驱动，不能使用静态 Twist 来源："
                                     + inputs.start_body)
            if projection.reference_name:
                parent = projection.reference_parent_path
                if (parent and ((c.ls(parent, long=True) or [])
                                != [parent]
                                or not self._has_fit_part_parent_chain(
                                    inputs.start_body, parent))):
                    raise ValueError("Fit Part 矩阵参照父级无效")

    def create_fit_part_twist_projection(
        self, projection: FitPartTwistProjection
    ) -> None:
        self._require_transaction()
        c = self._cmds
        source = projection.input
        self._transaction_changed = True

        def create(compose_name: str, decompose_name: str,
                   project_name: str, rotation: str,
                   order: str) -> str:
            compose = c.createNode("composeMatrix", name=compose_name)
            decompose = c.createNode("decomposeMatrix", name=decompose_name)
            project = c.createNode("quatToEuler", name=project_name)
            c.connectAttr(rotation, compose + ".inputRotate")
            c.connectAttr(order, compose + ".inputRotateOrder")
            c.connectAttr(compose + ".outputMatrix",
                          decompose + ".inputMatrix")
            c.connectAttr(decompose + ".outputQuatX",
                          project + ".inputQuatX")
            c.connectAttr(decompose + ".outputQuatW",
                          project + ".inputQuatW")
            return project + ".outputRotateX"

        if (source.world_matrix_plug or projection.matrix_blend_name
                or projection.static_source_name):
            matrix_source = source.world_matrix_plug
            if projection.static_source_name:
                static = c.createNode("transform",
                                      name=projection.static_source_name,
                                      parent=source.static_parent_body,
                                      skipSelect=True)
                c.xform(static, worldSpace=True, matrix=c.xform(
                    source.start_body, query=True, worldSpace=True,
                    matrix=True))
                c.addAttr(static, longName="advPyStaticTwistOwner",
                          dataType="string")
                c.setAttr(static + ".advPyStaticTwistOwner",
                          "adv_py.fit_part_twist.static.v1",
                          type="string", lock=True)
                c.setAttr(static + ".visibility", False)
                matrix_source = static + ".worldMatrix[0]"
            if projection.matrix_blend_name:
                world_blend = c.createNode(
                    "blendMatrix", name=projection.matrix_blend_name)
                c.connectAttr(source.fk_world_matrix_plug,
                              world_blend + ".inputMatrix")
                c.connectAttr(source.ik_world_matrix_plug,
                              world_blend + ".target[0].targetMatrix")
                c.connectAttr(source.ik_fk_blend_plug,
                              world_blend + ".target[0].weight")
                matrix_source = world_blend + ".outputMatrix"
            if projection.reference_name:
                options = ({"parent": projection.reference_parent_path}
                           if projection.reference_parent_path else {})
                reference = c.createNode(
                    "transform", name=projection.reference_name,
                    skipSelect=True, **options)
                c.xform(reference, worldSpace=True, matrix=c.xform(
                    source.start_body, query=True, worldSpace=True,
                    matrix=True))
                c.addAttr(reference, longName="advPyTwistReferenceOwner",
                          dataType="string")
                c.setAttr(reference + ".advPyTwistReferenceOwner",
                          "adv_py.fit_part_twist.v1", type="string", lock=True)
                c.setAttr(reference + ".visibility", False)
            matrix = c.createNode("multMatrix", name=projection.compose_name)
            decompose = c.createNode("decomposeMatrix",
                                     name=projection.decompose_name)
            project = c.createNode("quatToEuler",
                                   name=projection.project_name)
            c.connectAttr(matrix_source,
                          matrix + ".matrixIn[0]")
            c.connectAttr(source.reference_inverse_plug or
                          projection.reference_name + ".worldInverseMatrix[0]",
                          matrix + ".matrixIn[1]")
            c.connectAttr(matrix + ".matrixSum",
                          decompose + ".inputMatrix")
            c.connectAttr(source.rotate_order_plug,
                          decompose + ".inputRotateOrder")
            c.connectAttr(decompose + ".outputQuatX",
                          project + ".inputQuatX")
            c.connectAttr(decompose + ".outputQuatW",
                          project + ".inputQuatW")
            fk_output = project + ".outputRotateX"
        else:
            fk_output = create(
                projection.compose_name, projection.decompose_name,
                projection.project_name, source.rotation_plug,
                source.rotate_order_plug)
        if projection.blend_name:
            ik_output = create(
                projection.ik_compose_name,
                projection.ik_decompose_name,
                projection.ik_project_name,
                source.ik_rotation_plug,
                source.ik_rotate_order_plug)
            blend = c.createNode("blendTwoAttr", name=projection.blend_name)
            c.connectAttr(fk_output, blend + ".input[0]")
            c.connectAttr(ik_output, blend + ".input[1]")
            c.connectAttr(source.ik_fk_blend_plug,
                          blend + ".attributesBlender")

    def capture_fit_part_projection_output(
        self, projection: FitPartTwistProjection
    ) -> str | None:
        c = self._cmds
        output = projection.output_plug
        if not c.objExists(output):
            return None
        def has_projection_graph(compose: str, decompose: str,
                                 project: str, rotation: str,
                                 order: str) -> bool:
            if any(not c.objExists(name) or c.nodeType(name) != kind
                   for name, kind in ((compose, "composeMatrix"),
                                      (decompose, "decomposeMatrix"),
                                      (project, "quatToEuler"))):
                return False
            expected = (
                (rotation, compose + ".inputRotate"),
                (order, compose + ".inputRotateOrder"),
                (compose + ".outputMatrix",
                 decompose + ".inputMatrix"),
                (decompose + ".outputQuatX",
                 project + ".inputQuatX"),
                (decompose + ".outputQuatW",
                 project + ".inputQuatW"),
            )
            return all(c.isConnected(source, target)
                       for source, target in expected)

        source = projection.input
        if source.reference_inverse_plug:
            from .maya_source_part_reference import audit
            audit(self, source.reference_inverse_plug.split('.', 1)[0])
        if (source.world_matrix_plug or projection.matrix_blend_name
                or projection.static_source_name):
            reference = projection.reference_name
            matrix = projection.compose_name
            decompose = projection.decompose_name
            project = projection.project_name
            parent = (c.listRelatives(reference, parent=True,
                                     fullPath=True) or []
                      if reference else [])
            matrix_source = (projection.matrix_blend_name + ".outputMatrix"
                             if projection.matrix_blend_name else
                             projection.static_source_name + ".worldMatrix[0]"
                             if projection.static_source_name else
                             source.world_matrix_plug)
            expected = (
                (matrix_source, matrix + ".matrixIn[0]"),
                (source.reference_inverse_plug or
                 reference + ".worldInverseMatrix[0]",
                 matrix + ".matrixIn[1]"),
                (matrix + ".matrixSum", decompose + ".inputMatrix"),
                (source.rotate_order_plug,
                 decompose + ".inputRotateOrder"),
                (decompose + ".outputQuatX", project + ".inputQuatX"),
                (decompose + ".outputQuatW", project + ".inputQuatW"),
            )
            if (any(not c.objExists(name) or c.nodeType(name) != kind
                    for name, kind in (
                        (matrix, "multMatrix"),
                        (decompose, "decomposeMatrix"),
                        (project, "quatToEuler")))
                    or (reference is not None and (
                        not c.objExists(reference)
                        or c.nodeType(reference) != "transform"
                        or parent != ([projection.reference_parent_path]
                                      if projection.reference_parent_path else [])
                        or not c.objExists(
                            reference + ".advPyTwistReferenceOwner")
                        or c.getAttr(reference + ".advPyTwistReferenceOwner")
                        != "adv_py.fit_part_twist.v1"
                        or c.getAttr(reference + ".visibility")
                        or max(abs(float(a) - float(b)) for a, b in zip(
                            c.xform(reference, query=True, worldSpace=True,
                                    matrix=True),
                            c.xform(source.start_body, query=True,
                                    worldSpace=True, matrix=True))) > 1e-4))
                    or any(not c.isConnected(upstream, target)
                           for upstream, target in expected)):
                return None
            if projection.matrix_blend_name:
                blend = projection.matrix_blend_name
                if (not c.objExists(blend)
                        or c.nodeType(blend) != "blendMatrix"
                        or any(not c.isConnected(upstream, target)
                               for upstream, target in (
                                   (source.fk_world_matrix_plug,
                                    blend + ".inputMatrix"),
                                   (source.ik_world_matrix_plug,
                                    blend + ".target[0].targetMatrix"),
                                   (source.ik_fk_blend_plug,
                                    blend + ".target[0].weight")))):
                    return None
            if projection.static_source_name:
                static = projection.static_source_name
                if not c.objExists(static) or c.nodeType(static) != "transform":
                    return None
                static_parent = c.listRelatives(
                    static, parent=True, fullPath=True) or []
                if (static_parent != [source.static_parent_body]
                        or not c.objExists(static + ".advPyStaticTwistOwner")
                        or c.getAttr(static + ".advPyStaticTwistOwner")
                        != "adv_py.fit_part_twist.static.v1"
                        or not c.getAttr(static + ".advPyStaticTwistOwner",
                                         lock=True)
                        or c.getAttr(static + ".visibility")
                        or max(abs(float(a) - float(b)) for a, b in zip(
                            c.xform(static, query=True, worldSpace=True,
                                    matrix=True),
                            c.xform(source.start_body, query=True,
                                    worldSpace=True, matrix=True))) > 1e-4):
                    return None
        elif not has_projection_graph(
                projection.compose_name, projection.decompose_name,
                projection.project_name, source.rotation_plug,
                source.rotate_order_plug):
            return None
        if projection.blend_name:
            if (not c.objExists(projection.blend_name)
                    or c.nodeType(projection.blend_name) != "blendTwoAttr"
                    or not has_projection_graph(
                        projection.ik_compose_name,
                        projection.ik_decompose_name,
                        projection.ik_project_name,
                        source.ik_rotation_plug,
                        source.ik_rotate_order_plug)):
                return None
            expected = (
                projection.project_name + ".outputRotateX",
                projection.ik_project_name + ".outputRotateX",
                source.ik_fk_blend_plug,
            )
            destinations = (
                projection.blend_name + ".input[0]",
                projection.blend_name + ".input[1]",
                projection.blend_name + ".attributesBlender",
            )
            if any(not c.isConnected(source, destination,
                                     ignoreUnitConversion=source.endswith('.outputRotateX'))
                   for destination, source in zip(destinations, expected)):
                return None
        return output

    def capture_reparented_fit_part_static_source(
        self, projection: FitPartTwistProjection,
        parent_path: str, child_path: str,
    ) -> bool:
        c = self._cmds
        static = projection.static_source_name
        reference = projection.reference_name
        if (not static or not reference
                or any(not c.objExists(name) or c.nodeType(name) != "transform"
                       for name in (static, reference))
                or (c.ls(child_path, long=True, type="joint") or [])
                != [child_path]
                or not self._has_fit_part_parent_chain(
                    child_path, parent_path)
                or (c.listRelatives(child_path, parent=True,
                                    fullPath=True) or []) == [parent_path]):
            return False
        if any((c.listRelatives(name, parent=True,
                                fullPath=True) or []) != [parent_path]
               for name in (static, reference)):
            return False
        if (c.connectionInfo(projection.compose_name + ".matrixIn[0]",
                             sourceFromDestination=True)
                != static + ".worldMatrix[0]"
                or c.connectionInfo(projection.compose_name + ".matrixIn[1]",
                                    sourceFromDestination=True)
                != reference + ".worldInverseMatrix[0]"):
            return False
        child_matrix = c.xform(child_path, query=True, worldSpace=True,
                               matrix=True)
        return all(
            max(abs(float(a) - float(b)) for a, b in zip(
                c.xform(name, query=True, worldSpace=True, matrix=True),
                child_matrix)) <= 1e-4
            for name in (static, reference))

    def preflight_fit_part_twist_control_rewire(
        self, spec: FitPartTwistControlRewire,
    ) -> None:
        c = self._cmds
        if ((c.ls(spec.start_body, long=True, type="joint") or [])
                != [spec.start_body]
                or (c.ls(spec.control_source_path, long=True,
                         type="transform") or [])
                != [spec.control_source_path]
                or not c.objExists(spec.static_source_name)
                or c.nodeType(spec.static_source_name) != "transform"
                or not c.objExists(spec.compose_name)
                or c.nodeType(spec.compose_name) != "multMatrix"
                or c.connectionInfo(spec.matrix_input,
                                    sourceFromDestination=True)
                != spec.static_source_name + ".worldMatrix[0]"
                or (c.listConnections(
                        spec.static_source_name + ".worldMatrix[0]",
                        source=False, destination=True, plugs=True) or [])
                != [spec.matrix_input]):
            raise ValueError("通用 Twist 静态来源无法改接 FK："
                             + spec.start_body)
        old = c.xform(spec.static_source_name, query=True,
                      worldSpace=True, matrix=True)
        new = c.xform(spec.control_source_path, query=True,
                      worldSpace=True, matrix=True)
        if (len(old) != 16 or len(new) != 16
                or max(abs(float(a) - float(b))
                       for a, b in zip(old[12:15], new[12:15])) > 1e-4):
            raise ValueError("通用 Twist FK 来源与绑定静态姿态不一致："
                             + spec.start_body)

    def connect_fit_part_twist_control_rewire(
        self, spec: FitPartTwistControlRewire,
    ) -> None:
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        c.disconnectAttr(spec.static_source_name + ".worldMatrix[0]",
                         spec.matrix_input)
        c.connectAttr(spec.control_matrix, spec.matrix_input)
        c.delete(spec.static_source_name)

    def capture_fit_part_twist_control_rewire(
        self, spec: FitPartTwistControlRewire,
    ) -> bool:
        c = self._cmds
        return (not c.objExists(spec.static_source_name)
                and c.connectionInfo(spec.matrix_input,
                                     sourceFromDestination=True)
                == spec.control_matrix)

    def preflight_fit_part_twist_step(self, step: FitPartTwistStep) -> None:
        c = self._cmds
        part = self._unique_fit_part_joint(step.part_name)
        marker = part + ".advPyAuxiliaryInfluenceKind"
        if not c.objExists(marker) or c.getAttr(marker) != _FIT_PART_KIND:
            raise ValueError("Fit Part 扭转需要本工程创建的关节："
                             + step.part_name)
        if not c.objExists(step.down_twist_plug):
            raise ValueError("Fit Part 下游扭转来源不存在："
                             + step.down_twist_plug)
        if step.up_twist_plug and not c.objExists(step.up_twist_plug):
            raise ValueError("Fit Part 上游扭转来源不存在："
                             + step.up_twist_plug)
        target = ("offsetParentMatrix" if step.use_offset_parent_matrix
                  else "rotateX")
        if (c.attributeQuery("twistAmount", node=part, exists=True)
                or c.attributeQuery("twistAddition", node=part, exists=True)
                or not c.getAttr(part + "." + target, settable=True)):
            raise ValueError("Fit Part 扭转目标不可写：" + step.part_name)
        if step.use_offset_parent_matrix and any(
                not c.getAttr(part + "." + attr, settable=True)
                for attr in ("rotateX", "rotateY", "rotateZ")):
            raise ValueError("Fit Part OPM 需要可写的局部平移和旋转："
                             + step.part_name)
        if step.compensate_start_body:
            body_name = step.start_body.rsplit("|", 1)[-1]
            bodies = c.ls(body_name, long=True, type="joint") or []
            constraint = step.body_constraint_name
            if (len(bodies) != 1
                    or bodies[0] != step.start_body
                    or not self._is_owned_body_or_mechanism(bodies[0])
                    or not c.objExists(constraint)
                    or c.nodeType(constraint) != "orientConstraint"
                    or not c.isConnected(
                        constraint + ".constraintRotateX",
                        bodies[0] + ".rotateX")
                    or c.attributeQuery("twistAmount", node=bodies[0],
                                        exists=True)
                    or c.attributeQuery("twistAddition", node=bodies[0],
                                        exists=True)
                    or not c.getAttr(constraint + ".offsetX",
                                     settable=True)
                    or abs(float(c.getAttr(constraint + ".offsetX")))
                    > 1e-8):
                raise ValueError("Body 第零段扭转接收端无效：" + body_name)

    def create_fit_part_twist_step(self, step: FitPartTwistStep) -> None:
        self._require_transaction()
        c = self._cmds
        part = self._unique_fit_part_joint(step.part_name)
        self._transaction_changed = True
        if step.compensate_start_body:
            body_name = step.start_body.rsplit("|", 1)[-1]
            body = (c.ls(body_name, long=True, type="joint") or [])[0]
            constraint = step.body_constraint_name
            weight_name, amount_name, offset_name = (
                step.body_compensation_nodes)
            c.addAttr(body, longName="twistAmount",
                      attributeType="double", minValue=0.0,
                      maxValue=1.0, defaultValue=0.0, keyable=True)
            c.addAttr(body, longName="twistAddition",
                      attributeType="double", defaultValue=0.0,
                      keyable=True)
            c.createNode("plusMinusAverage", name=weight_name)
            c.createNode("multDoubleLinear", name=amount_name)
            c.createNode("plusMinusAverage", name=offset_name)
            c.connectAttr(body + ".twistAmount",
                          weight_name + ".input1D[0]")
            c.setAttr(weight_name + ".input1D[1]", -1.0)
            c.connectAttr(step.down_twist_plug,
                          amount_name + ".input1")
            c.connectAttr(weight_name + ".output1D",
                          amount_name + ".input2")
            c.connectAttr(amount_name + ".output",
                          offset_name + ".input1D[0]")
            c.connectAttr(body + ".twistAddition",
                          offset_name + ".input1D[1]")
            c.connectAttr(offset_name + ".output1D",
                          constraint + ".offsetX")
        c.addAttr(part, longName="twistAmount", attributeType="double",
                  minValue=0.0, maxValue=1.0,
                  defaultValue=step.default_amount, keyable=True)
        c.addAttr(part, longName="twistAddition", attributeType="double",
                  defaultValue=0.0, keyable=True)
        amount = c.createNode("multDoubleLinear", name=step.amount_node)
        target = c.createNode("plusMinusAverage", name=step.target_node)
        difference = c.createNode("plusMinusAverage",
                                  name=step.difference_node)
        c.connectAttr(step.down_twist_plug, amount + ".input1")
        c.connectAttr(part + ".twistAmount", amount + ".input2")
        c.connectAttr(amount + ".output", target + ".input1D[0]")
        c.connectAttr(part + ".twistAddition", target + ".input1D[1]")
        if step.up_amount_node and step.up_twist_plug:
            up = c.createNode("multDoubleLinear", name=step.up_amount_node)
            c.connectAttr(step.up_twist_plug, up + ".input1")
            c.connectAttr(part + ".twistAmount", up + ".input2")
            c.connectAttr(up + ".output", target + ".input1D[2]")
        c.setAttr(difference + ".operation", 2)
        c.connectAttr(target + ".output1D", difference + ".input1D[0]")
        if step.previous_target_plug:
            c.connectAttr(step.previous_target_plug,
                          difference + ".input1D[1]")
        else:
            c.setAttr(difference + ".input1D[1]", 0.0)
        if step.use_offset_parent_matrix:
            matrix = c.createNode("composeMatrix", name=step.matrix_name)
            translation = c.getAttr(part + ".translate")[0]
            c.setAttr(matrix + ".inputTranslate", *translation,
                      type="float3")
            for axis in "XYZ":
                destination = part + ".translate" + axis
                source = c.connectionInfo(destination,
                                          sourceFromDestination=True)
                if source:
                    c.disconnectAttr(source, destination)
                    c.connectAttr(source, matrix + ".inputTranslate" + axis,
                                  force=True)
            c.connectAttr(difference + ".output1D",
                          matrix + ".inputRotateX")
            c.connectAttr(matrix + ".outputMatrix",
                          part + ".offsetParentMatrix")
            c.setAttr(part + ".translate", 0.0, 0.0, 0.0,
                      type="double3")
            c.setAttr(part + ".rotate", 0.0, 0.0, 0.0,
                      type="double3")
        else:
            c.connectAttr(difference + ".output1D", part + ".rotateX")

    def capture_fit_part_twist_output(
        self, step: FitPartTwistStep
    ) -> str | None:
        c = self._cmds
        part = self._unique_fit_part_joint(step.part_name)
        nodes = ((step.amount_node, "multDoubleLinear"),
                 (step.target_node, "plusMinusAverage"),
                 (step.difference_node, "plusMinusAverage"))
        if step.up_amount_node:
            nodes += ((step.up_amount_node, "multDoubleLinear"),)
        if step.matrix_name:
            nodes += ((step.matrix_name, "composeMatrix"),)
        if step.compensate_start_body:
            weight_name, amount_name, offset_name = (
                step.body_compensation_nodes)
            nodes += ((weight_name, "plusMinusAverage"),
                      (amount_name, "multDoubleLinear"),
                      (offset_name, "plusMinusAverage"))
        if any(not c.objExists(name) or c.nodeType(name) != kind
               for name, kind in nodes):
            return None
        if step.compensate_start_body:
            body_name = step.start_body.rsplit("|", 1)[-1]
            bodies = c.ls(body_name, long=True, type="joint") or []
            if len(bodies) != 1:
                return None
            body = bodies[0]
            constraint = step.body_constraint_name
            weight_name, amount_name, offset_name = (
                step.body_compensation_nodes)
            body_links = (
                (body + ".twistAmount",
                 weight_name + ".input1D[0]"),
                (step.down_twist_plug, amount_name + ".input1"),
                (weight_name + ".output1D",
                 amount_name + ".input2"),
                (amount_name + ".output",
                 offset_name + ".input1D[0]"),
                (body + ".twistAddition",
                 offset_name + ".input1D[1]"),
                (offset_name + ".output1D",
                 constraint + ".offsetX"),
            )
            if (not c.objExists(body + ".twistAmount")
                    or not c.objExists(body + ".twistAddition")
                    or not c.objExists(constraint)
                    or c.nodeType(constraint) != "orientConstraint"
                    or not c.isConnected(
                        constraint + ".constraintRotateX",
                        body + ".rotateX")
                    or abs(float(c.getAttr(body + ".twistAmount"))) > 1e-8
                    or abs(float(c.getAttr(body + ".twistAddition"))) > 1e-8
                    or not c.getAttr(body + ".twistAmount", keyable=True)
                    or not c.getAttr(body + ".twistAddition", keyable=True)
                    or c.getAttr(weight_name + ".operation") != 1
                    or c.getAttr(offset_name + ".operation") != 1
                    or abs(float(c.getAttr(weight_name
                                        + ".input1D[1]")) + 1.0) > 1e-8
                    or any(not c.isConnected(upstream, target, ignoreUnitConversion=True)
                           for upstream, target in body_links)):
                return None
        if (not c.objExists(part + ".twistAmount")
                or not c.objExists(part + ".twistAddition")
                or not c.getAttr(part + ".twistAmount", keyable=True)
                or not c.getAttr(part + ".twistAddition", keyable=True)
                or abs(float(c.getAttr(part + ".twistAmount"))
                       - step.default_amount) > 1e-8
                or abs(float(c.getAttr(part + ".twistAddition"))) > 1e-8):
            return None
        expected = (
            (step.down_twist_plug, step.amount_node + ".input1"),
            (part + ".twistAmount", step.amount_node + ".input2"),
            (step.amount_node + ".output",
             step.target_node + ".input1D[0]"),
            (part + ".twistAddition",
             step.target_node + ".input1D[1]"),
            (step.target_plug,
             step.difference_node + ".input1D[0]"),
        )
        if step.up_amount_node and step.up_twist_plug:
            expected += (
                (step.up_twist_plug, step.up_amount_node + ".input1"),
                (part + ".twistAmount",
                 step.up_amount_node + ".input2"),
                (step.up_amount_node + ".output",
                 step.target_node + ".input1D[2]"),
            )
        if step.previous_target_plug:
            expected += ((step.previous_target_plug,
                          step.difference_node + ".input1D[1]"),)
        elif (c.connectionInfo(step.difference_node + ".input1D[1]",
                               isDestination=True)
              or abs(c.getAttr(step.difference_node
                               + ".input1D[1]")) > 1e-8):
            return None
        if (c.getAttr(step.difference_node + ".operation") != 2
                or any(not c.isConnected(source, target, ignoreUnitConversion=True)
                       for source, target in expected)):
            return None
        if step.use_offset_parent_matrix:
            matrix_source = c.connectionInfo(
                part + ".offsetParentMatrix",
                sourceFromDestination=True)
            if matrix_source != step.matrix_name + ".outputMatrix":
                return None
            if (any(abs(c.getAttr(part + "." + attribute)) > 1e-8
                    for attribute in ("translateX", "translateY",
                                      "translateZ", "rotateX", "rotateY",
                                      "rotateZ"))):
                return None
            destination = step.matrix_name + ".inputRotateX"
        else:
            destination = part + ".rotateX"
        return (step.output_plug if c.isConnected(step.output_plug, destination,
                                                  ignoreUnitConversion=True) else None)
