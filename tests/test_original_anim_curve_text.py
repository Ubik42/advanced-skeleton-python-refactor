import unittest
from adv_py.core.original_anim_curve_text import (
    OriginalCurveKey,OriginalCurveText,parse_original_curve_text,original_curve_text)


class OriginalAnimCurveTextTests(unittest.TestCase):
    def test_source_text_round_trip_preserves_fixed_angles_and_order(self):
        curve=OriginalCurveText('animCurveUA',(
            OriginalCurveKey(-10.,-25.,'fixed','spline',12.,22.,.5,.75),
            OriginalCurveKey(0.,0.,'linear','step'),
            OriginalCurveKey(10.,50.,'spline','fixed',0.,35.,0.,.9)),1,4)
        for expression in (False,True):
            self.assertEqual(parse_original_curve_text(original_curve_text(
                curve,expression=expression)),curve)

    def test_source_missing_incoming_data_and_unknown_fields(self):
        curve=parse_original_curve_text('nodeType: animCurveUU, keyCount: 2, '
            'key 0:, time: -1, value: 0.5, outTangentType: fixed, '
            'outTangentAngle: 18, outTangentWeight: 0.4, '
            'ignored: yes, key 1:, value: 1, preInfinity: 1, postInfinity: 1')
        self.assertEqual(curve.keys[0].in_angle,0.)
        self.assertEqual(curve.keys[0].in_weight,0.)
        self.assertEqual(curve.keys[1].time,0.)
        self.assertEqual(curve.keys[0].out_weight,.4)

    def test_invalid_data_does_not_execute_a_statement(self):
        for text in ('nodeType: transform, keyCount: 0',
                     'nodeType: animCurveUU, keyCount: -1',
                     'nodeType: animCurveUU, keyCount: 1, key 0:, value: nan'):
            with self.assertRaises(ValueError):parse_original_curve_text(text)
