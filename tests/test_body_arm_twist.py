import unittest
from math import cos, isclose, pi, sin

from adv_py.core import (
    BodyArmTwistValidationError,
    project_twist_quaternion_x,
    twist_angle_x,
)


def quaternion_product(left, right):
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


class BodyArmTwistTests(unittest.TestCase):
    def test_projects_mixed_swing_and_twist_onto_local_x(self):
        twist = (sin(pi / 4.0), 0.0, 0.0, cos(pi / 4.0))
        swing = (0.0, sin(pi / 6.0), 0.0, cos(pi / 6.0))
        mixed = quaternion_product(swing, twist)

        projected = project_twist_quaternion_x(mixed)

        self.assertTrue(all(isclose(a, b, abs_tol=1e-8) for a, b in zip(projected, twist)))
        self.assertTrue(isclose(twist_angle_x(mixed), pi / 2.0, abs_tol=1e-8))

    def test_pure_or_degenerate_swing_has_no_axial_twist(self):
        pure_swing = (0.0, sin(pi / 6.0), 0.0, cos(pi / 6.0))
        half_turn_swing = (0.0, 1.0, 0.0, 0.0)

        self.assertEqual(project_twist_quaternion_x(pure_swing), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(project_twist_quaternion_x(half_turn_swing), (0.0, 0.0, 0.0, 1.0))

    def test_rejects_non_finite_quaternion(self):
        with self.assertRaisesRegex(BodyArmTwistValidationError, "四元数"):
            project_twist_quaternion_x((float("nan"), 0.0, 0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
