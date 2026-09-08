from __future__ import annotations

from contextlib import contextmanager
import unittest

from adv_py.application import ConnectMocapBody, DisconnectMocapBody
from adv_py.core import (
    MocapBodyConnectionSnapshot,
    MocapConstraintKind,
    MocapConstraintState,
    MocapMappingValidationError,
    MocapTargetInputState,
    MocapTargetPose,
    oriented_body_provenance,
    plan_mocap_body_connection,
    plan_mocap_body_mapping,
)

from test_mocap_mapping import make_body, make_source, valid_mappings


class FakeConnectionHost:
    def __init__(self) -> None:
        self.source = make_source()
        self.body = make_body()
        self.constraints = {}
        self.inputs = {}
        self.foreign_names = set()
        self.transactions = []
        self.fail_structure = False

    def capture_mocap_source(self, root_name):
        return self.source

    def capture_body_skeleton(self, root_name):
        return self.body

    @contextmanager
    def transaction(self, label):
        before_constraints = dict(self.constraints)
        before_inputs = dict(self.inputs)
        self.transactions.append(label)
        try:
            yield
        except Exception:
            self.constraints = before_constraints
            self.inputs = before_inputs
            raise

    def find_mocap_name_collisions(self, plan):
        return tuple(
            spec.name for spec in plan.constraints
            if spec.name in self.constraints or spec.name in self.foreign_names
        )

    def capture_mocap_target_inputs(self, plan):
        return tuple(
            MocapTargetInputState(
                spec.target_path, attribute,
                self.inputs.get((spec.target_path, attribute)),
            )
            for spec in plan.constraints
            for attribute in spec.target_attributes
        )

    def capture_mocap_target_poses(self, plan):
        return tuple(
            MocapTargetPose(
                spec.target_path,
                (1.0, 0.0, 0.0, 0.0,
                 0.0, 1.0, 0.0, 0.0,
                 0.0, 0.0, 1.0, 0.0,
                 0.0, 0.0, 0.0, 1.0),
            )
            for spec in plan.constraints
        )

    def create_mocap_constraints(self, plan):
        for spec in plan.constraints:
            target = "|Wrong" if self.fail_structure else spec.target_path
            self.constraints[spec.name] = MocapConstraintState(
                spec.name, spec.source_path, target, spec.kind
            )
            for attribute in spec.target_attributes:
                self.inputs[(spec.target_path, attribute)] = spec.name

    def capture_mocap_connection(self, plan):
        return MocapBodyConnectionSnapshot(
            tuple(
                self.constraints[spec.name]
                for spec in plan.constraints if spec.name in self.constraints
            ),
            self.capture_mocap_target_inputs(plan),
        )

    def delete_mocap_constraints(self, plan):
        for spec in plan.constraints:
            del self.constraints[spec.name]
            for attribute in spec.target_attributes:
                self.inputs.pop((spec.target_path, attribute), None)


class MocapConnectionTests(unittest.TestCase):
    def test_plan_uses_parent_for_root_and_orient_for_descendants(self):
        mapping = plan_mocap_body_mapping(
            make_source(), make_body(), valid_mappings(),
            oriented_body_provenance("|FitSkeleton", 3),
        )

        plan = plan_mocap_body_connection(mapping)

        self.assertEqual(plan.constraints[0].kind, MocapConstraintKind.PARENT)
        self.assertEqual(len(plan.constraints[0].target_attributes), 6)
        self.assertTrue(all(
            item.kind is MocapConstraintKind.ORIENT
            for item in plan.constraints[1:]
        ))
        self.assertEqual(
            plan.constraints[0].name,
            "AdvPy_Mocap_Root_M_ParentConstraint",
        )

    def test_connect_builds_one_audited_transaction(self):
        host = FakeConnectionHost()

        result = ConnectMocapBody(host).execute(
            "|TakeA:Hips", valid_mappings(), expected_body_joint_count=3
        )

        self.assertEqual(len(result.snapshot.constraints), 3)
        self.assertEqual(host.transactions, ["AdvPy Connect MoCap Body"])
        self.assertEqual(len(host.inputs), 12)

    def test_connect_rejects_occupied_input_before_transaction(self):
        host = FakeConnectionHost()
        host.inputs[("|Root_M", "translateX")] = "foreignNode"

        with self.assertRaises(MocapMappingValidationError):
            ConnectMocapBody(host).execute(
                "|TakeA:Hips", valid_mappings(), expected_body_joint_count=3
            )

        self.assertEqual(host.transactions, [])
        self.assertEqual(host.constraints, {})

    def test_failed_postcheck_rolls_back_all_constraints(self):
        host = FakeConnectionHost()
        host.fail_structure = True

        with self.assertRaises(MocapMappingValidationError):
            ConnectMocapBody(host).execute(
                "|TakeA:Hips", valid_mappings(), expected_body_joint_count=3
            )

        self.assertEqual(host.constraints, {})
        self.assertEqual(host.inputs, {})

    def test_disconnect_deletes_only_an_exact_owned_connection(self):
        host = FakeConnectionHost()
        ConnectMocapBody(host).execute(
            "|TakeA:Hips", valid_mappings(), expected_body_joint_count=3
        )

        DisconnectMocapBody(host).execute(
            "|TakeA:Hips", valid_mappings(), expected_body_joint_count=3
        )

        self.assertEqual(host.constraints, {})
        self.assertEqual(host.inputs, {})
        self.assertEqual(host.transactions[-1], "AdvPy Disconnect MoCap Body")

    def test_disconnect_refuses_tampered_constraint(self):
        host = FakeConnectionHost()
        result = ConnectMocapBody(host).execute(
            "|TakeA:Hips", valid_mappings(), expected_body_joint_count=3
        )
        first = result.plan.constraints[0]
        host.constraints[first.name] = MocapConstraintState(
            first.name, first.source_path, "|ForeignBody", first.kind
        )

        with self.assertRaises(MocapMappingValidationError):
            DisconnectMocapBody(host).execute(
                "|TakeA:Hips", valid_mappings(), expected_body_joint_count=3
            )

        self.assertEqual(len(host.constraints), 3)


if __name__ == "__main__":
    unittest.main()
