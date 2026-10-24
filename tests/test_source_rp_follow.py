"""RP source mode, physical Fit ancestry and saved legacy records."""
from dataclasses import asdict
from types import SimpleNamespace as Row
import unittest
from adv_py.core.fit_symmetry import FitBuildSide as Side
from adv_py.core.source_rp_follow import plan_source_rp_follows
from adv_py.core.body_fit_follow_spaces import BodyFitFollowSpacesState
from adv_py.core.character_registry import canonical, CharacterRegistryError
from adv_py.adapters.maya_source_rp_follow import decode


class SourceRpFollowTests(unittest.TestCase):
    def fixture(self, *, leg=False, center=False, independent=False, native=None, opm=True):
        label='Leg' if leg else 'Arm'; end_name='Foot_L' if leg else 'Wrist_L'
        body_root='|Body|Root_M'; chest=body_root+'|Chest_M'
        start_source=chest+'|Shoulder_L'; end_source=start_source+'|'+end_name
        root='|Controls'; frame=root+'|Parent'; start=frame+'|Offset|Start'; end=start+'|End'
        body=Row(root=body_root,joints=(Row(path=body_root,name='Root_M',parent_path='|Body'),
            Row(path=chest,name='Chest_M',parent_path=body_root),
            Row(path=start_source,name='Shoulder_L',parent_path=chest),
            Row(path=end_source,name=end_name,parent_path=start_source)))
        ik=Row(chain=(start,end),side=Side.LEFT,root_path=root,wrist_control_path=root+'|IK',
            wrist_sub_path=None,wrist_offset_path=root+'|IKOffset',pole_control_path=root+'|Pole',
            pole_offset_path=root+'|PoleOffset',pole_position=(1.,2.,3.),handle_name='Handle')
        limb=Row(label=label,ik=Row(limbs=(ik,)),mechanisms=Row(joints=(
            Row(path=start,source_joint=start_source),Row(path=end,source_joint=end_source))))
        global_control=Row(control_path='|Main',extra_control_paths=('|MainExtra1','|MainExtra2'))
        root_plan=Row(root_x=Row(control_path='|RootX'),leg_lock_path='|LegLock',center_between_feet=center)
        fit='|Fit|Shoulder_NonSymmetry|'+end_name.rsplit('_',1)[0]+'_NonSymmetry' if independent else '|Fit|Root|Chest|Shoulder|'+end_name.rsplit('_',1)[0]
        instances=(Row(output_name=end_name,source_joint=fit),)
        return plan_source_rp_follows(body,(limb,),global_control,root_plan,
            use_offset_parent_matrix=opm,native_controls=native,instances=instances)[0]

    def test_native_modes_use_source_output_and_reverse_main_extra_order(self):
        for opm in (False,True):
            plan=self.fixture(opm=opm)
            for spec in plan.spaces:
                self.assertTrue(spec.source_rp)
                self.assertEqual(spec.use_offset_parent_matrix,opm)
                self.assertEqual([t.label for t in spec.targets[:3]],['MainExtra2','MainExtra1','Main'])
                self.assertEqual(spec.output_node in spec.node_names,not opm)

    def test_independent_fit_ancestry_controls_chest_level(self):
        plan=self.fixture(independent=True)
        self.assertTrue(all('Chest' not in [t.label for t in spec.targets] for spec in plan.spaces))
        legacy=self.fixture(independent=True,native=frozenset())
        self.assertTrue(all('Chest' in [t.label for t in spec.targets] for spec in legacy.spaces))

    def test_leg_overrides_last_pole_target_and_uses_actual_ik_parent_frame(self):
        plan=self.fixture(leg=True)
        pole=plan.spaces[-1]
        self.assertEqual(pole.targets[-1].source,plan.control)
        self.assertEqual(pole.targets[-1].weight,10.)
        self.assertEqual(pole.source_rp_pole_target,plan.pole_aim.target_path)
        self.assertEqual(plan.pole_aim.source_frame,'|Controls|Parent')
        self.assertNotIn(plan.pole_aim.frame_name,plan.pole_aim.node_names)

    def test_center_between_feet_only_removes_ik_follow(self):
        plan=self.fixture(leg=True,center=True)
        self.assertEqual(len(plan.spaces),1)
        self.assertEqual(plan.spaces[0].fk_control,plan.pole)

    def text(self,plan):
        identity=tuple(1. if i in (0,5,10,15) else 0. for i in range(16))
        states=tuple(BodyFitFollowSpacesState(identity,identity,tuple(identity for t in s.targets),None,identity) for s in plan.spaces)
        return dict(plan=asdict(plan),states=[asdict(s) for s in states]),states

    def test_native_record_round_trip_both_modes(self):
        for opm in (False,True):
            plan=self.fixture(leg=True,opm=opm);raw,states=self.text(plan)
            self.assertEqual(decode(canonical(raw)),(plan,states))

    def test_legacy_record_without_new_fields_keeps_saved_graph(self):
        plan=self.fixture(leg=True,native=frozenset());raw,states=self.text(plan)
        for row in raw['plan']['spaces']:
            for key in ('source_native','source_rp','source_rp_pole_target','use_offset_parent_matrix'):row.pop(key)
        for key in ('source_frame','use_offset_parent_matrix'):raw['plan']['pole_aim'].pop(key)
        self.assertEqual(decode(canonical(raw)),(plan,states))
        self.assertIsNone(plan.pole_aim.source_frame)
        self.assertEqual(plan.spaces[-1].targets[-1].source,plan.pole_aim.target_path)

    def test_record_rejects_mixed_fk_and_rp_output_modes(self):
        raw,_=self.text(self.fixture());raw['plan']['spaces'][0]['source_native']=True
        with self.assertRaises(CharacterRegistryError):decode(canonical(raw))

if __name__=='__main__': unittest.main()
