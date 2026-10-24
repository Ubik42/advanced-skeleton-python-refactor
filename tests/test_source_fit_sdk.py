"""Fit SDK data and recording boundary checks; no Maya process starts."""
import unittest

from adv_py.adapters.maya_source_fit_sdk import MayaSourceFitSDKMixin
from adv_py.core.source_fit_sdk import (
    SourceFitSDKDriven, SourceFitSDKOptions, SourceFitSDKPlan,
    source_fit_sdk_driven, source_fit_sdk_prompt,
)
from adv_py.core.character_identity import CharacterIdentity


class SDKCommands:
    def __init__(self):
        self.calls = []

    def attributeQuery(self, *args, **kwargs):
        return True

    def __getattr__(self, method):
        def record(*args, **kwargs):
            self.calls.append((method, args, kwargs))
        return record


class SourceFitSDKTests(unittest.TestCase):
    def test_trs_sample_order_preserves_duplicate_default_pose_commands(self):
        rows = source_fit_sdk_driven(
            'setAttr ThumbFinger1.ry 0;setAttr ThumbFinger1.tx 1;setAttr ThumbFinger1.ry 2;',
            (('ThumbFinger1','tx',1.), ('ThumbFinger1','ry',10.)))
        self.assertEqual(rows, (
            SourceFitSDKDriven('ThumbFinger1','ry',0.,10.),
            SourceFitSDKDriven('ThumbFinger1','ry',2.,10.)))

    def test_strict_threshold_and_unrecorded_channels_are_not_driven(self):
        rows = source_fit_sdk_driven('setAttr A.tx 0;setAttr A.ty 0;',
            (('A','tx',.001), ('A','ty',-.00100001), ('A','tz',99.)))
        self.assertEqual(rows, (SourceFitSDKDriven('A','ty',0.,-.00100001),))

    def test_pose_is_never_evaluated_and_leading_whitespace_is_not_repaired(self):
        self.assertEqual(source_fit_sdk_driven(
            'python dangerous; setAttr A.tx 0;setAttr -type double A.ty 0;',
            (('A','tx',9.), ('A','ty',9.))), ())

    def test_namespaced_numeric_pose_plugs_map_at_explicit_address_boundary(self):
        identity = CharacterIdentity('hero')
        self.assertEqual(source_fit_sdk_driven('setAttr hero:ThumbFinger1.rx 0;',
            (('ThumbFinger1','rx',5.),), map_address=identity.to_local),
            (SourceFitSDKDriven('ThumbFinger1','rx',0.,5.),))

    def test_suggestion_removes_only_first_digit_finger_and_toe_occurrence(self):
        for joint, expected in (('ThumbFinger12','thumb2Curl'),
                ('BigToe2','bigCurl'), ('Elbow','')):
            plan = SourceFitSDKPlan('SDK', ('SDK',),
                (SourceFitSDKDriven(joint,'ry',0.,9.),))
            self.assertEqual(plan.suggested_attribute, expected)

    def test_options_keep_zero_driver_and_optional_soft_limits(self):
        options = SourceFitSDKOptions('driver',0.,None,None)
        self.assertEqual(options.driver_value,0.)
        for name in ('','two words'):
            with self.assertRaises(ValueError):
                SourceFitSDKOptions(name)

    def test_prompt_truncation_ignores_empty_lines_like_mel_tokenize(self):
        original = '\n'.join('line'+str(i) for i in range(36))+'\n\n'
        result = source_fit_sdk_prompt(original)
        self.assertTrue(result.endswith('...And 1 more..'))
        self.assertNotIn('line35\n',result)

    def test_existing_attribute_replaced_then_linear_keys_and_native_infinity(self):
        c = SDKCommands()
        host = MayaSourceFitSDKMixin()
        host._cmds = c
        host._require_transaction = lambda: None
        plan = SourceFitSDKPlan('SDK', ('SDK','Other'), (
            SourceFitSDKDriven('ThumbFinger1','ry',2.,9.),))
        self.assertEqual(host.create_source_fit_sdk_attribute(plan,
            SourceFitSDKOptions('thumbCurl',-10.,None,10.)),1)
        self.assertEqual(c.calls[0],('deleteAttr',('SDK.thumbCurl',),{}))
        keys = [row for row in c.calls if row[0] == 'setDrivenKeyframe']
        self.assertEqual([(row[2]['driverValue'],row[2]['value']) for row in keys],
                         [(0.,2.),(-10.,9.)])
        self.assertTrue(all(row[2]['inTangentType']=='linear' and
                            row[2]['outTangentType']=='linear' for row in keys))
        self.assertEqual(c.calls[-2],('setInfinity',(),
            {'preInfinite':'cycleRelative','postInfinite':'cycleRelative'}))
        self.assertEqual(c.calls[-1],('select',(('SDK','Other'),),{'replace':True}))


if __name__ == '__main__':
    unittest.main()
