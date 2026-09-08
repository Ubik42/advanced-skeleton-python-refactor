import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import BuildBodyExportSkeleton
from adv_py.core import (
    BODY_EXPORT_KIND,
    BODY_EXPORT_OWNER,
    BODY_EXPORT_SCHEMA_VERSION,
    BodyExportJointState,
    BodyExportSkeletonSnapshot,
    BodyJointState,
    BodyRootMotionSnapshot,
    BodySkeletonSnapshot,
    FitBuildSide,
    FitUpAxis,
    audit_body_export_skeleton,
    oriented_body_provenance,
    plan_body_export_skeleton,
    plan_body_root_motion,
)
from adv_py.core.body_skeleton import BodySkeletonProvenanceState
from adv_py.core.fit_settings import FitSkeletonValidationError


IDENTITY = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
)


def make_body(*, owned=True):
    provenance = oriented_body_provenance("|FitSkeleton", 3)
    provenance_state = BodySkeletonProvenanceState(
        owner=provenance.owner if owned else "foreign",
        artifact_kind=provenance.artifact_kind,
        schema_version=provenance.schema_version,
        source_container=provenance.source_container,
        body_joint_count=provenance.body_joint_count,
    )
    joints = tuple(
        BodyJointState(
            path=path,
            name=name,
            parent_path=parent,
            side=FitBuildSide.MIDDLE,
            world_position=position,
            label=None,
            joint_orient=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
            world_axes=IDENTITY,
        )
        for path, name, parent, position in (
            ("|Root_M", "Root_M", None, (0.0, 0.0, 0.0)),
            ("|Root_M|Spine1_M", "Spine1_M", "|Root_M", (0.0, 0.0, 4.0)),
            (
                "|Root_M|Spine1_M|Head_M",
                "Head_M",
                "|Root_M|Spine1_M",
                (0.0, 0.0, 8.0),
            ),
        )
    )
    return BodySkeletonSnapshot("|Root_M", joints, provenance_state)


def make_root_motion_plan():
    return plan_body_root_motion(
        source_root_path="|Root_M",
        up_axis=FitUpAxis.Z,
    )


def make_root_motion_snapshot(plan):
    return BodyRootMotionSnapshot(
        output_path=plan.output_path,
        output_parent_path=None,
        output_type="joint",
        translation=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0),
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


def make_export_snapshot(plan):
    states = []
    for spec in plan.joints:
        if spec.is_root:
            constraint = f"{spec.output_path}|{spec.root_constraint_name}"
            translate = tuple(
                f"{constraint}.constraintTranslate{axis}"
                for axis in "XYZ"
            )
            rotate = tuple(
                f"{constraint}.constraintRotate{axis}"
                for axis in "XYZ"
            )
        else:
            translate = tuple(
                f"{spec.source_path}.translate{axis}" for axis in "XYZ"
            )
            rotate = tuple(
                f"{spec.source_path}.rotate{axis}" for axis in "XYZ"
            )
        scale = tuple(
            f"{spec.source_path}.scale{axis}" for axis in "XYZ"
        )
        states.append(BodyExportJointState(
            source_path=spec.source_path,
            output_name=spec.output_name,
            output_path=spec.output_path,
            output_parent_path=spec.output_parent_path,
            side=spec.side,
            label=spec.label,
            joint_orient=spec.joint_orient,
            world_position=spec.world_position,
            world_axes=spec.world_axes,
            translation_sources=translate,
            rotation_sources=rotate,
            scale_sources=scale,
        ))
    return BodyExportSkeletonSnapshot(
        root_path=plan.root.output_path,
        joints=tuple(states),
        owner=BODY_EXPORT_OWNER,
        artifact_kind=BODY_EXPORT_KIND,
        schema_version=BODY_EXPORT_SCHEMA_VERSION,
        source_body_root=plan.source_body_root,
        joint_count=len(plan.joints),
    )


class FakeExportHost:
    def __init__(self, *, owned=True, collision=False):
        self.body = make_body(owned=owned)
        self.root_motion_plan = make_root_motion_plan()
        self.root_motion = make_root_motion_snapshot(self.root_motion_plan)
        self.export = None
        self.collision = collision
        self.transactions = 0

    def scene_up_axis(self):
        return FitUpAxis.Z

    def capture_body_skeleton(self, root_name):
        return self.body

    def capture_body_root_motion(self, plan):
        return self.root_motion

    def find_name_collisions(self, name):
        return (f"|{name}",) if self.collision else ()

    @contextmanager
    def transaction(self, label):
        self.transactions += 1
        before = self.export
        try:
            yield
        except Exception:
            self.export = before
            raise

    def create_body_export_skeleton(self, plan):
        self.export = make_export_snapshot(plan)

    def capture_body_export_skeleton(self, plan):
        return self.export


class BodyExportSkeletonTests(unittest.TestCase):
    def test_plan_builds_complete_hierarchy_below_root_motion(self):
        plan = plan_body_export_skeleton(make_body(), make_root_motion_plan())

        self.assertEqual(len(plan.joints), 3)
        self.assertEqual(
            plan.root.output_path,
            "|AdvPy_GameRootMotion|AdvPy_EXP_Root_M",
        )
        self.assertEqual(
            plan.joints[-1].output_parent_path,
            "|AdvPy_GameRootMotion|AdvPy_EXP_Root_M|AdvPy_EXP_Spine1_M",
        )
        self.assertIsNone(plan.joints[-1].root_constraint_name)

    def test_audit_requires_pose_provenance_and_exact_wiring(self):
        plan = plan_body_export_skeleton(make_body(), make_root_motion_plan())
        snapshot = make_export_snapshot(plan)
        self.assertEqual(audit_body_export_skeleton(plan, snapshot), ())

        second = snapshot.joints[1]
        broken = replace(
            snapshot,
            owner="foreign",
            joints=(
                snapshot.joints[0],
                replace(second, rotation_sources=(None, None, None)),
                snapshot.joints[2],
            ),
        )
        self.assertEqual(
            {issue.code for issue in audit_body_export_skeleton(plan, broken)},
            {"provenance_mismatch", "joint_wiring_mismatch"},
        )

    def test_application_builds_owned_export_hierarchy_in_one_transaction(self):
        host = FakeExportHost()

        result = BuildBodyExportSkeleton(host).apply()

        self.assertEqual(len(result.verified.joints), 3)
        self.assertEqual(host.transactions, 1)

    def test_application_blocks_foreign_body_and_collisions_before_transaction(self):
        for host in (
            FakeExportHost(owned=False),
            FakeExportHost(collision=True),
        ):
            with self.subTest(host=host):
                with self.assertRaises(FitSkeletonValidationError):
                    BuildBodyExportSkeleton(host).apply()
                self.assertEqual(host.transactions, 0)
                self.assertIsNone(host.export)


if __name__ == "__main__":
    unittest.main()
