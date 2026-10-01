import unittest
from dataclasses import replace

from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.character_registry import (CharacterRegistration,
    CharacterBindJoint,CharacterNode,CharacterChannel,CharacterRegistryError)
from adv_py.core.spline_control_rebuild import plan_spline_control_rebuild


MATRIX=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)


def registration(count):
    root='|Group|Spline'
    targets=tuple(root+f'|AdvPy_SplineIK{i}' for i in range(count))
    body=(CharacterBindJoint('|Body',None,MATRIX),
          CharacterBindJoint('|Body|End','|Body',MATRIX))
    spline=BodySplinePlan(root,(),tuple(row.path for row in body),(),
        '|Group|Pelvis','|Group|Chest',targets,
        tuple((0.,float(i)/(count-1),0.) for i in range(count)),
        ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.)),(1.,),
        source_curve_points=((0.,0.,0.),(0.,1.,0.)))
    channels=tuple(CharacterChannel(f'source.spline.{i}.translateX',target,'translateX')
        for i,target in enumerate(targets))+(CharacterChannel(
            'source.spline.stretchy',targets[-1],'stretchy',0.,10.),)
    nodes=tuple(CharacterNode(path,'uuid-'+str(i),'transform',root)
                for i,path in enumerate(targets))
    return CharacterRegistration('|Body','|FitSkeleton',channels,body,nodes,spline,None)


class SplineControlRebuildTests(unittest.TestCase):
    def test_indexed_animation_survives_and_endpoint_setting_moves(self):
        before,after=registration(3),registration(5)
        plan=plan_spline_control_rebuild(before,after,(('',5),))
        source=before.spine.settings+'.stretchy'
        self.assertEqual(plan.destination(source),after.spine.settings+'.stretchy')
        indexed=before.spine.targets[-1]+'.translateX'
        self.assertEqual(plan.destination(indexed),indexed)

    def test_removed_index_has_no_destination_but_settings_still_move(self):
        before,after=registration(5),registration(3)
        plan=plan_spline_control_rebuild(before,after,(('',3),))
        self.assertIsNone(plan.destination(before.spine.targets[-1]+'.translateX'))
        self.assertEqual(plan.destination(before.spine.settings+'.stretchy'),
                         after.spine.settings+'.stretchy')
        self.assertIn(before.spine.targets[-1],plan.removed_controls)

    def test_binding_changes_are_still_rejected(self):
        before,after=registration(3),registration(5)
        matrix=(*MATRIX[:12],1.,*MATRIX[13:])
        after=replace(after,body=(replace(after.body[0],matrix=matrix),after.body[1]))
        with self.assertRaises(CharacterRegistryError):
            plan_spline_control_rebuild(before,after,(('',5),))

    def test_other_system_channel_loss_is_rejected(self):
        before,after=registration(3),registration(5)
        before=replace(before,channels=before.channels+(
            CharacterChannel('arm.extra','|Arm','translateX'),))
        with self.assertRaises(CharacterRegistryError):
            plan_spline_control_rebuild(before,after,(('',5),))

    def test_fractional_boolean_duplicate_and_unknown_counts_rejected(self):
        for counts in ((('',True),),(('',3.5),),(('unknown',5),),(('',5),('',5))):
            with self.subTest(counts=counts),self.assertRaises(CharacterRegistryError):
                plan_spline_control_rebuild(registration(3),registration(5),counts)

    def test_nonselected_spline_cannot_change_channels(self):
        before,after=registration(3),registration(5)
        channel=CharacterChannel('other.spline.rotateX','|Other','rotateX',0.,1.)
        before=replace(before,channels=before.channels+(channel,))
        after=replace(after,channels=after.channels+(replace(channel,maximum=10.),))
        with self.assertRaises(CharacterRegistryError):
            plan_spline_control_rebuild(before,after,(('',5),))


if __name__=='__main__':unittest.main()
