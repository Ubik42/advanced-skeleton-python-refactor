from __future__ import annotations

import unittest

from adv_py.application import InspectMocapSource
from adv_py.core import (
    MocapChannelSnapshot,
    MocapDriverKind,
    MocapJointSnapshot,
    MocapSourceSnapshot,
    MocapSourceValidationError,
    audit_mocap_source,
    summarize_mocap_source,
)


def make_snapshot() -> MocapSourceSnapshot:
    root = "|TakeA:Hips"
    spine = f"{root}|TakeA:Spine"
    head = f"{spine}|TakeA:Head"
    return MocapSourceSnapshot(
        root=root,
        joints=(
            MocapJointSnapshot(root, "Hips", "TakeA", None),
            MocapJointSnapshot(spine, "Spine", "TakeA", root),
            MocapJointSnapshot(head, "Head", "TakeA", spine),
        ),
        channels=(
            MocapChannelSnapshot(
                root,
                "translateX",
                MocapDriverKind.ANIMATION_CURVE,
                "TakeA:Hips_translateX.output",
                (1.0, 10.0, 20.0),
            ),
            MocapChannelSnapshot(
                spine,
                "rotateY",
                MocapDriverKind.ANIMATION_CURVE,
                "TakeA:Spine_rotateY.output",
                (1.0, 20.0),
            ),
        ),
    )


class FakeMocapHost:
    def __init__(self, snapshot: MocapSourceSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = []

    def capture_mocap_source(self, root_name: str) -> MocapSourceSnapshot:
        self.calls.append(root_name)
        return self.snapshot


class MocapSourceTests(unittest.TestCase):
    def test_valid_source_has_portable_names_and_clip_range(self):
        snapshot = make_snapshot()

        summary = summarize_mocap_source(snapshot)

        self.assertEqual(summary.namespace, "TakeA")
        self.assertEqual(summary.joint_count, 3)
        self.assertEqual(summary.animated_joint_count, 2)
        self.assertEqual(summary.channel_count, 2)
        self.assertEqual((summary.start_time, summary.end_time), (1.0, 20.0))
        self.assertEqual(summary.portable_joint_names, ("Hips", "Spine", "Head"))

    def test_duplicate_names_mixed_namespaces_and_broken_parent_are_reported(self):
        snapshot = make_snapshot()
        duplicate = MocapJointSnapshot(
            "|TakeA:Hips|Other:Branch|Other:Spine",
            "Spine",
            "Other",
            None,
        )
        damaged = MocapSourceSnapshot(
            snapshot.root,
            snapshot.joints + (duplicate,),
            snapshot.channels,
        )

        codes = {issue.code for issue in audit_mocap_source(damaged)}

        self.assertIn("mixed_namespaces", codes)
        self.assertIn("broken_joint_parent", codes)
        self.assertIn("duplicate_portable_name", codes)

    def test_non_curve_driver_and_invalid_key_times_are_rejected(self):
        snapshot = make_snapshot()
        unsafe = MocapSourceSnapshot(
            snapshot.root,
            snapshot.joints,
            (
                MocapChannelSnapshot(
                    snapshot.root,
                    "rotateX",
                    MocapDriverKind.OTHER,
                    "constraint1.outputX",
                    (),
                ),
                MocapChannelSnapshot(
                    snapshot.root,
                    "translateY",
                    MocapDriverKind.ANIMATION_CURVE,
                    "curve1.output",
                    (10.0, 1.0, 1.0),
                ),
            ),
        )

        codes = {issue.code for issue in audit_mocap_source(unsafe)}

        self.assertIn("unsupported_driver", codes)
        self.assertIn("invalid_key_times", codes)

    def test_inspection_captures_once_and_defers_failure_to_require_valid(self):
        empty = MocapSourceSnapshot("|Hips", (), ())
        host = FakeMocapHost(empty)

        inspection = InspectMocapSource(host).execute("|Hips")

        self.assertFalse(inspection.valid)
        self.assertEqual(host.calls, ["|Hips"])
        with self.assertRaises(MocapSourceValidationError):
            inspection.require_valid()
        with self.assertRaises(MocapSourceValidationError):
            InspectMocapSource(host).execute("  ")


if __name__ == "__main__":
    unittest.main()
