import unittest
from contextlib import contextmanager

from adv_py.application import ScaleControlCurves
from adv_py.core import (
    ControlCurveShapeState, ControlCurveState, ControlCurveValidationError,
    plan_control_curve_scale,
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


if __name__ == "__main__":
    unittest.main()
