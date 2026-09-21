from dataclasses import replace
import unittest
from adv_py.core.character_preservation import CharacterPreservation,PreservedCurve,PreservedSkin,PreservedDeformer,validate_preservation,validate_rebuild_layout
from adv_py.core.character_registry import CharacterRegistryError
from test_character_registry import registration_fixture
from test_character_pose import pose_fixture


class CharacterPreservationTests(unittest.TestCase):
    def setUp(self):
        reg=registration_fixture()
        curve=PreservedCurve('curve','curve-id','animCurveTA','time1.outTime',('control.rotateX',),
            (1.,11.),(0.,20.),('fixed','fixed'),('step','fixed'),(0.,12.),(0.,-10.),
            (1.,.7),(1.,.9),(False,False),(False,False),(11.,),True,3,4)
        matrix=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
        skin=PreservedSkin('skin','skin-id',(('mesh','mesh-id',1),),(('skinningMethod',2.),),
            ((4,'joint.worldMatrix[0]',matrix,''),),((0,((4,1.),)),),((0,.4),),())
        self.snapshot=CharacterPreservation(reg,pose_fixture(reg),7.,'film','hero',(curve,),(skin,),())

    def test_digest_detects_tangents_bind_matrices_and_sparse_weights(self):
        original=self.snapshot.content_digest
        changes=(replace(self.snapshot,curves=(replace(self.snapshot.curves[0],out_angles=(0.,-11.)),)),
                 replace(self.snapshot,skins=(replace(self.snapshot.skins[0],blend_weights=((0,.5),)),)),
                 replace(self.snapshot,skins=(replace(self.snapshot.skins[0],weights=((0,((4,.9),)),)),)))
        for changed in changes:self.assertNotEqual(changed.content_digest,original)
        self.assertEqual(validate_preservation(self.snapshot),self.snapshot)

    def test_rejects_partial_curves_invalid_indices_and_nonfinite_values(self):
        curve=self.snapshot.curves[0];skin=self.snapshot.skins[0]
        for bad in (replace(self.snapshot,curves=(replace(curve,in_weights=(1.,)),)),
                    replace(self.snapshot,curves=(replace(curve,breakdown_times=(8.,)),)),
                    replace(self.snapshot,curves=(curve,curve)),
                    replace(self.snapshot,skins=(replace(skin,weights=((0,((9,1.),)),)),)),
                    replace(self.snapshot,skins=(replace(skin,settings=(('envelope',float('nan')),)),))):
            with self.assertRaises(CharacterRegistryError):validate_preservation(bad)

    def test_deformer_stack_is_part_of_preservation_contract(self):
        deformer=PreservedDeformer('blend','blend-id','blendShape',(('meshShape',2),),
                                  (('envelope',.6),('weight[0]',.4)),('smile','weight[0]'),())
        retained=replace(self.snapshot,deformers=(deformer,))
        self.assertNotEqual(retained.content_digest,self.snapshot.content_digest)
        self.assertNotEqual(replace(retained,deformers=(replace(deformer,settings=(('envelope',.7),)),)).content_digest,
                            retained.content_digest)
        for invalid in (replace(deformer,node_type='unknown'),replace(deformer,mesh_stack=()),
                        replace(deformer,settings=(('envelope',float('nan')),))):
            with self.assertRaises(CharacterRegistryError):
                validate_preservation(replace(self.snapshot,deformers=(invalid,)))

    def test_replacement_requires_explicit_topology_and_bind_layout_compatibility(self):
        reg=self.snapshot.registration
        validate_rebuild_layout(reg,reg)
        changed=replace(reg,channels=(replace(reg.channels[0],key='different.control'),)+reg.channels[1:])
        with self.assertRaises(CharacterRegistryError):validate_rebuild_layout(reg,changed)
        matrix=list(reg.body[0].matrix);matrix[12]+=.01
        changed=replace(reg,body=(replace(reg.body[0],matrix=tuple(matrix)),)+reg.body[1:])
        with self.assertRaises(CharacterRegistryError):validate_rebuild_layout(reg,changed)
