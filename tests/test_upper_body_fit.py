import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import BuildSyntheticUpperBodyFit
from adv_py.core import (
    IDENTITY_AXES,
    FitContainerDisplayStyle,
    FitContainerShape,
    FitContainerState,
    FitHierarchyNode,
    FitHierarchySnapshot,
    FitJointOrientationState,
    FitOrientationSnapshot,
    FitUpAxis,
    default_fit_skeleton_settings,
)


class FakeUpperBodyFitHost:
    def __init__(self, *, drift_after_create=False):
        self.container = "|FitSkeleton"
        self.created = []
        self.labels = {}
        self.orientations = {}
        self.settings = default_fit_skeleton_settings(self.container)
        self.transaction_count = 0
        self.orient_count = 0
        self.drift_after_create = drift_after_create
        self._drift_delivered = False

    def scene_up_axis(self):
        return FitUpAxis.Z

    def inspect_fit_container(self, name):
        del name
        return FitContainerState(
            path=self.container,
            short_name="FitSkeleton",
            shape=FitContainerShape.RING,
            display_style=FitContainerDisplayStyle.FIT,
            locked_channels=frozenset({"tx", "ty", "tz", "rx", "ry", "rz"}),
            local_translation=(0.0, 0.0, 0.0),
            local_rotation=(0.0, 0.0, 0.0),
            bounding_size=(6.0, 6.0, 0.0),
        )

    def capture_fit_hierarchy(self, container_name):
        del container_name
        world_positions = {}
        nodes = []
        for spec, path, parent in self.created:
            parent_world = world_positions.get(parent, (0.0, 0.0, 0.0))
            world = tuple(
                parent_value + local_value
                for parent_value, local_value in zip(
                    parent_world,
                    spec.local_position,
                )
            )
            world_positions[path] = world
            nodes.append(
                FitHierarchyNode(
                    path,
                    spec.name,
                    parent,
                    spec.local_position,
                    world,
                )
            )
        return FitHierarchySnapshot(
            self.container,
            tuple(sorted(nodes, key=lambda node: (node.path.count("|"), node.path))),
        )

    def capture_fit_orientation(self, container_name):
        hierarchy = self.capture_fit_hierarchy(container_name)
        if (
            self.drift_after_create
            and hierarchy.joints
            and not self._drift_delivered
        ):
            self._drift_delivered = True
            changed = replace(
                hierarchy.joints[-1],
                world_position=(99.0, 0.0, 0.0),
            )
            hierarchy = replace(
                hierarchy,
                joints=hierarchy.joints[:-1] + (changed,),
            )
        return FitOrientationSnapshot(
            hierarchy,
            FitUpAxis.Z,
            tuple(
                FitJointOrientationState(
                    node.path,
                    self.orientations.get(
                        node.path,
                        ((0.0, 0.0, 0.0), IDENTITY_AXES),
                    )[0],
                    (0.0, 0.0, 0.0),
                    self.orientations.get(
                        node.path,
                        ((0.0, 0.0, 0.0), IDENTITY_AXES),
                    )[1],
                )
                for node in hierarchy.joints
            ),
        )

    def read_fit_skeleton_settings(self, container_name):
        del container_name
        return self.settings

    def find_name_collisions(self, name):
        del name
        return ()

    @contextmanager
    def transaction(self, label):
        del label
        before = (
            list(self.created),
            dict(self.labels),
            dict(self.orientations),
            self.orient_count,
        )
        self.transaction_count += 1
        try:
            yield
        except Exception:
            (
                self.created,
                self.labels,
                self.orientations,
                self.orient_count,
            ) = before
            raise

    def create_fit_joint(self, parent, spec):
        path = f"{parent}|{spec.name}"
        self.created.append((spec, path, parent))
        return path

    def set_joint_label(self, joint, label):
        self.labels[joint] = label

    def read_joint_label(self, joint):
        return self.labels.get(joint)

    def orient_fit_joint(self, change):
        self.orient_count += 1
        self.orientations[change.joint] = (
            (10.0, 20.0, 30.0),
            (
                change.desired_primary_world,
                change.desired_secondary_world,
                (0.0, 0.0, 1.0),
            ),
        )


class UpperBodyFitTests(unittest.TestCase):
    def test_previews_then_builds_and_orients_in_one_transaction(self):
        host = FakeUpperBodyFitHost()
        use_case = BuildSyntheticUpperBodyFit(host)

        preview = use_case.plan()

        self.assertTrue(preview.ready)
        self.assertEqual(len(preview.predicted_orientation_changes), 11)
        self.assertFalse(host.created)
        result = use_case.apply()
        self.assertEqual(len(result.template.hierarchy.joints), 14)
        self.assertEqual(len(result.orientation.plan.changes), 11)
        self.assertEqual(host.transaction_count, 1)
        self.assertEqual(host.orient_count, 11)

    def test_plan_drift_rolls_back_the_created_tree(self):
        host = FakeUpperBodyFitHost(drift_after_create=True)

        with self.assertRaisesRegex(RuntimeError, "计划漂移"):
            BuildSyntheticUpperBodyFit(host).apply()

        self.assertFalse(host.created)
        self.assertFalse(host.labels)
        self.assertFalse(host.orientations)
        self.assertEqual(host.transaction_count, 1)


if __name__ == "__main__":
    unittest.main()
