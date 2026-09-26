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

    def test_rejects_missing_endpoint(self):
        with self.assertRaisesRegex(ValueError, "Hip_L"):
            plan_limb_parts(body(omit="Hip_L"))


if __name__ == "__main__":
    unittest.main()
