import unittest
from dataclasses import replace
from math import sqrt
from math import cos, sin, radians

from adv_py.application import BuildBodyCharacterRig, BuildOrientedBodySkeleton
from adv_py.core.body_torso import plan_body_torso
from adv_py.core.body_spine import spine_roll_degrees, spine_pose_error, spine_ik_goal_position
from adv_py.core.fit_settings import FitSkeletonValidationError
from test_body_skeleton import FakeBodySkeletonHost


class BodySpineTests(unittest.TestCase):
    def test_spine_plan_separates_pelvis_and_output_chest_space(self):
        host = FakeBodySkeletonHost(with_hand=True)
        body = BuildOrientedBodySkeleton(host).apply().snapshot
        character = BuildBodyCharacterRig(host).plan()
        # The memory fixture omits real Maya joint orientation; supply its spine aim.
        waist = next(j for j in body.joints if j.name == "Spine1_M")
        chest = next(j for j in body.joints if j.name == "Chest_M")
        delta = tuple(b-a for a, b in zip(waist.world_position, chest.world_position))
        length = sqrt(sum(v*v for v in delta))
        x = tuple(v / length for v in delta)
        y = (1.0, 0.0, 0.0)
        z = (0.0, x[2], -x[1])
        body = replace(body, joints=tuple(replace(j, world_axes=(x, y, z)) if j.name == "Spine1_M" else j for j in body.joints))
        torso = plan_body_torso(body, character.arm, character.leg, spine_ik=True)
        spine = torso.spine
        self.assertEqual(len(torso.controls.controls), 8)
        self.assertEqual(len(spine.joints), 6)
        self.assertEqual(len(torso.node_names), len(set(torso.node_names)))
        self.assertEqual(torso.controls.controls[0].driven_joint, body.root)
        self.assertEqual(torso.controls.controls[2].driven_joint, spine.joints[1].path)
        self.assertEqual(torso.controls.controls[4].parent_path, spine.chest_space)
        self.assertEqual(spine.body_joints[0], body.root)
        self.assertTrue(all(length > 0 for length in spine.lengths))

    def test_roll_restores_rotation_around_shared_aim(self):
        angle = radians(37)
        solved = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
        wanted = ((1, 0, 0), (0, cos(angle), sin(angle)), (0, -sin(angle), cos(angle)))
        self.assertAlmostEqual(spine_roll_degrees(wanted, solved), 37)
        with self.assertRaises(FitSkeletonValidationError):
            spine_roll_degrees(((0, 1, 0), *wanted[1:]), solved)

    def test_spine_requires_torso(self):
        with self.assertRaises(FitSkeletonValidationError):
            BuildBodyCharacterRig(FakeBodySkeletonHost()).plan(include_spine_ik=True)

    def test_exact_extension_has_small_outward_solver_bias(self):
        goal = spine_ik_goal_position((0, 0, 0), (0, 0, 3), (0, 0, 6))
        self.assertAlmostEqual(goal[2], 6.00006)
        bent = (0, 2, 5)
        self.assertEqual(spine_ik_goal_position((0, 0, 0), (0, 0, 3), bent), bent)

    def test_pose_verification_rejects_missing_duplicate_and_nonfinite_matrices(self):
        pose = (("|Root", (1.0,) * 16),)
        self.assertEqual(spine_pose_error(pose, pose), 0.0)
        for invalid in ((), (("|Other", (1.0,) * 16),), (("|Root", (float("nan"),) * 16),), pose + pose):
            with self.assertRaises(FitSkeletonValidationError):
                spine_pose_error(pose, invalid)


if __name__ == "__main__":
    unittest.main()
