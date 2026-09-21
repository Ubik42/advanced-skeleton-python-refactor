import unittest
from math import sqrt

from adv_py.core.body_spline import _basis, fit_spline_controls
from adv_py.core.fit_settings import FitSkeletonValidationError


class SplineCurveFitTests(unittest.TestCase):
    def test_joint_positions_lie_on_fitted_curve(self):
        for count in (3, 5, 9):
            points = tuple((0., float(i), .25 * ((i % 3) - 1)) for i in range(count))
            controls = fit_spline_controls(points)
            self.assertEqual(len(controls), max(4, count + 1))
            lengths = tuple(sqrt(sum((b - a) ** 2 for a, b in zip(left, right)))
                            for left, right in zip(points, points[1:]))
            total = sum(lengths)
            for index, point in enumerate(points):
                weights = _basis(len(controls), (len(controls) - 3) * sum(lengths[:index]) / total)
                actual = tuple(sum(weight * cv[axis] for weight, cv in zip(weights, controls))
                               for axis in range(3))
                self.assertLess(max(abs(a - b) for a, b in zip(actual, point)), 1e-5)

    def test_rejects_degenerate_or_nonfinite_points(self):
        for points in (((0., 0., 0.),),
                       ((0., 0., 0.), (0., 0., 0.)),
                       ((0., 0., 0.), (0., float('inf'), 0.))):
            with self.assertRaises(FitSkeletonValidationError):
                fit_spline_controls(points)
