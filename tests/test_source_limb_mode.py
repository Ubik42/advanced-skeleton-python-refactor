import json
import unittest
from dataclasses import asdict
from types import SimpleNamespace as Row

from adv_py.core.character_registry import canonical,CharacterRegistryError
from adv_py.core.fit_symmetry import FitBuildSide
from adv_py.core.source_limb_mode import plan_source_limb_modes,decode_source_limb_mode


def fixture(side='R',two=False):
    suffix='_'+side
    root='|Group|DeformationSystem|Root_M'
    start=root+'|Shoulder'+suffix
    middle=start+'|Elbow'+suffix
    end=middle+'|Wrist'+suffix
    joints=[Row(path=root,name='Root_M',parent_path='|Group|DeformationSystem')]
    joints.extend(Row(path=node,name=node.rsplit('|',1)[-1],parent_path=node.rsplit('|',1)[0])
                  for node in (start,middle,end))
    sources=(start,start,end) if two else (start,middle,end)
    mechanisms=tuple(Row(path='|Mechanism|IK'+str(i),source_joint=node) for i,node in enumerate(sources))
    ik=Row(chain=tuple(j.path for j in mechanisms),side=FitBuildSide(side),
           source_pole_length=20.,wrist_offset_path='|IKOffset',pole_offset_path='|PoleOffset')
    blend_side=Row(side=ik.side,attribute='armIkFk_'+side,
                   joints=tuple(Row(fk_driver='|Mechanism|FK'+str(i)) for i in range(3)))
    limb=Row(label='Arm',mechanisms=Row(joints=mechanisms),ik=Row(limbs=(ik,)),
             blend=Row(sides=(blend_side,),settings_path='|AdvPy_ArmSettings'),
             root_frames=(Row(joint=ik.chain[0],frame='|IKParent'),))
    fk=Row(controls=tuple(Row(driven_joint=row.fk_driver,control_path='|Control'+str(i),
                              offset_path='|Offset'+str(i)) for i,row in enumerate(blend_side.joints)),
           hidden_controls=frozenset({'|Control1'}))
    hierarchy=Row(joints=(Row(world_position=(0.,0.,0.)),Row(world_position=(0.,80.,0.))))
    return limb,Row(root=root,joints=tuple(joints)),hierarchy,fk


class SourceLimbModeTests(unittest.TestCase):
    def plan(self,side='R',two=False):
        limb,body,hierarchy,fk=fixture(side,two)
        return plan_source_limb_modes(limb,body,hierarchy,(),
            '|Group|MotionSystem|RootSystem|LegLockConstrained',True,fk)[0]

    def test_parent_visibility_and_public_units_for_both_sides(self):
        for side in ('R','L'):
            plan=self.plan(side)
            self.assertEqual(plan.source_mode.name,'FKIKArm_'+side)
            self.assertEqual(plan.source_mode.parent_source,
                             '|Group|MotionSystem|RootSystem|LegLockConstrained')
            self.assertTrue(plan.mode_plug.endswith('.FKIKBlend'))
            self.assertEqual(plan.source_mode.side_sign,-1 if side=='L' else 1)
            self.assertEqual(plan.visibility_targets,(('ik','|IKOffset'),('ik','|PoleOffset'),
                ('ik','|IKParent'),('fk','|Offset0'),('fk','|Offset2')))
            self.assertEqual(decode_source_limb_mode(canonical(asdict(plan))),plan)

    def test_original_two_joint_chain_keeps_repeated_start_middle(self):
        plan=self.plan(two=True)
        self.assertEqual(plan.body_joints[0],plan.body_joints[1])
        self.assertEqual(decode_source_limb_mode(canonical(asdict(plan))),plan)

    def test_semantic_body_keeps_a_physical_part_parent(self):
        limb,body,hierarchy,fk=fixture()
        part='|Group|DeformationSystem|Root_M|SpinePart2_M'
        body.joints[1].parent_path=part
        plan=plan_source_limb_modes(limb,body,hierarchy,(),'|RootFollow',True,fk)[0]
        self.assertEqual(plan.source_mode.parent_source,part)

    def test_saved_record_rejects_cross_side_and_unrecorded_root_visibility(self):
        original=asdict(self.plan())
        for field,value in (('body_joints',[*original['body_joints'][:-1], '|Wrist_L']),
                            ('root_frame','|Unrecorded'),
                            ('visibility_targets',[('ik','|IKOffset'),('fk','|IKOffset')])):
            invalid=json.loads(canonical(original));invalid[field]=value
            with self.assertRaises(CharacterRegistryError):decode_source_limb_mode(canonical(invalid))

    def test_schema_does_not_accept_unbounded_unknown_fields(self):
        raw=asdict(self.plan());raw['shortcut']='ignore original'
        with self.assertRaises(CharacterRegistryError):decode_source_limb_mode(canonical(raw))
