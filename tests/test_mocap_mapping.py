from __future__ import annotations

import unittest

from adv_py.application import InspectMocapBodyMapping
from adv_py.core import (
    BodyJointState,
    BodySkeletonProvenanceState,
    BodySkeletonSnapshot,
    FitBuildSide,
    MocapChannelSnapshot,
    MocapDriverKind,
    MocapJointMapping,
    MocapJointSnapshot,
    MocapMappingValidationError,
    MocapSourceSnapshot,
    audit_mocap_body_mapping,
    oriented_body_provenance,
    plan_mocap_body_mapping,
)


def make_source() -> MocapSourceSnapshot:
    root = "|TakeA:Hips"
    spine = f"{root}|TakeA:Spine"
    head = f"{spine}|TakeA:Head"
    return MocapSourceSnapshot(
        root,
        (
            MocapJointSnapshot(root, "Hips", "TakeA", None),
            MocapJointSnapshot(spine, "Spine", "TakeA", root),
            MocapJointSnapshot(head, "Head", "TakeA", spine),
        ),
        (
            MocapChannelSnapshot(
                root,
                "translateX",
                MocapDriverKind.ANIMATION_CURVE,
                "TakeA:Hips_translateX.output",
                (1.0, 20.0),
            ),
            MocapChannelSnapshot(
                spine,
                "rotateX",
                MocapDriverKind.ANIMATION_CURVE,
                "TakeA:Spine_rotateX.output",
                (1.0, 10.0, 20.0),
            ),
        ),
    )


def make_body(*, owned: bool = True) -> BodySkeletonSnapshot:
    expected = oriented_body_provenance("|FitSkeleton", 3)
    provenance = BodySkeletonProvenanceState(
        owner=expected.owner if owned else "foreign",
        artifact_kind=expected.artifact_kind,
        schema_version=expected.schema_version,
        source_container=expected.source_container,
        body_joint_count=expected.body_joint_count,
    )
    root = "|Root_M"
    spine = f"{root}|Spine1_M"
    head = f"{spine}|Head_M"
    joints = tuple(
        BodyJointState(
            path=path,
            name=name,
            parent_path=parent,
            side=FitBuildSide.MIDDLE,
            world_position=(0.0, float(index), 0.0),
            label=None,
            joint_orient=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
        )
        for index, (path, name, parent) in enumerate((
            (root, "Root_M", None),
            (spine, "Spine1_M", root),
            (head, "Head_M", spine),
        ))
    )
    return BodySkeletonSnapshot(root, joints, provenance)


def valid_mappings() -> tuple[MocapJointMapping, ...]:
    return (
        MocapJointMapping("Hips", "Root_M", True, True),
        MocapJointMapping("Spine", "Spine1_M"),
        MocapJointMapping("Head", "Head_M"),
    )


class FakeMappingHost:
    def __init__(self) -> None:
        self.source_calls = []
        self.body_calls = []

    def capture_mocap_source(self, root_name):
        self.source_calls.append(root_name)
        return make_source()

    def capture_body_skeleton(self, root_name):
        self.body_calls.append(root_name)
        return make_body()


class MocapMappingTests(unittest.TestCase):
    def test_explicit_mapping_resolves_paths_channels_and_range(self):
        expected = oriented_body_provenance("|FitSkeleton", 3)

        plan = plan_mocap_body_mapping(
            make_source(), make_body(), valid_mappings(), expected
        )

        self.assertEqual(plan.source_namespace, "TakeA")
        self.assertEqual((plan.start_time, plan.end_time), (1.0, 20.0))
        self.assertEqual(plan.entries[0].source_path, "|TakeA:Hips")
        self.assertEqual(plan.entries[0].target_path, "|Root_M")
        self.assertEqual(plan.entries[0].animated_attributes, ("translateX",))
        self.assertEqual(plan.entries[1].animated_attributes, ("rotateX",))

    def test_duplicate_unknown_and_non_root_translation_are_reported(self):
        expected = oriented_body_provenance("|FitSkeleton", 3)
        mappings = (
            MocapJointMapping("Hips", "Root_M", True, True),
            MocapJointMapping("Spine", "Spine1_M", True, True),
            MocapJointMapping("Spine", "MissingTarget"),
        )

        codes = {
            issue.code
            for issue in audit_mocap_body_mapping(
                make_source(), make_body(), mappings, expected
            )
        }

        self.assertIn("duplicate_source_mapping", codes)
        self.assertIn("missing_target", codes)
        self.assertIn("non_root_translation", codes)

    def test_root_channels_topology_and_body_ownership_are_enforced(self):
        expected = oriented_body_provenance("|FitSkeleton", 3)
        reversed_mapping = (
            MocapJointMapping("Hips", "Root_M", True, False),
            MocapJointMapping("Spine", "Head_M"),
            MocapJointMapping("Head", "Spine1_M"),
        )

        codes = {
            issue.code
            for issue in audit_mocap_body_mapping(
                make_source(), make_body(owned=False), reversed_mapping, expected
            )
        }

        self.assertIn("incomplete_root_channels", codes)
        self.assertIn("topology_mismatch", codes)
        self.assertTrue(any(code.startswith("body_") for code in codes))

    def test_application_captures_each_side_once_before_returning_plan(self):
        host = FakeMappingHost()

        inspection = InspectMocapBodyMapping(host).execute(
            "|TakeA:Hips",
            valid_mappings(),
            expected_body_joint_count=3,
        )
        plan = inspection.require_valid()

        self.assertTrue(inspection.valid)
        self.assertEqual(len(plan.entries), 3)
        self.assertEqual(host.source_calls, ["|TakeA:Hips"])
        self.assertEqual(host.body_calls, ["Root_M"])
        with self.assertRaises(MocapMappingValidationError):
            InspectMocapBodyMapping(host).execute("", valid_mappings())


if __name__ == "__main__":
    unittest.main()
