import unittest
from contextlib import contextmanager
from copy import deepcopy

from adv_py.application import EditFitJointMetadata, InspectFitJoints
from adv_py.core import (
    FitJointField,
    FitJointMetadata,
    FitJointPatch,
    FitJointValidationError,
    predict_fit_joint_metadata,
)


class FakeFitJointHost:
    def __init__(self, metadata):
        self.metadata = {item.joint: item for item in metadata}
        self.transaction_count = 0
        self.apply_count = 0

    def resolve_joints(self, names):
        missing = [name for name in names if name not in self.metadata]
        if missing:
            raise FitJointValidationError(f"关节不存在：{missing[0]}")
        return tuple(names)

    def read_fit_joint_metadata(self, joint):
        return self.metadata[joint]

    @contextmanager
    def transaction(self, label):
        del label
        before = deepcopy(self.metadata)
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.metadata = before
            raise

    def apply_fit_joint_edit(self, joint, edit):
        self.apply_count += 1
        self.metadata[joint] = predict_fit_joint_metadata(
            self.metadata[joint], FitJointPatch((edit,))
        )


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

    def test_previews_and_applies_a_subdivision_mode_switch(self) -> None:
        metadata = FitJointMetadata(
            joint="|FitSkeleton|Arm",
            twist_joints=2,
            bendy_controls=1,
            present_fields=frozenset(
                {FitJointField.TWIST_JOINTS, FitJointField.BENDY_CONTROLS}
            ),
        )
        host = FakeFitJointHost((metadata,))
        editor = EditFitJointMetadata(host)
        patch = FitJointPatch.from_values(
            twist_joints=None,
            bendy_controls=None,
            inbetween_joints=3,
            untwister=True,
        )

        preview = editor.plan((metadata.joint,), patch)
        result = editor.apply((metadata.joint,), patch)

        self.assertEqual(len(preview.changes), 4)
        self.assertEqual(result.verified[0].inbetween_joints, 3)
        self.assertTrue(result.verified[0].untwister)
        self.assertEqual(host.transaction_count, 1)

    def test_invalid_final_state_is_rejected_without_a_transaction(self) -> None:
        metadata = FitJointMetadata(
            joint="|FitSkeleton|Arm",
            twist_joints=2,
            present_fields=frozenset({FitJointField.TWIST_JOINTS}),
        )
        host = FakeFitJointHost((metadata,))
        editor = EditFitJointMetadata(host)

        with self.assertRaisesRegex(FitJointValidationError, "不能同时"):
            editor.apply(
                (metadata.joint,),
                FitJointPatch.from_values(inbetween_joints=2),
            )

        self.assertEqual(host.transaction_count, 0)
        self.assertEqual(host.apply_count, 0)

    def test_post_verification_failure_rolls_back(self) -> None:
        metadata = FitJointMetadata(joint="|FitSkeleton|Arm")

        class FaultyHost(FakeFitJointHost):
            def apply_fit_joint_edit(self, joint, edit):
                self.apply_count += 1

        host = FaultyHost((metadata,))
        editor = EditFitJointMetadata(host)

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            editor.apply(
                (metadata.joint,),
                FitJointPatch.from_values(no_mirror=True),
            )

        self.assertEqual(host.metadata[metadata.joint], metadata)


if __name__ == "__main__":
    unittest.main()
