"""Native template identities survive the registered Body animation route."""
from dataclasses import replace
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from adv_py.core.character_registry import CharacterChannel
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.name_matcher_fit import NameMatcherRow, NameMatcherRules
from adv_py.core.name_matcher_animation import plan_name_matcher_animation_bake
from adv_py.core.source_name_matcher import plan_source_name_matcher_constraints
from adv_py.adapters.maya_name_matcher import MayaNameMatcherHost


def saved(channels=(), limbs=(), spine=None, additional=()):
    return SimpleNamespace(channels=channels, source_limbs=limbs,
                           spine=spine, additional_spines=additional)


class NativeAnimationTests(unittest.TestCase):
    def test_native_finger_four_and_duplicate_rows_are_literal_last_row_wins(self):
        mapping = plan_source_name_matcher_constraints(
            ('|rig|Root_M', '|rig|IndexFinger4_R', '|rig|IndexFinger4_L'),
            (('|src|pelvis', 'pelvis'), ('|src|r_tip', 'r_tip'), ('|src|l_tip', 'l_tip')),
            (NameMatcherRow('Root', 'ignored'), NameMatcherRow('Root', 'pelvis'),
             NameMatcherRow('IndexFinger4', 'tip')), NameMatcherRules('r','l','',True,True))
        self.assertEqual(tuple(pair.external_joint for pair in mapping.pairs),
                         ('|src|pelvis','|src|r_tip','|src|l_tip'))
        self.assertFalse(mapping.missing)

    def test_generic_rp_and_spline_fk_are_resolved_from_actual_records(self):
        body = ('|rig|Root_M', '|rig|Wrist_R', '|rig|TailEnd_M')
        external = ('|src|root', '|src|hand', '|src|tail')
        mapping = plan_source_name_matcher_constraints(body,
            tuple((path,path.rsplit('|',1)[-1]) for path in external),
            tuple(NameMatcherRow(joint.rsplit('|',1)[-1][:-2], path.rsplit('|',1)[-1])
                  for joint,path in zip(body,external)), NameMatcherRules('','',''))
        channels = (
            CharacterChannel('generic.fk.Root_MFK.rotateX','|controls|root','rotateX'),
            CharacterChannel('generic.fk.Root_MFK.extra.rotateX','|controls|rootExtra','rotateX'),
            CharacterChannel('source.rp.wrist.mode','|controls|armMode','FKIKBlend'),
            CharacterChannel('source.spline.tail.mode','|controls|tailMode','FKIKBlend'))
        limb = SimpleNamespace(blend_key=channels[2].key,joints=(SimpleNamespace(
            body=body[1],control='|controls|handFK',fk_driver='|mechanism|hand'),))
        spline = SimpleNamespace(body_joints=(body[2],),fk_controls=('|controls|tailFK',),
                                 mode_plug='|controls|tailMode.FKIKBlend')
        result = plan_name_matcher_animation_bake(mapping,saved(channels,(limb,),spline),
            tuple('|NameMatcherKeepAnimation:'+path.rsplit('|',1)[-1] for path in external))
        self.assertEqual(tuple(link.control for link in result.links),
                         ('|controls|root','|controls|handFK','|controls|tailFK'))
        self.assertEqual(result.fk_mode_plugs,
                         ('|controls|armMode.FKIKBlend','|controls|tailMode.FKIKBlend'))

    def test_conflicting_fk_records_are_rejected_instead_of_last_one_winning(self):
        mapping = plan_source_name_matcher_constraints(('|rig|Root_M',),
            (('|src|root','root'),),(NameMatcherRow('Root','root'),),NameMatcherRules())
        channels = (CharacterChannel('generic.fk.Root_MFK.rotateX','|ctrl|first','rotateX'),)
        spline = SimpleNamespace(body_joints=('|rig|Root_M',),fk_controls=('|ctrl|second',),
                                 mode_plug='|ctrl|mode.FKIKBlend')
        with self.assertRaisesRegex(FitSkeletonValidationError,'不唯一'):
            plan_name_matcher_animation_bake(mapping,saved(channels,spine=spline),
                                            ('|NameMatcherKeepAnimation:root',))

    def test_constraints_are_not_animation_and_custom_animated_attributes_are_kept(self):
        incoming = {'|src.translateX':'pointConstraint1.outputTranslateX',
                    '|src.rotateX':'turn.output','|src.custom':'customCurve.output'}
        commands = SimpleNamespace(
            ls=lambda *args,**kwargs:['|src'],
            listRelatives=lambda *args,**kwargs:[],
            listAttr=lambda *args,**kwargs:['custom'],
            connectionInfo=lambda plug,**kwargs:incoming.get(plug,''),
            nodeType=lambda node:{'|src':'joint','pointConstraint1':'pointConstraint',
                                  'turn':'animCurveTA','customCurve':'animCurveTU'}[node])
        host = MayaNameMatcherHost.__new__(MayaNameMatcherHost)
        host.capture_source_skeleton = lambda root:(SimpleNamespace(path='|src'),)
        with patch.dict(sys.modules,{'maya':SimpleNamespace(cmds=commands)}):
            result = host.capture_name_matcher_source_animation('|src')
        self.assertEqual(result,(('|src.custom','customCurve.output'),('|src.rotateX','turn.output')))


if __name__=='__main__':unittest.main()
