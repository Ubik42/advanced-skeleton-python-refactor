import unittest

from adv_py.application import BuildBodyCharacterRig, BuildOrientedBodySkeleton
from adv_py.core.body_control_spaces import control_space_pose_error
from adv_py.core.fit_settings import FitSkeletonValidationError
from test_body_skeleton import FakeBodySkeletonHost


class SpaceHost(FakeBodySkeletonHost):
    def preflight_body_torso(self, plan):
        pass


class BodyControlSpacesTests(unittest.TestCase):
    def test_explicit_groups_and_paired_poles(self):
        host = SpaceHost(with_hand=True)
        BuildOrientedBodySkeleton(host).apply()
        plan = BuildBodyCharacterRig(host).plan(include_torso=True, include_control_spaces=True).control_spaces
        self.assertEqual(tuple(s.key for s in plan.spaces), ("head", "hand_R", "hand_L", "foot_R", "foot_L"))
        self.assertEqual(len(plan.node_names), 9)
        self.assertTrue(plan.space("head").rotation_only)
        self.assertEqual(plan.space("head").initial_mode, "body")
        self.assertTrue(plan.space("head").body_source.endswith(
            "|AdvPy_TorsoNeck_MFK"))
        self.assertTrue(all(len(s.targets) == 2 for s in plan.spaces[1:]))
        with self.assertRaises(FitSkeletonValidationError):
            plan.space("unknown")
        with self.assertRaises(FitSkeletonValidationError):
            plan.space("head").source("world")

    def test_space_feature_requires_torso(self):
        with self.assertRaises(FitSkeletonValidationError):
            BuildBodyCharacterRig(SpaceHost()).plan(include_control_spaces=True)

    def test_pose_audit_rejects_invalid_data(self):
        pose = (("a", (1.0,) * 16),)
        self.assertEqual(control_space_pose_error(pose, pose), 0)
        for after in ((), (("a", (float("nan"),) * 16),), (("b", (1.0,) * 16),)):
            with self.assertRaises(FitSkeletonValidationError):
                control_space_pose_error(pose, after)
