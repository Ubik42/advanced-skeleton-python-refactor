"""Maya node boundary for the generic Fit-driven Part hierarchy."""
from __future__ import annotations

from adv_py.core.fit_part import (
    FitPartChildState,
    FitPartJointSpec,
    FitPartJointState,
    FitPartReparentSpec,
)
from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_part_twist import (
    FitPartTwistProjection, FitPartTwistStep,
)
from adv_py.core.fit_part_scale import (
    FitPartLimbScaleChain, FitPartScaleStep,
)

_FIT_PART_KIND = "fit-part-v1"


class MayaFitPartMixin:
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
            for name in chain.part_names:
                part = self._unique_fit_part_joint(name)
                c.connectAttr(blend + ".output", part + ".scale")

    def capture_fit_part_limb_scale(
        self, chain: FitPartLimbScaleChain
    ) -> bool:
        c = self._cmds
        if chain.use_offset_parent_matrix:
            body = self._unique_fit_part_joint(chain.start_body_name)
            if c.connectionInfo(body + ".offsetParentMatrix",
                    sourceFromDestination=True) != chain.scale_matrix_name + ".matrixSum":
                return False
            return all(c.connectionInfo(chain.scale_compose_name
                       + ".inputScale" + axis, sourceFromDestination=True)
                       == chain.blend_name + ".output" + color
                       for axis, color in zip("XYZ", "RGB"))
        return all(c.connectionInfo(self._unique_fit_part_joint(name)
                   + ".scale", sourceFromDestination=True)
                   == chain.output_plug for name in chain.part_names)

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
        source = self._cmds.connectionInfo(
            step.target_plug, sourceFromDestination=True)
        return source or None

    def _unique_fit_part_joint(self, name: str) -> str:
        matches = self._cmds.ls(name, long=True, type="joint") or []
        if len(matches) != 1:
            raise ValueError("Fit Part 需要唯一关节名称：" + name)
        return matches[0]

    def preflight_fit_part_hierarchy(
        self,
        joints: tuple[FitPartJointSpec, ...],
        reparents: tuple[FitPartReparentSpec, ...],
    ) -> None:
        c = self._cmds
        planned_names = {item.name for item in joints}
        for spec in joints:
            self._unique_fit_part_joint(spec.start_body_name)
            self._unique_fit_part_joint(spec.end_body_name)
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
        c.setAttr(joint + ".segmentScaleCompensate",
                  spec.segment_scale_compensate)
        c.xform(joint, worldSpace=True, translation=spec.world_position)
        c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind",
                  dataType="string")
        c.setAttr(joint + ".advPyAuxiliaryInfluenceKind", _FIT_PART_KIND,
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
                child))
        return tuple(result)

    def capture_fit_part_body_paths(
        self, names: tuple[str, ...]
    ) -> tuple[tuple[str, str], ...]:
        return tuple((name, self._unique_fit_part_joint(name))
                     for name in names)

    def preflight_fit_part_twist_projection(
        self, projection: FitPartTwistProjection
    ) -> None:
        c = self._cmds
        inputs = projection.input
        plugs = (inputs.rotation_plug, inputs.rotate_order_plug,
                 inputs.up_twist_plug, inputs.ik_rotation_plug,
                 inputs.ik_rotate_order_plug, inputs.ik_fk_blend_plug)
        for plug in plugs:
            if plug and not c.objExists(plug):
                raise ValueError("Fit Part 扭转投影来源不存在：" + plug)

    def create_fit_part_twist_projection(
        self, projection: FitPartTwistProjection
    ) -> None:
        self._require_transaction()
        c = self._cmds
        source = projection.input

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

        fk_output = create(
            projection.compose_name, projection.decompose_name,
            projection.project_name, source.rotation_plug,
            source.rotate_order_plug)
        self._transaction_changed = True
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
        if projection.blend_name:
            expected = (
                projection.project_name + ".outputRotateX",
                projection.ik_project_name + ".outputRotateX",
                projection.input.ik_fk_blend_plug,
            )
            destinations = (
                projection.blend_name + ".input[0]",
                projection.blend_name + ".input[1]",
                projection.blend_name + ".attributesBlender",
            )
            if any(c.connectionInfo(destination,
                    sourceFromDestination=True) != source
                   for destination, source in zip(destinations, expected)):
                return None
        return output

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

    def create_fit_part_twist_step(self, step: FitPartTwistStep) -> None:
        self._require_transaction()
        c = self._cmds
        part = self._unique_fit_part_joint(step.part_name)
        c.addAttr(part, longName="twistAmount", attributeType="double",
                  minValue=0.0, maxValue=1.0,
                  defaultValue=step.default_amount, keyable=True)
        c.addAttr(part, longName="twistAddition", attributeType="double",
                  defaultValue=0.0, keyable=True)
        amount = c.createNode("multDoubleLinear", name=step.amount_node)
        target = c.createNode("plusMinusAverage", name=step.target_node)
        difference = c.createNode("plusMinusAverage",
                                  name=step.difference_node)
        self._transaction_changed = True
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
        if step.use_offset_parent_matrix:
            matrix_source = c.connectionInfo(
                part + ".offsetParentMatrix",
                sourceFromDestination=True)
            if matrix_source != step.matrix_name + ".outputMatrix":
                return None
            return c.connectionInfo(
                step.matrix_name + ".inputRotateX",
                sourceFromDestination=True) or None
        return c.connectionInfo(
            part + ".rotateX", sourceFromDestination=True) or None
