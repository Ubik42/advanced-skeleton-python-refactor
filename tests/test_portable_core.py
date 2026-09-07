import unittest

from adv_py.application import BuildRig
from adv_py.adapters import InMemoryRigHost
from adv_py.core import NodeSpec, PlanValidationError, RigPlan, transpose_flat, translation_matrix, validate_plan
from adv_py.examples import two_joint_plan


def sample_plan() -> RigPlan:
    return two_joint_plan()


class PortableCoreTests(unittest.TestCase):
    def test_builds_the_same_plan_through_a_host_port(self) -> None:
        host = InMemoryRigHost()

        result = BuildRig(host).execute(sample_plan())

        self.assertEqual(result.created_nodes, 4)
        self.assertEqual(host.nodes["tip"].parent, "root")
        self.assertEqual(len(host.constraints), 2)

    def test_dry_run_does_not_mutate_host(self) -> None:
        host = InMemoryRigHost()

        result = BuildRig(host).execute(sample_plan(), dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(host.nodes, {})

    def test_rolls_back_the_last_successful_transaction(self) -> None:
        host = InMemoryRigHost()
        BuildRig(host).execute(sample_plan())

        host.rollback_last()

        self.assertEqual(host.nodes, {})
        self.assertEqual(host.constraints, [])

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

    def test_matrix_translation_survives_maya_layout_roundtrip(self) -> None:
        matrix = translation_matrix(1.0, 2.0, 3.0)

        self.assertEqual(transpose_flat(transpose_flat(matrix)), matrix)
