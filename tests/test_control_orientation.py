import unittest
from contextlib import contextmanager

from adv_py.application import (SetControlOrientationAxis,
                                SetControlOrientationWorld,
                                SetControlOrientationWorldMatch)
from adv_py.core import (
    ControlAxis, ControlOrientationState, ControlOrientationValidationError,
    CustomOrientationPreview, plan_control_orientation_axis,
    plan_control_orientation_world,
    plan_control_orientation_world_match,
    plan_custom_control_orientations,
)


IDENTITY = (1., 0., 0., 0., 0., 1., 0., 0.,
            0., 0., 1., 0., 0., 0., 0., 1.)


class Host:
    def __init__(self):
        self.state = ControlOrientationState("|Control", IDENTITY)
        self.transactions = []
        self.points = (("|Control|Shape", ((1., 2., 3.),)),)
        self.child_selections = ()

    def capture_control_orientations(self, controls):
        return (self.state,)

    def capture_control_orientation_child_targets(
            self, controls, child_selections=()):
        self.child_selections = child_selections
        return (("|Control", (3., 0., 0.)),)

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

    def test_mirrored_behavior_is_symmetric_and_idempotent(self):
        left = (-1., 0., 0., 0., 0., 1., 0., 0.,
                0., 0., -1., 0., 0., 0., 0., 1.)
        states = (ControlOrientationState("|Shoulder_R", IDENTITY),
                  ControlOrientationState("|Shoulder_L", left))
        first = plan_control_orientation_axis(
            states, "X", "Y", mirror=True, mirrored_behavior=True)
        self.assertEqual(first.changes[1].after.world_matrix[:12], (
            1., 0., 0., 0., 0., -1., 0., 0.,
            0., 0., -1., 0.))
        second = plan_control_orientation_axis(
            tuple(change.after for change in first.changes),
            "X", "Y", mirror=True, mirrored_behavior=True)
        self.assertEqual(tuple(change.after.world_matrix for change in
                               second.changes),
                         tuple(change.after.world_matrix for change in
                               first.changes))

    def test_side_marker_before_fk_suffix_uses_left_mirror_frame(self):
        left = ControlOrientationState("|TorsoScapula_LFK", IDENTITY)
        planned = plan_control_orientation_axis(
            (left,), "X", "Y", mirrored_behavior=True)
        self.assertNotEqual(planned.changes[0].after.world_matrix,
                            left.world_matrix)

    def test_world_orientation_preserves_position_and_axis_lengths(self):
        rotated = (0., 2., 0., 0., -3., 0., 0., 0.,
                   0., 0., 4., 0., 1., 2., 3., 1.)
        before = ControlOrientationState(
            "|Control", rotated, mirrored_behavior=True)
        plan = plan_control_orientation_world((before,), True, True)
        after = plan.changes[0].after
        self.assertEqual(after.world_matrix, (
            2., 0., 0., 0., 0., 3., 0., 0.,
            0., 0., 4., 0., 1., 2., 3., 1.))
        self.assertEqual((after.primary_axis, after.secondary_axis),
                         (ControlAxis.X, ControlAxis.Y))
        self.assertTrue(after.curve_unaffected and after.mirror)
        self.assertFalse(after.mirrored_behavior)

    def test_world_orientation_uses_one_verified_transaction(self):
        host = Host()
        host.state = ControlOrientationState(
            "|Control", (0., 1., 0., 0., -1., 0., 0., 0.,
                          0., 0., 1., 0., 0., 0., 0., 1.))
        result = SetControlOrientationWorld(host).apply(
            ("|Control",), True)
        self.assertEqual(result.verified[0].world_matrix, IDENTITY)
        self.assertEqual(len(host.transactions), 1)

    def test_world_match_aims_at_child_with_world_up(self):
        state = ControlOrientationState("|Control", IDENTITY)
        plan = plan_control_orientation_world_match(
            (state,), (("|Control", (0., 0., 3.)),),
            "X", "Y", "Y", True)
        matrix = plan.changes[0].after.world_matrix
        self.assertEqual(matrix[:12], (
            0., 0., 1., 0., 0., 1., 0., 0.,
            -1., 0., 0., 0.))
        self.assertFalse(plan.mirrored_behavior)

    def test_world_match_rejects_parallel_up_and_aim(self):
        with self.assertRaises(ControlOrientationValidationError):
            plan_control_orientation_world_match(
                (ControlOrientationState("|Control", IDENTITY),),
                (("|Control", (0., 3., 0.)),), "X", "Y", "Y")

    def test_world_match_rejects_coincident_or_nonfinite_child(self):
        state = ControlOrientationState("|Control", IDENTITY)
        for child in ((0., 0., 0.), (float("nan"), 0., 1.)):
            with self.subTest(child=child):
                with self.assertRaises(ControlOrientationValidationError):
                    plan_control_orientation_world_match(
                        (state,), (("|Control", child),), "X", "Y", "Y")

    def test_world_match_signed_axes_preserve_position_and_scale(self):
        matrix = (2., 0., 0., 0., 0., 3., 0., 0.,
                  0., 0., 4., 0., 1., 2., 3., 1.)
        plan = plan_control_orientation_world_match(
            (ControlOrientationState("|Control", matrix),),
            (("|Control", (1., 2., 8.)),), "-Z", "X", "Y")
        result = plan.changes[0].after.world_matrix
        self.assertEqual(result[12:16], matrix[12:16])
        self.assertEqual(result[:12], (
            0., 2., 0., 0.,
            3., 0., 0., 0.,
            0., 0., -4., 0.))

    def test_world_match_uses_one_verified_transaction(self):
        host = Host()
        result = SetControlOrientationWorldMatch(host).apply(
            ("|Control",), "X", "Y", "Y", True, False,
            (("|Control", "Child"),))
        self.assertEqual(result.verified[0].world_matrix, IDENTITY)
        self.assertEqual(len(host.transactions), 1)
        self.assertEqual(host.child_selections, (("|Control", "Child"),))


if __name__ == "__main__":
    unittest.main()
