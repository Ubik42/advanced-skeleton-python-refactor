import unittest

from adv_py.core.least_squares import least_squares


class LeastSquaresTests(unittest.TestCase):
    def test_nonlinear_bounded_fit(self):
        state=[]
        def evaluate(p):
            state[:]=p
            x,y=p
            return (x*x+y-5.,x+y*y-5.)
        result=least_squares(evaluate,(1.,1.),bounds=((0.,3.),(0.,3.)))
        self.assertTrue(result.converged)
        self.assertEqual(tuple(state),result.parameters)
        self.assertLess(max(abs(v) for v in result.residual),1e-7)

    def test_rank_deficient_and_unreachable_bound(self):
        self.assertTrue(least_squares(lambda p:(p[0]+p[1]-3.,),(0.,0.)).converged)
        result=least_squares(lambda p:(p[0]-2.,),(.5,),bounds=((0.,1.),))
        self.assertFalse(result.converged)
        self.assertAlmostEqual(result.parameters[0],1.)

    def test_nonfinite_or_inconsistent_outputs_rejected(self):
        with self.assertRaises(ValueError):least_squares(lambda p:(float('nan'),),(0.,))
        with self.assertRaises(ValueError):least_squares(lambda p:(1.,),(0.,),bounds=((1.,2.),))


class NonfiniteSceneFrameTests(unittest.TestCase):
    def test_nonfinite_world_matrix_rejected_before_axis_calculation(self):
        from types import SimpleNamespace
        from adv_py.adapters.maya_spine import MayaBodySpineMixin
        from adv_py.core.fit_settings import FitSkeletonValidationError
        host=SimpleNamespace(_cmds=SimpleNamespace(xform=lambda *a,**k:[float('nan')]*16))
        with self.assertRaisesRegex(FitSkeletonValidationError,'世界矩阵'):
            MayaBodySpineMixin._spine_world_frame(host,'|InvalidJoint')
