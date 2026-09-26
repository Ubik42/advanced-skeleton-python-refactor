import unittest
from types import SimpleNamespace

from adv_py.core.finger_mid_deform import plan_finger_mid_influences


def body_with_fingers(*, omit: str = ""):
    joints = []
    for side in ("R", "L"):
        for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
            parent = f"{finger}Finger2_{side}"
            tip = f"{finger}Finger3_{side}"
            if parent != omit:
                joints.append(SimpleNamespace(name=parent, path="|" + parent,
                    parent_path="|Wrist_" + side, world_position=(0., 0., 0.)))
            if tip != omit:
                joints.append(SimpleNamespace(name=tip,
                    path="|" + parent + "|" + tip,
                    parent_path="|" + parent,
                    world_position=(1., 2., 3.)))
    return SimpleNamespace(joints=tuple(joints))


class FingerMidPlanTests(unittest.TestCase):
    def test_plans_ten_helpers_under_their_direct_parents(self):
        specs = plan_finger_mid_influences(body_with_fingers())
        self.assertEqual(len(specs), 10)
        self.assertEqual(len({spec.name for spec in specs}), 10)
        self.assertEqual(specs[0].name, "ThumbFinger3_R_50")
        self.assertEqual(specs[0].zero_name, "ThumbFinger3_R_00")
        self.assertEqual(specs[0].parent, "|ThumbFinger2_R")
        self.assertEqual(specs[0].tip,
                         "|ThumbFinger2_R|ThumbFinger3_R")
        self.assertEqual(specs[0].position, (1., 2., 3.))

    def test_rejects_incomplete_finger_chain(self):
        with self.assertRaisesRegex(ValueError, "Finger2"):
            plan_finger_mid_influences(body_with_fingers(
                omit="IndexFinger2_L"))


if __name__ == "__main__":
    unittest.main()
