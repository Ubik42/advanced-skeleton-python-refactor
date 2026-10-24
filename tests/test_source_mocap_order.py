"""MoCap operations follow the original DeformationSystem traversal."""
from types import SimpleNamespace
import unittest

from adv_py.core.character_registry import CharacterChannel
from adv_py.core.name_matcher_fit import NameMatcherConstraintPair,NameMatcherConstraintPlan
from adv_py.core.name_matcher_mocap import plan_name_matcher_mocap,source_mocap_operations
from adv_py.core.fit_settings import FitSkeletonValidationError


class SourceMocapOrderTests(unittest.TestCase):
    def registration(self):
        channels=[]
        for joint in ('Wrist_R','Elbow_R','Shoulder_R','Chest_M'):
            channels.append(CharacterChannel('generic.fk.'+joint+'FK.rotateX','|FK'+joint,'rotateX'))
        for role,key in (('IKArm_R','arm.ik.R'),('PoleArm_R','arm.pole.R'),('IKSpine3_M','spine.ik')):
            channels.append(CharacterChannel(key+'.translateX','|'+role,'translateX'))
        channels.append(CharacterChannel('root.x.translateX','|AdvPy_RootX_M','translateX'))
        return SimpleNamespace(channels=tuple(channels),source_limbs=(),spine=None,additional_spines=(),
            nodes=(SimpleNamespace(path='|AdvPy_RootX_M'),))

    def test_pole_is_interleaved_before_next_fk_joint_and_root(self):
        pairs=tuple(NameMatcherConstraintPair('|'+name,'|source|'+name)
            for name in ('Wrist_R','Elbow_R','Shoulder_R','Chest_M','Root_M'))
        plan=plan_name_matcher_mocap(NameMatcherConstraintPlan(pairs,()),self.registration())
        operations=source_mocap_operations(plan)
        labels=[(kind,(plan.links[index].control if kind=='link' else plan.poles[index].control))
            for kind,index in operations]
        self.assertEqual(labels,[('link','|FKWrist_R'),('link','|IKArm_R'),
            ('link','|FKElbow_R'),('pole','|PoleArm_R'),('link','|FKShoulder_R'),
            ('link','|FKChest_M'),('link','|IKSpine3_M'),('link','|AdvPy_RootX_M')])
        self.assertEqual(plan.poles[0].source_joint,'|Elbow_R')

    def test_missing_fk_continues_before_ik_and_pole_branches(self):
        registration=self.registration()
        registration.channels=tuple(channel for channel in registration.channels
            if channel.node!='|FKElbow_R')
        pairs=(NameMatcherConstraintPair('|Elbow_R','|source|Elbow_R'),
            NameMatcherConstraintPair('|Root_M','|source|Root_M'))
        plan=plan_name_matcher_mocap(NameMatcherConstraintPlan(pairs,()),registration)
        self.assertFalse(plan.poles)
        self.assertEqual(plan.unmapped_controls,('Elbow_R',))

    def test_partial_or_duplicate_operation_schedule_is_rejected_before_write(self):
        pairs=(NameMatcherConstraintPair('|Root_M','|source|Root_M'),)
        plan=plan_name_matcher_mocap(NameMatcherConstraintPlan(pairs,()),self.registration())
        from dataclasses import replace
        for operations in ((('link',0),('link',0)),(('pole',0),),(('link',True),)):
            with self.assertRaises(FitSkeletonValidationError):
                source_mocap_operations(replace(plan,operations=operations))


if __name__=='__main__':unittest.main()
