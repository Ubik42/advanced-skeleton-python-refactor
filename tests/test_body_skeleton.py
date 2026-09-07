import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import (
    BuildBodySkeleton,
    BuildOrientedBodySkeleton,
    InspectBodySkeletonProvenance,
    OrientBodySkeleton,
)
from adv_py.core import (
    IDENTITY_AXES,
    BodyJointState,
    BodySkeletonSnapshot,
    BodySkeletonProvenanceState,
    BodySkeletonValidationError,
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
    def __init__(
        self,
        *,
        faulty_capture=False,
        faulty_after_orientation=False,
        faulty_provenance=False,
    ):
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
        angled_axes = (
            (0.8, 0.6, 0.0),
            (-0.6, 0.8, 0.0),
            (0.0, 0.0, 1.0),
        )
        self.fit_snapshot = replace(
            self.fit_snapshot,
            joints=tuple(
                replace(state, world_axes=angled_axes)
                if state.joint.endswith("|Scapula")
                else state
                for state in self.fit_snapshot.joints
            ),
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
        self.faulty_after_orientation = faulty_after_orientation
        self.orientation_write_count = 0
        self.faulty_provenance = faulty_provenance
        self.provenance = None
        self.in_transaction = False

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
        before_provenance = self.provenance
        self.transaction_count += 1
        self.in_transaction = True
        try:
            yield
        except Exception:
            self.body = before
            self.provenance = before_provenance
            raise
        finally:
            self.in_transaction = False

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
        should_corrupt = self.faulty_capture or (
            self.faulty_after_orientation and self.orientation_write_count > 0
        )
        if should_corrupt and self.in_transaction and joints:
            joints = (
                replace(joints[0], world_position=(99.0, 0.0, 0.0)),
            ) + joints[1:]
        return BodySkeletonSnapshot(root, joints, self.provenance)

    def set_body_joint_world_axes(self, change):
        self.orientation_write_count += 1
        self.body = [
            replace(state, world_axes=change.desired_world_axes)
            if state.path == change.joint
            else state
            for state in self.body
        ]

    def set_body_joint_world_position(self, joint, position):
        self.body = [
            replace(state, world_position=position)
            if state.path == joint
            else state
            for state in self.body
        ]

    def write_body_provenance(self, root, provenance):
        del root
        count = provenance.body_joint_count
        if self.faulty_provenance:
            count += 1
        self.provenance = BodySkeletonProvenanceState(
            provenance.owner,
            provenance.artifact_kind,
            provenance.schema_version,
            provenance.source_container,
            count,
        )


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

    def test_orients_right_and_left_behavior_frames_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        BuildBodySkeleton(host).apply()
        use_case = OrientBodySkeleton(host)

        preview = use_case.plan()

        self.assertEqual(len(preview.changes), 13)
        before_positions = {
            state.path: state.world_position for state in preview.before.joints
        }
        result = use_case.apply()
        self.assertEqual(host.transaction_count, 2)
        self.assertEqual(
            {state.path: state.world_position for state in result.verified.joints},
            before_positions,
        )
        right = next(
            state for state in result.verified.joints if state.name == "Scapula_R"
        )
        left = next(
            state for state in result.verified.joints if state.name == "Scapula_L"
        )
        self.assertEqual(right.world_axes[0], (0.8, 0.6, 0.0))
        self.assertEqual(left.world_axes[0], (-0.8, 0.6, 0.0))
        self.assertFalse(use_case.plan().changes)

    def test_locked_body_joint_orient_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildBodySkeleton(host).apply()
        host.body = [
            replace(state, writable_joint_orient_axes=frozenset({"x", "y"}))
            if state.name == "Scapula_L"
            else state
            for state in host.body
        ]

        with self.assertRaisesRegex(
            BodySkeletonValidationError,
            "jointOrient 不可完整写入",
        ):
            OrientBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 1)

    def test_body_orientation_postcheck_failure_rolls_back_axes(self):
        host = FakeBodySkeletonHost()
        BuildBodySkeleton(host).apply()
        before = tuple(host.body)
        host.faulty_capture = True

        with self.assertRaisesRegex(RuntimeError, "朝向后复检失败"):
            OrientBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertEqual(tuple(host.body), before)

    def test_atomic_body_build_creates_and_orients_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        use_case = BuildOrientedBodySkeleton(host)

        preview = use_case.plan()

        self.assertTrue(preview.ready)
        self.assertFalse(host.body)
        result = use_case.apply()
        self.assertEqual(host.transaction_count, 1)
        self.assertEqual(len(result.snapshot.joints), 30)
        self.assertEqual(len(result.orientation_changes), 13)
        self.assertFalse(OrientBodySkeleton(host).plan().changes)
        audit = InspectBodySkeletonProvenance(host).execute()
        self.assertTrue(audit.owned)
        self.assertEqual(audit.snapshot.provenance, result.snapshot.provenance)

    def test_atomic_body_build_collision_stops_before_transaction(self):
        host = FakeBodySkeletonHost()
        host.collisions["Hip_L"] = ("|Existing|Hip_L",)

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildOrientedBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 0)
        self.assertFalse(host.body)

    def test_atomic_orientation_failure_removes_created_body(self):
        host = FakeBodySkeletonHost(faulty_after_orientation=True)

        with self.assertRaisesRegex(RuntimeError, "朝向后复检失败"):
            BuildOrientedBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertFalse(host.body)

    def test_atomic_provenance_failure_removes_created_body(self):
        host = FakeBodySkeletonHost(faulty_provenance=True)

        with self.assertRaisesRegex(RuntimeError, "关节数量不一致"):
            BuildOrientedBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertFalse(host.body)
        self.assertIsNone(host.provenance)


if __name__ == "__main__":
    unittest.main()
