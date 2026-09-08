import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import BakeBodyRootMotion, BuildBodyRootMotion
from adv_py.core import (
    BodyJointState,
    BodyRootMotionBakedChannelState,
    BodyRootMotionBakedSnapshot,
    BodyRootMotionKeyState,
    BodyRootMotionSample,
    BodyRootMotionSnapshot,
    BodyRootMotionValidationError,
    BodySkeletonSnapshot,
    FitBuildSide,
    FitUpAxis,
    audit_baked_body_root_motion,
    audit_body_root_motion,
    oriented_body_provenance,
    plan_body_root_motion,
    plan_body_root_motion_bake,
)
from adv_py.core.body_skeleton import BodySkeletonProvenanceState
from adv_py.core.fit_settings import FitSkeletonValidationError


def make_plan(up_axis=FitUpAxis.Z, source="|Root_M"):
    return plan_body_root_motion(source_root_path=source, up_axis=up_axis)


def make_snapshot(plan):
    return BodyRootMotionSnapshot(
        output_path=plan.output_path,
        output_parent_path=None,
        output_type="joint",
        translation=(4.0, 2.0, 0.0),
        rotation=(0.0, 0.0, 35.0),
        scale=(1.0, 1.0, 1.0),
        joint_orient=(0.0, 0.0, 0.0),
        translation_sources=(
            f"{plan.point_constraint_name}.constraintTranslateX",
            f"{plan.point_constraint_name}.constraintTranslateY",
            None,
        ),
        rotation_sources=(
            None,
            None,
            f"{plan.orient_constraint_name}.constraintRotateZ",
        ),
        point_targets=(plan.source_root_path,),
        orient_targets=(plan.source_root_path,),
    )


def make_body(owned=True):
    provenance = oriented_body_provenance("|FitSkeleton", 1)
    state = BodySkeletonProvenanceState(
        owner=provenance.owner if owned else "foreign",
        artifact_kind=provenance.artifact_kind,
        schema_version=provenance.schema_version,
        source_container=provenance.source_container,
        body_joint_count=provenance.body_joint_count,
    )
    joint = BodyJointState(
        path="|Root_M",
        name="Root_M",
        parent_path=None,
        side=FitBuildSide.MIDDLE,
        world_position=(0.0, 0.0, 0.0),
        label=None,
        joint_orient=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0),
    )
    return BodySkeletonSnapshot("|Root_M", (joint,), state)


def make_samples(plan):
    return tuple(
        BodyRootMotionSample(
            frame=frame,
            translation=(float(frame), float(frame * 2), 0.0),
            rotation=(0.0, 0.0, float(frame * 3)),
        )
        for frame in plan.frames
    )


def make_baked_snapshot(plan, samples):
    translate_indices = {
        f"translate{axis.upper()}": "xyz".index(axis)
        for axis in plan.root_motion.translation_axes
    }
    channels = []
    for attribute in plan.channel_attributes:
        values = tuple(
            sample.translation[translate_indices[attribute]]
            if attribute in translate_indices
            else sample.rotation["xyz".index(plan.root_motion.rotation_axis)]
            for sample in samples
        )
        channels.append(BodyRootMotionBakedChannelState(
            attribute=attribute,
            source_kind="animation_curve",
            keys=tuple(
                BodyRootMotionKeyState(frame, value, "linear", "linear")
                for frame, value in zip(plan.frames, values)
            ),
        ))
    return BodyRootMotionBakedSnapshot(
        output_path=plan.root_motion.output_path,
        point_constraint_exists=False,
        orient_constraint_exists=False,
        channels=tuple(channels),
    )


class FakeRootMotionHost:
    def __init__(self, *, owned=True, collision=False):
        self.body = make_body(owned)
        self.collision = collision
        self.snapshot = None
        self.baked_snapshot = None
        self.transactions = 0

    def scene_up_axis(self):
        return FitUpAxis.Z

    def capture_body_skeleton(self, root_name):
        return self.body

    def find_name_collisions(self, name):
        return (f"|{name}",) if self.collision else ()

    @contextmanager
    def transaction(self, label):
        self.transactions += 1
        before = self.snapshot
        before_baked = self.baked_snapshot
        try:
            yield
        except Exception:
            self.snapshot = before
            self.baked_snapshot = before_baked
            raise

    def create_body_root_motion(self, plan):
        self.snapshot = make_snapshot(plan)

    def capture_body_root_motion(self, plan):
        return self.snapshot

    def sample_body_root_motion(self, plan):
        return make_samples(plan)

    def bake_body_root_motion(self, plan, samples):
        self.baked_snapshot = make_baked_snapshot(plan, samples)

    def capture_baked_body_root_motion(self, plan):
        return self.baked_snapshot


class BodyRootMotionTests(unittest.TestCase):
    def test_plan_maps_z_up_to_xy_translation_and_z_yaw(self):
        plan = make_plan()

        self.assertEqual(plan.translation_axes, ("x", "y"))
        self.assertEqual(plan.rotation_axis, "z")
        self.assertEqual(plan.skipped_translation_axis, "z")
        self.assertEqual(plan.skipped_rotation_axes, ("x", "y"))

    def test_plan_maps_y_up_and_preserves_source_namespace(self):
        plan = make_plan(FitUpAxis.Y, "|Hero:Root_M")

        self.assertEqual(plan.translation_axes, ("x", "z"))
        self.assertEqual(plan.rotation_axis, "y")
        self.assertEqual(plan.output_path, "|Hero:AdvPy_GameRootMotion")

    def test_plan_rejects_nested_source_and_qualified_output_basename(self):
        with self.assertRaises(BodyRootMotionValidationError):
            make_plan(source="|Group|Root_M")
        with self.assertRaises(BodyRootMotionValidationError):
            plan_body_root_motion(
                source_root_path="|Root_M",
                up_axis=FitUpAxis.Z,
                output_basename="Hero:RootMotion",
            )

    def test_audit_reports_filtered_axis_and_wiring_damage(self):
        plan = make_plan()
        snapshot = make_snapshot(plan)
        self.assertEqual(audit_body_root_motion(plan, snapshot), ())

        broken = replace(
            snapshot,
            translation=(4.0, 2.0, 1.0),
            rotation_sources=(None, None, None),
        )
        self.assertEqual(
            {issue.code for issue in audit_body_root_motion(plan, broken)},
            {"rotation_wiring_mismatch", "vertical_motion_mismatch"},
        )

    def test_application_builds_owned_body_in_one_transaction(self):
        host = FakeRootMotionHost()

        result = BuildBodyRootMotion(host).apply()

        self.assertEqual(result.verified.output_path, "|AdvPy_GameRootMotion")
        self.assertEqual(host.transactions, 1)

    def test_application_blocks_foreign_body_and_collisions_before_transaction(self):
        for host in (
            FakeRootMotionHost(owned=False),
            FakeRootMotionHost(collision=True),
        ):
            with self.subTest(host=host):
                with self.assertRaises(FitSkeletonValidationError):
                    BuildBodyRootMotion(host).apply()
                self.assertEqual(host.transactions, 0)
                self.assertIsNone(host.snapshot)

    def test_bake_plan_defines_inclusive_integer_samples(self):
        plan = plan_body_root_motion_bake(
            make_plan(),
            start_frame=1,
            end_frame=9,
            sample_by=2,
        )

        self.assertEqual(plan.frames, (1, 3, 5, 7, 9))
        self.assertEqual(
            plan.channel_attributes,
            ("translateX", "translateY", "rotateZ"),
        )
        for invalid in (
            {"start_frame": 5, "end_frame": 1, "sample_by": 1},
            {"start_frame": 1, "end_frame": 6, "sample_by": 2},
            {"start_frame": True, "end_frame": 5, "sample_by": 1},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(BodyRootMotionValidationError):
                    plan_body_root_motion_bake(make_plan(), **invalid)

    def test_baked_audit_requires_exact_linear_keys_and_no_constraints(self):
        plan = plan_body_root_motion_bake(
            make_plan(),
            start_frame=1,
            end_frame=3,
        )
        samples = make_samples(plan)
        snapshot = make_baked_snapshot(plan, samples)
        self.assertEqual(
            audit_baked_body_root_motion(plan, samples, snapshot),
            (),
        )

        first = snapshot.channels[0]
        broken_key = replace(first.keys[0], out_tangent="spline")
        broken = replace(
            snapshot,
            point_constraint_exists=True,
            channels=(
                replace(first, keys=(broken_key,) + first.keys[1:]),
            ) + snapshot.channels[1:],
        )
        self.assertEqual(
            {issue.code for issue in audit_baked_body_root_motion(
                plan,
                samples,
                broken,
            )},
            {"baked_constraint_remains", "baked_key_tangent_mismatch"},
        )

    def test_application_bakes_existing_driver_in_one_more_transaction(self):
        host = FakeRootMotionHost()
        BuildBodyRootMotion(host).apply()

        result = BakeBodyRootMotion(host).apply(
            start_frame=1,
            end_frame=3,
        )

        self.assertEqual(tuple(sample.frame for sample in result.samples), (1, 2, 3))
        self.assertEqual(len(result.verified.channels), 3)
        self.assertEqual(host.transactions, 2)


if __name__ == "__main__":
    unittest.main()
