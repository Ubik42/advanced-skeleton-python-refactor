import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import BuildBodySkeleton
from adv_py.core import (
    IDENTITY_AXES,
    BodyJointState,
    BodySkeletonSnapshot,
    FitJointMetadata,
    FitJointOrientationState,
    FitOrientationSnapshot,
    FitSkeletonValidationError,
    FitUpAxis,
    default_fit_skeleton_settings,
    predict_fit_template_hierarchy,
    synthetic_body_source_fit_template,
)


class FakeBodySkeletonHost:
    def __init__(self, *, faulty_capture=False):
        template = synthetic_body_source_fit_template(FitUpAxis.Z)
        hierarchy = predict_fit_template_hierarchy(template, "|FitSkeleton")
        self.fit_snapshot = FitOrientationSnapshot(
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
            tuple(FitJointMetadata(node.path) for node in hierarchy.joints),
        )
        self.settings = default_fit_skeleton_settings(hierarchy.container)
        labels_by_name = {spec.name: spec.label for spec in template.joints}
        self.labels = {
            node.path: labels_by_name[node.short_name] for node in hierarchy.joints
        }
        self.collisions = {}
        self.body = []
        self.transaction_count = 0
        self.faulty_capture = faulty_capture

    def capture_fit_orientation(self, container_name):
        del container_name
        return self.fit_snapshot

    def read_fit_skeleton_settings(self, container_name):
        del container_name
        return self.settings

    def read_joint_label(self, joint):
        return self.labels.get(joint)

    def find_name_collisions(self, name):
        return tuple(self.collisions.get(name, ()))

    @contextmanager
    def transaction(self, label):
        del label
        before = list(self.body)
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.body = before
            raise

    def create_body_joint(self, spec):
        self.body.append(
            BodyJointState(
                spec.path,
                spec.name,
                spec.parent_path,
                spec.side,
                spec.world_position,
                spec.label,
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0),
            )
        )
        return spec.path

    def capture_body_skeleton(self, root_name):
        root = f"|{root_name}"
        joints = tuple(self.body)
        if self.faulty_capture and joints:
            joints = (
                replace(joints[0], world_position=(99.0, 0.0, 0.0)),
            ) + joints[1:]
        return BodySkeletonSnapshot(root, joints)


class BodySkeletonTests(unittest.TestCase):
    def test_previews_and_builds_thirty_joints_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        use_case = BuildBodySkeleton(host)

        preview = use_case.plan()

        self.assertTrue(preview.ready)
        self.assertEqual(len(preview.specs), 30)
        self.assertFalse(host.body)
        result = use_case.apply()
        self.assertEqual(len(result.snapshot.joints), 30)
        self.assertEqual(host.transaction_count, 1)
        self.assertIs(host.fit_snapshot, result.plan.symmetry.source)

    def test_name_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        host.collisions["Hip_L"] = ("|Existing|Hip_L",)

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 0)
        self.assertFalse(host.body)

    def test_post_verification_failure_rolls_back_all_body_joints(self):
        host = FakeBodySkeletonHost(faulty_capture=True)

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertFalse(host.body)


if __name__ == "__main__":
    unittest.main()
