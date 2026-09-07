import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import OrientSimpleFitChain
from adv_py.core import (
    IDENTITY_AXES,
    FitHierarchyNode,
    FitHierarchySnapshot,
    FitJointOrientationState,
    FitOrientationRequest,
    FitOrientationSnapshot,
    FitOrientationValidationError,
    FitUpAxis,
    FitWorldAxis,
    default_fit_skeleton_settings,
    plan_simple_fit_orientations,
)


def orientation_snapshot(*, locked_joint=None):
    container = "|FitSkeleton"
    nodes = (
        FitHierarchyNode(
            f"{container}|Root",
            "Root",
            container,
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        ),
        FitHierarchyNode(
            f"{container}|Root|Spine1",
            "Spine1",
            f"{container}|Root",
            (0.0, 0.0, 4.0),
            (0.0, 0.0, 4.0),
        ),
        FitHierarchyNode(
            f"{container}|Root|Spine1|Spine2",
            "Spine2",
            f"{container}|Root|Spine1",
            (0.0, 0.0, 4.0),
            (0.0, 0.0, 8.0),
        ),
    )
    states = tuple(
        FitJointOrientationState(
            joint=node.path,
            joint_orient=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
            world_axes=IDENTITY_AXES,
            writable_joint_orient_axes=(
                frozenset({"x", "y"})
                if node.short_name == locked_joint
                else frozenset({"x", "y", "z"})
            ),
        )
        for node in nodes
    )
    return FitOrientationSnapshot(
        FitHierarchySnapshot(container, nodes),
        FitUpAxis.Z,
        states,
    )


class FakeFitOrientationHost:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or orientation_snapshot()
        self.settings = default_fit_skeleton_settings(
            self.snapshot.hierarchy.container
        )
        self.transaction_count = 0
        self.orient_count = 0

    def capture_fit_orientation(self, container_name):
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

    def orient_fit_joint(self, change):
        self.orient_count += 1
        self.snapshot = replace(
            self.snapshot,
            joints=tuple(
                replace(
                    state,
                    joint_orient=(10.0, 20.0, 30.0),
                    world_axes=(
                        change.desired_primary_world,
                        change.desired_secondary_world,
                        (1.0, 0.0, 0.0),
                    ),
                )
                if state.joint == change.joint
                else state
                for state in self.snapshot.joints
            ),
        )


class FitOrientationTests(unittest.TestCase):
    def test_z_up_parallel_chain_uses_world_y_as_fallback(self) -> None:
        changes = plan_simple_fit_orientations(
            orientation_snapshot(),
            FitOrientationRequest(("Root", "Spine1")),
        )

        self.assertEqual(len(changes), 2)
        self.assertTrue(
            all(change.secondary_world_axis is FitWorldAxis.Y for change in changes)
        )
        self.assertEqual(changes[0].desired_primary_world, (0.0, 0.0, 1.0))

    def test_leaf_and_locked_joint_are_rejected(self) -> None:
        with self.assertRaisesRegex(FitOrientationValidationError, "直接 joint 子级"):
            plan_simple_fit_orientations(
                orientation_snapshot(),
                FitOrientationRequest(("Spine2",)),
            )
        with self.assertRaisesRegex(FitOrientationValidationError, "不可完整写入"):
            plan_simple_fit_orientations(
                orientation_snapshot(locked_joint="Spine1"),
                FitOrientationRequest(("Spine1",)),
            )

    def test_applies_two_orientations_in_one_transaction(self) -> None:
        host = FakeFitOrientationHost()
        result = OrientSimpleFitChain(host).apply(
            FitOrientationRequest(("Root", "Spine1"))
        )

        self.assertEqual(len(result.plan.changes), 2)
        self.assertEqual(host.orient_count, 2)
        self.assertEqual(host.transaction_count, 1)

    def test_failed_orientation_verification_rolls_back(self) -> None:
        class FaultyHost(FakeFitOrientationHost):
            def orient_fit_joint(self, change):
                del change
                self.orient_count += 1

        host = FaultyHost()
        before = host.snapshot
        with self.assertRaisesRegex(RuntimeError, "轴向不一致"):
            OrientSimpleFitChain(host).apply(
                FitOrientationRequest(("Root",))
            )

        self.assertEqual(host.snapshot, before)


if __name__ == "__main__":
    unittest.main()
