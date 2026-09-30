from __future__ import annotations

from math import sqrt, isfinite

from adv_py.core.body_spine import spine_roll_degrees, spine_ik_goal_position
from adv_py.core.body_limb_ik import solve_limb_pole_position
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.body_controller_layers import (
    audit_body_extra_controller, audit_body_sub_controller,
)
from .maya_adv_icons import create_adv_icon
from . import maya_chest_space


class MayaBodySpineMixin:
    def ensure_precise_body_spine_solver(self,plan):
        """Upgrade this owned spine only; never edit Maya's shared solver settings."""
        self._require_transaction()
        self.validate_body_spine(plan)
        c=self._cmds
        solver="AdvPy_SpineRPSolver"
        current=c.ikHandle("AdvPy_SpineIKHandle",query=True,solver=True)
        if current==solver:
            return
        if current!="ikRPsolver" or c.objExists(solver):
            raise FitSkeletonValidationError("脊柱求解器有外部替换或名称冲突")
        self._transaction_changed=True
        c.createNode("ikRPsolver",name=solver,skipSelect=True)
        c.addAttr(solver,longName="advPySpineSolverOwner",dataType="string")
        c.setAttr(solver+".advPySpineSolverOwner","adv_py.spine_solver.v1",type="string",lock=True)
        c.addAttr(solver,longName="characterRoot",attributeType="message")
        c.connectAttr(plan.root_path+".message",solver+".characterRoot")
        c.setAttr(solver+".characterRoot",lock=True)
        c.setAttr(solver+".tolerance",1e-10,lock=True)
        c.ikHandle("AdvPy_SpineIKHandle",edit=True,solver=solver)
        self.validate_body_spine(plan)

    def _spine_frame(self, name, parent, position, axes):
        node = self._cmds.createNode("transform", name=name, parent=parent, skipSelect=True)
        node = self._resolve_connected_node(node)
        self._cmds.xform(node, worldSpace=True, matrix=(
            *axes[0], 0, *axes[1], 0, *axes[2], 0, *position, 1,
        ))
        return node

    def prepare_body_spine(self, plan):
        self._require_transaction()
        self._transaction_changed = True
        root = self._cmds.createNode("transform", name=plan.root_path.rsplit("|", 1)[-1],
                                     parent=plan.root_path.rsplit("|", 1)[0], skipSelect=True)
        self._cmds.addAttr(root, longName="advPySpineOwner", dataType="string")
        self._cmds.setAttr(root + ".advPySpineOwner", "adv_py.spine.v5", type="string", lock=True)
        for spec in plan.joints:
            self.create_body_arm_mechanism_joint(spec)
        chest = plan.joints[2]
        self._spine_frame(plan.chest_space.rsplit("|", 1)[-1], plan.chest_space.rsplit("|", 1)[0],
                          chest.world_position, chest.world_axes)

    def create_body_spine(self, plan):
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        for offset, control, pos in (
            (plan.ik_offset, plan.ik_control, plan.joints[2].world_position),
            (plan.pole_offset, plan.pole_control, plan.pole_position),
        ):
            self._spine_frame(offset.rsplit("|", 1)[-1], offset.rsplit("|", 1)[0], pos, plan.joints[2].world_axes)
            parent = offset
            if control == plan.ik_control and plan.ik_extra_path:
                parent = self._create_body_extra_layer(
                    offset, plan.ik_extra_path.rsplit("|", 1)[-1],
                    plan.ik_extra_path)
            elif control == plan.pole_control and plan.pole_extra_path:
                parent = self._create_body_extra_layer(
                    offset, plan.pole_extra_path.rsplit("|", 1)[-1],
                    plan.pole_extra_path)
            create_adv_icon(
                c, name=control.rsplit("|", 1)[-1], parent=parent,
                template=("IK_icon" if control == plan.ik_control
                          else "Pole_icon"), radius=1.5,
                fallback_normal=(1.0, 0.0, 0.0))
            if control == plan.ik_control:
                if plan.ik_extra_path and plan.ik_extra_curve:
                    self._add_body_extra_curve(plan.ik_extra_path, control)
                if plan.ik_sub_path:
                    self._create_body_sub_control(
                        control, plan.ik_sub_path.rsplit("|", 1)[-1],
                        plan.ik_sub_path)
            for axis in "XYZ":
                c.setAttr(control + ".scale" + axis, lock=True, keyable=False)
        c.addAttr(plan.ik_control, longName="spineIkFk", attributeType="double", minValue=0, maxValue=1, defaultValue=0, keyable=True)
        c.addAttr(plan.ik_control, longName="waistRoll", attributeType="doubleAngle", defaultValue=0, keyable=True)
        c.addAttr(plan.ik_control, longName="stretchy", attributeType="double",
                  minValue=0, maxValue=10, defaultValue=0, keyable=True)
        c.addAttr(plan.ik_control, longName="antiPop", attributeType="double",
                  minValue=0, maxValue=10, defaultValue=0, keyable=True)
        c.addAttr(plan.ik_control, longName="volume", attributeType="double",
                  minValue=0, maxValue=10, defaultValue=10, keyable=True)
        for index in (1, 2):
            c.addAttr(plan.ik_control, longName=f"Lenght{index}",
                      attributeType="double", minValue=0.001,
                      defaultValue=1, keyable=True)
            c.addAttr(plan.ik_control, longName=f"Fatness{index}",
                      attributeType="double", defaultValue=0, keyable=True)
        c.addAttr(plan.pole_control, longName="lock",
                  attributeType="double", minValue=0, maxValue=10,
                  defaultValue=0, keyable=True)
        c.createNode("transform", name=plan.waist_output.rsplit("|", 1)[-1], parent=plan.joints[4].path, skipSelect=True)
        c.connectAttr(plan.roll_plug, plan.waist_output + ".rotateX")
        c.pointConstraint((plan.fk_sources or plan.fk_controls)[0],
                          plan.joints[0].path, maintainOffset=False,
                          name="AdvPy_SpineFKRootPoint")
        c.pointConstraint(plan.pelvis_control, plan.joints[3].path, maintainOffset=False, name="AdvPy_SpineIKRootPoint")
        # Preferred bend disambiguates the fully straight synthetic bind chain.
        c.setAttr(plan.joints[4].path + ".preferredAngleZ", -0.1)
        handle, effector = c.ikHandle(name="AdvPy_SpineIKHandle", startJoint=plan.joints[3].path,
                                      endEffector=plan.joints[5].path, solver="ikRPsolver")
        c.rename(effector, "AdvPy_SpineIKEffector")
        c.parent(handle, plan.ik_driver)
        c.setAttr("AdvPy_SpineIKHandle.visibility", False)
        c.poleVectorConstraint(plan.pole_control, "AdvPy_SpineIKHandle", name="AdvPy_SpinePoleConstraint")
        c.orientConstraint(plan.ik_driver, plan.joints[5].path, maintainOffset=False, name="AdvPy_SpineIKChestOrient")
        self._create_body_spine_stretch_volume(plan)
        c.createNode("reverse", name="AdvPy_SpineReverse")
        c.connectAttr(plan.blend_plug, "AdvPy_SpineReverse.inputX")
        for control, joint in zip(plan.fk_controls, plan.joints[:3]):
            c.connectAttr(control + ".scale", joint.path + ".scale")
        for label, body, fk, ik in (
            ("Waist", plan.body_joints[1], plan.joints[1].path, plan.waist_output),
            ("Chest", plan.body_joints[2], plan.joints[2].path, plan.joints[5].path),
        ):
            for suffix, command in (("Point", c.pointConstraint),
                                    ("Orient", c.orientConstraint),
                                    ("Scale", c.scaleConstraint)):
                node = command(fk, ik, body, maintainOffset=False, name=f"AdvPy_Spine{label}{suffix}")[0]
                weights = command(node, query=True, weightAliasList=True)
                c.connectAttr("AdvPy_SpineReverse.outputX", node + "." + weights[0])
                c.connectAttr(plan.blend_plug, node + "." + weights[1])
                if suffix == "Orient":
                    c.setAttr(node + ".interpType", 2)
        maya_chest_space.create(
            self, plan.body_joints[2], plan.chest_space,
            "AdvPy_SpineChestSpaceParent",
            plan.use_offset_parent_matrix)
        c.setAttr(plan.root_path + ".visibility", False)
        self.validate_body_spine(plan)

    def _create_body_spine_stretch_volume(self, plan):
        """Measure in the spine frame so character scale does not cause stretch."""
        c = self._cmds
        start = c.createNode("multMatrix", name="AdvPy_SpineStretchStartMM")
        target = c.createNode("multMatrix", name="AdvPy_SpineStretchTargetMM")
        for node, source in ((start, plan.joints[3].path),
                             (target, plan.ik_driver)):
            c.connectAttr(source + ".worldMatrix[0]", node + ".matrixIn[0]")
            c.connectAttr(plan.root_path + ".worldInverseMatrix[0]",
                          node + ".matrixIn[1]")
        distance = c.createNode("distanceBetween",
                                name="AdvPy_SpineStretchDistance")
        c.connectAttr(start + ".matrixSum", distance + ".inMatrix1")
        c.connectAttr(target + ".matrixSum", distance + ".inMatrix2")
        rest_length = sum(plan.lengths)
        normal = c.createNode("animCurveUU",
                              name="AdvPy_SpineAntiPopNormal")
        anti_pop = c.createNode("animCurveUU",
                                name="AdvPy_SpineAntiPopCurve")
        curves = (
            (normal, ((1.0, 1.0, "spline", "linear"),
                      (1.2, 1.2, "spline", "spline"))),
            (anti_pop, ((0.1, 1.0, "spline", "spline"),
                        (0.7, 1.0, "linear", "spline"),
                        (0.85, 0.9, "spline", "spline"),
                        (1.0, 1.0, "spline", "linear"),
                        (1.2, 1.2, "spline", "spline"))),
        )
        for curve, keys in curves:
            for index, (position, value, tangent_in, tangent_out) in enumerate(keys):
                c.setKeyframe(curve, float=rest_length * position,
                              value=rest_length * value)
                c.keyTangent(curve, edit=True, index=(index, index),
                             inTangentType=tangent_in,
                             outTangentType=tangent_out)
            c.setAttr(curve + ".postInfinity", 1)
            c.connectAttr(distance + ".distance", curve + ".input")
        anti_weight = c.createNode("unitConversion",
                                   name="AdvPy_SpineAntiPopWeight")
        c.setAttr(anti_weight + ".conversionFactor", 0.1)
        c.connectAttr(plan.anti_pop_plug, anti_weight + ".input")
        anti_blend = c.createNode("blendTwoAttr",
                                  name="AdvPy_SpineAntiPopBlend")
        c.connectAttr(normal + ".output", anti_blend + ".input[0]")
        c.connectAttr(anti_pop + ".output", anti_blend + ".input[1]")
        c.connectAttr(anti_weight + ".output",
                      anti_blend + ".attributesBlender")
        pole = c.createNode("multMatrix", name="AdvPy_SpinePoleLocalMM")
        c.connectAttr(plan.pole_control + ".worldMatrix[0]",
                      pole + ".matrixIn[0]")
        c.connectAttr(plan.root_path + ".worldInverseMatrix[0]",
                      pole + ".matrixIn[1]")
        pole_weight = c.createNode("unitConversion",
                                   name="AdvPy_SpinePoleLockWeight")
        c.setAttr(pole_weight + ".conversionFactor", 0.1)
        c.connectAttr(plan.pole_lock_plug, pole_weight + ".input")
        ratio = c.createNode("multiplyDivide", name="AdvPy_SpineStretchRatio")
        c.setAttr(ratio + ".operation", 2)
        c.setAttr(ratio + ".input2X", rest_length)
        c.connectAttr(anti_blend + ".output", ratio + ".input1X")
        clamp = c.createNode("clamp", name="AdvPy_SpineStretchClamp")
        c.setAttr(clamp + ".minR", 0.0)
        c.setAttr(clamp + ".maxR", 1.0)
        c.connectAttr(ratio + ".outputX", clamp + ".inputR")
        weight = c.createNode("unitConversion",
                              name="AdvPy_SpineStretchWeight")
        c.setAttr(weight + ".conversionFactor", 0.1)
        c.connectAttr(plan.stretch_plug, weight + ".input")
        blend = c.createNode("blendColors", name="AdvPy_SpineStretchBlend")
        c.connectAttr(ratio + ".outputX", blend + ".color1R")
        c.connectAttr(clamp + ".outputR", blend + ".color2R")
        c.connectAttr(weight + ".output", blend + ".blender")
        segments = c.createNode("multiplyDivide",
                                name="AdvPy_SpineStretchSegments")
        for index, (axis, length, joint) in enumerate(
                zip("XY", plan.lengths, plan.joints[4:6]), 1):
            c.setAttr(segments + ".input1" + axis, length)
            c.connectAttr(blend + ".outputR",
                          segments + ".input2" + axis)
            length_node = c.createNode("multiplyDivide",
                                       name=f"AdvPy_SpineLength{index}")
            c.connectAttr(segments + ".output" + axis,
                          length_node + ".input1X")
            c.connectAttr(plan.ik_control + f".Lenght{index}",
                          length_node + ".input2X")
            pole_distance = c.createNode(
                "distanceBetween", name=f"AdvPy_SpinePoleDistance{index}")
            c.connectAttr(pole + ".matrixSum",
                          pole_distance + ".inMatrix1")
            c.connectAttr((start if index == 1 else target) + ".matrixSum",
                          pole_distance + ".inMatrix2")
            pole_blend = c.createNode(
                "blendTwoAttr", name=f"AdvPy_SpinePoleLockBlend{index}")
            c.connectAttr(length_node + ".outputX",
                          pole_blend + ".input[0]")
            c.connectAttr(pole_distance + ".distance",
                          pole_blend + ".input[1]")
            c.connectAttr(pole_weight + ".output",
                          pole_blend + ".attributesBlender")
            c.connectAttr(pole_blend + ".output",
                          joint.path + ".translateX")
        inverse = c.createNode("multiplyDivide",
                               name="AdvPy_SpineVolumeInverse")
        c.setAttr(inverse + ".operation", 2)
        c.setAttr(inverse + ".input1X", 1.0)
        c.connectAttr(blend + ".outputR", inverse + ".input2X")
        power = c.createNode("multiplyDivide", name="AdvPy_SpineVolumePower")
        c.setAttr(power + ".operation", 3)
        c.setAttr(power + ".input2X", 0.5)
        c.connectAttr(inverse + ".outputX", power + ".input1X")
        volume_weight = c.createNode("unitConversion",
                                     name="AdvPy_SpineVolumeWeight")
        c.setAttr(volume_weight + ".conversionFactor", 0.1)
        c.connectAttr(plan.volume_plug, volume_weight + ".input")
        volume = c.createNode("blendColors", name="AdvPy_SpineVolumeBlend")
        c.connectAttr(power + ".outputX", volume + ".color1R")
        c.setAttr(volume + ".color2R", 1.0)
        c.connectAttr(volume_weight + ".output", volume + ".blender")
        for index, joint in enumerate(plan.joints[3:5], 1):
            fatness = c.createNode("plusMinusAverage",
                                   name=f"AdvPy_SpineFatness{index}")
            if index == 1:
                c.setAttr(fatness + ".input1D[0]", 1.0)
            else:
                c.connectAttr(volume + ".outputR",
                              fatness + ".input1D[0]")
            c.connectAttr(plan.ik_control + f".Fatness{index}",
                          fatness + ".input1D[1]")
            for axis in "YZ":
                c.connectAttr(fatness + ".output1D",
                              joint.path + ".scale" + axis)

    def _audit_body_spine_stretch_volume(self, plan, owner):
        c = self._cmds
        expected_types = {
            "AdvPy_SpineStretchStartMM": "multMatrix",
            "AdvPy_SpineStretchTargetMM": "multMatrix",
            "AdvPy_SpineStretchDistance": "distanceBetween",
            "AdvPy_SpineStretchRatio": "multiplyDivide",
            "AdvPy_SpineStretchClamp": "clamp",
            "AdvPy_SpineStretchWeight": "unitConversion",
            "AdvPy_SpineStretchBlend": "blendColors",
            "AdvPy_SpineStretchSegments": "multiplyDivide",
            "AdvPy_SpineVolumeInverse": "multiplyDivide",
            "AdvPy_SpineVolumePower": "multiplyDivide",
            "AdvPy_SpineVolumeWeight": "unitConversion",
            "AdvPy_SpineVolumeBlend": "blendColors",
        }
        if owner in ("adv_py.spine.v3", "adv_py.spine.v4",
                     "adv_py.spine.v5"):
            expected_types.update({
                "AdvPy_SpineLength1": "multiplyDivide",
                "AdvPy_SpineLength2": "multiplyDivide",
                "AdvPy_SpineFatness1": "plusMinusAverage",
                "AdvPy_SpineFatness2": "plusMinusAverage",
            })
        if owner in ("adv_py.spine.v4", "adv_py.spine.v5"):
            expected_types.update({
                "AdvPy_SpinePoleLocalMM": "multMatrix",
                "AdvPy_SpinePoleDistance1": "distanceBetween",
                "AdvPy_SpinePoleDistance2": "distanceBetween",
                "AdvPy_SpinePoleLockWeight": "unitConversion",
                "AdvPy_SpinePoleLockBlend1": "blendTwoAttr",
                "AdvPy_SpinePoleLockBlend2": "blendTwoAttr",
            })
        if owner == "adv_py.spine.v5":
            expected_types.update({
                "AdvPy_SpineAntiPopNormal": "animCurveUU",
                "AdvPy_SpineAntiPopCurve": "animCurveUU",
                "AdvPy_SpineAntiPopWeight": "unitConversion",
                "AdvPy_SpineAntiPopBlend": "blendTwoAttr",
            })
        if any(c.nodeType(name) != kind for name, kind in
               expected_types.items()):
            raise FitSkeletonValidationError("Spine 伸展或体积节点类型变化")
        for plug in (plan.stretch_plug, plan.volume_plug):
            if not c.objExists(plug) or not c.getAttr(plug, keyable=True):
                raise FitSkeletonValidationError("Spine 伸展或体积控制属性缺失")
        if owner in ("adv_py.spine.v3", "adv_py.spine.v4",
                     "adv_py.spine.v5") and any(
                not c.objExists(plan.ik_control + "." + name)
                or not c.getAttr(plan.ik_control + "." + name,
                                 keyable=True)
                for name in ("Lenght1", "Lenght2", "Fatness1",
                             "Fatness2")):
            raise FitSkeletonValidationError("Spine 逐段长度或粗细属性缺失")
        if owner in ("adv_py.spine.v4", "adv_py.spine.v5") and (
                not c.objExists(plan.pole_lock_plug)
                or not c.getAttr(plan.pole_lock_plug, keyable=True)):
            raise FitSkeletonValidationError("Spine Pole Lock 控制属性缺失")
        if owner == "adv_py.spine.v5" and (
                not c.objExists(plan.anti_pop_plug)
                or not c.getAttr(plan.anti_pop_plug, keyable=True)):
            raise FitSkeletonValidationError("Spine AntiPop 控制属性缺失")
        edges = [
            (plan.joints[3].path + ".worldMatrix[0]",
             "AdvPy_SpineStretchStartMM.matrixIn[0]"),
            (plan.ik_driver + ".worldMatrix[0]",
             "AdvPy_SpineStretchTargetMM.matrixIn[0]"),
            ("AdvPy_SpineStretchStartMM.matrixSum",
             "AdvPy_SpineStretchDistance.inMatrix1"),
            ("AdvPy_SpineStretchTargetMM.matrixSum",
             "AdvPy_SpineStretchDistance.inMatrix2"),
            ("AdvPy_SpineStretchRatio.outputX",
             "AdvPy_SpineStretchClamp.inputR"),
            (plan.stretch_plug, "AdvPy_SpineStretchWeight.input"),
            ("AdvPy_SpineStretchWeight.output",
             "AdvPy_SpineStretchBlend.blender"),
            ("AdvPy_SpineStretchBlend.outputR",
             "AdvPy_SpineVolumeInverse.input2X"),
            ("AdvPy_SpineVolumeInverse.outputX",
             "AdvPy_SpineVolumePower.input1X"),
            (plan.volume_plug, "AdvPy_SpineVolumeWeight.input"),
            ("AdvPy_SpineVolumeWeight.output",
             "AdvPy_SpineVolumeBlend.blender"),
            ("AdvPy_SpineVolumePower.outputX",
             "AdvPy_SpineVolumeBlend.color1R"),
        ]
        for name in ("Start", "Target"):
            edges.append((plan.root_path + ".worldInverseMatrix[0]",
                          "AdvPy_SpineStretch" + name + "MM.matrixIn[1]"))
        if owner == "adv_py.spine.v5":
            edges.extend((
                ("AdvPy_SpineStretchDistance.distance",
                 "AdvPy_SpineAntiPopNormal.input"),
                ("AdvPy_SpineStretchDistance.distance",
                 "AdvPy_SpineAntiPopCurve.input"),
                ("AdvPy_SpineAntiPopNormal.output",
                 "AdvPy_SpineAntiPopBlend.input[0]"),
                ("AdvPy_SpineAntiPopCurve.output",
                 "AdvPy_SpineAntiPopBlend.input[1]"),
                (plan.anti_pop_plug,
                 "AdvPy_SpineAntiPopWeight.input"),
                ("AdvPy_SpineAntiPopWeight.output",
                 "AdvPy_SpineAntiPopBlend.attributesBlender"),
                ("AdvPy_SpineAntiPopBlend.output",
                 "AdvPy_SpineStretchRatio.input1X"),
                ("AdvPy_SpineStretchRatio.outputX",
                 "AdvPy_SpineStretchBlend.color1R"),
                ("AdvPy_SpineStretchClamp.outputR",
                 "AdvPy_SpineStretchBlend.color2R"),
            ))
        else:
            edges.extend((
                ("AdvPy_SpineStretchDistance.distance",
                 "AdvPy_SpineStretchRatio.input1X"),
                ("AdvPy_SpineStretchClamp.outputR",
                 "AdvPy_SpineStretchBlend.color1R"),
            ))
        for index, (axis, joint) in enumerate(
                zip("XY", plan.joints[4:6]), 1):
            edges.append(("AdvPy_SpineStretchBlend.outputR",
                          "AdvPy_SpineStretchSegments.input2" + axis))
            if owner in ("adv_py.spine.v3", "adv_py.spine.v4",
                         "adv_py.spine.v5"):
                edges.extend((
                    ("AdvPy_SpineStretchSegments.output" + axis,
                     f"AdvPy_SpineLength{index}.input1X"),
                    (plan.ik_control + f".Lenght{index}",
                     f"AdvPy_SpineLength{index}.input2X"),
                ))
                if owner in ("adv_py.spine.v4", "adv_py.spine.v5"):
                    edges.extend((
                        (f"AdvPy_SpineLength{index}.outputX",
                         f"AdvPy_SpinePoleLockBlend{index}.input[0]"),
                        (f"AdvPy_SpinePoleDistance{index}.distance",
                         f"AdvPy_SpinePoleLockBlend{index}.input[1]"),
                        ("AdvPy_SpinePoleLockWeight.output",
                         f"AdvPy_SpinePoleLockBlend{index}.attributesBlender"),
                        (f"AdvPy_SpinePoleLockBlend{index}.output",
                         joint.path + ".translateX"),
                        ("AdvPy_SpinePoleLocalMM.matrixSum",
                         f"AdvPy_SpinePoleDistance{index}.inMatrix1"),
                        (("AdvPy_SpineStretchStartMM" if index == 1
                          else "AdvPy_SpineStretchTargetMM") + ".matrixSum",
                         f"AdvPy_SpinePoleDistance{index}.inMatrix2"),
                    ))
                else:
                    edges.append((f"AdvPy_SpineLength{index}.outputX",
                                  joint.path + ".translateX"))
            else:
                edges.append(("AdvPy_SpineStretchSegments.output" + axis,
                              joint.path + ".translateX"))
        if owner in ("adv_py.spine.v3", "adv_py.spine.v4",
                     "adv_py.spine.v5"):
            edges.append(("AdvPy_SpineVolumeBlend.outputR",
                          "AdvPy_SpineFatness2.input1D[0]"))
            for index, joint in enumerate(plan.joints[3:5], 1):
                edges.append((plan.ik_control + f".Fatness{index}",
                              f"AdvPy_SpineFatness{index}.input1D[1]"))
                for axis in "YZ":
                    edges.append((f"AdvPy_SpineFatness{index}.output1D",
                                  joint.path + ".scale" + axis))
        else:
            for axis in "YZ":
                edges.append(("AdvPy_SpineVolumeBlend.outputR",
                              plan.joints[4].path + ".scale" + axis))
        if owner in ("adv_py.spine.v4", "adv_py.spine.v5"):
            edges.extend((
                (plan.pole_control + ".worldMatrix[0]",
                 "AdvPy_SpinePoleLocalMM.matrixIn[0]"),
                (plan.root_path + ".worldInverseMatrix[0]",
                 "AdvPy_SpinePoleLocalMM.matrixIn[1]"),
                (plan.pole_lock_plug,
                 "AdvPy_SpinePoleLockWeight.input"),
            ))
        if any(not c.isConnected(source, target) for source, target in edges):
            raise FitSkeletonValidationError("Spine 伸展或体积驱动连接变化")
        constants = (
            ("AdvPy_SpineStretchRatio.operation", 2.0),
            ("AdvPy_SpineStretchRatio.input2X", sum(plan.lengths)),
            ("AdvPy_SpineStretchClamp.minR",
             0.0 if owner == "adv_py.spine.v5" else 1.0),
            ("AdvPy_SpineStretchClamp.maxR",
             1.0 if owner == "adv_py.spine.v5" else 1000000.0),
            ("AdvPy_SpineStretchWeight.conversionFactor", 0.1),
            ("AdvPy_SpineVolumeInverse.operation", 2.0),
            ("AdvPy_SpineVolumeInverse.input1X", 1.0),
            ("AdvPy_SpineVolumePower.operation", 3.0),
            ("AdvPy_SpineVolumePower.input2X", 0.5),
            ("AdvPy_SpineVolumeWeight.conversionFactor", 0.1),
            ("AdvPy_SpineVolumeBlend.color2R", 1.0),
            *(("AdvPy_SpineStretchSegments.input1" + axis, length)
              for axis, length in zip("XY", plan.lengths)),
        )
        if owner != "adv_py.spine.v5":
            constants += (("AdvPy_SpineStretchBlend.color2R", 1.0),)
        if owner in ("adv_py.spine.v3", "adv_py.spine.v4",
                     "adv_py.spine.v5"):
            constants += (("AdvPy_SpineFatness1.input1D[0]", 1.0),)
        if owner in ("adv_py.spine.v4", "adv_py.spine.v5"):
            constants += (("AdvPy_SpinePoleLockWeight.conversionFactor",
                           0.1),)
        if owner == "adv_py.spine.v5":
            constants += (("AdvPy_SpineAntiPopWeight.conversionFactor",
                           0.1),)
        if any(abs(float(c.getAttr(plug)) - value) > 1e-5
               for plug, value in constants):
            raise FitSkeletonValidationError("Spine 伸展或体积绑定参数变化")
        if owner == "adv_py.spine.v5":
            rest = sum(plan.lengths)
            profiles = (
                ("AdvPy_SpineAntiPopNormal",
                 ((1.0, 1.0, "spline", "linear"),
                  (1.2, 1.2, "spline", "spline"))),
                ("AdvPy_SpineAntiPopCurve",
                 ((0.1, 1.0, "spline", "spline"),
                  (0.7, 1.0, "linear", "spline"),
                  (0.85, 0.9, "spline", "spline"),
                  (1.0, 1.0, "spline", "linear"),
                  (1.2, 1.2, "spline", "spline"))),
            )
            for curve, profile in profiles:
                positions = c.keyframe(curve, query=True,
                                       floatChange=True) or []
                values = c.keyframe(curve, query=True,
                                    valueChange=True) or []
                in_types = c.keyTangent(curve, query=True,
                                        inTangentType=True) or []
                out_types = c.keyTangent(curve, query=True,
                                         outTangentType=True) or []
                if (len(positions) != len(profile)
                        or len(values) != len(profile)
                        or tuple(in_types) != tuple(row[2] for row in profile)
                        or tuple(out_types) != tuple(row[3] for row in profile)
                        or c.getAttr(curve + ".postInfinity") != 1
                        or any(abs(float(position) - rest * expected[0])
                               > 1e-5 or abs(float(value) - rest * expected[1])
                               > 1e-5 for position, value, expected in
                               zip(positions, values, profile))):
                    raise FitSkeletonValidationError(
                        "Spine AntiPop 距离曲线或切线变化")

    def validate_body_spine(self, plan):
        c = self._cmds
        if not c.objExists(plan.root_path + ".advPySpineOwner"):
            raise FitSkeletonValidationError("Spine 机制归属标记缺失")
        owner = c.getAttr(plan.root_path + ".advPySpineOwner")
        if owner not in ("adv_py.spine.v1", "adv_py.spine.v2",
                         "adv_py.spine.v3", "adv_py.spine.v4",
                         "adv_py.spine.v5"):
            raise FitSkeletonValidationError("Spine 机制归属标记无效")
        pole_nodes = frozenset((
            "AdvPy_SpinePoleLocalMM", "AdvPy_SpinePoleDistance1",
            "AdvPy_SpinePoleDistance2", "AdvPy_SpinePoleLockWeight",
            "AdvPy_SpinePoleLockBlend1", "AdvPy_SpinePoleLockBlend2",
        ))
        if owner == "adv_py.spine.v5":
            nodes = plan.node_names
        elif owner == "adv_py.spine.v4":
            nodes = tuple(name for name in plan.node_names
                          if not name.startswith("AdvPy_SpineAntiPop"))
        elif owner == "adv_py.spine.v3":
            nodes = tuple(name for name in plan.node_names
                          if name not in pole_nodes and not
                          name.startswith("AdvPy_SpineAntiPop"))
        elif owner == "adv_py.spine.v2":
            nodes = tuple(name for name in plan.node_names
                          if name not in pole_nodes and not
                          name.startswith(("AdvPy_SpineLength",
                                           "AdvPy_SpineFatness",
                                           "AdvPy_SpineAntiPop")))
        else:
            nodes = tuple(name for name in plan.node_names
                          if name not in pole_nodes and not
                          name.startswith(("AdvPy_SpineStretch",
                                           "AdvPy_SpineVolume",
                                           "AdvPy_SpineLength",
                                           "AdvPy_SpineFatness",
                                           "AdvPy_SpineAntiPop")))
        if any(len(c.ls(name, long=True) or []) != 1 for name in nodes):
            raise FitSkeletonValidationError("Spine 节点集合缺失或名称不唯一")
        if plan.ik_extra_path:
            issues = audit_body_extra_controller(
                plan.ik_offset, plan.ik_control, plan.ik_extra_path,
                self._capture_body_extra_layer(
                    plan.ik_extra_path, plan.ik_control),
                extra_curve=plan.ik_extra_curve)
            if issues:
                raise FitSkeletonValidationError(
                    "Spine IK Extra 层复检失败：" + "；".join(issues))
            control_parent = c.listRelatives(
                plan.ik_control, parent=True, fullPath=True) or []
            if control_parent != [plan.ik_extra_path]:
                raise FitSkeletonValidationError("Spine IK 控制器父层改变")
        elif plan.ik_extra_curve:
            raise FitSkeletonValidationError("旧版 Spine IK 无 Extra 曲线层")
        if plan.pole_extra_path:
            issues = audit_body_extra_controller(
                plan.pole_offset, plan.pole_control,
                plan.pole_extra_path,
                self._capture_body_extra_layer(
                    plan.pole_extra_path, plan.pole_control),
                extra_curve=False)
            if issues:
                raise FitSkeletonValidationError(
                    "Spine Pole Extra 层复检失败：" + "；".join(issues))
        pole_parent = c.listRelatives(
            plan.pole_control, parent=True, fullPath=True) or []
        if pole_parent != [plan.pole_extra_path or plan.pole_offset]:
            raise FitSkeletonValidationError("Spine Pole 控制器父层改变")
        sub_state = self._capture_body_ik_sub_control(
            plan.ik_control, plan.ik_sub_path)
        issues = audit_body_sub_controller(
            plan.ik_control, plan.ik_sub_path, sub_state)
        if issues:
            raise FitSkeletonValidationError(
                "Spine IK Sub 层复检失败：" + "；".join(issues))
        if owner in ("adv_py.spine.v2", "adv_py.spine.v3",
                     "adv_py.spine.v4", "adv_py.spine.v5"):
            self._audit_body_spine_stretch_volume(plan, owner)
        solver=c.ikHandle("AdvPy_SpineIKHandle",query=True,solver=True)
        if solver!="ikRPsolver":
            if (solver!="AdvPy_SpineRPSolver" or c.nodeType(solver)!="ikRPsolver"
                    or c.referenceQuery(solver,isNodeReferenced=True)
                    or not c.objExists(solver+".advPySpineSolverOwner")
                    or c.getAttr(solver+".advPySpineSolverOwner")!="adv_py.spine_solver.v1"
                    or not c.isConnected(plan.root_path+".message",solver+".characterRoot")
                    or c.getAttr(solver+".tolerance")!=1e-10
                    or c.listConnections(solver+".tolerance",s=True,d=False)
                    or (c.listConnections(solver,s=False,d=True,plugs=True) or []) != ["AdvPy_SpineIKHandle.ikSolver"]):
                raise FitSkeletonValidationError("独立脊柱求解器归属、精度或输出被修改")
        for joint in plan.joints:
            parents = c.listRelatives(joint.path, parent=True, fullPath=True) or []
            if c.nodeType(joint.path) != "joint" or parents != [joint.parent_path]:
                raise FitSkeletonValidationError("Spine 驱动关节类型或父链改变")
            if not c.isConnected(joint.source_joint + ".message", joint.path + ".advPySourceJoint"):
                raise FitSkeletonValidationError("Spine 驱动关节来源改变")
        def targets(name, command, expected):
            actual = tuple(self._resolve_connected_node(n) for n in (command(name, query=True, targetList=True) or []))
            if actual != expected:
                raise FitSkeletonValidationError(f"Spine 约束来源已变化：{name}")
        for label, body, fk, ik in (
            ("Waist", plan.body_joints[1], plan.joints[1].path, plan.waist_output),
            ("Chest", plan.body_joints[2], plan.joints[2].path, plan.joints[5].path),
        ):
            for suffix, kind, command in (
                    ("Point", "translate", c.pointConstraint),
                    ("Orient", "rotate", c.orientConstraint),
                    ("Scale", "scale", c.scaleConstraint)):
                name = f"AdvPy_Spine{label}{suffix}"
                targets(name, command, (fk, ik))
                weights = command(name, query=True, weightAliasList=True)
                expected = ("AdvPy_SpineReverse.outputX", plan.blend_plug)
                for weight, source in zip(weights, expected):
                    if not c.isConnected(source, name + "." + weight):
                        raise FitSkeletonValidationError("Spine blend 权重接线变化")
                for axis in "XYZ":
                    if not c.isConnected(f"{name}.constraint{kind.title()}{axis}", f"{body}.{kind}{axis}"):
                        raise FitSkeletonValidationError("Spine Body 输出接线变化")
        maya_chest_space.audit(
            self, plan.body_joints[2], plan.chest_space,
            "AdvPy_SpineChestSpaceParent",
            plan.use_offset_parent_matrix)
        targets("AdvPy_SpinePoleConstraint", c.poleVectorConstraint, (plan.pole_control,))
        targets("AdvPy_SpineIKChestOrient", c.orientConstraint, (plan.ik_driver,))
        for role, index in (("FK", 0), ("IK", 3)):
            name = f"AdvPy_Spine{role}RootPoint"
            if role == "FK":
                fk_targets = c.orientConstraint(
                    'AdvPy_SpineBaseFKOrient', query=True,
                    targetList=True) or []
                if len(fk_targets) != 1:
                    raise FitSkeletonValidationError(
                        'Spine Base FK 朝向来源不唯一')
                source = self._resolve_connected_node(fk_targets[0])
            else:
                source = plan.pelvis_control
            targets(name, c.pointConstraint, (source,))
            for axis in "XYZ":
                if not c.isConnected(name + ".constraintTranslate" + axis, plan.joints[index].path + ".translate" + axis):
                    raise FitSkeletonValidationError("Spine 起点约束输出改变")
        for name, control, base_source, joint in zip(
            ("AdvPy_SpineBaseFKOrient", "AdvPy_TorsoSpine1_MOrient", "AdvPy_TorsoChest_MOrient"),
            plan.fk_controls, plan.fk_sources or plan.fk_controls,
            plan.joints[:3],
        ):
            source = base_source
            start = {"AdvPy_SpineBaseFKOrient": "Root_M",
                     "AdvPy_TorsoSpine1_MOrient": "Spine1_M"}.get(name)
            inbetween_redirect = False
            if start:
                proxy_name = "AdvPy_" + start + "_InbetweenFKX"
                marker = proxy_name + ".advPyInbetweenFkOwner"
                if c.objExists(proxy_name):
                    if (not c.objExists(marker)
                            or c.getAttr(marker)
                            != "adv_py.inbetween_fk.v1"):
                        raise FitSkeletonValidationError(
                            "脊柱 Inbetween FKX 归属无效：" + proxy_name)
                    proxy = c.ls(proxy_name, long=True,
                                 type="joint") or []
                    if len(proxy) != 1:
                        raise FitSkeletonValidationError(
                            "脊柱 Inbetween FKX 不唯一：" + proxy_name)
                    source = proxy[0]
                    inbetween_redirect = True
            if name == "AdvPy_TorsoSpine1_MOrient" and c.objExists(
                    "AdvPy_AxialFKXSpine1_M.advPyAxialBodyOwner"):
                if inbetween_redirect:
                    raise FitSkeletonValidationError(
                        "脊柱存在两个轴向 FKX 来源")
                marker = "AdvPy_AxialFKXSpine1_M.advPyAxialBodyOwner"
                if c.getAttr(marker) != "adv_py.axial_body.v1":
                    raise FitSkeletonValidationError("轴向脊柱驱动归属无效")
                proxy = c.ls("AdvPy_AxialFKXSpine1_M", long=True,
                             type="transform") or []
                if len(proxy) != 1:
                    raise FitSkeletonValidationError("轴向脊柱驱动缺失")
                source = proxy[0]
            targets(name, c.orientConstraint, (source,))
            if any(not c.isConnected(name + ".constraintRotate" + axis, joint.path + ".rotate" + axis) for axis in "XYZ"):
                raise FitSkeletonValidationError("Spine FK 驱动输出改变")
            if not c.isConnected(control + ".scale", joint.path + ".scale"):
                raise FitSkeletonValidationError("Spine FK 驱动缩放来源改变")
        handle = "AdvPy_SpineIKHandle"
        chain = tuple(self._resolve_connected_node(node) for node in c.ikHandle(handle, query=True, jointList=True))
        if (chain != (plan.solver_joint_list or
                      tuple(j.path for j in plan.joints[3:5]))
                or (c.listRelatives(handle, parent=True, fullPath=True) or []) != [plan.ik_driver]
                or not c.isConnected(plan.blend_plug, "AdvPy_SpineReverse.inputX")):
            raise FitSkeletonValidationError("Spine IK handle 或混合输入结构改变")
        for attr in ("translateX", "translateY", "translateZ", "rotateY", "rotateZ"):
            if abs(c.getAttr(plan.waist_output + "." + attr)) > 1e-6 or c.listConnections(plan.waist_output + "." + attr, source=True, destination=False):
                raise FitSkeletonValidationError("Spine waist 输出层被修改")
        if not c.isConnected(plan.roll_plug, plan.waist_output + ".rotateX"):
            raise FitSkeletonValidationError("Spine waist roll 接线变化")

    def _spine_world_frame(self, node):
        matrix = tuple(float(v) for v in self._cmds.xform(node, query=True, worldSpace=True, matrix=True))
        if len(matrix)!=16 or not all(isfinite(value) for value in matrix):
            raise FitSkeletonValidationError('节点世界矩阵包含非有限数值：'+node)
        axes = tuple(self._normalized_vector(matrix[i:i+3]) for i in (0, 4, 8))
        return matrix, axes

    def capture_body_spine_pose(self, plan):
        body = self.capture_body_skeleton(plan.body_joints[0])
        return tuple((j.path, self._spine_world_frame(j.path)[0]) for j in body.joints)

    def preflight_body_spine_match(self, plan, mode):
        self.validate_body_spine(plan)
        c = self._cmds
        owner = c.getAttr(plan.root_path + ".advPySpineOwner")
        has_stretch = owner in ("adv_py.spine.v2", "adv_py.spine.v3",
                                "adv_py.spine.v4", "adv_py.spine.v5")
        if mode not in ("fk", "ik"):
            raise FitSkeletonValidationError("Spine 匹配模式必须是 fk 或 ik")
        if c.ls(type="animLayer"):
            raise FitSkeletonValidationError("Spine 当前姿态匹配暂不支持动画层")
        if c.currentUnit(query=True, angle=True) != "deg":
            raise FitSkeletonValidationError("Spine 当前匹配要求 Maya 角度单位为 degree")
        value = c.getAttr(plan.blend_plug)
        if value not in (0.0, 1.0):
            raise FitSkeletonValidationError("Spine 匹配要求当前 blend 位于 FK 或 IK 端点")
        targets = ([(plan.ik_driver, "translate"), (plan.ik_driver, "rotate"), (plan.pole_control, "translate")]
                   if mode == "ik" else [(path, "rotate") for path in plan.fk_controls])
        for path, kind in targets:
            self._preflight_torso_channels(path, tuple(kind + axis for axis in "XYZ"))
        self._preflight_torso_channels(plan.ik_control, ("spineIkFk", "waistRoll"))
        if has_stretch:
            if mode == "ik":
                self._preflight_torso_channels(plan.ik_control, ("stretchy",))
                if owner in ("adv_py.spine.v3", "adv_py.spine.v4",
                             "adv_py.spine.v5"):
                    self._preflight_torso_channels(
                        plan.ik_control,
                        ("Lenght1", "Lenght2", "Fatness1", "Fatness2"))
                if owner in ("adv_py.spine.v4", "adv_py.spine.v5"):
                    self._preflight_torso_channels(plan.pole_control,
                                                   ("lock",))
                if owner == "adv_py.spine.v5":
                    self._preflight_torso_channels(plan.ik_control,
                                                   ("antiPop",))
            elif (any(abs(float(c.getAttr(joint.path + ".translateX"))
                          - rest) > 1e-4
                      for joint, rest in zip(plan.joints[4:6], plan.lengths))
                  or any(abs(float(c.getAttr(joint.path + ".scale" + axis))
                             - 1.0) > 1e-4
                         for joint in plan.joints[3:5]
                         for axis in "YZ")):
                raise FitSkeletonValidationError(
                    "Spine IK 已拉伸或改变体积，固定长度 FK 无法保持同一姿态")
        matrix, axes = self._spine_world_frame(plan.root_path)
        scales = tuple(sqrt(sum(v*v for v in matrix[i:i+3])) for i in (0, 4, 8))
        x, y, z = axes
        determinant = x[0]*(y[1]*z[2]-y[2]*z[1])-x[1]*(y[0]*z[2]-y[2]*z[0])+x[2]*(y[0]*z[1]-y[1]*z[0])
        if min(scales) < 1e-5 or max(scales)-min(scales) > 1e-4 or abs(determinant-1) > 1e-4:
            raise FitSkeletonValidationError("Spine 匹配只支持正等比缩放")
        if mode == "ik":
            positions = tuple(self._spine_world_frame(j.path)[0][12:15] for j in plan.joints[:3])
            for a, b, rest in zip(positions, positions[1:], plan.lengths):
                length = sqrt(sum((x-y)**2 for x, y in zip(a, b)))
                if abs(length-rest*scales[0]) > 1e-4:
                    raise FitSkeletonValidationError("Spine FK 骨段长度改变，不能直接匹配到固定长度 IK")
        return value

    def _spine_set_world_rotation(self, node, matrix):
        from maya.api import OpenMaya as om
        from math import degrees
        rotation = om.MTransformationMatrix(om.MMatrix(matrix)).rotation()
        self._cmds.xform(node, worldSpace=True, rotation=tuple(degrees(v) for v in rotation))

    def match_body_spine(self, plan, mode):
        self._require_transaction()
        c = self._cmds
        if mode == "ik":
            frames = tuple(self._spine_world_frame(j.path) for j in plan.joints[:3])
            positions = tuple(frame[0][12:15] for frame in frames)
            pole = solve_limb_pole_position(*positions, frames[0][1][1], limb_label="Spine", distance_scale=0.75)
            self._transaction_changed = True
            owner = c.getAttr(plan.root_path + ".advPySpineOwner")
            if owner in ("adv_py.spine.v2", "adv_py.spine.v3",
                         "adv_py.spine.v4", "adv_py.spine.v5"):
                c.setAttr(plan.stretch_plug, 0.0)
            if owner in ("adv_py.spine.v3", "adv_py.spine.v4",
                         "adv_py.spine.v5"):
                for index in (1, 2):
                    c.setAttr(plan.ik_control + f".Lenght{index}", 1.0)
                    c.setAttr(plan.ik_control + f".Fatness{index}", 0.0)
            if owner in ("adv_py.spine.v4", "adv_py.spine.v5"):
                c.setAttr(plan.pole_lock_plug, 0.0)
            if owner == "adv_py.spine.v5":
                c.setAttr(plan.anti_pop_plug, 0.0)
            c.xform(plan.ik_driver, worldSpace=True, translation=spine_ik_goal_position(*positions))
            self._spine_set_world_rotation(plan.ik_driver, frames[2][0])
            c.xform(plan.pole_control, worldSpace=True, translation=pole)
            c.setAttr(plan.roll_plug, spine_roll_degrees(frames[1][1], self._spine_world_frame(plan.joints[4].path)[1]))
            c.setAttr(plan.blend_plug, 1.0)
        else:
            frames = tuple(self._spine_world_frame(path)[0] for path in (plan.joints[3].path, plan.waist_output, plan.joints[5].path))
            self._transaction_changed = True
            for control, matrix in zip(plan.fk_controls, frames):
                self._spine_set_world_rotation(control, matrix)
            c.setAttr(plan.blend_plug, 0.0)
