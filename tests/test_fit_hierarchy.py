import unittest

from adv_py.application import InspectFitHierarchy
from adv_py.core import (
    FitHierarchyNode,
    FitHierarchyPolicy,
    FitHierarchySnapshot,
    FitHierarchyValidationError,
    audit_fit_hierarchy,
)


def node(path, name, parent, local=(0.0, 0.0, 0.0)):
    return FitHierarchyNode(
        path=path,
        short_name=name,
        dag_parent=parent,
        local_position=local,
        world_position=local,
    )


class FakeHierarchyHost:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def capture_fit_hierarchy(self, container_name):
        self.calls.append(container_name)
        return self.snapshot


class FitHierarchyTests(unittest.TestCase):
    def test_accepts_one_centered_root_and_joint_only_parent_chain(self) -> None:
        snapshot = FitHierarchySnapshot(
            container="|Group|FitSkeleton",
            joints=(
                node("|Group|FitSkeleton|Root", "Root", "|Group|FitSkeleton"),
                node(
                    "|Group|FitSkeleton|Root|Spine1",
                    "Spine1",
                    "|Group|FitSkeleton|Root",
                    (0.0, 5.0, 0.0),
                ),
            ),
        )
        host = FakeHierarchyHost(snapshot)

        audit = InspectFitHierarchy(host).execute("FitSkeleton")

        self.assertTrue(audit.valid)
        self.assertIs(audit.require_valid(), snapshot)
        self.assertEqual(host.calls, ["FitSkeleton"])

    def test_reports_root_name_position_and_ambiguous_joint_names(self) -> None:
        container = "|FitSkeleton"
        snapshot = FitHierarchySnapshot(
            container=container,
            joints=(
                node(
                    "|FitSkeleton|Bad_Root", "Bad_Root", container, (0.5, 0, 0)
                ),
                node(
                    "|FitSkeleton|Bad_Root|1Finger",
                    "1Finger",
                    "|FitSkeleton|Bad_Root",
                ),
                node(
                    "|FitSkeleton|Bad_Root|Palm|1Finger",
                    "1Finger",
                    "|FitSkeleton|Bad_Root|Palm",
                ),
            ),
        )

        issues = audit_fit_hierarchy(snapshot, FitHierarchyPolicy(center_tolerance=0.01))

        self.assertEqual(
            {issue.code for issue in issues},
            {
                "unexpected_root_name",
                "root_off_center",
                "underscore_in_name",
                "leading_digit",
                "duplicate_short_name",
                "non_joint_parent",
            },
        )

    def test_reports_multiple_roots_and_a_synthetic_parent_cycle(self) -> None:
        snapshot = FitHierarchySnapshot(
            container="|FitSkeleton",
            joints=(
                node("|FitSkeleton|Root", "Root", "|FitSkeleton"),
                node("|FitSkeleton|Extra", "Extra", "|FitSkeleton"),
                node("cycleA", "CycleA", "cycleB"),
                node("cycleB", "CycleB", "cycleA"),
            ),
        )
        audit = InspectFitHierarchy(FakeHierarchyHost(snapshot)).execute()

        self.assertEqual(
            {issue.code for issue in audit.issues},
            {"root_count", "parent_cycle"},
        )
        with self.assertRaisesRegex(FitHierarchyValidationError, "构建前校验失败"):
            audit.require_valid()


if __name__ == "__main__":
    unittest.main()
