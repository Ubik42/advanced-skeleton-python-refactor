import unittest
from contextlib import contextmanager

from adv_py.application import ColorControlCurves, ScaleControlCurves
from adv_py.core import (
    ControlCurveColorMode, ControlCurveColorState, ControlCurveShapeColorState,
    ControlCurveShapeState, ControlCurveState, ControlCurveValidationError,
    SIDE_PALETTE, TYPE_PALETTE, control_curve_side, control_curve_type,
    plan_control_curve_colors, plan_control_curve_scale,
)


IDENTITY = (1., 0., 0., 0., 0., 1., 0., 0.,
            0., 0., 1., 0., 0., 0., 0., 1.)


def state(control="|Control", points=((1., 0., 0.), (0., 2., 0.))):
    return ControlCurveState(control, IDENTITY, (
        ControlCurveShapeState(control + "|ControlShape", 1, 0, points),))


class Host:
    def __init__(self):
        self.states = {"|Control": state()}
        self.transactions = []

    def capture_control_curves(self, controls, *, strict):
        found = tuple(self.states[name] for name in controls if name in self.states)
        if strict and len(found) != len(controls):
            raise ControlCurveValidationError("missing")
        return found

    @contextmanager
    def transaction(self, label):
        self.transactions.append(label)
        yield

    def set_control_curve_points(self, shape, points):
        current = self.states["|Control"]
        self.states["|Control"] = ControlCurveState(
            current.control, current.world_matrix,
            (ControlCurveShapeState(shape, 1, 0, points),))


class ColorHost:
    def __init__(self):
        self.states = {
            "|Arm_FK_R": ControlCurveColorState("|Arm_FK_R", (), (
                ControlCurveShapeColorState(
                    "|Arm_FK_R|Shape", False, False, (0., 0., 0.)),)),
        }
        self.transactions = []

    def capture_control_curve_colors(self, controls, semantic_keys, *, strict):
        semantics = dict(semantic_keys)
        found = []
        for name in controls:
            if name in self.states:
                current = self.states[name]
                found.append(ControlCurveColorState(
                    current.control, semantics.get(name, current.semantic_keys),
                    current.shapes))
        if strict and len(found) != len(controls):
            raise ControlCurveValidationError("missing")
        return tuple(found)

    @contextmanager
    def transaction(self, label):
        self.transactions.append(label)
        yield

    def set_control_curve_color(self, shape, color):
        current = self.states["|Arm_FK_R"]
        self.states[current.control] = ControlCurveColorState(
            current.control, current.semantic_keys,
            (ControlCurveShapeColorState(shape, True, True, color),))


class ControlCurveScaleTests(unittest.TestCase):
    def test_plan_scales_local_cvs_and_preserves_transform(self):
        plan = plan_control_curve_scale((state(),), 1.5)
        self.assertEqual(plan.after[0].world_matrix, IDENTITY)
        self.assertEqual(plan.after[0].shapes[0].points,
                         ((1.5, 0., 0.), (0., 3., 0.)))
        with self.assertRaises(ControlCurveValidationError):
            plan_control_curve_scale((state(),), 0.)

    def test_application_writes_and_verifies_one_transaction(self):
        host = Host()
        result = ScaleControlCurves(host).apply(("|Control",), 2.)
        self.assertEqual(len(host.transactions), 1)
        self.assertEqual(result.verified[0].shapes[0].points,
                         ((2., 0., 0.), (0., 4., 0.)))


class ControlCurveColorTests(unittest.TestCase):
    def test_side_and_type_classification_use_semantics_and_paths(self):
        right_fk = ControlCurveColorState("|Rig|Arm_FK_R", ("arm.fk.Wrist_R",), (
            ControlCurveShapeColorState("|Rig|Arm_FK_R|Shape", False, False,
                                        (0., 0., 0.)),))
        left_pole = ControlCurveColorState("|Rig|Pole_L", ("arm.pole.L",), (
            ControlCurveShapeColorState("|Rig|Pole_L|Shape", False, False,
                                        (0., 0., 0.)),))
        self.assertEqual(control_curve_side(right_fk), "right")
        self.assertEqual(control_curve_type(right_fk), "fk")
        self.assertEqual(control_curve_side(left_pole), "left")
        self.assertEqual(control_curve_type(left_pole), "pole")

    def test_plan_applies_stable_side_and_type_palettes(self):
        current = ColorHost().states["|Arm_FK_R"]
        side = plan_control_curve_colors((current,), ControlCurveColorMode.SIDE)
        self.assertEqual(side.after[0].shapes[0].color, SIDE_PALETTE["right"])
        typed = plan_control_curve_colors((ControlCurveColorState(
            current.control, ("arm.fk.Wrist_R",), current.shapes),), "type")
        self.assertEqual(typed.after[0].shapes[0].color, TYPE_PALETTE["fk"])

    def test_application_writes_rgb_override_and_verifies(self):
        host = ColorHost()
        result = ColorControlCurves(host).apply(
            ("|Arm_FK_R",), "type",
            (("|Arm_FK_R", ("arm.fk.Wrist_R",)),))
        self.assertEqual(len(host.transactions), 1)
        shape = result.verified[0].shapes[0]
        self.assertTrue(shape.override_enabled and shape.rgb_enabled)
        self.assertEqual(shape.color, TYPE_PALETTE["fk"])


if __name__ == "__main__":
    unittest.main()
