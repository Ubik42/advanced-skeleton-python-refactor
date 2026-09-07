import unittest

from adv_py.core import (
    BodyLegKneePinValidationError,
    knee_pin_factors,
)


class BodyLegKneePinTests(unittest.TestCase):
    def test_zero_weight_preserves_normal_stretch_and_total_ratio(self):
        factors, ratio = knee_pin_factors(
            (-4.0, 6.0),
            (1.25, 1.5),
            (9.0, 7.0),
            1.0,
            0.0,
        )

        self.assertEqual(factors, (1.25, 1.5))
        self.assertAlmostEqual(ratio, 1.4)

    def test_full_pin_uses_global_scale_compensated_distances(self):
        factors, ratio = knee_pin_factors(
            (-4.0, 6.0),
            (1.25, 1.5),
            (12.0, 8.0),
            2.0,
            1.0,
        )

        self.assertAlmostEqual(factors[0], 1.5)
        self.assertAlmostEqual(factors[1], 2.0 / 3.0)
        self.assertAlmostEqual(ratio, 1.0)

    def test_partial_pin_clamps_degenerate_length_and_rejects_bad_input(self):
        factors, ratio = knee_pin_factors(
            (4.0, 6.0),
            (1.0, 1.0),
            (0.0, 12.0),
            2.0,
            0.5,
            minimum_length=0.2,
        )

        self.assertAlmostEqual(factors[0], 0.525)
        self.assertAlmostEqual(factors[1], 1.0)
        self.assertAlmostEqual(ratio, 0.81)
        invalid = (
            ((4.0, 6.0), (1.0, 1.0), (-1.0, 2.0), 1.0, 1.0),
            ((4.0, 6.0), (1.0, 1.0), (1.0, 2.0), 0.0, 1.0),
            ((4.0, 6.0), (1.0, 1.0), (1.0, 2.0), 1.0, 1.1),
        )
        for args in invalid:
            with self.subTest(args=args):
                with self.assertRaisesRegex(
                    BodyLegKneePinValidationError,
                    "无效",
                ):
                    knee_pin_factors(*args)


if __name__ == "__main__":
    unittest.main()
