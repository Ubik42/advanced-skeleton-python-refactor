import unittest
from types import SimpleNamespace

from adv_py.core.limb_part_deform import plan_limb_parts


def body(*, omit=""):
    joints = []
    for side in ("R", "L"):
        parent = "|Root"
        for stem, position in (("Shoulder", (0., 0., 0.)),
                               ("Elbow", (3., 0., 0.)),
                               ("Wrist", (6., 0., 0.))):
            name = f"{stem}_{side}"
            path = parent + "|" + name
            if name != omit:
                joints.append(SimpleNamespace(name=name, path=path,
                    parent_path=parent, world_position=position))
            parent = path
        parent = "|Root"
        for stem, position in (("Hip", (0., 5., 0.)),
                               ("Knee", (3., 5., 0.))):
            name = f"{stem}_{side}"
            path = parent + "|" + name
            if name != omit:
                joints.append(SimpleNamespace(name=name, path=path,
                    parent_path=parent, world_position=position))
            parent = path
    return SimpleNamespace(joints=tuple(joints))


class LimbPartPlanTests(unittest.TestCase):
    def test_plans_six_weighted_segments_with_original_joint_names(self):
        specs = plan_limb_parts(body())
        self.assertEqual(len(specs), 6)
        self.assertEqual({name for spec in specs for name in
            (spec.part1_name, spec.part2_name)}, {
                f"{stem}Part{index}_{side}"
                for side in ("R", "L")
                for stem in ("Shoulder", "Elbow", "Hip")
                for index in (1, 2)})
        shoulder = specs[0]
        self.assertEqual(shoulder.positions, ((1., 0., 0.), (2., 0., 0.)))
        self.assertEqual(shoulder.part1, shoulder.start + "|ShoulderPart1_R")
        self.assertEqual(shoulder.part2, shoulder.part1 + "|ShoulderPart2_R")
        self.assertEqual(shoulder.twist_source, shoulder.start + ".rotate")
        self.assertEqual(shoulder.fatness_control, "AdvPy_ArmIK_R")
        self.assertEqual(shoulder.fatness_attribute, "Fatness1")
        self.assertEqual(shoulder.volume_source,
                         "AdvPy_ArmVolumeBlend_R.outputR")
        elbow = specs[1]
        self.assertEqual(elbow.fatness_attribute, "Fatness2")
        self.assertEqual(elbow.up_twist_source,
                         "AdvPy_LowerArmTwistProject_R.outputRotateX")
        hip = specs[2]
        self.assertEqual(hip.fatness_control, "AdvPy_LegIK_R")
        self.assertEqual(hip.volume_source,
                         "AdvPy_LegVolumeBlend_R.outputR")
        self.assertEqual(hip.twist_source, "AdvPy_HipFKDriver_R.rotate")
        self.assertEqual(hip.twist_ik_source,
                         "AdvPy_HipIKDriver_R.rotate")
        self.assertEqual(hip.twist_mode_blend_name,
                         "AdvPy_HipPart_RTwistModeBlend")

    def test_rejects_missing_endpoint(self):
        with self.assertRaisesRegex(ValueError, "Hip_L"):
            plan_limb_parts(body(omit="Hip_L"))


if __name__ == "__main__":
    unittest.main()
