import unittest

from adv_py.application import InspectFitJoints
from adv_py.core import FitJointMetadata, FitJointValidationError


class FakeFitJointHost:
    def __init__(self, metadata):
        self.metadata = {item.joint: item for item in metadata}

    def resolve_joints(self, names):
        missing = [name for name in names if name not in self.metadata]
        if missing:
            raise FitJointValidationError(f"关节不存在：{missing[0]}")
        return tuple(names)

    def read_fit_joint_metadata(self, joint):
        return self.metadata[joint]


class FitMetadataTests(unittest.TestCase):
    def test_reads_a_valid_fit_joint_profile(self) -> None:
        metadata = FitJointMetadata(
            joint="|FitSkeleton|Arm",
            twist_joints=2,
            bendy_controls=1,
            no_mirror=True,
            no_mirror_left=True,
            world_orient_up="yUp",
        )

        audit = InspectFitJoints(FakeFitJointHost((metadata,))).execute(
            (metadata.joint,)
        )

        self.assertTrue(audit.valid)
        self.assertEqual(audit.joints, (metadata,))

    def test_reports_incompatible_optional_metadata(self) -> None:
        metadata = FitJointMetadata(
            joint="|FitSkeleton|Arm",
            twist_joints=2,
            inbetween_joints=2,
            untwister=True,
            no_mirror_left=True,
        )

        audit = InspectFitJoints(FakeFitJointHost((metadata,))).execute(
            (metadata.joint,)
        )

        self.assertFalse(audit.valid)
        self.assertEqual(
            {issue.code for issue in audit.issues},
            {"mixed_subdivision_modes", "left_rule_without_no_mirror"},
        )


if __name__ == "__main__":
    unittest.main()
