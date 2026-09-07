import unittest
from dataclasses import replace

from adv_py.application import PlanFitSymmetry
from adv_py.core import (
    FitBuildSide,
    FitJointOrientationState,
    FitJointMetadata,
    FitOrientationSnapshot,
    FitSymmetryValidationError,
    FitUpAxis,
    IDENTITY_AXES,
    default_fit_skeleton_settings,
    expand_fit_symmetry,
    mirror_behavior_axes_yz,
    predict_fit_template_hierarchy,
    synthetic_body_source_fit_template,
)


def source_snapshot():
    hierarchy = predict_fit_template_hierarchy(
        synthetic_body_source_fit_template(FitUpAxis.Z),
        "|FitSkeleton",
    )
    metadata = tuple(FitJointMetadata(node.path) for node in hierarchy.joints)
    return hierarchy, metadata


class FakeSymmetryHost:
    def __init__(self):
        hierarchy, metadata = source_snapshot()
        self.snapshot = FitOrientationSnapshot(
            hierarchy,
            FitUpAxis.Z,
            tuple(
                FitJointOrientationState(
                    node.path,
                    (0.0, 0.0, 0.0),
                    (0.0, 0.0, 0.0),
                    IDENTITY_AXES,
                )
                for node in hierarchy.joints
            ),
            metadata,
        )
        self.settings = default_fit_skeleton_settings(hierarchy.container)
        self.read_count = 0

    def capture_fit_orientation(self, container_name):
        del container_name
        self.read_count += 1
        return self.snapshot

    def read_fit_skeleton_settings(self, container_name):
        del container_name
        return self.settings


class FitSymmetryTests(unittest.TestCase):
    def test_reflects_aim_and_secondary_then_rebuilds_right_handed_z(self):
        source = (
            (0.8, 0.6, 0.0),
            (-0.6, 0.8, 0.0),
            (0.0, 0.0, 1.0),
        )

        mirrored = mirror_behavior_axes_yz(source)

        self.assertEqual(mirrored[0], (-0.8, 0.6, 0.0))
        self.assertEqual(mirrored[1], (0.6, 0.8, 0.0))
        self.assertAlmostEqual(mirrored[2][2], -1.0)
        cross = (
            mirrored[0][1] * mirrored[1][2] - mirrored[0][2] * mirrored[1][1],
            mirrored[0][2] * mirrored[1][0] - mirrored[0][0] * mirrored[1][2],
            mirrored[0][0] * mirrored[1][1] - mirrored[0][1] * mirrored[1][0],
        )
        self.assertEqual(cross, mirrored[2])

    def test_expands_center_and_right_sources_into_m_r_l_topology(self):
        hierarchy, metadata = source_snapshot()

        instances = expand_fit_symmetry(hierarchy, metadata)
        by_name = {instance.output_name: instance for instance in instances}

        self.assertEqual(len(instances), 30)
        self.assertEqual(by_name["Root_M"].side, FitBuildSide.MIDDLE)
        self.assertEqual(by_name["Hip_R"].world_position[0], -1.5)
        self.assertEqual(by_name["Hip_L"].world_position[0], 1.5)
        self.assertEqual(by_name["Knee_L"].parent_output_path, "|Root_M|Hip_L")
        self.assertTrue(by_name["Wrist_L"].mirrored)

    def test_inherited_no_mirror_can_emit_right_only_or_left_only(self):
        hierarchy, metadata = source_snapshot()
        hip_path = next(
            node.path for node in hierarchy.joints if node.short_name == "Hip"
        )

        right_only = tuple(
            replace(item, no_mirror=True) if item.joint == hip_path else item
            for item in metadata
        )
        right_instances = expand_fit_symmetry(hierarchy, right_only)
        right_names = {item.output_name for item in right_instances}
        self.assertIn("Hip_R", right_names)
        self.assertNotIn("Hip_L", right_names)
        self.assertNotIn("ToesEnd_L", right_names)

        left_only = tuple(
            replace(item, no_mirror=True, no_mirror_left=True)
            if item.joint == hip_path
            else item
            for item in metadata
        )
        left_instances = expand_fit_symmetry(hierarchy, left_only)
        left_names = {item.output_name for item in left_instances}
        self.assertNotIn("Hip_R", left_names)
        self.assertIn("Hip_L", left_names)
        self.assertIn("ToesEnd_L", left_names)

    def test_rejects_an_unmarked_left_source_branch(self):
        hierarchy, metadata = source_snapshot()
        changed = tuple(
            replace(
                node,
                world_position=(
                    -node.world_position[0],
                    node.world_position[1],
                    node.world_position[2],
                ),
            )
            if "|Hip" in node.path
            else node
            for node in hierarchy.joints
        )

        with self.assertRaisesRegex(FitSymmetryValidationError, "必须从 Right"):
            expand_fit_symmetry(replace(hierarchy, joints=changed), metadata)

    def test_application_reads_once_and_keeps_scene_snapshot_unchanged(self):
        host = FakeSymmetryHost()
        before = host.snapshot

        plan = PlanFitSymmetry(host).execute()

        self.assertEqual(len(plan.instances), 30)
        self.assertEqual(host.read_count, 1)
        self.assertIs(host.snapshot, before)


if __name__ == "__main__":
    unittest.main()
