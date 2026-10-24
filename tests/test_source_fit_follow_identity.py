"""Independent Fit branches select authored settings before public name mapping."""
from dataclasses import replace
from types import SimpleNamespace as NS
import unittest

from adv_py.core.fit_metadata import FitJointMetadata
from adv_py.core.fit_symmetry import FitBuildSide as Side
from adv_py.core.body_fit_follow import plan_body_fit_follow
from adv_py.core.body_fit_named_follow import plan_body_fit_named_follow
from adv_py.core.body_fit_follow_spaces import plan_body_fit_follow_spaces
from adv_py.core.body_fit_advanced_constraint import plan_body_fit_advanced_constraints
from adv_py.core.body_fit_aim_at import plan_body_fit_aim_at
from adv_py.core.body_fit_geo_attach import plan_body_fit_geo_attach
from adv_py.core.body_fit_proximity_pin import plan_body_fit_proximity_pin
from adv_py.core.body_fit_ik_follow import plan_body_fit_ik_follow


class FollowIdentityTests(unittest.TestCase):
    def setUp(self):
        self.bodies = tuple(NS(name=name, path='|Body|'+name, parent_path='|Body|Root_M')
            for name in ('Shoulder_R','Shoulder_L','Wrist_R','Wrist_L','Root_M','Chest_M'))
        self.bodies += tuple(NS(name='Child_'+side, path='|Body|Shoulder_'+side+'|Child_'+side,
            parent_path='|Body|Shoulder_'+side) for side in ('R','L'))
        self.controls = tuple(NS(side=side,fit_joint_names=('Shoulder','Shoulder_NonSymmetry'),
            driven_joint='|Body|Shoulder_'+side.value,offset_path='|Controls|Offset_'+side.value,
            control_path='|Controls|Offset_'+side.value+'|FK_'+side.value,source_override_path=None)
            for side in (Side.RIGHT,Side.LEFT))
        self.instances = tuple(NS(output_name=name+'_'+side.value, side=side,
            source_joint='|Fit|'+name+('_NonSymmetry' if side is Side.LEFT else ''))
            for name in ('Shoulder','Wrist') for side in (Side.RIGHT,Side.LEFT))
        self.metadata = (FitJointMetadata('|Fit|Shoulder'),FitJointMetadata('|Fit|Shoulder_NonSymmetry'))

    def rows(self,**settings):
        return tuple(replace(row,**settings) for row in self.metadata)

    def assert_sides(self,specs):
        self.assertEqual(len(specs),2)
        self.assertEqual([s.source_body.rsplit('_',1)[-1] for s in specs],['R','L'])

    def test_seven_fk_features_resolve_both_authored_rows_once(self):
        features = (
            (plan_body_fit_follow,dict(follow='Root'),{}),
            (plan_body_fit_named_follow,dict(follow_by_name=(('Root',3.),)),{}),
            (plan_body_fit_follow_spaces,dict(follow_spaces=True),dict(main_path='|Main',root_path='|Root')),
            (plan_body_fit_advanced_constraints,dict(parent_constraint='Root'),{}),
            (plan_body_fit_geo_attach,dict(geo_attach='surface'),{}),
            (plan_body_fit_proximity_pin,dict(proximity_pin='mesh'),{}),
        )
        for planner,settings,kwargs in features:
            with self.subTest(planner=planner.__name__):
                specs=planner(self.rows(**settings),self.controls,self.bodies,
                    instances=self.instances,**kwargs)
                self.assert_sides(specs)
        targets=tuple(NS(side=side,fit_joint_names=('Chest',),driven_joint='|Body|Chest_M',
            control_path='|ChestFK',offset_path='|ChestOffset',source_override_path=None)
            for side in (Side.MIDDLE,))
        self.assert_sides(plan_body_fit_aim_at(self.rows(aim_at='Chest'),
            self.controls+targets,self.bodies,instances=self.instances))

    def test_left_only_metadata_does_not_leak_to_right(self):
        rows=(self.metadata[0],replace(self.metadata[1],follow='Root',follow_world=True))
        specs=plan_body_fit_follow(rows,self.controls,self.bodies,instances=self.instances)
        self.assertEqual(len(specs),1)
        self.assertEqual(specs[0].source_joint,'|Fit|Shoulder_NonSymmetry')
        self.assertTrue(specs[0].source_body.endswith('_L'))
        self.assertTrue(specs[0].world_target)

    def test_mirrored_left_uses_right_fit_row(self):
        mirrored=tuple(NS(output_name=i.output_name,side=i.side,
            source_joint=i.source_joint.removesuffix('_NonSymmetry')) for i in self.instances)
        specs=plan_body_fit_follow(self.rows(follow='Root')[:1],self.controls,self.bodies,
            instances=mirrored)
        self.assert_sides(specs)
        self.assertEqual({s.source_joint for s in specs},{'|Fit|Shoulder'})

    def test_native_aim_targets_follow_source_pass_and_no_mirror(self):
        instances=tuple(NS(**vars(i),mirrored=False) for i in self.instances)
        targets=tuple(NS(side=side,fit_joint_names=('Wrist','Wrist_NonSymmetry'),
            driven_joint='|Body|Wrist_'+side.value,control_path='|WristFK_'+side.value,
            offset_path='|WristOffset_'+side.value,source_override_path=None)
            for side in (Side.RIGHT,Side.LEFT))
        specs=plan_body_fit_aim_at(self.rows(aim_at='Wrist',no_mirror=True),self.controls+targets,
            self.bodies,instances=instances,source_native=True)
        self.assert_sides(specs)
        # Both authored source branches have noMirror; original chooses the
        # target's authored Fit position, not the source control's _L suffix.
        self.assertEqual([s.target_body for s in specs],['|Body|Wrist_R']*2)
        self.assertEqual([s.mirror_sign for s in specs],[1,-1])
        self.assertTrue(all(s.source_native for s in specs))
        self.assertEqual(specs[0].delta_matrix,'FKAimAtShoulder_R_aimConstraint1')

    def test_native_aim_mirrored_source_does_not_fallback_to_middle_target(self):
        instances=tuple(NS(output_name=i.output_name,side=i.side,
            source_joint=i.source_joint.removesuffix('_NonSymmetry'),
            mirrored=i.side is Side.LEFT) for i in self.instances)
        instances+=(NS(output_name='Chest_M',side=Side.MIDDLE,source_joint='|Fit|Chest',mirrored=False),)
        target=NS(side=Side.MIDDLE,fit_joint_names=('Chest',),driven_joint='|Body|Chest_M',
            control_path='|ChestFK',offset_path='|ChestOffset',source_override_path=None)
        specs=plan_body_fit_aim_at(self.rows(aim_at='Chest')[:1],self.controls+(target,),
            self.bodies,instances=instances,source_native=True)
        self.assertEqual(specs,())  # Original warns/skips missing FKChest_R/L.

    def test_source_sign_distinguishes_authored_left_from_mirrored_left(self):
        from adv_py.core.source_fit_identity import source_fit_side_sign
        cases=(('Shoulder_L','|Fit|Shoulder',False,1),
               ('Shoulder_L','|Fit|Shoulder',True,-1),
               ('Shoulder_R','|Fit|Shoulder_NonSymmetry',False,-1),
               ('Shoulder_M','|Fit|Shoulder',False,1))
        for name,path,mirrored,expected in cases:
            with self.subTest(name=name,path=path,mirrored=mirrored):
                self.assertEqual(source_fit_side_sign(name,
                    (NS(output_name=name,source_joint=path,mirrored=mirrored),)),expected)

    def test_native_aim_uses_inherited_no_mirror(self):
        instances=tuple(NS(**vars(i),mirrored=False) for i in self.instances)
        target=NS(side=Side.MIDDLE,fit_joint_names=('Chest',),driven_joint='|Body|Chest_M',
            control_path='|ChestFK',offset_path='|ChestOffset',source_override_path=None)
        instances+=(NS(output_name='Chest_M',side=Side.MIDDLE,source_joint='|Fit|Chest',mirrored=False),)
        rows=self.rows(aim_at='Chest')+(FitJointMetadata('|Fit',no_mirror=True),)
        specs=plan_body_fit_aim_at(rows,self.controls+(target,),self.bodies,
                                 instances=instances,source_native=True)
        self.assert_sides(specs)
        self.assertEqual({s.target_body for s in specs},{'|Body|Chest_M'})

    def test_ik_end_uses_its_physical_fit_row(self):
        limbs=tuple(NS(chain=('|Body|Shoulder_'+side.value,'|Body|Wrist_'+side.value),side=side,
            wrist_control_path='|IKOffset_'+side.value+'|IK',wrist_offset_path='|IKOffset_'+side.value)
            for side in (Side.RIGHT,Side.LEFT))
        rows=(FitJointMetadata('|Fit|Wrist',ik_follow='Root'),
              FitJointMetadata('|Fit|Wrist_NonSymmetry',ik_follow='Chest'))
        specs=plan_body_fit_ik_follow(rows,limbs,(),self.bodies,instances=self.instances)
        self.assert_sides(specs)
        self.assertEqual([s.primary_target for s in specs],['|Body|Root_M','|Body|Chest_M'])


if __name__ == '__main__':
    unittest.main()
