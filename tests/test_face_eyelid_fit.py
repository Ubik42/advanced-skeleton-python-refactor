from __future__ import annotations

import unittest

from adv_py.core.face_eyelid_fit import (eye_lid_aperture_height,
                                          eye_lid_area_faces,
                                          eye_lid_blink_offsets,
                                          eye_lid_sphere_blink,
                                          order_eye_lid_loop)


class EyeLidLoopTest(unittest.TestCase):
    def setUp(self):
        self.positions = {
            0: (-.5, 0, 0), 1: (-.65, .2, 0),
            2: (-1, .3, 0), 3: (-1.35, .2, 0),
            4: (-1.5, 0, 0), 5: (-1.35, -.2, 0),
            6: (-1, -.3, 0), 7: (-.65, -.2, 0),
        }
        self.edges = tuple((index, index, (index + 1) % 8)
                           for index in range(8))

    def test_closed_ring_splits_into_ordered_upper_and_lower_arcs(self):
        ordered = order_eye_lid_loop(self.edges[::-1], self.positions,
                                     eye_center_y=0)
        self.assertEqual(ordered.upper_vertices, (0, 1, 2, 3, 4))
        self.assertEqual(ordered.lower_vertices, (0, 7, 6, 5, 4))
        self.assertEqual(ordered.edge_ids, tuple(range(8)))

    def test_open_or_branched_selection_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "闭环"):
            order_eye_lid_loop(self.edges[:-1], self.positions,
                                eye_center_y=0)
        branched = self.edges + ((8, 0, 4),)
        with self.assertRaisesRegex(ValueError, "分叉"):
            order_eye_lid_loop(branched, self.positions,
                                eye_center_y=0)

    def test_explicit_corners_override_extreme_vertices(self):
        ordered = order_eye_lid_loop(self.edges, self.positions,
                                     eye_center_y=0,
                                     corner_vertices=(5, 1))
        self.assertEqual(ordered.upper_vertices, (1, 2, 3, 4, 5))
        self.assertEqual(ordered.lower_vertices, (1, 0, 7, 6, 5))
        one_corner = order_eye_lid_loop(self.edges, self.positions,
                                        eye_center_y=0,
                                        corner_vertices=(1,))
        self.assertEqual(one_corner.upper_vertices[0], 1)
        self.assertEqual(one_corner.upper_vertices[-1], 4)
        with self.assertRaisesRegex(ValueError, "边环"):
            order_eye_lid_loop(self.edges, self.positions,
                                eye_center_y=0,
                                corner_vertices=(1, 99))

    def test_left_side_reverses_inner_outer_x_order(self):
        mirrored = {index: (-point[0], point[1], point[2])
                    for index, point in self.positions.items()}
        ordered = order_eye_lid_loop(self.edges, mirrored,
                                     eye_center_y=0, side="Left",
                                     corner_vertices=(5, 1))
        self.assertEqual(ordered.upper_vertices, (1, 2, 3, 4, 5))
        self.assertEqual(ordered.lower_vertices, (1, 0, 7, 6, 5))

    def test_inner_area_is_the_band_containing_main(self):
        faces = ((0, 1), (1, 2), (2, 3), (0,), (3,))
        edges = ((0, 3), (0, 1), (1, 2), (2, 4))
        area = eye_lid_area_faces(faces, edges, outer_edges=(0,),
                                  main_edges=(2,), inner_edges=(3,))
        self.assertEqual(area, (0, 1, 2))
        with self.assertRaisesRegex(ValueError, "封闭|围住"):
            eye_lid_area_faces(faces, edges, outer_edges=(0,),
                               main_edges=(2,), inner_edges=(1,))

    def test_open_inner_boundary_can_connect_around_outer_loop(self):
        faces = ((0, 1, 6), (1, 2), (2, 3), (3, 4, 6), (5,))
        edges = ((0,), (0, 1), (1, 2), (2, 3), (3,), (4,), (0, 3))
        area = eye_lid_area_faces(faces, edges, outer_edges=(1,),
                                  main_edges=(2,), inner_edges=(4,))
        self.assertEqual(area, (0, 1, 2, 3))
        with self.assertRaisesRegex(ValueError, "围住"):
            eye_lid_area_faces(faces, edges, outer_edges=(1,),
                               main_edges=(2,), inner_edges=(5,))

    def test_blink_meets_at_common_height_and_keeps_corners(self):
        points = {0: (0., 0., 0.), 1: (1., 2., 0.),
                  2: (2., 0., 0.), 3: (1., -1., 0.)}
        offsets = eye_lid_blink_offsets((0, 1, 2), (0, 3, 2), points)
        self.assertEqual(offsets["upper"][::2], (0., 0.))
        self.assertEqual(offsets["lower"][::2], (0., 0.))
        self.assertAlmostEqual(points[1][1] + offsets["upper"][1], -.1)
        self.assertAlmostEqual(points[3][1] + offsets["lower"][1], -.1)
        with self.assertRaisesRegex(ValueError, "交叉"):
            eye_lid_blink_offsets((0, 3, 2), (0, 1, 2), points)
        self.assertAlmostEqual(
            eye_lid_aperture_height((0, 1, 2), (0, 3, 2), points), 3.)

    def test_blink_tracks_front_of_eye_sphere_and_rolls_joint(self):
        depth, roll = eye_lid_sphere_blink((0., .2, .3),
                                            (0., 0., 0.), -.3)
        self.assertAlmostEqual((-.1)**2 + (.3 + depth)**2,
                               .2**2 + .3**2)
        self.assertGreater(depth, 0.)
        self.assertGreater(roll, 40.)
        lower_depth, lower_roll = eye_lid_sphere_blink(
            (0., -.2, .3), (0., 0., 0.), .1)
        self.assertGreater(lower_depth, 0.)
        self.assertLess(lower_roll, 0.)
        with self.assertRaisesRegex(ValueError, "坐标无效"):
            eye_lid_sphere_blink((0., float("inf"), .3),
                                  (0., 0., 0.), -.3)


if __name__ == "__main__":
    unittest.main()
