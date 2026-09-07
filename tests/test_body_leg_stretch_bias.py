import unittest

from adv_py.core import (
    BodyLegStretchBiasValidationError,
    biased_stretch_factors,
)


class BodyLegStretchBiasTests(unittest.TestCase):
    def test_default_share_preserves_uniform_stretch(self):
        factors = biased_stretch_factors((4.0, 6.0), 1.5, 0.4)

        self.assertAlmostEqual(factors[0], 1.5)
        self.assertAlmostEqual(factors[1], 1.5)

    def test_extreme_shares_preserve_total_length(self):
        upper_only = biased_stretch_factors((4.0, 6.0), 1.5, 1.0)
        lower_only = biased_stretch_factors((4.0, 6.0), 1.5, 0.0)

        self.assertEqual(upper_only, (2.25, 1.0))
        self.assertAlmostEqual(lower_only[0], 1.0)
        self.assertAlmostEqual(lower_only[1], 11.0 / 6.0)
        for factors in (upper_only, lower_only):
            self.assertAlmostEqual(
                4.0 * factors[0] + 6.0 * factors[1],
                15.0,
            )

    def test_rejects_compression_zero_length_and_invalid_share(self):
        invalid = (
            ((4.0, 6.0), 0.9, 0.5),
            ((0.0, 6.0), 1.2, 0.5),
            ((4.0, 6.0), 1.2, 1.1),
        )
        for lengths, ratio, share in invalid:
            with self.subTest(lengths=lengths, ratio=ratio, share=share):
                with self.assertRaisesRegex(
                    BodyLegStretchBiasValidationError,
                    "无效",
                ):
                    biased_stretch_factors(lengths, ratio, share)


if __name__ == "__main__":
    unittest.main()
