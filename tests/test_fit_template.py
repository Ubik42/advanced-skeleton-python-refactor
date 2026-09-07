import unittest
from contextlib import contextmanager

from adv_py.application import CreateFitTemplate, CreateMinimalFitTemplate
from adv_py.core import (
    FitHierarchyNode,
    FitHierarchySnapshot,
    FitJointSpec,
    FitSkeletonSettings,
    FitSkeletonValidationError,
    FitTemplateSpec,
    FitUpAxis,
    JointLabel,
    default_fit_skeleton_settings,
    minimal_body_fit_template,
    synthetic_body_source_fit_template,
    synthetic_upper_body_fit_template,
)


class FakeFitTemplateHost:
    def __init__(self):
        self.container = "|FitSkeleton"
        self.created = []
        self.labels = {}
        self.collisions = {}
        self.settings = default_fit_skeleton_settings(self.container)
        self.transaction_count = 0

    def scene_up_axis(self):
        return FitUpAxis.Z

    def capture_fit_hierarchy(self, container_name):
        del container_name
        nodes = tuple(
            FitHierarchyNode(
                path=path,
                short_name=spec.name,
                dag_parent=parent,
                local_position=spec.local_position,
                world_position=spec.local_position,
            )
            for spec, path, parent in self.created
        )
        return FitHierarchySnapshot(self.container, nodes)

    def read_fit_skeleton_settings(self, container_name):
        del container_name
        return self.settings

    def find_name_collisions(self, name):
        return tuple(self.collisions.get(name, ()))

    @contextmanager
    def transaction(self, label):
        del label
        before = (list(self.created), dict(self.labels))
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.created, self.labels = before
            raise

    def create_fit_joint(self, parent, spec):
        path = f"{parent}|{spec.name}"
        self.created.append((spec, path, parent))
        return path

    def set_joint_label(self, joint, label):
        self.labels[joint] = label

    def read_joint_label(self, joint):
        return self.labels.get(joint)


class FitTemplateTests(unittest.TestCase):
    def test_synthetic_body_source_adds_observable_leg_and_foot_topology(self):
        template = synthetic_body_source_fit_template(FitUpAxis.Z, scale=2.0)
        by_name = {joint.name: joint for joint in template.joints}

        self.assertEqual(len(template.joints), 22)
        self.assertEqual(by_name["Hip"].parent, "Root")
        self.assertEqual(by_name["Knee"].local_position, (0.0, 0.0, -8.0))
        self.assertEqual(
            {joint.name for joint in template.joints if joint.parent == "Ankle"},
            {"Heel", "Toes"},
        )
        self.assertEqual(
            {joint.name for joint in template.joints if joint.parent == "Toes"},
            {"FootSideInner", "FootSideOuter", "ToesEnd"},
        )

    def test_synthetic_upper_body_has_bilateral_z_up_branches(self) -> None:
        template = synthetic_upper_body_fit_template(FitUpAxis.Z, scale=2.0)
        by_name = {joint.name: joint for joint in template.joints}

        self.assertEqual(len(template.joints), 14)
        self.assertEqual(
            {joint.name for joint in template.joints if joint.parent == "Spine2"},
            {"Neck", "ClavicleLeft", "ClavicleRight"},
        )
        self.assertEqual(by_name["Spine1"].local_position, (0.0, 0.0, 6.0))
        self.assertEqual(by_name["ElbowLeft"].local_position, (6.0, 0.0, 0.0))
        self.assertEqual(by_name["ElbowRight"].local_position, (-6.0, 0.0, 0.0))

    def test_generic_creator_builds_upper_body_in_one_transaction(self) -> None:
        host = FakeFitTemplateHost()
        template = synthetic_upper_body_fit_template(FitUpAxis.Z)

        result = CreateFitTemplate(host).apply(template)

        self.assertEqual(len(result.hierarchy.joints), 14)
        self.assertEqual(len(host.labels), 14)
        self.assertEqual(host.transaction_count, 1)

    def test_minimal_template_follows_z_up(self) -> None:
        template = minimal_body_fit_template(FitUpAxis.Z, segment_length=4.0)

        self.assertEqual(
            tuple(joint.name for joint in template.joints),
            ("Root", "Spine1", "Spine2"),
        )
        self.assertEqual(template.joints[1].local_position, (0.0, 0.0, 4.0))

    def test_rejects_a_parent_cycle(self) -> None:
        label = JointLabel.parse("Spine")
        with self.assertRaisesRegex(FitSkeletonValidationError, "循环"):
            FitTemplateSpec(
                "cyclic",
                (
                    FitJointSpec("Root", None, (0, 0, 0), JointLabel.parse("Root")),
                    FitJointSpec("Spine1", "Spine2", (0, 1, 0), label),
                    FitJointSpec("Spine2", "Spine1", (0, 1, 0), label),
                ),
            )

    def test_preflight_reports_existing_hierarchy_and_name_collision(self) -> None:
        host = FakeFitTemplateHost()
        template = minimal_body_fit_template(FitUpAxis.Z)
        host.created.append(
            (template.joints[0], "|FitSkeleton|Root", "|FitSkeleton")
        )
        host.collisions["Root"] = ("|FitSkeleton|Root",)

        plan = CreateMinimalFitTemplate(host).plan(template=template)

        self.assertFalse(plan.ready)
        self.assertEqual(host.transaction_count, 0)

    def test_creates_and_verifies_three_joint_chain_in_one_transaction(self) -> None:
        host = FakeFitTemplateHost()

        result = CreateMinimalFitTemplate(host).apply(segment_length=4.0)

        self.assertEqual(
            tuple(node.short_name for node in result.hierarchy.joints),
            ("Root", "Spine1", "Spine2"),
        )
        self.assertEqual(len(host.labels), 3)
        self.assertEqual(host.transaction_count, 1)

    def test_label_verification_failure_rolls_back(self) -> None:
        class FaultyHost(FakeFitTemplateHost):
            def read_joint_label(self, joint):
                del joint
                return None

        host = FaultyHost()
        with self.assertRaisesRegex(RuntimeError, "标签不一致"):
            CreateMinimalFitTemplate(host).apply()

        self.assertFalse(host.created)
        self.assertFalse(host.labels)


if __name__ == "__main__":
    unittest.main()
