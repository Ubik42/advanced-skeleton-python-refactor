"""Maya driver graph for original-name limb Part Skin influences."""
from __future__ import annotations

from adv_py.core.limb_part_deform import LimbPartSegmentSpec
from .maya_body import MayaBodyBuildHost


class MayaLimbPartHost(MayaBodyBuildHost):
    def preflight_limb_part_source(self, spec: LimbPartSegmentSpec) -> None:
        if not self._cmds.objExists(spec.twist_source):
            raise ValueError("四肢分段需要有效的关节旋转：" + spec.twist_source)
        if spec.twist_ik_source and not self._cmds.objExists(
                spec.twist_ik_source):
            raise ValueError("四肢分段缺少 IK 关节旋转：" +
                             spec.twist_ik_source)
        if spec.split_body_twist:
            c = self._cmds
            marker = "AdvPy_AxialFKXSpine1_M.advPyAxialBodyOwner"
            constraint = f"AdvPy_{spec.stem}IKFKBlend_{spec.side}"
            if (not c.objExists(marker)
                    or c.getAttr(marker) != "adv_py.axial_body.v1"
                    or not c.objExists(constraint + ".offsetX")
                    or not c.getAttr(constraint + ".offsetX",
                                     settable=True)):
                raise ValueError("四肢分段扭转需要完整的轴向导向驱动")
        if spec.up_twist_source and not self._cmds.objExists(spec.up_twist_source):
            raise ValueError("四肢分段缺少远端扭转来源：" + spec.up_twist_source)
        if spec.up_twist_source:
            end = "Wrist" if spec.stem == "Elbow" else "Knee"
            if not self._cmds.objExists(f"AdvPy_{end}FK_{spec.side}.rotate"):
                raise ValueError("四肢分段缺少远端 FK 控制：" + end)
        control = f"AdvPy_{spec.stem}FK_{spec.side}"
        settings = "AdvPy_ArmSettings" if spec.stem in ("Shoulder", "Elbow") else "AdvPy_LegSettings"
        mode = "armIkFk" if spec.stem in ("Shoulder", "Elbow") else "legIkFk"
        if not self._cmds.objExists(control + ".scale") or not self._cmds.objExists(
                f"{settings}.{mode}_{spec.side}"):
            raise ValueError("四肢分段需要完整的 FK 控制和 IK/FK 模式：" + control)
        if not self._cmds.objExists(spec.fatness_control):
            raise ValueError("四肢分段缺少 IK 控制：" + spec.fatness_control)
        if self._cmds.objExists(spec.fatness_control + "." + spec.fatness_attribute):
            raise ValueError("四肢分段 Fatness 属性已被占用：" +
                             spec.fatness_control + "." + spec.fatness_attribute)
        if not self._cmds.objExists(spec.volume_source):
            raise ValueError("四肢分段缺少体积驱动：" + spec.volume_source)

    def create_limb_part_segment(self, spec: LimbPartSegmentSpec) -> None:
        self._require_transaction()
        c = self._cmds
        self.preflight_limb_part_source(spec)
        self._transaction_changed = True

        translation = c.createNode("multiplyDivide", name=spec.translation_name)
        c.connectAttr(spec.end + ".translate", translation + ".input1")
        c.setAttr(translation + ".input2", 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)
        scale_blend = c.createNode("blendColors", name=spec.scale_blend_name)
        c.setAttr(scale_blend + ".color1", 1.0, 1.0, 1.0)
        c.connectAttr(spec.volume_source, scale_blend + ".color1R")
        c.addAttr(spec.fatness_control, longName=spec.fatness_attribute,
                  attributeType="double", defaultValue=0.0, keyable=True)
        fatness = c.createNode("plusMinusAverage", name=spec.fatness_add_name)
        c.connectAttr(spec.volume_source, fatness + ".input1D[0]")
        c.connectAttr(spec.fatness_control + "." + spec.fatness_attribute,
                      fatness + ".input1D[1]")
        c.connectAttr(fatness + ".output1D", scale_blend + ".color1G")
        c.connectAttr(fatness + ".output1D", scale_blend + ".color1B")
        control = f"AdvPy_{spec.stem}FK_{spec.side}"
        settings = "AdvPy_ArmSettings" if spec.stem in ("Shoulder", "Elbow") else "AdvPy_LegSettings"
        mode = "armIkFk" if spec.stem in ("Shoulder", "Elbow") else "legIkFk"
        c.connectAttr(f"{settings}.{mode}_{spec.side}", scale_blend + ".blender")
        c.connectAttr(control + ".scale", scale_blend + ".color2")
        first_translation = c.createNode("multiplyDivide",
                                         name=spec.first_translation_name)
        c.connectAttr(translation + ".output", first_translation + ".input1")
        c.connectAttr(scale_blend + ".output", first_translation + ".input2")

        compose = c.createNode("composeMatrix", name=spec.twist_compose_name)
        twist_decompose = c.createNode("decomposeMatrix",
                                         name=spec.twist_decompose_name)
        project = c.createNode("quatToEuler", name=spec.twist_project_name)
        c.connectAttr(spec.twist_source, compose + ".inputRotate")
        rotate_order_source = (spec.twist_source.rsplit(".", 1)[0]
                               if spec.twist_mode_blend_name else spec.start)
        c.connectAttr(rotate_order_source + ".rotateOrder",
                      compose + ".inputRotateOrder")
        c.connectAttr(compose + ".outputMatrix",
                      twist_decompose + ".inputMatrix")
        c.connectAttr(twist_decompose + ".outputQuatX",
                      project + ".inputQuatX")
        c.connectAttr(twist_decompose + ".outputQuatW",
                      project + ".inputQuatW")
        twist_angle = project + ".outputRotateX"
        if spec.twist_mode_blend_name:
            ik_compose = c.createNode("composeMatrix",
                name=spec.twist_mode_blend_name + "IkCompose")
            ik_decompose = c.createNode("decomposeMatrix",
                name=spec.twist_mode_blend_name + "IkDecompose")
            ik_project = c.createNode("quatToEuler",
                name=spec.twist_mode_blend_name + "IkProject")
            ik_driver = spec.twist_ik_source.rsplit(".", 1)[0]
            c.connectAttr(spec.twist_ik_source,
                          ik_compose + ".inputRotate")
            c.connectAttr(ik_driver + ".rotateOrder",
                          ik_compose + ".inputRotateOrder")
            c.connectAttr(ik_compose + ".outputMatrix",
                          ik_decompose + ".inputMatrix")
            c.connectAttr(ik_decompose + ".outputQuatX",
                          ik_project + ".inputQuatX")
            c.connectAttr(ik_decompose + ".outputQuatW",
                          ik_project + ".inputQuatW")
            mode_blend = c.createNode("blendTwoAttr",
                                      name=spec.twist_mode_blend_name)
            c.connectAttr(twist_angle, mode_blend + ".input[0]")
            c.connectAttr(ik_project + ".outputRotateX",
                          mode_blend + ".input[1]")
            module = "Leg" if spec.stem == "Hip" else "Arm"
            c.connectAttr(f"AdvPy_{module}Settings."
                          + f"{module.lower()}IkFk_{spec.side}",
                          mode_blend + ".attributesBlender")
            twist_angle = mode_blend + ".output"
        if spec.split_body_twist:
            reverse = c.createNode("multDoubleLinear",
                name=spec.twist_compose_name + "BodyReverse")
            c.setAttr(reverse + ".input2", -1.0)
            c.connectAttr(twist_angle,
                          reverse + ".input1")
            c.connectAttr(reverse + ".output",
                f"AdvPy_{spec.stem}IKFKBlend_{spec.side}.offsetX")

        parent = spec.start
        # The original Body end lies below both Part joints. The new Body end
        # is a direct child of start; compensate the proximal twist on the
        # helper branch while retaining the original editable amounts.
        for name, path, amount in (
                (spec.part1_name, spec.part1, 1.0 / 3.0),
                (spec.part2_name, spec.part2, 2.0 / 3.0)):
            joint = c.createNode("joint", name=name, parent=parent,
                                 skipSelect=True)
            joint = (c.ls(joint, long=True) or [joint])[0]
            if joint != path:
                raise RuntimeError("四肢分段关节路径漂移：" + name)
            c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind",
                      dataType="string")
            c.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                      "limb-part-v1", type="string", lock=True)
            c.addAttr(joint, longName="twistAmount", attributeType="double",
                      defaultValue=amount, keyable=True)
            c.addAttr(joint, longName="twistAddition", attributeType="double",
                      defaultValue=0.0, keyable=True)
            c.connectAttr((first_translation if amount < 0.5 else translation)
                          + ".output", joint + ".translate")
            c.connectAttr(parent + ".scale", joint + ".inverseScale")
            for axis, color in (("X", "R"), ("Y", "G"), ("Z", "B")):
                c.connectAttr(scale_blend + ".output" + color,
                              joint + ".scale" + axis)
            parent = joint

        first = c.createNode("multDoubleLinear", name=spec.twist1_name)
        second = c.createNode("multDoubleLinear", name=spec.twist2_name)
        first_sum = c.createNode("plusMinusAverage", name=spec.twist1_sum_name)
        second_sum = c.createNode("plusMinusAverage", name=spec.twist2_sum_name)
        first_comp = c.createNode("plusMinusAverage", name=spec.twist1_comp_name)
        second_comp = c.createNode("plusMinusAverage", name=spec.twist2_comp_name)
        for amount_node, joint in ((first, spec.part1), (second, spec.part2)):
            c.connectAttr(twist_angle, amount_node + ".input1")
            c.connectAttr(joint + ".twistAmount", amount_node + ".input2")
        for amount_node, sum_node, joint in (
                (first, first_sum, spec.part1),
                (second, second_sum, spec.part2)):
            c.connectAttr(amount_node + ".output", sum_node + ".input1D[0]")
            c.connectAttr(joint + ".twistAddition", sum_node + ".input1D[1]")
        if spec.up_twist_source:
            end = "Wrist" if spec.stem == "Elbow" else "Knee"
            fk_control = f"AdvPy_{end}FK_{spec.side}"
            up_compose = c.createNode("composeMatrix", name=spec.up_fk_compose_name)
            up_decompose = c.createNode("decomposeMatrix",
                                          name=spec.up_fk_decompose_name)
            up_project = c.createNode("quatToEuler",
                                        name=spec.up_fk_project_name)
            up_blend = c.createNode("blendTwoAttr", name=spec.up_blend_name)
            c.connectAttr(fk_control + ".rotate", up_compose + ".inputRotate")
            c.connectAttr(fk_control + ".rotateOrder",
                          up_compose + ".inputRotateOrder")
            c.connectAttr(up_compose + ".outputMatrix",
                          up_decompose + ".inputMatrix")
            c.connectAttr(up_decompose + ".outputQuatX",
                          up_project + ".inputQuatX")
            c.connectAttr(up_decompose + ".outputQuatW",
                          up_project + ".inputQuatW")
            c.connectAttr(up_project + ".outputRotateX",
                          up_blend + ".input[0]")
            c.connectAttr(spec.up_twist_source, up_blend + ".input[1]")
            c.connectAttr(f"{settings}.{mode}_{spec.side}",
                          up_blend + ".attributesBlender")
            for name, joint, sum_node in (
                    (spec.up_twist1_name, spec.part1, first_sum),
                    (spec.up_twist2_name, spec.part2, second_sum)):
                upstream = c.createNode("multDoubleLinear", name=name)
                c.connectAttr(up_blend + ".output", upstream + ".input1")
                c.connectAttr(joint + ".twistAmount", upstream + ".input2")
                c.connectAttr(upstream + ".output", sum_node + ".input1D[2]")
        c.setAttr(first_comp + ".operation", 2)
        c.setAttr(second_comp + ".operation", 2)
        c.connectAttr(first_sum + ".output1D", first_comp + ".input1D[0]")
        c.connectAttr(twist_angle,
                      first_comp + ".input1D[1]")
        c.connectAttr(second_sum + ".output1D", second_comp + ".input1D[0]")
        c.connectAttr(first_sum + ".output1D", second_comp + ".input1D[1]")
        c.connectAttr((first_sum if spec.split_body_twist else first_comp)
                      + ".output1D", spec.part1 + ".rotateX")
        c.connectAttr(second_comp + ".output1D", spec.part2 + ".rotateX")
        if spec.split_body_twist and spec.stem == "Shoulder":
            proxy = c.createNode("joint",
                name=f"AdvPy_ElbowOriginalLocal_{spec.side}",
                parent=spec.part2, skipSelect=True)
            c.addAttr(proxy, longName="advPyAuxiliaryInfluenceKind",
                      dataType="string")
            c.setAttr(proxy + ".advPyAuxiliaryInfluenceKind",
                      "original-local-angle-v1", type="string", lock=True)
            c.setAttr(proxy + ".rotateOrder", c.getAttr(
                f"AdvPy_ElbowFK_{spec.side}.rotateOrder"))
            c.setAttr(proxy + ".jointOrient", *c.getAttr(
                spec.end + ".jointOrient")[0])
            c.xform(proxy, worldSpace=True, matrix=c.xform(
                spec.end, query=True, worldSpace=True, matrix=True))
            c.orientConstraint(spec.end, proxy, maintainOffset=False,
                name=f"AdvPy_ElbowOriginalLocalOrient_{spec.side}")

    def capture_limb_part_segment(self, spec: LimbPartSegmentSpec
                                  ) -> tuple[tuple[str, str, tuple[float, float, float]], ...]:
        c = self._cmds
        result = []
        for path in (spec.part1, spec.part2):
            matches = c.ls(path, long=True, type="joint") or []
            if len(matches) != 1:
                raise RuntimeError("四肢分段关节缺失：" + path)
            parent = (c.listRelatives(path, parent=True,
                                      fullPath=True) or [""])[0]
            position = tuple(float(value) for value in c.xform(path,
                query=True, worldSpace=True, translation=True))
            result.append((path, parent, position))
        return tuple(result)
