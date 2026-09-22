import unittest

from adv_py.core import (
    FaceMeshSnapshot, FaceShapeKind, FaceTarget, validate_face_targets,
)


class FaceShapesTests(unittest.TestCase):
    def test_expression_and_viseme_require_matching_topology_and_real_delta(self):
        topology = "a" * 64
        neutral = FaceMeshSnapshot("|Neutral", 3, topology,
            ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.)))
        smile = FaceMeshSnapshot("|Smile", 3, topology,
            ((0., 0., 0.), (1., .3, 0.), (0., 1., 0.)))
        viseme = FaceMeshSnapshot("|VisemeA", 3, topology,
            ((0., 0., 0.), (1., 0., 0.), (0., 1., .4)))
        targets = (
            (FaceTarget("smile_R", FaceShapeKind.EXPRESSION, "|Smile"), smile),
            (FaceTarget("viseme_A", FaceShapeKind.VISEME, "|VisemeA"), viseme),
        )
        validate_face_targets(neutral, targets)
        with self.assertRaisesRegex(ValueError, "拓扑"):
            validate_face_targets(neutral, (targets[0],
                (targets[1][0], FaceMeshSnapshot("|VisemeA", 3, "b" * 64,
                                                 viseme.points))))
        with self.assertRaisesRegex(ValueError, "有效形变"):
            validate_face_targets(neutral, ((targets[0][0],
                FaceMeshSnapshot("|Smile", 3, topology, neutral.points)),))
        with self.assertRaisesRegex(ValueError, "重复"):
            validate_face_targets(neutral, (targets[0],
                (FaceTarget("smile_R", FaceShapeKind.VISEME, "|VisemeA"), viseme)))


if __name__ == "__main__":
    unittest.main()
