import unittest

from adv_py.adapters.maya_spline_matching import _solve_linear
from adv_py.core.character_registry import CharacterRegistryError


class SplineLinearSolveTests(unittest.TestCase):
    def test_pivoted_system_recovers_coupled_parameters(self):
        matrix = ((0.,2.,1.),(1.,-1.,0.),(3.,1.,3.))
        wanted = (2.,-3.,4.)
        values = tuple(sum(a*b for a,b in zip(row,wanted)) for row in matrix)
        actual = _solve_linear(matrix,values)
        for a,b in zip(actual,wanted):self.assertAlmostEqual(a,b)

    def test_degenerate_controls_are_rejected(self):
        with self.assertRaises(CharacterRegistryError):
            _solve_linear(((1.,2.),(2.,4.)),(1.,2.))
