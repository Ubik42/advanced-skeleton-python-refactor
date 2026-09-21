from types import SimpleNamespace
import unittest
from adv_py.core.body_arm_match import _signed_local_x_distance
from adv_py.core.body_leg_match import _signed_local_axis_distance


class LimbMatchScaleTests(unittest.TestCase):
    def parent(self,scale):
        return SimpleNamespace(world_position=(2.,3.,4.),world_axes=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.)),world_scale=scale)

    def test_arm_world_distance_becomes_local_length(self):
        parent=self.parent((1.5,1.5,1.5))
        self.assertAlmostEqual(_signed_local_x_distance(parent,SimpleNamespace(world_position=(6.5,3.,4.))),3.)
        self.assertAlmostEqual(_signed_local_x_distance(parent,SimpleNamespace(world_position=(-2.5,3.,4.))),-3.)

    def test_leg_uses_signed_principal_axis_scale(self):
        parent=self.parent((1.5,2.,3.))
        self.assertEqual(_signed_local_axis_distance(parent,SimpleNamespace(world_position=(2.,-5.,4.))),('Y',-4.))
        self.assertEqual(_signed_local_axis_distance(parent,SimpleNamespace(world_position=(2.,3.,13.))),('Z',3.))

    def test_invalid_scale_is_rejected(self):
        for scale in (0.,-1.,float('nan')):
            with self.subTest(scale=scale),self.assertRaises(ValueError):
                _signed_local_x_distance(self.parent((scale,1.,1.)),SimpleNamespace(world_position=(5.,3.,4.)))
