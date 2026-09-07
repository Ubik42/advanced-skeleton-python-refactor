import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import EditFitJointPositions
from adv_py.core import (
    FitHierarchyNode,
    FitHierarchySnapshot,
    FitJointPositionEdit,
    FitJointPositionPatch,
    FitPositionValidationError,
    default_fit_skeleton_settings,
)


def hierarchy(*, spine_locked=False):
    writable = (
        frozenset({"x", "y"})
        if spine_locked
        else frozenset({"x", "y", "z"})
    )
    return FitHierarchySnapshot(
        container="|FitSkeleton",
        joints=(
            FitHierarchyNode(
                "|FitSkeleton|Root",
                "Root",
                "|FitSkeleton",
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0),
            ),
            FitHierarchyNode(
                "|FitSkeleton|Root|Spine1",
                "Spine1",
                "|FitSkeleton|Root",
                (0.0, 0.0, 4.0),
                (0.0, 0.0, 4.0),
                locked_translation_axes=(frozenset({"z"}) if spine_locked else frozenset()),
                writable_translation_axes=writable,
            ),
            FitHierarchyNode(
                "|FitSkeleton|Root|Spine1|Spine2",
                "Spine2",
                "|FitSkeleton|Root|Spine1",
                (0.0, 0.0, 4.0),
                (0.0, 0.0, 8.0),
            ),
        ),
    )


class FakeFitPositionHost:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or hierarchy()
        self.settings = default_fit_skeleton_settings(self.snapshot.container)
        self.transaction_count = 0
        self.set_count = 0

    def capture_fit_hierarchy(self, container_name):
        del container_name
        return self.snapshot

    def read_fit_skeleton_settings(self, container_name):
        del container_name
        return self.settings

    @contextmanager
    def transaction(self, label):
        del label
        before = self.snapshot
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.snapshot = before
            raise

    def set_fit_joint_local_position(self, joint, position, changed_axes):
        del changed_axes
        self.set_count += 1
        self.snapshot = replace(
            self.snapshot,
            joints=tuple(
                replace(node, local_position=position) if node.path == joint else node
                for node in self.snapshot.joints
            ),
        )


class FitPositionTests(unittest.TestCase):
    def test_plan_reports_only_effective_axis_changes(self) -> None:
        host = FakeFitPositionHost()
        patch = FitJointPositionPatch(
            (
                FitJointPositionEdit("Spine1", (0.0, 0.0, 5.0)),
                FitJointPositionEdit("Spine2", (0.0, 0.0, 4.0)),
            )
        )

        plan = EditFitJointPositions(host).plan(patch)

        self.assertEqual(len(plan.changes), 1)
        self.assertEqual(plan.changes[0].changed_axes, ("z",))
        self.assertEqual(host.transaction_count, 0)

    def test_locked_changed_axis_is_rejected_before_transaction(self) -> None:
        host = FakeFitPositionHost(hierarchy(spine_locked=True))
        patch = FitJointPositionPatch(
            (FitJointPositionEdit("Spine1", (0.0, 0.0, 5.0)),)
        )

        with self.assertRaisesRegex(FitPositionValidationError, "锁定"):
            EditFitJointPositions(host).apply(patch)

        self.assertEqual(host.transaction_count, 0)
        self.assertEqual(host.set_count, 0)

    def test_root_cannot_move_off_center(self) -> None:
        patch = FitJointPositionPatch(
            (FitJointPositionEdit("Root", (0.5, 0.0, 0.0)),)
        )

        with self.assertRaisesRegex(FitPositionValidationError, "中心"):
            EditFitJointPositions(FakeFitPositionHost()).plan(patch)

    def test_applies_batch_in_one_transaction(self) -> None:
        host = FakeFitPositionHost()
        patch = FitJointPositionPatch(
            (
                FitJointPositionEdit("Spine1", (0.0, 0.0, 5.0)),
                FitJointPositionEdit("Spine2", (0.0, 0.0, 3.0)),
            )
        )

        result = EditFitJointPositions(host).apply(patch)

        self.assertEqual(len(result.plan.changes), 2)
        self.assertEqual(host.transaction_count, 1)
        self.assertEqual(host.set_count, 2)

    def test_failed_post_verification_rolls_back(self) -> None:
        class FaultyHost(FakeFitPositionHost):
            def set_fit_joint_local_position(self, joint, position, changed_axes):
                del joint, position, changed_axes
                self.set_count += 1

        host = FaultyHost()
        before = host.snapshot
        patch = FitJointPositionPatch(
            (FitJointPositionEdit("Spine1", (0.0, 0.0, 5.0)),)
        )

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            EditFitJointPositions(host).apply(patch)

        self.assertEqual(host.snapshot, before)


if __name__ == "__main__":
    unittest.main()
