"""World-frame interpolation for a changing spine joint count."""
from math import cos, radians, sin, sqrt
import unittest

from adv_py.core.spine_pose_resampling import (
    SpinePoseResamplingError,resample_spine_world_matrices)


def frame(y,angle=0.,scale=1.):
    a=radians(angle);c=cos(a)*scale;s=sin(a)*scale
    return (c,s,0.,0.,-s,c,0.,0.,0.,0.,scale,0.,0.,y,0.,1.)


class SpinePoseResamplingTests(unittest.TestCase):
    def test_interpolates_position_rotation_and_preserves_anchors(self):
        source=(frame(0.,0.),frame(1.,30.),frame(2.,60.),frame(3.,90.))
        target=resample_spine_world_matrices(source,(0.,.2,.4,.5,.6,.8,1.))
        self.assertEqual(target[0],source[0])
        self.assertEqual(target[-1],source[-1])
        self.assertAlmostEqual(target[3][13],1.5)
        self.assertAlmostEqual(target[3][0],cos(radians(45)),places=6)
        self.assertAlmostEqual(target[3][1],sin(radians(45)),places=6)
        self.assertAlmostEqual(target[3][4],-sin(radians(45)),places=6)

    def test_uses_actual_arc_lengths_and_uniform_scale(self):
        source=(frame(0.,scale=1.5),frame(1.,scale=1.5),
                frame(4.,scale=1.5),frame(5.,scale=1.5))
        target=resample_spine_world_matrices(source,(0.,.2,.5,.8,1.))
        self.assertEqual(target[1],source[1])
        self.assertAlmostEqual(target[2][13],2.5)
        self.assertAlmostEqual(target[2][0],1.5)
        self.assertEqual(target[-2],source[2])

    def test_explicit_bind_positions_and_invalid_frames(self):
        source=(frame(0.),frame(1.),frame(3.))
        result=resample_spine_world_matrices(source,(0.,.25,.5,.75,1.),
            source_positions=(0.,.25,1.))
        self.assertEqual(result[1],source[1])
        self.assertAlmostEqual(result[2][13],1.+(3.-1.)/3)
        bad=list(source[1]);bad[4]=.4;bad[5]=sqrt(.84)
        with self.assertRaisesRegex(SpinePoseResamplingError,'shear'):
            resample_spine_world_matrices((source[0],tuple(bad),source[2]),(0.,1.))
        with self.assertRaisesRegex(SpinePoseResamplingError,'距离'):
            resample_spine_world_matrices((source[0],source[0]),(0.,1.))
        with self.assertRaisesRegex(SpinePoseResamplingError,'严格递增'):
            resample_spine_world_matrices(source,(0.,.5,.5,1.))
        huge=list(source[1]);huge[0]=1e308
        with self.assertRaises(SpinePoseResamplingError):
            resample_spine_world_matrices((source[0],tuple(huge),source[2]),(0.,1.))


if __name__=='__main__':
    unittest.main()
