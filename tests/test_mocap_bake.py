from contextlib import contextmanager
from dataclasses import replace
import unittest

from adv_py.application.mocap_bake import BakeMocapBody
from adv_py.application.mocap_connection import ConnectMocapBody
from adv_py.core.mocap_bake import (
    MocapBodySample, plan_mocap_body_bake, validate_mocap_samples,
)
from adv_py.core.mocap_mapping import MocapMappingValidationError
from test_mocap_connection import FakeConnectionHost
from test_mocap_mapping import valid_mappings


class FakeBakeHost(FakeConnectionHost):
    def __init__(self):
        super().__init__()
        self.keys = None
        self.fail_readback = False
        self.fail_keys = False
        self.locked = False

    @contextmanager
    def transaction(self, label):
        before = self.keys
        try:
            with super().transaction(label):
                yield
        except Exception:
            self.keys = before
            raise

    def preflight_mocap_bake(self, plan):
        if self.locked:
            raise MocapMappingValidationError("locked")

    def sample_mocap_body(self, plan):
        return tuple(MocapBodySample(
            frame, tuple(float(frame + (1 if self.keys and self.fail_readback else 0))
                         for _ in plan.channels),
            self.capture_mocap_target_poses(plan.connection),
        ) for frame in plan.frames)

    def write_mocap_keys(self, plan, samples):
        self.keys = samples

    def verify_mocap_keys(self, plan, samples):
        if self.fail_keys:
            raise MocapMappingValidationError("bad keys")


class MocapBakeTests(unittest.TestCase):
    def setUp(self):
        self.host = FakeBakeHost()
        self.connection = ConnectMocapBody(self.host).execute(
            "|TakeA:Hips", valid_mappings(), expected_body_joint_count=3,
        ).plan
        self.host.transactions.clear()
        self.options = dict(start_frame=1, end_frame=9, sample_by=2, expected_body_joint_count=3)

    def run_bake(self):
        return BakeMocapBody(self.host).execute("|TakeA:Hips", valid_mappings(), **self.options)

    def test_explicit_plan_is_read_only(self):
        plan = BakeMocapBody(self.host).plan("|TakeA:Hips", valid_mappings(), **self.options)
        self.assertEqual(plan.frames, (1, 3, 5, 7, 9))
        self.assertEqual(len(plan.channels), 12)
        self.assertEqual(self.host.transactions, [])
        self.assertEqual(len(self.host.constraints), 3)

    def test_invalid_ranges_are_rejected(self):
        for start, end, step in ((True, 9, 1), (1, 9.0, 1), (9, 1, 1),
                                 (1, 9, 0), (1, 8, 2), (-2, 9, 1), (1, 100, 1)):
            with self.subTest(values=(start, end, step)), self.assertRaises(MocapMappingValidationError):
                plan_mocap_body_bake(self.connection, start, end, step)

    def test_bake_replaces_constraints_in_one_transaction(self):
        samples = self.run_bake()
        self.assertEqual(len(samples), 5)
        self.assertEqual(self.host.keys, samples)
        self.assertFalse(self.host.constraints)
        self.assertEqual(self.host.transactions, ["AdvPy Bake MoCap Body"])

    def test_missing_connection_and_locked_target_prevent_mutation(self):
        self.host.locked = True
        with self.assertRaises(MocapMappingValidationError):
            self.run_bake()
        self.host.locked = False
        self.host.constraints.clear()
        with self.assertRaises(MocapMappingValidationError):
            self.run_bake()
        self.assertFalse(self.host.transactions)

    def test_key_and_pose_failures_restore_connection(self):
        for flag in ("fail_keys", "fail_readback"):
            with self.subTest(flag=flag):
                setattr(self.host, flag, True)
                with self.assertRaises(MocapMappingValidationError):
                    self.run_bake()
                self.assertEqual(len(self.host.constraints), 3)
                self.assertEqual(len(self.host.inputs), 12)
                self.assertIsNone(self.host.keys)
                setattr(self.host, flag, False)

    def test_incomplete_and_nonfinite_samples_rejected(self):
        plan = plan_mocap_body_bake(self.connection, 1, 9, 2)
        samples = self.host.sample_mocap_body(plan)
        for invalid in (samples[:-1], (replace(samples[0], values=(float("nan"),) * 12),) + samples[1:],
                        (replace(samples[0], poses=()),) + samples[1:]):
            with self.assertRaises(MocapMappingValidationError):
                validate_mocap_samples(plan, invalid)


if __name__ == "__main__":
    unittest.main()
