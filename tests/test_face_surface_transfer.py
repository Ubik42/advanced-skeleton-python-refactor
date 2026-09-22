"""Cross-topology sculpt displacement projection and refusal boundaries."""
from dataclasses import replace
import unittest

from adv_py.core import (FaceMeshSnapshot, FaceShapeKind, FaceTargetAsset,
    transfer_face_target_asset)


class FaceSurfaceTransferTests(unittest.TestCase):
    def setUp(self):
        self.source = FaceMeshSnapshot("|Source", 3, "a" * 64,
            ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.)))
        self.target = FaceMeshSnapshot("|Target", 4, "b" * 64,
            ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (.25, .25, 0.)))
        self.asset = FaceTargetAsset("smile_R", FaceShapeKind.EXPRESSION, 3,
            self.source.topology_digest, self.source.position_digest,
            ((1, 1., 0., 0.),))

    def test_interpolates_sparse_displacement_across_topology(self):
        result = transfer_face_target_asset(self.source, self.target,
            ((0, 1, 2),), self.asset, max_distance=0.)
        self.assertEqual(result.asset.vertex_count, 4)
        self.assertEqual(result.asset.topology_digest, "b" * 64)
        self.assertEqual(result.asset.deltas, ((1, 1., 0., 0.),
                                               (3, .25, 0., 0.)))
        self.assertEqual(result.max_neutral_distance, 0.)
        self.assertEqual(result.transferred_vertex_count, 2)

    def test_rejects_far_surface_bad_faces_and_other_source(self):
        distant = replace(self.target, points=self.target.points[:3]
                          + ((.25, .25, 2.),))
        with self.assertRaisesRegex(ValueError, "目标顶点 3"):
            transfer_face_target_asset(self.source, distant, ((0, 1, 2),),
                                       self.asset, max_distance=.1)
        with self.assertRaisesRegex(ValueError, "三角面顶点索引"):
            transfer_face_target_asset(self.source, self.target, ((0, 0, 2),),
                                       self.asset, max_distance=0.)
        with self.assertRaisesRegex(ValueError, "基准位置"):
            transfer_face_target_asset(self.source, self.target, ((0, 1, 2),),
                replace(self.asset, neutral_position_digest="c" * 64),
                max_distance=0.)

    def test_spatial_tree_selects_nearest_triangle_on_grid(self):
        points = tuple((float(x), float(y), 0.)
                       for y in range(5) for x in range(5))
        source = FaceMeshSnapshot("|Grid", len(points), "d" * 64, points)
        triangles = []
        for y in range(4):
            for x in range(4):
                a = y * 5 + x
                triangles.extend(((a, a + 1, a + 5),
                                  (a + 1, a + 6, a + 5)))
        target = FaceMeshSnapshot("|GridOther", 3, "e" * 64,
            ((2., 2., 0.), (2.25, 2.25, 0.), (4., 4., 0.)))
        asset = FaceTargetAsset("smile_R", FaceShapeKind.EXPRESSION, 25,
            source.topology_digest, source.position_digest,
            ((12, 1., 0., 0.),))
        result = transfer_face_target_asset(source, target, tuple(triangles),
                                             asset, max_distance=0.)
        self.assertEqual(result.source_triangle_count, 32)
        self.assertAlmostEqual(result.asset.deltas[0][1], 1.)
        self.assertAlmostEqual(result.asset.deltas[1][1], .5)
        self.assertEqual(result.asset.deltas[-1][0], 1)


if __name__ == "__main__":
    unittest.main()
