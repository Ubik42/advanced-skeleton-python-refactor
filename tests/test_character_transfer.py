import unittest
import json
from adv_py.core.character_preservation import character_transfer_error
from adv_py.core.character_registry import CharacterRegistryError


class CharacterTransferTests(unittest.TestCase):
    def setUp(self):
        self.matrix=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
        self.row=(1.,(('Root',self.matrix),),(('hand',self.matrix),),(('mesh-id',(1.,2.,3.)),),())

    def test_position_error_includes_actual_skin_geometry(self):
        changed=self.row[:3]+((('mesh-id',(1.,2.,3.2)),),())
        self.assertAlmostEqual(character_transfer_error((self.row,),(changed,)),.2)
        self.assertEqual(character_transfer_error((self.row,),(self.row,)),0.)
        self.assertEqual(character_transfer_error(json.loads(json.dumps([self.row])),(self.row,)),0.)

    def test_rejects_lost_frame_mesh_identity_and_nonfinite_positions(self):
        for changed in ((),((2.,)+self.row[1:],),(self.row[:3]+((),()),),
                        (self.row[:3]+((('mesh-id',(float('nan'),2.,3.)),),()),)):
            with self.assertRaises(ValueError):character_transfer_error((self.row,),changed)
