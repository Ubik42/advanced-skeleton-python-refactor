import unittest

from adv_py.core import BodyArmStretchValidationError, compensated_stretch_ratio


class BodyArmStretchTests(unittest.TestCase):
    def test_compensates_world_distance_by_global_scale(self):
        self.assertAlmostEqual(compensated_stretch_ratio(10.0, 10.0, 1.0), 1.0)
        self.assertAlmostEqual(compensated_stretch_ratio(20.0, 10.0, 2.0), 1.0)
        self.assertAlmostEqual(compensated_stretch_ratio(27.0, 10.0, 2.0), 1.35)

    def test_rejects_non_positive_or_non_finite_inputs(self):
        for values in ((0.0, 1.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 0.0), (float("inf"), 1.0, 1.0)):
            with self.subTest(values=values):
                with self.assertRaisesRegex(BodyArmStretchValidationError, "正有限数值"):
                    compensated_stretch_ratio(*values)


if __name__ == "__main__":
    unittest.main()
