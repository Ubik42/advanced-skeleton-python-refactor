import unittest

from adv_py.core import (
    BodyArmBlendPlan,
    BodyArmBlendSideSpec,
    BodyArmStretchPlan,
    BodyArmStretchSideSpec,
    BodyArmTwistJointSpec,
    BodyArmTwistPlan,
    BodyArmTwistSegment,
    BodyArmVolumeValidationError,
    FitBuildSide,
    plan_body_arm_volume,
    volume_preservation_scale,
)


def stretch_side(side, suffix):
    return BodyArmStretchSideSpec(
        side,
        f"armStretch_{suffix}",
        f"|Start_{suffix}",
        f"Start_{suffix}",
        (0.0, 0.0, 0.0),
        f"|Wrist_{suffix}",
        f"Distance_{suffix}",
        f"Ratio_{suffix}",
        f"Clamp_{suffix}",
        f"StretchBlend_{suffix}",
        f"Segments_{suffix}",
        10.0,
        (f"|Elbow_{suffix}", f"|Wrist_{suffix}"),
        (5.0, 5.0),
    )


def twist_joint(side, suffix, index):
    return BodyArmTwistJointSpec(
        side,
        BodyArmTwistSegment.LOWER,
        index / 3.0,
        f"|Twist|Base_{suffix}|Helper{index}_{suffix}",
        f"Helper{index}_{suffix}",
        f"|Twist|Base_{suffix}",
        f"|Elbow_{suffix}",
        f"|Wrist_{suffix}",
        f"Position{index}_{suffix}",
        f"Scale{index}_{suffix}",
        f"Project_{suffix}",
        (float(index), 0.0, 0.0),
    )


class BodyArmVolumeTests(unittest.TestCase):
    def test_computes_full_partial_and_disabled_volume_preservation(self):
        self.assertAlmostEqual(volume_preservation_scale(1.44), 5.0 / 6.0)
        self.assertAlmostEqual(volume_preservation_scale(1.44, 0.0), 1.0)
        self.assertAlmostEqual(volume_preservation_scale(1.44, 0.5), 11.0 / 12.0)

    def test_plans_bilateral_helper_scale_outputs(self):
        stretch = BodyArmStretchPlan(
            "|AdvPy_ArmSettings",
            (
                stretch_side(FitBuildSide.RIGHT, "R"),
                stretch_side(FitBuildSide.LEFT, "L"),
            ),
        )
        twist = BodyArmTwistPlan(
            "|Twist",
            "Twist",
            (),
            tuple(
                twist_joint(side, suffix, index)
                for suffix, side in (
                    ("R", FitBuildSide.RIGHT),
                    ("L", FitBuildSide.LEFT),
                )
                for index in (1, 2)
            ),
        )
        blend = BodyArmBlendPlan(
            "|AdvPy_ArmSettings",
            "AdvPy_ArmSettings",
            (
                BodyArmBlendSideSpec(FitBuildSide.RIGHT, "armIkFk_R", "Reverse_R", ()),
                BodyArmBlendSideSpec(FitBuildSide.LEFT, "armIkFk_L", "Reverse_L", ()),
            ),
        )

        plan = plan_body_arm_volume(stretch, twist, blend)

        self.assertEqual(plan.settings_path, "|AdvPy_ArmSettings")
        self.assertEqual(len(plan.sides), 2)
        self.assertTrue(all(spec.exponent == -0.5 for spec in plan.sides))
        self.assertEqual(plan.sides[0].mode_attribute, "armIkFk_R")
        self.assertEqual(plan.sides[0].mode_blend_name, "AdvPy_ArmVolumeMode_R")
        self.assertEqual(
            plan.sides[0].helper_joints,
            (
                "|Twist|Base_R|Helper1_R",
                "|Twist|Base_R|Helper2_R",
            ),
        )

    def test_rejects_invalid_ratio_or_strength(self):
        for ratio, strength in ((0.0, 1.0), (1.0, -0.1), (1.0, 1.1)):
            with self.subTest(ratio=ratio, strength=strength):
                with self.assertRaisesRegex(BodyArmVolumeValidationError, "无效"):
                    volume_preservation_scale(ratio, strength)


if __name__ == "__main__":
    unittest.main()
