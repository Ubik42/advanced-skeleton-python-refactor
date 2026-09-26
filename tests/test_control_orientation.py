import unittest
from contextlib import contextmanager

from adv_py.application import SetControlOrientationAxis
from adv_py.core import (
    ControlAxis, ControlOrientationState, ControlOrientationValidationError,
    CustomOrientationPreview, plan_control_orientation_axis,
    plan_custom_control_orientations,
)


IDENTITY = (1., 0., 0., 0., 0., 1., 0., 0.,
            0., 0., 1., 0., 0., 0., 0., 1.)


class Host:
    def __init__(self):
        self.state = ControlOrientationState("|Control", IDENTITY)
        self.transactions = []
        self.points = (("|Control|Shape", ((1., 2., 3.),)),)

    def capture_control_orientations(self, controls):
        return (self.state,)

    @contextmanager
    def transaction(self, label):
        self.transactions.append(label)
        yield

    def apply_control_orientation(self, state):
        self.state = state

    def capture_control_curve_world_points(self, controls):
        return self.points

    def restore_control_curve_world_points(self, shapes):
        self.points = shapes


class ControlOrientationTests(unittest.TestCase):
    def test_axis_permutation_preserves_semantic_primary_and_secondary(self):
        plan = plan_control_orientation_axis(
            (ControlOrientationState("|Control", IDENTITY),), "Z", "X")
        matrix = plan.changes[0].after.world_matrix
        self.assertEqual(matrix[:12], (
            0., 1., 0., 0.,
            0., 0., 1., 0.,
            1., 0., 0., 0.,
        ))
        self.assertEqual(plan.primary_axis, ControlAxis.Z)
        self.assertEqual(plan.secondary_axis, ControlAxis.X)

    def test_collinear_axis_pair_is_rejected(self):
        with self.assertRaises(ControlOrientationValidationError):
            plan_control_orientation_axis(
                (ControlOrientationState("|Control", IDENTITY),), "X", "-X")

    def test_application_writes_and_verifies_one_transaction(self):
        host = Host()
        result = SetControlOrientationAxis(host).apply(("|Control",), "-Y", "Z")
        self.assertEqual(len(host.transactions), 1)
        self.assertEqual(result.verified[0].primary_axis, ControlAxis.NEG_Y)
        self.assertEqual(result.verified[0].secondary_axis, ControlAxis.Z)

    def test_curve_unaffected_flows_through_plan_and_verification(self):
        host = Host()
        result = SetControlOrientationAxis(host).apply(
            ("|Control",), "Z", "X", True)
        self.assertTrue(result.plan.curve_unaffected)
        self.assertTrue(result.verified[0].curve_unaffected)
        self.assertEqual(host.points[0][1], ((1., 2., 3.),))

    def test_custom_preview_preserves_manual_orientation(self):
        rotated = (0., 1., 0., 0., -1., 0., 0., 0.,
                   0., 0., 1., 0., 0., 0., 0., 1.)
        changes = plan_custom_control_orientations(
            (ControlOrientationState("|Control", IDENTITY),),
            (CustomOrientationPreview("|Control", IDENTITY, rotated),))
        self.assertEqual(changes[0].after.world_matrix, rotated)

    def test_custom_preview_rejects_movement_before_writing(self):
        moved = (*IDENTITY[:12], 1., 0., 0., 1.)
        with self.assertRaises(ControlOrientationValidationError):
            plan_custom_control_orientations(
                (ControlOrientationState("|Control", IDENTITY),),
                (CustomOrientationPreview("|Control", IDENTITY, moved),))

    def test_mirror_axis_option_reorients_each_side_from_its_own_frame(self):
        left = (-1., 0., 0., 0., 0., -1., 0., 0.,
                0., 0., 1., 0., 0., 0., 0., 1.)
        plan = plan_control_orientation_axis((
            ControlOrientationState("|Shoulder_R", IDENTITY),
            ControlOrientationState("|Shoulder_L", left),
        ), "Z", "X", mirror=True)
        self.assertTrue(plan.mirror)
        self.assertTrue(all(change.after.mirror for change in plan.changes))
        self.assertNotEqual(plan.changes[0].after.world_matrix,
                            plan.changes[1].after.world_matrix)


if __name__ == "__main__":
    unittest.main()
