import unittest

from adv_py.application import BuildRig
from adv_py.adapters import InMemoryRigHost
from adv_py.core import ConstraintSpec, NodeSpec, PlanValidationError, RigPlan, validate_plan


def sample_plan() -> RigPlan:
    return RigPlan(
        name="两节测试骨架",
        nodes=(
            NodeSpec(key="root", name="Root", kind="joint"),
            NodeSpec(key="tip", name="Tip", kind="joint", parent="root"),
            NodeSpec(key="ctrl", name="Root_CTRL", kind="control"),
        ),
        constraints=(
            ConstraintSpec(kind="parent", sources=("ctrl",), target="root"),
        ),
    )


class PortableCoreTests(unittest.TestCase):
    def test_builds_the_same_plan_through_a_host_port(self) -> None:
        host = InMemoryRigHost()

        result = BuildRig(host).execute(sample_plan())

        self.assertEqual(result.created_nodes, 3)
        self.assertEqual(host.nodes["tip"].parent, "root")
        self.assertEqual(len(host.constraints), 1)

    def test_dry_run_does_not_mutate_host(self) -> None:
        host = InMemoryRigHost()

        result = BuildRig(host).execute(sample_plan(), dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(host.nodes, {})

    def test_rejects_parent_cycle_before_mutation(self) -> None:
        invalid = RigPlan(
            name="循环",
            nodes=(
                NodeSpec(key="a", name="A", kind="joint", parent="b"),
                NodeSpec(key="b", name="B", kind="joint", parent="a"),
            ),
        )

        with self.assertRaises(PlanValidationError):
            validate_plan(invalid)

