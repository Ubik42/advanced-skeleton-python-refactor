import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import OrientSimpleFitChain, OrientWorldFitJoints
from adv_py.core import (
    IDENTITY_AXES,
    FitHierarchyNode,
    FitHierarchySnapshot,
    FitJointOrientationState,
    FitJointMetadata,
    FitLocalDirection,
    FitOrientationAxisConfiguration,
    FitOrientationRequest,
    FitOrientationSnapshot,
    FitOrientationValidationError,
    FitUpAxis,
    FitWorldAxis,
    FitWorldOrientationPolicy,
    default_fit_skeleton_settings,
    plan_simple_fit_orientations,
    plan_world_fit_orientations,
    parse_world_orientation_policy,
    world_axes_from_orientation_policy,
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


def world_orientation_snapshot(*, forward="zForward"):
    snapshot = orientation_snapshot()
    return replace(
        snapshot,
        up_axis=FitUpAxis.Y,
        metadata=tuple(
            FitJointMetadata(
                joint=state.joint,
                world_orient_up="xDown" if state.joint.endswith("|Root") else None,
                world_orient_forward=forward
                if state.joint.endswith("|Root")
                else None,
            )
            for state in snapshot.joints
        ),
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

    def orient_world_fit_joint(self, change):
        self.orient_count += 1
        self.snapshot = replace(
            self.snapshot,
            joints=tuple(
                replace(
                    state,
                    joint_orient=(0.0, 0.0, -90.0),
                    world_axes=change.desired_world_axes,
                )
                if state.joint == change.joint
                else state
                for state in self.snapshot.joints
            ),
        )


class FitOrientationTests(unittest.TestCase):
    def test_builds_right_handed_world_axes_from_fixed_policy(self) -> None:
        axes = world_axes_from_orientation_policy(
            FitWorldOrientationPolicy(
                FitLocalDirection.NEGATIVE_X,
                FitLocalDirection.POSITIVE_Z,
            )
        )

        self.assertEqual(
            axes,
            ((0.0, -1.0, 0.0), (1.0, 0.0, -0.0), (0.0, 0.0, 1.0)),
        )

    def test_world_plan_uses_child_horizontal_direction_for_free_forward(self) -> None:
        snapshot = world_orientation_snapshot(forward="free")
        changes = plan_world_fit_orientations(
            snapshot,
            FitOrientationRequest(("Root",)),
        )

        self.assertEqual(len(changes), 1)
        self.assertEqual(
            changes[0].desired_world_axes,
            ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0)),
        )
        custom = plan_world_fit_orientations(
            replace(
                snapshot,
                axis_configuration=FitOrientationAxisConfiguration(
                    secondary=FitLocalDirection.POSITIVE_Z
                ),
            ),
            FitOrientationRequest(("Root",)),
        )
        self.assertEqual(
            custom[0].desired_world_axes,
            ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        )

    def test_world_plan_rejects_world_match_and_non_y_up_scene(self) -> None:
        with self.assertRaisesRegex(FitOrientationValidationError, "World Match"):
            plan_world_fit_orientations(
                replace(
                    world_orientation_snapshot(),
                    axis_configuration=FitOrientationAxisConfiguration(
                        world_match=True
                    ),
                ),
                FitOrientationRequest(("Root",)),
            )
        with self.assertRaisesRegex(FitOrientationValidationError, "Y-Up"):
            plan_world_fit_orientations(
                replace(world_orientation_snapshot(), up_axis=FitUpAxis.Z),
                FitOrientationRequest(("Root",)),
            )

    def test_applies_fixed_world_orientation_in_one_transaction(self) -> None:
        host = FakeFitOrientationHost(world_orientation_snapshot())
        result = OrientWorldFitJoints(host).apply(
            FitOrientationRequest(("Root",))
        )

        self.assertEqual(len(result.plan.changes), 1)
        self.assertEqual(host.orient_count, 1)
        self.assertEqual(host.transaction_count, 1)
        self.assertFalse(
            OrientWorldFitJoints(host).plan(FitOrientationRequest(("Root",))).changes
        )

    def test_failed_world_orientation_verification_rolls_back(self) -> None:
        class FaultyWorldHost(FakeFitOrientationHost):
            def orient_world_fit_joint(self, change):
                del change
                self.orient_count += 1

        host = FaultyWorldHost(world_orientation_snapshot())
        before = host.snapshot
        with self.assertRaisesRegex(RuntimeError, "世界轴不一致"):
            OrientWorldFitJoints(host).apply(FitOrientationRequest(("Root",)))

        self.assertEqual(host.snapshot, before)

    def test_parses_fixed_and_free_world_orientation_policies(self) -> None:
        fixed = parse_world_orientation_policy("xDown", "zForward")
        free = parse_world_orientation_policy("yUp", "free")

        self.assertEqual(fixed.up_local_direction, FitLocalDirection.NEGATIVE_X)
        self.assertEqual(
            fixed.forward_local_direction, FitLocalDirection.POSITIVE_Z
        )
        self.assertEqual(free.up_local_direction, FitLocalDirection.POSITIVE_Y)
        self.assertIsNone(free.forward_local_direction)

    def test_rejects_incomplete_or_conflicting_world_orientation_policy(self) -> None:
        with self.assertRaisesRegex(FitOrientationValidationError, "缺少"):
            parse_world_orientation_policy(None, "zForward")
        with self.assertRaisesRegex(FitOrientationValidationError, "同一本地轴"):
            parse_world_orientation_policy("xUp", "xBackward")

    def test_world_orientation_is_blocked_before_simple_chain_writes(self) -> None:
        snapshot = orientation_snapshot()
        snapshot = replace(
            snapshot,
            metadata=tuple(
                FitJointMetadata(
                    joint=state.joint,
                    world_orient_up="yUp" if state.joint.endswith("|Root") else None,
                    world_orient_forward="zForward"
                    if state.joint.endswith("|Root")
                    else None,
                )
                for state in snapshot.joints
            ),
        )

        with self.assertRaisesRegex(FitOrientationValidationError, "尚不支持"):
            plan_simple_fit_orientations(
                snapshot,
                FitOrientationRequest(("Root",)),
            )

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
