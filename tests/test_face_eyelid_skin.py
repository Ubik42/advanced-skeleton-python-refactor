import unittest

from adv_py.core.face_eyelid_skin import (
    eyelid_skin_factors, inner_eyelid_skin_factors,
    outer_eyelid_skin_factors, split_arc_weight)


class EyeLidSkinFactorsTests(unittest.TestCase):
    def test_main_arcs_drive_separately_and_boundaries_stay_on_head(self):
        adjacency = {index: set() for index in range(25)}
        positions = {index: (float(index % 5), float(index // 5), 0.)
                     for index in range(25)}
        for row in range(5):
            for column in range(5):
                index = row * 5 + column
                for neighbor in ((index + 1,) if column < 4 else ()) + (
                        (index + 5,) if row < 4 else ()):
                    adjacency[index].add(neighbor)
                    adjacency[neighbor].add(index)
        boundary = {index for index in range(25)
                    if index // 5 in (0, 4) or index % 5 in (0, 4)}
        boundary.add(12)
        factors = eyelid_skin_factors(adjacency, positions, set(range(25)),
                    boundary, (6, 7, 8), (16, 17, 18), {12})
        self.assertEqual(factors[7], (1., 0.))
        self.assertEqual(factors[17], (0., 1.))
        self.assertEqual(factors[12], (0., 0.))
        self.assertTrue(all(factors[index] == (0., 0.) for index in boundary))
        shared_corners = boundary | {6, 8}
        shared = eyelid_skin_factors(adjacency, positions, set(range(25)),
                    shared_corners, (6, 7, 8), (16, 17, 18), {12})
        self.assertEqual(shared[6], (0., 0.))
        self.assertEqual(shared[8], (0., 0.))
        with self.assertRaisesRegex(ValueError, "主环无效"):
            eyelid_skin_factors(adjacency, positions, set(range(25)),
                    shared_corners | {7}, (6, 7, 8), (16, 17, 18), {12})

    def test_outer_falloff_and_arc_segment_interpolation(self):
        adjacency = {index: set() for index in range(25)}
        positions = {index: (float(index % 5), float(index // 5), 0.)
                     for index in range(25)}
        for index in range(25):
            for neighbor in (index - 1, index + 1,
                             index - 5, index + 5):
                if (0 <= neighbor < 25 and
                        abs(neighbor // 5 - index // 5)
                        + abs(neighbor % 5 - index % 5) == 1):
                    adjacency[index].add(neighbor)
        area = {6, 7, 8, 11, 12, 13, 16, 17, 18}
        main = {index: (0., 0.) for index in area}
        outer = outer_eyelid_skin_factors(adjacency, positions,
            area, (6, 7, 8), (16, 17, 18), {11, 12, 13}, main)
        self.assertAlmostEqual(sum(outer[7]), 1.)
        self.assertAlmostEqual(sum(outer[2]), .35 * 2 / 3)
        self.assertEqual(outer[12], (0., 0.))
        self.assertEqual(outer[7], (1., 0.))
        main[7] = (1./3., 0.)
        shared = outer_eyelid_skin_factors(adjacency, positions,
            area, (6, 7, 8), (16, 17, 18), {11, 12, 13}, main)
        self.assertAlmostEqual(sum(shared[7]), 2./3.)
        self.assertAlmostEqual(sum(shared[7]) + sum(main[7]), 1.)
        self.assertEqual(split_arc_weight(1.5, positions,
                         (6, 7, 8), .6), {6: .3, 7: .3})

    def test_open_aperture_inner_influence_fades_into_neighboring_row(self):
        adjacency = {index: set() for index in range(25)}
        positions = {index: (float(index % 5), float(index // 5), 0.)
                     for index in range(25)}
        for index in range(25):
            for neighbor in (index - 1, index + 1, index - 5, index + 5):
                if (0 <= neighbor < 25 and
                        abs(neighbor // 5 - index // 5)
                        + abs(neighbor % 5 - index % 5) == 1):
                    adjacency[index].add(neighbor)
        factors = inner_eyelid_skin_factors(adjacency, positions,
            set(range(25)), (16, 17, 18), (6, 7, 8))
        self.assertEqual(factors[17], (1., 0.))
        self.assertEqual(factors[7], (0., 1.))
        self.assertAlmostEqual(sum(factors[12]), 2./3.)
        self.assertEqual(factors[6], (0., 0.))

    def test_open_aperture_first_rim_vertices_keep_full_weight(self):
        positions = {0: (0., 0., 0.), 1: (.02, .4, 0.),
                     2: (.8, .4, 0.), 3: (1., 0., 0.),
                     4: (.02, -.4, 0.), 5: (.8, -.4, 0.)}
        adjacency = {index: set() for index in positions}
        for first, second in ((0, 1), (1, 2), (2, 3),
                              (3, 5), (5, 4), (4, 0)):
            adjacency[first].add(second)
            adjacency[second].add(first)
        factors = inner_eyelid_skin_factors(
            adjacency, positions, set(positions),
            (0, 1, 2, 3), (0, 4, 5, 3))
        self.assertEqual(factors[1], (1., 0.))
        self.assertEqual(factors[4], (0., 1.))
        self.assertEqual(factors[0], (0., 0.))
        self.assertEqual(factors[3], (0., 0.))
