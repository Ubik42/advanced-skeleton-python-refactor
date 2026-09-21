import unittest
from adv_py.core.limb_shape_matching import matched_local_length, matched_volume_factor
from adv_py.core.character_registry import CharacterRegistryError


class LimbShapeMatchingTests(unittest.TestCase):
    def test_rotated_scaled_parent_preserves_signed_local_length(self):
        matrix=(0.,2.,0.,0.,-2.,0.,0.,0.,0.,0.,2.,0.,7.,8.,9.,1.)
        self.assertAlmostEqual(matched_local_length((7.,8.,9.),(7.,14.,9.),matrix,'X',-1.),-3.)
        self.assertAlmostEqual(matched_local_length((7.,8.,9.),(1.,8.,9.),matrix,'Y',1.),3.)

    def test_volume_factor_preserves_existing_width(self):
        self.assertAlmostEqual(matched_volume_factor(.75,.5),1.5)
        self.assertAlmostEqual(matched_volume_factor(1.,.8)*.8,1.)

    def test_degenerate_and_nonfinite_shape_inputs_rejected(self):
        matrix=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
        for reference in (0.,True,float('nan')):
            with self.subTest(reference=reference),self.assertRaises(CharacterRegistryError):
                matched_local_length((0,0,0),(1,0,0),matrix,'X',reference)
        with self.assertRaises(CharacterRegistryError):matched_local_length((0,0,0),(0,0,0),matrix,'X',1.)
        for width,base in ((0.,1.),(1.,0.),(float('nan'),1.),(1.,float('inf')),(1e308,1e-7)):
            with self.subTest(width=width,base=base),self.assertRaises(CharacterRegistryError):matched_volume_factor(width,base)
