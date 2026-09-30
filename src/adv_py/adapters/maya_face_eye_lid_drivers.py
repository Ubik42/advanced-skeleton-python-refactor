"""Original asFaceEyeLid blink/lidOut/Fleshy networks, 33636–33788."""
from adv_py.core.control_curves import _inverse_matrix


class MayaFaceEyeLidDriversMixin:
    def _original_lid_normalize_reverse(self, name, driver):
        c = self._cmds
        conversion = c.createNode("unitConversion", name=name + "UnitConversion")
        c.setAttr(conversion + ".conversionFactor", .1)
        c.connectAttr(driver, conversion + ".input")
        reverse = c.createNode("reverse", name=name + "Reverse")
        c.connectAttr(conversion + ".output", reverse + ".inputX")
        return conversion, reverse

    def create_original_eye_lid_driver_graph(self, source):
        self._require_transaction()
        c = self._cmds
        for side, factor in (("_R", 1), ("_L", -1)):
            for arc, arc_factor in (("upper", 1), ("lower", -1)):
                control = arc + "Lid" + side
                if not c.objExists(control + ".blink"):
                    c.addAttr(control, longName="blink", attributeType="double", softMinValue=0,
                              softMaxValue=10, keyable=True)
                    self.original_face_output_bw(control + ".blink")
                center_range = "upperblinkCenterSR" + side
                if arc == "upper":
                    c.addAttr(control, longName="blinkCenter", attributeType="double", softMinValue=0,
                              softMaxValue=10, defaultValue=2, keyable=True)
                    center = self.original_face_output_bw(control + ".blinkCenter")
                    c.createNode("setRange", name=center_range)
                    c.setAttr(center_range + ".oldMax", 10, 10, 10, type="float3")
                    c.connectAttr("bw" + control + "_blink.output", center_range + ".valueX")
                    plus = c.createNode("plusMinusAverage", name="upperblinkCenterPMA" + side)
                    c.setAttr(plus + ".input1D[0]", 10)
                    c.setAttr(plus + ".operation", 2)
                    c.connectAttr(center, plus + ".input1D[1]")
                    c.connectAttr(plus + ".output1D", center_range + ".maxX")
                    c.connectAttr(center, center_range + ".maxY")
                else:
                    c.connectAttr("bw" + control + "_blink.output", center_range + ".valueY")
                temp = c.createNode("transform", name="tempTransform", parent="upperLid" + side)
                c.parent(temp, "lowerLid" + side)
                close_y = c.getAttr(temp + ".ty")
                c.delete(temp)
                divide = c.createNode("multiplyDivide", name=arc + "blinkBlendMPD1" + side)
                c.setAttr(divide + ".operation", 2)
                plus = c.createNode("plusMinusAverage", name=arc + "blinkBlendPMA" + side)
                parallel = c.createNode("plusMinusAverage", name=arc + "blinkBlendForceParallelEvalPMA" + side)
                # Original deliberately evaluates all three axes: a direct TY
                # connection fails with keyed TX under parallel evaluation.
                for axis in "xyz":
                    c.connectAttr(control + ".t" + axis, parallel + ".input3D[0].input3D" + axis)
                c.connectAttr(parallel + ".output3D.output3Dy", plus + ".input3D[0].input3Dy")
                c.connectAttr("SDK" + control + ".ty", plus + ".input3D[1].input3Dy")
                c.connectAttr(plus + ".output3D.output3Dy", divide + ".input1Y")
                c.setAttr(divide + ".input2Y", close_y / -10.0 * arc_factor)
                weighted = c.createNode("blendWeighted", name=arc + "LidBlendWeighted" + side)
                c.connectAttr(center_range + ".outValue" + ("X" if arc == "upper" else "Y"), weighted + ".input[0]")
                c.connectAttr(divide + ".outputY", weighted + ".input[1]")
                conversion, reverse = self._original_lid_normalize_reverse(arc + "blinkBlend" + side, weighted + ".output")
                blend = arc + "LidCurveBlinkBS" + side
                c.connectAttr(conversion + ".output", blend + "." + arc + "ClosedLidCurve" + side)
                c.connectAttr(reverse + ".outputX", blend + "." + arc + "UnClosedLidCurve" + side)
                if not c.objExists(control + ".lidOut"):
                    c.addAttr(control, longName="lidOut", attributeType="double", softMinValue=0,
                              softMaxValue=10, keyable=True)
                    output = self.original_face_output_bw(control + ".lidOut")
                    self._original_lid_normalize_reverse(arc + "lidOutBlend" + side, output)
                c.connectAttr(arc + "lidOutBlend" + side + "UnitConversion.output", "LidSetup" + side + "." + arc + "LidOut")
                c.delete(arc + "lidOutBlend" + side + "Reverse")
            for part in ("Main", "Outer"):
                if part == "Outer" and source["simpler"]:
                    continue
                suffix = "Outer" if part == "Outer" else ""
                for corner in ("inner", "upper", "outer", "lower"):
                    self._original_lid_fleshy_driver(source, corner, suffix, side, factor)
            for attribute in c.listAttr("ctrlEye" + side, keyable=True) or []:
                plug = "ctrlEye" + side + "." + attribute
                if not c.getAttr(plug, lock=True):
                    self.original_face_output_bw(plug)

    def _original_lid_fleshy_driver(self, source, corner, suffix, side, factor):
        c = self._cmds
        stem = corner + "Lid" + suffix
        control = stem + side
        default = {"inner": 1, "upper": 7, "outer": 1, "lower": 3}[corner]
        if suffix:
            default /= 5.0
        fleshy = c.createNode("transform", name=stem + "Fleshy" + side, parent=stem + "Offset" + side)
        if c.objExists(stem + "Attach" + side):
            c.parent(fleshy, stem + "Attach" + side)
        c.parent("SDK" + control, fleshy)
        c.addAttr(control, longName="fleshy", attributeType="double", softMinValue=0,
                  softMaxValue=10, defaultValue=default, keyable=True)
        multiply = c.createNode("multiplyDivide", name=control + "FleshyMPD")
        tx = c.createNode("unitConversion", name=control + "FleshyTXConversion")
        ty = c.createNode("unitConversion", name=control + "FleshyTYConversion")
        c.setAttr(tx + ".conversionFactor", -.125 * factor)
        c.setAttr(ty + ".conversionFactor", -.130)
        if source["opm"]:
            dm = "EyeJointDM" + side
            if not c.objExists(dm):
                c.createNode("decomposeMatrix", name=dm)
                c.setAttr(dm + ".inputRotateOrder", c.getAttr("EyeJoint" + side + ".rotateOrder"))
                zero = c.createNode("multMatrix", name="EyeJointToZeroMM" + side)
                matrix = tuple(c.getAttr("EyeJointMM" + side + ".matrixSum")[0])
                c.setAttr(zero + ".matrixIn[0]", *_inverse_matrix(matrix), type="matrix")
                c.connectAttr("EyeJointMM" + side + ".matrixSum", zero + ".matrixIn[1]")
                c.connectAttr(zero + ".matrixSum", dm + ".inputMatrix")
            c.connectAttr(dm + ".outputRotateY", tx + ".input")
            c.connectAttr(dm + ".outputRotateX", ty + ".input")
        else:
            c.connectAttr("EyeJoint" + side + ".ry", tx + ".input")
            c.connectAttr("EyeJoint" + side + ".rx", ty + ".input")
        c.connectAttr(tx + ".output", multiply + ".input1X")
        c.connectAttr(ty + ".output", multiply + ".input1Y")
        for axis in "XY":
            c.connectAttr(control + ".fleshy", multiply + ".input2" + axis)
            c.connectAttr(multiply + ".output" + axis, fleshy + ".t" + axis.lower())
        if not suffix:
            if c.objExists(corner + "blinkBlendPMA" + side):
                c.connectAttr(fleshy + ".ty", corner + "blinkBlendPMA" + side + ".input3D[2].input3Dy")
            if c.objExists(corner + "LidJointPMAt" + side):
                c.connectAttr(fleshy + ".t", corner + "LidJointPMAt" + side + ".input3D[3]", force=True)
            c.connectAttr(fleshy + ".t", stem + "PMA" + side + ".input3D[2]")
