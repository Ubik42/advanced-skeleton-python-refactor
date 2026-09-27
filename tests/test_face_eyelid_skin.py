import unittest

from adv_py.core.face_eyelid_skin import (
    eyelid_skin_factors, outer_eyelid_skin_factors, split_arc_weight)


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
                    boundary, (6, 7, 8), (16, 17, 18))
        self.assertEqual(factors[7], (.85, 0.))
        self.assertEqual(factors[17], (0., .85))
        self.assertEqual(factors[12], (0., 0.))
        self.assertTrue(all(factors[index] == (0., 0.) for index in boundary))

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
        outer = outer_eyelid_skin_factors(adjacency, positions,
            {6, 7, 8, 11, 12, 13, 16, 17, 18},
            (6, 7, 8), (16, 17, 18))
        self.assertAlmostEqual(sum(outer[7]), .35)
        self.assertAlmostEqual(sum(outer[2]), .35 * 2 / 3)
        self.assertNotIn(12, outer)
        self.assertEqual(split_arc_weight(1.5, positions,
                         (6, 7, 8), .6), {6: .3, 7: .3})
