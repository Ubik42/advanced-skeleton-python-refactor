from __future__ import annotations

import unittest

from adv_py.core.face_eyelid_fit import (eye_lid_area_faces,
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


if __name__ == "__main__":
    unittest.main()
